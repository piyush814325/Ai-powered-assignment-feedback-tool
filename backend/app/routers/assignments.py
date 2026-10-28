import logging
from datetime import datetime, timezone
from typing import List
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES, ROSTER_TOPIC_MAX_CHARS
from app.database import get_db
from app.models import (
    Assignment,
    AssignmentAssignee,
    Evaluation,
    Feedback,
    Submission,
    UploadBatch,
    UploadBatchFile,
    UploadBatchFileStatus,
    UploadBatchStatus,
    User,
    UserRole,
    VerificationAttempt,
)
from app.routers.auth import get_current_user, require_teacher
from app.schemas.schemas import AssignmentCreate, AssignmentResponse, AssignmentUpdate
from app.schemas.teacher_uploads import (
    AssigneeImportApprovedRow,
    AssigneeImportCandidate,
    AssigneeImportConfirmRequest,
    AssigneeImportPreviewResponse,
    AssigneeImportRow,
    AssigneeTopicUpdateRequest,
    AssignmentAssigneeStudent,
    AssignmentAssigneesRequest,
    AssignmentAssigneesResponse,
)
from app.services.excel_parser import parse_excel, validate_excel_upload
from app.services.roster_cells import clean_roster_cell, normalize_roll_no
from app.services.student_matching import (
    StudentCandidate,
    match_roster_student,
)
from app.services.file_storage import delete_storage_objects, get_storage
from rapidfuzz import fuzz

router = APIRouter(prefix="/assignments", tags=["assignments"])
logger = logging.getLogger(__name__)
_ACTIVE_UPLOAD_FILE_STATUSES = (
    UploadBatchFileStatus.PROCESSING,
    UploadBatchFileStatus.PARSED,
    UploadBatchFileStatus.NAME_DETECTED,
    UploadBatchFileStatus.MATCHED,
    UploadBatchFileStatus.GRADING,
)


def _owned_assignment_or_404(
    db: Session, assignment_id: int, teacher: User
) -> Assignment:
    query = db.query(Assignment).filter(Assignment.id == assignment_id)
    if teacher.role != UserRole.ADMIN:
        query = query.filter(Assignment.teacher_id == teacher.id)
    assignment = query.first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


def _assignee_rows(db: Session, assignment: Assignment) -> list[dict]:
    rows = (
        db.query(
            User.id,
            User.full_name,
            User.roll_no,
            AssignmentAssignee.topic_text,
            AssignmentAssignee.topic_number,
            AssignmentAssignee.source,
        )
        .join(AssignmentAssignee, AssignmentAssignee.student_id == User.id)
        .filter(
            AssignmentAssignee.assignment_id == assignment.id,
            User.role == UserRole.STUDENT,
        )
        .order_by(User.full_name, User.id)
        .all()
    )
    return [
        {
            "id": row.id,
            "full_name": row.full_name,
            "roll_no": normalize_roll_no(row.roll_no),
            "topic_text": row.topic_text,
            "topic_number": row.topic_number,
            "source": row.source,
        }
        for row in rows
    ]


@router.get("/{assignment_id}/assignees", response_model=AssignmentAssigneesResponse)
def list_assignment_assignees(
    assignment_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    return {"assignment_id": assignment.id, "students": _assignee_rows(db, assignment)}


@router.patch(
    "/{assignment_id}/assignees/{student_id}",
    response_model=AssignmentAssigneeStudent,
)
def update_assignment_assignee_topic(
    assignment_id: int,
    student_id: int,
    request: AssigneeTopicUpdateRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    topic = clean_roster_cell(request.topic_text, is_topic=True).text
    if not topic:
        raise HTTPException(status_code=422, detail="Topic text cannot be empty")
    if len(topic) > ROSTER_TOPIC_MAX_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Topic text must be {ROSTER_TOPIC_MAX_CHARS} characters or fewer",
        )
    assignee = (
        db.query(AssignmentAssignee)
        .join(User, User.id == AssignmentAssignee.student_id)
        .filter(
            AssignmentAssignee.assignment_id == assignment.id,
            AssignmentAssignee.student_id == student_id,
            User.role == UserRole.STUDENT,
        )
        .first()
    )
    if assignee is None:
        raise HTTPException(status_code=404, detail="Assignment assignee not found")
    assignee.topic_text = topic
    assignee.topic_number = (
        request.topic_number
        if request.topic_number is not None
        else clean_roster_cell(request.topic_text, is_topic=True).topic_number
    )
    db.commit()
    student = db.query(User).filter(User.id == student_id).one()
    return {
        "id": student.id,
        "full_name": student.full_name,
        "roll_no": normalize_roll_no(student.roll_no),
        "topic_text": assignee.topic_text,
        "topic_number": assignee.topic_number,
        "source": assignee.source,
    }


@router.put("/{assignment_id}/assignees", response_model=AssignmentAssigneesResponse)
def set_assignment_assignees(
    assignment_id: int,
    request: AssignmentAssigneesRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    student_ids = list(dict.fromkeys(request.student_ids))
    if student_ids:
        students = (
            db.query(User.id)
            .filter(User.id.in_(student_ids), User.role == UserRole.STUDENT)
            .all()
        )
        if len(students) != len(student_ids):
            raise HTTPException(status_code=422, detail="Every assignee must be a student account")
    existing_rows = db.query(AssignmentAssignee).filter(
        AssignmentAssignee.assignment_id == assignment.id
    ).all()
    existing_by_student = {row.student_id: row for row in existing_rows}
    requested_ids = set(student_ids)
    for existing in existing_rows:
        if existing.student_id not in requested_ids:
            db.delete(existing)
    db.add_all(
        AssignmentAssignee(assignment_id=assignment.id, student_id=student_id)
        for student_id in student_ids
        if student_id not in existing_by_student
    )
    db.commit()
    return {"assignment_id": assignment.id, "students": _assignee_rows(db, assignment)}


def _import_columns(
    row: tuple[str, ...],
) -> tuple[int | None, int | None, int | None]:
    student_column = None
    topic_column = None
    roll_column = None
    for index, value in enumerate(row):
        key = re.sub(r"[^a-z0-9]+", "", clean_roster_cell(value).text.casefold())
        if key in {"student", "studentname", "name"}:
            student_column = index
        elif key in {"topic", "topics", "assignment", "subject", "project", "title", "projecttopics"}:
            topic_column = index
        elif key in {"rollno", "rollnumber"}:
            roll_column = index
    return student_column, topic_column, roll_column


@router.post(
    "/{assignment_id}/assignees/import-preview",
    response_model=AssigneeImportPreviewResponse,
)
async def preview_assignment_assignee_import(
    assignment_id: int,
    file: UploadFile = File(...),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        validate_excel_upload(content, filename, file.content_type)
        parsed = parse_excel(content, filename)
    except ValueError as error:
        message = str(error)
        error_status = (
            status.HTTP_413_CONTENT_TOO_LARGE
            if "byte limit" in message or "uncompressed-size limit" in message
            else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            if "supported" in message or "MIME type" in message
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(status_code=error_status, detail=message) from error

    students = [
        StudentCandidate(
            id=user.id,
            full_name=user.full_name,
            roll_no=normalize_roll_no(user.roll_no),
        )
        for user in db.query(User)
        .filter(User.role == UserRole.STUDENT)
        .order_by(User.full_name, User.id)
        .all()
    ]
    rows: list[AssigneeImportRow] = []
    row_offset = 0
    has_student_header = False
    weak_topic_count = 0
    rows_with_topic_count = 0
    for sheet in parsed.sheets:
        if not sheet.rows:
            continue
        student_column, topic_column, roll_column = _import_columns(sheet.rows[0])
        if student_column is None:
            row_offset += len(sheet.rows)
            continue
        has_student_header = True
        for row_number, values in enumerate(sheet.rows[1:], start=row_offset + 2):
            student_name = clean_roster_cell(
                values[student_column] if student_column < len(values) else ""
            ).text
            topic_result = clean_roster_cell(
                values[topic_column] if topic_column is not None and topic_column < len(values) else "",
                is_topic=True,
            )
            topic = (
                topic_result.text
                if topic_column is not None and topic_column < len(values)
                else ""
            )
            roll_no = normalize_roll_no(
                values[roll_column] if roll_column is not None and roll_column < len(values) else ""
            )
            exact_roll = [candidate for candidate in students if getattr(candidate, "roll_no", None) == roll_no] if roll_no else []
            if len(exact_roll) == 1:
                match_status = "matched"
                candidates = [{
                    "student_id": exact_roll[0].id,
                    "full_name": exact_roll[0].full_name,
                    "score": 100,
                }]
            elif len(exact_roll) > 1:
                match_status = "ambiguous"
                candidates = [
                    {"student_id": candidate.id, "full_name": candidate.full_name, "score": 100}
                    for candidate in exact_roll[:3]
                ]
            else:
                match = match_roster_student(student_name, students)
                match_status = {
                    "auto_matched": "matched",
                    "needs_confirmation": "ambiguous",
                    "unmatched": "unmatched",
                }[match.match_status]
                candidates = list(match.candidates)
            if topic:
                rows_with_topic_count += 1
                topic_score = max(
                    fuzz.WRatio(topic, assignment.title),
                    fuzz.WRatio(topic, assignment.subject_name),
                    fuzz.WRatio(topic, assignment.subject_code),
                )
                topic_check = "ok" if topic_score >= 85 else "weak"
                if topic_check == "weak":
                    weak_topic_count += 1
            else:
                topic_check = "missing"
            rows.append(
                AssigneeImportRow(
                    row_number=row_number,
                    student_name=student_name,
                    topic=topic,
                    topic_check=topic_check,
                    status=match_status,
                    candidates=[
                        AssigneeImportCandidate(**candidate)
                        for candidate in candidates
                    ],
                    topic_number=topic_result.topic_number,
                )
            )
        row_offset += len(sheet.rows)
    if not has_student_header:
        raise HTTPException(
            status_code=422,
            detail="Spreadsheet must include a student column",
        )
    warning = (
        "Most topics in this file do not match this assignment. Check that you selected the right assignment."
        if rows_with_topic_count and weak_topic_count * 2 > rows_with_topic_count
        else None
    )
    return {"assignment_id": assignment.id, "rows": rows, "warning": warning}


@router.post(
    "/{assignment_id}/assignees/import-preview/confirm",
    response_model=AssignmentAssigneesResponse,
)
def confirm_assignment_assignee_import(
    assignment_id: int,
    request: AssigneeImportConfirmRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    approved_ids = list(dict.fromkeys([
        *request.student_ids,
        *(row.student_id for row in request.rows),
    ]))
    if approved_ids:
        students = (
            db.query(User.id)
            .filter(User.id.in_(approved_ids), User.role == UserRole.STUDENT)
            .all()
        )
        if len(students) != len(approved_ids):
            raise HTTPException(status_code=422, detail="Every approved assignee must be a student account")
    row_data = {row.student_id: row for row in request.rows}
    if len(row_data) != len(request.rows):
        raise HTTPException(status_code=422, detail="A student may appear only once in the import confirmation")
    try:
        for student_id in approved_ids:
            row: AssigneeImportApprovedRow | None = row_data.get(student_id)
            existing = db.query(AssignmentAssignee).filter(
                AssignmentAssignee.assignment_id == assignment.id,
                AssignmentAssignee.student_id == student_id,
            ).first()
            if row is None:
                if existing is None:
                    db.add(
                        AssignmentAssignee(
                            assignment_id=assignment.id,
                            student_id=student_id,
                        )
                    )
                continue
            topic_result = clean_roster_cell(row.topic_text, is_topic=True)
            topic_text = topic_result.text or None
            topic_number = row.topic_number if row.topic_number is not None else topic_result.topic_number
            if existing is None:
                db.add(AssignmentAssignee(
                    assignment_id=assignment.id,
                    student_id=student_id,
                    topic_text=topic_text,
                    topic_number=topic_number,
                    source="roster_import",
                    roster_row_ref=f"assignees-import#{row.row_number}" if row.row_number else None,
                ))
            else:
                if topic_text:
                    existing.topic_text = topic_text
                    existing.topic_number = topic_number
                existing.source = "roster_import"
                existing.roster_row_ref = (
                    f"assignees-import#{row.row_number}" if row.row_number else None
                )
        db.commit()
    except Exception as error:
        db.rollback()
        logger.error(
            "Assignment deletion transaction failed: exception_type=%s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not delete the assignment.",
        ) from error
    return {"assignment_id": assignment.id, "students": _assignee_rows(db, assignment)}


def assignment_response(assignment: Assignment) -> dict:
    return {
        "id": assignment.id,
        "teacher_id": assignment.teacher_id,
        "subject_name": assignment.subject_name,
        "subject_code": assignment.subject_code,
        "title": assignment.title,
        "description": assignment.description,
        "due_date": assignment.due_date,
        "max_score": assignment.max_score,
        "allowed_file_types": assignment.allowed_file_types or [],
        "rubric": assignment.rubric or [],
        "is_active": assignment.is_active,
        "submission_count": len(assignment.submissions),
        "created_at": assignment.created_at,
        "updated_at": assignment.updated_at,
    }


def normalize_rubric(criteria: list) -> list:
    normalized = []
    used_keys = set()
    for criterion in criteria:
        label = criterion.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="Every rubric criterion needs a label")
        key = (criterion.key or "").strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", key or label.lower()).strip("_")
        if not key:
            raise HTTPException(status_code=400, detail="Rubric criterion keys must contain letters or numbers")
        if key in used_keys:
            raise HTTPException(status_code=400, detail=f"Duplicate rubric criterion key: {key}")
        if criterion.max_points <= 0:
            raise HTTPException(status_code=400, detail="Rubric max points must be greater than zero")
        used_keys.add(key)
        normalized.append({"key": key, "label": label, "description": (criterion.description or "").strip(), "max_points": criterion.max_points})
    return normalized


def validate_assignment(data: AssignmentCreate | AssignmentUpdate, existing: Assignment | None = None) -> list | None:
    if data.max_score is not None and data.max_score <= 0:
        raise HTTPException(status_code=400, detail="Max score must be greater than zero")
    if data.allowed_file_types is not None and not data.allowed_file_types:
        raise HTTPException(status_code=400, detail="Select at least one allowed file type")
    if data.due_date is not None:
        due_date = data.due_date
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)
        if due_date <= datetime.now(timezone.utc) and isinstance(data, AssignmentCreate):
            raise HTTPException(status_code=400, detail="Due date must be in the future")
    rubric = normalize_rubric(data.rubric) if data.rubric is not None else None
    max_score = data.max_score if data.max_score is not None else (existing.max_score if existing else 100)
    is_active = data.is_active if data.is_active is not None else (existing.is_active if existing else True)
    if is_active and not rubric and not (existing and existing.rubric):
        raise HTTPException(status_code=400, detail="An active assignment needs at least one rubric criterion")
    if rubric and round(sum(item["max_points"] for item in rubric), 2) != round(max_score, 2):
        raise HTTPException(status_code=400, detail="Rubric max points must add up to the assignment max score")
    return rubric


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    assignment_data: AssignmentCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    rubric = validate_assignment(assignment_data)
    payload = assignment_data.model_dump()
    payload["rubric"] = rubric or []
    assignment = Assignment(teacher_id=teacher.id, **payload)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.get("", response_model=List[AssignmentResponse])
def list_assignments(
    search: str | None = Query(default=None, min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Assignment)
    if current_user.role.value == "teacher":
        query = query.filter(Assignment.teacher_id == current_user.id)
    else:
        query = query.filter(Assignment.is_active.is_(True))
    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Assignment.subject_name).like(term),
                func.lower(Assignment.subject_code).like(term),
                func.lower(Assignment.title).like(term),
            )
        )
    assignments = query.order_by(Assignment.due_date.is_(None), Assignment.due_date, Assignment.created_at.desc()).all()
    responses = [assignment_response(assignment) for assignment in assignments]
    if current_user.role == UserRole.STUDENT and assignments:
        topics = dict(
            db.query(AssignmentAssignee.assignment_id, AssignmentAssignee.topic_text)
            .filter(
                AssignmentAssignee.student_id == current_user.id,
                AssignmentAssignee.assignment_id.in_([item.id for item in assignments]),
            )
            .all()
        )
        for response in responses:
            response["student_topic"] = topics.get(response["id"])
    return responses


@router.get("/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment or (current_user.role.value != "teacher" and not assignment.is_active):
        raise HTTPException(status_code=404, detail="Assignment not found")
    response = assignment_response(assignment)
    if current_user.role == UserRole.STUDENT:
        assignee = (
            db.query(AssignmentAssignee)
            .filter(
                AssignmentAssignee.assignment_id == assignment.id,
                AssignmentAssignee.student_id == current_user.id,
            )
            .first()
        )
        response["student_topic"] = assignee.topic_text if assignee else None
    return response


@router.patch("/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: int,
    assignment_data: AssignmentUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == teacher.id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    payload = assignment_data.model_dump(exclude_unset=True)
    rubric = validate_assignment(assignment_data, assignment)
    if rubric is not None and rubric != (assignment.rubric or []) and assignment.submissions:
        raise HTTPException(status_code=409, detail="Rubric cannot be edited after students have submitted work")
    if rubric is not None:
        payload["rubric"] = rubric
    for key, value in payload.items():
        setattr(assignment, key, value)
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.get("/{assignment_id}/delete-impact")
def get_assignment_delete_impact(
    assignment_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == teacher.id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    students_assigned = db.query(func.count(AssignmentAssignee.id)).filter(
        AssignmentAssignee.assignment_id == assignment.id
    ).scalar() or 0
    submissions = db.query(func.count(Submission.id)).filter(
        Submission.assignment_id == assignment.id
    ).scalar() or 0
    graded_submissions = (
        db.query(func.count(Submission.id))
        .join(Evaluation, Evaluation.submission_id == Submission.id)
        .filter(
            Submission.assignment_id == assignment.id,
            Evaluation.total_score.is_not(None),
        )
        .scalar()
        or 0
    )
    return {
        "students_assigned": students_assigned,
        "submissions": submissions,
        "graded_submissions": graded_submissions,
    }


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == teacher.id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    active_batch = (
        db.query(UploadBatch.id)
        .outerjoin(UploadBatchFile, UploadBatchFile.batch_id == UploadBatch.id)
        .filter(
            or_(
                UploadBatch.status == UploadBatchStatus.PROCESSING,
                UploadBatchFile.status.in_(_ACTIVE_UPLOAD_FILE_STATUSES),
            ),
            or_(
                UploadBatch.target_assignment_id == assignment.id,
                UploadBatchFile.resolved_assignment_id == assignment.id,
            ),
        )
        .first()
    )
    if active_batch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An upload batch for this assignment is still processing. Try again when it finishes.",
        )

    submission_ids = [
        row.id
        for row in db.query(Submission.id).filter(
            Submission.assignment_id == assignment.id
        )
    ]
    evaluation_ids = [
        row.id
        for row in db.query(Evaluation.id)
        .join(Submission, Submission.id == Evaluation.submission_id)
        .filter(Submission.assignment_id == assignment.id)
    ]
    linked_files = (
        db.query(UploadBatchFile)
        .filter(UploadBatchFile.submission_id.in_(submission_ids))
        .all()
        if submission_ids
        else []
    )
    file_keys = {
        key
        for key in (
            *(
                row.file_path
                for row in db.query(Submission.file_path).filter(
                    Submission.id.in_(submission_ids)
                )
            ),
            *(item.storage_key for item in linked_files),
        )
        if key
    }
    affected_batch_ids = {item.batch_id for item in linked_files}

    try:
        db.query(UploadBatch).filter(
            UploadBatch.target_assignment_id == assignment.id
        ).update({UploadBatch.target_assignment_id: None}, synchronize_session=False)
        db.query(UploadBatchFile).filter(
            UploadBatchFile.resolved_assignment_id == assignment.id
        ).update({UploadBatchFile.resolved_assignment_id: None}, synchronize_session=False)
        db.query(AssignmentAssignee).filter(
            AssignmentAssignee.assignment_id == assignment.id
        ).delete(synchronize_session=False)
        if evaluation_ids:
            db.query(Feedback).filter(
                Feedback.evaluation_id.in_(evaluation_ids)
            ).delete(synchronize_session=False)
            db.query(Evaluation).filter(
                Evaluation.id.in_(evaluation_ids)
            ).delete(synchronize_session=False)
        if submission_ids:
            db.query(VerificationAttempt).filter(
                or_(
                    VerificationAttempt.assignment_id == assignment.id,
                    VerificationAttempt.submission_id.in_(submission_ids),
                )
            ).delete(synchronize_session=False)
            db.query(UploadBatchFile).filter(
                UploadBatchFile.submission_id.in_(submission_ids)
            ).delete(synchronize_session=False)
            db.query(Submission).filter(
                Submission.id.in_(submission_ids)
            ).delete(synchronize_session=False)
        for batch_id in affected_batch_ids:
            batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).first()
            if batch:
                batch.file_count = db.query(func.count(UploadBatchFile.id)).filter(
                    UploadBatchFile.batch_id == batch_id
                ).scalar() or 0
        db.delete(assignment)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if file_keys:
        try:
            delete_storage_objects(get_storage(), file_keys)
        except Exception as error:
            logger.error(
                "Assignment file cleanup failed: exception_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="The assignment was deleted, but some stored files could not be removed.",
            ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
