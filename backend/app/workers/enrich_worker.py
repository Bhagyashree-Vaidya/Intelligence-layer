"""Enrich worker — AI-powered job metadata extraction.

Runs after new jobs are scraped. Extracts structured PM-specific
metadata from job descriptions using the AI orchestrator.
"""

from app.database import get_db
from app.logger import log
from app.services.ai import orchestrator


async def enrich_jobs(ctx: dict, job_ids: list[int] | None = None) -> dict:
    """Enrich jobs with AI-extracted metadata.

    If job_ids is None, enriches all un-enriched jobs.
    """
    db = get_db()

    if job_ids:
        resp = db.table("jobs").select("*").in_("id", job_ids).execute()
    else:
        # Find jobs that haven't been enriched yet
        resp = (
            db.table("jobs")
            .select("*")
            .is_("enriched_at", "null")
            .order("scraped_at", desc=True)
            .limit(50)
            .execute()
        )

    jobs = resp.data or []
    if not jobs:
        log.info("No jobs to enrich")
        return {"enriched": 0, "errors": 0}

    enriched_count = 0
    error_count = 0

    for job in jobs:
        try:
            enrichment = await orchestrator.enrich_job(
                title=job.get("title", ""),
                company=job.get("company", ""),
                description=job.get("description", ""),
            )

            if enrichment:
                import json
                from datetime import datetime, timezone

                db.table("jobs").update({
                    "pm_keywords": json.dumps(enrichment.get("pm_keywords", [])),
                    "required_skills": json.dumps(enrichment.get("required_skills", [])),
                    "preferred_skills": json.dumps(enrichment.get("preferred_skills", [])),
                    "inferred_seniority": enrichment.get("inferred_seniority", ""),
                    "pm_specialization": enrichment.get("pm_specialization", ""),
                    "technical_depth": enrichment.get("technical_depth", 0),
                    "leadership_score": enrichment.get("leadership_score", 0),
                    "remote_type": enrichment.get("remote_type", ""),
                    "visa_likelihood": enrichment.get("visa_likelihood", 0),
                    "enriched_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", job["id"]).execute()

                enriched_count += 1

        except Exception as e:
            log.error(f"Enrich failed for job {job.get('id')}: {e}")
            error_count += 1
            continue

    log.info(f"Enrichment complete: {enriched_count} enriched, {error_count} errors")
    return {"enriched": enriched_count, "errors": error_count}
