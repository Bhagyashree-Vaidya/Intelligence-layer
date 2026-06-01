"""Social Signals API — hiring intent from LinkedIn posts.

Endpoints:
  GET  /api/signals         — list classified hiring signals
  GET  /api/signals/stats   — dashboard summary stats
  POST /api/signals/scan    — trigger a manual scan
  GET  /api/signals/contacts — networking contacts from signals
  POST /api/signals/outreach — generate outreach message for a contact
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.logger import log
from app.services.signals.classifier import get_signals, get_contacts, get_signal_stats

router = APIRouter(prefix="/api/signals", tags=["signals"])


# ── List signals ─────────────────────────────────────────────────────────

@router.get("")
async def list_signals(
    min_intent: int = Query(50, ge=0, le=100),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
):
    """Get classified hiring signals, sorted by hiring intent."""
    offset = (page - 1) * per_page
    signals, total = await get_signals(
        min_intent=min_intent,
        action=action,
        limit=per_page,
        offset=offset,
    )
    return {
        "signals": signals,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


# ── Stats ────────────────────────────────────────────────────────────────

@router.get("/stats")
async def signal_stats():
    """Dashboard stats for the signals tab."""
    return await get_signal_stats()


# ── Manual scan trigger ──────────────────────────────────────────────────

@router.post("/scan")
async def trigger_scan():
    """Manually trigger a LinkedIn signal scan.

    Dispatches to the arq worker queue. Falls back to inline
    execution if Redis is unavailable (dev mode).
    """
    try:
        from app.services.queue import enqueue_signal_scan, is_redis_available

        if await is_redis_available():
            job_id = await enqueue_signal_scan()
            return {
                "status": "queued",
                "job_id": job_id,
                "message": "Signal scan dispatched to worker queue",
            }
    except Exception as e:
        log.warning(f"Queue unavailable, running inline: {e}")

    # Fallback: run inline (useful for dev without Redis)
    from app.workers.signals_worker import scan_linkedin_signals
    result = await scan_linkedin_signals(ctx={})
    return {
        "status": "completed",
        "result": result,
        "message": "Signal scan completed inline (no Redis)",
    }


# ── Contacts ─────────────────────────────────────────────────────────────

@router.get("/contacts")
async def list_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    recruiter_only: bool = Query(False),
):
    """Get networking contacts discovered from signals."""
    offset = (page - 1) * per_page
    contacts, total = await get_contacts(
        limit=per_page,
        offset=offset,
        recruiter_only=recruiter_only,
    )
    return {
        "contacts": contacts,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ── Outreach generation ─────────────────────────────────────────────────

class OutreachRequest(BaseModel):
    post_content: str
    author_name: str
    author_title: str
    role_mentioned: str = ""


@router.post("/outreach")
async def generate_outreach(req: OutreachRequest):
    """Generate a personalized outreach message for a hiring signal."""
    from app.services.ai import orchestrator
    from app.database import get_profile

    profile = await get_profile()
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not set up yet")

    # Build user profile summary for outreach generation
    user_summary = (
        f"{profile.get('first_name', '')} {profile.get('last_name', '')}, "
        f"{profile.get('current_title', '')} at {profile.get('current_company', '')}. "
        f"Skills: {profile.get('skills', '')}. "
        f"Experience: {profile.get('years_experience', 0)} years."
    )

    message = await orchestrator.generate_outreach(
        post_content=req.post_content,
        author_name=req.author_name,
        author_title=req.author_title,
        role_mentioned=req.role_mentioned,
        user_profile=user_summary,
    )

    return {"outreach_message": message}
