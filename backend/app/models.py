from sqlalchemy import Integer, String, Text, Float, DateTime, Enum, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, timezone
from typing import Optional
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class SubmissionStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.STUDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="student")
    assignments: Mapped[list["Assignment"]] = relationship("Assignment", back_populates="teacher")
    evaluations: Mapped[list["Evaluation"]] = relationship("Evaluation", back_populates="reviewed_by")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=100, nullable=False)
    allowed_file_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rubric: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    teacher: Mapped["User"] = relationship("User", back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="assignment")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id"), nullable=False, index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # pdf, docx, code, image
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus), default=SubmissionStatus.UPLOADED)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student: Mapped[Optional["User"]] = relationship("User", back_populates="submissions")
    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="submissions")
    evaluation: Mapped[Optional["Evaluation"]] = relationship("Evaluation", uselist=False, back_populates="submission")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(Integer, ForeignKey("submissions.id"), unique=True)
    rubric_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rubrics.id"), nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)   # {criterion_id: score, ...}
    feedback: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # {criterion_id: feedback_text, ...}
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # {criterion_id: evidence_text, ...}
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 - 1.0
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Two-stage evaluation fields (Stage 1: Classification)
    content_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # code, document_with_images, text_document, mixed
    domain: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)        # computer_science, engineering, finance, medical, general
    complexity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)    # simple, moderate, complex
    classification_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Model ID used for classification

    # Two-stage evaluation fields (Stage 2: Grading)
    grading_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Model ID used for grading
    issues: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)               # [{criterion_key?, description, severity}, ...]
    has_ungraded_visual_content: Mapped[bool] = mapped_column(Boolean, default=False) # Images found but not graded by AI

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
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
    criteria: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [{id, name, weight, max_points, description}, ...]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
