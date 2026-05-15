"""JobPilot — Unified multi-ATS job scraper.

Scrapes jobs from:
  - Greenhouse (public JSON API)
  - Lever (public JSON API)
  - Ashby (public JSON API)
  - SmartRecruiters (public JSON API)
  - Workday (hidden JSON API)
  - Workable (public widget API)

All scrapers use httpx (async HTTP) — no browser needed for API-based scraping.
"""

import asyncio
import json
import re
import ssl
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Callable

import httpx

# ── Configuration ────────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "company_config.json"
SLUGS_FILE = Path(__file__).parent.parent / "company_slugs.txt"

ROLE_FILTERS = {
    "pm": [
        r"\bproduct\s+manager\b", r"\btechnical\s+product\s+manager\b",
        r"\bassociate\s+product\s+manager\b", r"\bsenior\s+product\s+manager\b",
        r"\bstaff\s+product\s+manager\b", r"\bgroup\s+product\s+manager\b",
        r"\bprincipal\s+product\s+manager\b", r"\bdirector.*product\s+manage",
        r"\bvp.*product\b", r"\bhead\s+of\s+product\b",
        r"\bproduct\s+lead\b", r"\bproduct\s+owner\b",
    ],
    "product": [
        r"^product\b", r"\bproduct$", r"\bproduct\s+analyst\b",
        r"\bproduct\s+strategy\b", r"\bproduct\s+ops\b",
        r"\bproduct\s+marketing\b",
    ],
    "tpm": [
        r"\btechnical\s+program\s+manager\b", r"\bprogram\s+manager\b",
        r"\btpm\b", r"\bagile\s+program\s+manager\b",
    ],
    "ux": [
        r"\bux\s+designer\b", r"\bux\s+design\b", r"\bux\s+researcher\b",
        r"\bux\s+research\b", r"\buser\s+experience\b",
        r"\bproduct\s+designer\b", r"\bux/ui\b", r"\bui/ux\b",
    ],
    "swe": [
        r"\bsoftware\s+development\s+engineer\b", r"\bsde\b", r"\bswe\b",
        r"\bsoftware\s+engineer\b", r"\bfrontend\s+engineer\b",
        r"\bbackend\s+engineer\b", r"\bfull[\s\-]?stack\s+engineer\b",
        r"\bplatform\s+engineer\b",
    ],
    "presales": [
        r"\bpre[\-\s]?sales\b", r"\bsolutions\s+engineer\b",
        r"\bsolutions\s+consultant\b", r"\bsales\s+engineer\b",
        r"\bproduct\s+consultant\b", r"\bsolutions\s+architect\b",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def load_greenhouse_slugs() -> list[str]:
    """Legacy: load from company_slugs.txt for backward compatibility."""
    if SLUGS_FILE.exists():
        return [l.strip() for l in SLUGS_FILE.read_text().splitlines() if l.strip()]
    return []


def compile_role_patterns(role_keys: list[str] | None = None) -> list[re.Pattern]:
    patterns = []
    if role_keys:
        for key in role_keys:
            patterns.extend(ROLE_FILTERS.get(key, []))
    else:
        for group in ROLE_FILTERS.values():
            patterns.extend(group)
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def matches_title(title: str, compiled: list[re.Pattern]) -> bool:
    return any(p.search(title) for p in compiled)


def strip_html(html: str) -> str:
    if not html:
        return ""
    text = unescape(html)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_recent(ts: str, cutoff: datetime) -> bool:
    """Check if a timestamp string is more recent than the cutoff."""
    if not ts:
        return True  # If no timestamp, include it
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except (ValueError, TypeError):
        return True  # Can't parse → include


def s(v) -> str:
    """Coerce any value to string for SQLite safety."""
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


# ── US-only location filter ─────────────────────────────────────────────────

US_STATES_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_US_PAT = re.compile(
    r"\b(?:united\s+states|usa|u\.s\.a\.?|u\.s\.)\b", re.IGNORECASE
)
_STATE_NAMES_PAT = re.compile(
    r"\b(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|"
    r"kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    r"mississippi|missouri|montana|nebraska|nevada|new\s+hampshire|"
    r"new\s+jersey|new\s+mexico|new\s+york|north\s+carolina|north\s+dakota|"
    r"ohio|oklahoma|oregon|pennsylvania|rhode\s+island|south\s+carolina|"
    r"south\s+dakota|tennessee|texas|utah|vermont|virginia|washington|"
    r"west\s+virginia|wisconsin|wyoming|district\s+of\s+columbia)\b",
    re.IGNORECASE,
)
_FOREIGN_PAT = re.compile(
    r"\b(?:canada|uk|united\s+kingdom|india|germany|france|japan|australia|"
    r"singapore|ireland|netherlands|brazil|mexico|china|hong\s+kong|taiwan|"
    r"south\s+korea|israel|sweden|switzerland|spain|italy|poland|czech|"
    r"austria|belgium|denmark|norway|finland|portugal|london|toronto|"
    r"vancouver|berlin|munich|paris|dublin|amsterdam|tokyo|sydney|"
    r"melbourne|bangalore|hyderabad|tel\s+aviv|stockholm|zurich|madrid|"
    r"warsaw|prague|vienna|brussels|copenhagen|oslo|helsinki|lisbon|"
    r"mumbai|pune|delhi|chennai|gurgaon|noida|ontario|british\s+columbia|"
    r"quebec|alberta|manila|bangkok|jakarta|buenos\s+aires|bogot[aá]|"
    r"s[aã]o\s+paulo|shanghai|beijing|shenzhen)\b",
    re.IGNORECASE,
)


def is_us_location(location: str) -> bool:
    """Check if a location string appears to be in the United States.

    Returns True for US locations, Remote (without foreign qualifier),
    and unknown/empty locations (benefit of the doubt).
    """
    if not location or not location.strip():
        return True  # Unknown → include
    loc = location.strip()
    if _US_PAT.search(loc):
        return True
    if _STATE_NAMES_PAT.search(loc):
        return True
    # Check for 2-letter state abbreviations in comma/pipe-separated parts
    parts = [p.strip() for p in loc.replace("|", ",").split(",")]
    for part in parts:
        if part.upper() in US_STATES_ABBR:
            return True
    # "Remote" without a foreign country → include
    if re.search(r"\bremote\b", loc, re.IGNORECASE) and not _FOREIGN_PAT.search(loc):
        return True
    # Explicitly foreign → exclude
    if _FOREIGN_PAT.search(loc):
        return False
    return True  # Can't determine → include


# ── Greenhouse Scraper ───────────────────────────────────────────────────────

def flatten_greenhouse(job: dict, company: str) -> dict:
    loc = job.get("location", {})
    location = loc.get("name", "") if isinstance(loc, dict) else str(loc or "")
    departments = job.get("departments") or []
    metadata = {m.get("name", ""): m.get("value") for m in (job.get("metadata") or [])}
    return {
        "greenhouse_id": s(job.get("id", "")),
        "company": company,
        "title": job.get("title", ""),
        "location": location,
        "department": ", ".join(d.get("name", "") for d in departments),
        "url": job.get("absolute_url", ""),
        "description": strip_html(job.get("content", "")),
        "updated_at": job.get("updated_at", ""),
        "first_published": job.get("first_published", ""),
        "employment_type": s(metadata.get("Employment Type", "")),
        "salary_range": s(metadata.get("Salary Range", metadata.get("Compensation Range", ""))),
    }


async def scrape_greenhouse(
    client: httpx.AsyncClient,
    company: str,
    slug: str,
    compiled: list[re.Pattern],
    cutoff: datetime,
    role_keys: list[str] | None,
) -> list[dict]:
    """Scrape one Greenhouse board via their public JSON API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            ts = job.get("updated_at", "")
            if role_keys is not None and not matches_title(title, compiled):
                continue
            if not is_recent(ts, cutoff):
                continue
            jobs.append(flatten_greenhouse(job, company))
        return jobs
    except Exception:
        return []


# ── Lever Scraper ────────────────────────────────────────────────────────────

def flatten_lever(job: dict, company: str) -> dict:
    categories = job.get("categories", {})
    return {
        "greenhouse_id": s(job.get("id", "")),
        "company": company,
        "title": job.get("text", ""),
        "location": categories.get("location", ""),
        "department": categories.get("department", ""),
        "url": job.get("hostedUrl", job.get("applyUrl", "")),
        "description": strip_html(job.get("descriptionPlain", job.get("description", ""))),
        "updated_at": "",
        "first_published": datetime.fromtimestamp(
            job.get("createdAt", 0) / 1000, tz=timezone.utc
        ).isoformat() if job.get("createdAt") else "",
        "employment_type": categories.get("commitment", ""),
        "salary_range": "",
    }


async def scrape_lever(
    client: httpx.AsyncClient,
    company: str,
    slug: str,
    compiled: list[re.Pattern],
    cutoff: datetime,
    role_keys: list[str] | None,
) -> list[dict]:
    """Scrape one Lever board via their public JSON API."""
    url = f"https://api.lever.co/v0/postings/{slug}"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        postings = resp.json()
        if not isinstance(postings, list):
            return []
        jobs = []
        for job in postings:
            title = job.get("text", "")
            # Lever uses createdAt (epoch ms)
            created = job.get("createdAt", 0)
            if created:
                ts = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
            else:
                ts = ""
            if role_keys is not None and not matches_title(title, compiled):
                continue
            if not is_recent(ts, cutoff):
                continue
            jobs.append(flatten_lever(job, company))
        return jobs
    except Exception:
        return []


# ── Ashby Scraper ────────────────────────────────────────────────────────────

def flatten_ashby(job: dict, company: str) -> dict:
    return {
        "greenhouse_id": s(job.get("id", "")),
        "company": company,
        "title": job.get("title", ""),
        "location": job.get("location", ""),
        "department": job.get("department", job.get("departmentName", "")),
        "url": f"https://jobs.ashbyhq.com/{company}/{job.get('id', '')}",
        "description": strip_html(job.get("descriptionHtml", job.get("descriptionPlain", ""))),
        "updated_at": job.get("updatedAt", ""),
        "first_published": job.get("publishedAt", ""),
        "employment_type": job.get("employmentType", ""),
        "salary_range": "",
    }


async def scrape_ashby(
    client: httpx.AsyncClient,
    company: str,
    slug: str,
    compiled: list[re.Pattern],
    cutoff: datetime,
    role_keys: list[str] | None,
) -> list[dict]:
    """Scrape one Ashby board via their public JSON API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            ts = job.get("updatedAt", job.get("publishedAt", ""))
            if role_keys is not None and not matches_title(title, compiled):
                continue
            if not is_recent(ts, cutoff):
                continue
            jobs.append(flatten_ashby(job, company))
        return jobs
    except Exception:
        return []


# ── SmartRecruiters Scraper ──────────────────────────────────────────────────

def flatten_smartrecruiters(job: dict, company: str) -> dict:
    loc = job.get("location", {})
    location_parts = [loc.get("city", ""), loc.get("region", ""), loc.get("country", "")]
    location = ", ".join(p for p in location_parts if p)
    return {
        "greenhouse_id": s(job.get("id", job.get("uuid", ""))),
        "company": company,
        "title": job.get("name", ""),
        "location": location,
        "department": job.get("department", {}).get("label", "") if isinstance(job.get("department"), dict) else "",
        "url": job.get("ref", job.get("applyUrl", "")),
        "description": "",  # SR listing API doesn't include description
        "updated_at": job.get("releasedDate", ""),
        "first_published": job.get("releasedDate", ""),
        "employment_type": job.get("typeOfEmployment", {}).get("label", "") if isinstance(job.get("typeOfEmployment"), dict) else "",
        "salary_range": "",
    }


async def scrape_smartrecruiters(
    client: httpx.AsyncClient,
    company: str,
    slug: str,
    compiled: list[re.Pattern],
    cutoff: datetime,
    role_keys: list[str] | None,
) -> list[dict]:
    """Scrape one SmartRecruiters board via their public API."""
    all_jobs = []
    offset = 0
    limit = 100

    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?offset={offset}&limit={limit}"
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            postings = data.get("content", [])
            if not postings:
                break

            for job in postings:
                title = job.get("name", "")
                ts = job.get("releasedDate", "")
                if role_keys is not None and not matches_title(title, compiled):
                    continue
                if not is_recent(ts, cutoff):
                    continue
                all_jobs.append(flatten_smartrecruiters(job, company))

            total = data.get("totalFound", 0)
            offset += limit
            if offset >= total:
                break
        except Exception:
            break

    return all_jobs


# ── Workday Scraper ──────────────────────────────────────────────────────────

def flatten_workday(job: dict, company: str, base_url: str) -> dict:
    external_path = job.get("externalPath", "")
    url = f"https://{base_url}{external_path}" if external_path else ""
    posted = job.get("postedOn", "")
    # Workday uses relative dates like "Posted 2 Days Ago" — normalize
    location_parts = []
    for loc in (job.get("locationsText", "") or "").split("|"):
        loc = loc.strip()
        if loc:
            location_parts.append(loc)

    return {
        "greenhouse_id": s(job.get("bulletFields", [""])[0] if job.get("bulletFields") else ""),
        "company": company,
        "title": job.get("title", ""),
        "location": " | ".join(location_parts),
        "department": "",
        "url": url,
        "description": "",  # Workday list API doesn't include descriptions
        "updated_at": "",
        "first_published": posted,
        "employment_type": job.get("timeType", ""),
        "salary_range": "",
    }


async def scrape_workday(
    client: httpx.AsyncClient,
    company: str,
    config: dict,
    compiled: list[re.Pattern],
    cutoff: datetime,
    role_keys: list[str] | None,
) -> list[dict]:
    """Scrape one Workday board via their hidden JSON API.

    Endpoint: https://{host}/wday/cxs/{company}/{board}/jobs
    Method: POST with JSON body {"limit": N, "offset": 0}
    Key: Must send Origin + Referer headers or you get 406/422.
    """
    host = config["host"]
    wd_company = config["company"]
    board = config["board"]
    url = f"https://{host}/wday/cxs/{wd_company}/{board}/jobs"

    # Workday requires browser-like Origin/Referer or it blocks with 406/422
    wd_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/{board}",
    }

    all_jobs = []
    offset = 0
    limit = 20  # Workday max per request

    while True:
        payload = {"limit": limit, "offset": offset, "appliedFacets": {}, "searchText": ""}
        try:
            resp = await client.post(url, json=payload, headers=wd_headers, timeout=20)
            if resp.status_code not in (200, 201):
                break
            data = resp.json()
            postings = data.get("jobPostings", [])
            if not postings:
                break

            for job in postings:
                title = job.get("title", "")
                if role_keys is not None and not matches_title(title, compiled):
                    continue
                # Workday doesn't give ISO dates in list — include if title matches
                all_jobs.append(flatten_workday(job, company, host))

            total = data.get("total", 0)
            offset += limit
            if offset >= total or offset >= 200:  # Cap at 200 to avoid rate limits
                break
        except Exception:
            break

    return all_jobs


# ── Workable Scraper ─────────────────────────────────────────────────────────

def flatten_workable(job: dict, company: str) -> dict:
    return {
        "greenhouse_id": s(job.get("id", job.get("shortcode", ""))),
        "company": company,
        "title": job.get("title", ""),
        "location": f"{job.get('city', '')} {job.get('country', '')}".strip(),
        "department": job.get("department", ""),
        "url": job.get("url", job.get("application_url", "")),
        "description": strip_html(job.get("description", "")),
        "updated_at": job.get("published_on", ""),
        "first_published": job.get("published_on", ""),
        "employment_type": job.get("employment_type", ""),
        "salary_range": "",
    }


async def scrape_workable(
    client: httpx.AsyncClient,
    company: str,
    slug: str,
    compiled: list[re.Pattern],
    cutoff: datetime,
    role_keys: list[str] | None,
) -> list[dict]:
    """Scrape one Workable board via their widget API."""
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        jobs = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            ts = job.get("published_on", "")
            if role_keys is not None and not matches_title(title, compiled):
                continue
            if not is_recent(ts, cutoff):
                continue
            jobs.append(flatten_workable(job, company))
        return jobs
    except Exception:
        return []


# ── Unified Scraper Entry Point ──────────────────────────────────────────────

async def scrape_jobs(
    companies: list[str] | None = None,
    role_keys: list[str] | None = None,
    hours: int = 168,
    concurrency: int = 20,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Scrape all configured ATS platforms. Returns flat list of job dicts.

    Args:
        companies: Optional list of company names to scrape.
                   If None, scrape all companies in company_config.json.
        role_keys: Filter by role category ('pm', 'swe', 'ux', etc.).
                   If None, match all roles in ROLE_FILTERS.
        hours: Only include jobs updated within this many hours.
        concurrency: Max concurrent HTTP requests.
        progress_callback: Called with (done, total) as scraping progresses.
    """
    config = load_config()
    compiled = compile_role_patterns(role_keys)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    sem = asyncio.Semaphore(concurrency)

    # Build task list from all ATS platforms
    tasks = []
    task_labels = []

    # Greenhouse — also fall back to company_slugs.txt for legacy support
    gh_map = config.get("greenhouse", {})
    if companies:
        gh_companies = {c: gh_map[c] for c in companies if c in gh_map}
    else:
        gh_companies = dict(gh_map)
        # Add any slugs from the legacy file not already in config
        for slug in load_greenhouse_slugs():
            if slug not in gh_companies:
                gh_companies[slug] = slug
    for company, slug in gh_companies.items():
        task_labels.append(f"greenhouse/{company}")

    # Lever
    lever_map = config.get("lever", {})
    if companies:
        lever_companies = {c: lever_map[c] for c in companies if c in lever_map}
    else:
        lever_companies = dict(lever_map)
    for company, slug in lever_companies.items():
        task_labels.append(f"lever/{company}")

    # Ashby
    ashby_map = config.get("ashby", {})
    if companies:
        ashby_companies = {c: ashby_map[c] for c in companies if c in ashby_map}
    else:
        ashby_companies = dict(ashby_map)
    for company, slug in ashby_companies.items():
        task_labels.append(f"ashby/{company}")

    # SmartRecruiters
    sr_map = config.get("smartrecruiters", {})
    if companies:
        sr_companies = {c: sr_map[c] for c in companies if c in sr_map}
    else:
        sr_companies = dict(sr_map)
    for company, slug in sr_companies.items():
        task_labels.append(f"smartrecruiters/{company}")

    # Workday
    wd_map = config.get("workday", {})
    if companies:
        wd_companies = {c: wd_map[c] for c in companies if c in wd_map}
    else:
        wd_companies = dict(wd_map)
    for company in wd_companies:
        task_labels.append(f"workday/{company}")

    # Workable
    wa_map = config.get("workable", {})
    if companies:
        wa_companies = {c: wa_map[c] for c in companies if c in wa_map}
    else:
        wa_companies = dict(wa_map)
    for company, slug in wa_companies.items():
        task_labels.append(f"workable/{company}")

    total_tasks = len(task_labels)
    completed = 0
    all_jobs = []

    async def run_with_sem(coro):
        nonlocal completed
        async with sem:
            result = await coro
            completed += 1
            if progress_callback:
                progress_callback(completed, total_tasks)
            return result

    # Run all scrapers concurrently with shared httpx client
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(headers=HEADERS, verify=ssl_ctx, follow_redirects=True) as client:
        coros = []

        # Greenhouse tasks
        for company, slug in gh_companies.items():
            coros.append(run_with_sem(
                scrape_greenhouse(client, company, slug, compiled, cutoff, role_keys)
            ))

        # Lever tasks
        for company, slug in lever_companies.items():
            coros.append(run_with_sem(
                scrape_lever(client, company, slug, compiled, cutoff, role_keys)
            ))

        # Ashby tasks
        for company, slug in ashby_companies.items():
            coros.append(run_with_sem(
                scrape_ashby(client, company, slug, compiled, cutoff, role_keys)
            ))

        # SmartRecruiters tasks
        for company, slug in sr_companies.items():
            coros.append(run_with_sem(
                scrape_smartrecruiters(client, company, slug, compiled, cutoff, role_keys)
            ))

        # Workday tasks
        for company, wd_config in wd_companies.items():
            coros.append(run_with_sem(
                scrape_workday(client, company, wd_config, compiled, cutoff, role_keys)
            ))

        # Workable tasks
        for company, slug in wa_companies.items():
            coros.append(run_with_sem(
                scrape_workable(client, company, slug, compiled, cutoff, role_keys)
            ))

        # Run all concurrently
        results = await asyncio.gather(*coros, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_jobs.extend(result)

    # Filter to US-only locations and sort by recency
    us_jobs = [j for j in all_jobs if is_us_location(j.get("location", ""))]
    us_jobs.sort(key=lambda j: j.get("updated_at", j.get("first_published", "")), reverse=True)
    return us_jobs
