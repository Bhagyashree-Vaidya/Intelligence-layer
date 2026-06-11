"""Daily/Weekly task system + artifact generators.

This is the pivot: the platform's job is now to drive the HUMAN actions that
actually get interviews (outreach, memos, follow-ups), not to feel productive.

Endpoints:
  GET  /api/tasks/today              — daily checklist + tick state + CIOS funnel
  GET  /api/tasks/week              — weekly checklist + tick state
  POST /api/tasks/tick              — tick/untick an item
  POST /api/tasks/generate/memo     — strategy memo for a target company + person
  POST /api/tasks/generate/pm-concept
  POST /api/tasks/generate/article  — LinkedIn post
  GET  /api/tasks/memo-target       — suggest a real person to send the memo to
  GET  /api/tasks/artifacts         — past generated artifacts
"""

from datetime import date, timedelta

from fastapi import APIRouter

from app import database as db
from app.services.ai import orchestrator
from app.logger import log

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# Canonical checklist definitions (the daily/weekly rituals from the verdict).
DAILY_TASKS = [
    {"key": "outreach_5",   "label": "5 hyper-personal outreach messages to UW alumni / HMs"},
    {"key": "strategy_memo", "label": "Write/refine ONE strategy memo — send to a real human"},
    {"key": "apply_5",      "label": "Apply to 5 roles (tailored resume)"},
    {"key": "follow_ups",   "label": "Follow up with people who haven't replied"},
    {"key": "pm_concept",   "label": "Learn 1 PM concept"},
]

WEEKLY_TASKS = [
    {"key": "linkedin_post", "label": "Post one article on LinkedIn"},
    {"key": "cios_review",   "label": "Run the CIOS review — double down on what got replies, kill what didn't"},
    {"key": "case_study",    "label": "Add one case study to the portfolio site"},
    {"key": "book_read",     "label": "Read (book progress)"},
    {"key": "resume_update", "label": "Update resume per feedback"},
]


def _today() -> str:
    return date.today().isoformat()


def _week_start() -> str:
    t = date.today()
    return (t - timedelta(days=t.weekday())).isoformat()  # Monday


async def _profile_text() -> tuple[str, str]:
    """Return (formatted profile, voice instructions)."""
    p = await db.get_profile()
    voice = p.get("voice_instructions", "") or ""
    txt = (
        f"Name: {p.get('first_name','')} {p.get('last_name','')}\n"
        f"Title: {p.get('current_title','')}\n"
        f"Experience: {p.get('years_experience',0)} years\n"
        f"Skills: {p.get('skills','')}\n"
        f"Education: {p.get('education','')}"
    )
    return txt, voice


@router.get("/today")
async def today():
    log_rows = await db.get_task_log(_today(), "daily")
    items = [{**t, "done": log_rows.get(t["key"], {}).get("done", False),
              "notes": log_rows.get(t["key"], {}).get("notes", "")} for t in DAILY_TASKS]
    funnel = await db.get_cios_metrics()
    return {"date": _today(), "tasks": items, "funnel": funnel}


@router.get("/week")
async def week():
    log_rows = await db.get_task_log(_week_start(), "weekly")
    items = [{**t, "done": log_rows.get(t["key"], {}).get("done", False),
              "notes": log_rows.get(t["key"], {}).get("notes", "")} for t in WEEKLY_TASKS]
    return {"week_start": _week_start(), "tasks": items}


@router.post("/tick")
async def tick(body: dict):
    """Body: {task_key, cadence ('daily'|'weekly'), done: bool, notes?}."""
    cadence = body.get("cadence", "daily")
    period = _today() if cadence == "daily" else _week_start()
    await db.set_task(
        task_key=body["task_key"], cadence=cadence, period=period,
        done=bool(body.get("done", True)), notes=body.get("notes", ""),
    )
    return {"ok": True}


@router.get("/memo-target")
async def memo_target():
    """Suggest a real person to send today's strategy memo to — prefer a
    relevant US contact (recruiter/HM) we already discovered, not yet contacted."""
    client = db.get_db()
    resp = (
        client.table("contacts")
        .select("id, name, title, company, linkedin_url, is_recruiter, outreach_status, is_relevant")
        .eq("is_relevant", True)
        .order("is_recruiter", desc=False)  # prefer HMs over recruiters
        .limit(50)
        .execute()
    )
    contacts = resp.data or []
    # Prefer someone not yet contacted.
    pick = next((c for c in contacts if (c.get("outreach_status") or "none") == "none"), None)
    if not pick and contacts:
        pick = contacts[0]
    return {"target": pick, "candidates": contacts[:10]}


@router.post("/generate/memo")
async def generate_memo(body: dict):
    """Body: {company, target_name?, target_title?, target_url?}."""
    profile_txt, voice = await _profile_text()
    company = body.get("company", "")
    target_name = body.get("target_name", "")
    memo = await orchestrator.generate_strategy_memo(
        company=company, target_name=target_name,
        target_title=body.get("target_title", ""),
        user_profile=profile_txt, voice=voice,
    )
    aid = await db.save_artifact(
        kind="strategy_memo", body=memo, title=f"Memo: {company}",
        company=company, target_name=target_name, target_url=body.get("target_url", ""),
    )
    return {"id": aid, "company": company, "target_name": target_name,
            "target_url": body.get("target_url", ""), "memo": memo}


@router.post("/generate/pm-concept")
async def generate_pm_concept(body: dict | None = None):
    focus = (body or {}).get("focus", "")
    text = await orchestrator.generate_pm_concept(focus=focus)
    aid = await db.save_artifact(kind="pm_concept", body=text, title=focus or "PM concept")
    return {"id": aid, "concept": text}


@router.post("/generate/article")
async def generate_article(body: dict):
    """Body: {topic?}."""
    profile_txt, voice = await _profile_text()
    topic = (body or {}).get("topic", "")
    text = await orchestrator.generate_linkedin_article(
        topic=topic, user_profile=profile_txt, voice=voice,
    )
    aid = await db.save_artifact(kind="linkedin_article", body=text, title=topic or "LinkedIn post")
    return {"id": aid, "article": text}


@router.get("/artifacts")
async def artifacts(kind: str | None = None):
    rows = await db.get_artifacts(kind=kind)
    return {"artifacts": rows, "total": len(rows)}
