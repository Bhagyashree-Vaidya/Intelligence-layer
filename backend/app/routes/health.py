"""Health check endpoint for Render monitoring."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "jobpilot-api"}
