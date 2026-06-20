"""Link-health check — auto-removes dead job listings (404/closed).

Job boards close postings constantly (the listing 404s). This pings each job
URL and deletes the ones that are gone, so the dashboard never shows a dead
link. Applied jobs are NEVER deleted (preserve the funnel) even if the posting
closed. Runs as part of the manual "Fetch new jobs".
"""

import asyncio
import httpx

from app.logger import log

CONCURRENCY = 15
TIMEOUT = 12
# Status codes that mean the posting is gone.
DEAD_CODES = {404, 410}


async def _is_dead(client: httpx.AsyncClient, url: str) -> bool:
    """True if the URL is definitively gone. Conservative: only treat clear
    404/410 as dead; network errors / blocks are NOT treated as dead (avoid
    deleting good jobs on a transient hiccup)."""
    if not url:
        return False
    try:
        r = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        return r.status_code in DEAD_CODES
    except Exception:
        return False  # transient/blocked → keep the job


async def prune_dead_links(max_jobs: int = 1200) -> dict:
    """Check job URLs and delete the dead ones (except applied jobs)."""
    from app import database as db

    client_db = db.get_db()
    # Applied job_ids — never delete these.
    apps = client_db.table("applications").select("job_id").execute()
    applied = {a["job_id"] for a in (apps.data or []) if a.get("job_id")}

    rows = (
        client_db.table("jobs")
        .select("id, url")
        .order("scraped_at", desc=True)
        .limit(max_jobs)
        .execute()
    ).data or []

    checked = 0
    dead_ids: list[int] = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (JobPilot link-check)"},
    ) as client:
        async def check(row):
            nonlocal checked
            if row["id"] in applied:
                return
            async with sem:
                if await _is_dead(client, row.get("url", "")):
                    dead_ids.append(row["id"])
            checked += 1
        await asyncio.gather(*(check(r) for r in rows))

    # Delete dead jobs.
    for jid in dead_ids:
        try:
            client_db.table("jobs").delete().eq("id", jid).execute()
        except Exception as e:
            log.warning(f"link_health delete failed for {jid}: {e}")

    log.info(f"Link-health: checked {checked}, removed {len(dead_ids)} dead listings")
    return {"checked": checked, "removed": len(dead_ids)}
