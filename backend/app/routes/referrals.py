"""Referral API routes — warm-intro targets for the Top 70 companies.

The Referral tab answers: "Who do I know (or could reach) at each of my 70
target companies, and what do I say?" It reads the contacts table, keeps only
people at Top-70 companies, ranks them by how useful they are for a warm intro,
and drafts outreach in the user's voice.

Discovery of NEW people (cookieless Apify people-search) is a separate step;
this route organizes + actions whoever is already in contacts.
"""

from fastapi import APIRouter, HTTPException

from app import database as db
from app.services.night_shift_config import is_tier_1, is_tier_2, _norm, TIER_1_COMPANIES, TIER_2_COMPANIES

router = APIRouter(prefix="/api/referrals", tags=["referrals"])

# Ranking: lower number = surface first. Matches the user's priority —
# hiring managers, alumni, team seniors first; recruiters/peers last.
_RANK = {
    "hiring_manager": 0,
    "alum": 1,
    "team_senior": 2,
    "referrer": 3,
    "recruiter": 4,
    "peer": 5,
    "": 6,
    "other": 6,
}


def _target_label(company: str) -> str | None:
    """Return the canonical Top-70 company name a contact belongs to, or None."""
    if is_tier_1(company):
        n = _norm(company)
        for canon, aliases in TIER_1_COMPANIES.items():
            if any(n == a or n.startswith(a) or a in n for a in aliases):
                return canon
    if is_tier_2(company):
        n = _norm(company)
        for canon in TIER_2_COMPANIES:
            if n.startswith(_norm(canon)) or _norm(canon) in n:
                return canon
    return None


@router.get("")
async def list_referrals():
    """All Top-70 contacts, grouped by company, ranked within each company."""
    client = db.get_db()
    resp = client.table("contacts").select("*").execute()
    rows = resp.data or []

    groups: dict[str, list[dict]] = {}
    for c in rows:
        label = _target_label(c.get("company") or "")
        if not label:
            continue
        c["target_company"] = label
        groups.setdefault(label, []).append(c)

    # Rank within each company, then order companies by how many warm contacts.
    out = []
    for company, people in groups.items():
        people.sort(key=lambda p: (_RANK.get(p.get("relationship_type", ""), 6),
                                   not p.get("is_relevant", False)))
        warm = sum(1 for p in people if p.get("relationship_type") in ("hiring_manager", "alum", "team_senior"))
        out.append({"company": company, "count": len(people), "warm": warm, "people": people})

    out.sort(key=lambda g: (-g["warm"], -g["count"], g["company"]))
    total_people = sum(g["count"] for g in out)
    return {"groups": out, "companies": len(out), "total_people": total_people}


@router.post("/discover")
async def discover_people(body: dict | None = None):
    """Run cookieless Apify people-discovery for the Top 70 (or a subset).

    Body (optional):
      - companies: list[str]  — limit to these companies (default: all 70)
    Cost: ~$0.001/result via fabri-lab/linkedin-public-search-lead-extractor.
    All 70 ≈ ~$3-5. Needs Apify credit; returns an error if the token has none.
    """
    from app.services.people_discovery import run_people_discovery
    body = body or {}
    companies = body.get("companies")
    result = await run_people_discovery(companies=companies)
    return result


@router.post("/{contact_id}/sent")
async def mark_sent(contact_id: int, body: dict | None = None):
    """Toggle whether outreach was sent to this contact (checkbox tracking)."""
    from datetime import datetime, timezone
    body = body or {}
    sent = bool(body.get("sent", True))
    client = db.get_db()
    update = {"outreach_status": "sent" if sent else "none"}
    if sent:
        update["outreach_sent_at"] = datetime.now(timezone.utc).isoformat()
    client.table("contacts").update(update).eq("id", contact_id).execute()
    return {"ok": True, "sent": sent}


@router.post("/{contact_id}/outreach")
async def referral_outreach(contact_id: int):
    """Draft a referral outreach message (user's voice) for one contact."""
    from app.services.ai import orchestrator

    client = db.get_db()
    resp = client.table("contacts").select("*").eq("id", contact_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Contact not found")
    c = resp.data[0]

    profile = await db.get_profile()
    user_summary = (
        f"{profile.get('first_name','')} {profile.get('last_name','')}, "
        f"{profile.get('current_title','')} at {profile.get('current_company','')}. "
        f"Skills: {profile.get('skills','')}. "
        f"Experience: {profile.get('years_experience',0)} years."
    )
    # Reuse the outreach generator. The 'post_content' slot carries context about
    # why we're reaching this specific person at this company.
    rel = c.get("relationship_type") or "contact"
    context = (
        f"Reaching out to a {rel} at {c.get('company','')}. "
        f"Their role: {c.get('title','')}. "
        f"Latest role they mentioned hiring for: {c.get('latest_role_mentioned','') or 'n/a'}."
    )
    message = await orchestrator.generate_outreach(
        post_content=context,
        author_name=c.get("name", ""),
        author_title=c.get("title", ""),
        role_mentioned=c.get("latest_role_mentioned", "") or "Product Manager",
        user_profile=user_summary,
        voice=profile.get("voice_instructions", "") or "",
    )
    # Persist the draft.
    client.table("contacts").update({"outreach_message": message}).eq("id", contact_id).execute()
    return {"outreach_message": message}
