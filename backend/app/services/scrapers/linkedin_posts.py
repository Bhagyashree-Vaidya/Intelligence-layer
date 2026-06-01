"""LinkedIn hiring-post scraper — finds social signals before ATS saturation.

Uses Apify's LinkedIn Posts Scraper actor to find hiring-related posts.
These appear BEFORE formal job postings → higher response rate on outreach.

Flow: Apify scrape → raw posts → classify via AI → store in Supabase
"""

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.logger import log


# ── Apify Actor for LinkedIn post search ─────────────────────────────────

LINKEDIN_POSTS_ACTOR = "curious_coder/linkedin-post-search-scraper"

# Keywords that signal hiring intent in posts
HIRING_KEYWORDS = [
    "hiring", "we're hiring", "we are hiring", "join our team",
    "looking for", "open role", "open position", "head of product",
    "product manager", "PM role", "product lead", "senior PM",
    "staff PM", "group PM", "director of product", "VP product",
    "product analyst", "growth PM", "technical PM", "platform PM",
    "data PM", "API PM", "infra PM", "founding PM",
    "come work with", "DM me if interested", "know anyone",
    "building a team", "growing the team", "expanding our",
    "#hiring #productmanagement", "#hiring #productmanager",
]

# Build search queries from keyword groups
SEARCH_QUERIES = [
    '"hiring" "product manager"',
    '"we\'re hiring" "PM"',
    '"open role" "product"',
    '"looking for" "product manager"',
    '"join our team" "product"',
    '"head of product" "hiring"',
    '"founding PM"',
]


async def scrape_linkedin_posts(
    queries: list[str] | None = None,
    max_posts_per_query: int = 25,
    date_range: str = "past-24h",
) -> list[dict[str, Any]]:
    """Scrape LinkedIn for hiring-related posts via Apify.

    Args:
        queries: Search queries. Defaults to SEARCH_QUERIES.
        max_posts_per_query: Max posts to fetch per query.
        date_range: "past-24h", "past-week", "past-month"

    Returns:
        List of normalized post dicts ready for classification.
    """
    settings = get_settings()
    if not settings.apify_token:
        log.warning("APIFY_TOKEN not set — skipping LinkedIn post scrape")
        return []

    queries = queries or SEARCH_QUERIES
    all_posts: list[dict] = []

    async with httpx.AsyncClient(timeout=120) as client:
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
                log.info(f"LinkedIn posts: '{query}' → {len(posts)} results")
            except Exception as e:
                log.error(f"LinkedIn post scrape failed for '{query}': {e}")
                continue

    # Deduplicate by post URL
    seen_urls: set[str] = set()
    unique_posts: list[dict] = []
    for post in all_posts:
        url = post.get("url", "")
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
    date_range: str = "past-24h",
) -> list[dict]:
    """Run the Apify LinkedIn Posts actor and return normalized results."""
    run_url = f"https://api.apify.com/v2/acts/{LINKEDIN_POSTS_ACTOR}/run-sync-get-dataset-items"

    payload = {
        "searchQueries": [query],
        "maxResults": max_results,
        "datePosted": date_range,
        "sortBy": "date_posted",
    }

    resp = await client.post(
        run_url,
        json=payload,
        params={"token": token},
        timeout=120,
    )
    resp.raise_for_status()
    raw_items = resp.json()

    return [_normalize_post(item) for item in raw_items if isinstance(item, dict)]


def _normalize_post(raw: dict) -> dict:
    """Normalize Apify LinkedIn post data to our schema."""
    author = raw.get("author", {}) or {}

    return {
        "platform": "linkedin",
        "post_url": raw.get("url", raw.get("postUrl", "")),
        "content": raw.get("text", raw.get("description", "")),
        "author_name": author.get("name", raw.get("authorName", "")),
        "author_title": author.get("headline", raw.get("authorTitle", "")),
        "author_url": author.get("url", raw.get("authorProfileUrl", "")),
        "author_company": _extract_company(author),
        "likes": raw.get("numLikes", raw.get("likesCount", 0)),
        "comments": raw.get("numComments", raw.get("commentsCount", 0)),
        "reposts": raw.get("numReposts", raw.get("repostsCount", 0)),
        "posted_at": raw.get("postedAt", raw.get("date", "")),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_company(author: dict) -> str:
    """Try to extract company from author profile data."""
    headline = author.get("headline", "")
    # Common patterns: "VP Product at Stripe", "PM @ Google"
    for sep in [" at ", " @ ", " - "]:
        if sep in headline:
            return headline.split(sep)[-1].strip()
    return author.get("company", "")


def has_hiring_signal(text: str) -> bool:
    """Quick keyword check before expensive AI classification."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in HIRING_KEYWORDS)
