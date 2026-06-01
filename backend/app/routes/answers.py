"""Answer engine API routes for screening questions."""

import re
from pathlib import Path

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


@router.get("/answers/bank")
async def get_answer_bank():
    """Return the application_answers.md content parsed into a searchable dict.

    The MD file has sections like:
      ### Question Title
      Answer text

    Returns: { "sections": { "question_title": "answer", ... } }
    """
    md_path = Path(__file__).parent.parent / "data" / "application_answers.md"
    if not md_path.exists():
        return {"sections": {}, "raw": "", "error": "application_answers.md not found"}

    raw = md_path.read_text()

    # Parse ### headings and their content
    sections: dict[str, str] = {}
    current_heading = ""
    current_content: list[str] = []

    for line in raw.split("\n"):
        if line.startswith("### "):
            # Save previous section
            if current_heading:
                content = "\n".join(current_content).strip()
                # Skip empty or comment-only sections
                if content and not content.startswith("<!--"):
                    sections[current_heading] = content
            current_heading = line[4:].strip()
            current_content = []
        elif current_heading:
            current_content.append(line)

    # Save last section
    if current_heading:
        content = "\n".join(current_content).strip()
        if content and not content.startswith("<!--"):
            sections[current_heading] = content

    return {"sections": sections, "total": len(sections)}


@router.post("/answers/lookup")
async def lookup_answer(body: dict):
    """Find the best matching answer for a screening question.

    Body: { "question": "Are you authorized to work in the US?" }
    Returns: { "answer": "Yes", "matched_key": "..." }
    """
    question = (body.get("question") or "").lower().strip()
    if not question:
        return {"answer": "", "matched_key": None}

    # Load the answer bank
    bank_resp = await get_answer_bank()
    sections = bank_resp.get("sections", {})

    # Try to match the question against section headings
    best_match = None
    best_score = 0

    for key, value in sections.items():
        key_lower = key.lower()
        # Exact substring match
        if question in key_lower or key_lower in question:
            score = len(key_lower)
            if score > best_score:
                best_score = score
                best_match = (key, value)
            continue

        # Word overlap scoring
        q_words = set(re.findall(r'\w+', question))
        k_words = set(re.findall(r'\w+', key_lower))
        overlap = len(q_words & k_words)
        if overlap > best_score:
            best_score = overlap
            best_match = (key, value)

    if best_match:
        return {"answer": best_match[1], "matched_key": best_match[0]}

    return {"answer": "", "matched_key": None}
