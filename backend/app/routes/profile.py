"""Profile & resume API routes."""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response

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
        # New stable download route (streams from Supabase Storage with disk fallback).
        "default_resume_url": f"/api/resumes/{default_resume['id']}/download" if default_resume else None,
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
    ext = Path(file.filename).suffix
    safe_name = f"{uuid.uuid4().hex}{ext}"
    data = await file.read()
    content_type = file.content_type or "application/pdf"

    # Primary: persist to Supabase Storage (survives Fly restarts).
    storage_path = safe_name
    stored = db.upload_resume_file(storage_path, data, content_type)
    if not stored:
        storage_path = ""  # fell back to disk only

    # Fallback/local copy: also write to disk (so /tmp path still works in dev
    # and if Storage is briefly unavailable).
    try:
        resume_dir = Path(settings.resume_upload_dir)
        resume_dir.mkdir(parents=True, exist_ok=True)
        (resume_dir / safe_name).write_bytes(data)
    except Exception as e:
        log.warning(f"Local resume copy failed (Storage is primary): {e}")

    resume_id = await db.add_resume(
        safe_name, file.filename, role_tags, is_default, storage_path=storage_path
    )
    log.info(f"Resume uploaded: {file.filename} -> {safe_name} (storage={'yes' if stored else 'disk-only'})")
    return {"ok": True, "id": resume_id, "filename": safe_name, "stored_in_storage": stored}


@router.get("/resumes/{resume_id}/download")
async def download_resume(resume_id: int):
    """Stream a resume file. Tries Supabase Storage first, then local disk."""
    settings = get_settings()
    resumes = await db.get_resumes()
    row = next((r for r in resumes if r["id"] == resume_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Resume not found")

    filename = row.get("original_name") or "resume.pdf"
    storage_path = row.get("storage_path") or ""

    # 1. Supabase Storage
    if storage_path:
        data = db.download_resume_file(storage_path)
        if data:
            return Response(
                content=data,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )

    # 2. Local disk fallback
    p = Path(settings.resume_upload_dir) / row.get("filename", "")
    if p.exists():
        return Response(
            content=p.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    raise HTTPException(status_code=404, detail="Resume file missing from Storage and disk")


@router.get("/resumes/{resume_id}/signed-url")
async def resume_signed_url(resume_id: int):
    """Return a short-lived signed URL the extension can fetch directly."""
    resumes = await db.get_resumes()
    row = next((r for r in resumes if r["id"] == resume_id), None)
    if not row or not row.get("storage_path"):
        raise HTTPException(status_code=404, detail="Resume has no Storage object")
    url = db.create_resume_signed_url(row["storage_path"])
    if not url:
        raise HTTPException(status_code=500, detail="Could not create signed URL")
    return {"url": url, "filename": row.get("original_name", "resume.pdf")}


@router.delete("/resumes/{resume_id}")
async def delete_resume(resume_id: int):
    settings = get_settings()
    filename = await db.delete_resume(resume_id)
    if filename:
        p = Path(settings.resume_upload_dir) / filename
        if p.exists():
            p.unlink()
    return {"ok": True}
