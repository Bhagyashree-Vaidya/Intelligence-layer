"""Signal classifier — AI-powered hiring intent detection.

Takes raw LinkedIn posts, classifies them for hiring signals,
and stores results in Supabase for the frontend dashboard.
"""

from datetime import datetime, timezone
from typing import Any

from app.database import get_db
from app.logger import log
from app.services.ai import orchestrator
from app.services.scrapers.linkedin_posts import has_hiring_signal, is_likely_us


# ── Classification pipeline ──────────────────────────────────────────────

async def classify_and_store(posts: list[dict]) -> dict[str, Any]:
    """Classify a batch of posts and store results.

    Returns summary stats: {processed, stored, skipped, errors}
    """
    stats = {"processed": 0, "stored": 0, "skipped": 0, "errors": 0}

    for post in posts:
        try:
            stats["processed"] += 1

            # Quick keyword pre-filter — skip posts with zero hiring keywords
            if not has_hiring_signal(post.get("content", "")):
                stats["skipped"] += 1
                continue

            # US location filter — skip clearly foreign posts (saves Claude API $$$)
            if not is_likely_us(post):
                stats["skipped"] += 1
                continue

            # Check if we already have this post
            if await _post_exists(post.get("post_url", "")):
                stats["skipped"] += 1
                continue

            # AI classification via orchestrator
            classification = await orchestrator.classify_signal(
                post_content=post.get("content", ""),
                author_info=f"{post.get('author_name', '')} — {post.get('author_title', '')}",
            )

            # Only store posts with meaningful hiring intent
            if classification.get("hiring_intent", 0) < 30:
                stats["skipped"] += 1
                continue

            # Store the classified signal
            await _store_signal(post, classification)
            stats["stored"] += 1

            # If high-confidence, also create/update contact
            if classification.get("hiring_intent", 0) >= 70:
                await _upsert_contact(post, classification)

        except Exception as e:
            log.error(f"Signal classification error: {e}")
            stats["errors"] += 1
            continue

    log.info(
        f"Signal classification complete: "
        f"{stats['stored']} stored, {stats['skipped']} skipped, "
        f"{stats['errors']} errors out of {stats['processed']} processed"
    )
    return stats


async def _post_exists(post_url: str) -> bool:
    """Check if we already classified this post."""
    if not post_url:
        return False
    db = get_db()
    resp = (
        db.table("linkedin_posts")
        .select("id")
        .eq("post_url", post_url)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


async def _store_signal(post: dict, classification: dict) -> None:
    """Insert classified signal into linkedin_posts table."""
    db = get_db()
    db.table("linkedin_posts").insert({
        "post_url": post.get("post_url", ""),
        "content": (post.get("content", "") or "")[:5000],
        "author_name": post.get("author_name", ""),
        "author_title": post.get("author_title", ""),
        "author_url": post.get("author_url", ""),
        "author_company": post.get("author_company", ""),
        "platform": post.get("platform", "linkedin"),
        "likes": post.get("likes", 0),
        "comments": post.get("comments", 0),
        "reposts": post.get("reposts", 0),
        "posted_at": post.get("posted_at") or None,
        "scraped_at": post.get("scraped_at", datetime.now(timezone.utc).isoformat()),
        # AI classification results
        "hiring_intent": classification.get("hiring_intent", 0),
        "role_mentioned": classification.get("role_mentioned", ""),
        "company_mentioned": classification.get("company_mentioned", ""),
        "seniority_level": classification.get("seniority_level", ""),
        "is_recruiter": classification.get("is_recruiter", False),
        "outreach_viability": classification.get("outreach_viability", 0),
        "urgency_score": classification.get("urgency_score", 0),
        "suggested_action": classification.get("suggested_action", "skip"),
        "ai_reason": classification.get("reason", ""),
    }).execute()


async def _upsert_contact(post: dict, classification: dict) -> None:
    """Create or update a contact from a high-intent hiring post."""
    db = get_db()
    author_url = post.get("author_url", "")
    if not author_url:
        return

    # Check if contact exists
    existing = (
        db.table("contacts")
        .select("id, interaction_count")
        .eq("linkedin_url", author_url)
        .limit(1)
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()

    if existing.data:
        # Update existing contact — bump interaction count
        contact = existing.data[0]
        db.table("contacts").update({
            "last_seen_at": now,
            "interaction_count": (contact.get("interaction_count", 0) or 0) + 1,
            "latest_post_url": post.get("post_url", ""),
            "latest_role_mentioned": classification.get("role_mentioned", ""),
        }).eq("id", contact["id"]).execute()
    else:
        # Create new contact
        db.table("contacts").insert({
            "name": post.get("author_name", ""),
            "title": post.get("author_title", ""),
            "company": post.get("author_company", "") or classification.get("company_mentioned", ""),
            "linkedin_url": author_url,
            "source": "linkedin_signal",
            "is_recruiter": classification.get("is_recruiter", False),
            "first_seen_at": now,
            "last_seen_at": now,
            "interaction_count": 1,
            "latest_post_url": post.get("post_url", ""),
            "latest_role_mentioned": classification.get("role_mentioned", ""),
            "outreach_status": "none",
        }).execute()


# ── Query helpers for API routes ─────────────────────────────────────────

async def get_signals(
    min_intent: int = 50,
    action: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Fetch classified signals from DB, sorted by hiring intent."""
    db = get_db()
    q = (
        db.table("linkedin_posts")
        .select("*", count="exact")
        .gte("hiring_intent", min_intent)
    )
    if action:
        q = q.eq("suggested_action", action)

    q = q.order("hiring_intent", desc=True).order("scraped_at", desc=True)
    q = q.range(offset, offset + limit - 1)

    resp = q.execute()
    total = resp.count if resp.count is not None else len(resp.data or [])
    return resp.data or [], total


async def get_contacts(
    limit: int = 50,
    offset: int = 0,
    recruiter_only: bool = False,
) -> tuple[list[dict], int]:
    """Fetch networking contacts, sorted by recency."""
    db = get_db()
    q = db.table("contacts").select("*", count="exact")
    if recruiter_only:
        q = q.eq("is_recruiter", True)

    q = q.order("last_seen_at", desc=True)
    q = q.range(offset, offset + limit - 1)

    resp = q.execute()
    total = resp.count if resp.count is not None else len(resp.data or [])
    return resp.data or [], total


async def get_signal_stats() -> dict:
    """Dashboard stats for the signals tab."""
    db = get_db()

    total = db.table("linkedin_posts").select("id", count="exact").execute()
    high_intent = (
        db.table("linkedin_posts")
        .select("id", count="exact")
        .gte("hiring_intent", 70)
        .execute()
    )
    actionable = (
        db.table("linkedin_posts")
        .select("id", count="exact")
        .in_("suggested_action", ["apply", "message", "connect"])
        .execute()
    )
    contacts_count = db.table("contacts").select("id", count="exact").execute()

    return {
        "total_signals": total.count or 0,
        "high_intent": high_intent.count or 0,
        "actionable": actionable.count or 0,
        "contacts": contacts_count.count or 0,
    }
