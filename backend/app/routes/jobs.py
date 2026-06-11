"""Job browsing, scoring, recruiter, and outreach API routes."""

import json

from fastapi import APIRouter, HTTPException, Query

from app import database as db
from app.services import relevancy_engine
from app.services.ai import orchestrator
from app.logger import log

router = APIRouter(prefix="/api", tags=["jobs"])

# Fixed cover-letter sign-off — appended in code so contact details are never
# altered or hallucinated by the AI.
COVER_LETTER_SIGNATURE = (
    "Best,\n"
    "Bhagyashree Vaidya (Shree)\n"
    "bhagyav@uw.edu | (206) 673-0335\n"
    "LinkedIn: https://www.linkedin.com/in/bhagyashree-vaidya-6b47a811a/"
)


@router.get("/jobs")
async def list_jobs(
    q: str = "", company: str = "", location: str = "", role: str = "",
    freshness: str = "", sort: str = "relevancy", page: int = 1,
    targets_only: bool = False,
):
    """Search and filter jobs with pagination."""
    jobs, total = await db.search_jobs(
        q, company, location, role,
        freshness=freshness, sort=sort, page=page, per_page=40,
        targets_only=targets_only,
    )

    # Enrich each job
    for job in jobs:
        job["freshness"] = relevancy_engine.compute_freshness(
            job.get("updated_at") or job.get("first_published", "")
        )
        kw_raw = job.get("keywords_matched", "")
        if isinstance(kw_raw, str) and kw_raw:
            try:
                job["keywords_list"] = json.loads(kw_raw)
            except Exception:
                job["keywords_list"] = []
        else:
            job["keywords_list"] = kw_raw if isinstance(kw_raw, list) else []

        rs = job.get("relevancy_score", 0) or 0
        job["color"] = "green" if rs >= 75 else "yellow" if rs >= 50 else "orange" if rs >= 30 else "gray"

    total_pages = max(1, (total + 39) // 40)
    return {"jobs": jobs, "total": total, "page": page, "total_pages": total_pages}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/rescore")
async def rescore_all(only_unscored: bool = Query(False), max_batches: int | None = Query(None)):
    """Rescore jobs against the current profile.

    only_unscored: only score jobs with relevancy_score 0/NULL (backfill/incremental).
    max_batches: cap work at N×1000 rows per call (avoids HTTP timeout on big backfills).
    """
    profile = await db.get_profile()
    count = await db.rescore_all_jobs(profile, only_unscored=only_unscored, max_batches=max_batches)
    return {"ok": True, "rescored": count, "only_unscored": only_unscored}


@router.get("/jobs/{job_id}/recruiter")
async def get_recruiter(job_id: int):
    """LinkedIn search URLs for recruiters / hiring managers."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    urls = relevancy_engine.get_recruiter_urls(
        job["company"], job["title"], job.get("department", ""),
    )
    return urls


@router.post("/jobs/{job_id}/message")
async def generate_message(job_id: int, body: dict | None = None):
    """Generate a personalized outreach message."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    profile = await db.get_profile()
    contact_name = (body or {}).get("contact_name", "[Name]")
    message = relevancy_engine.generate_outreach_message(profile, job, contact_name)
    recruiter_urls = relevancy_engine.get_recruiter_urls(
        job["company"], job["title"], job.get("department", ""),
    )
    return {"message": message, "job": {"title": job["title"], "company": job["company"]}, **recruiter_urls}


@router.post("/jobs/{job_id}/cover-letter")
async def generate_cover_letter(job_id: int):
    """Generate a tailored cover letter for a job. → OpenAI (Claude fallback)."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    profile = await db.get_profile()
    if not profile:
        raise HTTPException(400, "Profile not set up yet")

    user_summary = (
        f"{profile.get('first_name', '')} {profile.get('last_name', '')}, "
        f"{profile.get('current_title', '')} at {profile.get('current_company', '')}. "
        f"Experience: {profile.get('years_experience', 0)} years. "
        f"Skills: {profile.get('skills', '')}. "
        f"Education: {profile.get('education', '')}. "
        f"Work auth: {profile.get('work_auth', '')} | Sponsorship: {profile.get('sponsorship', '')}."
    )

    try:
        letter = await orchestrator.generate_cover_letter(
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            job_description=job.get("description", "") or "",
            user_profile=user_summary,
            voice=profile.get("voice_instructions", "") or "",
        )
    except Exception as e:
        log.error(f"Cover letter generation failed for job {job_id}: {e}")
        raise HTTPException(502, "Cover letter generation failed — check AI keys")

    # Append the fixed signature deterministically (never AI-altered).
    letter = f"{letter.rstrip()}\n\n{COVER_LETTER_SIGNATURE}"

    return {
        "cover_letter": letter,
        "job": {"title": job.get("title", ""), "company": job.get("company", "")},
    }


@router.post("/jobs/fix-dates")
async def fix_dates():
    """One-time fix: normalize all non-ISO dates in the jobs table."""
    count = await db.normalize_job_dates()
    return {"ok": True, "fixed": count}


@router.get("/stats")
async def get_stats():
    """Dashboard statistics."""
    stats = await db.get_stats()
    applied_ids = list(await db.get_applied_job_ids())
    return {"stats": stats, "applied_ids": applied_ids}
