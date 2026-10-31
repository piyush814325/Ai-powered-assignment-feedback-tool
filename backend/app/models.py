from datetime import datetime, timezone
import enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    SmallInteger,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import event
from app.database import Base
from app.services.roster_cells import normalize_roll_no


JSON_LIST_TYPE = MutableList.as_mutable(JSON().with_variant(JSONB(), "postgresql"))
JSON_DICT_TYPE = MutableDict.as_mutable(JSON().with_variant(JSONB(), "postgresql"))
SUBMISSION_STUDENT_ASSIGNMENT_INDEX = "uq_submissions_student_assignment"


class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class SubmissionStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


class SubmissionSource(str, enum.Enum):
    STUDENT_UPLOAD = "student_upload"
    TEACHER_UPLOAD = "teacher_upload"


class UploadBatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadBatchFileStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    NAME_DETECTED = "name_detected"
    MATCHED = "matched"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    GRADING = "grading"
    GRADED = "graded"
    NEEDS_ATTENTION = "needs_attention"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    REJECTED = "rejected"
    ROSTER_DETECTED = "roster_detected"
    IMPORTED = "imported"


class StudentMatchStatus(str, enum.Enum):
    AUTO_MATCHED = "auto_matched"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNMATCHED = "unmatched"
    CONFIRMED_BY_TEACHER = "confirmed_by_teacher"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)
    full_name: Mapped[str] = mapped_column(String(255))
    roll_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=7), default=UserRole.STUDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    submissions: Mapped[list["Submission"]] = relationship(
        "Submission",
        back_populates="student",
        foreign_keys="Submission.student_id",
    )
    assignments: Mapped[list["Assignment"]] = relationship("Assignment", back_populates="teacher")
    evaluations: Mapped[list["Evaluation"]] = relationship("Evaluation", back_populates="reviewed_by")


@event.listens_for(User, "before_insert")
@event.listens_for(User, "before_update")
def _normalize_user_roll_no(_mapper, _connection, user: User) -> None:
    user.roll_no = normalize_roll_no(user.roll_no)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=100, nullable=False)
    allowed_file_types: Mapped[list] = mapped_column(JSON_LIST_TYPE, nullable=False, default=list)
    rubric: Mapped[list] = mapped_column(JSON_LIST_TYPE, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    teacher: Mapped["User"] = relationship("User", back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="assignment")


class AssignmentAssignee(Base):
    __tablename__ = "assignment_assignees"
    __table_args__ = (
        Index(
            "uq_assignment_assignees_assignment_student",
            "assignment_id",
            "student_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assignment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assignments.id"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    topic_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    topic_number: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    roster_row_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    target_assignment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("assignments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[UploadBatchStatus] = mapped_column(
        Enum(UploadBatchStatus, native_enum=False, length=20),
        default=UploadBatchStatus.PENDING,
        nullable=False,
    )


class UploadBatchFile(Base):
    __tablename__ = "upload_batch_files"
    __table_args__ = (
        Index("ix_upload_batch_files_batch_status", "batch_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("upload_batches.id"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[UploadBatchFileStatus] = mapped_column(
        Enum(UploadBatchFileStatus, native_enum=False, length=32),
        default=UploadBatchFileStatus.UPLOADED,
        nullable=False,
    )
    detected_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parsed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_visual_content: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    name_detection: Mapped[Optional[dict]] = mapped_column(JSON_DICT_TYPE, nullable=True)
    candidates: Mapped[Optional[list]] = mapped_column(JSON_LIST_TYPE, nullable=True)
    match_status: Mapped[Optional[StudentMatchStatus]] = mapped_column(
        Enum(StudentMatchStatus, native_enum=False, length=32), nullable=True
    )
    resolved_student_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    resolved_assignment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("assignments.id"), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_step: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    submission_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("submissions.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index(
            SUBMISSION_STUDENT_ASSIGNMENT_INDEX,
            "student_id",
            "assignment_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id"), nullable=False, index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # pdf, docx, code
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=15),
        default=SubmissionStatus.UPLOADED,
    )
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_extraction_warning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    verification_verdict: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    verification_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_detected_topic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_expected_topic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_reasons: Mapped[Optional[list]] = mapped_column(JSON_LIST_TYPE, nullable=True)
    verification_missing_requirements: Mapped[Optional[list]] = mapped_column(JSON_LIST_TYPE, nullable=True)
    verification_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    verification_error_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    teacher_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    teacher_override_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    teacher_override_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    teacher_override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by_teacher_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    source: Mapped[Optional[SubmissionSource]] = mapped_column(
        Enum(SubmissionSource, native_enum=False, length=20), nullable=True
    )
    upload_batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("upload_batches.id"), nullable=True
    )
    name_detection: Mapped[Optional[dict]] = mapped_column(JSON_DICT_TYPE, nullable=True)
    match_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_status: Mapped[Optional[StudentMatchStatus]] = mapped_column(
        Enum(StudentMatchStatus, native_enum=False, length=32), nullable=True
    )
    teacher_confirmed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    teacher_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="submissions",
        foreign_keys=[student_id],
    )
    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="submissions")
    evaluation: Mapped[Optional["Evaluation"]] = relationship("Evaluation", uselist=False, back_populates="submission")
    verification_attempts: Mapped[list["VerificationAttempt"]] = relationship(
        "VerificationAttempt", back_populates="submission", cascade="all, delete-orphan"
    )

    @property
    def student_name(self) -> Optional[str]:
        return self.student.full_name if self.student else None

    @property
    def can_resubmit(self) -> bool:
        assignment = self.assignment
        if not assignment or not assignment.is_active:
            return False
        if assignment.due_date is None:
            return True
        due_date = assignment.due_date
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= due_date


class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"
    __table_args__ = (
        Index("ix_verification_attempts_student_assignment_created", "student_id", "assignment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(Integer, ForeignKey("submissions.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    submission: Mapped["Submission"] = relationship("Submission", back_populates="verification_attempts")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(Integer, ForeignKey("submissions.id"), unique=True)
    rubric_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rubrics.id"), nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scores: Mapped[Optional[dict]] = mapped_column(JSON_DICT_TYPE, nullable=True)   # {criterion_id: score, ...}
    feedback: Mapped[Optional[dict]] = mapped_column(JSON_DICT_TYPE, nullable=True) # {criterion_id: feedback_text, ...}
    evidence: Mapped[Optional[dict]] = mapped_column(JSON_DICT_TYPE, nullable=True) # {criterion_id: evidence_text, ...}
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 - 1.0
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Two-stage evaluation fields (Stage 1: Classification)
    content_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # code, document_with_images, text_document, mixed
    domain: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)        # computer_science, engineering, finance, medical, general
    complexity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)    # simple, moderate, complex
    classification_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Model ID used for classification

    # Two-stage evaluation fields (Stage 2: Grading)
    grading_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Model ID used for grading
    issues: Mapped[Optional[list]] = mapped_column(JSON_LIST_TYPE, nullable=True) # [{criterion_key?, description, severity}, ...]
    has_ungraded_visual_content: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    submission: Mapped["Submission"] = relationship("Submission", back_populates="evaluation")
    rubric: Mapped[Optional["Rubric"]] = relationship("Rubric", back_populates="evaluations")
    reviewed_by: Mapped[Optional["User"]] = relationship("User", back_populates="evaluations")


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_points: Mapped[int] = mapped_column(Integer, default=100)
    criteria: Mapped[Optional[list]] = mapped_column(JSON_LIST_TYPE, nullable=True)  # [{id, name, weight, max_points, description}, ...]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    evaluations: Mapped[list["Evaluation"]] = relationship("Evaluation", back_populates="rubric")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    evaluation_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("evaluations.id"), nullable=True)
    criterion_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # AI confidence (0.0-1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
