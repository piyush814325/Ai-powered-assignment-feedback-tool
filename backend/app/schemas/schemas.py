from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class SubmissionStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


# Auth Schemas
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.STUDENT
    roll_no: Optional[str] = Field(default=None, max_length=50)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    roll_no: Optional[str] = None
    role: UserRole
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Assignment Schemas
class RubricCriterion(BaseModel):
    key: Optional[str] = None
    label: str
    description: Optional[str] = None
    max_points: float


class AssignmentCreate(BaseModel):
    subject_name: str
    subject_code: str
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    max_score: float = 100
    allowed_file_types: List[str]
    rubric: List[RubricCriterion] = []
    is_active: bool = True


class AssignmentUpdate(BaseModel):
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    max_score: Optional[float] = None
    allowed_file_types: Optional[List[str]] = None
    rubric: Optional[List[RubricCriterion]] = None
    is_active: Optional[bool] = None


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_id: int
    subject_name: str
    subject_code: str
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    max_score: float
    allowed_file_types: List[str]
    rubric: List[RubricCriterion]
    is_active: bool
    student_topic: Optional[str] = None
    submission_count: int = 0
    created_at: datetime
    updated_at: datetime

# Submission Schemas
class SubmissionCreate(BaseModel):
    assignment_id: int


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    student_name: Optional[str] = None
    assignment_id: int
    assignment: Optional[AssignmentResponse] = None
    can_resubmit: bool
    file_path: Optional[str]
    original_filename: Optional[str] = None
    file_type: str
    status: str
    source: Optional[str] = None
    extracted_text: Optional[str] = None
    extracted_code: Optional[str] = None
    text_extraction_warning: Optional[str] = None
    content_hash: Optional[str] = None
    verification_verdict: Optional[str] = None
    verification_confidence: Optional[float] = None
    verification_detected_topic: Optional[str] = None
    verification_expected_topic: Optional[str] = None
    student_topic: Optional[str] = None
    verification_reasons: Optional[List[str]] = None
    verification_missing_requirements: Optional[List[str]] = None
    verification_model: Optional[str] = None
    verification_error_code: Optional[str] = None
    teacher_override: bool = False
    teacher_override_by: Optional[int] = None
    teacher_override_at: Optional[datetime] = None
    teacher_override_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class SubmissionWithEvaluation(SubmissionResponse):
    evaluation: Optional["EvaluationResponse"] = None


class SubmissionEvaluationResponse(BaseModel):
    submission_id: int
    status: SubmissionStatus
    evaluation: Optional["EvaluationResponse"] = None
    verification_verdict: Optional[str] = None
    verification_confidence: Optional[float] = None
    verification_detected_topic: Optional[str] = None
    verification_expected_topic: Optional[str] = None
    verification_reasons: Optional[List[str]] = None
    verification_missing_requirements: Optional[List[str]] = None
    verification_model: Optional[str] = None
    verification_error_code: Optional[str] = None


class VerificationOverrideRequest(BaseModel):
    reason: str


# Evaluation Schemas
class FeedbackItemResponse(BaseModel):
    criterion_id: str
    score: float
    feedback_text: str
    evidence: str
    confidence: float


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    rubric_id: int
    total_score: Optional[float]
    scores: Dict[str, float]
    feedback: Dict[str, str]
    evidence: Dict[str, str]
    ai_confidence: Optional[float]
    is_ai_generated: bool
    is_reviewed: bool
    created_at: datetime
    updated_at: datetime

class EvaluationCreate(BaseModel):
    submission_id: int
    rubric_id: int
    scores: Dict[str, float]
    feedback: Dict[str, str]
    evidence: Dict[str, str]
    ai_confidence: float


class EvaluationUpdate(BaseModel):
    scores: Optional[Dict[str, float]] = None
    feedback: Optional[Dict[str, str]] = None
    is_reviewed: Optional[bool] = None


# Rubric Schemas
class RubricCriterion(BaseModel):
    id: str
    name: str
    description: str
    weight: float
    max_points: int


class RubricCreate(BaseModel):
    name: str
    description: str
    total_points: int = 100
    criteria: List[RubricCriterion]


class RubricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    total_points: int
    criteria: List[RubricCriterion]
    is_active: bool
    created_at: datetime

# Document Parsing Response
class ParsedDocumentResponse(BaseModel):
    text: str
    code: Optional[str] = None
    images: Optional[List[str]] = None  # base64 encoded or file paths
    file_type: str
    parsed_at: datetime
