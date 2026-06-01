"""Auto-apply API routes — enable/disable, trigger, view logs, role config."""

from fastapi import APIRouter

from app import database as db
from app.services import auto_apply
from app.services.role_classifier import ROLE_LABELS, ROLE_RESUME_MAP, ROLE_PATTERNS
from app.logger import log

router = APIRouter(prefix="/api/auto-apply", tags=["auto-apply"])


@router.get("/settings")
async def get_settings():
    """Get current auto-apply configuration."""
    settings = await db.get_auto_apply_settings()
    return {"settings": settings}


@router.put("/settings")
async def update_settings(body: dict):
    """Update auto-apply settings.

    Body fields:
      - enabled: bool
      - min_score: int (0 = no score filter)
      - max_per_run: int
      - exclude_companies: str (comma-separated)
      - enabled_roles: str (comma-separated, e.g. "pm,tpm,product")
    """
    updated = await db.update_auto_apply_settings(body)
    log.info(
        f"Auto-apply settings updated: enabled={updated.get('enabled')}, "
        f"roles={updated.get('enabled_roles')}"
    )
    return {"settings": updated}


@router.get("/roles")
async def list_roles():
    """List all available role categories for auto-apply.

    Shows which roles exist, their labels, which resume tag they use,
    and which are currently enabled.
    """
    settings = await db.get_auto_apply_settings()
    enabled = set(
        r.strip() for r in (settings.get("enabled_roles") or "").split(",") if r.strip()
    )

    roles = []
    for key in ROLE_PATTERNS:
        roles.append({
            "key": key,
            "label": ROLE_LABELS.get(key, key),
            "resume_tag": ROLE_RESUME_MAP.get(key, key),
            "enabled": key in enabled,
            "pattern_count": len(ROLE_PATTERNS[key]),
        })

    return {"roles": roles, "enabled_roles": list(enabled)}


@router.post("/run")
async def trigger_run(body: dict | None = None):
    """Manually trigger an auto-apply run.

    Optional body:
      - dry_run: bool (default false) — preview what would be applied
      - max: int — override max applications for this run
    """
    body = body or {}
    dry_run = body.get("dry_run", False)
    max_apps = body.get("max", 50)

    settings = await db.get_auto_apply_settings()
    enabled_roles = [
        r.strip() for r in (settings.get("enabled_roles") or "pm,tpm,product").split(",")
        if r.strip()
    ]

    result = await auto_apply.run_auto_apply(
        min_score=settings.get("min_score", 0),
        max_applications=max_apps,
        exclude_companies=(settings.get("exclude_companies") or "").split(","),
        enabled_roles=enabled_roles,
        dry_run=dry_run,
    )
    return result


@router.post("/dry-run")
async def dry_run():
    """Preview which jobs would be auto-applied to (no submissions).

    Respects all filters: role, company exclusions, ATS support.
    """
    settings = await db.get_auto_apply_settings()
    enabled_roles = [
        r.strip() for r in (settings.get("enabled_roles") or "pm,tpm,product").split(",")
        if r.strip()
    ]

    result = await auto_apply.run_auto_apply(
        min_score=settings.get("min_score", 0),
        max_applications=100,
        exclude_companies=(settings.get("exclude_companies") or "").split(","),
        enabled_roles=enabled_roles,
        dry_run=True,
    )
    return result


@router.get("/log")
async def get_log(limit: int = 50):
    """Get recent auto-apply log entries."""
    entries = await db.get_auto_apply_log(limit=limit)
    return {"log": entries, "total": len(entries)}
