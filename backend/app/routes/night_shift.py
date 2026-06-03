"""Night Shift API routes — toggle, select (queue), review queue.

Night Shift = browser-automation auto-apply v2. It NEVER touches Tier-1 (Top 20)
companies and NEVER submits — it fills forms and parks them for morning review.

Endpoints:
  GET  /api/night-shift/settings        — read toggle + cap
  PUT  /api/night-shift/settings        — flip toggle / set cap / roles
  POST /api/night-shift/select          — populate the queue (respects toggle)
  POST /api/night-shift/select?dry_run=true — preview selection (no writes)
  GET  /api/night-shift/queue           — the review inbox
  POST /api/night-shift/queue/{id}      — update one item's status (review actions)
  GET  /api/night-shift/tiers           — show the Tier-1/Tier-2 lists (transparency)
"""

from fastapi import APIRouter

from app import database as db
from app.services import night_shift
from app.services.night_shift_config import TIER_1_COMPANIES, TIER_2_COMPANIES
from app.logger import log

router = APIRouter(prefix="/api/night-shift", tags=["night-shift"])


@router.get("/settings")
async def get_settings():
    """Read the Night Shift toggle, nightly cap, and role filter."""
    settings = await db.get_night_shift_settings()
    return {"settings": settings}


@router.put("/settings")
async def update_settings(body: dict):
    """Update Night Shift settings.

    Body fields (all optional):
      - enabled: bool         — the dark/light toggle (OFF by default)
      - max_per_night: int    — nightly cap (default 20)
      - min_fit_score: int    — only queue jobs at/above this AI fit score
      - enabled_roles: str    — comma-separated (e.g. "pm,tpm,product")
    """
    updated = await db.update_night_shift_settings(body)
    log.info(f"Night Shift settings updated: enabled={updated.get('enabled')}, "
             f"cap={updated.get('max_per_night')}")
    return {"settings": updated}


@router.post("/select")
async def select(dry_run: bool = False):
    """Populate the review queue with eligible Tier-2 jobs.

    Applies ALL guardrails (toggle ON, Tier-1 hard block, Tier-2 only, role
    filter, skip applied/queued, one-per-company, nightly cap). With
    dry_run=true, returns what WOULD be queued without writing.
    """
    result = await night_shift.select_for_night_shift(dry_run=dry_run)
    return result


@router.get("/queue")
async def get_queue(status: str | None = None, limit: int = 100):
    """The morning review inbox. Optionally filter by status
    (queued / filled / submitted / error / skipped)."""
    items = await db.get_night_shift_queue(status=status, limit=limit)
    return {"queue": items, "total": len(items)}


@router.post("/queue/{item_id}")
async def update_queue_item(item_id: int, body: dict):
    """Update a queue item (review actions / extension status callbacks).

    Body fields (allowed): status, error_message, fill_screenshot,
    filled_at, reviewed_at, resume_id.
    """
    await db.update_night_shift_item(item_id, **body)
    return {"ok": True}


@router.get("/tiers")
async def get_tiers():
    """Show the tier lists so the user can see exactly what's protected
    (Tier-1 NEVER auto-applied) vs eligible (Tier-2)."""
    return {
        "tier_1_never_apply": sorted(TIER_1_COMPANIES.keys()),
        "tier_2_eligible": TIER_2_COMPANIES,
        "tier_1_count": len(TIER_1_COMPANIES),
        "tier_2_count": len(TIER_2_COMPANIES),
    }
