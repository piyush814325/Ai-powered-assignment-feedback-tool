import logging

from sqlalchemy import Column, inspect, text
from sqlalchemy.schema import CreateColumn

from app.database import Base
from app.models import SUBMISSION_STUDENT_ASSIGNMENT_INDEX

logger = logging.getLogger(__name__)


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
    inspector = inspect(engine)
    for table in Base.metadata.tables.values():
        if not inspector.has_table(table.name):
            continue
        if engine.dialect.name == "sqlite":
            with engine.connect() as connection:
                existing_names = set(
                    connection.execute(
                        text(
                            "SELECT name FROM sqlite_master "
                            "WHERE type = 'index' AND tbl_name = :table_name"
                        ),
                        {"table_name": table.name},
                    ).scalars()
                )
        else:
            existing_names = {
                index.get("name") for index in inspector.get_indexes(table.name)
            }
        skip_submission_unique_index = False
        if (
            table.name == "submissions"
            and SUBMISSION_STUDENT_ASSIGNMENT_INDEX not in existing_names
        ):
            with engine.connect() as connection:
                duplicate_groups, duplicate_rows = connection.execute(
                    text(
                        "SELECT COUNT(*), COALESCE(SUM(grouped.row_count), 0) "
                        "FROM (SELECT COUNT(*) AS row_count FROM submissions "
                        "WHERE student_id IS NOT NULL GROUP BY student_id, assignment_id "
                        "HAVING COUNT(*) > 1) AS grouped"
                    )
                ).one()
            if duplicate_groups:
                skip_submission_unique_index = True
                logger.warning(
                    "Skipped unique submission index because duplicates exist: "
                    "duplicate_groups=%s duplicate_rows=%s",
                    duplicate_groups,
                    duplicate_rows,
                )
        for index in table.indexes:
            if index.name in existing_names:
                continue
            if (
                skip_submission_unique_index
                and index.name == SUBMISSION_STUDENT_ASSIGNMENT_INDEX
            ):
                continue
            index.create(
                bind=engine,
                checkfirst=engine.dialect.name != "sqlite",
            )
            if index.name:
                existing_names.add(index.name)


def _ensure_foreign_keys(engine) -> None:
    inspector = inspect(engine)
    foreign_key_specs = (
        ("submissions", "teacher_override_by", "users", "fk_submissions_teacher_override_by_users"),
        ("submissions", "uploaded_by_teacher_id", "users", "fk_submissions_uploaded_by_teacher_users"),
        ("submissions", "teacher_confirmed_by", "users", "fk_submissions_teacher_confirmed_by_users"),
        ("submissions", "upload_batch_id", "upload_batches", "fk_submissions_upload_batch"),
        ("assignment_assignees", "assignment_id", "assignments", "fk_assignment_assignees_assignment"),
        ("assignment_assignees", "student_id", "users", "fk_assignment_assignees_student"),
        ("upload_batches", "teacher_id", "users", "fk_upload_batches_teacher"),
        ("upload_batches", "target_assignment_id", "assignments", "fk_upload_batches_target_assignment"),
        ("upload_batch_files", "batch_id", "upload_batches", "fk_upload_batch_files_batch"),
        ("upload_batch_files", "resolved_student_id", "users", "fk_upload_batch_files_student"),
        ("upload_batch_files", "resolved_assignment_id", "assignments", "fk_upload_batch_files_assignment"),
        ("upload_batch_files", "submission_id", "submissions", "fk_upload_batch_files_submission"),
    )
    preparer = engine.dialect.identifier_preparer
    for table_name, column_name, referred_table, constraint_name in foreign_key_specs:
        if not inspector.has_table(table_name) or not inspector.has_table(referred_table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if column_name not in columns:
            continue
        existing = inspector.get_foreign_keys(table_name)
        has_reference = any(
            foreign_key.get("constrained_columns") == [column_name]
            and foreign_key.get("referred_table") == referred_table
            for foreign_key in existing
        )
        if has_reference:
            continue
        table = preparer.quote(table_name)
        column = preparer.quote(column_name)
        target = preparer.quote(referred_table)
        constraint = preparer.quote(constraint_name)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                f"FOREIGN KEY ({column}) REFERENCES {target} (id)"
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
