"""Scraper trigger and progress API routes + WebSocket for real-time updates."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import database as db
from app.services import scraper_service as scraper
from app.services import bigtech_scrapers as bigtech
from app.services import apify_service as apify
from app.logger import log

router = APIRouter(prefix="/api", tags=["scraper"])

# In-memory scrape state (single-user app)
scrape_status = {"running": False, "progress": "", "last_result": ""}

# WebSocket connections for real-time progress
_ws_clients: set[WebSocket] = set()


async def _broadcast(msg: dict):
    """Send status update to all connected WebSocket clients."""
    import json
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


@router.websocket("/ws/scrape")
async def scrape_ws(ws: WebSocket):
    """WebSocket endpoint for real-time scrape progress."""
    await ws.accept()
    _ws_clients.add(ws)
    try:
        # Send current status immediately
        await ws.send_text(__import__("json").dumps(scrape_status))
        while True:
            await ws.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


@router.get("/scrape/status")
async def scrape_progress():
    return scrape_status


@router.post("/scrape")
async def start_ats_scrape(body: dict | None = None):
    """Trigger ATS-only scrape."""
    if scrape_status["running"]:
        return {"error": "Scrape already running"}, 409

    body = body or {}
    hours = int(body.get("hours", 1440))
    roles = body.get("roles", "")
    role_keys = [r.strip() for r in roles.split(",") if r.strip()] or None

    scrape_status.update(running=True, progress="Starting...", last_result="")

    async def run():
        try:
            def on_progress(done, total):
                scrape_status["progress"] = f"{done}/{total} companies"
                asyncio.ensure_future(_broadcast(scrape_status))

            jobs = await scraper.scrape_jobs(role_keys=role_keys, hours=hours, progress_callback=on_progress)
            count = await db.upsert_jobs(jobs)
            scrape_status["last_result"] = f"Scraped {len(jobs)} jobs from {count} entries"
            log.info(scrape_status["last_result"])
        except Exception as e:
            scrape_status["last_result"] = f"Error: {e}"
            log.error(f"ATS scrape failed: {e}")
        finally:
            scrape_status.update(running=False, progress="")
            await _broadcast(scrape_status)

    asyncio.create_task(run())
    return {"status": "started"}


@router.post("/scrape/bigtech")
async def start_bigtech_scrape(body: dict | None = None):
    if scrape_status["running"]:
        return {"error": "Scrape already running"}, 409

    body = body or {}
    companies = [c.strip() for c in body.get("companies", "").split(",") if c.strip()] or None
    search_terms = [r.strip() for r in body.get("roles", "").split(",") if r.strip()] or None

    scrape_status.update(running=True, progress="Starting Big Tech scrape...", last_result="")

    async def run():
        try:
            def on_progress(done, total):
                scrape_status["progress"] = f"{done}/{total} Big Tech companies"
                asyncio.ensure_future(_broadcast(scrape_status))

            jobs = await bigtech.scrape_bigtech(
                companies=companies, search_terms=search_terms,
                max_per_company=100, progress_callback=on_progress,
            )
            count = await db.upsert_jobs(jobs)
            scrape_status["last_result"] = f"Big Tech: {len(jobs)} jobs, {count} saved"
            log.info(scrape_status["last_result"])
        except Exception as e:
            scrape_status["last_result"] = f"Error: {e}"
            log.error(f"Big Tech scrape failed: {e}")
        finally:
            scrape_status.update(running=False, progress="")
            await _broadcast(scrape_status)

    asyncio.create_task(run())
    return {"status": "started"}


@router.post("/scrape/apify")
async def start_apify_scrape(body: dict | None = None):
    if scrape_status["running"]:
        return {"error": "Scrape already running"}, 409

    body = body or {}
    platform = body.get("platform", "linkedin")
    search_terms = [r.strip() for r in body.get("roles", "").split(",") if r.strip()] or None

    scrape_status.update(running=True, progress=f"Starting Apify {platform}...", last_result="")

    async def run():
        try:
            total = 0

            # General role-based search
            scrape_status["progress"] = f"Running Apify {platform} general search..."
            await _broadcast(scrape_status)
            jobs = await apify.scrape_via_apify(platform=platform, search_terms=search_terms)
            count = await db.upsert_jobs(jobs)
            total += len(jobs)

            # Company-targeted searches (for companies without ATS APIs)
            scrape_status["progress"] = "Running Apify company-targeted searches..."
            await _broadcast(scrape_status)
            company_jobs = await apify.scrape_company_linkedin_jobs()
            count2 = await db.upsert_jobs(company_jobs)
            total += len(company_jobs)

            scrape_status["last_result"] = (
                f"Apify: {len(jobs)} general + {len(company_jobs)} company-targeted = {total} total"
            )
            log.info(scrape_status["last_result"])
        except Exception as e:
            scrape_status["last_result"] = f"Apify error: {e}"
            log.error(f"Apify scrape failed: {e}")
        finally:
            scrape_status.update(running=False, progress="")
            await _broadcast(scrape_status)

    asyncio.create_task(run())
    return {"status": "started"}


@router.post("/scrape/all")
async def start_full_scrape(body: dict | None = None):
    """Run ALL scrapers in sequence + rescore."""
    if scrape_status["running"]:
        return {"error": "Scrape already running"}, 409

    body = body or {}
    hours = int(body.get("hours", 1440))
    roles = body.get("roles", "")
    role_keys = [r.strip() for r in roles.split(",") if r.strip()] or None

    scrape_status.update(running=True, progress="Starting full scrape...", last_result="")

    async def run():
        total_jobs = 0
        errors = []
        try:
            # 1. ATS
            scrape_status["progress"] = "Scraping ATS platforms..."
            await _broadcast(scrape_status)
            try:
                ats_jobs = await scraper.scrape_jobs(role_keys=role_keys, hours=hours)
                await db.upsert_jobs(ats_jobs)
                total_jobs += len(ats_jobs)
            except Exception as e:
                errors.append(f"ATS: {e}")
                log.error(f"ATS scrape error: {e}")

            # 2. Big Tech
            scrape_status["progress"] = "Scraping Big Tech..."
            await _broadcast(scrape_status)
            try:
                bt_jobs = await bigtech.scrape_bigtech(max_per_company=50)
                await db.upsert_jobs(bt_jobs)
                total_jobs += len(bt_jobs)
            except Exception as e:
                errors.append(f"BigTech: {e}")
                log.error(f"Big Tech scrape error: {e}")

            # 3. Apify — general + company-targeted
            try:
                config = apify.load_apify_config()
                if config.get("token"):
                    scrape_status["progress"] = "Scraping LinkedIn via Apify..."
                    await _broadcast(scrape_status)
                    li_jobs = await apify.scrape_via_apify(
                        platform="linkedin",
                        search_terms=role_keys or ["Product Manager", "Software Engineer",
                                                   "Program Manager", "UX Designer"],
                    )
                    await db.upsert_jobs(li_jobs)
                    total_jobs += len(li_jobs)

                    scrape_status["progress"] = "Scraping company-targeted LinkedIn..."
                    await _broadcast(scrape_status)
                    co_jobs = await apify.scrape_company_linkedin_jobs()
                    await db.upsert_jobs(co_jobs)
                    total_jobs += len(co_jobs)
            except Exception as e:
                errors.append(f"Apify: {e}")
                log.error(f"Apify scrape error: {e}")

            # 4. Rescore
            scrape_status["progress"] = "Scoring relevancy..."
            await _broadcast(scrape_status)
            profile = await db.get_profile()
            await db.rescore_all_jobs(profile)

            err_str = f" (errors: {'; '.join(errors)})" if errors else ""
            scrape_status["last_result"] = f"Done: {total_jobs} jobs scraped & scored{err_str}"
            log.info(scrape_status["last_result"])
        except Exception as e:
            scrape_status["last_result"] = f"Error: {e}"
            log.error(f"Full scrape failed: {e}")
        finally:
            scrape_status.update(running=False, progress="")
            await _broadcast(scrape_status)

    asyncio.create_task(run())
    return {"status": "started"}


# ── Coverage Health Check ──────────────────────────────────────────────────

TARGET_COMPANIES = [
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


@router.get("/scrape/health")
async def coverage_health():
    """Check which target companies have jobs and return coverage gaps."""
    supa = db.get_db()

    results = {}
    zero_jobs = []
    for company in TARGET_COMPANIES:
        resp = (
            supa.table("jobs")
            .select("id", count="exact")
            .ilike("company", f"%{company}%")
            .execute()
        )
        count = resp.count or 0
        results[company] = count
        if count == 0:
            zero_jobs.append(company)

    total_resp = supa.table("jobs").select("id", count="exact").execute()
    total_jobs = total_resp.count or 0

    # Get latest health check records
    history = (
        supa.table("scrape_health")
        .select("*")
        .order("checked_at", desc=True)
        .limit(5)
        .execute()
    )

    return {
        "total_jobs": total_jobs,
        "target_companies": len(TARGET_COMPANIES),
        "covered": len(TARGET_COMPANIES) - len(zero_jobs),
        "coverage_pct": round(
            (len(TARGET_COMPANIES) - len(zero_jobs)) / len(TARGET_COMPANIES) * 100, 1
        ),
        "zero_job_companies": zero_jobs,
        "company_counts": results,
        "recent_checks": history.data or [],
    }
