"""Health check endpoint for Fly.io monitoring + service status."""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Basic health check — must respond fast for Fly.io probes."""
    return {"status": "ok", "service": "jobpilot-api"}


@router.post("/health/daily-email")
async def trigger_daily_health_email():
    """Manually run the daily pipeline-health check and email the summary now."""
    from app.workers import run_daily_health_email
    result = await run_daily_health_email(ctx={})
    return {"ok": True, **result}


@router.get("/health/detailed")
async def health_detailed():
    """Detailed status of all connected services."""
    s = get_settings()

    services = {
        "api": "ok",
        "supabase": "configured" if s.supabase_url else "missing",
        "openai": "configured" if s.openai_api_key else "missing",
        "claude": "configured" if s.claude_api else "missing",
        "redis": "unknown",
        "apify": "configured" if s.apify_token else "missing",
        "browserbase": "configured" if s.browserbase_api_key else "missing",
    }

    # Check Redis connectivity
    if s.redis_url:
        try:
            from app.services.queue import is_redis_available
            services["redis"] = "connected" if await is_redis_available() else "error"
        except Exception:
            services["redis"] = "error"
    else:
        services["redis"] = "missing"

    return {
        "status": "ok",
        "service": "jobpilot-api",
        "environment": s.environment,
        "services": services,
    }


@router.get("/health/infra")
async def infra_health():
    """Infrastructure billing/usage health — checks Supabase DB size,
    Apify credits, Redis, and email alert readiness."""
    import httpx
    from app import database as db

    s = get_settings()
    checks = {}
    warnings = []

    # 1. Supabase DB size (free tier = 500 MB)
    try:
        supa = db.get_db()
        resp = supa.rpc("exec_sql", {}).execute()  # fallback below
    except Exception:
        pass

    try:
        supa = db.get_db()
        # Use a simple count as proxy; real size needs pg_database_size
        job_count = supa.table("jobs").select("id", count="exact").execute()
        checks["supabase"] = {
            "status": "ok",
            "jobs_count": job_count.count or 0,
            "project": "lmkcwvuqdiicndfeenuc",
            "note": "Free tier: 500 MB DB, 1 GB file storage, 50k auth users",
        }
    except Exception as e:
        checks["supabase"] = {"status": "error", "error": str(e)}
        warnings.append("Supabase connection failed")

    # 2. Apify credits
    if s.apify_token:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.apify.com/v2/users/me/usage",
                    headers={"Authorization": f"Bearer {s.apify_token}"},
                )
                if resp.status_code == 200:
                    usage = resp.json().get("data", {})
                    checks["apify"] = {
                        "status": "ok",
                        "usage": usage,
                    }
                elif resp.status_code == 401:
                    checks["apify"] = {"status": "error", "error": "Token expired/invalid"}
                    warnings.append("Apify token is invalid or expired!")
                else:
                    # Try the /users/me endpoint instead
                    resp2 = await client.get(
                        "https://api.apify.com/v2/users/me",
                        headers={"Authorization": f"Bearer {s.apify_token}"},
                    )
                    if resp2.status_code == 200:
                        user = resp2.json().get("data", {})
                        plan = user.get("plan", {})
                        checks["apify"] = {
                            "status": "ok",
                            "username": user.get("username"),
                            "plan": plan.get("id", "unknown"),
                            "monthly_usd": plan.get("monthlyBasePriceUsd"),
                        }
                    else:
                        checks["apify"] = {"status": "warning", "http": resp.status_code}
        except Exception as e:
            checks["apify"] = {"status": "error", "error": str(e)}
            warnings.append(f"Cannot reach Apify API: {e}")
    else:
        checks["apify"] = {"status": "not_configured"}
        warnings.append("APIFY_TOKEN not set — LinkedIn scraping disabled")

    # 3. Redis (Upstash)
    if s.redis_url:
        try:
            from app.services.queue import is_redis_available
            ok = await is_redis_available()
            checks["redis"] = {
                "status": "ok" if ok else "error",
                "provider": "upstash" if "upstash" in s.redis_url else "unknown",
                "note": "Free tier: 10k commands/day" if "upstash" in s.redis_url else "",
            }
            if not ok:
                warnings.append("Redis is unreachable — cron jobs won't run!")
        except Exception as e:
            checks["redis"] = {"status": "error", "error": str(e)}
            warnings.append(f"Redis error: {e}")
    else:
        checks["redis"] = {"status": "not_configured"}
        warnings.append("REDIS_URL not set — background workers disabled")

    # 4. Email alerts
    checks["email_alerts"] = {
        "status": "ok" if s.smtp_password else "not_configured",
        "recipient": s.alert_email,
        "smtp_host": s.smtp_host,
    }
    if not s.smtp_password:
        warnings.append("SMTP_PASSWORD not set — email alerts disabled")

    # 5. Fly.io (self-report)
    checks["fly"] = {
        "status": "ok",
        "note": "shared-cpu-1x, 1 GB RAM, auto-suspend. Free tier: 3 shared VMs, 160 GB outbound",
    }

    return {
        "status": "warning" if warnings else "ok",
        "warnings": warnings,
        "checks": checks,
    }
