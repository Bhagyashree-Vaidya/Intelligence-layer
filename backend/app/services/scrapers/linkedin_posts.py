"""LinkedIn hiring-post scraper — finds social signals before ATS saturation.

Uses Apify's harvestapi/linkedin-post-search actor (NO cookies, NO login needed).
Completely separate from the job scraper in apify_service.py.

Flow: Apify scrape → raw posts → classify via AI → store in Supabase
"""

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.logger import log


# ── Apify Actor for LinkedIn POST search (not job search) ─────────────
# This is SEPARATE from the job scraper (curious_coder~linkedin-jobs-scraper)
# in apify_service.py. That one stays untouched for job listings.

LINKEDIN_POSTS_ACTOR = "harvestapi~linkedin-post-search"

# Hashtag-driven hiring-post queries (user's ask: #hiring + #PM combos). These
# run BROAD (not restricted to target-company employees) because hiring posts
# come from recruiters/founders, not company staff. The US + PM gate downstream
# (is_likely_us + _contact_relevance) keeps results on-target (~80% US — hashtags
# like #hiringUS are used loosely worldwide, so a post-filter is essential).
SEARCH_QUERIES = [
    "#hiring #productmanager",
    "#hiring #PM product manager",
    "#productmanagement #hiring",
    "#hiringUS product manager",
    "#UShiring product manager",
    "#techhiring product manager",
    '#hiring "product manager" "United States"',
]

# US target companies — posts are scraped only from employees of these companies.
# This eliminates company-page spam and off-target roles at the source.
# NOTE: the actor caps `authorsCompanies` at 20 per run, so we batch into groups.
TARGET_COMPANIES = [
    "Google", "Microsoft", "Amazon", "Meta", "Apple", "Adobe", "Salesforce",
    "ServiceNow", "Amazon Web Services", "Databricks", "Snowflake", "NVIDIA",
    "Cisco", "VMware", "Palantir Technologies", "MongoDB", "Atlassian", "GitHub",
    "Capital One", "Intuit", "PayPal", "Visa", "Mastercard", "Oracle", "IBM",
    "Accenture", "Walmart Global Tech", "Expedia Group", "Stripe", "Airbnb",
    "OpenAI", "Zillow", "Redfin", "Tableau", "Qualtrics", "Docusign", "Netflix",
    "Uber", "Lyft", "DoorDash", "Shopify", "Twilio", "Elastic", "Workday", "SAP",
    "eBay", "Etsy", "Spotify", "Booking.com", "The Walt Disney Company", "LinkedIn",
    "TikTok", "Pinterest", "Snap Inc.", "Robinhood", "Coinbase", "Figma", "Asana",
    "Notion", "Dropbox", "Slack", "Zoom", "HubSpot", "Okta", "Cloudflare",
    "CrowdStrike", "Datadog", "Splunk", "Confluent",
]

_COMPANY_BATCH_SIZE = 20  # actor hard cap on authorsCompanies


def _company_batches() -> list[list[str]]:
    """Split target companies into batches within the actor's 20-company cap."""
    return [
        TARGET_COMPANIES[i:i + _COMPANY_BATCH_SIZE]
        for i in range(0, len(TARGET_COMPANIES), _COMPANY_BATCH_SIZE)
    ]

# Keywords that signal hiring intent in posts
HIRING_KEYWORDS = [
    "hiring", "we're hiring", "we are hiring", "join our team",
    "looking for", "open role", "open position", "head of product",
    "product manager", "PM role", "product lead", "senior PM",
    "staff PM", "group PM", "director of product", "VP product",
    "come work with", "DM me if interested", "know anyone",
    "building a team", "growing the team", "expanding our",
    "#hiring", "#productmanagement", "#productmanager",
    "founding PM", "first PM", "product owner",
]


async def scrape_linkedin_posts(
    queries: list[str] | None = None,
    max_posts_per_query: int = 25,
    date_range: str = "24h",
    use_company_filter: bool = False,
) -> list[dict[str, Any]]:
    """Scrape LinkedIn for hiring-related posts via Apify.

    Uses harvestapi/linkedin-post-search — NO cookies, NO login.
    Your LinkedIn account is never touched.

    Scrapes only posts authored by employees of TARGET_COMPANIES (batched
    within the actor's 20-company cap). This keeps results on-target and
    avoids company-page spam. Location/role are filtered downstream.

    Args:
        queries: Search queries. Defaults to SEARCH_QUERIES.
        max_posts_per_query: Max posts per (query × company-batch) run.
        date_range: "1h", "24h", "week", "month". Default 24h matches the
            scan cadence so we don't pay to re-scrape the same posts.

    Returns:
        List of normalized post dicts ready for classification.
    """
    settings = get_settings()
    if not settings.apify_token:
        log.warning("APIFY_TOKEN not set — skipping LinkedIn post scrape")
        return []

    queries = queries or SEARCH_QUERIES
    # Hashtag mode runs broad (one pass per query, no company filter). Company
    # mode (legacy) batches across target-company employees.
    batches = _company_batches() if use_company_filter else [None]
    all_posts: list[dict] = []

    async with httpx.AsyncClient(timeout=180) as client:
        for query in queries:
            for companies in batches:
                try:
                    posts = await _run_actor(
                        client=client,
                        token=settings.apify_token,
                        query=query,
                        max_results=max_posts_per_query,
                        date_range=date_range,
                        authors_companies=companies,
                    )
                    all_posts.extend(posts)
                    log.info(f"LinkedIn posts: '{query[:40]}' → {len(posts)} results")
                except Exception as e:
                    log.error(f"LinkedIn post scrape failed for '{query[:40]}': {e}")
                    continue

    # Deduplicate by post URL
    seen_urls: set[str] = set()
    unique_posts: list[dict] = []
    for post in all_posts:
        url = post.get("post_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_posts.append(post)

    log.info(
        f"LinkedIn post scrape complete: {len(unique_posts)} unique posts "
        f"from {len(queries)} queries × {len(batches)} company batches"
    )
    return unique_posts


async def _run_actor(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    max_results: int = 40,
    date_range: str = "24h",
    authors_companies: list[str] | None = None,
) -> list[dict]:
    """Run the Apify LinkedIn Posts actor and return normalized results.

    Actor: harvestapi/linkedin-post-search (pay-per-event)
    - No cookies needed
    - $0.002 per post
    - Uses async run → poll → fetch pattern (pay-per-event actors
      don't support run-sync-get-dataset-items)
    """
    import asyncio

    # Step 1: Start the run
    run_url = f"https://api.apify.com/v2/acts/{LINKEDIN_POSTS_ACTOR}/runs"
    payload: dict = {
        "searchQueries": [query],
        "maxPosts": max_results,
        "postedLimit": date_range,
        "sortBy": "date",  # newest first → fresh posts each scan, less re-scraping
    }
    if authors_companies:
        # Actor caps this at 20 — caller (_company_batches) guarantees that.
        payload["authorsCompanies"] = authors_companies[:20]

    resp = await client.post(
        run_url, json=payload, params={"token": token}, timeout=30,
    )
    if resp.status_code != 201:
        body = resp.text[:500]
        log.error(f"Apify run start failed ({resp.status_code}): {body}")
        raise httpx.HTTPStatusError(
            f"Apify {resp.status_code}: {body}",
            request=resp.request, response=resp,
        )
    run_data = resp.json().get("data", {})
    run_id = run_data.get("id")
    dataset_id = run_data.get("defaultDatasetId")

    if not run_id:
        log.error(f"Apify run failed to start for query: {query[:50]}")
        return []

    # Step 2: Poll until run finishes (max 3 minutes)
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    for _ in range(36):  # 36 × 5s = 3 minutes max
        await asyncio.sleep(5)
        status_resp = await client.get(
            status_url, params={"token": token}, timeout=15,
        )
        status = status_resp.json().get("data", {}).get("status", "")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        log.error(f"Apify run {run_id} ended with status: {status}")
        return []

    # Step 3: Fetch dataset items
    if not dataset_id:
        log.error(f"No dataset ID for run {run_id}")
        return []

    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    items_resp = await client.get(
        items_url, params={"token": token, "limit": max_results}, timeout=30,
    )
    items_resp.raise_for_status()
    raw_items = items_resp.json()

    return [_normalize_post(item) for item in raw_items if isinstance(item, dict)]


def _normalize_post(raw: dict) -> dict:
    """Normalize harvestapi/linkedin-post-search output to our schema."""
    author = raw.get("author", {}) or {}
    engagement = raw.get("engagement", {}) or {}
    posted_at = raw.get("postedAt", {}) or {}
    job = raw.get("job", {}) or {}
    article = raw.get("article", {}) or {}

    return {
        "platform": "linkedin",
        "post_url": raw.get("linkedinUrl", raw.get("url", "")),
        "content": raw.get("content", ""),
        "author_name": author.get("name", ""),
        "author_title": author.get("info", ""),
        "author_url": author.get("linkedinUrl", ""),
        "author_company": _extract_company(author),
        "author_type": author.get("type", ""),  # "profile" (person) vs "company"
        "likes": engagement.get("likes", 0),
        "comments": engagement.get("comments", 0),
        "reposts": engagement.get("shares", 0),
        "posted_at": posted_at.get("date", ""),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        # Extra data from harvestapi
        "job_title": job.get("title", ""),
        "job_url": job.get("linkedinUrl", ""),
        "job_location": job.get("location", ""),
        "job_company": job.get("subtitle", "").replace("Job by ", "").replace("Jobs by ", ""),
        # Linked job article (often carries the location, e.g. "...Edinburgh, UK")
        "article_title": article.get("title", ""),
        "article_link": article.get("link", ""),
    }


def _extract_company(author: dict) -> str:
    """Try to extract company from author profile data."""
    info = author.get("info", "")
    # Common patterns: "Director of PM @ Stripe", "PM at Google", "VP Product - Meta"
    for sep in [" at ", " @ ", " - "]:
        if sep in info:
            return info.split(sep)[-1].strip()
    return ""


def has_hiring_signal(text: str) -> bool:
    """Quick keyword check before expensive AI classification."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in HIRING_KEYWORDS)


# Countries/cities to reject — saves Claude API calls on non-US posts
_FOREIGN_LOCATIONS = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai",
    "london", "uk", "united kingdom", "manchester", "berlin", "germany", "munich",
    "paris", "france", "amsterdam", "netherlands", "dublin", "ireland",
    "singapore", "tokyo", "japan", "sydney", "australia", "melbourne",
    "toronto", "canada", "vancouver", "montreal",  # Canada OK if remote-US
    "dubai", "uae", "abu dhabi", "saudi", "qatar",
    "lagos", "nigeria", "kenya", "south africa", "johannesburg",
    "brazil", "são paulo", "mexico city", "buenos aires",
    "beijing", "shanghai", "shenzhen", "china",
]


# Locale fragments in job-board article links that signal a non-US role.
_FOREIGN_URL_HINTS = [
    "/es/", "/ja/", "/jp/", "/de/", "/fr/", "/in/jobs", "amazon.jobs/es",
    "en-gb", "en-in", "en-ca", "en-au", ".co.uk", ".co.jp", ".co.in",
    "/india", "/japan", "/canada", "/uk/", "/emea",
]

_US_TERMS = [
    "united states", " usa", "u.s.", " us ", " us,", " us-", "remote (us",
    "us remote", "us-based", "us applicants",
    "new york", "san francisco", "bay area", "seattle", "austin", "california",
    "texas", "washington", "boston", "chicago", "denver", "los angeles",
    "atlanta", "phoenix", "mclean", "virginia", " ca ", " ny ", " wa ", " tx ",
    "santa clara", "mountain view", "sunnyvale", "san jose", "menlo park",
]


def is_likely_us(post: dict) -> bool:
    """Check if a post is likely about a US-based role.

    Stricter than before: company-targeting still surfaces many non-US roles
    (these companies hire globally), so we now read the article title and the
    job-board link locale in addition to content. Returns False when foreign
    signals are present without any US signal.
    """
    content = (post.get("content", "") or "").lower()
    author_title = (post.get("author_title", "") or "").lower()
    job_location = (post.get("job_location", "") or "").lower()
    article_title = (post.get("article_title", "") or "").lower()
    article_link = (post.get("article_link", "") or "").lower()

    combined = f"{content} {author_title} {job_location} {article_title}"

    us_hits = sum(1 for t in _US_TERMS if t in combined)
    foreign_hits = sum(1 for loc in _FOREIGN_LOCATIONS if loc in combined)
    foreign_url = any(h in article_link for h in _FOREIGN_URL_HINTS)

    # Clear US signal wins
    if us_hits > 0:
        return True
    # Any foreign signal (text or URL locale) with no US signal → reject
    if foreign_hits > 0 or foreign_url:
        return False

    # No location signal at all → pass through (classifier/relevance gate decides)
    return True
