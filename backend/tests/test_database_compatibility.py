import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import (
    Base,
    classify_database_error,
    database_connection_target,
    engine,
    normalize_database_url,
    sanitize_database_error,
)
from app.migration import _ensure_indexes, _ensure_model_columns, run_migrations
from app.models import (
    Assignment,
    Evaluation,
    Submission,
    SUBMISSION_STUDENT_ASSIGNMENT_INDEX,
    SubmissionStatus,
    UploadBatch,
    UploadBatchStatus,
    User,
    UserRole,
)
from app.routers.assignments import delete_assignment
from app.routers.submissions import list_submissions
from app.services.file_storage import SupabaseStorage
from main import health_check


def _database_targets():
    targets = [("sqlite", "sqlite://")]
    test_database_url = os.getenv("TEST_DATABASE_URL") or os.getenv("TEST_POSTGRES_URL")
    if test_database_url:
        targets.append(("postgresql", test_database_url))
    return targets


@pytest.fixture(params=_database_targets(), ids=lambda target: target[0])
def compatibility_db(request):
    dialect, url = request.param
    if dialect == "sqlite":
        db_engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        normalized = normalize_database_url(url)
        db_engine = create_engine(normalized, pool_pre_ping=True)

    Base.metadata.create_all(bind=db_engine)
    if dialect == "postgresql":
        run_migrations(db_engine)
    session = Session(db_engine)
    try:
        yield session, db_engine
    finally:
        session.close()
        Base.metadata.drop_all(bind=db_engine)
        db_engine.dispose()


def _create_related_rows(db: Session):
    suffix = uuid4().hex
    teacher = User(
        email=f"teacher-{suffix}@example.test",
        full_name="Case Test Teacher",
        hashed_password="test-hash",
        role=UserRole.TEACHER,
    )
    student = User(
        email=f"Student-{suffix}@example.test",
        full_name="MiXeD Student",
        hashed_password="test-hash",
        role=UserRole.STUDENT,
    )
    db.add_all([teacher, student])
    db.flush()
    assignment = Assignment(
        teacher_id=teacher.id,
        subject_name="Data Structures",
        subject_code=f"CS-{suffix[:8]}",
        title="Binary tree",
        max_score=100,
        allowed_file_types=["pdf", "docx", "code"],
        rubric=[{"key": "correctness", "label": "Correctness", "max_points": 100}],
    )
    db.add(assignment)
    db.flush()
    submission = Submission(
        student_id=student.id,
        assignment_id=assignment.id,
        file_path="submissions/test.txt",
        file_type="txt",
        status=SubmissionStatus.UPLOADED,
    )
    db.add(submission)
    db.flush()
    return teacher, student, assignment, submission


def test_allowed_file_types_strip_legacy_txt_and_image_values():
    from app.routers.assignments import normalize_allowed_file_types

    assert normalize_allowed_file_types(["txt", "image", "pdf", "docx"]) == ["pdf", "docx"]
    assert normalize_allowed_file_types(["image", "txt"]) == ["pdf", "docx", "code"]
    assert normalize_allowed_file_types(["pdf", "docx", "code"]) == ["pdf", "docx", "code"]


def test_submission_unique_index_rejects_second_student_assignment_row():
    db_engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(bind=db_engine)
    db = Session(db_engine)
    try:
        _, student, assignment, _ = _create_related_rows(db)
        db.commit()
        db.add(Submission(
            student_id=student.id,
            assignment_id=assignment.id,
            file_path="submissions/second.py",
            file_type="code",
            status=SubmissionStatus.UPLOADED,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(Submission).filter(
            Submission.student_id == student.id,
            Submission.assignment_id == assignment.id,
        ).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=db_engine)
        db_engine.dispose()


def test_duplicate_submission_migration_skips_index_and_logs_counts(caplog):
    db_engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(bind=db_engine)
    db = Session(db_engine)
    try:
        _, student, assignment, first = _create_related_rows(db)
        db.commit()
        with db_engine.begin() as connection:
            connection.exec_driver_sql(
                f'DROP INDEX "{SUBMISSION_STUDENT_ASSIGNMENT_INDEX}"'
            )
        db.add(Submission(
            student_id=student.id,
            assignment_id=assignment.id,
            file_path="submissions/duplicate.py",
            file_type="code",
            status=SubmissionStatus.UPLOADED,
        ))
        db.commit()

        with caplog.at_level("WARNING"):
            _ensure_indexes(db_engine)

        assert db.query(Submission).filter(
            Submission.student_id == student.id,
            Submission.assignment_id == assignment.id,
        ).count() == 2
        index_names = {
            index["name"] for index in inspect(db_engine).get_indexes("submissions")
        }
        assert SUBMISSION_STUDENT_ASSIGNMENT_INDEX not in index_names
        assert "duplicate_groups=1 duplicate_rows=2" in caplog.text
        warning = next(
            record for record in caplog.records
            if "Skipped unique submission index" in record.message
        )
        assert warning.args == (1, 2)
    finally:
        db.close()
        Base.metadata.drop_all(bind=db_engine)
        db_engine.dispose()


def test_postgres_url_normalization():
    assert normalize_database_url(
        "postgres://user:password@host:5432/db"
    ) == "postgresql+psycopg2://user:password@host:5432/db"
    assert normalize_database_url(
        "postgresql://user:password@host:5432/db"
    ) == "postgresql+psycopg2://user:password@host:5432/db"
    with pytest.raises(ValueError, match="valid Supabase PostgreSQL URL"):
        normalize_database_url("mysql://user:password@host/db")
    with pytest.raises(ValueError, match="valid Supabase PostgreSQL URL"):
        normalize_database_url("postgresql://user:password@host:6543/db")


def test_postgres_url_normalization_strips_quotes_and_requires_ssl():
    normalized = normalize_database_url(
        '  "postgres://postgres.project-ref:pass%40word@aws-0-region.pooler.supabase.com:5432/postgres"\r\n'
    )
    parsed = make_url(normalized)
    assert parsed.drivername == "postgresql+psycopg2"
    assert parsed.password == "pass@word"


def test_engine_uses_postgres_pool_and_ssl_settings():
    assert engine.url.drivername == "postgresql+psycopg2"
    assert engine.url.query["sslmode"] == "require"
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 1800
    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 5


def test_connection_target_classifies_supabase_hosts_without_password():
    target = database_connection_target(
        "postgresql+psycopg2://postgres.project-ref:secret@"
        "aws-0-region.pooler.supabase.com:5432/postgres?sslmode=require"
    )
    assert target == {
        "host": "aws-0-region.pooler.supabase.com",
        "port": 5432,
        "database": "postgres",
        "username_prefix": "postgres.project...",
        "sslmode_set": True,
        "host_kind": "supabase pooler",
    }
    assert "secret" not in str(target)

    direct_target = database_connection_target(
        "postgresql://postgres:secret@db.project-ref.supabase.co:5432/postgres"
    )
    assert direct_target["host_kind"] == "supabase direct (db.<ref>.supabase.co)"


@pytest.mark.parametrize(
    ("message", "hint"),
    [
        ("could not translate host name", "DNS or network failure"),
        ("password authentication failed", "rejected authentication"),
        ("Tenant or user not found", "pooler tenant/user"),
        ("connection timed out", "timed out"),
        ("SSL SYSCALL error", "SSL connection failed"),
    ],
)
def test_database_error_classification(message, hint):
    assert hint in classify_database_error(RuntimeError(message))


def test_database_error_sanitization_removes_connection_credentials():
    error = RuntimeError(
        "failed postgres://postgres.project:top-secret@pooler.example/db "
        "password=top-secret for user 'postgres.project'"
    )
    safe_message = sanitize_database_error(error)
    assert "top-secret" not in safe_message
    assert "postgres.project" not in safe_message
    assert "[REDACTED_CONNECTION_URI]" in safe_message


def test_case_insensitive_email_and_name_lookup(compatibility_db):
    db, _ = compatibility_db
    teacher, student, _, submission = _create_related_rows(db)
    db.commit()

    by_email = db.query(User).filter(
        func.lower(User.email) == student.email.lower()
    ).one()
    name_results = list_submissions(
        student_name="mixed student",
        current_user=teacher,
        db=db,
    )
    db.add(User(
        email=student.email.swapcase(),
        full_name="Duplicate Student",
        hashed_password="test-hash",
        role=UserRole.STUDENT,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert by_email.id == student.id
    assert [result["id"] for result in name_results] == [submission.id]


def test_assignment_delete_removes_assignment_without_submissions(compatibility_db):
    db, _ = compatibility_db
    teacher, _, assignment, _ = _create_related_rows(db)
    db.delete(db.query(Submission).filter(Submission.assignment_id == assignment.id).one())
    db.commit()

    response = delete_assignment(assignment.id, teacher, db)

    assert response.status_code == 204
    assert db.get(Assignment, assignment.id) is None


def test_assignment_delete_removes_assignment_and_submission(compatibility_db):
    db, _ = compatibility_db
    teacher, _, assignment, submission = _create_related_rows(db)
    submission.file_path = None
    submission_id = submission.id
    db.commit()

    response = delete_assignment(assignment.id, teacher, db)

    assert response.status_code == 204
    assert db.get(Assignment, assignment.id) is None
    assert db.get(Submission, submission_id) is None


def test_mutable_json_values_persist(compatibility_db):
    db, _ = compatibility_db
    _, _, assignment, submission = _create_related_rows(db)
    evaluation = Evaluation(
        submission_id=submission.id,
        total_score=10,
        scores={"correctness": 10},
        feedback={"correctness": "Initial feedback"},
        evidence={"correctness": "Evidence"},
        ai_confidence=0.5,
        is_ai_generated=True,
        is_reviewed=False,
    )
    db.add(evaluation)
    db.commit()

    assignment.rubric.append({"key": "clarity", "label": "Clarity", "max_points": 0})
    evaluation.scores["correctness"] = 12
    evaluation.feedback["correctness"] = "Updated feedback"
    db.commit()
    db.expire_all()

    assert len(db.get(Assignment, assignment.id).rubric) == 2
    assert db.get(Evaluation, evaluation.id).scores["correctness"] == 12
    assert db.get(Evaluation, evaluation.id).feedback["correctness"] == "Updated feedback"


def test_large_extracted_text_persists(compatibility_db):
    db, db_engine = compatibility_db
    _, _, _, submission = _create_related_rows(db)
    long_text = "x" * 100_000
    submission.extracted_text = long_text
    submission.created_at = datetime(2026, 1, 1, 6, 30, tzinfo=timezone.utc)
    db.commit()
    db.expire_all()

    persisted = db.get(Submission, submission.id)
    assert len(persisted.extracted_text) == 100_000
    assert persisted.created_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 1, 1, 6, 30, tzinfo=timezone.utc
    )
    assert inspect(db_engine).has_table("submissions")


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def upload(self, key, content, file_options):
        self.objects[key] = content
        self.last_file_options = file_options

    def download(self, key):
        return self.objects[key]

    def remove(self, keys):
        for key in keys:
            self.objects.pop(key, None)

    def create_signed_url(self, key, expires_in):
        return {"signedURL": f"https://storage.test/{key}?expires={expires_in}"}


class FakeStorageClient:
    def __init__(self):
        self.bucket = FakeBucket()

    class Storage:
        def __init__(self, bucket):
            self.bucket = bucket

        def from_(self, _bucket_name):
            return self.bucket

    @property
    def storage(self):
        return self.Storage(self.bucket)


def test_supabase_storage_operations_and_upload_limit():
    client = FakeStorageClient()
    storage = SupabaseStorage(client, "private-uploads", max_upload_bytes=32)
    key = storage.save("answer.txt", b"assignment content", "text/plain")

    assert key.startswith("submissions/")
    assert key.endswith(".txt")
    assert storage.read(key) == b"assignment content"
    assert b"".join(storage.stream(key, chunk_size=5)) == b"assignment content"
    assert storage.signed_url(key, 30).endswith("expires=30")
    with pytest.raises(ValueError, match="exceeds"):
        storage.save("large.txt", b"x" * 33, "text/plain")
    storage.delete(key)
    assert key not in client.bucket.objects


def test_health_check_reports_database_success_and_failure(monkeypatch):
    class HealthyConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return None

    class HealthyEngine:
        def connect(self):
            return HealthyConnection()

    class UnhealthyEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    import main

    monkeypatch.setattr(main, "engine", HealthyEngine())
    assert health_check() == {"status": "ok", "database": "connected"}
    monkeypatch.setattr(main, "engine", UnhealthyEngine())
    with pytest.raises(HTTPException) as error:
        health_check()
    assert error.value.status_code == 503


def test_database_startup_retries_and_logs_sanitized_failure(monkeypatch, caplog):
    import main

    failure = OperationalError(
        "connect",
        {},
        RuntimeError("Tenant or user not found"),
    )

    class FailingEngine:
        attempts = 0

        def connect(self):
            self.attempts += 1
            raise failure

    fake_engine = FailingEngine()
    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(main.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        main,
        "DATABASE_URL",
        "postgresql://postgres.project-ref:test-password@"
        "aws-0-region.pooler.supabase.com:5432/postgres",
    )
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("SUPABASE_BUCKET", "private-uploads")

    with pytest.raises(RuntimeError, match="pooler tenant/user") as error:
        main.initialize_database()

    assert fake_engine.attempts == 5
    assert error.value.__cause__ is failure
    assert "test-password" not in caplog.text
    assert "test-service-role-key" not in caplog.text
    assert "Tenant or user not found" in caplog.text


def test_roster_schema_additions_are_idempotent_on_sqlite():
    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(bind=db_engine)
        with db_engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX ix_users_roll_no")
            connection.exec_driver_sql("ALTER TABLE users DROP COLUMN roll_no")
            for column in (
                "topic_text",
                "topic_number",
                "source",
                "roster_row_ref",
            ):
                connection.exec_driver_sql(
                    f"ALTER TABLE assignment_assignees DROP COLUMN {column}"
                )
        for _ in range(2):
            _ensure_model_columns(db_engine)
            _ensure_indexes(db_engine)
        inspector = inspect(db_engine)
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        assignee_columns = {
            column["name"] for column in inspector.get_columns("assignment_assignees")
        }
        assert "roll_no" in user_columns
        assert {
            "topic_text",
            "topic_number",
            "source",
            "roster_row_ref",
        }.issubset(assignee_columns)
        with db_engine.connect() as connection:
            index_names = set(
                connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='users'")
                ).scalars()
            )
        assert "ix_users_roll_no" in index_names
    finally:
        db_engine.dispose()


def test_upload_batch_name_addition_is_idempotent_and_preserves_legacy_rows():
    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(bind=db_engine)
        with Session(db_engine) as db:
            teacher = User(
                email=f"legacy-batch-{uuid4().hex}@example.test",
                full_name="Legacy Batch Owner",
                hashed_password="test-hash",
                role=UserRole.TEACHER,
            )
            db.add(teacher)
            db.flush()
            batch = UploadBatch(
                teacher_id=teacher.id,
                name=None,
                file_count=2,
                status=UploadBatchStatus.COMPLETED,
            )
            db.add(batch)
            db.commit()
            batch_id = batch.id

        with db_engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE upload_batches DROP COLUMN name")

        _ensure_model_columns(db_engine)
        inspector = inspect(db_engine)
        columns_after_first_startup = {
            column["name"] for column in inspector.get_columns("upload_batches")
        }
        with db_engine.connect() as connection:
            row_after_first_startup = connection.execute(
                text(
                    "SELECT id, teacher_id, file_count, status, name "
                    "FROM upload_batches WHERE id = :batch_id"
                ),
                {"batch_id": batch_id},
            ).one()

        _ensure_model_columns(db_engine)
        inspector = inspect(db_engine)
        columns_after_second_startup = {
            column["name"] for column in inspector.get_columns("upload_batches")
        }
        with db_engine.connect() as connection:
            row_after_second_startup = connection.execute(
                text(
                    "SELECT id, teacher_id, file_count, status, name "
                    "FROM upload_batches WHERE id = :batch_id"
                ),
                {"batch_id": batch_id},
            ).one()

        assert "name" in columns_after_first_startup
        assert columns_after_second_startup == columns_after_first_startup
        assert row_after_first_startup == row_after_second_startup
        assert row_after_second_startup.name is None
        assert row_after_second_startup.file_count == 2
        assert row_after_second_startup.status == UploadBatchStatus.COMPLETED.name
    finally:
        db_engine.dispose()


@pytest.mark.skipif(
    not (os.getenv("TEST_DATABASE_URL") or os.getenv("TEST_POSTGRES_URL")),
    reason="requires a disposable PostgreSQL test database",
)
def test_postgres_migrations_are_idempotent_and_rls_enabled():
    test_database_url = os.getenv("TEST_DATABASE_URL") or os.environ["TEST_POSTGRES_URL"]
    url = make_url(test_database_url)
    if not url.database:
        pytest.fail("TEST_DATABASE_URL must point to a dedicated disposable database")
    db_engine = create_engine(normalize_database_url(test_database_url))
    try:
        Base.metadata.create_all(bind=db_engine)
        run_migrations(db_engine)
        run_migrations(db_engine)
        with db_engine.connect() as connection:
            rls_tables = set(connection.execute(text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relrowsecurity"
            )).scalars())
            policies = connection.execute(text(
                "SELECT tablename, policyname FROM pg_policies "
                "WHERE schemaname = 'public'"
            )).all()
        inspector = inspect(db_engine)
        assert {
            "roll_no"
        }.issubset(
            {column["name"] for column in inspector.get_columns("users")}
        )
        assert {
            "topic_text",
            "topic_number",
            "source",
            "roster_row_ref",
        }.issubset(
            {
                column["name"]
                for column in inspector.get_columns("assignment_assignees")
            }
        )
        roll_index = next(
            index
            for index in inspector.get_indexes("users")
            if "roll_no" in index["column_names"]
        )
        assert roll_index["unique"] is False
        assert set(Base.metadata.tables).issubset(rls_tables)
        assert not [policy for policy in policies if policy.tablename in Base.metadata.tables]
    finally:
        Base.metadata.drop_all(bind=db_engine)
        db_engine.dispose()
