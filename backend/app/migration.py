from sqlalchemy import Column, inspect, text
from sqlalchemy.schema import CreateColumn

from app.database import Base
import app.models


def _ensure_model_columns(engine) -> None:
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            additive_column = Column(
                column.name,
                column.type,
                nullable=True,
                server_default=column.server_default,
            )
            ddl = CreateColumn(additive_column).compile(dialect=engine.dialect)
            quoted_table = engine.dialect.identifier_preparer.quote(table.name)
            with engine.begin() as connection:
                connection.exec_driver_sql(f"ALTER TABLE {quoted_table} ADD COLUMN {ddl}")


def _convert_legacy_types(engine) -> None:
    inspector = inspect(engine)
    preparer = engine.dialect.identifier_preparer
    for table_name, column_name, length in (
        ("users", "role", 7),
        ("submissions", "status", 15),
    ):
        if not inspector.has_table(table_name):
            continue
        column = next(
            (item for item in inspector.get_columns(table_name) if item["name"] == column_name),
            None,
        )
        if column and column["type"].__class__.__name__.lower() == "enum":
            table = preparer.quote(table_name)
            name = preparer.quote(column_name)
            with engine.begin() as connection:
                connection.exec_driver_sql(f"ALTER TABLE {table} ALTER COLUMN {name} DROP DEFAULT")
                connection.exec_driver_sql(
                    f"ALTER TABLE {table} ALTER COLUMN {name} TYPE VARCHAR({length}) "
                    f"USING {name}::text"
                )

    for table_name, column_names in (
        ("assignments", ["allowed_file_types", "rubric"]),
        ("submissions", ["verification_reasons", "verification_missing_requirements"]),
        ("evaluations", ["scores", "feedback", "evidence", "issues"]),
        ("rubrics", ["criteria"]),
    ):
        if not inspector.has_table(table_name):
            continue
        for column in inspector.get_columns(table_name):
            if column["name"] in column_names and column["type"].__class__.__name__.lower() == "json":
                table = preparer.quote(table_name)
                name = preparer.quote(column["name"])
                with engine.begin() as connection:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ALTER COLUMN {name} TYPE JSONB USING {name}::jsonb"
                    )

    for table_name, column_names in (
        ("users", ["created_at"]),
        ("assignments", ["due_date", "created_at", "updated_at"]),
        ("submissions", ["teacher_override_at", "created_at", "updated_at"]),
        ("verification_attempts", ["created_at"]),
        ("evaluations", ["created_at", "updated_at"]),
        ("rubrics", ["created_at"]),
        ("feedback", ["created_at"]),
    ):
        if not inspector.has_table(table_name):
            continue
        for column in inspector.get_columns(table_name):
            if column["name"] in column_names and getattr(column["type"], "timezone", True) is False:
                table = preparer.quote(table_name)
                name = preparer.quote(column["name"])
                with engine.begin() as connection:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ALTER COLUMN {name} "
                        f"TYPE TIMESTAMP WITH TIME ZONE USING {name} AT TIME ZONE 'UTC'"
                    )


def _ensure_indexes(engine) -> None:
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def _ensure_foreign_keys(engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("submissions") or not inspector.has_table("users"):
        return
    foreign_keys = inspector.get_foreign_keys("submissions")
    has_override_reference = any(
        foreign_key.get("constrained_columns") == ["teacher_override_by"]
        and foreign_key.get("referred_table") == "users"
        for foreign_key in foreign_keys
    )
    if not has_override_reference and "teacher_override_by" in {
        column["name"] for column in inspector.get_columns("submissions")
    }:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE submissions ADD CONSTRAINT "
                "fk_submissions_teacher_override_by_users "
                "FOREIGN KEY (teacher_override_by) REFERENCES users (id)"
            )


def _enable_row_level_security(engine) -> None:
    inspector = inspect(engine)
    preparer = engine.dialect.identifier_preparer
    for table_name in Base.metadata.tables:
        if inspector.has_table(table_name, schema="public"):
            quoted_table = preparer.quote(table_name)
            quoted_schema = preparer.quote("public")
            with engine.begin() as connection:
                policies = connection.execute(
                    text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname = 'public' AND tablename = :table_name"
                    ),
                    {"table_name": table_name},
                ).scalars()
                for policy_name in policies:
                    quoted_policy = preparer.quote(policy_name)
                    connection.exec_driver_sql(
                        f"DROP POLICY IF EXISTS {quoted_policy} "
                        f"ON {quoted_schema}.{quoted_table}"
                    )
                connection.exec_driver_sql(
                    f"ALTER TABLE {quoted_schema}.{quoted_table} ENABLE ROW LEVEL SECURITY"
                )


def run_migrations(engine) -> None:
    """Apply safe, additive PostgreSQL schema updates and enable RLS."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Only PostgreSQL is supported; configure the Supabase database URL")
    _ensure_model_columns(engine)
    _convert_legacy_types(engine)
    _ensure_foreign_keys(engine)
    _ensure_indexes(engine)
    _enable_row_level_security(engine)
