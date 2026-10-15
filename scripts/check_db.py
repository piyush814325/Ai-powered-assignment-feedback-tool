"""Check DATABASE_URL connectivity without displaying credentials."""

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

try:
    from sqlalchemy import text
    from app.database import (
        DATABASE_URL,
        classify_database_error,
        database_connection_target,
        engine,
        sanitize_database_error,
    )
except Exception as error:
    print(f"Database check failed: {type(error).__name__}: {error}")
    raise SystemExit(1) from None

try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    print(f"Database connection successful: {database_connection_target(DATABASE_URL)}")
except Exception as error:
    print(
        "Database connection failed: "
        f"exception_type={type(error).__name__}; "
        f"message={sanitize_database_error(error)}; "
        f"hint={classify_database_error(error)}; "
        f"target={database_connection_target(DATABASE_URL)}"
    )
    raise SystemExit(1) from None
finally:
    engine.dispose()
