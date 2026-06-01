"""Signals worker — LinkedIn hiring post scan + classification.

Scheduled via arq cron (every 4 hours). Can also be triggered manually
via POST /api/signals/scan.
"""

from app.logger import log
from app.services.scrapers.linkedin_posts import scrape_linkedin_posts
from app.services.signals.classifier import classify_and_store


async def scan_linkedin_signals(ctx: dict) -> dict:
    """Full pipeline: scrape LinkedIn posts → classify → store.

    Returns:
        Summary dict with scrape + classification stats.
    """
    log.info("Starting LinkedIn signal scan...")

    # Step 1: Scrape LinkedIn for hiring-related posts
    posts = await scrape_linkedin_posts(
        max_posts_per_query=25,
        date_range="24h",
    )

    if not posts:
        log.info("No LinkedIn posts found in this scan")
        return {"scraped": 0, "classified": {}}

    log.info(f"Scraped {len(posts)} LinkedIn posts, starting classification...")

    # Step 2: Classify and store signals
    classification_stats = await classify_and_store(posts)

    result = {
        "scraped": len(posts),
        "classified": classification_stats,
    }

    log.info(f"Signal scan complete: {result}")
    return result
