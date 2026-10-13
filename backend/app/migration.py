from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models import Assignment, Submission, User, UserRole


LEGACY_RUBRIC = [
    {"key": "clarity", "label": "Clarity", "description": "Clear and understandable", "max_points": 15},
    {"key": "completeness", "label": "Completeness", "description": "All requirements met", "max_points": 20},
    {"key": "code_quality", "label": "Code Quality", "description": "Well-written code", "max_points": 15},
    {"key": "correctness", "label": "Correctness", "description": "Correct solution", "max_points": 25},
    {"key": "documentation", "label": "Documentation", "description": "Well-documented", "max_points": 10},
    {"key": "organization", "label": "Organization", "description": "Well-organized", "max_points": 10},
    {"key": "originality", "label": "Originality", "description": "Original work", "max_points": 5},
]


def migrate_assignment_rubrics(bind) -> None:
    """Add assignment rubrics and preserve legacy assignments."""
    inspector = inspect(bind)
    if "assignments" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("assignments")}
    if "rubric" not in columns:
        with bind.begin() as connection:
            if bind.dialect.name == "sqlite":
                connection.execute(text("ALTER TABLE assignments ADD COLUMN rubric JSON"))
            else:
                connection.execute(text("ALTER TABLE assignments ADD COLUMN rubric JSON NULL"))
    session = Session(bind=bind)
    try:
        for assignment in session.query(Assignment).filter(Assignment.rubric.is_(None)).all():
            assignment.rubric = LEGACY_RUBRIC
        session.commit()
    finally:
        session.close()


def migrate_legacy_submission_assignments(bind) -> None:
    """Preserve pre-assignment submissions when upgrading the legacy string column."""
    inspector = inspect(bind)
    if "submissions" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("submissions")}
    assignment_column = columns.get("assignment_id")
    if not assignment_column or assignment_column["type"].__class__.__name__.lower() not in {"varchar", "string"}:
        return

    session = Session(bind=bind)
    try:
        legacy_submissions = session.query(Submission).all()
        if not legacy_submissions:
            return

        teacher = session.query(User).filter(User.role == UserRole.TEACHER).first()
        if not teacher:
            teacher = session.query(User).first()
        if not teacher:
            raise RuntimeError("Cannot migrate legacy submissions until at least one user exists")

        assignments_by_legacy_id = {}
        for submission in legacy_submissions:
            legacy_id = (submission.assignment_id or "").strip() or f"legacy-submission-{submission.id}"
            assignment = assignments_by_legacy_id.get(legacy_id)
            if assignment is None:
                assignment = session.query(Assignment).filter(
                    Assignment.teacher_id == teacher.id,
                    Assignment.title == f"Legacy assignment: {legacy_id}",
                ).first()
                if assignment is None:
                    assignment = Assignment(
                        teacher_id=teacher.id,
                        subject_name="Legacy submissions",
                        subject_code="LEGACY",
                        title=f"Legacy assignment: {legacy_id}",
                        description="Migrated from the pre-assignment submission record.",
                        due_date=None,
                        max_score=100,
                        allowed_file_types=["pdf", "docx", "txt", "code", "image"],
                        is_active=False,
                    )
                    session.add(assignment)
                    session.flush()
                assignments_by_legacy_id[legacy_id] = assignment
            submission.assignment_id = assignment.id

        session.commit()
        if bind.dialect.name in ("mysql", "postgresql"):
            with bind.begin() as connection:
                if bind.dialect.name == "mysql":
                    connection.execute(text("ALTER TABLE submissions MODIFY assignment_id INTEGER NOT NULL"))
                else:
                    connection.execute(text("ALTER TABLE submissions ALTER COLUMN assignment_id SET NOT NULL"))
                    connection.execute(text("ALTER TABLE submissions ALTER COLUMN assignment_id TYPE INTEGER USING assignment_id::integer"))
                foreign_keys = inspect(bind).get_foreign_keys("submissions")
                if not any(fk.get("name") == "fk_submissions_assignment_id" for fk in foreign_keys):
                    connection.execute(text(
                        "ALTER TABLE submissions ADD CONSTRAINT fk_submissions_assignment_id "
                        "FOREIGN KEY (assignment_id) REFERENCES assignments(id)"
                    ))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate_evaluation_two_stage_fields(bind) -> None:
    """
    Add new columns to Evaluation table for two-stage rubric-aware grading.
    
    New fields:
    - content_type: classification result (code, document_with_images, text_document, mixed)
    - domain: inferred domain (computer_science, engineering, finance, medical, general)
    - complexity: complexity level (simple, moderate, complex)
    - issues: JSON array of {criterion_key?, description, severity} objects
    - has_ungraded_visual_content: flag set when images found but not used in grading
    - classification_model: model ID used for classification (Stage 1)
    - grading_model: model ID used for grading (Stage 2)
    """
    inspector = inspect(bind)
    if "evaluations" not in inspector.get_table_names():
        return
    
    columns = {column["name"] for column in inspector.get_columns("evaluations")}
    new_columns = [
        ("content_type", "VARCHAR(50)"),
        ("domain", "VARCHAR(50)"),
        ("complexity", "VARCHAR(20)"),
        ("issues", "JSON"),
        ("has_ungraded_visual_content", "BOOLEAN"),
        ("classification_model", "VARCHAR(255)"),
        ("grading_model", "VARCHAR(255)"),
    ]
    
    with bind.begin() as connection:
        for col_name, col_type in new_columns:
            if col_name not in columns:
                if bind.dialect.name == "sqlite":
                    connection.execute(text(f"ALTER TABLE evaluations ADD COLUMN {col_name} {col_type}"))
                elif bind.dialect.name in ("mysql", "postgresql"):
                    if col_name == "has_ungraded_visual_content":
                        connection.execute(text(f"ALTER TABLE evaluations ADD COLUMN {col_name} {col_type} DEFAULT FALSE"))
                    else:
                        connection.execute(text(f"ALTER TABLE evaluations ADD COLUMN {col_name} {col_type} NULL"))
                else:
                    connection.execute(text(f"ALTER TABLE evaluations ADD COLUMN {col_name} {col_type}"))

