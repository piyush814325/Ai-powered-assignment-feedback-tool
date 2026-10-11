from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Assignment, Submission, Evaluation, User, SubmissionStatus, Rubric
from app.schemas.schemas import SubmissionResponse, SubmissionWithEvaluation, EvaluationResponse
from app.services.document_parser import DocumentParser
from app.services.llm_service import LLMEvaluationService
from app.services.rubric_engine import RubricEngine
from app.services.groq_models import get_model, ModelCategory
from app.services.classification_service import ClassificationService
from app.services.grading_service import GradingService
import os
from pathlib import Path
from datetime import datetime, timezone

router = APIRouter(prefix="/submissions", tags=["submissions"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


from fastapi.security import OAuth2PasswordBearer
from app.routers.auth import get_current_user
from app.services.auth_service import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


@router.post("/upload", response_model=SubmissionResponse)
async def upload_submission(
    file: UploadFile = File(...),
    assignment_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload an assignment file."""

    if current_user.role.value != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students can submit assignments")

    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.is_active.is_(True),
    ).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignment is not active or does not exist")

    now = datetime.now(timezone.utc)
    if assignment.due_date:
        due_date = assignment.due_date
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)
        if now > due_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The assignment due date has passed")

    file_name = file.filename or ""
    file_ext = Path(file_name).suffix.lower()
    allowed_extensions = {".pdf", ".docx", ".txt", ".py", ".java", ".cpp", ".js", ".ts", ".png", ".jpg", ".jpeg"}
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file_ext} not allowed"
        )
    
    file_type = "code" if file_ext in {".py", ".java", ".cpp", ".js", ".ts"} else file_ext.strip(".")
    allowed_types = {value.lower().lstrip(".") for value in (assignment.allowed_file_types or [])}
    file_category = "image" if file_type in {"png", "jpg", "jpeg"} else file_type
    if file_type not in allowed_types and file_category not in allowed_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File type '{file_type}' is not allowed for this assignment")

    file_path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{file_name}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    submission = Submission(
        student_id=current_user.id,
        assignment_id=assignment.id,
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
    use_mock_llm: bool = False,
    db: Session = Depends(get_db)
):
    """
    Trigger two-stage evaluation of a submission.
    
    Stage 1: Classification (content type, domain, complexity)
    Stage 2: Grading (rubric-based scoring with model routing)
    """
    
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
        
        rubric_criteria = submission.assignment.rubric or []
        if not rubric_criteria:
            raise ValueError("Assignment has no rubric criteria")

        # STAGE 1: Classification
        content_type, domain, complexity, classification_confidence, preliminary_issues = await ClassificationService.classify(
            text, code, rubric_criteria
        )
        
        classification_model = get_model(ModelCategory.CLASSIFY)
        
        # Check for ungraded visual content
        has_images = len(images) > 0 if images else False
        has_ungraded_visual_content = has_images
        
        # STAGE 2: Grading with model routing
        classification_result = {
            "content_type": content_type,
            "domain": domain,
            "complexity": complexity
        }
        
        scores, feedback, evidence, grading_confidence, grading_model = await GradingService.grade(
            text, code, rubric_criteria, classification_result, use_mock=use_mock_llm
        )
        
        # Calculate total score using rubric engine
        total_score, _ = RubricEngine.evaluate(text, code, rubric_criteria, scores, feedback, evidence)
        
        # Combine all issues
        issues = preliminary_issues or []
        
        # Check if evaluation record already exists for this submission
        existing_evaluation = db.query(Evaluation).filter(Evaluation.submission_id == submission_id).first()
        if existing_evaluation:
            existing_evaluation.rubric_id = rubric_id
            existing_evaluation.total_score = total_score
            existing_evaluation.scores = scores
            existing_evaluation.feedback = feedback
            existing_evaluation.evidence = evidence
            existing_evaluation.ai_confidence = grading_confidence
            existing_evaluation.is_ai_generated = True
            existing_evaluation.grading_model = grading_model
            existing_evaluation.classification_model = classification_model
            existing_evaluation.content_type = content_type
            existing_evaluation.domain = domain
            existing_evaluation.complexity = complexity
            existing_evaluation.issues = issues
            existing_evaluation.has_ungraded_visual_content = has_ungraded_visual_content
            evaluation = existing_evaluation
        else:
            evaluation = Evaluation(
                submission_id=submission_id,
                rubric_id=rubric_id,
                total_score=total_score,
                scores=scores,
                feedback=feedback,
                evidence=evidence,
                ai_confidence=grading_confidence,
                is_ai_generated=True,
                is_reviewed=False,
                grading_model=grading_model,
                classification_model=classification_model,
                content_type=content_type,
                domain=domain,
                complexity=complexity,
                issues=issues,
                has_ungraded_visual_content=has_ungraded_visual_content
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
                # Only mark failed if there is no pre-existing valid evaluation
                existing_eval = db.query(Evaluation).filter(Evaluation.submission_id == submission_id).first()
                if existing_eval:
                    sub.status = SubmissionStatus.READY
                else:
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
    
    # Self-heal status if evaluation is present but status was marked failed
    if submission.evaluation and submission.status == SubmissionStatus.FAILED:
        submission.status = SubmissionStatus.READY
        db.commit()

    return submission


@router.get("/", response_model=list[SubmissionWithEvaluation])
def list_submissions(student_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List submissions with evaluations."""
    
    query = db.query(Submission)
    if student_id:
        query = query.filter(Submission.student_id == student_id)
    
    submissions = query.order_by(Submission.created_at.desc()).all()
    
    # Self-heal any inconsistent status records where evaluation exists
    changed = False
    for sub in submissions:
        if sub.evaluation and sub.status == SubmissionStatus.FAILED:
            sub.status = SubmissionStatus.READY
            changed = True
    if changed:
        db.commit()

    return submissions


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
        
        rubric_criteria = evaluation.submission.assignment.rubric or []
        valid_max_points = {
            criterion.get("key", criterion.get("id")): float(criterion.get("max_points", 0))
            for criterion in rubric_criteria
        }
        updated_scores = {
            key: min(max(0, float(value)), valid_max_points[key])
            for key, value in updated_scores.items()
            if key in valid_max_points
        }
        evaluation.scores = updated_scores
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

