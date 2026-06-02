"""arq worker configuration — persistent background jobs with Redis.

Replaces asyncio.create_task() with reliable, retryable, scheduled jobs.
Runs alongside the FastAPI server via supervisord in production.

Worker functions live in separate modules; this file wires them together.
"""

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.logger import log


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    s = get_settings()
    if not s.redis_url:
        raise RuntimeError(
            "REDIS_URL not set — arq workers need Redis. "
            "Get a free instance at https://upstash.com"
        )

    url = s.redis_url
    # Upstash uses rediss:// (TLS). arq RedisSettings has a native `ssl` param.
    if url.startswith("rediss://"):
        # Parse: rediss://default:PASSWORD@HOST:PORT
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password or None,
            ssl=True,
        )
    elif url.startswith("redis://"):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password or None,
        )
    else:
        raise ValueError(f"Unsupported REDIS_URL scheme: {url[:20]}...")


# ── Worker functions (imported at runtime to avoid circular deps) ────────

async def run_signal_scan(ctx: dict) -> dict:
    """Scan LinkedIn for hiring posts and classify them."""
    from app.workers.signals_worker import scan_linkedin_signals
    return await scan_linkedin_signals(ctx)


async def run_enrich_jobs(ctx: dict, job_ids: list[int] | None = None) -> dict:
    """Enrich jobs with AI-extracted metadata."""
    from app.workers.enrich_worker import enrich_jobs
    return await enrich_jobs(ctx, job_ids)


async def run_score_jobs(ctx: dict, job_ids: list[int] | None = None) -> dict:
    """Score jobs against user profile."""
    from app.workers.score_worker import score_jobs
    return await score_jobs(ctx, job_ids)


async def run_auto_apply(ctx: dict) -> dict:
    """Scheduled auto-apply: submit applications for eligible jobs."""
    from app.workers.auto_apply_worker import auto_apply_batch
    return await auto_apply_batch(ctx)


async def run_scrape_all(ctx: dict) -> dict:
    """Scheduled job scrape: ATS + Big Tech + Apify, then rescore + health check."""
    from app.services import scraper_service as scraper
    from app.services import bigtech_scrapers as bigtech
    from app.services import apify_service as apify
    from app import database as db

    total = 0
    errors = []

    # 1. ATS platforms (Greenhouse, Lever, Ashby, etc.)
    try:
        ats_jobs = await scraper.scrape_jobs(hours=1440)
        await db.upsert_jobs(ats_jobs)
        total += len(ats_jobs)
        log.info(f"Cron scrape: {len(ats_jobs)} ATS jobs")
    except Exception as e:
        errors.append(f"ATS: {e}")
        log.error(f"Cron ATS scrape error: {e}")

    # 2. Big Tech (Apple, Meta, Google, Amazon, Microsoft, Netflix)
    try:
        bt_jobs = await bigtech.scrape_bigtech(max_per_company=100)
        await db.upsert_jobs(bt_jobs)
        total += len(bt_jobs)
        log.info(f"Cron scrape: {len(bt_jobs)} Big Tech jobs")
    except Exception as e:
        errors.append(f"BigTech: {e}")
        log.error(f"Cron BigTech scrape error: {e}")

    # 3. Apify — general LinkedIn search + company-targeted searches
    try:
        config = apify.load_apify_config()
        if config.get("token"):
            # 3a. General role search (broad discovery)
            li_jobs = await apify.scrape_via_apify(
                platform="linkedin",
                search_terms=["Product Manager", "Software Engineer",
                              "Program Manager", "UX Designer"],
            )
            await db.upsert_jobs(li_jobs)
            total += len(li_jobs)
            log.info(f"Cron scrape: {len(li_jobs)} Apify LinkedIn general jobs")

            # 3b. Company-targeted searches (Meta, Uber, Adobe, etc.)
            company_jobs = await apify.scrape_company_linkedin_jobs()
            await db.upsert_jobs(company_jobs)
            total += len(company_jobs)
            log.info(f"Cron scrape: {len(company_jobs)} Apify company-targeted jobs")
    except Exception as e:
        errors.append(f"Apify: {e}")
        log.error(f"Cron Apify error: {e}")

    # 4. Rescore against profile
    try:
        profile = await db.get_profile()
        await db.rescore_all_jobs(profile)
    except Exception as e:
        errors.append(f"Rescore: {e}")

    # 5. Coverage health check — log alerts for missing companies
    try:
        await run_coverage_check(ctx)
    except Exception as e:
        log.error(f"Coverage check error: {e}")

    return {"total": total, "errors": errors}


# ── Coverage Health Check ──────────────────────────────────────────────────

# Top 70 target companies — the user's priority list.
# Keys are the canonical names we check the DB for (case-insensitive).
TARGET_COMPANIES: list[str] = [
    "google", "microsoft", "apple", "amazon", "meta", "netflix",
    "salesforce", "slack", "zoom", "stripe", "airbnb", "uber",
    "doordash", "lyft", "pinterest", "reddit", "discord", "figma",
    "notion", "asana", "mongodb", "databricks", "snowflake",
    "cloudflare", "datadog", "okta", "segment", "plaid", "brex",
    "ramp", "robinhood", "coinbase", "block", "toast", "affirm",
    "chime", "sofi", "mercury", "marqeta", "spacex", "anduril",
    "palantir", "scaleai", "openai", "anthropic", "duolingo",
    "instacart", "roblox", "coursera", "dropbox", "gusto",
    "airtable", "rippling", "samsara", "nvidia", "dell", "intel",
    "etsy", "spotify", "adobe", "snap", "tiktok", "servicenow",
    "paypal", "intuit", "ibm", "oracle", "cisco", "linkedin",
]


async def run_coverage_check(ctx: dict) -> dict:
    """Check which target companies have jobs, detect regressions, send alerts."""
    from app import database as db
    from app.config import get_settings

    supa = db.get_db()
    alerts = []
    zero_jobs = []
    company_counts = {}

    # Get job counts per company (case-insensitive)
    for company in TARGET_COMPANIES:
        resp = (
            supa.table("jobs")
            .select("id", count="exact")
            .ilike("company", f"%{company}%")
            .execute()
        )
        count = resp.count or 0
        company_counts[company] = count
        if count == 0:
            zero_jobs.append(company)

    # Get totals
    total_resp = supa.table("jobs").select("id", count="exact").execute()
    total_jobs = total_resp.count or 0

    companies_resp = supa.table("jobs").select("company").execute()
    unique_companies = len(set(r["company"] for r in (companies_resp.data or [])))

    # --- Regression detection: compare with last health check ---
    prev = (
        supa.table("scrape_health")
        .select("zero_job_companies")
        .order("checked_at", desc=True)
        .limit(1)
        .execute()
    )
    prev_zero = set(prev.data[0]["zero_job_companies"]) if prev.data else set()
    curr_zero = set(zero_jobs)

    # Companies that NEWLY lost all jobs (were covered before, now 0)
    new_gaps = curr_zero - prev_zero
    # Companies that got FIXED (were 0, now have jobs)
    fixed = prev_zero - curr_zero

    if new_gaps:
        alert_msg = (
            f"🚨 SCRAPER REGRESSION: {len(new_gaps)} companies LOST coverage: "
            f"{', '.join(sorted(new_gaps))}"
        )
        alerts.append(alert_msg)
        log.error(alert_msg)

    if fixed:
        log.info(f"✅ Coverage restored for: {', '.join(sorted(fixed))}")

    if zero_jobs:
        gap_msg = (
            f"COVERAGE GAP: {len(zero_jobs)}/{len(TARGET_COMPANIES)} target companies "
            f"have 0 jobs: {', '.join(zero_jobs)}"
        )
        alerts.append(gap_msg)
        log.warning(gap_msg)

    # Save health check to DB
    supa.table("scrape_health").insert({
        "total_jobs": total_jobs,
        "total_companies": unique_companies,
        "zero_job_companies": zero_jobs,
        "alerts": alerts,
        "source_breakdown": {"new_gaps": list(new_gaps), "fixed": list(fixed)},
    }).execute()

    # Prune old health checks (keep last 100)
    old = (
        supa.table("scrape_health")
        .select("id")
        .order("checked_at", desc=True)
        .range(100, 200)
        .execute()
    )
    if old.data:
        for row in old.data:
            supa.table("scrape_health").delete().eq("id", row["id"]).execute()

    # --- Send email alert if there are regressions ---
    if new_gaps:
        await _send_coverage_alert(
            new_gaps=new_gaps,
            total_zero=zero_jobs,
            total_jobs=total_jobs,
            total_companies=unique_companies,
        )

    result = {
        "total_jobs": total_jobs,
        "total_companies": unique_companies,
        "zero_job_companies": zero_jobs,
        "new_gaps": list(new_gaps),
        "fixed": list(fixed),
        "alerts": alerts,
    }
    log.info(
        f"Coverage check: {total_jobs} jobs, {unique_companies} cos, "
        f"{len(zero_jobs)} gaps, {len(new_gaps)} new regressions"
    )
    return result


async def _send_coverage_alert(
    new_gaps: set,
    total_zero: list,
    total_jobs: int,
    total_companies: int,
):
    """Send an email alert when scrapers stop pulling jobs for target companies."""
    import smtplib
    from email.mime.text import MIMEText
    from app.config import get_settings

    s = get_settings()
    if not s.smtp_password:
        log.warning("SMTP_PASSWORD not set — cannot send coverage alert email")
        return

    subject = f"🚨 JobPilot: {len(new_gaps)} companies lost job coverage"
    body = (
        f"JobPilot Scraper Alert\n"
        f"{'=' * 40}\n\n"
        f"🚨 REGRESSION DETECTED\n"
        f"These companies STOPPED returning jobs:\n"
        + "\n".join(f"  ❌ {c}" for c in sorted(new_gaps))
        + f"\n\n"
        f"Total coverage: {total_companies} companies, {total_jobs} jobs\n"
        f"All companies with 0 jobs ({len(total_zero)}):\n"
        + "\n".join(f"  • {c}" for c in total_zero)
        + f"\n\n"
        f"Check: https://jobs.shreevaidya.com/api/scrape/health\n"
        f"Fix: re-run scrapers or check ATS configs\n"
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = s.alert_email
    msg["To"] = s.alert_email

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port) as server:
            server.starttls()
            server.login(s.alert_email, s.smtp_password)
            server.send_message(msg)
        log.info(f"Coverage alert email sent to {s.alert_email}")
    except Exception as e:
        log.error(f"Failed to send coverage alert email: {e}")


async def run_health_check(ctx: dict) -> dict:
    """Standalone coverage health check — runs independently of scrape."""
    return await run_coverage_check(ctx)


async def startup(ctx: dict) -> None:
    """Called when arq worker starts. Initialize shared resources."""
    log.info("arq worker starting up")
    ctx["settings"] = get_settings()


async def shutdown(ctx: dict) -> None:
    """Called when arq worker shuts down."""
    log.info("arq worker shutting down")


# ── arq WorkerSettings — this is what `arq app.workers.WorkerSettings` loads ─

class WorkerSettings:
    """arq discovers this class by convention."""

    redis_settings = get_redis_settings()

    functions = [
        run_signal_scan,
        run_enrich_jobs,
        run_score_jobs,
        run_scrape_all,
        run_auto_apply,
        run_health_check,
    ]

    cron_jobs = [
        # ── SIGNALS: 4x/day (every 6h) — company-targeted, 24h window (~$12/mo) ──
        cron(run_signal_scan, hour={0, 6, 12, 18}, minute=15),

        # ── JOBS: 6x/day (every 4h) — 200+ fresh jobs/day ──
        cron(run_scrape_all, hour={0, 4, 8, 12, 16, 20}, minute=30),

        # ── AUTO-APPLY: 4x/day ──
        cron(run_auto_apply, hour={1, 7, 13, 19}, minute=45),

        # ── HEALTH CHECK: 2x/day ──
        cron(run_health_check, hour={6, 18}, minute=30),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # Retry failed jobs up to 3 times with exponential backoff
    max_tries = 3
    job_timeout = 600  # 10 minutes max per job
    health_check_interval = 60
