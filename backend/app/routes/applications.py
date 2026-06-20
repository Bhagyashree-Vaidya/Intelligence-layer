"""Application tracking API routes."""

from fastapi import APIRouter

from app import database as db
from app.logger import log

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/applications")
async def list_applications(status: str = ""):
    """List all applications, optionally filtered by status."""
    apps = await db.get_applications()
    app_stats = await db.get_application_stats()

    if status:
        apps = [a for a in apps if a["status"] == status]

    stage_map = {"saved": 0, "applied": 1, "screen": 2, "interview": 3, "offer": 4, "rejected": 5}
    for a in apps:
        a["stage"] = stage_map.get(a["status"], 0)

    return {"applications": apps, "stats": app_stats}


@router.post("/track/{job_id}")
async def track_application(job_id: int, body: dict | None = None):
    """Chrome extension or frontend calls this after submitting an application.

    If already tracked, updates the status instead of creating a duplicate.
    """
    status = (body or {}).get("status", "applied")

    # Check if already tracked (avoid duplicates)
    existing = await db.get_application_by_job_id(job_id)
    if existing:
        # If existing is "saved" and new is "applied", upgrade it
        if existing["status"] == "saved" and status == "applied":
            await db.update_application_status(existing["id"], "applied")
            log.info(f"Application upgraded: job {job_id} saved → applied")
            return {"ok": True, "id": existing["id"], "updated": True}
        # Already tracked at same or higher status
        return {"ok": True, "id": existing["id"], "already_tracked": True}

    app_id = await db.save_application(job_id, None, status)
    log.info(f"Application tracked: job {job_id} → {status}")
    return {"ok": True, "id": app_id}


@router.delete("/track/{job_id}")
async def untrack_application(job_id: int):
    """Un-apply: delete the application for this job (mis-click / didn't go
    through). Removes the application + its events; count drops by 1."""
    client = db.get_db()
    apps = client.table("applications").select("id").eq("job_id", job_id).execute()
    deleted = 0
    for a in (apps.data or []):
        client.table("application_events").delete().eq("app_id", a["id"]).execute()
        client.table("applications").delete().eq("id", a["id"]).execute()
        deleted += 1
    log.info(f"Application un-tracked: job {job_id} ({deleted} removed)")
    return {"ok": True, "deleted": deleted}


@router.patch("/applications/{app_id}/status")
async def update_status(app_id: int, body: dict):
    """Update an application's pipeline status."""
    status = body.get("status")
    if not status:
        return {"error": "status required"}, 400
    await db.update_application_status(app_id, status)
    log.info(f"Application {app_id} → {status}")
    return {"ok": True}


@router.get("/applications/summary")
async def application_summary():
    """Quick summary for dashboard counter — lightweight."""
    stats = await db.get_application_stats()
    return stats
