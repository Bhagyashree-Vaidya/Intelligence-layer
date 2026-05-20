"""Answer engine API routes for screening questions."""

from fastapi import APIRouter

from app import database as db
from app.services import answer_engine

router = APIRouter(prefix="/api", tags=["answers"])


@router.post("/answers")
async def generate_answers(body: dict):
    """Chrome extension sends questions; we return smart answers.

    Body: { "questions": [...], "company": "stripe", "role_title": "PM" }
    """
    questions = body.get("questions", [])
    company = body.get("company", "")
    role_title = body.get("role_title", "")
    profile = await db.get_profile()
    answers = answer_engine.generate_all_answers(questions, company, role_title, profile)
    return answers


@router.get("/answers/config")
async def get_answer_config():
    """Return the current answers.yaml as JSON."""
    answers = answer_engine.load_custom_answers()
    return answers
