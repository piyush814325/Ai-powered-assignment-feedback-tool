import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, engine, normalize_database_url
from app.migration import run_migrations
from app.models import Assignment, Evaluation, Submission, SubmissionStatus, User, UserRole
from app.routers.assignments import delete_assignment
from app.routers.submissions import list_submissions
from app.services.file_storage import SupabaseStorage
from main import health_check


def _database_targets():
    targets = [("sqlite", "sqlite://")]
    if os.getenv("TEST_POSTGRES_URL"):
        targets.append(("postgresql", os.environ["TEST_POSTGRES_URL"]))
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
        parsed_url = make_url(url)
        if not parsed_url.database or "test" not in parsed_url.database.casefold():
            pytest.fail("TEST_POSTGRES_URL must point to a dedicated database containing 'test'")
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
        allowed_file_types=["txt"],
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


def test_engine_uses_postgres_pool_and_ssl_settings():
    assert engine.url.drivername == "postgresql+psycopg2"
    assert engine.url.query["sslmode"] == "require"
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 1800
    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 5


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
    assert [result.id for result in name_results] == [submission.id]


def test_assignment_delete_removes_assignment_without_submissions(compatibility_db):
    db, _ = compatibility_db
    teacher, _, assignment, _ = _create_related_rows(db)
    db.delete(db.query(Submission).filter(Submission.assignment_id == assignment.id).one())
    db.commit()

    response = delete_assignment(assignment.id, teacher, db)

    assert response.status_code == 204
    assert db.get(Assignment, assignment.id) is None


def test_assignment_with_submissions_cannot_be_deleted(compatibility_db):
    db, _ = compatibility_db
    teacher, _, assignment, submission = _create_related_rows(db)

    with pytest.raises(HTTPException) as error:
        delete_assignment(assignment.id, teacher, db)

    assert error.value.status_code == 409
    assert db.get(Assignment, assignment.id) is not None
    assert db.get(Submission, submission.id) is not None


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


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="requires a disposable PostgreSQL test database")
def test_postgres_migrations_are_idempotent_and_rls_enabled():
    url = make_url(os.environ["TEST_POSTGRES_URL"])
    if not url.database or "test" not in url.database.casefold():
        pytest.fail("TEST_POSTGRES_URL must point to a dedicated database containing 'test'")
    db_engine = create_engine(normalize_database_url(os.environ["TEST_POSTGRES_URL"]))
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
        assert set(Base.metadata.tables).issubset(rls_tables)
        assert not [policy for policy in policies if policy.tablename in Base.metadata.tables]
    finally:
        Base.metadata.drop_all(bind=db_engine)
        db_engine.dispose()
