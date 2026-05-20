"""Application tracking API routes."""

from fastapi import APIRouter

from app import database as db

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
    """Chrome extension or frontend calls this after submitting an application."""
    status = (body or {}).get("status", "applied")
    app_id = await db.save_application(job_id, None, status)
    return {"ok": True, "id": app_id}


@router.patch("/applications/{app_id}/status")
async def update_status(app_id: int, body: dict):
    """Update an application's pipeline status."""
    status = body.get("status")
    if not status:
        return {"error": "status required"}, 400
    await db.update_application_status(app_id, status)
    return {"ok": True}
