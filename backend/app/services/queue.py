"""Queue service — enqueue jobs into arq/Redis.

Thin wrapper so route handlers can dispatch background work
without importing arq internals directly.
"""

from arq.connections import ArqRedis, create_pool

from app.logger import log
from app.workers import get_redis_settings

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    """Get or create the arq Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = await create_pool(get_redis_settings())
    return _pool


async def enqueue_signal_scan() -> str | None:
    """Trigger a LinkedIn signal scan in the background."""
    try:
        pool = await get_pool()
        job = await pool.enqueue_job("run_signal_scan")
        log.info(f"Enqueued signal scan: {job.job_id}")
        return job.job_id
    except Exception as e:
        log.error(f"Failed to enqueue signal scan: {e}")
        return None


async def enqueue_enrich(job_ids: list[int] | None = None) -> str | None:
    """Trigger job enrichment in the background."""
    try:
        pool = await get_pool()
        job = await pool.enqueue_job("run_enrich_jobs", job_ids=job_ids)
        log.info(f"Enqueued enrichment: {job.job_id}")
        return job.job_id
    except Exception as e:
        log.error(f"Failed to enqueue enrichment: {e}")
        return None


async def enqueue_scoring(job_ids: list[int] | None = None) -> str | None:
    """Trigger job scoring in the background."""
    try:
        pool = await get_pool()
        job = await pool.enqueue_job("run_score_jobs", job_ids=job_ids)
        log.info(f"Enqueued scoring: {job.job_id}")
        return job.job_id
    except Exception as e:
        log.error(f"Failed to enqueue scoring: {e}")
        return None


async def is_redis_available() -> bool:
    """Check if Redis is reachable."""
    try:
        pool = await get_pool()
        await pool.ping()
        return True
    except Exception:
        return False
