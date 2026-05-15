"""JobPilot — Job dashboard + profile API for the Chrome extension."""

import sys
import asyncio
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure sibling modules are importable (needed for Vercel deployment)
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db
import scraper_service as scraper
import bigtech_scrapers as bigtech
import answer_engine
import apify_service as apify
import relevancy_engine

BASE_DIR = Path(__file__).parent
RESUME_DIR = BASE_DIR / "data" / "resumes"
RESUME_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="JobPilot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/resumes-dl", StaticFiles(directory=RESUME_DIR), name="resumes-dl")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

scrape_status = {"running": False, "progress": "", "last_result": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    q: str = "",
    company: str = "",
    location: str = "",
    role: str = "",
    freshness: str = "",
    sort: str = "relevancy",
    page: int = 1,
):
    jobs, total = await db.search_jobs(
        q, company, location, role,
        freshness=freshness, sort=sort, page=page, per_page=40,
    )
    applied_ids = await db.get_applied_job_ids()
    stats = await db.get_stats()
    total_pages = max(1, (total + 39) // 40)

    # Enrich each job with freshness and parsed keywords
    import json as _json
    for job in jobs:
        job["freshness"] = relevancy_engine.compute_freshness(
            job.get("updated_at") or job.get("first_published", "")
        )
        kw_raw = job.get("keywords_matched", "")
        if isinstance(kw_raw, str) and kw_raw:
            try:
                job["keywords_list"] = _json.loads(kw_raw)
            except Exception:
                job["keywords_list"] = []
        else:
            job["keywords_list"] = []
        # Color based on relevancy_score
        rs = job.get("relevancy_score", 0) or 0
        if rs >= 75:
            job["color"] = "green"
        elif rs >= 50:
            job["color"] = "yellow"
        elif rs >= 30:
            job["color"] = "orange"
        else:
            job["color"] = "gray"

    return templates.TemplateResponse(request, "dashboard.html", {
        "jobs": jobs, "applied_ids": applied_ids,
        "stats": stats, "total": total, "page": page,
        "total_pages": total_pages,
        "q": q, "company": company, "location": location, "role": role,
        "freshness": freshness, "sort": sort,
    })


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    profile = await db.get_profile()
    resumes = await db.get_resumes()
    stats = await db.get_stats()
    return templates.TemplateResponse(request, "profile.html", {
        "profile": profile, "resumes": resumes, "stats": stats,
    })


@app.get("/applications", response_class=HTMLResponse)
async def applications_page(request: Request, status: str = ""):
    apps = await db.get_applications()
    app_stats = await db.get_application_stats()
    stats = await db.get_stats()

    # Filter by status tab if set
    if status:
        apps = [a for a in apps if a["status"] == status]

    # Map pipeline stage numbers for the progress bar
    stage_map = {"saved": 0, "applied": 1, "screen": 2, "interview": 3, "offer": 4, "rejected": 5}
    for a in apps:
        a["stage"] = stage_map.get(a["status"], 0)

    return templates.TemplateResponse(request, "applications.html", {
        "applications": apps,
        "app_stats": app_stats,
        "stats": stats,
        "current_status": status,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API — Profile (also consumed by the Chrome extension)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/profile")
async def api_get_profile():
    """Chrome extension calls this to get autofill data."""
    profile = await db.get_profile()
    resumes = await db.get_resumes()
    default_resume = next((r for r in resumes if r["is_default"]), resumes[0] if resumes else None)
    return {
        "profile": profile,
        "resumes": resumes,
        "default_resume_url": f"/resumes-dl/{default_resume['filename']}" if default_resume else None,
        "default_resume_name": default_resume["original_name"] if default_resume else None,
    }


@app.post("/api/profile")
async def save_profile(request: Request):
    data = await request.form()
    await db.update_profile(dict(data))
    return RedirectResponse("/profile?saved=1", status_code=303)


# ═══════════════════════════════════════════════════════════════════════════════
# API — Resumes
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/resumes/upload")
async def upload_resume(
    file: UploadFile = File(...),
    role_tags: str = Form(""),
    is_default: str = Form("off"),
):
    ext = Path(file.filename).suffix
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = RESUME_DIR / safe_name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    await db.add_resume(safe_name, file.filename, role_tags, is_default == "on")
    return RedirectResponse("/profile?uploaded=1", status_code=303)


@app.post("/api/resumes/{resume_id}/delete")
async def delete_resume(resume_id: int):
    filename = await db.delete_resume(resume_id)
    if filename:
        p = RESUME_DIR / filename
        if p.exists():
            p.unlink()
    return RedirectResponse("/profile?deleted=1", status_code=303)


# ═══════════════════════════════════════════════════════════════════════════════
# API — Scraper
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/scrape")
async def start_scrape(request: Request):
    if scrape_status["running"]:
        return JSONResponse({"error": "Scrape already running"}, 409)

    form = await request.form()
    hours = int(form.get("hours", 168))
    roles = form.get("roles", "")
    role_keys = [r.strip() for r in roles.split(",") if r.strip()] or None

    scrape_status.update(running=True, progress="Starting...", last_result="")

    async def run():
        try:
            def on_progress(done, total):
                scrape_status["progress"] = f"{done}/{total} companies"

            jobs = await scraper.scrape_jobs(
                role_keys=role_keys, hours=hours, progress_callback=on_progress,
            )
            count = await db.upsert_jobs(jobs)
            scrape_status["last_result"] = f"Scraped {len(jobs)} matching jobs from {count} entries"
        except Exception as e:
            scrape_status["last_result"] = f"Error: {e}"
        finally:
            scrape_status.update(running=False, progress="")

    asyncio.create_task(run())
    return JSONResponse({"status": "started"})


@app.get("/api/scrape/status")
async def scrape_progress():
    return scrape_status


# ═══════════════════════════════════════════════════════════════════════════════
# API — Application tracking
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/track/{job_id}")
async def track_application(job_id: int, status: str = Form("applied")):
    """Chrome extension or dashboard calls this after user submits an app."""
    await db.save_application(job_id, None, status)
    return JSONResponse({"ok": True})


@app.post("/api/applications/{app_id}/status")
async def update_status(app_id: int, status: str = Form(...)):
    await db.update_application_status(app_id, status)
    return RedirectResponse("/applications", 303)


# ═══════════════════════════════════════════════════════════════════════════════
# API — Smart Answer Engine (consumed by Chrome extension)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/answers")
async def generate_answers(request: Request):
    """Chrome extension sends questions found on the form; we return smart answers.

    Expected JSON body:
      { "questions": ["Why do you want to work here?", ...],
        "company": "stripe",
        "role_title": "Product Manager" }
    """
    data = await request.json()
    questions = data.get("questions", [])
    company = data.get("company", "")
    role_title = data.get("role_title", "")

    profile = await db.get_profile()
    answers = answer_engine.generate_all_answers(questions, company, role_title, profile)
    return JSONResponse(answers)


# ═══════════════════════════════════════════════════════════════════════════════
# API — Big Tech Scraper
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/scrape/bigtech")
async def start_bigtech_scrape(request: Request):
    """Scrape Big Tech career pages (Apple, Google, Meta, Amazon, Microsoft)."""
    if scrape_status["running"]:
        return JSONResponse({"error": "Scrape already running"}, 409)

    form = await request.form()
    companies_str = form.get("companies", "")
    companies = [c.strip() for c in companies_str.split(",") if c.strip()] or None
    roles_str = form.get("roles", "")
    search_terms = [r.strip() for r in roles_str.split(",") if r.strip()] or None

    scrape_status.update(running=True, progress="Starting Big Tech scrape...", last_result="")

    async def run():
        try:
            def on_progress(done, total):
                scrape_status["progress"] = f"{done}/{total} Big Tech companies"

            jobs = await bigtech.scrape_bigtech(
                companies=companies,
                search_terms=search_terms,
                max_per_company=100,
                progress_callback=on_progress,
            )
            count = await db.upsert_jobs(jobs)
            scrape_status["last_result"] = f"Scraped {len(jobs)} Big Tech jobs, saved {count}"
        except Exception as e:
            scrape_status["last_result"] = f"Error: {e}"
        finally:
            scrape_status.update(running=False, progress="")

    asyncio.create_task(run())
    return JSONResponse({"status": "started"})


# ═══════════════════════════════════════════════════════════════════════════════
# API — Apify (LinkedIn/Indeed/Glassdoor)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/scrape/apify")
async def start_apify_scrape(request: Request):
    """Scrape LinkedIn/Indeed via Apify paid actors.

    Form fields:
      platform: "linkedin" or "indeed"
      roles: comma-separated search terms
    """
    if scrape_status["running"]:
        return JSONResponse({"error": "Scrape already running"}, 409)

    form = await request.form()
    platform = form.get("platform", "linkedin")
    roles_str = form.get("roles", "")
    search_terms = [r.strip() for r in roles_str.split(",") if r.strip()] or None

    scrape_status.update(running=True, progress=f"Starting Apify {platform} scrape...", last_result="")

    async def run():
        try:
            scrape_status["progress"] = f"Running Apify {platform} actor..."
            jobs = await apify.scrape_via_apify(
                platform=platform,
                search_terms=search_terms,
            )
            count = await db.upsert_jobs(jobs)
            scrape_status["last_result"] = f"Apify {platform}: {len(jobs)} jobs scraped, {count} saved"
        except Exception as e:
            scrape_status["last_result"] = f"Apify error: {e}"
        finally:
            scrape_status.update(running=False, progress="")

    asyncio.create_task(run())
    return JSONResponse({"status": "started"})


# ═══════════════════════════════════════════════════════════════════════════════
# API — Answer config (view/edit answers.yaml)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/answers/config")
async def get_answer_config():
    """Return the current answers.yaml as JSON for the profile page."""
    answers = answer_engine.load_custom_answers()
    return JSONResponse(answers)


# ═══════════════════════════════════════════════════════════════════════════════
# API — Relevancy scoring & recruiter finder
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/rescore")
async def rescore_all():
    """Rescore every job against the current profile."""
    profile = await db.get_profile()
    count = await db.rescore_all_jobs(profile)
    return JSONResponse({"ok": True, "rescored": count})


@app.get("/api/jobs/{job_id}/recruiter")
async def get_recruiter(job_id: int):
    """Return LinkedIn search URLs for recruiters/hiring managers."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    urls = relevancy_engine.get_recruiter_urls(
        job["company"], job["title"], job.get("department", ""),
    )
    return JSONResponse(urls)


@app.post("/api/jobs/{job_id}/message")
async def generate_message(job_id: int, request: Request):
    """Generate a personalized outreach message for a job's recruiter.

    Optional JSON body: {"contact_name": "Jane Smith"}
    """
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    profile = await db.get_profile()
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    contact_name = data.get("contact_name", "[Name]")
    message = relevancy_engine.generate_outreach_message(profile, job, contact_name)
    recruiter_urls = relevancy_engine.get_recruiter_urls(
        job["company"], job["title"], job.get("department", ""),
    )
    return JSONResponse({
        "message": message,
        "job": {"title": job["title"], "company": job["company"]},
        **recruiter_urls,
    })


@app.post("/api/scrape/all")
async def start_full_scrape(request: Request):
    """Run ALL scrapers in parallel: ATS + Big Tech + Apify (if token set)."""
    if scrape_status["running"]:
        return JSONResponse({"error": "Scrape already running"}, 409)

    form = await request.form()
    hours = int(form.get("hours", 24))
    roles = form.get("roles", "")
    role_keys = [r.strip() for r in roles.split(",") if r.strip()] or None

    scrape_status.update(running=True, progress="Starting full scrape...", last_result="")

    async def run():
        total_jobs = 0
        errors = []
        try:
            # 1. ATS scrape
            scrape_status["progress"] = "Scraping ATS platforms..."
            try:
                ats_jobs = await scraper.scrape_jobs(role_keys=role_keys, hours=hours)
                await db.upsert_jobs(ats_jobs)
                total_jobs += len(ats_jobs)
            except Exception as e:
                errors.append(f"ATS: {e}")

            # 2. Big Tech scrape
            scrape_status["progress"] = "Scraping Big Tech..."
            try:
                bt_jobs = await bigtech.scrape_bigtech(max_per_company=50)
                await db.upsert_jobs(bt_jobs)
                total_jobs += len(bt_jobs)
            except Exception as e:
                errors.append(f"BigTech: {e}")

            # 3. Apify LinkedIn (if token configured)
            try:
                config = apify.load_apify_config()
                if config.get("token"):
                    scrape_status["progress"] = "Scraping LinkedIn via Apify..."
                    li_jobs = await apify.scrape_via_apify(
                        platform="linkedin",
                        search_terms=role_keys or ["Product Manager", "Software Engineer"],
                    )
                    await db.upsert_jobs(li_jobs)
                    total_jobs += len(li_jobs)
            except Exception as e:
                errors.append(f"Apify: {e}")

            # 4. Rescore all jobs
            scrape_status["progress"] = "Scoring relevancy..."
            profile = await db.get_profile()
            await db.rescore_all_jobs(profile)

            err_str = f" (errors: {'; '.join(errors)})" if errors else ""
            scrape_status["last_result"] = f"Done: {total_jobs} jobs scraped & scored{err_str}"
        except Exception as e:
            scrape_status["last_result"] = f"Error: {e}"
        finally:
            scrape_status.update(running=False, progress="")

    asyncio.create_task(run())
    return JSONResponse({"status": "started"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
