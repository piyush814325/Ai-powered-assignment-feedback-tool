from datetime import datetime, timezone
from typing import List
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Assignment, User
from app.routers.auth import get_current_user, require_teacher
from app.schemas.schemas import AssignmentCreate, AssignmentResponse, AssignmentUpdate

router = APIRouter(prefix="/assignments", tags=["assignments"])


def assignment_response(assignment: Assignment) -> dict:
    return {
        "id": assignment.id,
        "teacher_id": assignment.teacher_id,
        "subject_name": assignment.subject_name,
        "subject_code": assignment.subject_code,
        "title": assignment.title,
        "description": assignment.description,
        "due_date": assignment.due_date,
        "max_score": assignment.max_score,
        "allowed_file_types": assignment.allowed_file_types or [],
        "rubric": assignment.rubric or [],
        "is_active": assignment.is_active,
        "submission_count": len(assignment.submissions),
        "created_at": assignment.created_at,
        "updated_at": assignment.updated_at,
    }


def normalize_rubric(criteria: list) -> list:
    normalized = []
    used_keys = set()
    for criterion in criteria:
        label = criterion.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="Every rubric criterion needs a label")
        key = (criterion.key or "").strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", key or label.lower()).strip("_")
        if not key:
            raise HTTPException(status_code=400, detail="Rubric criterion keys must contain letters or numbers")
        if key in used_keys:
            raise HTTPException(status_code=400, detail=f"Duplicate rubric criterion key: {key}")
        if criterion.max_points <= 0:
            raise HTTPException(status_code=400, detail="Rubric max points must be greater than zero")
        used_keys.add(key)
        normalized.append({"key": key, "label": label, "description": (criterion.description or "").strip(), "max_points": criterion.max_points})
    return normalized


def validate_assignment(data: AssignmentCreate | AssignmentUpdate, existing: Assignment | None = None) -> list | None:
    if data.max_score is not None and data.max_score <= 0:
        raise HTTPException(status_code=400, detail="Max score must be greater than zero")
    if data.allowed_file_types is not None and not data.allowed_file_types:
        raise HTTPException(status_code=400, detail="Select at least one allowed file type")
    if data.due_date is not None:
        due_date = data.due_date
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)
        if due_date <= datetime.now(timezone.utc) and isinstance(data, AssignmentCreate):
            raise HTTPException(status_code=400, detail="Due date must be in the future")
    rubric = normalize_rubric(data.rubric) if data.rubric is not None else None
    max_score = data.max_score if data.max_score is not None else (existing.max_score if existing else 100)
    is_active = data.is_active if data.is_active is not None else (existing.is_active if existing else True)
    if is_active and not rubric and not (existing and existing.rubric):
        raise HTTPException(status_code=400, detail="An active assignment needs at least one rubric criterion")
    if rubric and round(sum(item["max_points"] for item in rubric), 2) != round(max_score, 2):
        raise HTTPException(status_code=400, detail="Rubric max points must add up to the assignment max score")
    return rubric


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    assignment_data: AssignmentCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    rubric = validate_assignment(assignment_data)
    payload = assignment_data.model_dump()
    payload["rubric"] = rubric or []
    assignment = Assignment(teacher_id=teacher.id, **payload)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.get("", response_model=List[AssignmentResponse])
def list_assignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Assignment)
    if current_user.role.value == "teacher":
        query = query.filter(Assignment.teacher_id == current_user.id)
    else:
        query = query.filter(Assignment.is_active.is_(True))
    assignments = query.order_by(Assignment.due_date.is_(None), Assignment.due_date, Assignment.created_at.desc()).all()
    return [assignment_response(assignment) for assignment in assignments]


@router.get("/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment or (current_user.role.value != "teacher" and not assignment.is_active):
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment_response(assignment)


@router.patch("/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: int,
    assignment_data: AssignmentUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == teacher.id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    payload = assignment_data.model_dump(exclude_unset=True)
    rubric = validate_assignment(assignment_data, assignment)
    if rubric is not None and rubric != (assignment.rubric or []) and assignment.submissions:
        raise HTTPException(status_code=409, detail="Rubric cannot be edited after students have submitted work")
    if rubric is not None:
        payload["rubric"] = rubric
    for key, value in payload.items():
        setattr(assignment, key, value)
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)


@router.delete("/{assignment_id}", response_model=AssignmentResponse)
def deactivate_assignment(
    assignment_id: int,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == teacher.id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignment.is_active = False
    db.commit()
    db.refresh(assignment)
    return assignment_response(assignment)
