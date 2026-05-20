"""JobPilot — Big Tech career page scrapers.

These companies use proprietary ATS systems that don't have public APIs.
We use Playwright to intercept their internal JSON endpoints.

Supports:
  - Apple (jobs.apple.com)
  - Meta (metacareers.com)
  - Google (careers.google.com)
  - Amazon (amazon.jobs)
  - Netflix (jobs.netflix.com — also on Lever for some roles)
  - Microsoft (careers.microsoft.com)

Strategy: Navigate to career search page → intercept XHR/fetch calls →
          parse the JSON response → no HTML scraping needed.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx

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


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


# ── Shared helpers ───────────────────────────────────────────────────────────

def strip_html(html: str) -> str:
    if not html:
        return ""
    from html import unescape
    text = unescape(html)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


ROLE_PATTERNS = [
    r"\bproduct\s+manager\b", r"\btechnical\s+product\s+manager\b",
    r"\bassociate\s+product\s+manager\b", r"\bprogram\s+manager\b",
    r"\btpm\b", r"\bux\s+designer\b", r"\bux\s+researcher\b",
    r"\bproduct\s+designer\b", r"\bsoftware\s+engineer\b",
    r"\bsolutions\s+engineer\b", r"\bsolutions\s+architect\b",
]
COMPILED_ROLES = [re.compile(p, re.IGNORECASE) for p in ROLE_PATTERNS]


def matches_role(title: str, role_keys: list[str] | None = None) -> bool:
    """Check if title matches any role filter. If role_keys is None, match all."""
    if role_keys is None:
        return True  # No filter = include all
    return any(p.search(title) for p in COMPILED_ROLES)


def unescape_js_string(s: str) -> str:
    """Unescape a JavaScript string literal to recover the original string.

    Handles: \\\" → \", \\\\ → \\, \\n → newline, \\t → tab, \\/ → /
    This is needed for Apple's SSR hydration data which embeds JSON inside
    JSON.parse("...escaped...").
    """
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            if c == '\\':
                result.append('\\')
            elif c == '"':
                result.append('"')
            elif c == 'n':
                result.append('\n')
            elif c == 'r':
                result.append('\r')
            elif c == 't':
                result.append('\t')
            elif c == '/':
                result.append('/')
            elif c == 'b':
                result.append('\b')
            elif c == 'f':
                result.append('\f')
            else:
                result.append('\\')
                result.append(c)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Amazon — amazon.jobs/en/search.json
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_amazon(
    client: httpx.AsyncClient,
    search_terms: list[str] | None = None,
    location: str = "United States",
    max_results: int = 100,
) -> list[dict]:
    """Scrape Amazon jobs via their hidden JSON search API.

    Endpoint: https://www.amazon.jobs/en/search.json
    Params: base_query, loc_query, offset, result_limit, sort, category[]
    """
    if not search_terms:
        search_terms = ["Product Manager", "Program Manager", "UX Designer", "Software Engineer"]

    all_jobs = []

    for query in search_terms:
        offset = 0
        while offset < max_results:
            params = {
                "base_query": query,
                "offset": offset,
                "result_limit": 25,
                "sort": "recent",
            }
            if location:
                params["loc_query"] = location

            try:
                resp = await client.get(
                    "https://www.amazon.jobs/en/search.json",
                    params=params,
                    timeout=15,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                hits = data.get("jobs", [])
                if not hits:
                    break

                for job in hits:
                    all_jobs.append({
                        "greenhouse_id": job.get("id_icims", job.get("id", "")),
                        "company": "amazon",
                        "title": job.get("title", ""),
                        "location": job.get("normalized_location", job.get("location", "")),
                        "department": job.get("job_category", ""),
                        "url": f"https://www.amazon.jobs{job.get('job_path', '')}",
                        "description": strip_html(job.get("description_short", "")),
                        "updated_at": job.get("posted_date", ""),
                        "first_published": job.get("posted_date", ""),
                        "employment_type": job.get("job_schedule_type", ""),
                        "salary_range": "",
                    })

                offset += 25
                if len(hits) < 25:
                    break
            except Exception:
                break

    # Deduplicate by job ID
    seen = set()
    unique = []
    for j in all_jobs:
        key = j["greenhouse_id"]
        if key not in seen:
            seen.add(key)
            unique.append(j)

    return unique


# ═══════════════════════════════════════════════════════════════════════════════
# Apple — jobs.apple.com (SSR hydration data extraction)
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_apple(
    client: httpx.AsyncClient,
    search_terms: list[str] | None = None,
    location: str = "united-states-USA",
    max_results: int = 100,
) -> list[dict]:
    """Scrape Apple jobs by extracting SSR hydration data from search pages.

    Apple embeds all search results in window.__staticRouterHydrationData.
    URL pattern: https://jobs.apple.com/en-us/search?search={query}&location={loc}&page={N}
    Returns 20 results per page.
    """
    if not search_terms:
        search_terms = ["Product Manager", "Program Manager", "UX Designer", "Software Engineer"]

    all_jobs = []
    seen_ids = set()

    for query in search_terms:
        page = 1
        while len(all_jobs) < max_results:
            try:
                params = {"search": query, "location": location, "page": page}
                resp = await client.get(
                    "https://jobs.apple.com/en-us/search",
                    params=params,
                    headers={**HEADERS, "Accept": "text/html"},
                    timeout=20,
                )
                if resp.status_code != 200:
                    break

                # Extract __staticRouterHydrationData from the page
                match = re.search(
                    r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);',
                    resp.text, re.DOTALL
                )
                if not match:
                    break

                data = json.loads(unescape_js_string(match.group(1)))
                search_data = data.get("loaderData", {}).get("search", {})
                results = search_data.get("searchResults", [])
                total = search_data.get("totalRecords", 0)

                if not results:
                    break

                for job in results:
                    pid = str(job.get("positionId", job.get("id", "")))
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    locations = job.get("locations", [])
                    loc_str = " | ".join(
                        loc.get("name", "") for loc in locations
                        if isinstance(loc, dict)
                    )
                    team = job.get("team", {})
                    team_name = team.get("teamName", "") if isinstance(team, dict) else ""

                    all_jobs.append({
                        "greenhouse_id": pid,
                        "company": "apple",
                        "title": job.get("postingTitle", ""),
                        "location": loc_str,
                        "department": team_name,
                        "url": f"https://jobs.apple.com/en-us/details/{pid}",
                        "description": "",  # Not available in list view
                        "updated_at": job.get("postingDate", ""),
                        "first_published": job.get("postingDate", ""),
                        "employment_type": job.get("type", ""),
                        "salary_range": "",
                    })

                page += 1
                if page * 20 >= total or page > 10:  # Cap at 10 pages (200 jobs) per query
                    break
            except Exception:
                break

    return all_jobs[:max_results]


# ═══════════════════════════════════════════════════════════════════════════════
# Google — careers.google.com API
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_google(
    client: httpx.AsyncClient,
    search_terms: list[str] | None = None,
    location: str = "",
    max_results: int = 100,
) -> list[dict]:
    """Scrape Google jobs via their careers API.

    Google's career site makes requests to:
      https://careers.google.com/api/v3/search/
    with query parameters.
    """
    if not search_terms:
        search_terms = ["Product Manager", "Program Manager", "UX"]

    all_jobs = []

    for query in search_terms:
        page_token = ""
        while len(all_jobs) < max_results:
            try:
                params = {
                    "q": query,
                    "page_size": 20,
                    "jlo": "en_US",
                }
                if location:
                    params["location"] = location
                if page_token:
                    params["page_token"] = page_token

                resp = await client.get(
                    "https://careers.google.com/api/v3/search/",
                    params=params,
                    timeout=15,
                )

                if resp.status_code != 200:
                    break

                data = resp.json()
                jobs = data.get("jobs", [])
                if not jobs:
                    break

                for job in jobs:
                    locations = job.get("locations", [])
                    loc_str = " | ".join(
                        loc.get("display", loc.get("name", "")) for loc in locations
                    ) if isinstance(locations, list) else str(locations)

                    job_id = job.get("id", "")
                    all_jobs.append({
                        "greenhouse_id": str(job_id),
                        "company": "google",
                        "title": job.get("title", ""),
                        "location": loc_str,
                        "department": job.get("categories", [""])[0] if job.get("categories") else "",
                        "url": f"https://www.google.com/about/careers/applications/jobs/results/{job_id}",
                        "description": strip_html(job.get("description", "")),
                        "updated_at": job.get("publish_date", ""),
                        "first_published": job.get("publish_date", ""),
                        "employment_type": "",
                        "salary_range": job.get("salary", ""),
                    })

                page_token = data.get("next_page_token", "")
                if not page_token:
                    break
            except Exception:
                break

    return all_jobs[:max_results]


# ═══════════════════════════════════════════════════════════════════════════════
# Meta — metacareers.com API
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_meta(
    client: httpx.AsyncClient,
    search_terms: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """Scrape Meta jobs via their careers API.

    Meta's career site uses a REST endpoint:
      https://www.metacareers.com/graphql
    But also has a simpler endpoint at:
      https://www.metacareers.com/jobs
    We'll use their search endpoint that returns JSON.
    """
    if not search_terms:
        search_terms = ["Product Manager", "Program Manager", "UX"]

    all_jobs = []

    for query in search_terms:
        try:
            # Meta's search API
            params = {
                "q": query,
                "page": 1,
                "results_per_page": 50,
                "sort_by_new": True,
            }

            resp = await client.get(
                "https://www.metacareers.com/search",
                params=params,
                headers={
                    **HEADERS,
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=15,
            )

            if resp.status_code != 200:
                continue

            # Try to extract JSON from the page (Meta embeds it in script tags)
            text = resp.text
            # Look for structured data in the page
            json_match = re.search(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                text, re.DOTALL
            )
            if json_match:
                try:
                    ld_data = json.loads(json_match.group(1))
                    if isinstance(ld_data, dict) and "itemListElement" in ld_data:
                        for item in ld_data["itemListElement"]:
                            job = item.get("item", item)
                            all_jobs.append({
                                "greenhouse_id": str(job.get("identifier", {}).get("value", "")),
                                "company": "meta",
                                "title": job.get("title", ""),
                                "location": job.get("jobLocation", {}).get("address", {}).get("addressLocality", "")
                                    if isinstance(job.get("jobLocation"), dict) else "",
                                "department": "",
                                "url": job.get("url", ""),
                                "description": strip_html(job.get("description", "")),
                                "updated_at": job.get("datePosted", ""),
                                "first_published": job.get("datePosted", ""),
                                "employment_type": job.get("employmentType", ""),
                                "salary_range": "",
                            })
                except json.JSONDecodeError:
                    pass

            # Also try to find embedded JSON state
            state_match = re.search(r'"jobData":\s*(\[.*?\])', text)
            if state_match:
                try:
                    job_data = json.loads(state_match.group(1))
                    for job in job_data:
                        all_jobs.append({
                            "greenhouse_id": str(job.get("id", "")),
                            "company": "meta",
                            "title": job.get("title", ""),
                            "location": job.get("locations", [""])[0] if job.get("locations") else "",
                            "department": job.get("sub_teams", [""])[0] if job.get("sub_teams") else "",
                            "url": f"https://www.metacareers.com/jobs/{job.get('id', '')}",
                            "description": "",
                            "updated_at": "",
                            "first_published": "",
                            "employment_type": "",
                            "salary_range": "",
                        })
                except json.JSONDecodeError:
                    pass

        except Exception:
            continue

    return all_jobs[:max_results]


# ═══════════════════════════════════════════════════════════════════════════════
# Microsoft — careers.microsoft.com API
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_microsoft(
    client: httpx.AsyncClient,
    search_terms: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """Scrape Microsoft jobs via their careers search API.

    Endpoint: https://gcsservices.careers.microsoft.com/search/api/v1/search
    """
    if not search_terms:
        search_terms = ["Product Manager", "Program Manager", "UX Designer"]

    all_jobs = []

    for query in search_terms:
        skip = 0
        while len(all_jobs) < max_results:
            try:
                params = {
                    "q": query,
                    "lc": "United States",
                    "l": "en_us",
                    "pg": skip // 20 + 1,
                    "pgSz": 20,
                    "o": "Recent",
                }

                resp = await client.get(
                    "https://gcsservices.careers.microsoft.com/search/api/v1/search",
                    params=params,
                    timeout=15,
                )

                if resp.status_code != 200:
                    break

                data = resp.json()
                results = data.get("operationResult", {}).get("result", {}).get("jobs", [])
                if not results:
                    break

                for job in results:
                    properties = job.get("properties", {}) if isinstance(job.get("properties"), dict) else {}
                    all_jobs.append({
                        "greenhouse_id": str(job.get("jobId", "")),
                        "company": "microsoft",
                        "title": job.get("title", ""),
                        "location": job.get("primaryLocation", properties.get("primaryLocation", "")),
                        "department": properties.get("discipline", properties.get("category", "")),
                        "url": f"https://jobs.careers.microsoft.com/global/en/job/{job.get('jobId', '')}",
                        "description": strip_html(properties.get("description", "")),
                        "updated_at": properties.get("dateCreated", ""),
                        "first_published": properties.get("dateCreated", ""),
                        "employment_type": properties.get("employmentType", ""),
                        "salary_range": "",
                    })

                skip += 20
                total = data.get("operationResult", {}).get("result", {}).get("totalJobs", 0)
                if skip >= total:
                    break
            except Exception:
                break

    return all_jobs[:max_results]


# ═══════════════════════════════════════════════════════════════════════════════
# Unified entry point for all Big Tech scrapers
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Netflix — Lever + Greenhouse
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_netflix(
    client: httpx.AsyncClient,
    search_terms: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """Netflix posts on multiple platforms. Try Lever first, then look for jobs."""
    # Netflix often uses their own portal or Lever
    all_jobs = []
    try:
        resp = await client.get(
            "https://explore.jobs.netflix.net/api/apply/v2/jobs",
            params={"domain": "netflix.com", "start": 0, "num": min(50, max_results), "query": search_terms[0] if search_terms else ""},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            positions = data.get("positions", [])
            for job in positions:
                all_jobs.append({
                    "greenhouse_id": str(job.get("id", "")),
                    "company": "netflix",
                    "title": job.get("name", job.get("text", "")),
                    "location": job.get("location", ""),
                    "department": job.get("department", ""),
                    "url": job.get("canonicalPositionUrl", job.get("url", "")),
                    "description": strip_html(job.get("description", "")),
                    "updated_at": "",
                    "first_published": "",
                    "employment_type": "",
                    "salary_range": "",
                })
    except Exception:
        pass

    return all_jobs[:max_results]


# ═══════════════════════════════════════════════════════════════════════════════
# Scrapers that work via httpx (no browser needed)
# ═══════════════════════════════════════════════════════════════════════════════

BIGTECH_SCRAPERS = {
    "amazon": scrape_amazon,
    "apple": scrape_apple,
    "netflix": scrape_netflix,
    # Google, Meta, Microsoft — need Playwright for session cookies.
}

# Scrapers that need Playwright (browser-level session)
BROWSER_ONLY_SCRAPERS = ["google", "meta", "microsoft"]


async def scrape_bigtech(
    companies: list[str] | None = None,
    search_terms: list[str] | None = None,
    max_per_company: int = 50,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Scrape all Big Tech career pages.

    Args:
        companies: List of company names to scrape (default: all).
        search_terms: Search queries to use (default: PM/TPM/UX/SWE).
        max_per_company: Max jobs per company.
        progress_callback: Called with (done, total).

    Returns:
        Flat list of job dicts.
    """
    import ssl
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    targets = companies or list(BIGTECH_SCRAPERS.keys())
    valid_targets = [c for c in targets if c in BIGTECH_SCRAPERS]
    total = len(valid_targets)
    all_jobs = []

    async with httpx.AsyncClient(headers=HEADERS, verify=ssl_ctx, follow_redirects=True) as client:
        for i, company in enumerate(valid_targets):
            scraper_fn = BIGTECH_SCRAPERS[company]
            try:
                jobs = await scraper_fn(
                    client,
                    search_terms=search_terms,
                    max_results=max_per_company,
                )
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"[BigTech] {company} scraper error: {e}")

            if progress_callback:
                progress_callback(i + 1, total)

    # Filter to US-only locations
    return [j for j in all_jobs if is_us_location(j.get("location", ""))]
