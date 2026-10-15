import logging
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta
from app.database import get_db
from app.models import Assignment, Submission, Evaluation, User, SubmissionStatus, Rubric, VerificationAttempt
from app.schemas.schemas import (
    SubmissionResponse,
    SubmissionWithEvaluation,
    SubmissionEvaluationResponse,
    EvaluationResponse,
    VerificationOverrideRequest,
)
from app.services.document_parser import DocumentParser
from app.services.llm_service import LLMEvaluationService
from app.services.rubric_engine import RubricEngine
from app.services.groq_models import get_model, ModelCategory
from app.services.classification_service import ClassificationService
from app.services.grading_service import GradingService
from app.services.verification_service import SubmissionVerificationService
from app.config import (
    MAX_UPLOAD_BYTES,
    VERIFICATION_MISMATCH_THRESHOLD,
    VERIFICATION_RATE_LIMIT,
    VERIFICATION_RATE_WINDOW_HOURS,
)
from pathlib import Path
from datetime import datetime, timezone
from app.services.file_storage import get_storage

router = APIRouter(prefix="/submissions", tags=["submissions"])
logger = logging.getLogger(__name__)


from fastapi.security import OAuth2PasswordBearer
from app.routers.auth import get_current_user, require_teacher
from app.services.auth_service import decode_token
from sqlalchemy import func

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

    file_name = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    file_type = _validated_file_type(file_name, assignment)
    file_path = await _save_upload(file, file_name)
    
    submission = Submission(
        student_id=current_user.id,
        assignment_id=assignment.id,
        file_path=file_path,
        original_filename=file_name,
        file_type=file_type,
        status=SubmissionStatus.UPLOADED
    )
    
    db.add(submission)
    db.commit()
    db.refresh(submission)
    
    return submission


def _validated_file_type(file_name: str, assignment: Assignment) -> str:
    file_ext = Path(file_name).suffix.lower()
    allowed_extensions = {".pdf", ".docx", ".txt", ".py", ".java", ".cpp", ".js", ".ts", ".png", ".jpg", ".jpeg"}
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed")
    file_type = "code" if file_ext in {".py", ".java", ".cpp", ".js", ".ts"} else file_ext.strip(".")
    allowed_types = {value.lower().lstrip(".") for value in (assignment.allowed_file_types or [])}
    file_category = "image" if file_type in {"png", "jpg", "jpeg"} else file_type
    if file_type not in allowed_types and file_category not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_type}' is not allowed for this assignment",
        )
    return file_type


async def _save_upload(file: UploadFile, file_name: str) -> str:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds the {MAX_UPLOAD_BYTES}-byte limit",
        )
    content_type = file.content_type or "application/octet-stream"
    try:
        return await run_in_threadpool(
            get_storage().save,
            file_name,
            content,
            content_type,
        )
    except ValueError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error


def _record_verification_attempt(submission: Submission, db: Session) -> None:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=VERIFICATION_RATE_WINDOW_HOURS)
    attempts = db.query(VerificationAttempt).filter(
        VerificationAttempt.student_id == submission.student_id,
        VerificationAttempt.assignment_id == submission.assignment_id,
        VerificationAttempt.created_at >= window_start,
    ).count()
    if attempts >= VERIFICATION_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Verification limit reached. Try again later.")
    db.add(VerificationAttempt(
        submission_id=submission.id,
        student_id=submission.student_id,
        assignment_id=submission.assignment_id,
        created_at=now,
    ))
    db.commit()


def _evaluation_result(submission: Submission, evaluation: Optional[Evaluation] = None) -> dict:
    return {
        "submission_id": submission.id,
        "status": submission.status,
        "evaluation": evaluation,
        "verification_verdict": submission.verification_verdict,
        "verification_confidence": submission.verification_confidence,
        "verification_detected_topic": submission.verification_detected_topic,
        "verification_expected_topic": submission.verification_expected_topic,
        "verification_reasons": submission.verification_reasons,
        "verification_missing_requirements": submission.verification_missing_requirements,
        "verification_model": submission.verification_model,
        "verification_error_code": submission.verification_error_code,
    }


async def _verify_submission_file(
    submission: Submission,
    db: Session,
    use_mock_llm: bool,
) -> tuple[str, Optional[str], object, str, dict]:
    stage_started = perf_counter()
    if submission.file_path is None:
        raise ValueError("Submission has no file path")
    content = await run_in_threadpool(get_storage().read, submission.file_path)
    text, code, images, file_type = DocumentParser.parse_document(
        content,
        submission.file_path,
    )
    submission.extracted_text = text
    submission.extracted_code = code
    submission.file_type = file_type
    content_hash = SubmissionVerificationService.content_hash(text, code)
    same_assignment_duplicate = db.query(Submission.id).filter(
        Submission.id != submission.id,
        Submission.student_id == submission.student_id,
        Submission.assignment_id == submission.assignment_id,
        Submission.content_hash == content_hash,
    ).first() is not None
    wrong_assignment_evidence = db.query(Submission.id).filter(
        Submission.id != submission.id,
        Submission.student_id == submission.student_id,
        Submission.assignment_id != submission.assignment_id,
        Submission.content_hash == content_hash,
    ).first() is not None
    submission.content_hash = content_hash
    db.commit()
    logger.info(
        "Submission preparation completed: submission_id=%s duration_seconds=%.2f",
        submission.id,
        perf_counter() - stage_started,
    )

    rubric_criteria = submission.assignment.rubric or []
    if not rubric_criteria:
        raise ValueError("Assignment has no rubric criteria")

    verification_content = text or ""
    if code and code != text:
        verification_content = f"{verification_content}\n{code}"
    verification_started = perf_counter()
    verification = await SubmissionVerificationService.verify(
        submission.assignment,
        verification_content,
        has_images=bool(images),
        use_mock=use_mock_llm,
        wrong_assignment_evidence=wrong_assignment_evidence,
    )
    if same_assignment_duplicate and verification["verdict"] == "match":
        verification["verdict"] = "duplicate_submission"
        verification["reasons"].append(
            "The same student has already submitted this content for this assignment."
        )
    elif same_assignment_duplicate:
        verification["reasons"].append(
            "The same student has already submitted this content for this assignment."
        )

    submission.verification_verdict = verification["verdict"]
    submission.verification_confidence = verification["confidence"]
    submission.verification_detected_topic = verification["detected_topic"]
    submission.verification_expected_topic = verification["expected_topic"]
    submission.verification_reasons = verification["reasons"]
    submission.verification_missing_requirements = verification["missing_requirements"]
    submission.verification_model = verification["model"]
    submission.verification_error_code = verification.get("error_code")
    db.commit()
    logger.info(
        "Submission verification completed: submission_id=%s verdict=%s model_id=%s duration_seconds=%.2f",
        submission.id,
        verification["verdict"],
        verification.get("model"),
        perf_counter() - verification_started,
    )
    return text, code, images, content_hash, verification


async def _evaluate_submission(
    submission_id: int,
    rubric_id: int,
    use_mock_llm: bool,
    db: Session,
    *,
    allow_mismatch: bool = False,
    record_attempt: bool = True,
) -> dict:
    evaluation_started = perf_counter()
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if record_attempt and submission.student_id is not None:
        _record_verification_attempt(submission, db)
    prior_hash = submission.content_hash
    submission.status = SubmissionStatus.PROCESSING
    db.commit()

    try:
        text, code, images, content_hash, verification = await _verify_submission_file(
            submission, db, use_mock_llm
        )
        if prior_hash != content_hash and submission.evaluation:
            db.delete(submission.evaluation)
            db.flush()
        db.commit()

        rubric_criteria = submission.assignment.rubric or []

        should_reject = (
            verification["verdict"] == "unreadable_or_empty"
            or (
                verification["verdict"] == "mismatch"
                and verification["confidence"] is not None
                and verification["confidence"] >= VERIFICATION_MISMATCH_THRESHOLD
            )
        )
        if should_reject and not allow_mismatch:
            existing_evaluation = db.query(Evaluation).filter(
                Evaluation.submission_id == submission_id
            ).first()
            if existing_evaluation:
                db.delete(existing_evaluation)
            submission.status = SubmissionStatus.NEEDS_ATTENTION
            db.commit()
            return _evaluation_result(submission)

        # Stage 1: classification starts only after verification permits grading.
        classification_started = perf_counter()
        content_type, domain, complexity, _, preliminary_issues = await ClassificationService.classify(
            text, code, rubric_criteria
        )
        classification_model = get_model(ModelCategory.CLASSIFY)
        logger.info(
            "Submission classification completed: submission_id=%s model_id=%s duration_seconds=%.2f",
            submission_id,
            classification_model,
            perf_counter() - classification_started,
        )

        classification_result = {
            "content_type": content_type,
            "domain": domain,
            "complexity": complexity,
        }
        grading_started = perf_counter()
        scores, feedback, evidence, grading_confidence, grading_model = await GradingService.grade(
            text, code, rubric_criteria, classification_result, use_mock=use_mock_llm
        )
        logger.info(
            "Submission grading completed: submission_id=%s model_id=%s duration_seconds=%.2f",
            submission_id,
            grading_model,
            perf_counter() - grading_started,
        )
        total_score, _ = RubricEngine.evaluate(text, code, rubric_criteria, scores, feedback, evidence)
        has_ungraded_visual_content = bool(images)

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
            existing_evaluation.issues = preliminary_issues or []
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
                issues=preliminary_issues or [],
                has_ungraded_visual_content=has_ungraded_visual_content,
            )
            db.add(evaluation)

        submission.status = SubmissionStatus.READY
        db.commit()
        db.refresh(submission)
        db.refresh(evaluation)
        logger.info(
            "Submission evaluation completed: submission_id=%s duration_seconds=%.2f",
            submission_id,
            perf_counter() - evaluation_started,
        )
        return _evaluation_result(submission, evaluation)
    except HTTPException:
        raise
    except Exception as error:
        db.rollback()
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if submission:
            existing_evaluation = db.query(Evaluation).filter(Evaluation.submission_id == submission_id).first()
            submission.status = SubmissionStatus.READY if existing_evaluation else SubmissionStatus.FAILED
            db.commit()
        raise HTTPException(status_code=500, detail="Submission evaluation failed") from error


@router.post("/evaluate/{submission_id}", response_model=SubmissionEvaluationResponse)
async def evaluate_submission(
    submission_id: int,
    rubric_id: int = 1,
    use_mock_llm: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger two-stage evaluation of a submission.

    Stage 1: Classification (content type, domain, complexity)
    Stage 2: Grading (rubric-based scoring with model routing)
    """

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role.value == "student" and submission.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only evaluate your own submission")
    if current_user.role.value == "teacher" and submission.assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only evaluate submissions for your assignments")
    return await _evaluate_submission(
        submission_id,
        rubric_id,
        use_mock_llm,
        db,
        record_attempt=current_user.role.value == "student",
    )


@router.post("/{submission_id}/replace", response_model=SubmissionEvaluationResponse)
async def replace_submission(
    submission_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission or submission.student_id != current_user.id or current_user.role.value != "student":
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status != SubmissionStatus.NEEDS_ATTENTION:
        raise HTTPException(status_code=400, detail="Only submissions needing attention can be replaced")
    file_name = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    file_type = _validated_file_type(file_name, submission.assignment)
    previous_file_path = submission.file_path
    submission.file_path = await _save_upload(file, file_name)
    submission.original_filename = file_name
    submission.file_type = file_type
    submission.extracted_text = None
    submission.extracted_code = None
    submission.content_hash = None
    submission.verification_verdict = None
    submission.verification_confidence = None
    submission.verification_detected_topic = None
    submission.verification_expected_topic = None
    submission.verification_reasons = None
    submission.verification_missing_requirements = None
    submission.verification_model = None
    submission.verification_error_code = None
    submission.teacher_override = False
    submission.teacher_override_by = None
    submission.teacher_override_at = None
    submission.teacher_override_reason = None
    if submission.evaluation:
        db.delete(submission.evaluation)
    submission.status = SubmissionStatus.UPLOADED
    db.commit()
    result = await _evaluate_submission(submission.id, 1, False, db)
    if previous_file_path:
        try:
            await run_in_threadpool(get_storage().delete, previous_file_path)
        except Exception as error:
            logger.error(
                "Previous Supabase upload cleanup failed: exception_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="Replacement was processed, but the previous stored file could not be removed",
            ) from error
    return result


@router.get("/{submission_id}/file")
def download_submission_file(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission or submission.file_path is None:
        raise HTTPException(status_code=404, detail="Submission file not found")
    if current_user.role.value == "student" and submission.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="Submission file not found")
    if current_user.role.value == "teacher" and submission.assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=404, detail="Submission file not found")
    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "code": "text/plain",
        "image": "application/octet-stream",
    }.get(submission.file_type or "", "application/octet-stream")
    return StreamingResponse(
        get_storage().stream(submission.file_path),
        media_type=media_type,
    )


@router.post(
    "/{submission_id}/verification/override",
    response_model=SubmissionEvaluationResponse,
)
async def override_verification(
    submission_id: int,
    request: VerificationOverrideRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission or submission.assignment.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status != SubmissionStatus.NEEDS_ATTENTION:
        raise HTTPException(status_code=400, detail="Only submissions needing attention can be overridden")
    reason = request.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="An override reason is required")
    submission.teacher_override = True
    submission.teacher_override_by = teacher.id
    submission.teacher_override_at = datetime.now(timezone.utc)
    submission.teacher_override_reason = reason[:2000]
    db.commit()
    return await _evaluate_submission(
        submission.id,
        1,
        False,
        db,
        allow_mismatch=True,
        record_attempt=False,
    )


@router.post(
    "/{submission_id}/verification/rerun",
    response_model=SubmissionEvaluationResponse,
)
async def rerun_verification(
    submission_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission or submission.assignment.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        await _verify_submission_file(submission, db, False)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Submission verification failed") from error
    return _evaluation_result(submission, submission.evaluation)


@router.get("/{submission_id}", response_model=SubmissionWithEvaluation)
def get_submission(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get submission with evaluation."""

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role.value == "student" and submission.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role.value == "teacher" and submission.assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Self-heal status if evaluation is present but status was marked failed
    if submission.evaluation and submission.status == SubmissionStatus.FAILED:
        submission.status = SubmissionStatus.READY
        db.commit()

    return submission


@router.get("/", response_model=list[SubmissionWithEvaluation])
def list_submissions(
    student_id: Optional[int] = None,
    student_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List submissions with evaluations."""
    
    query = db.query(Submission)
    if current_user.role.value == "student":
        query = query.filter(Submission.student_id == current_user.id)
    elif current_user.role.value == "teacher":
        query = query.join(Assignment).filter(Assignment.teacher_id == current_user.id)
        if student_id:
            query = query.filter(Submission.student_id == student_id)
        if student_name:
            query = query.join(User, Submission.student_id == User.id).filter(
                func.lower(User.full_name).like(f"%{student_name.lower()}%")
            )
    elif student_id:
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
