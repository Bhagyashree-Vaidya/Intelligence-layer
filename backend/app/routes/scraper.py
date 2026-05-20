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
    _ws_clients -= dead


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
    hours = int(body.get("hours", 168))
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
            scrape_status["progress"] = f"Running Apify {platform} actor..."
            await _broadcast(scrape_status)
            jobs = await apify.scrape_via_apify(platform=platform, search_terms=search_terms)
            count = await db.upsert_jobs(jobs)
            scrape_status["last_result"] = f"Apify {platform}: {len(jobs)} jobs, {count} saved"
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
    hours = int(body.get("hours", 24))
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

            # 3. Apify
            try:
                config = apify.load_apify_config()
                if config.get("token"):
                    scrape_status["progress"] = "Scraping LinkedIn via Apify..."
                    await _broadcast(scrape_status)
                    li_jobs = await apify.scrape_via_apify(
                        platform="linkedin",
                        search_terms=role_keys or ["Product Manager", "Software Engineer"],
                    )
                    await db.upsert_jobs(li_jobs)
                    total_jobs += len(li_jobs)
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
