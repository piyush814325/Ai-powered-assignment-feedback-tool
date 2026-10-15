import os
import re
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()


def normalize_database_url(database_url: str) -> str:
    try:
        database_url = database_url.strip().strip("\"'").strip()
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        url = make_url(database_url)
        if url.get_backend_name() != "postgresql" or url.port not in (None, 5432):
            raise ValueError
        return url.set(drivername="postgresql+psycopg2").render_as_string(
            hide_password=False
        )
    except (ArgumentError, ValueError, TypeError) as error:
        safe_cause = RuntimeError(
            f"{type(error).__name__}: {sanitize_database_error(error)}"
        )
        raise ValueError(
            "DATABASE_URL must be a valid Supabase PostgreSQL URL"
        ) from safe_cause


def database_connection_target(database_url: str) -> dict[str, Any]:
    url = make_url(database_url)
    host = url.host or "<missing>"
    if host.endswith(".pooler.supabase.com"):
        host_kind = "supabase pooler"
    elif host.startswith("db.") and host.endswith(".supabase.co"):
        host_kind = "supabase direct (db.<ref>.supabase.co)"
    else:
        host_kind = "other"

    username = url.username or "<missing>"
    username_prefix = username[:16] + ("..." if len(username) > 16 else "")
    return {
        "host": host,
        "port": url.port or 5432,
        "database": url.database or "<missing>",
        "username_prefix": username_prefix,
        "sslmode_set": url.query.get("sslmode") == "require",
        "host_kind": host_kind,
    }


def sanitize_database_error(error: BaseException) -> str:
    message = str(error)
    message = re.sub(
        r"(?i)(?:postgres(?:ql)?(?:\+\w+)?://)[^\s'\"<>]+",
        "[REDACTED_CONNECTION_URI]",
        message,
    )
    message = re.sub(
        r"(?i)\b(password|passwd|service_role_key|api[_-]?key)\s*[=:]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        message,
    )
    message = re.sub(
        r"(?i)(for user\s+)[\"']?[^\"'\s,;]+[\"']?",
        r"\1[REDACTED]",
        message,
    )
    return message[:1000] or type(error).__name__


def classify_database_error(error: BaseException) -> str:
    message = str(error).casefold()
    if any(
        phrase in message
        for phrase in (
            "could not translate host name",
            "could not resolve",
            "name or service not known",
            "temporary failure in name resolution",
            "network is unreachable",
            "no route to host",
        )
    ):
        return (
            "DNS or network failure: check the Supabase Session Pooler host. "
            "A direct db.<ref>.supabase.co connection is IPv6-only and will not work on Render."
        )
    if "password authentication failed" in message:
        return (
            "PostgreSQL rejected authentication: check the database password and URL-encode "
            "special characters in it."
        )
    if "tenant or user not found" in message:
        return (
            "Supabase pooler tenant/user was not found: use username postgres.<project-ref> "
            "and the correct region-specific pooler host."
        )
    if any(phrase in message for phrase in ("connection timed out", "connect timeout", "timeout expired")):
        return "Connection timed out: check the pooler host, port 5432, and whether the Supabase project is paused."
    if "ssl" in message or "tls" in message:
        return "SSL connection failed: ensure DATABASE_URL uses sslmode=require."
    return "Check DATABASE_URL and Supabase PostgreSQL availability."


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; configure the Supabase Session Pooler URL")

try:
    DATABASE_URL = normalize_database_url(DATABASE_URL)
except ValueError as error:
    raise RuntimeError(str(error)) from error

database_url = make_url(DATABASE_URL).update_query_dict({"sslmode": "require"})
DATABASE_URL = database_url.render_as_string(hide_password=False)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
