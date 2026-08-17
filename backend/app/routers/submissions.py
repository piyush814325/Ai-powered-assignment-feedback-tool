from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Submission, Evaluation, User, SubmissionStatus, Rubric
from app.schemas.schemas import SubmissionResponse, SubmissionWithEvaluation, EvaluationResponse
from app.services.document_parser import DocumentParser
from app.services.llm_service import LLMEvaluationService
from app.services.rubric_engine import RubricEngine
import os
from pathlib import Path
from datetime import datetime

router = APIRouter(prefix="/submissions", tags=["submissions"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


from fastapi.security import OAuth2PasswordBearer
from app.services.auth_service import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


@router.post("/upload", response_model=SubmissionResponse)
async def upload_submission(
    file: UploadFile = File(...),
    assignment_id: str = None,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Upload an assignment file."""
    
    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    allowed_extensions = {".pdf", ".docx", ".txt", ".py", ".java", ".cpp", ".js", ".ts", ".png", ".jpg", ".jpeg"}
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file_ext} not allowed"
        )
    
    # Extract student_id from token if present
    student_id = 1
    if token:
        payload = decode_token(token)
        if payload and "user_id" in payload:
            student_id = payload["user_id"]
    
    # Save file
    file_path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{file.filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Determine file type
    file_type = "code" if file_ext in {".py", ".java", ".cpp", ".js", ".ts"} else file_ext.strip(".")
    
    # Create submission record
    submission = Submission(
        student_id=student_id,
        assignment_id=assignment_id or "default",
        file_path=file_path,
        file_type=file_type,
        status=SubmissionStatus.UPLOADED
    )
    
    db.add(submission)
    db.commit()
    db.refresh(submission)
    
    return submission


@router.post("/evaluate/{submission_id}", response_model=EvaluationResponse)
async def evaluate_submission(
    submission_id: int,
    rubric_id: int = 1,
    use_mock_llm: bool = True,
    db: Session = Depends(get_db)
):
    """Trigger evaluation of a submission."""
    
    # Get submission
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Update status
    submission.status = SubmissionStatus.PROCESSING
    db.commit()
    
    try:
        # Parse document
        text, code, images, file_type = DocumentParser.parse_document(submission.file_path)
        submission.extracted_text = text
        submission.extracted_code = code
        submission.file_type = file_type
        db.commit()
        
        # Mock rubric criteria (TODO: Load from database)
        rubric_criteria = [
            {"id": "clarity", "name": "Clarity", "description": "Clear and understandable", "weight": 1.0, "max_points": 15},
            {"id": "completeness", "name": "Completeness", "description": "All requirements met", "weight": 1.0, "max_points": 20},
            {"id": "code_quality", "name": "Code Quality", "description": "Well-written code", "weight": 1.0, "max_points": 15},
            {"id": "correctness", "name": "Correctness", "description": "Correct solution", "weight": 1.5, "max_points": 25},
            {"id": "documentation", "name": "Documentation", "description": "Well-documented", "weight": 0.75, "max_points": 10},
            {"id": "organization", "name": "Organization", "description": "Well-organized", "weight": 0.75, "max_points": 10},
            {"id": "originality", "name": "Originality", "description": "Original work", "weight": 0.5, "max_points": 5},
        ]
        
        # Ensure valid rubric_id
        rubric_row = db.query(Rubric).filter(Rubric.id == rubric_id).first()
        if not rubric_row:
            rubric_row = db.query(Rubric).first()
            if rubric_row:
                rubric_id = rubric_row.id

        # Evaluate with LLM
        scores, feedback, evidence, confidence = await LLMEvaluationService.evaluate_with_llm(
            text, code, rubric_criteria, use_mock=use_mock_llm
        )
        
        # Calculate total score using rubric engine
        total_score, _ = RubricEngine.evaluate(text, code, rubric_criteria, scores, feedback, evidence)
        
        # Create evaluation record
        evaluation = Evaluation(
            submission_id=submission_id,
            rubric_id=rubric_id,
            total_score=total_score,
            scores=scores,
            feedback=feedback,
            evidence=evidence,
            ai_confidence=confidence,
            is_ai_generated=True,
            is_reviewed=False
        )
        
        db.add(evaluation)
        submission.status = SubmissionStatus.READY
        db.commit()
        db.refresh(evaluation)
        
        return evaluation
    
    except Exception as e:
        db.rollback()
        try:
            sub = db.query(Submission).filter(Submission.id == submission_id).first()
            if sub:
                sub.status = SubmissionStatus.FAILED
                db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{submission_id}", response_model=SubmissionWithEvaluation)
def get_submission(submission_id: int, db: Session = Depends(get_db)):
    """Get submission with evaluation."""
    
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    return submission


@router.get("/", response_model=list[SubmissionWithEvaluation])
def list_submissions(student_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List submissions with evaluations."""
    
    query = db.query(Submission)
    if student_id:
        query = query.filter(Submission.student_id == student_id)
    
    return query.order_by(Submission.created_at.desc()).all()


@router.patch("/evaluate/{evaluation_id}/review", response_model=EvaluationResponse)
def review_evaluation(
    evaluation_id: int,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Mark an evaluation as reviewed by teacher."""
    
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    reviewer_id = None
    if token:
        payload = decode_token(token)
        if payload and "user_id" in payload:
            reviewer_id = payload["user_id"]
    
    evaluation.is_reviewed = True
    if reviewer_id:
        evaluation.reviewed_by_id = reviewer_id
        
    db.commit()
    db.refresh(evaluation)
    return evaluation


from app.schemas.schemas import EvaluationUpdate

@router.put("/evaluations/{evaluation_id}", response_model=EvaluationResponse)
def update_evaluation(
    evaluation_id: int,
    eval_update: EvaluationUpdate,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update evaluation scores & feedback (Teacher override)."""
    
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    if eval_update.scores is not None:
        updated_scores = dict(evaluation.scores or {})
        updated_scores.update(eval_update.scores)
        evaluation.scores = updated_scores
        
        # Recalculate total score
        # Criterion weights: clarity (15), completeness (20), code_quality (15), correctness (25), documentation (10), organization (10), originality (5)
        rubric_criteria = [
            {"id": "clarity", "max_points": 15, "weight": 1.0},
            {"id": "completeness", "max_points": 20, "weight": 1.0},
            {"id": "code_quality", "max_points": 15, "weight": 1.0},
            {"id": "correctness", "max_points": 25, "weight": 1.5},
            {"id": "documentation", "max_points": 10, "weight": 0.75},
            {"id": "organization", "max_points": 10, "weight": 0.75},
            {"id": "originality", "max_points": 5, "weight": 0.5},
        ]
        total_score, _ = RubricEngine.evaluate("", None, rubric_criteria, updated_scores, {}, {})
        evaluation.total_score = total_score
        
    if eval_update.feedback is not None:
        updated_fb = dict(evaluation.feedback or {})
        updated_fb.update(eval_update.feedback)
        evaluation.feedback = updated_fb
        
    if eval_update.is_reviewed is not None:
        evaluation.is_reviewed = eval_update.is_reviewed
        
    if token:
        payload = decode_token(token)
        if payload and "user_id" in payload:
            evaluation.reviewed_by_id = payload["user_id"]

    db.commit()
    db.refresh(evaluation)
    return evaluation

