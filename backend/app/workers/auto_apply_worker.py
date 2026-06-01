"""arq worker function for scheduled auto-apply.

Runs every 6 hours (offset from scrape cron by 1 hour so fresh jobs
are already in the DB when auto-apply runs).
"""

from app.logger import log


async def auto_apply_batch(ctx: dict) -> dict:
    """Scheduled auto-apply: submit applications for eligible jobs.

    Only runs if auto-apply is enabled in settings.
    Respects enabled_roles — only applies to PM/TPM/product by default.
    """
    from app import database as db
    from app.services.auto_apply import run_auto_apply

    # Check if auto-apply is enabled
    settings = await db.get_auto_apply_settings()
    if not settings.get("enabled"):
        log.info("Auto-apply cron: disabled, skipping")
        return {"skipped": True, "reason": "disabled"}

    enabled_roles = [
        r.strip() for r in (settings.get("enabled_roles") or "pm,tpm,product").split(",")
        if r.strip()
    ]

    log.info(f"Auto-apply cron: starting batch run (roles={enabled_roles})")

    result = await run_auto_apply(
        min_score=settings.get("min_score", 0),
        max_applications=settings.get("max_per_run", 50),
        exclude_companies=(settings.get("exclude_companies") or "").split(","),
        enabled_roles=enabled_roles,
        one_per_company=True,
        dry_run=False,
    )

    log.info(
        f"Auto-apply cron done: {result.get('applied', 0)} applied, "
        f"{result.get('failed', 0)} failed, "
        f"{result.get('skipped_wrong_role', 0)} skipped (wrong role) "
        f"out of {result.get('total_eligible', 0)} eligible"
    )
    return result
