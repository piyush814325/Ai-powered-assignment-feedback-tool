import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()


def normalize_database_url(database_url: str) -> str:
    try:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        url = make_url(database_url)
        if url.get_backend_name() != "postgresql" or url.port not in (None, 5432):
            raise ValueError
        return url.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)
    except (ArgumentError, ValueError, TypeError):
        raise ValueError("DATABASE_URL must be a valid Supabase PostgreSQL URL") from None


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; configure the Supabase Session Pooler URL")

try:
    DATABASE_URL = normalize_database_url(DATABASE_URL)
except ValueError as error:
    raise RuntimeError(str(error)) from None

database_url = make_url(DATABASE_URL)
database_url = database_url.update_query_dict({"sslmode": "require"})

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
