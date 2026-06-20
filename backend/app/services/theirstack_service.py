"""TheirStack jobs ingestion — fills the no-public-ATS gap companies.

TheirStack aggregates postings from Workday, LinkedIn, and thousands of sites,
so it reaches the companies our ATS/BigTech scrapers can't (Adobe, Capital One,
Cisco, IBM, VMware, Walmart, GitHub, etc.).

Cost: 1 API credit per job returned. Free tier = 200/month. So this is run
SPARINGLY (one-time fill + monthly refresh), per-company, capped — NOT on the
4x/day cadence Apify uses. Product + Program roles only for now.
"""

import httpx
from datetime import datetime, timezone

from app.config import get_settings
from app.logger import log

API_URL = "https://api.theirstack.com/v1/jobs/search"

# The 15 companies with zero PM/Program coverage that TheirStack can reach.
GAP_COMPANIES = [
    "Adobe", "Capital One", "Cisco", "IBM", "VMware", "Walmart",
    "GitHub", "Tableau", "HubSpot", "DocuSign", "Redfin", "Booking.com",
    "Shopify", "CrowdStrike", "Splunk",
]

# Product + Program title patterns (consulting intentionally excluded for now).
JOB_TITLES = ["product manager", "program manager", "technical program manager"]

# Per-company cap to bound credit spend (1 credit/job). 15 cos x 10 = 150 credits.
PER_COMPANY_CAP = 10


def _map_job(j: dict, company: str) -> dict | None:
    """Map a TheirStack job to our jobs-table row shape."""
    title = j.get("job_title") or ""
    url = j.get("url") or j.get("final_url") or ""
    if not title or not url:
        return None
    jid = j.get("id")
    return {
        "greenhouse_id": f"theirstack_{jid}" if jid else f"theirstack_{abs(hash(url))}",
        "company": company,
        "title": title,
        "location": j.get("location") or j.get("short_location") or "",
        "department": "",
        "url": url,
        "description": (j.get("description") or "")[:10000],
        "updated_at": j.get("date_posted") or "",
        "first_published": j.get("date_posted") or "",
        "employment_type": "",
        "salary_range": j.get("salary_string") or "",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_company_jobs(company: str, token: str, max_age_days: int = 7,
                             cap: int = PER_COMPANY_CAP,
                             discovered_max_age_days: int | None = None) -> list[dict]:
    """Fetch recent US Product/Program jobs for one company from TheirStack.

    discovered_max_age_days: if set, only return jobs TheirStack *discovered*
    that recently — keeps repeat 'Fetch new jobs' clicks cheap (1 credit/job,
    and we only pay for genuinely-new postings)."""
    payload = {
        "company_name_case_insensitive_or": [company],
        "job_title_or": JOB_TITLES,
        "job_country_code_or": ["US"],
        "posted_at_max_age_days": max_age_days,
        "limit": cap,
        "include_total_results": False,
    }
    if discovered_max_age_days is not None:
        payload["discovered_at_max_age_days"] = discovered_max_age_days
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(API_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"TheirStack {resp.status_code}: {resp.text[:200]}")
        data = resp.json().get("data", [])
    rows = [_map_job(j, company) for j in data]
    return [r for r in rows if r]


async def run_theirstack_fill(companies: list[str] | None = None,
                              max_age_days: int = 7,
                              discovered_max_age_days: int | None = None,
                              cap: int = PER_COMPANY_CAP) -> dict:
    """Fetch + upsert gap-company jobs. Returns a summary. Credit cost ≈ total
    jobs returned (so pass discovered_max_age_days on recurring runs to stay
    cheap)."""
    from app import database as db

    settings = get_settings()
    token = settings.theirstack_api_key
    if not token:
        return {"success": False, "error": "THEIRSTACK_API_KEY not set"}

    targets = companies or GAP_COMPANIES
    total = 0
    per_company = {}
    errors = []
    for company in targets:
        try:
            rows = await fetch_company_jobs(
                company, token, max_age_days=max_age_days, cap=cap,
                discovered_max_age_days=discovered_max_age_days,
            )
            if rows:
                await db.upsert_jobs(rows)
            per_company[company] = len(rows)
            total += len(rows)
            log.info(f"TheirStack {company}: {len(rows)} jobs")
        except Exception as e:
            errors.append(f"{company}: {e}")
            log.error(f"TheirStack fill error {company}: {e}")

    return {
        "success": True,
        "companies": len(targets),
        "jobs_upserted": total,
        "credits_spent_est": total,
        "per_company": per_company,
        "errors": errors,
    }
