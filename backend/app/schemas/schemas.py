from pydantic import BaseModel, EmailStr
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


# Auth Schemas
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.STUDENT


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Submission Schemas
class SubmissionCreate(BaseModel):
    assignment_id: str


class SubmissionResponse(BaseModel):
    id: int
    student_id: int
    assignment_id: str
    file_path: str
    file_type: str
    status: SubmissionStatus
    extracted_text: Optional[str] = None
    extracted_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubmissionWithEvaluation(SubmissionResponse):
    evaluation: Optional["EvaluationResponse"] = None


# Evaluation Schemas
class FeedbackItemResponse(BaseModel):
    criterion_id: str
    score: float
    feedback_text: str
    evidence: str
    confidence: float


class EvaluationResponse(BaseModel):
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

    class Config:
        from_attributes = True


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
    id: int
    name: str
    description: str
    total_points: int
    criteria: List[RubricCriterion]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Document Parsing Response
class ParsedDocumentResponse(BaseModel):
    text: str
    code: Optional[str] = None
    images: Optional[List[str]] = None  # base64 encoded or file paths
    file_type: str
    parsed_at: datetime
