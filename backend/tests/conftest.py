import os
import re
import sqlite3

import pytest
from dotenv import load_dotenv
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _database_identity(
    database_url: str,
) -> tuple[str, str | None, int | None, str | None]:
    url = make_url(database_url)
    host = url.host or ""
    project_ref = None
    direct_host = re.fullmatch(r"db\.([^.]+)\.supabase\.co", host)
    pooler_user = re.fullmatch(r"postgres\.([^.]+)", url.username or "")
    if direct_host:
        project_ref = direct_host.group(1)
    elif pooler_user and host.endswith(".pooler.supabase.com"):
        project_ref = pooler_user.group(1)
    if project_ref:
        return url.get_backend_name(), project_ref, None, None
    return url.get_backend_name(), url.host, url.port, url.database


def pytest_configure() -> None:
    load_dotenv()
    application_url = os.getenv("DATABASE_URL")
    test_url = os.getenv("TEST_DATABASE_URL") or os.getenv("TEST_POSTGRES_URL")
    if application_url and test_url:
        try:
            same_database = _database_identity(application_url) == _database_identity(test_url)
        except (ArgumentError, ValueError, TypeError):
            same_database = application_url == test_url
        if same_database:
            raise pytest.UsageError(
                "Refusing to run tests: TEST_DATABASE_URL must not target DATABASE_URL"
            )
