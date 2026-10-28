import io
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db, normalize_database_url
from app.models import (
    Assignment,
    AssignmentAssignee,
    Evaluation,
    Feedback,
    StudentMatchStatus,
    Submission,
    SubmissionSource,
    SubmissionStatus,
    UploadBatch,
    UploadBatchFile,
    UploadBatchFileStatus,
    UploadBatchStatus,
    Rubric,
    User,
    UserRole,
    VerificationAttempt,
)
from app.routers import assignments, auth, roster_import, submissions, teacher_uploads
from app.routers.auth import get_current_user
from app.services import auth_service, excel_parser
from app.services.roster_cells import normalize_roll_no


class MemoryStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.saved_keys: list[str] = []
        self.fail_read: set[str] = set()

    def save(self, filename: str, content: bytes, _content_type: str) -> str:
        key = f"submissions/{uuid4().hex}.{filename.rsplit('.', 1)[-1]}"
        self.files[key] = content
        self.saved_keys.append(key)
        return key

    def read(self, key: str) -> bytes:
        if key in self.fail_read:
            raise OSError("test storage read failure")
        return self.files[key]

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


@pytest.fixture
def upload_test_context(monkeypatch):
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if test_database_url:
        engine = create_engine(
            normalize_database_url(test_database_url),
            pool_pre_ping=True,
        )
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    if engine.dialect.name == "postgresql":
        table_names = ", ".join(
            f'"{table.name}"' for table in Base.metadata.sorted_tables
        )
        with engine.begin() as connection:
            connection.execute(
                text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
            )
    setup = factory()
    suffix = uuid4().hex[:8]
    teacher = User(
        email=f"teacher-{suffix}@example.test",
        full_name="Teacher One",
        hashed_password="hash",
        role=UserRole.TEACHER,
    )
    other_teacher = User(
        email=f"teacher-other-{suffix}@example.test",
        full_name="Teacher Two",
        hashed_password="hash",
        role=UserRole.TEACHER,
    )
    student = User(
        email=f"vexari-{suffix}@example.test",
        full_name="Vexari Quorium",
        hashed_password="hash",
        role=UserRole.STUDENT,
    )
    similar_student = User(
        email=f"vexari-two-{suffix}@example.test",
        full_name="Vexari Quoriumx",
        hashed_password="hash",
        role=UserRole.STUDENT,
    )
    admin = User(
        email=f"admin-{suffix}@example.test",
        full_name="Admin",
        hashed_password="hash",
        role=UserRole.ADMIN,
    )
    rubric = Rubric(
        name="Upload test rubric",
        description="Fixture rubric",
        total_points=100,
        criteria=[{"id": "one", "name": "One", "weight": 1, "max_points": 100}],
    )
    setup.add_all([teacher, other_teacher, student, similar_student, admin, rubric])
    setup.flush()
    assignment = Assignment(
        teacher_id=teacher.id,
        subject_name="Data Mining",
        subject_code="DMDW1",
        title="Blockchain",
        max_score=100,
        allowed_file_types=["spreadsheet"],
        rubric=[
            {
                "key": "understanding",
                "label": "Understanding",
                "description": "Explain the topic",
                "max_points": 100,
            }
        ],
        is_active=True,
    )
    other_assignment = Assignment(
        teacher_id=other_teacher.id,
        subject_name="Other",
        subject_code="OTH1",
        title="Other assignment",
        max_score=100,
        allowed_file_types=["spreadsheet"],
        rubric=[{"key": "one", "label": "One", "max_points": 100}],
        is_active=True,
    )
    setup.add_all([assignment, other_assignment])
    setup.commit()
    ids = {
        "teacher": teacher.id,
        "other_teacher": other_teacher.id,
        "student": student.id,
        "similar_student": similar_student.id,
        "admin": admin.id,
        "assignment": assignment.id,
        "other_assignment": other_assignment.id,
        "rubric": rubric.id,
    }
    setup.close()

    acting = {"user_id": ids["teacher"]}
    storage = MemoryStorage()
    request_sessions = []
    monkeypatch.setattr(teacher_uploads, "SessionLocal", factory)
    monkeypatch.setattr(teacher_uploads, "get_storage", lambda: storage)
    monkeypatch.setattr(assignments, "get_storage", lambda: storage)
    monkeypatch.setattr(roster_import, "get_storage", lambda: storage)
    monkeypatch.setattr(submissions, "get_storage", lambda: storage)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    app = FastAPI()

    def override_db():
        session = factory()
        request_sessions.append(session)
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = factory()
        try:
            return session.query(User).filter(User.id == acting["user_id"]).one()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.include_router(auth.router)
    app.include_router(teacher_uploads.router)
    app.include_router(assignments.router)
    app.include_router(roster_import.router)
    app.include_router(submissions.router)
    app.include_router(submissions.student_router)
    client = TestClient(app)
    try:
        yield {
            "client": client,
            "app": app,
            "factory": factory,
            "engine": engine,
            "acting": acting,
            "storage": storage,
            "request_sessions": request_sessions,
            "ids": ids,
        }
    finally:
        client.close()
        if engine.dialect.name == "postgresql":
            table_names = ", ".join(
                f'"{table.name}"' for table in Base.metadata.sorted_tables
            )
            with engine.begin() as connection:
                connection.execute(
                    text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
                )
        else:
            Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def sqlite_upload_test_context(monkeypatch, request):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    return request.getfixturevalue("upload_test_context")


def _csv(name: str = "Vexari Quorium") -> bytes:
    return (
        f"Student Name,{name}\n"
        "Topic,Blockchain decentralized ledger\n"
        "Explanation,This spreadsheet describes blocks hashing consensus and a distributed ledger.\n"
    ).encode()


def _roster_xlsx(
    rows: list[tuple[str, str, str]],
    sheet_name="Roster",
    *,
    add_second_sheet: bool = False,
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(["Roll No", "Student Name", "Project TOPICS"])
    worksheet.append(["R-101", "ANON ROSTER ONE", "1.  Sample Topic One"])
    worksheet.append(["R-102", "ANON ROSTER TWO", "Topic Two"])
    worksheet.append(["R-103", "ANON ROSTER THREE", "Topic Three"])
    for row in rows:
        worksheet.append(row)
    if add_second_sheet:
        second = workbook.create_sheet("Second Roster")
        second.append(["Registration No.", "Student Name", "Project"])
        second.append(["Q-201", "ANON SECOND ONE", "Second topic one"])
        second.append(["Q-202", "ANON SECOND TWO", "Second topic two"])
        second.append(["Q-203", "ANON SECOND THREE", "Second topic three"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _seed_batch(context, filename: str, content: bytes, status=UploadBatchFileStatus.UPLOADED):
    db: Session = context["factory"]()
    try:
        batch = UploadBatch(
            teacher_id=context["ids"]["teacher"],
            target_assignment_id=context["ids"]["assignment"],
            file_count=1,
            status=UploadBatchStatus.PENDING,
        )
        db.add(batch)
        db.flush()
        key = f"submissions/{uuid4().hex}.csv"
        context["storage"].files[key] = content
        item = UploadBatchFile(
            batch_id=batch.id,
            storage_key=key,
            original_filename=filename,
            status=status,
        )
        db.add(item)
        db.commit()
        return batch.id, item.id, key
    finally:
        db.close()


def _remove_similar_student(context):
    db: Session = context["factory"]()
    try:
        db.query(User).filter(User.id == context["ids"]["similar_student"]).delete()
        db.commit()
    finally:
        db.close()


def test_teacher_cannot_upload_to_another_teachers_assignment(upload_test_context):
    client = upload_test_context["client"]
    response = client.post(
        "/teacher/uploads",
        data={"assignment_id": upload_test_context["ids"]["other_assignment"]},
        files={"files": ("Vexari.csv", _csv(), "text/csv")},
    )

    assert response.status_code == 404
    assert upload_test_context["storage"].saved_keys == []


def test_upload_batch_name_is_optional_normalized_and_length_limited(
    sqlite_upload_test_context,
    monkeypatch,
):
    context = sqlite_upload_test_context
    monkeypatch.setattr(teacher_uploads, "process_upload_batch", lambda _batch_id: None)
    endpoint = "/teacher/uploads"

    named = context["client"].post(
        endpoint,
        data={"name": "  Agile   Technology - Section A presentations  "},
        files={"files": ("named.csv", _csv(), "text/csv")},
    )
    assert named.status_code == 202, named.text
    assert named.json()["name"] == "Agile Technology - Section A presentations"

    unnamed = context["client"].post(
        endpoint,
        files={"files": ("unnamed.csv", _csv(), "text/csv")},
    )
    assert unnamed.status_code == 202, unnamed.text
    assert unnamed.json()["name"] is None
    unnamed_detail = context["client"].get(
        f"/teacher/uploads/{unnamed.json()['id']}"
    )
    assert unnamed_detail.status_code == 200
    assert unnamed_detail.json()["name"] is None

    whitespace_name = context["client"].post(
        endpoint,
        data={"name": " \t   "},
        files={"files": ("whitespace.csv", _csv(), "text/csv")},
    )
    assert whitespace_name.status_code == 202, whitespace_name.text
    assert whitespace_name.json()["name"] is None

    max_length = context["client"].post(
        endpoint,
        data={"name": "x" * 120},
        files={"files": ("max-length.csv", _csv(), "text/csv")},
    )
    assert max_length.status_code == 202, max_length.text
    assert max_length.json()["name"] == "x" * 120

    too_long = context["client"].post(
        endpoint,
        data={"name": "x" * 121},
        files={"files": ("too-long.csv", _csv(), "text/csv")},
    )
    assert too_long.status_code == 422
    assert too_long.json()["detail"] == "Batch name must be 120 characters or fewer."

    batch_id = named.json()["id"]
    detail = context["client"].get(f"/teacher/uploads/{batch_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == named.json()["name"]
    listed = context["client"].get("/teacher/uploads")
    assert listed.status_code == 200
    named_summary = next(
        item for item in listed.json()["items"] if item["id"] == batch_id
    )
    assert named_summary["name"] == named.json()["name"]
    legacy_summary = next(
        item for item in listed.json()["items"] if item["id"] == unnamed.json()["id"]
    )
    assert legacy_summary["name"] is None


def test_upload_batch_rename_is_owned_and_normalized(sqlite_upload_test_context):
    context = sqlite_upload_test_context
    batch_id, _file_id, _key = _seed_batch(context, "rename.csv", _csv())

    renamed = context["client"].patch(
        f"/teacher/uploads/{batch_id}",
        json={"name": "  Data   Structures\tSection B "},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json() == {
        "id": batch_id,
        "name": "Data StructuresSection B",
    }

    too_long = context["client"].patch(
        f"/teacher/uploads/{batch_id}",
        json={"name": "x" * 121},
    )
    assert too_long.status_code == 422
    assert too_long.json()["detail"] == "Batch name must be 120 characters or fewer."

    context["acting"]["user_id"] = context["ids"]["other_teacher"]
    forbidden_owner = context["client"].patch(
        f"/teacher/uploads/{batch_id}",
        json={"name": "Other teacher batch"},
    )
    assert forbidden_owner.status_code == 404


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "message", "status_code"),
    [
        ("student.xlsm", b"not a spreadsheet", "application/vnd.ms-excel", ".xlsx and .csv", 415),
        ("student.csv", b"\x00\x01\x02", "text/csv", "binary data", 422),
        ("student.xlsx", b"corrupt", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "does not match", 422),
        ("encrypted.xlsx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Encrypted Excel", 415),
        ("student.csv", b"student,topic\n", "application/json", "MIME type", 415),
    ],
)
def test_rejects_invalid_uploads(upload_test_context, filename, content, content_type, message, status_code):
    response = upload_test_context["client"].post(
        "/teacher/uploads",
        files={"files": (filename, content, content_type)},
    )

    assert response.status_code == status_code
    assert message in response.json()["detail"]
    assert upload_test_context["storage"].saved_keys == []


def test_oversized_upload_is_rejected(upload_test_context, monkeypatch):
    monkeypatch.setattr(teacher_uploads, "MAX_UPLOAD_BYTES", 4)

    response = upload_test_context["client"].post(
        "/teacher/uploads",
        files={"files": ("student.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 413
    assert "byte limit" in response.json()["detail"]


def test_zip_bomb_upload_is_rejected_before_workbook_loading(
    upload_test_context, monkeypatch
):
    import io
    import zipfile

    from app.services import excel_parser

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", "A" * 2048)
    monkeypatch.setattr(excel_parser, "EXCEL_MAX_UNCOMPRESSED_BYTES", 128)

    response = upload_test_context["client"].post(
        "/teacher/uploads",
        files={
            "files": (
                "compressed.xlsx",
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 413
    assert "uncompressed-size limit" in response.json()["detail"]


def test_upload_uses_private_uuid_key_and_auto_matches_then_grades(
    upload_test_context, monkeypatch
):
    _remove_similar_student(upload_test_context)
    seen_sessions = []

    async def grade(submission_id, _rubric_id, use_mock, db, **_kwargs):
        seen_sessions.append((db, use_mock))
        submission = db.query(Submission).filter(Submission.id == submission_id).one()
        submission.status = SubmissionStatus.READY
        db.commit()
        return {"submission_id": submission_id, "status": "ready"}

    monkeypatch.setattr(teacher_uploads, "_evaluate_submission", grade)
    response = upload_test_context["client"].post(
        "/teacher/uploads",
        data={"assignment_id": upload_test_context["ids"]["assignment"]},
        files={"files": ("Vexari_Quorium_DMDW1.csv", _csv(), "text/csv")},
    )

    assert response.status_code == 202
    assert response.json()["file_count"] == 1
    assert len(upload_test_context["storage"].saved_keys) == 1
    assert upload_test_context["storage"].saved_keys[0].startswith("submissions/")
    assert "Vexari_Quorium_DMDW1.csv" not in upload_test_context["storage"].saved_keys[0]
    assert seen_sessions and seen_sessions[0][1] is True
    assert seen_sessions[0][0] not in upload_test_context["request_sessions"]

    batch = upload_test_context["client"].get(
        f"/teacher/uploads/{response.json()['id']}"
    ).json()
    assert batch["files"][0]["match_status"] == "auto_matched"
    assert batch["files"][0]["status"] == "graded"
    assert batch["files"][0]["resolved_student_name"] == "Vexari Quorium"

    db: Session = upload_test_context["factory"]()
    try:
        submission = db.query(Submission).one()
        assert submission.source == SubmissionSource.TEACHER_UPLOAD
        assert submission.match_status == StudentMatchStatus.AUTO_MATCHED
        assert submission.uploaded_by_teacher_id == upload_test_context["ids"]["teacher"]
    finally:
        db.close()


def test_class_roster_upload_is_detected_and_not_graded(upload_test_context):
    context = upload_test_context
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["RollNo", "Student Name", "Project TOPICS"])
    worksheet.append(["R-101", "ANON STUDENT ONE", "Topic One"])
    worksheet.append(["R-102", "ANON STUDENT TWO", "Topic Two"])
    worksheet.append(["R-103", "ANON STUDENT THREE", "Topic Three"])
    output = io.BytesIO()
    workbook.save(output)

    response = context["client"].post(
        "/teacher/uploads",
        files={
            "files": (
                "class-list.xlsx",
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 202
    batch = context["client"].get(f"/teacher/uploads/{response.json()['id']}").json()
    file_row = batch["files"][0]
    assert file_row["status"] == "roster_detected"
    assert file_row["roster_detected"] is True
    assert file_row["roster_message"] == (
        "This looks like a class list, not one student's submission. Use Import assignments."
    )
    assert file_row["roster_layout"]["name_column"] == 1
    assert file_row["roster_layout"]["roll_column"] == 0
    assert file_row["roster_layout"]["topic_column"] == 2
    assert file_row["detected_name"] is None
    assert file_row["submission_id"] is None

    db: Session = context["factory"]()
    try:
        assert db.query(Submission).count() == 0
    finally:
        db.close()


def test_truncated_workbook_warning_is_returned_on_file_row(upload_test_context, monkeypatch):
    context = upload_test_context
    monkeypatch.setattr(excel_parser, "EXCEL_MAX_ROWS", 1)
    monkeypatch.setattr(teacher_uploads, "EXCEL_MAX_ROWS", 1)
    content = b"Student Name,Vexari Quorium\nTopic,Blockchain\n"

    response = context["client"].post(
        "/teacher/uploads",
        data={"assignment_id": context["ids"]["assignment"]},
        files={
            "files": (
                "students.csv",
                content,
                "text/csv",
            )
        },
    )

    assert response.status_code == 202
    batch = context["client"].get(f"/teacher/uploads/{response.json()['id']}").json()
    file_row = batch["files"][0]
    assert file_row["status"] == "awaiting_confirmation"
    assert file_row["error"] is None
    assert file_row["warning"] == (
        "Only the first 1 rows per sheet were read; "
        "1 additional non-empty rows were omitted."
    )


def test_ambiguous_match_waits_for_teacher_confirmation(upload_test_context):
    batch_id, file_id, _key = _seed_batch(
        upload_test_context,
        "Vexari_Quorium_DMDW1.csv",
        _csv(),
    )
    teacher_uploads.process_upload_batch(batch_id)

    db: Session = upload_test_context["factory"]()
    try:
        item = db.query(UploadBatchFile).filter(UploadBatchFile.id == file_id).one()
        assert item.status == UploadBatchFileStatus.AWAITING_CONFIRMATION
        assert item.match_status == StudentMatchStatus.NEEDS_CONFIRMATION
        assert item.submission_id is None
    finally:
        db.close()


def test_restricted_assignment_confirmation_rejects_ineligible_student(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        assignment = db.query(Assignment).filter(
            Assignment.id == context["ids"]["assignment"]
        ).one()
        db.add(
            AssignmentAssignee(
                assignment_id=assignment.id,
                student_id=context["ids"]["student"],
            )
        )
        db.commit()
    finally:
        db.close()
    batch_id, file_id, _key = _seed_batch(
        context,
        "unknown_DMDW1.csv",
        _csv("Unregistered Person"),
        UploadBatchFileStatus.AWAITING_CONFIRMATION,
    )
    response = context["client"].post(
        f"/teacher/uploads/{batch_id}/files/{file_id}/confirm",
        json={
            "student_id": context["ids"]["similar_student"],
            "assignment_id": context["ids"]["assignment"],
        },
    )

    assert response.status_code == 422
    assert "not assigned" in response.json()["detail"]


def test_duplicate_file_is_flagged_without_replacing_submission(
    upload_test_context, monkeypatch
):
    context = upload_test_context
    _remove_similar_student(context)

    async def grade(submission_id, _rubric_id, _use_mock, db, **_kwargs):
        submission = db.query(Submission).filter(Submission.id == submission_id).one()
        submission.status = SubmissionStatus.READY
        db.commit()
        return {}

    monkeypatch.setattr(teacher_uploads, "_evaluate_submission", grade)
    first_response = context["client"].post(
        "/teacher/uploads",
        data={"assignment_id": context["ids"]["assignment"]},
        files={"files": ("Vexari_Quorium.csv", _csv(), "text/csv")},
    )
    second_response = context["client"].post(
        "/teacher/uploads",
        data={"assignment_id": context["ids"]["assignment"]},
        files={"files": ("Vexari_Quorium.csv", _csv(), "text/csv")},
    )
    assert first_response.status_code == second_response.status_code == 202
    second_batch = context["client"].get(
        f"/teacher/uploads/{second_response.json()['id']}"
    ).json()
    assert second_batch["files"][0]["status"] == "duplicate"
    assert second_batch["files"][0]["submission_id"] is None

    db: Session = context["factory"]()
    try:
        assert db.query(Submission).count() == 1
        first_batch_id = first_response.json()["id"]
        duplicate_file = (
            db.query(UploadBatchFile)
            .filter(UploadBatchFile.batch_id == second_response.json()["id"])
            .one()
        )
    finally:
        db.close()

    not_confirmed = context["client"].post(
        f"/teacher/uploads/{second_response.json()['id']}/files/{duplicate_file.id}/confirm",
        json={"student_id": context["ids"]["student"]},
    )
    assert not_confirmed.status_code == 409
    confirmed = context["client"].post(
        f"/teacher/uploads/{second_response.json()['id']}/files/{duplicate_file.id}/confirm",
        json={"student_id": context["ids"]["student"], "allow_duplicate": True},
    )
    assert confirmed.status_code == 202
    assert first_batch_id != second_response.json()["id"]


def test_student_visibility_hides_unreviewed_teacher_evaluation_and_file(
    upload_test_context,
):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        submission = Submission(
            student_id=context["ids"]["student"],
            assignment_id=context["ids"]["assignment"],
            file_path="submissions/private.csv",
            original_filename="private.csv",
            file_type="spreadsheet",
            status=SubmissionStatus.READY,
            source=SubmissionSource.TEACHER_UPLOAD,
            extracted_text="secret extracted work",
        )
        db.add(submission)
        db.flush()
        evaluation = Evaluation(
            submission_id=submission.id,
            rubric_id=context["ids"]["rubric"],
            total_score=91,
            scores={"one": 91},
            feedback={"one": "secret feedback"},
            evidence={"one": "secret evidence"},
            issues=[{"description": "secret issue"}],
            is_reviewed=False,
        )
        db.add(evaluation)
        db.commit()
        submission_id = submission.id
    finally:
        db.close()

    context["acting"]["user_id"] = context["ids"]["student"]
    listed = context["client"].get("/submissions/").json()
    detail = context["client"].get(f"/submissions/{submission_id}")
    guessed = context["client"].get(f"/submissions/{submission_id}/file")
    evaluate = context["client"].post(f"/submissions/evaluate/{submission_id}")
    assert len(listed) == 1
    assert listed[0]["status"] == "pending_teacher_review"
    assert listed[0]["evaluation"] is None
    assert listed[0]["extracted_text"] is None
    assert listed[0]["file_path"] is None
    assert listed[0]["original_filename"] is None
    assert "secret" not in str(listed[0]).lower()
    assert detail.status_code == 200
    assert detail.json()["status"] == "pending_teacher_review"
    assert detail.json()["evaluation"] is None
    assert detail.json()["extracted_text"] is None
    assert detail.json()["file_path"] is None
    assert detail.json()["original_filename"] is None
    assert "secret" not in detail.text.lower()
    assert guessed.status_code == 404
    assert evaluate.status_code == 403
    context["acting"]["user_id"] = context["ids"]["similar_student"]
    guessed_by_other_student = context["client"].get(f"/submissions/{submission_id}")
    assert guessed_by_other_student.status_code == 404

    db = context["factory"]()
    try:
        db.query(Evaluation).filter(Evaluation.submission_id == submission_id).one().is_reviewed = True
        db.commit()
    finally:
        db.close()
    context["acting"]["user_id"] = context["ids"]["student"]
    released_list = context["client"].get("/submissions/").json()
    released = context["client"].get(f"/submissions/{submission_id}").json()
    assert released_list[0]["evaluation"]["feedback"]["one"] == "secret feedback"
    assert released_list[0]["extracted_text"] == "secret extracted work"
    assert released["evaluation"]["total_score"] == 91


def test_student_upload_visibility_is_unchanged(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        submission = Submission(
            student_id=context["ids"]["student"],
            assignment_id=context["ids"]["assignment"],
            file_path="submissions/student.csv",
            original_filename="student.csv",
            file_type="spreadsheet",
            status=SubmissionStatus.READY,
            source=SubmissionSource.STUDENT_UPLOAD,
            extracted_text="student text",
        )
        db.add(submission)
        db.flush()
        db.add(
            Evaluation(
                submission_id=submission.id,
                rubric_id=context["ids"]["rubric"],
                total_score=80,
                scores={"one": 80},
                feedback={"one": "visible"},
                evidence={},
                is_reviewed=False,
            )
        )
        db.commit()
    finally:
        db.close()

    context["acting"]["user_id"] = context["ids"]["student"]
    result = context["client"].get("/submissions/").json()[0]
    assert result["status"] == "ready"
    assert result["evaluation"]["feedback"]["one"] == "visible"


def test_student_cannot_approve_evaluation_to_release_results(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        submission = Submission(
            student_id=context["ids"]["student"],
            assignment_id=context["ids"]["assignment"],
            file_path="submissions/private.csv",
            file_type="spreadsheet",
            status=SubmissionStatus.READY,
            source=SubmissionSource.TEACHER_UPLOAD,
        )
        db.add(submission)
        db.flush()
        evaluation = Evaluation(
            submission_id=submission.id,
            rubric_id=context["ids"]["rubric"],
            total_score=70,
            scores={"one": 70},
            feedback={},
            evidence={},
            is_reviewed=False,
        )
        db.add(evaluation)
        db.commit()
        evaluation_id = evaluation.id
    finally:
        db.close()

    context["acting"]["user_id"] = context["ids"]["student"]
    response = context["client"].patch(
        f"/submissions/evaluate/{evaluation_id}/review"
    )
    assert response.status_code == 403


def test_student_is_forbidden_from_new_teacher_endpoints(upload_test_context):
    context = upload_test_context
    batch_id, file_id, _key = _seed_batch(context, "forbidden.csv", _csv())
    context["acting"]["user_id"] = context["ids"]["student"]
    calls = [
        ("GET", "/teacher/students?query=pi", {}),
        ("GET", f"/assignments/{context['ids']['assignment']}/assignees", {}),
        ("PUT", f"/assignments/{context['ids']['assignment']}/assignees", {"json": {"student_ids": []}}),
        (
            "POST",
            f"/assignments/{context['ids']['assignment']}/assignees/import-preview",
            {"files": {"file": ("students.csv", b"student,topic\nVexari Quorium,Blockchain\n", "text/csv")}},
        ),
        (
            "POST",
            f"/assignments/{context['ids']['assignment']}/assignees/import-preview/confirm",
            {"json": {"student_ids": []}},
        ),
        ("GET", f"/teacher/uploads/{batch_id}", {}),
        ("GET", "/teacher/uploads?limit=10&offset=0", {}),
        (
            "POST",
            "/teacher/uploads",
            {"files": {"files": ("student.csv", _csv(), "text/csv")}},
        ),
        (
            "POST",
            f"/teacher/uploads/{batch_id}/files/{file_id}/confirm",
            {"json": {"student_id": context["ids"]["student"]}},
        ),
        (
            "POST",
            f"/teacher/uploads/{batch_id}/files/{file_id}/reject",
            {"json": {"reason": "No match"}},
        ),
        ("POST", f"/teacher/uploads/{batch_id}/files/{file_id}/retry", {}),
    ]
    for method, path, kwargs in calls:
        response = context["client"].request(method, path, **kwargs)
        assert response.status_code == 403, (method, path, response.text)


def test_assignment_assignee_endpoints_list_names_replace_validate_and_hide_nonowned(
    upload_test_context,
):
    context = upload_test_context
    assignment_id = context["ids"]["assignment"]
    response = context["client"].get(f"/assignments/{assignment_id}/assignees")
    assert response.status_code == 200, response.text
    assert response.json() == {"assignment_id": assignment_id, "students": []}

    replaced = context["client"].put(
        f"/assignments/{assignment_id}/assignees",
        json={"student_ids": [context["ids"]["student"], context["ids"]["student"]]},
    )
    assert replaced.status_code == 200
    assert replaced.json()["students"] == [
        {
            "id": context["ids"]["student"],
            "full_name": "Vexari Quorium",
            "topic_text": None,
            "topic_number": None,
            "source": None,
            "roll_no": None,
        }
    ]

    invalid = context["client"].put(
        f"/assignments/{assignment_id}/assignees",
        json={"student_ids": [context["ids"]["other_teacher"]]},
    )
    assert invalid.status_code == 422
    unchanged = context["client"].get(f"/assignments/{assignment_id}/assignees")
    assert unchanged.json() == replaced.json()

    other_assignment_id = context["ids"]["other_assignment"]
    assert context["client"].get(
        f"/assignments/{other_assignment_id}/assignees"
    ).status_code == 404
    assert context["client"].put(
        f"/assignments/{other_assignment_id}/assignees",
        json={"student_ids": []},
    ).status_code == 404


def test_assignment_assignee_import_preview_is_read_only_and_confirm_applies_approved_ids(
    upload_test_context,
):
    context = upload_test_context
    _remove_similar_student(context)
    assignment_id = context["ids"]["assignment"]
    csv = (
        "student,topic\n"
        "Vexari Quorium,Blockchain\n"
        "Unregistered Person,Blockchain\n"
    ).encode()
    preview = context["client"].post(
        f"/assignments/{assignment_id}/assignees/import-preview",
        files={"file": ("assignees.csv", csv, "text/csv")},
    )

    assert preview.status_code == 200
    assert [row["status"] for row in preview.json()["rows"]] == ["matched", "unmatched"]
    assert preview.json()["rows"][0]["topic_check"] == "ok"
    assert context["client"].get(
        f"/assignments/{assignment_id}/assignees"
    ).json()["students"] == []

    confirmed = context["client"].post(
        f"/assignments/{assignment_id}/assignees/import-preview/confirm",
        json={
            "student_ids": [context["ids"]["student"]],
            "rows": [{
                "student_id": context["ids"]["student"],
                "topic_text": "14.  Blockchain Attendance",
                "row_number": 2,
            }],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["students"] == [
        {
            "id": context["ids"]["student"],
            "full_name": "Vexari Quorium",
            "topic_text": "Blockchain Attendance",
            "topic_number": 14,
            "source": "roster_import",
            "roll_no": None,
        }
    ]


def test_assignee_import_preview_marks_ambiguous_student_rows(upload_test_context):
    context = upload_test_context
    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/assignees/import-preview",
        files={
            "file": (
                "assignees.csv",
                b"student,topic\nVexari Quorium,Blockchain\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["rows"][0]["status"] == "ambiguous"
    assert len(response.json()["rows"][0]["candidates"]) == 2


def test_assignee_import_preview_topic_is_optional_and_only_warns(
    upload_test_context,
):
    context = upload_test_context
    no_topic_column = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/assignees/import-preview",
        files={
            "file": (
                "assignees.csv",
                b"student\nVexari Quorium\n",
                "text/csv",
            )
        },
    )
    assert no_topic_column.status_code == 200
    assert no_topic_column.json()["rows"][0]["status"] == "ambiguous"
    assert no_topic_column.json()["rows"][0]["topic_check"] == "missing"
    assert no_topic_column.json()["warning"] is None

    weak_topics = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/assignees/import-preview",
        files={
            "file": (
                "assignees.csv",
                b"student,topic\nVexari Quorium,Ancient pottery\nAnother Student,Ancient pottery\n",
                "text/csv",
            )
        },
    )
    assert weak_topics.status_code == 200
    payload = weak_topics.json()
    assert [row["topic_check"] for row in payload["rows"]] == ["weak", "weak"]
    assert [row["status"] for row in payload["rows"]] == ["ambiguous", "unmatched"]
    assert payload["warning"] == (
        "Most topics in this file do not match this assignment. Check that you selected the right assignment."
    )


def test_assignee_import_preview_requires_student_column(upload_test_context):
    response = upload_test_context["client"].post(
        f"/assignments/{upload_test_context['ids']['assignment']}/assignees/import-preview",
        files={"file": ("assignees.csv", b"first,last\nVexari,Quorium\n", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Spreadsheet must include a student column"


def test_teacher_upload_batch_list_is_scoped_paginated_and_has_file_counts(
    upload_test_context,
):
    context = upload_test_context
    batch_ids = []
    for owner_id, status, file_status in [
        (
            context["ids"]["teacher"],
            UploadBatchStatus.COMPLETED,
            UploadBatchFileStatus.GRADED,
        ),
        (
            context["ids"]["teacher"],
            UploadBatchStatus.FAILED,
            UploadBatchFileStatus.FAILED,
        ),
        (
            context["ids"]["other_teacher"],
            UploadBatchStatus.COMPLETED,
            UploadBatchFileStatus.GRADED,
        ),
    ]:
        db: Session = context["factory"]()
        try:
            batch = UploadBatch(
                teacher_id=owner_id,
                file_count=1,
                status=status,
            )
            db.add(batch)
            db.flush()
            db.add(
                UploadBatchFile(
                    batch_id=batch.id,
                    storage_key=f"submissions/{uuid4().hex}.csv",
                    original_filename="batch.csv",
                    status=file_status,
                )
            )
            db.commit()
            batch_ids.append(batch.id)
        finally:
            db.close()

    page = context["client"].get("/teacher/uploads?limit=1&offset=0")
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["items"][0]["id"] == batch_ids[1]
    assert payload["items"][0]["counts"] == {"failed": 1}

    context["acting"]["user_id"] = context["ids"]["admin"]
    admin_page = context["client"].get("/teacher/uploads?limit=10&offset=0")
    assert admin_page.status_code == 200
    assert admin_page.json()["total"] == 3


def test_admin_can_manage_assignees(upload_test_context):
    context = upload_test_context
    context["acting"]["user_id"] = context["ids"]["admin"]
    response = context["client"].put(
        f"/assignments/{context['ids']['other_assignment']}/assignees",
        json={"student_ids": [context["ids"]["student"]]},
    )

    assert response.status_code == 200
    assert response.json()["students"] == [
        {
            "id": context["ids"]["student"],
            "full_name": "Vexari Quorium",
            "topic_text": None,
            "topic_number": None,
            "source": None,
            "roll_no": None,
        }
    ]


def test_teacher_cannot_read_another_teachers_batch(upload_test_context):
    context = upload_test_context
    batch = UploadBatch(
        teacher_id=context["ids"]["other_teacher"],
        target_assignment_id=context["ids"]["other_assignment"],
        file_count=0,
        status=UploadBatchStatus.PENDING,
    )
    db: Session = context["factory"]()
    try:
        db.add(batch)
        db.commit()
        batch_id = batch.id
    finally:
        db.close()
    response = context["client"].get(f"/teacher/uploads/{batch_id}")
    assert response.status_code == 404


def test_unmatched_upload_waits_for_teacher_confirmation(upload_test_context):
    context = upload_test_context
    batch_id, file_id, _key = _seed_batch(
        context,
        "unknown_DMDW1.csv",
        _csv("Unregistered Person"),
    )
    teacher_uploads.process_upload_batch(batch_id)
    db: Session = context["factory"]()
    try:
        item = db.query(UploadBatchFile).filter(UploadBatchFile.id == file_id).one()
        assert item.status == UploadBatchFileStatus.AWAITING_CONFIRMATION
        assert item.match_status == StudentMatchStatus.UNMATCHED
        assert item.submission_id is None
    finally:
        db.close()


def test_student_search_returns_only_students_and_paginates(upload_test_context):
    context = upload_test_context
    response = context["client"].get("/teacher/students?query=ve&limit=1&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    assert set(payload["items"][0]) == {"id", "full_name", "email", "roll_no"}


def test_roster_preview_matches_roll_numbers_and_falls_back_to_name_without_writes(
    upload_test_context,
):
    context = upload_test_context
    suffix = uuid4().hex[:8]
    db: Session = context["factory"]()
    try:
        roll_match = User(
            email=f"roll-{suffix}@example.test",
            full_name="ANON ROLL MATCH",
            hashed_password="hash",
            role=UserRole.STUDENT,
            roll_no=f"  r-{suffix} 101  ",
        )
        duplicate_one = User(
            email=f"duplicate-one-{suffix}@example.test",
            full_name="ANON DUPLICATE ONE",
            hashed_password="hash",
            role=UserRole.STUDENT,
            roll_no=f"dup-{suffix}",
        )
        duplicate_two = User(
            email=f"duplicate-two-{suffix}@example.test",
            full_name="ANON DUPLICATE TWO",
            hashed_password="hash",
            role=UserRole.STUDENT,
            roll_no=f" DUP-{suffix} ",
        )
        fallback = User(
            email=f"fallback-{suffix}@example.test",
            full_name=f"ANON FALLBACK {suffix}",
            hashed_password="hash",
            role=UserRole.STUDENT,
        )
        db.add_all([roll_match, duplicate_one, duplicate_two, fallback])
        db.commit()
        roll_match_id, duplicate_one_id, duplicate_two_id, fallback_id = (
            roll_match.id,
            duplicate_one.id,
            duplicate_two.id,
            fallback.id,
        )
    finally:
        db.close()
    content = _roster_xlsx(
        [
            (f"R-{suffix}  101", "nexari", "A unique topic"),
            (f"DUP-{suffix}", "ANON DUPLICATE", "Another topic"),
            ("UNKNOWN-ROLL", f"ANON FALLBACK {suffix}", "Fallback topic"),
        ]
    )
    before: Session = context["factory"]()
    try:
        before_assignees = before.query(AssignmentAssignee).count()
        before_users = before.query(User).count()
    finally:
        before.close()

    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/preview",
        files={"file": ("anonymous.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200, response.text
    rows = response.json()["rows"]
    assert rows[-3]["student_status"] == "matched"
    assert rows[-3]["matched_student"]["id"] == roll_match_id
    assert rows[-2]["student_status"] == "ambiguous"
    assert {candidate["id"] for candidate in rows[-2]["candidates"]} == {
        duplicate_one_id,
        duplicate_two_id,
    }
    assert rows[-1]["student_status"] == "matched"
    assert rows[-1]["matched_student"]["id"] == fallback_id
    assert response.json()["summary"]["will_update"] == 0
    after: Session = context["factory"]()
    try:
        assert after.query(AssignmentAssignee).count() == before_assignees
        assert after.query(User).count() == before_users
    finally:
        after.close()


def test_roster_preview_sheet_selection_and_stored_batch_file_reference(upload_test_context):
    context = upload_test_context
    content = _roster_xlsx([], "First Roster", add_second_sheet=True)
    batch_id, file_id, _key = _seed_batch(
        context,
        "roster.xlsx",
        content,
        UploadBatchFileStatus.ROSTER_DETECTED,
    )
    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/preview",
        json={"batch_id": batch_id, "file_id": file_id, "sheet_name": "Second Roster"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["chosen_sheet"] == "Second Roster"
    assert response.json()["sheet_names"] == ["First Roster", "Second Roster"]
    assert response.json()["header_row"] == 1
    assert response.json()["detected_layout"] == "3 students, 3 different topics"
    confirm = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/confirm",
        json={
            "batch_id": batch_id,
            "file_id": file_id,
            "sheet_name": "Second Roster",
            "rows": [{
                "row_number": 2,
                "student_id": context["ids"]["student"],
                "topic_text": "Sample Topic One",
                "topic_number": 1,
            }],
        },
    )
    assert confirm.status_code == 200
    db: Session = context["factory"]()
    try:
        assert db.get(UploadBatchFile, file_id).status == UploadBatchFileStatus.IMPORTED
    finally:
        db.close()


def test_roster_confirm_is_idempotent_updates_topics_and_only_fills_empty_roll_numbers(
    upload_test_context,
):
    context = upload_test_context
    suffix = uuid4().hex[:8]
    db: Session = context["factory"]()
    try:
        existing_student = db.query(User).filter(User.id == context["ids"]["student"]).one()
        existing_student.roll_no = "KEEP-ROLL"
        added_student = User(
            email=f"new-roster-{suffix}@example.test",
            full_name="ANON NEW ROSTER STUDENT",
            hashed_password="hash",
            role=UserRole.STUDENT,
        )
        db.add(added_student)
        db.flush()
        existing_student_id = existing_student.id
        added_student_id = added_student.id
        db.add_all(
            [
                AssignmentAssignee(
                    assignment_id=context["ids"]["assignment"],
                    student_id=existing_student_id,
                    topic_text="Old topic",
                    topic_number=1,
                    source=None,
                ),
                AssignmentAssignee(
                    assignment_id=context["ids"]["assignment"],
                    student_id=context["ids"]["similar_student"],
                    topic_text="Keep this topic",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()
    url = f"/assignments/{context['ids']['assignment']}/roster/confirm"
    body = {
        "rows": [
            {
                "row_number": 2,
                "student_id": existing_student_id,
                "topic_text": "Updated topic",
                "topic_number": 2,
                "roll_no": "SHOULD-NOT-OVERWRITE",
            },
            {
                "row_number": 3,
                "student_id": added_student_id,
                "topic_text": "New topic",
                "topic_number": 3,
                "roll_no": " save \t this ",
            },
        ],
        "save_roll_numbers": True,
        "sheet_name": "Roster",
    }
    first = context["client"].post(url, json=body)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "added": 1,
        "updated": 1,
        "skipped": 0,
        "already_assigned": 0,
        "roll_numbers_saved": 1,
    }
    second = context["client"].post(url, json=body)
    assert second.status_code == 200, second.text
    assert second.json()["added"] == 0
    assert second.json()["updated"] == 0
    assert second.json()["already_assigned"] == 2
    assert second.json()["roll_numbers_saved"] == 0
    body["rows"][0]["topic_text"] = "Changed once more"
    updated = context["client"].post(url, json=body)
    assert updated.json()["updated"] == 1

    db = context["factory"]()
    try:
        assignees = {
            row.student_id: row
            for row in db.query(AssignmentAssignee).filter(
                AssignmentAssignee.assignment_id == context["ids"]["assignment"]
            )
        }
        assert assignees[existing_student_id].topic_text == "Changed once more"
        assert assignees[context["ids"]["similar_student"]].topic_text == "Keep this topic"
        assert db.get(User, existing_student_id).roll_no == "KEEP-ROLL"
        assert db.get(User, added_student_id).roll_no == "SAVE THIS"
        assert assignees[added_student_id].source == "roster_import"
        assert assignees[added_student_id].roster_row_ref == "Roster#3"
    finally:
        db.close()


def test_roster_endpoints_enforce_assignment_ownership_and_student_role(upload_test_context):
    context = upload_test_context
    roster = _roster_xlsx([])
    path = f"/assignments/{context['ids']['assignment']}/roster/preview"
    assert context["client"].post(
        f"/assignments/{context['ids']['other_assignment']}/roster/preview",
        files={"file": ("roster.xlsx", roster, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).status_code == 404
    assert context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/confirm",
        json={
            "rows": [{
                "row_number": 2,
                "student_id": context["ids"]["teacher"],
                "topic_text": "Topic",
            }]
        },
    ).status_code == 422

    context["acting"]["user_id"] = context["ids"]["student"]
    assert context["client"].post(
        path,
        files={"file": ("roster.xlsx", roster, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).status_code == 403
    assert context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/confirm",
        json={"rows": []},
    ).status_code == 403


def test_roster_preview_rejects_another_teachers_stored_batch(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        batch = UploadBatch(
            teacher_id=context["ids"]["other_teacher"],
            target_assignment_id=context["ids"]["other_assignment"],
            file_count=1,
            status=UploadBatchStatus.COMPLETED,
        )
        db.add(batch)
        db.flush()
        key = f"submissions/{uuid4().hex}.xlsx"
        context["storage"].files[key] = _roster_xlsx([])
        batch_file = UploadBatchFile(
            batch_id=batch.id,
            storage_key=key,
            original_filename="roster.xlsx",
            status=UploadBatchFileStatus.ROSTER_DETECTED,
        )
        db.add(batch_file)
        db.commit()
        batch_id, file_id = batch.id, batch_file.id
    finally:
        db.close()

    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/preview",
        json={"batch_id": batch_id, "file_id": file_id},
    )
    assert response.status_code == 404


def test_existing_assignee_import_accepts_roll_headers_and_persists_clean_topic(
    upload_test_context,
):
    context = upload_test_context
    suffix = uuid4().hex[:8]
    db: Session = context["factory"]()
    try:
        student = User(
            email=f"single-roll-{suffix}@example.test",
            full_name="nexari",
            hashed_password="hash",
            role=UserRole.STUDENT,
            roll_no=f"  s-{suffix} ",
        )
        db.add(student)
        db.commit()
        student_id = student.id
        roll_no = student.roll_no
    finally:
        db.close()
    preview = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/assignees/import-preview",
        files={
            "file": (
                "assignees.csv",
                f"rOlL nO,Student Name,Project TOPICS\n{roll_no},nexari,5)  Topic With Number\n".encode(),
                "text/csv",
            )
        },
    )

    assert preview.status_code == 200, preview.text
    row = preview.json()["rows"][0]
    assert row["status"] == "matched"
    assert row["student_name"] == "nexari"
    assert row["topic"] == "Topic With Number"
    assert row["topic_number"] == 5
    confirmed = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/assignees/import-preview/confirm",
        json={
            "student_ids": [student_id],
            "rows": [{
                "student_id": student_id,
                "topic_text": row["topic"],
                "topic_number": row["topic_number"],
                "row_number": row["row_number"],
            }],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["students"][0]["topic_text"] == "Topic With Number"


def test_teacher_student_search_includes_roll_no_but_students_cannot_search_roster(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        student = db.get(User, context["ids"]["student"])
        student.roll_no = "ROLL-SEARCH-77"
        db.commit()
    finally:
        db.close()
    found = context["client"].get("/teacher/students?query=roll-search-77")
    assert found.status_code == 200
    assert found.json()["items"][0]["roll_no"] == "ROLL-SEARCH-77"
    context["acting"]["user_id"] = context["ids"]["student"]
    denied = context["client"].get("/teacher/students?query=roll-search-77")
    assert denied.status_code == 403


def test_registration_accepts_and_normalizes_optional_roll_number(upload_test_context):
    context = upload_test_context
    response = context["client"].post(
        "/auth/register",
        json={
            "email": f"register-{uuid4().hex}@example.com",
            "full_name": "ANON REGISTRATION STUDENT",
            "password": "valid-test-password",
            "roll_no": "  ab\t  123  ",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["roll_no"] == "AB 123"


def test_roster_preview_reports_missing_and_duplicate_row_data(upload_test_context):
    context = upload_test_context
    content = _roster_xlsx(
        [
            ("", "ANON ROSTER ONE", "A different topic"),
            ("R-404", "", "Topic without a name"),
            ("R-405", "ANON NO TOPIC", ""),
        ]
    )
    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/preview",
        files={"file": ("warnings.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200, response.text
    warnings = response.json()["warnings"]
    assert any("no student name" in warning for warning in warnings)
    assert any("do not have a topic" in warning for warning in warnings)
    assert any(
        "Duplicate student names" in warning
        for warning in warnings
    )


def test_student_submission_response_contains_only_their_own_topic_and_no_roll_numbers(
    upload_test_context,
):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        first = db.get(User, context["ids"]["student"])
        second = db.get(User, context["ids"]["similar_student"])
        first.roll_no = "PRIVATE-OWN-ROLL"
        second.roll_no = "PRIVATE-OTHER-ROLL"
        db.add_all(
            [
                AssignmentAssignee(
                    assignment_id=context["ids"]["assignment"],
                    student_id=first.id,
                    topic_text="Own private topic",
                ),
                AssignmentAssignee(
                    assignment_id=context["ids"]["assignment"],
                    student_id=second.id,
                    topic_text="Other private topic",
                ),
            ]
        )
        submission = Submission(
            student_id=first.id,
            assignment_id=context["ids"]["assignment"],
            file_path="private",
            original_filename="private.xlsx",
            file_type="spreadsheet",
            status=SubmissionStatus.UPLOADED,
            source=SubmissionSource.TEACHER_UPLOAD,
        )
        db.add(submission)
        db.commit()
        submission_id = submission.id
        other_submission = Submission(
            student_id=second.id,
            assignment_id=context["ids"]["assignment"],
            file_path="private-other",
            original_filename="private-other.xlsx",
            file_type="spreadsheet",
            status=SubmissionStatus.UPLOADED,
            source=SubmissionSource.TEACHER_UPLOAD,
        )
        db.add(other_submission)
        db.commit()
        other_submission_id = other_submission.id
    finally:
        db.close()

    context["acting"]["user_id"] = context["ids"]["student"]
    response = context["client"].get(f"/submissions/{submission_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["student_topic"] == "Own private topic"
    assert "roll_no" not in payload
    assert "PRIVATE-OTHER-ROLL" not in str(payload)
    assert "Other private topic" not in str(payload)
    assert context["client"].get(
        f"/submissions/{other_submission_id}"
    ).status_code == 404


def test_student_assignment_list_includes_only_own_topic(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        db.add_all(
            [
                AssignmentAssignee(
                    assignment_id=context["ids"]["assignment"],
                    student_id=context["ids"]["student"],
                    topic_text="Own assignment topic",
                ),
                AssignmentAssignee(
                    assignment_id=context["ids"]["assignment"],
                    student_id=context["ids"]["similar_student"],
                    topic_text="Other assignment topic",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()
    context["acting"]["user_id"] = context["ids"]["student"]
    response = context["client"].get("/assignments")
    assert response.status_code == 200
    assignment = next(
        row for row in response.json()
        if row["id"] == context["ids"]["assignment"]
    )
    assert assignment["student_topic"] == "Own assignment topic"
    assert "Other assignment topic" not in str(response.json())
    assert all("roll_no" not in row for row in response.json())
    detail = context["client"].get(
        f"/assignments/{context['ids']['assignment']}"
    )
    assert detail.json()["student_topic"] == "Own assignment topic"


def test_stale_processing_upload_is_marked_failed(upload_test_context):
    context = upload_test_context
    batch_id, file_id, _key = _seed_batch(
        context,
        "processing.csv",
        _csv(),
        UploadBatchFileStatus.PROCESSING,
    )
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    db: Session = context["factory"]()
    try:
        item = db.query(UploadBatchFile).filter(UploadBatchFile.id == file_id).one()
        item.updated_at = old
        db.commit()
        recovered = teacher_uploads.sweep_stale_upload_files(
            db,
            now=datetime.now(timezone.utc),
            timeout_minutes=30,
        )
        assert recovered == 1
        assert item.status == UploadBatchFileStatus.FAILED
        assert item.failed_step == "recovery"
        assert "interrupted" in item.error
    finally:
        db.close()


def test_startup_sweep_recovers_stale_processing_uploads(
    upload_test_context, monkeypatch
):
    context = upload_test_context
    _batch_id, file_id, _key = _seed_batch(
        context,
        "interrupted.csv",
        _csv(),
        UploadBatchFileStatus.PROCESSING,
    )
    db: Session = context["factory"]()
    try:
        db.query(UploadBatchFile).filter(UploadBatchFile.id == file_id).one().updated_at = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(teacher_uploads, "SessionLocal", context["factory"])

    recovered = teacher_uploads.schedule_stale_upload_sweep()

    assert recovered == 1
    db = context["factory"]()
    try:
        item = db.query(UploadBatchFile).filter(UploadBatchFile.id == file_id).one()
        assert item.status == UploadBatchFileStatus.FAILED
        assert item.failed_step == "recovery"
    finally:
        db.close()


def test_batch_continues_after_one_file_exception_and_retry_reprocesses(
    upload_test_context, monkeypatch
):
    context = upload_test_context
    _remove_similar_student(context)
    batch_id, failed_id, failed_key = _seed_batch(
        context, "broken_DMDW1.csv", _csv()
    )
    db: Session = context["factory"]()
    try:
        good_key = f"submissions/{uuid4().hex}.csv"
        context["storage"].files[good_key] = _csv()
        good = UploadBatchFile(
            batch_id=batch_id,
            storage_key=good_key,
            original_filename="Vexari_Quorium_DMDW1.csv",
            status=UploadBatchFileStatus.UPLOADED,
        )
        db.add(good)
        db.commit()
        good_id = good.id
    finally:
        db.close()
    context["storage"].fail_read.add(failed_key)
    graded_session_ids = []

    async def grade(submission_id, _rubric_id, _mock, db, **_kwargs):
        graded_session_ids.append(id(db))
        submission = db.query(Submission).filter(Submission.id == submission_id).one()
        submission.status = SubmissionStatus.READY
        db.commit()
        return {}

    monkeypatch.setattr(teacher_uploads, "_evaluate_submission", grade)
    teacher_uploads.process_upload_batch(batch_id)

    db = context["factory"]()
    try:
        failed = db.query(UploadBatchFile).filter(UploadBatchFile.id == failed_id).one()
        succeeded = db.query(UploadBatchFile).filter(UploadBatchFile.id == good_id).one()
        assert failed.status == UploadBatchFileStatus.FAILED
        assert succeeded.status == UploadBatchFileStatus.GRADED
        assert graded_session_ids
    finally:
        db.close()

    context["storage"].fail_read.clear()
    retry = context["client"].post(
        f"/teacher/uploads/{batch_id}/files/{failed_id}/retry"
    )
    assert retry.status_code == 202
    db = context["factory"]()
    try:
        assert (
            db.query(UploadBatchFile)
            .filter(UploadBatchFile.id == failed_id)
            .one()
            .status
            == UploadBatchFileStatus.AWAITING_CONFIRMATION
        )
    finally:
        db.close()


def test_rejected_file_is_not_processed(upload_test_context):
    context = upload_test_context
    batch_id, file_id, _key = _seed_batch(
        context,
        "unknown.csv",
        _csv("Unregistered Person"),
        UploadBatchFileStatus.AWAITING_CONFIRMATION,
    )
    response = context["client"].post(
        f"/teacher/uploads/{batch_id}/files/{file_id}/reject",
        json={"reason": "Wrong student"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (900000001, "900000001"),
        (900000001.0, "900000001"),
        ("900000001.0", "900000001"),
        (" 900000001 ", "900000001"),
        (" ab  12 ", "AB 12"),
    ],
)
def test_roll_number_normalization_handles_numeric_cells(value, expected):
    assert normalize_roll_no(value) == expected


def test_roster_confirm_rejects_duplicate_students_empty_topics_and_limits(upload_test_context):
    context = upload_test_context
    url = f"/assignments/{context['ids']['assignment']}/roster/confirm"
    row = {
        "row_number": 2,
        "student_id": context["ids"]["student"],
        "topic_text": "Topic",
    }
    duplicate = context["client"].post(url, json={"rows": [row, {**row, "row_number": 3}]})
    assert duplicate.status_code == 422
    assert "only once" in duplicate.json()["detail"]
    empty_topic = context["client"].post(url, json={"rows": [{**row, "topic_text": "  "}]})
    assert empty_topic.status_code == 422
    too_long = context["client"].post(url, json={"rows": [{**row, "topic_text": "T" * 501}]})
    assert too_long.status_code == 422
    too_many = context["client"].post(url, json={"rows": [row] * 501})
    assert too_many.status_code == 422


def test_roster_preview_reports_changed_existing_topic(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        db.get(User, context["ids"]["student"]).roll_no = "TOPIC-ROLL"
        db.add(
            AssignmentAssignee(
                assignment_id=context["ids"]["assignment"],
                student_id=context["ids"]["student"],
                topic_text="Old Topic",
            )
        )
        db.commit()
    finally:
        db.close()
    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/preview",
        files={
            "file": (
                "anonymous.xlsx",
                _roster_xlsx([("TOPIC-ROLL", "Vexari Quorium", "New Topic")]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()["rows"][-1]
    assert row["existing_topic"] == "Old Topic"
    assert row["will_change"] is True
    assert response.json()["summary"]["will_update"] == 1


def test_assignee_topic_patch_is_owned_and_validated(upload_test_context):
    context = upload_test_context
    student_id = context["ids"]["student"]
    db: Session = context["factory"]()
    try:
        db.add(
            AssignmentAssignee(
                assignment_id=context["ids"]["assignment"],
                student_id=student_id,
                topic_text="Old",
            )
        )
        db.commit()
    finally:
        db.close()
    url = f"/assignments/{context['ids']['assignment']}/assignees/{student_id}"
    response = context["client"].patch(url, json={"topic_text": "Updated"})
    assert response.status_code == 200, response.text
    assert response.json()["topic_text"] == "Updated"
    assert context["client"].patch(url, json={"topic_text": " "}).status_code == 422
    assert context["client"].patch(
        f"/assignments/{context['ids']['other_assignment']}/assignees/{student_id}",
        json={"topic_text": "Not allowed"},
    ).status_code == 404
    context["acting"]["user_id"] = context["ids"]["student"]
    assert context["client"].patch(
        url,
        json={"topic_text": "Student cannot edit"},
    ).status_code == 403


def test_numeric_excel_roll_numbers_match_and_save_without_decimal_suffix(upload_test_context):
    context = upload_test_context
    suffix = uuid4().hex[:8]
    db: Session = context["factory"]()
    try:
        matched = User(
            email=f"numeric-match-{suffix}@example.test",
            full_name="ANON NUMERIC MATCH",
            hashed_password="hash",
            role=UserRole.STUDENT,
            roll_no="900000001",
        )
        save_target = User(
            email=f"numeric-save-{suffix}@example.test",
            full_name="ANON NUMERIC SAVED",
            hashed_password="hash",
            role=UserRole.STUDENT,
        )
        db.add_all([matched, save_target])
        db.commit()
        matched_id, save_id = matched.id, save_target.id
    finally:
        db.close()
    content = _roster_xlsx(
        [
            (900000001.0, "ANON NUMERIC MATCH", "Numeric exact match"),
            (900000002.0, "ANON NUMERIC SAVED", "Numeric saved roll"),
        ]
    )
    preview = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/preview",
        files={"file": ("numeric.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    exact_row, save_row = preview.json()["rows"][-2:]
    assert exact_row["roll_no"] == "900000001"
    assert exact_row["matched_student"]["id"] == matched_id
    assert save_row["roll_no"] == "900000002"
    assert save_row["matched_student"]["id"] == save_id
    saved = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/confirm",
        json={
            "rows": [{
                "row_number": save_row["row_number"],
                "student_id": save_id,
                "topic_text": save_row["cleaned_topic"],
                "roll_no": save_row["roll_no"],
            }],
            "save_roll_numbers": True,
        },
    )
    assert saved.status_code == 200, saved.text
    db = context["factory"]()
    try:
        assert db.get(User, save_id).roll_no == "900000002"
    finally:
        db.close()


def test_roster_file_is_not_marked_imported_when_confirmed_without_changes(upload_test_context):
    context = upload_test_context
    db: Session = context["factory"]()
    try:
        db.add(
            AssignmentAssignee(
                assignment_id=context["ids"]["assignment"],
                student_id=context["ids"]["student"],
                topic_text="Existing topic",
            )
        )
        db.commit()
    finally:
        db.close()
    batch_id, file_id, _key = _seed_batch(
        context,
        "unchanged-roster.xlsx",
        _roster_xlsx([]),
        UploadBatchFileStatus.ROSTER_DETECTED,
    )
    response = context["client"].post(
        f"/assignments/{context['ids']['assignment']}/roster/confirm",
        json={
            "batch_id": batch_id,
            "file_id": file_id,
            "rows": [{
                "row_number": 2,
                "student_id": context["ids"]["student"],
                "topic_text": "Existing topic",
            }],
        },
    )
    assert response.status_code == 200, response.text
    db = context["factory"]()
    try:
        assert db.get(UploadBatchFile, file_id).status == UploadBatchFileStatus.ROSTER_DETECTED
    finally:
        db.close()


def test_assignment_delete_impact_cascade_and_repeat_delete(upload_test_context):
    context = upload_test_context
    ids = context["ids"]
    storage = context["storage"]
    db: Session = context["factory"]()
    try:
        assignment = db.get(Assignment, ids["assignment"])
        assignment.due_date = datetime.now(timezone.utc) + timedelta(days=2)
        assignees = [
            AssignmentAssignee(
                assignment_id=assignment.id,
                student_id=student_id,
                topic_text=f"Imported topic {index}",
                source="roster",
            )
            for index, student_id in enumerate(
                [ids["student"], ids["similar_student"]]
            )
        ]
        db.add_all(assignees)
        submissions_to_delete = [
            Submission(
                student_id=student_id,
                assignment_id=assignment.id,
                file_path=f"submissions/assignment-{index}.pdf",
                status=SubmissionStatus.READY,
            )
            for index, student_id in enumerate(
                [ids["student"], ids["similar_student"]]
            )
        ]
        db.add_all(submissions_to_delete)
        db.flush()
        evaluation = Evaluation(
            submission_id=submissions_to_delete[0].id,
            total_score=88,
            scores={"one": 88},
            feedback={"one": "Good work"},
            evidence={"one": "Evidence"},
        )
        db.add(evaluation)
        db.flush()
        db.add(
            Feedback(
                evaluation_id=evaluation.id,
                criterion_id="one",
                score=88,
                feedback_text="Good work",
            )
        )
        db.add(
            VerificationAttempt(
                submission_id=submissions_to_delete[0].id,
                student_id=ids["student"],
                assignment_id=assignment.id,
            )
        )
        batch = UploadBatch(
            teacher_id=ids["teacher"],
            target_assignment_id=assignment.id,
            file_count=2,
            status=UploadBatchStatus.COMPLETED,
        )
        db.add(batch)
        db.flush()
        linked_key = submissions_to_delete[0].file_path
        storage.files[linked_key] = b"assignment file"
        retained_key = "submissions/retained-roster.xlsx"
        storage.files[retained_key] = b"retained roster"
        db.add_all(
            [
                UploadBatchFile(
                    batch_id=batch.id,
                    storage_key=linked_key,
                    original_filename="submission.pdf",
                    status=UploadBatchFileStatus.GRADED,
                    submission_id=submissions_to_delete[0].id,
                    resolved_assignment_id=assignment.id,
                ),
                UploadBatchFile(
                    batch_id=batch.id,
                    storage_key=retained_key,
                    original_filename="roster.xlsx",
                    status=UploadBatchFileStatus.IMPORTED,
                    resolved_assignment_id=assignment.id,
                ),
            ]
        )
        unrelated_submission = Submission(
            student_id=ids["similar_student"],
            assignment_id=ids["other_assignment"],
            status=SubmissionStatus.UPLOADED,
        )
        db.add(unrelated_submission)
        db.commit()
        assignment_id = assignment.id
        batch_id = batch.id
        submission_ids = [item.id for item in submissions_to_delete]
        unrelated_submission_id = unrelated_submission.id
        unrelated_assignment_id = ids["other_assignment"]
        user_count = db.query(User.id).count()
    finally:
        db.close()

    impact = context["client"].get(f"/assignments/{assignment_id}/delete-impact")
    assert impact.status_code == 200
    assert impact.json() == {
        "students_assigned": 2,
        "submissions": 2,
        "graded_submissions": 1,
    }

    deleted = context["client"].delete(f"/assignments/{assignment_id}")
    assert deleted.status_code == 204
    repeated = context["client"].delete(f"/assignments/{assignment_id}")
    assert repeated.status_code == 404

    db = context["factory"]()
    try:
        assert db.get(Assignment, assignment_id) is None
        assert db.get(Assignment, unrelated_assignment_id) is not None
        assert db.get(Submission, unrelated_submission_id) is not None
        assert db.query(User.id).count() == user_count
        assert db.query(AssignmentAssignee).filter(
            AssignmentAssignee.assignment_id == assignment_id
        ).count() == 0
        assert db.query(Submission).filter(
            Submission.id.in_(submission_ids)
        ).count() == 0
        assert db.query(Evaluation).filter(
            Evaluation.submission_id.in_(submission_ids)
        ).count() == 0
        assert db.query(Feedback).filter(Feedback.evaluation_id == evaluation.id).count() == 0
        assert db.query(VerificationAttempt).filter(
            VerificationAttempt.submission_id.in_(submission_ids)
        ).count() == 0
        batch = db.get(UploadBatch, batch_id)
        assert batch.target_assignment_id is None
        assert batch.file_count == 1
        retained_file = db.query(UploadBatchFile).filter(
            UploadBatchFile.batch_id == batch_id
        ).one()
        assert retained_file.resolved_assignment_id is None
        assert retained_file.status == UploadBatchFileStatus.IMPORTED
    finally:
        db.close()
    assert linked_key not in storage.files
    assert retained_key in storage.files


def test_teacher_assignment_deletion_ownership_and_student_forbidden(upload_test_context):
    context = upload_test_context
    assignment_id = context["ids"]["assignment"]
    context["acting"]["user_id"] = context["ids"]["other_teacher"]
    assert context["client"].delete(f"/assignments/{assignment_id}").status_code == 404
    assert context["client"].get(
        f"/assignments/{assignment_id}/delete-impact"
    ).status_code == 404

    context["acting"]["user_id"] = context["ids"]["student"]
    assert context["client"].delete(f"/assignments/{assignment_id}").status_code == 403
    assert context["client"].delete("/assignments/999999").status_code == 403


def test_upload_batch_delete_preserves_assignment_topics_and_grades(upload_test_context):
    context = upload_test_context
    ids = context["ids"]
    db: Session = context["factory"]()
    try:
        assignment = db.get(Assignment, ids["assignment"])
        assignee = AssignmentAssignee(
            assignment_id=assignment.id,
            student_id=ids["student"],
            topic_text="Imported topic remains",
            source="roster",
        )
        batch = UploadBatch(
            teacher_id=ids["teacher"],
            target_assignment_id=assignment.id,
            file_count=1,
            status=UploadBatchStatus.COMPLETED,
        )
        db.add_all([assignee, batch])
        db.flush()
        key = "submissions/batch-content.xlsx"
        context["storage"].files[key] = b"batch content"
        submission = Submission(
            student_id=ids["student"],
            assignment_id=assignment.id,
            file_path=key,
            upload_batch_id=batch.id,
            status=SubmissionStatus.READY,
        )
        db.add(submission)
        db.flush()
        evaluation = Evaluation(
            submission_id=submission.id,
            total_score=90,
            scores={"one": 90},
            feedback={"one": "Good work"},
        )
        db.add(evaluation)
        db.add(
            UploadBatchFile(
                batch_id=batch.id,
                storage_key=key,
                original_filename="submission.xlsx",
                status=UploadBatchFileStatus.GRADED,
                submission_id=submission.id,
                resolved_assignment_id=assignment.id,
            )
        )
        db.commit()
        batch_id = batch.id
        submission_id = submission.id
        assignment_id = assignment.id
    finally:
        db.close()

    response = context["client"].delete(f"/teacher/upload-batches/{batch_id}")
    assert response.status_code == 204
    assert context["client"].delete(
        f"/teacher/upload-batches/{batch_id}"
    ).status_code == 404

    db = context["factory"]()
    try:
        assert db.get(Assignment, assignment_id) is not None
        assert db.query(AssignmentAssignee).filter(
            AssignmentAssignee.assignment_id == assignment_id,
            AssignmentAssignee.student_id == ids["student"],
        ).one().topic_text == "Imported topic remains"
        submission = db.get(Submission, submission_id)
        assert submission is not None
        assert submission.upload_batch_id is None
        assert submission.file_path is None
        assert db.query(Evaluation).filter(
            Evaluation.submission_id == submission_id
        ).one().total_score == 90
        assert db.get(UploadBatch, batch_id) is None
        assert db.query(UploadBatchFile).filter(
            UploadBatchFile.batch_id == batch_id
        ).count() == 0
    finally:
        db.close()
    assert key not in context["storage"].files


def test_upload_batch_delete_ownership_processing_and_single_file_delete(upload_test_context):
    context = upload_test_context
    ids = context["ids"]
    db: Session = context["factory"]()
    try:
        owned = UploadBatch(
            teacher_id=ids["teacher"],
            file_count=1,
            status=UploadBatchStatus.COMPLETED,
        )
        other = UploadBatch(
            teacher_id=ids["other_teacher"],
            file_count=0,
            status=UploadBatchStatus.COMPLETED,
        )
        processing = UploadBatch(
            teacher_id=ids["teacher"],
            file_count=1,
            status=UploadBatchStatus.PROCESSING,
        )
        db.add_all([owned, other, processing])
        db.flush()
        stored_key = "submissions/delete-one.csv"
        context["storage"].files[stored_key] = b"single file"
        file_row = UploadBatchFile(
            batch_id=owned.id,
            storage_key=stored_key,
            original_filename="failed.csv",
            status=UploadBatchFileStatus.FAILED,
        )
        processing_file = UploadBatchFile(
            batch_id=processing.id,
            storage_key="submissions/processing.csv",
            original_filename="processing.csv",
            status=UploadBatchFileStatus.UPLOADED,
        )
        db.add_all([file_row, processing_file])
        db.commit()
        owned_id, other_id, processing_id, file_id = (
            owned.id,
            other.id,
            processing.id,
            file_row.id,
        )
    finally:
        db.close()

    context["acting"]["user_id"] = ids["other_teacher"]
    assert context["client"].delete(
        f"/teacher/upload-batches/{owned_id}"
    ).status_code == 404
    context["acting"]["user_id"] = ids["student"]
    assert context["client"].delete(
        f"/teacher/upload-batches/{owned_id}"
    ).status_code == 403
    context["acting"]["user_id"] = ids["teacher"]
    assert context["client"].delete(
        f"/teacher/upload-batches/{processing_id}"
    ).status_code == 409

    deleted_file = context["client"].delete(
        f"/teacher/upload-batches/{owned_id}/files/{file_id}"
    )
    assert deleted_file.status_code == 204
    assert stored_key not in context["storage"].files
    db = context["factory"]()
    try:
        assert db.get(UploadBatch, owned_id).file_count == 0
        assert db.get(UploadBatch, other_id) is not None
        assert db.query(UploadBatchFile).filter(
            UploadBatchFile.id == file_id
        ).first() is None
    finally:
        db.close()


def test_student_submission_delete_ownership_grade_lock_and_topic(upload_test_context):
    context = upload_test_context
    ids = context["ids"]
    db: Session = context["factory"]()
    try:
        assignment = db.get(Assignment, ids["assignment"])
        assignment.due_date = datetime.now(timezone.utc) + timedelta(days=1)
        locked_assignment = Assignment(
            teacher_id=ids["teacher"],
            subject_name="Locked subject",
            subject_code="LOCK1",
            title="Locked assignment",
            max_score=100,
            allowed_file_types=["pdf"],
            rubric=[{"key": "one", "label": "One", "max_points": 100}],
            due_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(locked_assignment)
        db.flush()
        db.add(
            AssignmentAssignee(
                assignment_id=assignment.id,
                student_id=ids["student"],
                topic_text="The student's imported topic",
            )
        )
        ungraded = Submission(
            student_id=ids["student"],
            assignment_id=assignment.id,
            file_path="submissions/ungraded.pdf",
            status=SubmissionStatus.READY,
        )
        graded = Submission(
            student_id=ids["student"],
            assignment_id=assignment.id,
            file_path="submissions/graded.pdf",
            status=SubmissionStatus.READY,
        )
        locked = Submission(
            student_id=ids["student"],
            assignment_id=locked_assignment.id,
            file_path="submissions/locked.pdf",
            status=SubmissionStatus.READY,
        )
        other_student = Submission(
            student_id=ids["similar_student"],
            assignment_id=assignment.id,
            file_path="submissions/other-student.pdf",
            status=SubmissionStatus.READY,
        )
        db.add_all([ungraded, graded, locked, other_student])
        db.flush()
        ungraded_evaluation = Evaluation(
            submission_id=ungraded.id,
            total_score=None,
            scores={},
            feedback={},
        )
        graded_evaluation = Evaluation(
            submission_id=graded.id,
            total_score=80,
            scores={"one": 80},
            feedback={"one": "Graded"},
        )
        db.add_all([ungraded_evaluation, graded_evaluation])
        db.flush()
        db.add(
            Feedback(
                evaluation_id=ungraded_evaluation.id,
                criterion_id="one",
                feedback_text="Pending result",
            )
        )
        for key in (
            ungraded.file_path,
            graded.file_path,
            locked.file_path,
            other_student.file_path,
        ):
            context["storage"].files[key] = b"student file"
        db.commit()
        ungraded_id, graded_id, locked_id, other_id = (
            ungraded.id,
            graded.id,
            locked.id,
            other_student.id,
        )
        ungraded_key = ungraded.file_path
        locked_key = locked.file_path
    finally:
        db.close()

    context["acting"]["user_id"] = ids["student"]
    own_response = context["client"].delete(
        f"/student/submissions/{ungraded_id}"
    )
    assert own_response.status_code == 204
    assert context["client"].delete(
        f"/student/submissions/{ungraded_id}"
    ).status_code == 404
    assert context["client"].delete(
        f"/student/submissions/{other_id}"
    ).status_code == 404
    assert context["client"].delete(
        f"/student/submissions/{graded_id}"
    ).status_code == 409
    assert context["client"].delete(
        f"/student/submissions/{locked_id}"
    ).status_code == 409

    db = context["factory"]()
    try:
        assert db.get(Submission, ungraded_id) is None
        assert db.query(AssignmentAssignee).filter(
            AssignmentAssignee.assignment_id == ids["assignment"],
            AssignmentAssignee.student_id == ids["student"],
        ).one().topic_text == "The student's imported topic"
        assert db.query(Evaluation).filter(
            Evaluation.submission_id == ungraded_id
        ).count() == 0
        assert db.query(Feedback).filter(
            Feedback.evaluation_id == ungraded_evaluation.id
        ).count() == 0
        assert db.get(Submission, graded_id) is not None
        assert db.get(Submission, locked_id) is not None
    finally:
        db.close()
    assert ungraded_key not in context["storage"].files
    assert locked_key in context["storage"].files


def test_assignment_deactivate_reactivate_preserves_existing_data(
    sqlite_upload_test_context,
):
    context = sqlite_upload_test_context
    ids = context["ids"]
    db: Session = context["factory"]()
    try:
        assignee = AssignmentAssignee(
            assignment_id=ids["assignment"],
            student_id=ids["student"],
            topic_text="Imported topic",
            topic_number=1,
            source="roster",
        )
        submission = Submission(
            student_id=ids["student"],
            assignment_id=ids["assignment"],
            file_path="submissions/existing.txt",
            original_filename="existing.txt",
            file_type="txt",
            status=SubmissionStatus.READY,
            source=SubmissionSource.STUDENT_UPLOAD,
        )
        db.add_all([assignee, submission])
        db.flush()
        evaluation = Evaluation(
            submission_id=submission.id,
            rubric_id=ids["rubric"],
            total_score=80,
            scores={"one": 80},
            feedback={"one": "Existing feedback"},
            evidence={},
            is_reviewed=True,
        )
        db.add(evaluation)
        db.flush()
        feedback = Feedback(
            evaluation_id=evaluation.id,
            criterion_id="one",
            score=80,
            feedback_text="Existing feedback",
        )
        attempt = VerificationAttempt(
            submission_id=submission.id,
            student_id=ids["student"],
            assignment_id=ids["assignment"],
        )
        db.add_all([feedback, attempt])
        db.commit()
        assignee_id = assignee.id
        submission_id = submission.id
        evaluation_id = evaluation.id
        feedback_id = feedback.id
        attempt_id = attempt.id
    finally:
        db.close()

    assignment_url = f"/assignments/{ids['assignment']}"
    deactivated = context["client"].patch(
        assignment_url,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False

    context["acting"]["user_id"] = ids["student"]
    student_assignments = context["client"].get("/assignments").json()
    assert ids["assignment"] not in {
        assignment["id"] for assignment in student_assignments
    }

    context["acting"]["user_id"] = ids["teacher"]
    teacher_assignments = context["client"].get("/assignments").json()
    inactive_assignment = next(
        assignment for assignment in teacher_assignments
        if assignment["id"] == ids["assignment"]
    )
    assert inactive_assignment["is_active"] is False

    db = context["factory"]()
    try:
        assert db.get(AssignmentAssignee, assignee_id).topic_text == "Imported topic"
        assert db.get(Submission, submission_id) is not None
        assert db.get(Evaluation, evaluation_id).total_score == 80
        assert db.get(Feedback, feedback_id).feedback_text == "Existing feedback"
        assert db.get(VerificationAttempt, attempt_id) is not None
    finally:
        db.close()

    reactivated = context["client"].patch(
        assignment_url,
        json={"is_active": True},
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["is_active"] is True
    db = context["factory"]()
    try:
        assert db.get(AssignmentAssignee, assignee_id).topic_text == "Imported topic"
        assert db.get(Submission, submission_id) is not None
        assert db.get(Evaluation, evaluation_id).total_score == 80
        assert db.get(Feedback, feedback_id).feedback_text == "Existing feedback"
        assert db.get(VerificationAttempt, attempt_id) is not None
    finally:
        db.close()


def test_assignment_toggle_is_hidden_from_other_teachers_and_students(
    sqlite_upload_test_context,
):
    context = sqlite_upload_test_context
    assignment_id = context["ids"]["assignment"]
    url = f"/assignments/{assignment_id}"

    context["acting"]["user_id"] = context["ids"]["other_teacher"]
    other_teacher = context["client"].patch(url, json={"is_active": False})
    assert other_teacher.status_code == 404

    context["acting"]["user_id"] = context["ids"]["student"]
    student = context["client"].patch(url, json={"is_active": False})
    assert student.status_code == 403


def test_assignment_patch_uses_the_role_of_the_bearer_token(
    sqlite_upload_test_context,
    monkeypatch,
):
    context = sqlite_upload_test_context
    ids = context["ids"]
    monkeypatch.setattr(auth_service, "JWT_SECRET", "test-assignment-role-secret")
    context["app"].dependency_overrides.pop(get_current_user)

    db: Session = context["factory"]()
    try:
        teacher = db.get(User, ids["teacher"])
        student = db.get(User, ids["student"])
        assert teacher is not None
        assert student is not None
        teacher_token = auth_service.create_access_token({
            "sub": teacher.email,
            "user_id": teacher.id,
            "role": teacher.role.value,
        })
        student_token = auth_service.create_access_token({
            "sub": student.email,
            "user_id": student.id,
            "role": student.role.value,
        })
    finally:
        db.close()

    url = f"/assignments/{ids['assignment']}"
    student_response = context["client"].patch(
        url,
        json={"is_active": False},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert student_response.status_code == 403

    teacher_response = context["client"].patch(
        url,
        json={"is_active": False},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert teacher_response.status_code == 200
    assert teacher_response.json()["is_active"] is False


def test_student_submission_to_inactive_assignment_returns_conflict(
    sqlite_upload_test_context,
):
    context = sqlite_upload_test_context
    assignment_id = context["ids"]["assignment"]
    deactivated = context["client"].patch(
        f"/assignments/{assignment_id}",
        json={"is_active": False},
    )
    assert deactivated.status_code == 200

    context["acting"]["user_id"] = context["ids"]["student"]
    response = context["client"].post(
        "/submissions/upload",
        data={"assignment_id": str(assignment_id)},
        files={"file": ("work.txt", b"work", "text/plain")},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This assignment is inactive and no longer accepts submissions."
    )
    assert context["storage"].saved_keys == []
