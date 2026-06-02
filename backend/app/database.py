"""Supabase database layer — replaces SQLite with hosted PostgreSQL.

All queries use the Supabase Python client. Tables are created via
Supabase dashboard or the migration script in backend/scripts/migrate.py.
"""

import json
import re
from datetime import datetime, timezone
from dateutil import parser as dateparser

from supabase import create_client, Client

from app.config import get_settings
from app.logger import log

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = create_client(s.supabase_url, s.supabase_service_role_key)
        log.info("Supabase client initialized")
    return _client


# ── Profile ──────────────────────────────────────────────────────────────────

async def get_profile() -> dict:
    db = get_db()
    resp = db.table("profile").select("*").eq("id", 1).execute()
    if resp.data:
        row = resp.data[0]
        if isinstance(row.get("education"), str):
            row["education"] = json.loads(row["education"] or "[]")
        return row
    return {}


async def update_profile(data: dict):
    db = get_db()
    fields = [
        "first_name", "last_name", "email", "phone",
        "address", "city", "state", "zip_code", "country",
        "linkedin", "website", "github",
        "current_company", "current_title", "years_experience",
        "education", "skills", "cover_letter_default", "voice_instructions",
        "work_auth", "sponsorship", "gender", "race", "veteran", "disability",
    ]
    update = {}
    for f in fields:
        if f in data:
            val = data[f]
            if f == "education" and isinstance(val, list):
                val = json.dumps(val)
            update[f] = val
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    db.table("profile").upsert({"id": 1, **update}).execute()
    log.info("Profile updated")


# ── Resumes ──────────────────────────────────────────────────────────────────

async def get_resumes() -> list[dict]:
    db = get_db()
    resp = (
        db.table("resumes")
        .select("*")
        .order("is_default", desc=True)
        .order("uploaded_at", desc=True)
        .execute()
    )
    return resp.data or []


async def add_resume(filename: str, original_name: str, role_tags: str, is_default: bool) -> int:
    db = get_db()
    if is_default:
        db.table("resumes").update({"is_default": False}).neq("id", 0).execute()
    resp = db.table("resumes").insert({
        "filename": filename,
        "original_name": original_name,
        "role_tags": role_tags,
        "is_default": is_default,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return resp.data[0]["id"] if resp.data else 0


async def delete_resume(resume_id: int) -> str | None:
    db = get_db()
    resp = db.table("resumes").select("filename").eq("id", resume_id).execute()
    if resp.data:
        filename = resp.data[0]["filename"]
        db.table("resumes").delete().eq("id", resume_id).execute()
        return filename
    return None


# ── Jobs ─────────────────────────────────────────────────────────────────────


def _normalize_date(raw: str) -> str:
    """Parse any date string into ISO 8601 UTC format.

    Handles: ISO 8601, "May 21, 2026", "21 May 2026", epoch millis, etc.
    Returns empty string if unparseable.
    """
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()

    # Already valid ISO → return as-is
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        pass

    # Epoch milliseconds (e.g. "1716307200000")
    if raw.isdigit() and len(raw) >= 10:
        try:
            ts = int(raw)
            if ts > 1e12:  # milliseconds
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            pass

    # Fuzzy parse ("May 21, 2026", "21/05/2026", etc.)
    try:
        dt = dateparser.parse(raw, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError, OverflowError):
        pass

    return ""


async def upsert_jobs(jobs: list[dict]) -> int:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for j in jobs:
        row = {
            "greenhouse_id": str(j.get("greenhouse_id", j.get("id", ""))),
            "company": str(j.get("company", "")),
            "title": str(j.get("title", "")),
            "location": str(j.get("location", "")),
            "department": str(j.get("department", "")),
            "url": str(j.get("url", "")),
            "description": str(j.get("description", ""))[:10000],
            "updated_at": _normalize_date(str(j.get("updated_at", ""))),
            "first_published": _normalize_date(str(j.get("first_published", ""))),
            "employment_type": str(j.get("employment_type", "")),
            "salary_range": str(j.get("salary_range", "")),
            "scraped_at": now,
        }
        db.table("jobs").upsert(
            row,
            on_conflict="greenhouse_id,company",
        ).execute()
        count += 1

    log.info(f"Upserted {count} jobs")
    return count


async def normalize_job_dates() -> int:
    """One-time fix: convert all non-ISO dates in jobs table to ISO 8601."""
    db = get_db()
    fixed = 0
    page = 0
    page_size = 1000

    while True:
        resp = (
            db.table("jobs")
            .select("id, updated_at, first_published")
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break

        for row in rows:
            updates = {}
            ua = row.get("updated_at", "") or ""
            fp = row.get("first_published", "") or ""

            if ua and not re.match(r"^\d{4}-", ua):
                normalized = _normalize_date(ua)
                if normalized and normalized != ua:
                    updates["updated_at"] = normalized

            if fp and not re.match(r"^\d{4}-", fp):
                normalized = _normalize_date(fp)
                if normalized and normalized != fp:
                    updates["first_published"] = normalized

            if updates:
                db.table("jobs").update(updates).eq("id", row["id"]).execute()
                fixed += 1

        page += 1
        if len(rows) < page_size:
            break

    log.info(f"Normalized dates for {fixed} jobs")
    return fixed


async def search_jobs(
    query: str = "", company: str = "", location: str = "", role: str = "",
    freshness: str = "", sort: str = "relevancy", page: int = 1, per_page: int = 40,
) -> tuple[list[dict], int]:
    db = get_db()
    q = db.table("jobs").select("*", count="exact")

    if query:
        q = q.or_(f"title.ilike.%{query}%,description.ilike.%{query}%")
    if company:
        q = q.ilike("company", f"%{company}%")
    if location:
        q = q.ilike("location", f"%{location}%")
    if role:
        q = q.ilike("title", f"%{role}%")
    if freshness:
        hours_map = {"24h": 24, "48h": 48, "7d": 168, "30d": 720}
        hours = hours_map.get(freshness)
        if hours:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            q = q.gte("updated_at", cutoff)

    if sort == "date":
        q = q.order("updated_at", desc=True)
    elif sort == "company":
        q = q.order("company").order("relevancy_score", desc=True)
    else:
        q = q.order("relevancy_score", desc=True).order("updated_at", desc=True)

    offset = (page - 1) * per_page
    q = q.range(offset, offset + per_page - 1)
    resp = q.execute()

    total = resp.count if resp.count is not None else len(resp.data or [])
    return resp.data or [], total


async def get_job(job_id: int) -> dict | None:
    db = get_db()
    resp = db.table("jobs").select("*").eq("id", job_id).execute()
    return resp.data[0] if resp.data else None


# ── Applications ─────────────────────────────────────────────────────────────

async def add_application_event(
    app_id: int,
    to_status: str,
    from_status: str | None = None,
    channel: str = "",
    notes: str = "",
) -> int:
    """Append an immutable event to an application's timeline.

    This is the heart of the feedback loop: every status transition is recorded
    as its own timestamped row in application_events instead of overwriting
    applications.status. Makes Offer Rate, Interview Rate, and time-to-callback
    computable. Best-effort — never breaks the caller if the insert fails.
    """
    try:
        db = get_db()
        resp = db.table("application_events").insert({
            "app_id": app_id,
            "from_status": from_status,
            "to_status": to_status,
            "channel": channel,
            "notes": notes,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return resp.data[0]["id"] if resp.data else 0
    except Exception as e:
        log.error(f"add_application_event failed for app {app_id}: {e}")
        return 0


async def save_application(job_id: int, resume_id: int | None, status: str = "saved") -> int:
    db = get_db()
    resp = db.table("applications").insert({
        "job_id": job_id,
        "resume_id": resume_id,
        "status": status,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    app_id = resp.data[0]["id"] if resp.data else 0
    # Record the first event in the timeline (from_status NULL = creation).
    if app_id:
        await add_application_event(app_id, to_status=status, from_status=None)
    return app_id


async def update_application_status(app_id: int, status: str):
    db = get_db()
    # Read the current status first so we can record the transition (from → to).
    prev = db.table("applications").select("status").eq("id", app_id).execute()
    from_status = prev.data[0]["status"] if prev.data else None
    db.table("applications").update({"status": status}).eq("id", app_id).execute()
    # Append to the timeline only if the status actually changed.
    if from_status != status:
        await add_application_event(app_id, to_status=status, from_status=from_status)


async def get_applications() -> list[dict]:
    db = get_db()
    resp = (
        db.table("applications")
        .select("*, jobs(title, company, location, url), resumes(original_name)")
        .order("applied_at", desc=True)
        .execute()
    )
    rows = []
    for r in resp.data or []:
        job = r.pop("jobs", {}) or {}
        resume = r.pop("resumes", {}) or {}
        rows.append({**r, **job, "resume_name": resume.get("original_name", "")})
    return rows


async def get_applied_job_ids() -> set[int]:
    db = get_db()
    resp = db.table("applications").select("job_id").execute()
    return {r["job_id"] for r in resp.data or []}


async def get_application_by_job_id(job_id: int) -> dict | None:
    """Get an existing application by job ID (for duplicate detection)."""
    db = get_db()
    resp = db.table("applications").select("*").eq("job_id", job_id).limit(1).execute()
    return resp.data[0] if resp.data else None


async def get_stats() -> dict:
    db = get_db()
    jobs_resp = db.table("jobs").select("id", count="exact").execute()
    apps_resp = db.table("applications").select("id", count="exact").execute()
    companies_resp = db.rpc("count_distinct_companies").execute()

    return {
        "jobs": jobs_resp.count or 0,
        "applications": apps_resp.count or 0,
        "companies": companies_resp.data[0]["count"] if companies_resp.data else 0,
    }


async def get_application_stats() -> dict:
    db = get_db()
    resp = db.table("applications").select("status").execute()
    rows = resp.data or []

    status_counts: dict[str, int] = {}
    for r in rows:
        s = r["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    total = sum(status_counts.values())
    sent = total - status_counts.get("saved", 0)
    interviews = status_counts.get("interview", 0)
    offers = status_counts.get("offer", 0)
    screens = status_counts.get("screen", 0)
    responded = interviews + offers + screens + status_counts.get("rejected", 0)
    reply_rate = round((responded / sent * 100), 1) if sent > 0 else 0

    return {
        "total": total, "sent": sent, "reply_rate": reply_rate,
        "interviews": interviews, "offers": offers,
        "by_status": {
            "all": total,
            "saved": status_counts.get("saved", 0),
            "applied": status_counts.get("applied", 0),
            "screen": screens,
            "interview": interviews,
            "offer": offers,
            "rejected": status_counts.get("rejected", 0),
        },
    }


async def get_cios_metrics() -> dict:
    """North Star funnel from the event timeline (CIOS).

    Unlike get_application_stats (which counts CURRENT status only and so loses
    history when an app moves on), this counts whether an application EVER
    reached each stage — the correct basis for conversion rates.

    Optimization hierarchy (per CIOS spec):
      P1 Offer Rate          = offers / applications_sent
      P2 Interview Rate      = interviews / applications_sent
    """
    db = get_db()

    # applications "sent" = ever reached 'applied' or beyond (exclude pure 'saved')
    apps_resp = db.table("applications").select("id, status").execute()
    apps = apps_resp.data or []
    sent_ids = {a["id"] for a in apps if a["status"] != "saved"}
    sent = len(sent_ids)

    # For each app, the set of statuses it has EVER had (from the timeline).
    ev_resp = db.table("application_events").select("app_id, to_status").execute()
    reached: dict[str, set[int]] = {}
    for e in ev_resp.data or []:
        reached.setdefault(e["to_status"], set()).add(e["app_id"])

    def ever(*statuses: str) -> int:
        s: set[int] = set()
        for st in statuses:
            s |= reached.get(st, set())
        return len(s & sent_ids) if sent_ids else 0

    interviews = ever("interview", "offer")   # offer implies interview happened
    offers = ever("offer")

    def rate(n: int) -> float:
        return round(100.0 * n / sent, 1) if sent else 0.0

    return {
        "applications_sent": sent,
        "interviews": interviews,
        "offers": offers,
        "interview_rate": rate(interviews),   # P2
        "offer_rate": rate(offers),           # P1 — North Star
        "responses": ever("screen", "interview", "offer"),
        "response_rate": rate(ever("screen", "interview", "offer")),
        "rejections": ever("rejected"),
    }


# ── Auto-Apply ──────────────────────────────────────────────────────────────

async def get_auto_apply_candidates(
    min_score: int = 50,
    exclude_ids: set[int] | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get jobs eligible for auto-apply: high score, not yet applied, recent."""
    db = get_db()
    q = (
        db.table("jobs")
        .select("*")
        .gte("relevancy_score", min_score)
        .order("relevancy_score", desc=True)
        .limit(limit)
    )
    resp = q.execute()
    rows = resp.data or []

    # Filter out already-applied
    if exclude_ids:
        rows = [r for r in rows if r["id"] not in exclude_ids]

    return rows


async def log_auto_apply(
    job_id: int,
    status: str,
    ats: str = "",
    response: str = "",
) -> int:
    """Log an auto-apply attempt to the auto_apply_log table."""
    db = get_db()
    resp = db.table("auto_apply_log").insert({
        "job_id": job_id,
        "status": status,
        "ats_platform": ats,
        "response_data": response,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return resp.data[0]["id"] if resp.data else 0


async def get_auto_apply_log(limit: int = 50) -> list[dict]:
    """Get recent auto-apply log entries with job details."""
    db = get_db()
    resp = (
        db.table("auto_apply_log")
        .select("*, jobs(title, company, url)")
        .order("attempted_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = []
    for r in resp.data or []:
        job = r.pop("jobs", {}) or {}
        rows.append({**r, **job})
    return rows


async def get_auto_apply_settings() -> dict:
    """Get auto-apply settings from the auto_apply_settings table."""
    db = get_db()
    resp = db.table("auto_apply_settings").select("*").eq("id", 1).execute()
    if resp.data:
        return resp.data[0]
    return {
        "enabled": False,
        "min_score": 0,
        "max_per_run": 50,
        "exclude_companies": "",
        "enabled_roles": "pm,tpm,product",
    }


async def update_auto_apply_settings(data: dict) -> dict:
    """Update auto-apply settings."""
    db = get_db()
    update = {}
    for key in ("enabled", "min_score", "max_per_run", "exclude_companies", "enabled_roles"):
        if key in data:
            update[key] = data[key]
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    db.table("auto_apply_settings").upsert({"id": 1, **update}).execute()
    return await get_auto_apply_settings()


async def rescore_all_jobs(profile: dict, only_unscored: bool = False,
                           max_batches: int | None = None) -> int:
    """Score jobs against the profile.

    PostgREST caps a plain select at 1000 rows, so we MUST paginate or most
    of the table never gets scored (jobs then sink to the bottom of the
    relevancy-sorted UI and look 'missing').

    Args:
        only_unscored: if True, only score jobs with relevancy_score 0/NULL
            (incremental — fast, for the scrape pipeline). Every scored job
            gets at least the +3 location floor, so score==0 reliably means
            'never scored'. If False, re-score everything (for profile changes).
        max_batches: if set, stop after this many 1000-row batches (bounds the
            work per call so a one-shot HTTP trigger can't time out).
    """
    from app.services.relevancy_engine import score_job

    db = get_db()
    PAGE = 1000
    total = 0
    offset = 0
    batches = 0

    while True:
        q = db.table("jobs").select("id, title, description, location, department")
        if only_unscored:
            # Scored rows leave this filter (score >= 3), so always read the
            # first page of remaining unscored rows until none are left.
            q = q.or_("relevancy_score.eq.0,relevancy_score.is.null").limit(PAGE)
        else:
            q = q.range(offset, offset + PAGE - 1)

        rows = q.execute().data or []
        if not rows:
            break

        for row in rows:
            result = score_job(row, profile)
            db.table("jobs").update({
                "relevancy_score": result["relevancy_score"],
                "keywords_matched": json.dumps(result["keywords_matched"]),
            }).eq("id", row["id"]).execute()

        total += len(rows)
        batches += 1
        log.info(f"Rescored batch: {total} so far (only_unscored={only_unscored})")

        if len(rows) < PAGE:
            break
        if max_batches is not None and batches >= max_batches:
            break
        if not only_unscored:
            offset += PAGE

    log.info(f"Rescore complete: {total} jobs (only_unscored={only_unscored})")
    return total


# ── Night Shift ───────────────────────────────────────────────────────────────

async def get_night_shift_settings() -> dict:
    """Read the Night Shift toggle + cap (single row, id=1). OFF by default."""
    db = get_db()
    resp = db.table("night_shift_settings").select("*").eq("id", 1).execute()
    if resp.data:
        return resp.data[0]
    return {
        "enabled": False, "max_per_night": 20, "min_fit_score": 0,
        "enabled_roles": "pm,tpm,product",
    }


async def update_night_shift_settings(data: dict) -> dict:
    db = get_db()
    update = {}
    for key in ("enabled", "max_per_night", "min_fit_score", "enabled_roles"):
        if key in data:
            update[key] = data[key]
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    db.table("night_shift_settings").upsert({"id": 1, **update}).execute()
    return await get_night_shift_settings()


async def get_queued_job_ids() -> set[int]:
    """Job IDs already in the Night Shift queue that are still open
    (queued/filled) — so we never double-queue the same job."""
    db = get_db()
    resp = (
        db.table("night_shift_queue")
        .select("job_id")
        .in_("status", ["queued", "filled"])
        .execute()
    )
    return {r["job_id"] for r in resp.data or [] if r.get("job_id")}


async def enqueue_night_shift(item: dict) -> int:
    """Add one job to the Night Shift review queue. Best-effort; the unique
    partial index (job_id where status in queued/filled) prevents duplicates."""
    db = get_db()
    try:
        resp = db.table("night_shift_queue").insert({
            "job_id": item["job_id"],
            "company": item.get("company", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "role": item.get("role", ""),
            "resume_id": item.get("resume_id"),
            "tier": item.get("tier", "tier_2"),
            "status": "queued",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return resp.data[0]["id"] if resp.data else 0
    except Exception as e:
        # Duplicate (already queued) or other — log and skip, never crash the run.
        log.warning(f"enqueue_night_shift skip job {item.get('job_id')}: {e}")
        return 0


async def get_night_shift_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    """Read the review inbox, optionally filtered by status, with job details."""
    db = get_db()
    q = (
        db.table("night_shift_queue")
        .select("*, jobs(title, company, url, ai_overall_fit)")
        .order("queued_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    resp = q.execute()
    rows = []
    for r in resp.data or []:
        job = r.pop("jobs", {}) or {}
        rows.append({**r, **job})
    return rows


async def update_night_shift_item(item_id: int, **fields) -> None:
    """Update a queue item's status / error / timestamps."""
    db = get_db()
    allowed = {
        "status", "error_message", "fill_screenshot",
        "filled_at", "reviewed_at", "resume_id",
    }
    update = {k: v for k, v in fields.items() if k in allowed}
    if update:
        db.table("night_shift_queue").update(update).eq("id", item_id).execute()
