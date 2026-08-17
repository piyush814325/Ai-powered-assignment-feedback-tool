from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Enum, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
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

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    full_name = Column(String(255))
    hashed_password = Column(String(255))
    role = Column(Enum(UserRole), default=UserRole.STUDENT)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    submissions = relationship("Submission", back_populates="student")
    evaluations = relationship("Evaluation", back_populates="reviewed_by")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    assignment_id = Column(String(255))
    file_path = Column(String(500))
    file_type = Column(String(50))  # pdf, docx, code, image
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.UPLOADED)
    extracted_text = Column(Text, nullable=True)
    extracted_code = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    student = relationship("User", back_populates="submissions")
    evaluation = relationship("Evaluation", uselist=False, back_populates="submission")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), unique=True)
    rubric_id = Column(Integer, ForeignKey("rubrics.id"))
    total_score = Column(Float, nullable=True)
    scores = Column(JSON)  # {criterion_id: score, ...}
    feedback = Column(JSON)  # {criterion_id: feedback_text, ...}
    evidence = Column(JSON)  # {criterion_id: evidence_text, ...}
    ai_confidence = Column(Float, nullable=True)  # 0.0 - 1.0
    is_ai_generated = Column(Boolean, default=True)
    is_reviewed = Column(Boolean, default=False)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    submission = relationship("Submission", back_populates="evaluation")
    rubric = relationship("Rubric", back_populates="evaluations")
    reviewed_by = relationship("User", back_populates="evaluations")


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    description = Column(Text)
    total_points = Column(Integer, default=100)
    criteria = Column(JSON)  # [{id, name, weight, max_points, description}, ...]
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    evaluations = relationship("Evaluation", back_populates="rubric")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id"))
    criterion_id = Column(String(100))
    score = Column(Float)
    feedback_text = Column(Text)
    evidence = Column(Text)
    confidence = Column(Float)  # AI confidence (0.0-1.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
