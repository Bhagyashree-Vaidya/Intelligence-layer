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

# Search queries targeting REAL people posting about hiring
# (not job board spam — those get filtered by the AI classifier)
# US-focused queries — LinkedIn scopes results by location terms in query
SEARCH_QUERIES = [
    '"we\'re hiring" "product manager" United States',
    '"join my team" product manager remote OR hybrid',
    '"looking for a PM" OR "looking for a product manager" US',
    '"open role" "product manager" United States OR remote',
    '"founding PM" OR "first PM" United States',
    '"head of product" "hiring" US OR remote',
    '"senior PM" OR "staff PM" "hiring" United States',
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
    date_range: str = "week",
) -> list[dict[str, Any]]:
    """Scrape LinkedIn for hiring-related posts via Apify.

    Uses harvestapi/linkedin-post-search — NO cookies, NO login.
    Your LinkedIn account is never touched.

    Args:
        queries: Search queries. Defaults to SEARCH_QUERIES.
        max_posts_per_query: Max posts to fetch per query.
        date_range: "1h", "24h", "week", "month"

    Returns:
        List of normalized post dicts ready for classification.
    """
    settings = get_settings()
    if not settings.apify_token:
        log.warning("APIFY_TOKEN not set — skipping LinkedIn post scrape")
        return []

    queries = queries or SEARCH_QUERIES
    all_posts: list[dict] = []

    async with httpx.AsyncClient(timeout=180) as client:
        for query in queries:
            try:
                posts = await _run_actor(
                    client=client,
                    token=settings.apify_token,
                    query=query,
                    max_results=max_posts_per_query,
                    date_range=date_range,
                )
                all_posts.extend(posts)
                log.info(f"LinkedIn posts: '{query[:50]}' → {len(posts)} results")
            except Exception as e:
                log.error(f"LinkedIn post scrape failed for '{query[:50]}': {e}")
                continue

    # Deduplicate by post URL
    seen_urls: set[str] = set()
    unique_posts: list[dict] = []
    for post in all_posts:
        url = post.get("post_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_posts.append(post)

    log.info(f"LinkedIn post scrape complete: {len(unique_posts)} unique posts from {len(queries)} queries")
    return unique_posts


async def _run_actor(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    max_results: int = 25,
    date_range: str = "week",
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
    payload = {
        "searchQueries": [query],
        "maxPosts": max_results,
        "postedLimit": date_range,
        "sortBy": "relevance",
    }

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

    return {
        "platform": "linkedin",
        "post_url": raw.get("linkedinUrl", raw.get("url", "")),
        "content": raw.get("content", ""),
        "author_name": author.get("name", ""),
        "author_title": author.get("info", ""),
        "author_url": author.get("linkedinUrl", ""),
        "author_company": _extract_company(author),
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


def is_likely_us(post: dict) -> bool:
    """Quick check if a post is likely about a US-based role.
    Returns True if US or unclear (let classifier decide).
    Returns False only if clearly foreign (saves Claude API call).
    """
    # Check job location if available
    job_location = (post.get("job_location", "") or "").lower()
    if job_location:
        # Explicit US indicators → pass
        us_terms = ["united states", "usa", "remote", "hybrid",
                     "new york", "san francisco", "seattle", "austin",
                     "california", "texas", "washington", "boston",
                     "chicago", "denver", "los angeles", "atlanta"]
        if any(t in job_location for t in us_terms):
            return True
        # Explicit foreign indicators → reject
        if any(loc in job_location for loc in _FOREIGN_LOCATIONS):
            return False

    # Check post content for foreign location signals
    content = (post.get("content", "") or "").lower()
    author_title = (post.get("author_title", "") or "").lower()
    combined = f"{content} {author_title} {job_location}"

    # If clearly mentions a foreign location and NOT US → skip
    foreign_hits = sum(1 for loc in _FOREIGN_LOCATIONS if loc in combined)
    us_hits = sum(1 for t in ["united states", "usa", "us ", " us,", "remote", "san francisco",
                                "new york", "seattle", "austin", "california"] if t in combined)

    if foreign_hits > 0 and us_hits == 0:
        return False

    # Default: pass through (let classifier decide)
    return True
