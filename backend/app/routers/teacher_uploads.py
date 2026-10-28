import asyncio
import hashlib
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unicodedata

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import (
    EXCEL_MAX_ROWS,
    MAX_TEACHER_UPLOAD_FILES,
    MAX_UPLOAD_BYTES,
    TEACHER_STUDENTS_PAGE_SIZE,
    TEACHER_UPLOAD_CONCURRENCY,
    UPLOAD_PROCESSING_TIMEOUT_MINUTES,
)
from app.database import SessionLocal, get_db
from app.models import (
    Assignment,
    AssignmentAssignee,
    StudentMatchStatus,
    Submission,
    SubmissionSource,
    SubmissionStatus,
    UploadBatch,
    UploadBatchFile,
    UploadBatchFileStatus,
    UploadBatchStatus,
    User,
    UserRole,
)
from app.routers.auth import get_current_user, require_teacher
from app.routers.submissions import _evaluate_submission
from app.schemas.teacher_uploads import (
    ConfirmUploadRequest,
    RejectUploadRequest,
    TeacherStudentsPage,
    TeacherUploadBatchPage,
    UploadBatchCreatedResponse,
    UploadBatchFileResponse,
    UploadBatchRenameRequest,
    UploadBatchRenameResponse,
    UploadBatchResponse,
)
from app.services.excel_parser import ExcelParseError, parse_excel, validate_excel_upload
from app.services.file_storage import delete_storage_objects, get_storage
from app.services.roster_detection import (
    detect_roster_layouts,
    roster_layout_payload,
)
from app.services.student_matching import (
    StudentCandidate,
    detect_student_name,
    detect_student_name_with_llm,
    match_student,
)
from app.services.verification_service import SubmissionVerificationService

router = APIRouter(prefix="/teacher", tags=["teacher uploads"])
logger = logging.getLogger(__name__)
_UPLOAD_CONCURRENCY = max(1, min(2, TEACHER_UPLOAD_CONCURRENCY))
_BATCH_SEMAPHORE = threading.BoundedSemaphore(_UPLOAD_CONCURRENCY)
_PROCESSING_STATUSES = (
    UploadBatchFileStatus.PROCESSING,
    UploadBatchFileStatus.PARSED,
    UploadBatchFileStatus.NAME_DETECTED,
    UploadBatchFileStatus.MATCHED,
    UploadBatchFileStatus.GRADING,
    UploadBatchFileStatus.UPLOADED,
    UploadBatchFileStatus.GRADING,
)
_IN_PROGRESS_FILE_STATUSES = (
    UploadBatchFileStatus.PROCESSING,
    UploadBatchFileStatus.PARSED,
    UploadBatchFileStatus.NAME_DETECTED,
    UploadBatchFileStatus.MATCHED,
    UploadBatchFileStatus.GRADING,
)


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _owned_assignment(
    db: Session, assignment_id: int, teacher: User
) -> Assignment | None:
    query = db.query(Assignment).filter(Assignment.id == assignment_id)
    if not _is_admin(teacher):
        query = query.filter(Assignment.teacher_id == teacher.id)
    return query.first()


def _teacher_assignments(db: Session, teacher: User) -> list[Assignment]:
    query = db.query(Assignment)
    if not _is_admin(teacher):
        query = query.filter(Assignment.teacher_id == teacher.id)
    return query.order_by(Assignment.id).all()


def _normalize_batch_name(name: str | None) -> str | None:
    if name is None:
        return None
    without_controls = "".join(
        character for character in name
        if unicodedata.category(character) != "Cc"
    )
    normalized = re.sub(r"\s+", " ", without_controls).strip()
    if len(normalized) > 120:
        raise HTTPException(
            status_code=422,
            detail="Batch name must be 120 characters or fewer.",
        )
    return normalized or None


def _eligible_student_ids(db: Session, assignment: Assignment) -> set[int] | None:
    assignee_ids = {
        row.student_id
        for row in db.query(AssignmentAssignee.student_id)
        .filter(AssignmentAssignee.assignment_id == assignment.id)
        .all()
    }
    return assignee_ids or None


def _student_is_eligible(db: Session, assignment: Assignment, student_id: int) -> bool:
    allowed = _eligible_student_ids(db, assignment)
    return allowed is None or student_id in allowed


def _student_pool(
    db: Session, teacher: User, target_assignment: Assignment | None
) -> list[StudentCandidate]:
    if target_assignment:
        allowed = _eligible_student_ids(db, target_assignment)
        query = db.query(User).filter(User.role == UserRole.STUDENT)
        if allowed is not None:
            query = query.filter(User.id.in_(allowed))
        users = query.order_by(User.full_name, User.id).all()
        return [StudentCandidate(id=user.id, full_name=user.full_name) for user in users]

    assignments = _teacher_assignments(db, teacher)
    if any(_eligible_student_ids(db, assignment) is None for assignment in assignments):
        query = db.query(User).filter(User.role == UserRole.STUDENT)
    else:
        eligible_ids = {
            student_id
            for assignment in assignments
            for student_id in (_eligible_student_ids(db, assignment) or set())
        }
        if not eligible_ids:
            return []
        query = db.query(User).filter(
            User.role == UserRole.STUDENT,
            User.id.in_(eligible_ids),
        )
    users = query.order_by(User.full_name, User.id).all()
    return [StudentCandidate(id=user.id, full_name=user.full_name) for user in users]


def _eligible_assignments_for_student(
    db: Session,
    teacher: User,
    student_id: int,
    target_assignment_id: int | None = None,
) -> list[Assignment]:
    assignments = _teacher_assignments(db, teacher)
    if target_assignment_id is not None:
        assignments = [
            assignment
            for assignment in assignments
            if assignment.id == target_assignment_id
        ]
    return [
        assignment
        for assignment in assignments
        if _student_is_eligible(db, assignment, student_id)
    ]


def _assignment_label(assignment: Assignment) -> str:
    return f"{assignment.subject_code}: {assignment.title}"


def _batch_file_response(db: Session, item: UploadBatchFile) -> UploadBatchFileResponse:
    student = (
        db.query(User)
        .filter(User.id == item.resolved_student_id)
        .first()
        if item.resolved_student_id is not None
        else None
    )
    assignment = (
        db.query(Assignment)
        .filter(Assignment.id == item.resolved_assignment_id)
        .first()
        if item.resolved_assignment_id is not None
        else None
    )
    detection = item.name_detection or {}
    parse_counts = detection.get("parse_counts") or {}
    candidates = item.candidates or []
    submission_status = (
        db.query(Submission.status)
        .filter(Submission.id == item.submission_id)
        .scalar()
        if item.submission_id
        else None
    )
    return UploadBatchFileResponse(
        id=item.id,
        filename=item.original_filename,
        status=item.status.value,
        detected_name=item.detected_name,
        detected_name_source=detection.get("signal_source"),
        name_candidates=candidates,
        match_status=item.match_status.value if item.match_status else None,
        resolved_student_id=student.id if student else None,
        resolved_student_name=student.full_name if student else None,
        resolved_assignment_id=assignment.id if assignment else None,
        resolved_assignment_name=_assignment_label(assignment) if assignment else None,
        grading_status=submission_status.value if submission_status else None,
        error=item.error,
        warning=(
            f"Only the first {parse_counts.get('row_limit', EXCEL_MAX_ROWS)} rows per sheet were read; "
            f"{parse_counts.get('truncated_rows')} additional non-empty rows were omitted."
            if parse_counts.get("truncated") and parse_counts.get("truncated_rows", 0)
            else (
                "Some cell data was omitted to stay within the spreadsheet cell limit."
                if parse_counts.get("truncated")
                else None
            )
        ),
        roster_detected=item.status == UploadBatchFileStatus.ROSTER_DETECTED,
        roster_message=(
            "This looks like a class list, not one student's submission. Use Import assignments."
            if item.status == UploadBatchFileStatus.ROSTER_DETECTED
            else None
        ),
        roster_layout=(
            detection.get("roster_layout")
            if item.status == UploadBatchFileStatus.ROSTER_DETECTED
            else None
        ),
        submission_id=item.submission_id,
    )


@router.get("/students", response_model=TeacherStudentsPage)
def list_teacher_students(
    query: str = Query(min_length=2, max_length=255),
    limit: int = Query(default=TEACHER_STUDENTS_PAGE_SIZE, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    del teacher
    normalized_query = query.strip().casefold()
    if len(normalized_query) < 2:
        raise HTTPException(status_code=422, detail="Search query must contain at least 2 characters")
    filters = (
        User.role == UserRole.STUDENT,
        or_(
            func.lower(User.full_name).contains(normalized_query),
            func.lower(User.email).contains(normalized_query),
            func.upper(User.roll_no).contains(normalized_query.upper()),
        ),
    )
    total = db.query(func.count(User.id)).filter(*filters).scalar() or 0
    students = (
        db.query(User)
        .filter(*filters)
        .order_by(User.full_name, User.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "roll_no": user.roll_no,
            }
            for user in students
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/uploads", response_model=TeacherUploadBatchPage)
def list_teacher_upload_batches(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    query = db.query(UploadBatch)
    if not _is_admin(teacher):
        query = query.filter(UploadBatch.teacher_id == teacher.id)
    total = query.count()
    batches = (
        query.order_by(UploadBatch.created_at.desc(), UploadBatch.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    batch_ids = [batch.id for batch in batches]
    status_counts: dict[int, dict[str, int]] = {batch_id: {} for batch_id in batch_ids}
    if batch_ids:
        rows = (
            db.query(
                UploadBatchFile.batch_id,
                UploadBatchFile.status,
                func.count(UploadBatchFile.id),
            )
            .filter(UploadBatchFile.batch_id.in_(batch_ids))
            .group_by(UploadBatchFile.batch_id, UploadBatchFile.status)
            .all()
        )
        for batch_id, file_status, count in rows:
            status_counts[batch_id][file_status.value] = count
    return {
        "items": [
            {
                "id": batch.id,
                "name": batch.name,
                "status": batch.status.value,
                "file_count": batch.file_count,
                "created_at": batch.created_at,
                "counts": status_counts[batch.id],
            }
            for batch in batches
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/uploads",
    response_model=UploadBatchCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_upload_batch(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    assignment_id: int | None = Form(default=None),
    name: str | None = Form(default=None),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    batch_name = _normalize_batch_name(name)
    if not files:
        raise HTTPException(status_code=422, detail="Select at least one spreadsheet file")
    if len(files) > MAX_TEACHER_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"At most {MAX_TEACHER_UPLOAD_FILES} files may be uploaded per request",
        )
    target_assignment = None
    if assignment_id is not None:
        target_assignment = _owned_assignment(db, assignment_id, teacher)
        if not target_assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")

    uploads: list[tuple[str, bytes, str]] = []
    for upload in files:
        filename = (upload.filename or "").replace("\\", "/").split("/")[-1][:255]
        if not filename:
            raise HTTPException(status_code=422, detail="Every file needs a filename")
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        try:
            if len(content) > MAX_UPLOAD_BYTES:
                raise ValueError(
                    f"Uploaded file exceeds the {MAX_UPLOAD_BYTES}-byte limit"
                )
            validate_excel_upload(content, filename, upload.content_type)
        except ValueError as error:
            message = str(error)
            error_status = (
                status.HTTP_413_CONTENT_TOO_LARGE
                if "byte limit" in message or "uncompressed-size limit" in message
                else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
                if "supported" in message or "MIME type" in message
                else                 status.HTTP_422_UNPROCESSABLE_CONTENT
            )
            raise HTTPException(status_code=error_status, detail=message) from error
        uploads.append(
            (filename, content, upload.content_type or "application/octet-stream")
        )

    stored_keys: list[str] = []
    batch: UploadBatch | None = None
    try:
        storage = get_storage()
        for filename, content, content_type in uploads:
            key = await run_in_threadpool(storage.save, filename, content, content_type)
            stored_keys.append(key)
        batch = UploadBatch(
            teacher_id=teacher.id,
            name=batch_name,
            target_assignment_id=target_assignment.id if target_assignment else None,
            file_count=len(uploads),
            status=UploadBatchStatus.PENDING,
        )
        db.add(batch)
        db.flush()
        db.add_all(
            UploadBatchFile(
                batch_id=batch.id,
                storage_key=key,
                original_filename=filename,
                content_hash=hashlib.sha256(content).hexdigest(),
                status=UploadBatchFileStatus.UPLOADED,
            )
            for (filename, content, _content_type), key in zip(uploads, stored_keys)
        )
        db.commit()
        db.refresh(batch)
    except Exception as error:
        db.rollback()
        for key in stored_keys:
            try:
                await run_in_threadpool(get_storage().delete, key)
            except Exception as cleanup_error:
                logger.error(
                    "Upload cleanup failed: exception_type=%s",
                    type(cleanup_error).__name__,
                )
        raise HTTPException(status_code=500, detail="Could not save uploaded batch") from error

    background_tasks.add_task(process_upload_batch, batch.id)
    return {
        "id": batch.id,
        "name": batch.name,
        "status": batch.status.value,
        "file_count": batch.file_count,
    }


@router.get("/uploads/{batch_id}", response_model=UploadBatchResponse)
def get_upload_batch(
    batch_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    query = db.query(UploadBatch).filter(UploadBatch.id == batch_id)
    if not _is_admin(teacher):
        query = query.filter(UploadBatch.teacher_id == teacher.id)
    batch = query.first()
    if not batch:
        raise HTTPException(status_code=404, detail="Upload batch not found")
    files = (
        db.query(UploadBatchFile)
        .filter(UploadBatchFile.batch_id == batch.id)
        .order_by(UploadBatchFile.id)
        .all()
    )
    return {
        "id": batch.id,
        "name": batch.name,
        "status": batch.status.value,
        "file_count": batch.file_count,
        "created_at": batch.created_at,
        "files": [_batch_file_response(db, item) for item in files],
    }


@router.patch(
    "/uploads/{batch_id}",
    response_model=UploadBatchRenameResponse,
)
def rename_upload_batch(
    batch_id: int,
    request: UploadBatchRenameRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    batch = (
        db.query(UploadBatch)
        .filter(
            UploadBatch.id == batch_id,
            UploadBatch.teacher_id == teacher.id,
        )
        .first()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Upload batch not found")
    batch.name = _normalize_batch_name(request.name)
    db.commit()
    db.refresh(batch)
    return {"id": batch.id, "name": batch.name}


@router.delete("/upload-batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload_batch(
    batch_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    batch = (
        db.query(UploadBatch)
        .filter(
            UploadBatch.id == batch_id,
            UploadBatch.teacher_id == teacher.id,
        )
        .with_for_update()
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Upload batch not found")

    files = db.query(UploadBatchFile).filter(
        UploadBatchFile.batch_id == batch.id
    ).all()
    if batch.status == UploadBatchStatus.PROCESSING or any(
        item.status in _IN_PROGRESS_FILE_STATUSES for item in files
    ):
        raise HTTPException(
            status_code=409,
            detail="This upload batch is still processing. Try again when it finishes.",
        )

    submissions = db.query(Submission).filter(
        Submission.upload_batch_id == batch.id
    ).all()
    file_keys = {
        key
        for key in (
            *(item.storage_key for item in files),
            *(submission.file_path for submission in submissions),
        )
        if key
    }

    try:
        for submission in submissions:
            submission.upload_batch_id = None
            if submission.file_path in file_keys:
                submission.file_path = None
        db.query(UploadBatchFile).filter(
            UploadBatchFile.batch_id == batch.id
        ).delete(synchronize_session=False)
        db.delete(batch)
        db.commit()
    except Exception as error:
        db.rollback()
        logger.error(
            "Upload batch deletion transaction failed: exception_type=%s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not delete the upload batch.",
        ) from error

    if file_keys:
        try:
            delete_storage_objects(get_storage(), file_keys)
        except Exception as error:
            logger.error(
                "Upload batch file cleanup failed: exception_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="The upload batch was deleted, but some stored files could not be removed.",
            ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/upload-batches/{batch_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_upload_batch_file(
    batch_id: int,
    file_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    batch = (
        db.query(UploadBatch)
        .filter(
            UploadBatch.id == batch_id,
            UploadBatch.teacher_id == teacher.id,
        )
        .with_for_update()
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Upload batch not found")
    item = (
        db.query(UploadBatchFile)
        .filter(
            UploadBatchFile.id == file_id,
            UploadBatchFile.batch_id == batch.id,
        )
        .with_for_update()
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Upload file not found")
    if batch.status == UploadBatchStatus.PROCESSING or item.status in _IN_PROGRESS_FILE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="This upload file is still processing. Try again when it finishes.",
        )
    if item.submission_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This file is linked to a submission and cannot be deleted individually.",
        )

    storage_key = item.storage_key
    try:
        db.delete(item)
        batch.file_count = db.query(func.count(UploadBatchFile.id)).filter(
            UploadBatchFile.batch_id == batch.id,
            UploadBatchFile.id != item.id,
        ).scalar() or 0
        db.commit()
    except Exception as error:
        db.rollback()
        logger.error(
            "Upload file deletion transaction failed: exception_type=%s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not delete the upload file.",
        ) from error

    try:
        delete_storage_objects(get_storage(), [storage_key])
    except Exception as error:
        logger.error(
            "Upload file cleanup failed: exception_type=%s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="The upload file was deleted, but its stored contents could not be removed.",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_owned_batch_file(
    db: Session, teacher: User, batch_id: int, file_id: int
) -> tuple[UploadBatch, UploadBatchFile]:
    query = (
        db.query(UploadBatch, UploadBatchFile)
        .join(UploadBatchFile, UploadBatchFile.batch_id == UploadBatch.id)
        .filter(UploadBatch.id == batch_id, UploadBatchFile.id == file_id)
    )
    if not _is_admin(teacher):
        query = query.filter(UploadBatch.teacher_id == teacher.id)
    result = query.first()
    if not result:
        raise HTTPException(status_code=404, detail="Upload file not found")
    return result


@router.post("/uploads/{batch_id}/files/{file_id}/confirm", status_code=202)
def confirm_upload_file(
    batch_id: int,
    file_id: int,
    request: ConfirmUploadRequest,
    background_tasks: BackgroundTasks,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    batch, item = _get_owned_batch_file(db, teacher, batch_id, file_id)
    if item.status not in {
        UploadBatchFileStatus.AWAITING_CONFIRMATION,
        UploadBatchFileStatus.DUPLICATE,
    }:
        raise HTTPException(status_code=409, detail="Upload file is not awaiting confirmation")
    if item.status == UploadBatchFileStatus.DUPLICATE and not request.allow_duplicate:
        raise HTTPException(
            status_code=409,
            detail="This file is a duplicate; set allow_duplicate to create another submission",
        )
    student = db.query(User).filter(
        User.id == request.student_id,
        User.role == UserRole.STUDENT,
    ).first()
    if not student:
        raise HTTPException(status_code=422, detail="Selected user is not a student")
    assignment_id = request.assignment_id or item.resolved_assignment_id or batch.target_assignment_id
    if (
        batch.target_assignment_id is not None
        and assignment_id != batch.target_assignment_id
    ):
        raise HTTPException(
            status_code=422,
            detail="The assignment selected when uploading this batch cannot be changed",
        )
    if assignment_id is None:
        eligible = _eligible_assignments_for_student(db, teacher, student.id)
        if len(eligible) != 1:
            raise HTTPException(
                status_code=422,
                detail="Select one assignment owned by you for this student",
            )
        assignment = eligible[0]
    else:
        assignment = _owned_assignment(db, assignment_id, teacher)
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
    if not _student_is_eligible(db, assignment, student.id):
        raise HTTPException(status_code=422, detail="Student is not assigned to this assignment")
    duplicate_exists = (
        db.query(Submission.id)
        .filter(
            Submission.student_id == student.id,
            Submission.assignment_id == assignment.id,
            Submission.content_hash == item.content_hash,
        )
        .first()
        is not None
    )
    if duplicate_exists and not request.allow_duplicate:
        item.status = UploadBatchFileStatus.DUPLICATE
        item.error = "This student already has a submission with identical content for this assignment."
        item.resolved_student_id = student.id
        item.resolved_assignment_id = assignment.id
        item.match_status = StudentMatchStatus.CONFIRMED_BY_TEACHER
        db.commit()
        raise HTTPException(status_code=409, detail=item.error)

    submission = Submission(
        student_id=student.id,
        assignment_id=assignment.id,
        file_path=item.storage_key,
        original_filename=item.original_filename,
        file_type="spreadsheet",
        status=SubmissionStatus.UPLOADED,
        content_hash=item.content_hash,
        uploaded_by_teacher_id=batch.teacher_id,
        source=SubmissionSource.TEACHER_UPLOAD,
        upload_batch_id=batch.id,
        name_detection=item.name_detection,
        match_confidence=(item.name_detection or {}).get("confidence"),
        match_status=StudentMatchStatus.CONFIRMED_BY_TEACHER,
        teacher_confirmed_by=teacher.id,
        teacher_confirmed_at=datetime.now(timezone.utc),
    )
    db.add(submission)
    db.flush()
    item.resolved_student_id = student.id
    item.resolved_assignment_id = assignment.id
    item.submission_id = submission.id
    item.match_status = StudentMatchStatus.CONFIRMED_BY_TEACHER
    item.status = UploadBatchFileStatus.GRADING
    item.error = None
    item.failed_step = None
    db.commit()
    background_tasks.add_task(process_upload_batch, batch.id, [item.id])
    return {"file_id": item.id, "submission_id": submission.id, "status": "grading"}


@router.post("/uploads/{batch_id}/files/{file_id}/reject", status_code=200)
def reject_upload_file(
    batch_id: int,
    file_id: int,
    request: RejectUploadRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _batch, item = _get_owned_batch_file(db, teacher, batch_id, file_id)
    if item.status in {UploadBatchFileStatus.GRADED, UploadBatchFileStatus.REJECTED}:
        raise HTTPException(status_code=409, detail="Upload file can no longer be rejected")
    item.status = UploadBatchFileStatus.REJECTED
    item.error = request.reason.strip()
    item.failed_step = None
    db.commit()
    return {"file_id": item.id, "status": item.status.value}


@router.post("/uploads/{batch_id}/files/{file_id}/retry", status_code=202)
def retry_upload_file(
    batch_id: int,
    file_id: int,
    background_tasks: BackgroundTasks,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    batch, item = _get_owned_batch_file(db, teacher, batch_id, file_id)
    if item.status != UploadBatchFileStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed upload files can be retried")
    item.status = (
        UploadBatchFileStatus.GRADING
        if item.submission_id is not None
        else UploadBatchFileStatus.UPLOADED
    )
    item.error = None
    item.failed_step = None
    db.commit()
    background_tasks.add_task(process_upload_batch, batch.id, [item.id])
    return {"file_id": item.id, "status": item.status.value}


def _assignment_topic_terms(assignment: Assignment | None) -> list[str]:
    if not assignment:
        return []
    return [
        assignment.subject_name,
        assignment.subject_code,
        assignment.title,
    ]


def _persist_file_failure(item_id: int, error: Exception) -> None:
    session = SessionLocal()
    try:
        item = session.query(UploadBatchFile).filter(UploadBatchFile.id == item_id).first()
        if item:
            failed_step = item.failed_step or item.status.value
            item.status = UploadBatchFileStatus.FAILED
            item.failed_step = failed_step
            detail = (
                str(error).strip()
                if isinstance(error, ExcelParseError)
                else str(error).strip()
                if isinstance(error, ValueError)
                else "An unexpected processing error occurred."
            )
            item.error = (
                f"Processing failed: {detail or type(error).__name__}"
            )[:2000]
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not persist teacher upload failure: file_id=%s", item_id)
    finally:
        session.close()


async def _process_batch(batch_id: int, only_file_ids: list[int] | None = None) -> None:
    with _BATCH_SEMAPHORE:
        db = SessionLocal()
        try:
            batch = (
                db.query(UploadBatch)
                .filter(UploadBatch.id == batch_id)
                .with_for_update()
                .first()
            )
            if not batch:
                logger.error("Teacher upload batch not found: batch_id=%s", batch_id)
                return
            batch.status = UploadBatchStatus.PROCESSING
            db.commit()
            file_query = db.query(UploadBatchFile).filter(
                UploadBatchFile.batch_id == batch.id
            )
            if only_file_ids:
                file_query = file_query.filter(UploadBatchFile.id.in_(only_file_ids))
            files = file_query.order_by(UploadBatchFile.id).all()
            for file_row in files:
                if file_row.status in {
                    UploadBatchFileStatus.GRADED,
                    UploadBatchFileStatus.NEEDS_ATTENTION,
                    UploadBatchFileStatus.REJECTED,
                    UploadBatchFileStatus.DUPLICATE,
                    UploadBatchFileStatus.AWAITING_CONFIRMATION,
                    UploadBatchFileStatus.ROSTER_DETECTED,
                    UploadBatchFileStatus.IMPORTED,
                }:
                    continue
                if file_row.status == UploadBatchFileStatus.PROCESSING:
                    file_row.status = UploadBatchFileStatus.UPLOADED
                    db.commit()
                file_id = file_row.id
                try:
                    if file_row.submission_id is not None:
                        file_row.status = UploadBatchFileStatus.GRADING
                        file_row.failed_step = "grading"
                        db.commit()
                        await _grade_submission(db, file_row, file_row.submission_id)
                    else:
                        await _process_batch_file(db, batch, file_row)
                except Exception as error:
                    db.rollback()
                    _persist_file_failure(file_id, error)
                    logger.exception(
                        "Teacher upload file processing failed: batch_id=%s file_id=%s",
                        batch_id,
                        file_id,
                    )
                db.expire_all()
                batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
            unfinished = (
                db.query(UploadBatchFile.id)
                .filter(
                    UploadBatchFile.batch_id == batch_id,
                    UploadBatchFile.status.in_(
                        (
                            UploadBatchFileStatus.UPLOADED,
                            UploadBatchFileStatus.PROCESSING,
                            UploadBatchFileStatus.PARSED,
                            UploadBatchFileStatus.NAME_DETECTED,
                            UploadBatchFileStatus.MATCHED,
                            UploadBatchFileStatus.GRADING,
                        )
                    ),
                )
                .first()
            )
            failed = (
                db.query(UploadBatchFile.id)
                .filter(
                    UploadBatchFile.batch_id == batch_id,
                    UploadBatchFile.status == UploadBatchFileStatus.FAILED,
                )
                .first()
            )
            batch.status = (
                UploadBatchStatus.FAILED
                if failed
                else UploadBatchStatus.PROCESSING
                if unfinished
                else UploadBatchStatus.COMPLETED
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Teacher upload batch processing failed: batch_id=%s", batch_id)
        finally:
            db.close()


async def _process_batch_file(
    db: Session, batch: UploadBatch, item: UploadBatchFile
) -> None:
    item.status = UploadBatchFileStatus.PROCESSING
    item.failed_step = "parsing"
    item.error = None
    db.commit()

    content = await run_in_threadpool(get_storage().read, item.storage_key)
    parsed = await run_in_threadpool(parse_excel, content, item.original_filename)
    item.parsed_text = parsed.text
    item.has_visual_content = parsed.has_visual_content
    item.content_hash = SubmissionVerificationService.content_hash(parsed.text, None)
    item.name_detection = {
        "parse_counts": {
            "truncated": parsed.truncated,
            "row_limit": EXCEL_MAX_ROWS,
            "real_rows": parsed.real_row_count,
            "rows_retained": parsed.retained_row_count,
            "truncated_rows": parsed.truncated_row_count,
            "truncated_cells": parsed.truncated_cell_count,
        }
    } if parsed.truncated else None
    item.status = UploadBatchFileStatus.PARSED
    item.failed_step = None
    db.commit()

    roster_layouts = detect_roster_layouts(parsed, item.original_filename)
    if roster_layouts:
        item.status = UploadBatchFileStatus.ROSTER_DETECTED
        item.name_detection = {
            "parse_counts": (item.name_detection or {}).get("parse_counts"),
            "roster_layout": roster_layout_payload(roster_layouts[0]),
            "additional_roster_layouts": [
                roster_layout_payload(layout) for layout in roster_layouts[1:]
            ],
        }
        db.commit()
        return

    target_assignment = (
        db.query(Assignment)
        .filter(Assignment.id == batch.target_assignment_id)
        .first()
        if batch.target_assignment_id
        else None
    )
    batch_teacher = db.query(User).filter(User.id == batch.teacher_id).first()
    if not batch_teacher:
        raise ValueError("Upload batch owner no longer exists")
    candidates = _student_pool(db, batch_teacher, target_assignment)
    try:
        detection = await detect_student_name_with_llm(
            parsed,
            item.original_filename,
            _assignment_topic_terms(target_assignment),
            use_mock=not bool(os.getenv("GROQ_API_KEY", "").strip()),
        )
    except ValueError as error:
        logger.warning(
            "Teacher upload name extraction fallback: file_id=%s exception_type=%s",
            item.id,
            type(error).__name__,
        )
        detection = detect_student_name(
            parsed,
            item.original_filename,
            _assignment_topic_terms(target_assignment),
        )
    item.detected_name = detection.detected_name
    item.name_detection = {
        "detected_name": detection.detected_name,
        "signal_source": detection.signal_source,
        "confidence": detection.confidence,
        "parse_counts": (item.name_detection or {}).get("parse_counts"),
        "candidates": [
            {
                "name": signal.name,
                "source": signal.source,
                "confidence": signal.confidence,
            }
            for signal in detection.candidates
        ],
    }
    item.status = UploadBatchFileStatus.NAME_DETECTED
    item.failed_step = "matching"
    db.commit()

    match = match_student(
        detection.detected_name,
        candidates,
        name_confidence=detection.confidence,
    )
    item.match_status = StudentMatchStatus(match.match_status)
    item.candidates = list(match.candidates)
    item.status = UploadBatchFileStatus.MATCHED
    item.failed_step = "assignment_resolution"
    item.resolved_student_id = match.resolved_student_id
    db.commit()

    if match.resolved_student_id is None:
        item.status = UploadBatchFileStatus.AWAITING_CONFIRMATION
        db.commit()
        return

    eligible_assignments = _eligible_assignments_for_student(
        db,
        batch_teacher,
        match.resolved_student_id,
        batch.target_assignment_id,
    )
    if len(eligible_assignments) != 1:
        item.status = UploadBatchFileStatus.AWAITING_CONFIRMATION
        db.commit()
        return

    student_id = match.resolved_student_id
    assignment = eligible_assignments[0]
    duplicate_exists = (
        db.query(Submission.id)
        .filter(
            Submission.student_id == student_id,
            Submission.assignment_id == assignment.id,
            Submission.content_hash == item.content_hash,
        )
        .first()
        is not None
    )
    item.resolved_assignment_id = assignment.id
    if duplicate_exists:
        item.status = UploadBatchFileStatus.DUPLICATE
        item.error = "An identical submission already exists for this student and assignment."
        db.commit()
        return

    submission = Submission(
        student_id=student_id,
        assignment_id=assignment.id,
        file_path=item.storage_key,
        original_filename=item.original_filename,
        file_type="spreadsheet",
        status=SubmissionStatus.UPLOADED,
        content_hash=item.content_hash,
        uploaded_by_teacher_id=batch.teacher_id,
        source=SubmissionSource.TEACHER_UPLOAD,
        upload_batch_id=batch.id,
        name_detection=item.name_detection,
        match_confidence=detection.confidence,
        match_status=StudentMatchStatus.AUTO_MATCHED,
    )
    db.add(submission)
    db.flush()
    item.submission_id = submission.id
    item.status = UploadBatchFileStatus.GRADING
    item.failed_step = "grading"
    db.commit()
    await _grade_submission(db, item, submission.id)


async def _grade_submission(db: Session, item: UploadBatchFile, submission_id: int) -> None:
    result = await _evaluate_submission(
        submission_id,
        1,
        not bool(os.getenv("GROQ_API_KEY", "").strip()),
        db,
        record_attempt=False,
    )
    item = db.query(UploadBatchFile).filter(UploadBatchFile.id == item.id).first()
    if item:
        item.status = (
            UploadBatchFileStatus.NEEDS_ATTENTION
            if result.get("status") == SubmissionStatus.NEEDS_ATTENTION
            else UploadBatchFileStatus.GRADED
        )
        item.failed_step = None
        item.error = None
        db.commit()


def process_upload_batch(
    batch_id: int, only_file_ids: list[int] | None = None
) -> None:
    asyncio.run(_process_batch(batch_id, only_file_ids))


def sweep_stale_upload_files(
    db: Session | None = None,
    *,
    now: datetime | None = None,
    timeout_minutes: int = UPLOAD_PROCESSING_TIMEOUT_MINUTES,
) -> int:
    own_session = db is None
    session = db or SessionLocal()
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(minutes=timeout_minutes)
    try:
        stale_items = (
            session.query(UploadBatchFile)
            .filter(
                UploadBatchFile.status.in_(_PROCESSING_STATUSES),
                UploadBatchFile.updated_at < cutoff,
            )
            .all()
        )
        for item in stale_items:
            item.status = UploadBatchFileStatus.FAILED
            item.failed_step = "recovery"
            item.error = "Processing was interrupted by an instance restart; retry this file."
        if stale_items:
            session.commit()
            batch_ids = {item.batch_id for item in stale_items}
            for batch_id in batch_ids:
                batch = session.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
                if batch:
                    batch.status = UploadBatchStatus.FAILED
            session.commit()
        return len(stale_items)
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def schedule_stale_upload_sweep() -> int:
    count = sweep_stale_upload_files()
    if count:
        logger.warning("Marked stale teacher upload files failed: count=%s", count)
    return count
