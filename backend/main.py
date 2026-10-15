import logging
import os
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from app.routers import assignments, auth, submissions
from app.database import (
    Base,
    DATABASE_URL,
    classify_database_error,
    database_connection_target,
    engine,
    sanitize_database_error,
    SessionLocal,
)
from app.models import Rubric
from app.services.groq_models import ModelCategory, get_model
from app.migration import run_migrations
from app.services.document_parser import DocumentParser
import app.models  # Import models so they register with Base.metadata

logger = logging.getLogger(__name__)
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

def seed_default_rubric():
    db = SessionLocal()
    try:
        existing_rubric = db.query(Rubric).filter(Rubric.id == 1).first()
        if not existing_rubric:
            default_rubric = Rubric(
                id=1,
                name="Standard Assessment Rubric",
                description="Default evaluation rubric across core criteria",
                total_points=100,
                criteria=[
                    {"id": "clarity", "name": "Clarity", "description": "Clear and understandable", "weight": 1.0, "max_points": 15},
                    {"id": "completeness", "name": "Completeness", "description": "All requirements met", "weight": 1.0, "max_points": 20},
                    {"id": "code_quality", "name": "Code Quality", "description": "Well-written code", "weight": 1.0, "max_points": 15},
                    {"id": "correctness", "name": "Correctness", "description": "Correct solution", "weight": 1.5, "max_points": 25},
                    {"id": "documentation", "name": "Documentation", "description": "Well-documented", "weight": 0.75, "max_points": 10},
                    {"id": "organization", "name": "Organization", "description": "Well-organized", "weight": 0.75, "max_points": 10},
                    {"id": "originality", "name": "Originality", "description": "Original work", "weight": 0.5, "max_points": 5},
                ],
                is_active=True
            )
            db.add(default_rubric)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

app = FastAPI(title="AI Assignment Feedback Tool", version="0.1.0")
_groq_models_checked = False


@app.on_event("startup")
def initialize_database() -> None:
    if not os.getenv("JWT_SECRET", "").strip():
        raise RuntimeError("JWT_SECRET must be configured in the environment")
    missing_storage_settings = [
        setting
        for setting in (
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_BUCKET",
        )
        if not os.getenv(setting, "").strip()
    ]
    if missing_storage_settings:
        raise RuntimeError(
            "Supabase Storage settings are required: "
            + ", ".join(missing_storage_settings)
        )
    target = database_connection_target(DATABASE_URL)
    logger.info("Database connection target: %s", target)
    if target["host_kind"] == "supabase direct (db.<ref>.supabase.co)":
        logger.warning(
            "DATABASE_URL uses a Supabase direct database host. Direct connections are IPv6-only "
            "and will not work on Render; use the Supabase Session Pooler connection string."
        )

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            run_migrations(engine)
            seed_default_rubric()
            if not DocumentParser.tesseract_available():
                logger.warning(
                    "Tesseract OCR binary is unavailable; scanned/image-only submissions "
                    "will be marked unverifiable or not evaluated."
                )
            return
        except OperationalError as error:
            safe_message = sanitize_database_error(error)
            hint = classify_database_error(error)
            if attempt < max_attempts:
                delay = min(0.25 * (2 ** (attempt - 1)), 2.0)
                logger.warning(
                    "Database startup attempt failed: attempt=%s/%s exception_type=%s "
                    "message=%s hint=%s retry_in_seconds=%.2f",
                    attempt,
                    max_attempts,
                    type(error).__name__,
                    safe_message,
                    hint,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error(
                "Database startup failed: attempt=%s/%s exception_type=%s message=%s "
                "hint=%s target=%s",
                attempt,
                max_attempts,
                type(error).__name__,
                safe_message,
                hint,
                target,
            )
            raise RuntimeError(
                f"Unable to initialize Supabase PostgreSQL: {hint} Details: {safe_message}"
            ) from error
        except SQLAlchemyError as error:
            safe_message = sanitize_database_error(error)
            logger.error(
                "Database initialization failed: exception_type=%s message=%s target=%s",
                type(error).__name__,
                safe_message,
                target,
            )
            raise RuntimeError(
                f"Unable to initialize Supabase PostgreSQL: {safe_message}"
            ) from error


@app.on_event("startup")
async def log_groq_configuration() -> None:
    global _groq_models_checked
    api_key = os.getenv("GROQ_API_KEY", "")
    categories = {
        "classify": ModelCategory.CLASSIFY,
        "verify": ModelCategory.VERIFY,
        "grade_fast": ModelCategory.GRADE_FAST,
        "grade_reasoning": ModelCategory.GRADE_REASONING,
    }
    configured_models = {}
    for category, model_category in categories.items():
        try:
            configured_models[category] = get_model(model_category)
        except ValueError:
            configured_models[category] = "<not configured>"
    logger.info(
        "Groq configuration: GROQ_API_KEY loaded=%s; models=%s",
        bool(api_key),
        configured_models,
    )
    if not api_key or _groq_models_checked:
        return

    _groq_models_checked = True
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                GROQ_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            active_models = {
                entry.get("id")
                for entry in response.json().get("data", [])
                if isinstance(entry, dict) and isinstance(entry.get("id"), str)
            }
        for category, model_id in configured_models.items():
            if model_id not in active_models:
                logger.warning(
                    "Configured Groq model is not listed as active: category=%s model_id=%s",
                    category,
                    model_id,
                )
    except Exception as error:
        status_code = (
            error.response.status_code
            if isinstance(error, httpx.HTTPStatusError)
            else None
        )
        logger.warning(
            "Groq models list check failed: exception_type=%s http_status=%s",
            type(error).__name__,
            status_code,
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(assignments.router)
app.include_router(submissions.router)

@app.get("/health")
def health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        logger.error("Database health check failed: exception_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok", "database": "connected"}
