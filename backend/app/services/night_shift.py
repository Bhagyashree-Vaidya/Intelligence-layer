"""Night Shift — selection engine.

Picks eligible jobs and adds them to the review queue. It does NOT fill or
submit anything — that's the Chrome extension's job (step 4). This engine only
decides WHICH jobs Night Shift should work on tonight, applying every guardrail:

  1. Toggle must be ON (night_shift_settings.enabled). OFF → no-op.
  2. Tier-1 (Top 20) companies are NEVER selected (hard block).
  3. Only Tier-2 (companies 21-70) are eligible.
  4. Only enabled roles (pm/tpm/product by default).
  5. Skip jobs already applied to or already in the queue.
  6. Respect the nightly cap (max_per_night, default 20).
  7. One per company per run.

The actual submission is always human-reviewed (fill-and-park).
"""

import re
from pathlib import Path

from app.config import get_settings
from app.logger import log
from app.services.role_classifier import classify_role, get_resume_tag_for_role
from app.services.night_shift_config import night_shift_eligible, is_tier_1


def _company_key(name: str) -> str:
    """Canonical company key for the one-per-company guardrail.

    Company slugs in `jobs` are inconsistent — the same employer appears as
    'notion', 'Notion', and 'notion2' (duplicate ATS board configs). A plain
    lower() treats those as different companies and queues duplicate
    applications. Normalize: lowercase, strip non-alphanumerics, strip
    trailing digits ('notion2' → 'notion').
    """
    n = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return re.sub(r"\d+$", "", n)


async def select_for_night_shift(dry_run: bool = False) -> dict:
    """Select eligible jobs and queue them for Night Shift review.

    Args:
        dry_run: if True, return what WOULD be queued without writing.

    Returns a summary dict (counts + the selected items).
    """
    from app import database as db

    settings_ns = await db.get_night_shift_settings()

    # ── Guardrail 1: toggle ───────────────────────────────────────────────────
    if not settings_ns.get("enabled"):
        return {
            "success": True, "enabled": False, "queued": 0,
            "message": "Night Shift is OFF. Enable the toggle to run.",
        }

    cap = int(settings_ns.get("max_per_night", 20) or 20)
    min_fit = int(settings_ns.get("min_fit_score", 0) or 0)
    allowed_roles = set(
        r.strip() for r in (settings_ns.get("enabled_roles") or "pm,tpm,product").split(",")
        if r.strip()
    )

    # Profile sanity (needed later for filling, but check early).
    profile = await db.get_profile()
    if not profile.get("first_name") or not profile.get("email"):
        return {
            "success": False, "queued": 0,
            "error": "Profile incomplete — need first_name + email before Night Shift.",
        }

    resumes = await db.get_resumes()

    # Exclusion sets.
    applied_ids = await db.get_applied_job_ids()
    queued_ids = await db.get_queued_job_ids()
    exclude_ids = applied_ids | queued_ids

    # Pull a generous candidate pool (most get filtered by tier/role).
    candidates = await db.get_auto_apply_candidates(
        min_score=min_fit,
        exclude_ids=exclude_ids,
        limit=cap * 20,
    )

    selected: list[dict] = []
    # Seed with companies already open in the queue so re-runs can't queue a
    # second application to the same employer under a variant slug.
    seen_companies: set[str] = {
        _company_key(c) for c in await db.get_queued_companies()
    }
    blocked_tier1 = 0
    skipped_not_tier2 = 0
    skipped_role = 0

    for job in candidates:
        company = job.get("company") or ""
        title = job.get("title") or ""

        # ── Guardrail 2+3: tier ───────────────────────────────────────────────
        eligible, reason = night_shift_eligible(company)
        if not eligible:
            if reason == "tier_1_blocked":
                blocked_tier1 += 1
            else:
                skipped_not_tier2 += 1
            continue

        # ── Guardrail 4: role ─────────────────────────────────────────────────
        role = classify_role(title)
        if role is None or role not in allowed_roles:
            skipped_role += 1
            continue

        # ── Guardrail 7: one per company (normalized — 'notion2' == 'notion') ─
        ckey = _company_key(company)
        if ckey in seen_companies:
            continue

        # Pick a role-matched resume id (file handling happens in extension step).
        resume_id = _pick_resume_id(role, resumes)

        selected.append({
            "job_id": job["id"],
            "company": company,
            "title": title,
            "url": job.get("url", ""),
            "role": role,
            "resume_id": resume_id,
            "tier": "tier_2",
            "fit": job.get("ai_overall_fit", 0),
        })
        seen_companies.add(ckey)

        # ── Guardrail 6: nightly cap ──────────────────────────────────────────
        if len(selected) >= cap:
            break

    # Final safety net: assert NOTHING tier-1 slipped through.
    leaked = [s for s in selected if is_tier_1(s["company"])]
    if leaked:
        log.error(f"Night Shift ABORT: tier-1 leak detected: {[s['company'] for s in leaked]}")
        return {
            "success": False, "queued": 0,
            "error": "Safety abort: Tier-1 company in selection.",
            "leaked": [s["company"] for s in leaked],
        }

    if dry_run:
        return {
            "success": True, "enabled": True, "dry_run": True,
            "would_queue": len(selected),
            "blocked_tier1": blocked_tier1,
            "skipped_not_tier2": skipped_not_tier2,
            "skipped_wrong_role": skipped_role,
            "cap": cap,
            "selected": selected,
        }

    # Write to queue.
    queued = 0
    for item in selected:
        if await db.enqueue_night_shift(item):
            queued += 1

    await db.update_night_shift_settings({})  # bump updated_at
    log.info(f"Night Shift queued {queued} jobs (blocked {blocked_tier1} tier-1).")

    return {
        "success": True, "enabled": True, "dry_run": False,
        "queued": queued,
        "blocked_tier1": blocked_tier1,
        "skipped_not_tier2": skipped_not_tier2,
        "skipped_wrong_role": skipped_role,
        "cap": cap,
        "selected": selected,
    }


def _pick_resume_id(role: str, resumes: list[dict]) -> int | None:
    """Pick a role-matched resume id (or default). File resolution is the
    extension's concern; here we only record which resume to use.

    Only considers resumes with a storage_path — rows without one predate the
    Supabase Storage fix and their files were lost to the /tmp wipe, so
    pointing Night Shift at them would mean attaching a file that's gone.
    """
    usable = [r for r in resumes if r.get("storage_path")]
    if not usable:
        return None
    tag = get_resume_tag_for_role(role)
    for r in usable:
        tags = [t.strip().lower() for t in (r.get("role_tags") or "").split(",")]
        if tag in tags or role in tags:
            return r["id"]
    default = next((r for r in usable if r.get("is_default")), None)
    return default["id"] if default else usable[0]["id"]
