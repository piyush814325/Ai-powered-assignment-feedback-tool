from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.config import ROSTER_TOPIC_MAX_CHARS
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config import MAX_UPLOAD_BYTES
from app.database import get_db
from app.models import (
    Assignment,
    AssignmentAssignee,
    UploadBatch,
    UploadBatchFile,
    UploadBatchFileStatus,
    User,
    UserRole,
)
from app.routers.assignments import _owned_assignment_or_404
from app.routers.auth import require_teacher
from app.schemas.teacher_uploads import (
    RosterConfirmRequest,
    RosterConfirmResponse,
    RosterPreviewCandidate,
    RosterPreviewResponse,
    RosterPreviewRow,
    RosterPreviewStudent,
    RosterPreviewReference,
)
from app.services.excel_parser import (
    ExcelLimitError,
    parse_excel,
    validate_excel_upload,
)
from app.services.file_storage import get_storage
from app.services.roster_cells import clean_roster_cell, normalize_roll_no
from app.services.roster_detection import detect_roster_layouts
from app.services.student_matching import (
    StudentCandidate,
    match_roster_student,
)

router = APIRouter(prefix="/assignments", tags=["roster import"])
_HEADER_KEY = re.compile(r"[^a-z0-9]+")


def _column_key(value: str) -> str:
    return _HEADER_KEY.sub("", clean_roster_cell(value).text.casefold())


def _roster_error(error: ValueError) -> HTTPException:
    message = str(error)
    if "byte limit" in message or "uncompressed-size limit" in message:
        code = status.HTTP_413_CONTENT_TOO_LARGE
    elif "supported" in message or "MIME type" in message:
        code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=code, detail=message)


async def _load_preview_source(
    request: Request,
    assignment: Assignment,
    teacher: User,
    db: Session,
) -> tuple[bytes, str, str | None, int | None, int | None]:
    content_type = request.headers.get("content-type", "").casefold()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if isinstance(upload, StarletteUploadFile):
            filename = Path(upload.filename or "").name
            content = await upload.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Uploaded file exceeds the {MAX_UPLOAD_BYTES}-byte limit",
                )
            try:
                validate_excel_upload(content, filename, upload.content_type)
                return content, filename, form.get("sheet_name"), None, None
            except ValueError as error:
                raise _roster_error(error) from error
        try:
            reference = RosterPreviewReference(
                batch_id=int(str(form.get("batch_id", ""))),
                file_id=int(str(form.get("file_id", ""))),
                sheet_name=str(form.get("sheet_name") or "") or None,
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="Provide an .xlsx/.csv file or both batch_id and file_id",
            ) from None
    elif "application/json" in content_type:
        try:
            body = await request.json()
        except json.JSONDecodeError as error:
            raise HTTPException(
                status_code=422,
                detail="Request body must be valid JSON",
            ) from error
        try:
            reference = RosterPreviewReference.model_validate(body)
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail="Provide valid batch_id and file_id values",
            ) from error
    else:
        raise HTTPException(
            status_code=415,
            detail="Use multipart .xlsx/.csv data or a JSON batch/file reference",
        )

    owned = (
        db.query(UploadBatch, UploadBatchFile)
        .join(UploadBatchFile, UploadBatchFile.batch_id == UploadBatch.id)
        .filter(
            UploadBatch.id == reference.batch_id,
            UploadBatchFile.id == reference.file_id,
        )
    )
    if teacher.role != UserRole.ADMIN:
        owned = owned.filter(UploadBatch.teacher_id == teacher.id)
    result = owned.first()
    if result is None:
        raise HTTPException(status_code=404, detail="Roster upload file not found")
    batch, item = result
    if item.status not in {
        UploadBatchFileStatus.ROSTER_DETECTED,
        UploadBatchFileStatus.IMPORTED,
    }:
        raise HTTPException(status_code=422, detail="The selected upload is not a detected roster")
    if batch.target_assignment_id not in {None, assignment.id}:
        raise HTTPException(status_code=422, detail="The roster upload targets a different assignment")
    content = await run_in_threadpool(get_storage().read, item.storage_key)
    try:
        validate_excel_upload(
            content,
            item.original_filename,
            "text/csv" if item.original_filename.lower().endswith(".csv") else None,
        )
    except ValueError as error:
        raise _roster_error(error) from error
    return (
        content,
        item.original_filename,
        reference.sheet_name,
        batch.id,
        item.id,
    )


def _student_candidates(db: Session) -> list[StudentCandidate]:
    students = (
        db.query(User)
        .filter(User.role == UserRole.STUDENT)
        .order_by(User.full_name, User.id)
        .all()
    )
    return [
        StudentCandidate(
            id=student.id,
            full_name=student.full_name,
            roll_no=normalize_roll_no(student.roll_no),
        )
        for student in students
    ]


def _roll_match(
    roll_no: str | None, students: list[StudentCandidate]
) -> tuple[str | None, int | None, list[dict[str, Any]]]:
    normalized_roll = normalize_roll_no(roll_no)
    if not normalized_roll:
        return None, None, []
    exact = [student for student in students if student.roll_no == normalized_roll]
    candidates = [
        {
            "id": student.id,
            "full_name": student.full_name,
            "roll_no": student.roll_no,
            "score": 100,
        }
        for student in exact[:3]
    ]
    if len(exact) == 1:
        return "matched", exact[0].id, candidates
    if len(exact) > 1:
        return "ambiguous", None, candidates
    return None, None, []


def _candidate_model(candidate: dict[str, Any]) -> RosterPreviewCandidate:
    return RosterPreviewCandidate(
        id=int(candidate.get("id", candidate.get("student_id"))),
        full_name=str(candidate["full_name"]),
        roll_no=candidate.get("roll_no"),
        score=int(candidate["score"]),
    )


@router.post("/{assignment_id}/roster/preview", response_model=RosterPreviewResponse)
async def preview_roster(
    assignment_id: int,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    content, filename, requested_sheet, _batch_id, _file_id = await _load_preview_source(
        request, assignment, teacher, db
    )
    try:
        parsed = await run_in_threadpool(parse_excel, content, filename)
    except ValueError as error:
        raise _roster_error(error) from error

    layouts = detect_roster_layouts(parsed, filename)
    if not layouts:
        raise HTTPException(
            status_code=422,
            detail="No roster header was found. Include a student name column and a roll-number or topic column.",
        )
    if requested_sheet:
        selected = next(
            (layout for layout in layouts if layout.sheet_name == requested_sheet), None
        )
        if selected is None:
            raise HTTPException(
                status_code=422,
                detail="The selected sheet does not contain a recognized roster header",
            )
    else:
        selected = layouts[0]

    sheet = parsed.sheets[selected.sheet_index]
    header_index = next(
        (
            index
            for index, row_number in enumerate(sheet.source_row_numbers)
            if row_number == selected.header_row
        ),
        None,
    )
    if header_index is None:
        raise HTTPException(status_code=422, detail="The detected roster header is unavailable")
    header = sheet.rows[header_index]
    students = _student_candidates(db)
    existing_topics = {
        row.student_id: row.topic_text
        for row in db.query(AssignmentAssignee)
        .filter(AssignmentAssignee.assignment_id == assignment.id)
        .all()
    }
    row_models: list[RosterPreviewRow] = []
    top_warnings: list[str] = []
    name_counts: Counter[str] = Counter()
    student_topics: dict[int, set[str]] = defaultdict(set)
    topic_values: set[str] = set()
    name_column = selected.name_column
    roll_column = selected.roll_column
    topic_column = selected.topic_column
    for index in range(header_index + 1, len(sheet.rows)):
        values = sheet.rows[index]
        row_number = (
            sheet.source_row_numbers[index]
            if index < len(sheet.source_row_numbers)
            else selected.header_row + index - header_index
        )
        raw_name = values[name_column] if name_column < len(values) else ""
        raw_roll = values[roll_column] if roll_column is not None and roll_column < len(values) else ""
        raw_topic = values[topic_column] if topic_column is not None and topic_column < len(values) else ""
        cleaned_name = clean_roster_cell(raw_name).text
        cleaned_roll = normalize_roll_no(raw_roll)
        cleaned_topic_result = clean_roster_cell(raw_topic, is_topic=True)
        cleaned_topic = cleaned_topic_result.text
        row_warnings: list[str] = []
        if cleaned_name:
            name_counts[cleaned_name.casefold()] += 1
        elif cleaned_roll and cleaned_topic:
            row_warnings.append("Topic and roll number are present, but the student name is missing.")
        if cleaned_topic:
            topic_values.add(cleaned_topic.casefold())
        else:
            row_warnings.append("This student has no topic.")

        status_value, student_id, raw_candidates = _roll_match(cleaned_roll, students)
        if status_value is None:
            name_match = match_roster_student(cleaned_name, students)
            status_value = {
                "auto_matched": "matched",
                "needs_confirmation": "ambiguous",
                "unmatched": "unmatched",
            }[name_match.match_status]
            student_id = name_match.resolved_student_id
            raw_candidates = [
                {
                    "id": candidate["student_id"],
                    "full_name": candidate["full_name"],
                    "roll_no": next(
                        (
                            student.roll_no
                            for student in students
                            if student.id == candidate["student_id"]
                        ),
                        None,
                    ),
                    "score": candidate["score"],
                }
                for candidate in name_match.candidates
            ]
        if not cleaned_name:
            status_value = "unmatched"
            student_id = None
        if not cleaned_topic:
            status_value = "no_topic"
        elif cleaned_topic.casefold() == clean_roster_cell(assignment.title).text.casefold():
            row_warnings.append("Topic is identical to the assignment title.")
        if status_value == "unmatched" and cleaned_topic:
            row_warnings.append("No student account matched this row.")
        if status_value == "ambiguous":
            row_warnings.append("Choose the correct student account.")
        if student_id is not None and cleaned_topic:
            student_topics[student_id].add(cleaned_topic.casefold())
        matched_user = next(
            (student for student in students if student.id == student_id), None
        )
        existing_topic = existing_topics.get(student_id) if student_id is not None else None
        will_change = bool(
            student_id is not None
            and student_id in existing_topics
            and existing_topic != cleaned_topic
        )
        matched_student = (
            RosterPreviewStudent(
                id=matched_user.id,
                full_name=matched_user.full_name,
                roll_no=matched_user.roll_no,
            )
            if matched_user
            else None
        )
        row_models.append(
            RosterPreviewRow(
                row_number=row_number,
                roll_no=cleaned_roll,
                name_in_file=raw_name,
                cleaned_name=cleaned_name,
                topic_in_file=raw_topic,
                cleaned_topic=cleaned_topic,
                topic_number=cleaned_topic_result.topic_number,
                student_status=status_value,
                matched_student=matched_student,
                candidates=[_candidate_model(candidate) for candidate in raw_candidates[:3]],
                warnings=row_warnings,
                existing_topic=existing_topic,
                will_change=will_change,
            )
        )

    duplicate_name_keys = {
        key for key, count in name_counts.items() if count > 1
    }
    if duplicate_name_keys:
        top_warnings.append("Duplicate student names appear in this roster.")
        for row in row_models:
            if row.cleaned_name.casefold() in duplicate_name_keys:
                row.warnings.append("This name occurs more than once in the file.")
    if any(not row.cleaned_topic and row.cleaned_name for row in row_models):
        top_warnings.append("Some students do not have a topic.")
    if any(row.cleaned_topic and not row.cleaned_name for row in row_models):
        top_warnings.append("Some topics have no student name.")
    if any(len(topics) > 1 for topics in student_topics.values()):
        top_warnings.append("A matched student is listed with more than one topic.")
    if parsed.truncated:
        top_warnings.append(
            f"The spreadsheet was truncated after {parsed.retained_row_count} retained rows/cells."
        )
    if any(
        row.cleaned_topic.casefold() == clean_roster_cell(assignment.title).text.casefold()
        for row in row_models
        if row.cleaned_topic
    ):
        top_warnings.append("At least one topic is identical to the assignment title.")

    statuses = Counter(row.student_status for row in row_models)
    will_update = sum(row.will_change for row in row_models)
    summary: dict[str, int | str] = {
        "students_found": sum(bool(row.cleaned_name) for row in row_models),
        "matched": statuses["matched"],
        "need_confirmation": statuses["ambiguous"],
        "unmatched": statuses["unmatched"],
        "no_topic": statuses["no_topic"],
        "topics_found": sum(bool(row.cleaned_topic) for row in row_models),
        "total_rows": len(row_models),
        "will_update": will_update,
    }
    layout_text = (
        f"{summary['students_found']} students, "
        f"{len(topic_values)} different topics"
    )
    return RosterPreviewResponse(
        assignment_id=assignment.id,
        summary=summary,
        detected_layout=layout_text,
        chosen_sheet=selected.sheet_name,
        sheet_names=[sheet.name for sheet in parsed.sheets],
        header_row=selected.header_row,
        rows=row_models,
        warnings=top_warnings,
    )


@router.post(
    "/{assignment_id}/roster/confirm", response_model=RosterConfirmResponse
)
def confirm_roster(
    assignment_id: int,
    request: RosterConfirmRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = _owned_assignment_or_404(db, assignment_id, teacher)
    if request.batch_id is not None or request.file_id is not None:
        if request.batch_id is None or request.file_id is None:
            raise HTTPException(status_code=422, detail="Both batch_id and file_id are required")
        owned = (
            db.query(UploadBatch, UploadBatchFile)
            .join(UploadBatchFile, UploadBatchFile.batch_id == UploadBatch.id)
            .filter(
                UploadBatch.id == request.batch_id,
                UploadBatchFile.id == request.file_id,
            )
        )
        if teacher.role != UserRole.ADMIN:
            owned = owned.filter(UploadBatch.teacher_id == teacher.id)
        result = owned.first()
        if result is None:
            raise HTTPException(status_code=404, detail="Roster upload file not found")
        batch, batch_file = result
        if batch.target_assignment_id not in {None, assignment.id}:
            raise HTTPException(status_code=422, detail="The roster upload targets a different assignment")
        if batch_file.status not in {
            UploadBatchFileStatus.ROSTER_DETECTED,
            UploadBatchFileStatus.IMPORTED,
        }:
            raise HTTPException(status_code=409, detail="The upload is no longer available for import")
    else:
        batch_file = None

    student_ids = [row.student_id for row in request.rows]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(status_code=422, detail="A student may appear only once in a confirmation")
    students_by_id = {
        student.id: student
        for student in db.query(User)
        .filter(User.id.in_(student_ids), User.role == UserRole.STUDENT)
        .all()
    } if student_ids else {}
    if len(students_by_id) != len(student_ids):
        raise HTTPException(status_code=422, detail="Every student_id must belong to a student account")
    for row in request.rows:
        normalized_topic = clean_roster_cell(row.topic_text, is_topic=True).text
        if not normalized_topic:
            raise HTTPException(status_code=422, detail="Every confirmed row needs a topic")
        if len(normalized_topic) > ROSTER_TOPIC_MAX_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"Topic text must be {ROSTER_TOPIC_MAX_CHARS} characters or fewer",
            )

    added = updated = skipped = already_assigned = roll_numbers_saved = 0
    try:
        for row in request.rows:
            student = students_by_id[row.student_id]
            normalized_topic = clean_roster_cell(row.topic_text, is_topic=True)
            topic_text = normalized_topic.text
            topic_number = row.topic_number if row.topic_number is not None else normalized_topic.topic_number
            existing = (
                db.query(AssignmentAssignee)
                .filter(
                    AssignmentAssignee.assignment_id == assignment.id,
                    AssignmentAssignee.student_id == student.id,
                )
                .with_for_update()
                .first()
            )
            row_ref = f"{request.sheet_name or 'roster'}#{row.row_number}"
            if existing is None:
                db.add(
                    AssignmentAssignee(
                        assignment_id=assignment.id,
                        student_id=student.id,
                        topic_text=topic_text,
                        topic_number=topic_number,
                        source="roster_import",
                        roster_row_ref=row_ref,
                    )
                )
                added += 1
            elif existing.topic_text != topic_text or existing.topic_number != topic_number:
                existing.topic_text = topic_text
                existing.topic_number = topic_number
                existing.source = "roster_import"
                existing.roster_row_ref = row_ref
                updated += 1
            else:
                existing.source = "roster_import"
                existing.roster_row_ref = row_ref
                already_assigned += 1

            if request.save_roll_numbers and not normalize_roll_no(student.roll_no):
                normalized_roll = normalize_roll_no(row.roll_no)
                if normalized_roll:
                    student.roll_no = normalized_roll
                    roll_numbers_saved += 1
        if batch_file is not None and (added or updated):
            batch_file.status = UploadBatchFileStatus.IMPORTED
            batch_file.error = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "already_assigned": already_assigned,
        "roll_numbers_saved": roll_numbers_saved,
    }
