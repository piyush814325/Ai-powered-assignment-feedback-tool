from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models import (
    AssignmentAssignee,
    Submission,
    UploadBatch,
    UploadBatchFile,
)


def test_upload_tables_and_indexes_create_in_sqlite():
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

        assert inspector.has_table("assignment_assignees")
        assert inspector.has_table("upload_batches")
        assert inspector.has_table("upload_batch_files")
        assert {
            index["name"]
            for index in inspector.get_indexes("assignment_assignees")
        } >= {"uq_assignment_assignees_assignment_student"}
        assert {
            index["name"]
            for index in inspector.get_indexes("upload_batch_files")
        } >= {"ix_upload_batch_files_batch_status"}
        assert {
            "uploaded_by_teacher_id",
            "source",
            "upload_batch_id",
            "name_detection",
            "match_confidence",
            "match_status",
            "teacher_confirmed_by",
            "teacher_confirmed_at",
        } <= {column.name for column in Submission.__table__.columns}
        assert AssignmentAssignee.__table__.indexes
        assert UploadBatch.__table__.columns["created_at"].type.timezone
        assert UploadBatchFile.__table__.columns["updated_at"].type.timezone
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
