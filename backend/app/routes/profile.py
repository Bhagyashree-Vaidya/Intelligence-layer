"""Profile & resume API routes."""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app import database as db
from app.config import get_settings
from app.logger import log

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile")
async def get_profile():
    """Get profile data (also consumed by Chrome extension)."""
    profile = await db.get_profile()
    resumes = await db.get_resumes()
    default_resume = next((r for r in resumes if r.get("is_default")), resumes[0] if resumes else None)
    return {
        "profile": profile,
        "resumes": resumes,
        "default_resume_url": f"/resumes-dl/{default_resume['filename']}" if default_resume else None,
        "default_resume_name": default_resume["original_name"] if default_resume else None,
    }


@router.put("/profile")
async def update_profile(data: dict):
    """Update profile fields."""
    await db.update_profile(data)
    return {"ok": True}


# ── Resumes ──────────────────────────────────────────────────────────────────

@router.post("/resumes/upload")
async def upload_resume(
    file: UploadFile = File(...),
    role_tags: str = Form(""),
    is_default: bool = Form(False),
):
    settings = get_settings()
    resume_dir = Path(settings.resume_upload_dir)
    resume_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = resume_dir / safe_name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    resume_id = await db.add_resume(safe_name, file.filename, role_tags, is_default)
    log.info(f"Resume uploaded: {file.filename} -> {safe_name}")
    return {"ok": True, "id": resume_id, "filename": safe_name}


@router.delete("/resumes/{resume_id}")
async def delete_resume(resume_id: int):
    settings = get_settings()
    filename = await db.delete_resume(resume_id)
    if filename:
        p = Path(settings.resume_upload_dir) / filename
        if p.exists():
            p.unlink()
    return {"ok": True}
