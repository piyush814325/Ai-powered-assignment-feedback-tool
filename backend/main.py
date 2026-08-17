from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, submissions
from app.database import Base, engine, SessionLocal
from app.models import Rubric
import app.models  # Import models so they register with Base.metadata

# Create tables in database if they don't exist
Base.metadata.create_all(bind=engine)

def seed_default_rubric():
    db = SessionLocal()
    try:
        existing_rubric = db.query(Rubric).filter(Rubric.id == 1).first()
        if not existing_rubric:
            default_rubric = Rubric(
                id=1,
                name="Standard Assessment Rubric",
                description="Default evaluation rubric across core criteria",
                total_points=100,
                criteria=[
                    {"id": "clarity", "name": "Clarity", "description": "Clear and understandable", "weight": 1.0, "max_points": 15},
                    {"id": "completeness", "name": "Completeness", "description": "All requirements met", "weight": 1.0, "max_points": 20},
                    {"id": "code_quality", "name": "Code Quality", "description": "Well-written code", "weight": 1.0, "max_points": 15},
                    {"id": "correctness", "name": "Correctness", "description": "Correct solution", "weight": 1.5, "max_points": 25},
                    {"id": "documentation", "name": "Documentation", "description": "Well-documented", "weight": 0.75, "max_points": 10},
                    {"id": "organization", "name": "Organization", "description": "Well-organized", "weight": 0.75, "max_points": 10},
                    {"id": "originality", "name": "Originality", "description": "Original work", "weight": 0.5, "max_points": 5},
                ],
                is_active=True
            )
            db.add(default_rubric)
            db.commit()
    except Exception as err:
        print("Rubric seed info:", err)
        db.rollback()
    finally:
        db.close()

seed_default_rubric()

app = FastAPI(title="AI Assignment Feedback Tool", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(submissions.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
