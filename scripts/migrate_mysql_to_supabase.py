"""One-off, re-runnable copy of local MySQL records and uploads to Supabase."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url
from sqlalchemy.sql.sqltypes import DateTime, JSON
from supabase import create_client

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.database import Base, normalize_database_url
from app.migration import run_migrations
import app.models


TABLE_ORDER = (
    "users",
    "assignments",
    "submissions",
    "verification_attempts",
    "rubrics",
    "evaluations",
    "feedback",
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set before running this migration")
    return value


def _source_file(path_value: str, repository_root: Path) -> Path:
    original = Path(path_value)
    candidates = [original] if original.is_absolute() else [
        Path.cwd() / original,
        repository_root / original,
        repository_root / "backend" / "uploads" / original.name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Local upload referenced by a submission is missing: {path_value}"
    )


def _upload_key(bucket, submission_id: int, local_path: Path) -> str:
    object_id = uuid5(NAMESPACE_URL, f"assignment-submission:{submission_id}").hex
    key = f"submissions/{object_id}{local_path.suffix.lower()}"
    bucket.upload(
        key,
        local_path.read_bytes(),
        file_options={
            "content-type": "application/octet-stream",
            "upsert": "true",
        },
    )
    return key


def _convert_row(
    row: dict,
    target_table: Table,
    repository_root: Path,
    storage_bucket,
    upload_files: bool,
) -> dict:
    converted = {}
    target_columns = {column.name: column for column in target_table.columns}
    for name, value in row.items():
        column = target_columns.get(name)
        if column is None:
            continue
        if target_table.name == "submissions" and name == "original_filename" and not value:
            file_path = row.get("file_path")
            value = Path(str(file_path)).name if file_path else None
        if value is None:
            converted[name] = None
            continue
        if isinstance(column.type, DateTime) and isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if isinstance(column.type, JSON) and isinstance(value, str):
            value = json.loads(value)
        if target_table.name == "submissions" and name == "file_path":
            path_value = str(value)
            converted["original_filename"] = row.get("original_filename") or Path(path_value).name
            if path_value.startswith("submissions/"):
                value = path_value
            else:
                local_path = _source_file(path_value, repository_root)
                if upload_files:
                    value = _upload_key(storage_bucket, int(row["id"]), local_path)
                else:
                    object_id = uuid5(NAMESPACE_URL, f"assignment-submission:{row['id']}").hex
                    value = f"submissions/{object_id}{local_path.suffix.lower()}"
        converted[name] = value
    return converted


def _load_rows(source_connection, source_inspector, repository_root, bucket, upload_files):
    rows_by_table = {}
    target_tables = Base.metadata.tables
    for table_name in TABLE_ORDER:
        if not source_inspector.has_table(table_name) or table_name not in target_tables:
            continue
        source_table = Table(table_name, MetaData(), autoload_with=source_connection)
        target_table = target_tables[table_name]
        source_rows = source_connection.execute(select(source_table)).mappings()
        rows_by_table[table_name] = [
            _convert_row(
                dict(row),
                target_table,
                repository_root,
                bucket,
                upload_files,
            )
            for row in source_rows
        ]
    return rows_by_table


def _reset_sequences(connection) -> None:
    for table_name in TABLE_ORDER:
        table = Base.metadata.tables.get(table_name)
        if table is None or "id" not in table.columns:
            continue
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                "COALESCE((SELECT MAX(id) FROM " + table_name + "), 1), "
                "(SELECT MAX(id) IS NOT NULL FROM " + table_name + "))"
            ),
            {"table_name": table_name},
        )


def migrate(apply_changes: bool) -> None:
    mysql_url = _required_env("MYSQL_DATABASE_URL")
    postgres_url = normalize_database_url(_required_env("DATABASE_URL"))
    supabase_url = _required_env("SUPABASE_URL")
    service_role_key = _required_env("SUPABASE_SERVICE_ROLE_KEY")
    bucket_name = _required_env("SUPABASE_BUCKET")

    try:
        source_engine = create_engine(mysql_url, pool_pre_ping=True)
    except ModuleNotFoundError as error:
        if error.name == "pymysql":
            raise RuntimeError(
                "Install pymysql in this one-off migration environment to read MySQL"
            ) from None
        raise
    target_engine = create_engine(
        make_url(postgres_url).update_query_dict({"sslmode": "require"}),
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=5,
    )
    storage_client = create_client(supabase_url, service_role_key)
    bucket = storage_client.storage.from_(bucket_name)
    repository_root = REPOSITORY_ROOT

    try:
        with source_engine.connect() as source_connection:
            rows_by_table = _load_rows(
                source_connection,
                inspect(source_connection),
                repository_root,
                bucket,
                upload_files=apply_changes,
            )
        summary = {name: len(rows) for name, rows in rows_by_table.items()}
        print(f"Source rows found: {summary}")
        if not apply_changes:
            print("Dry run only; no database rows or Storage objects were changed.")
            return

        Base.metadata.create_all(bind=target_engine)
        run_migrations(target_engine)
        with target_engine.begin() as connection:
            for table_name in TABLE_ORDER:
                rows = rows_by_table.get(table_name, [])
                if not rows:
                    continue
                table = Base.metadata.tables[table_name]
                statement = pg_insert(table).values(rows).on_conflict_do_nothing()
                connection.execute(statement)
            _reset_sequences(connection)
        print("Migration completed; existing destination IDs were left unchanged.")
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write rows and upload files (default is a read-only dry run)",
    )
    arguments = parser.parse_args()
    if arguments.apply:
        confirmation = input(
            "This writes to Supabase and uploads local files. Type MIGRATE to continue: "
        )
        if confirmation != "MIGRATE":
            raise SystemExit("Migration cancelled.")
    migrate(apply_changes=arguments.apply)


if __name__ == "__main__":
    main()
