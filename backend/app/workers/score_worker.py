"""Score worker — AI-powered job-candidate matching.

Scores jobs against the user's profile using the AI orchestrator.
Produces multi-dimensional scores (ATS fit, PM transition, visa, etc.)
"""

from app.database import get_db, get_profile
from app.logger import log
from app.services.ai import orchestrator


async def score_jobs(ctx: dict, job_ids: list[int] | None = None) -> dict:
    """Score jobs against user profile.

    If job_ids is None, scores all un-scored enriched jobs.
    """
    db = get_db()

    # Need user profile for scoring
    profile = await get_profile()
    if not profile:
        log.warning("No profile found — cannot score jobs")
        return {"scored": 0, "errors": 0, "reason": "no_profile"}

    if job_ids:
        resp = db.table("jobs").select("*").in_("id", job_ids).execute()
    else:
        # Score enriched jobs that haven't been AI-scored yet
        resp = (
            db.table("jobs")
            .select("*")
            .not_.is_("enriched_at", "null")
            .is_("ai_scored_at", "null")
            .order("enriched_at", desc=True)
            .limit(50)
            .execute()
        )

    jobs = resp.data or []
    if not jobs:
        log.info("No jobs to score")
        return {"scored": 0, "errors": 0}

    scored_count = 0
    error_count = 0

    for job in jobs:
        try:
            scores = await orchestrator.score_job(
                job_data=job,
                profile_data=profile,
            )

            if scores:
                import json
                from datetime import datetime, timezone

                db.table("jobs").update({
                    "ai_overall_fit": scores.get("overall_fit", 0),
                    "ai_ats_score": scores.get("ats_score", 0),
                    "ai_pm_transition_fit": scores.get("pm_transition_fit", 0),
                    "ai_visa_probability": scores.get("visa_probability", 0),
                    "ai_response_probability": scores.get("response_probability", 0),
                    "ai_missing_skills": json.dumps(scores.get("missing_skills", [])),
                    "ai_resume_advice": scores.get("resume_recommendations", ""),
                    "ai_scored_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", job["id"]).execute()

                scored_count += 1

        except Exception as e:
            log.error(f"Score failed for job {job.get('id')}: {e}")
            error_count += 1
            continue

    log.info(f"Scoring complete: {scored_count} scored, {error_count} errors")
    return {"scored": scored_count, "errors": error_count}
