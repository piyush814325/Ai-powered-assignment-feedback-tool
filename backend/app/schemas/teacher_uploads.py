from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from app.config import ROSTER_CONFIRM_MAX_ROWS, ROSTER_TOPIC_MAX_CHARS


class TeacherStudentResponse(BaseModel):
    id: int
    full_name: str
    email: str
    roll_no: str | None = None


class TeacherStudentsPage(BaseModel):
    items: list[TeacherStudentResponse]
    total: int
    limit: int
    offset: int


class ConfirmUploadRequest(BaseModel):
    student_id: int
    assignment_id: int | None = None
    allow_duplicate: bool = False


class RejectUploadRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AssignmentAssigneesRequest(BaseModel):
    student_ids: list[int]


class AssigneeTopicUpdateRequest(BaseModel):
    topic_text: str = Field(min_length=1, max_length=ROSTER_TOPIC_MAX_CHARS)
    topic_number: int | None = Field(default=None, ge=0, le=32767)


class AssignmentAssigneeStudent(BaseModel):
    id: int
    full_name: str
    topic_text: str | None = None
    topic_number: int | None = None
    source: str | None = None
    roll_no: str | None = None


class AssignmentAssigneesResponse(BaseModel):
    assignment_id: int
    students: list[AssignmentAssigneeStudent]


class AssigneeImportCandidate(BaseModel):
    student_id: int
    full_name: str
    score: int


class AssigneeImportRow(BaseModel):
    row_number: int
    student_name: str
    topic: str
    topic_check: str
    status: str
    candidates: list[AssigneeImportCandidate]
    topic_number: int | None = None


class AssigneeImportPreviewResponse(BaseModel):
    assignment_id: int
    rows: list[AssigneeImportRow]
    warning: str | None = None


class TeacherUploadBatchSummary(BaseModel):
    id: int
    name: str | None = None
    status: str
    file_count: int
    created_at: datetime
    counts: dict[str, int]


class TeacherUploadBatchPage(BaseModel):
    items: list[TeacherUploadBatchSummary]
    total: int
    limit: int
    offset: int


class RosterLayoutResponse(BaseModel):
    sheet_index: int
    sheet_name: str
    header_row: int
    name_column: int
    roll_column: int | None
    topic_column: int | None
    row_count: int
    distinct_name_count: int


class AssigneeImportApprovedRow(BaseModel):
    student_id: int
    topic_text: str | None = None
    topic_number: int | None = None
    row_number: int | None = None
    roll_no: str | None = None


class AssigneeImportConfirmRequest(BaseModel):
    student_ids: list[int]
    rows: list[AssigneeImportApprovedRow] = Field(default_factory=list)


class RosterPreviewReference(BaseModel):
    batch_id: int
    file_id: int
    sheet_name: str | None = None


class RosterPreviewCandidate(BaseModel):
    id: int
    full_name: str
    roll_no: str | None = None
    score: int


class RosterPreviewStudent(BaseModel):
    id: int
    full_name: str
    roll_no: str | None = None


class RosterPreviewRow(BaseModel):
    row_number: int
    roll_no: str | None
    name_in_file: str
    cleaned_name: str
    topic_in_file: str
    cleaned_topic: str
    topic_number: int | None
    student_status: str
    matched_student: RosterPreviewStudent | None = None
    candidates: list[RosterPreviewCandidate]
    warnings: list[str]
    existing_topic: str | None = None
    will_change: bool = False


class RosterPreviewResponse(BaseModel):
    assignment_id: int
    summary: dict[str, int | str]
    detected_layout: str
    chosen_sheet: str
    sheet_names: list[str]
    header_row: int
    rows: list[RosterPreviewRow]
    warnings: list[str]


class RosterConfirmRow(BaseModel):
    row_number: int
    student_id: int
    topic_text: str = Field(min_length=1, max_length=ROSTER_TOPIC_MAX_CHARS)
    topic_number: int | None = Field(default=None, ge=0, le=32767)
    roll_no: str | None = Field(default=None, max_length=50)


class RosterConfirmRequest(BaseModel):
    rows: list[RosterConfirmRow] = Field(max_length=ROSTER_CONFIRM_MAX_ROWS)
    save_roll_numbers: bool = False
    batch_id: int | None = None
    file_id: int | None = None
    sheet_name: str | None = None


class RosterConfirmResponse(BaseModel):
    added: int
    updated: int
    skipped: int
    already_assigned: int
    roll_numbers_saved: int


class UploadBatchFileResponse(BaseModel):
    id: int
    filename: str
    status: str
    detected_name: str | None
    detected_name_source: str | None
    name_candidates: list[dict[str, Any]]
    match_status: str | None
    resolved_student_id: int | None
    resolved_student_name: str | None
    resolved_assignment_id: int | None
    resolved_assignment_name: str | None
    grading_status: str | None
    error: str | None
    warning: str | None = None
    roster_detected: bool = False
    roster_message: str | None = None
    roster_layout: RosterLayoutResponse | None = None
    submission_id: int | None


class UploadBatchResponse(BaseModel):
    id: int
    name: str | None = None
    status: str
    file_count: int
    files: list[UploadBatchFileResponse]
    created_at: datetime


class UploadBatchCreatedResponse(BaseModel):
    id: int
    name: str | None = None
    status: str
    file_count: int


class UploadBatchRenameRequest(BaseModel):
    name: str | None


class UploadBatchRenameResponse(BaseModel):
    id: int
    name: str | None
