"""People discovery for the Referral tab.

Finds warm-intro targets at the Top-70 companies via a COOKIELESS Apify actor
(fabri-lab/linkedin-public-search-lead-extractor) — no LinkedIn login, so the
user's F1-sensitive account is never touched.

Three searches per company, matching the user's priority:
  1. hiring_manager — Director/Head/Group/VP of Product
  2. alum          — University of Washington alumni in Product/Program roles
  3. team_senior   — Senior/Principal/Staff PMs (seniors on the team)

Results are US-filtered, deduped by LinkedIn URL, tagged with relationship_type
+ target_company, and upserted into the contacts table for the Referral tab.
"""

from datetime import datetime, timezone

from app.logger import log
from app.services.apify_service import run_apify_actor, load_apify_config, is_us_location
from app.services.night_shift_config import TIER_1_COMPANIES, TIER_2_COMPANIES

ACTOR_ID = "fabri-lab~linkedin-public-search-lead-extractor"

ALL_TARGETS = sorted(set(list(TIER_1_COMPANIES.keys()) + TIER_2_COMPANIES))

_HM_TITLES = ["Director of Product", "Group Product Manager", "Head of Product", "VP Product", "Director, Product Management"]
_ALUM_TITLES = ["Product Manager", "Program Manager", "Technical Program Manager"]
_SENIOR_TITLES = ["Senior Product Manager", "Principal Product Manager", "Staff Product Manager"]


def _search_input(company: str, titles: list[str], school: str | None = None) -> dict:
    inp = {
        "profileScraperMode": "Short",       # cheap, fast — no per-profile open
        "currentCompanyUrls": [company],
        "currentJobTitles": titles,
        "locations": ["United States"],
        "maxItems": 12,
        "takePages": 1,
    }
    if school:
        inp["schoolUrls"] = [school]
    return inp


def _extract(item: dict) -> dict | None:
    """Normalize one actor result into a contact dict, or None if unusable."""
    url = item.get("profileUrl") or item.get("url") or item.get("linkedinUrl") or ""
    name = item.get("fullName") or item.get("name") or ""
    if not url or not name:
        return None
    title = item.get("headline") or item.get("title") or item.get("jobTitle") or ""
    location = item.get("location") or item.get("addressWithCountry") or ""
    return {
        "name": name.strip(),
        "title": title.strip(),
        "linkedin_url": url.strip(),
        "location": location.strip(),
    }


def _relevant(c: dict) -> bool:
    """Gate: US + a real PM/Program/leadership title. Keeps the tab signal-dense."""
    loc = (c.get("location") or "").strip()
    if loc and not is_us_location(loc):
        return False
    t = (c.get("title") or "").lower()
    return any(k in t for k in ("product", "program"))


async def discover_for_company(company: str, token: str) -> list[dict]:
    """Run the 3 searches for one company, return relevant deduped contacts."""
    searches = [
        ("hiring_manager", _search_input(company, _HM_TITLES)),
        ("alum", _search_input(company, _ALUM_TITLES, school="University of Washington")),
        ("team_senior", _search_input(company, _SENIOR_TITLES)),
    ]
    found: dict[str, dict] = {}   # linkedin_url -> contact (first/best wins)
    for rel, inp in searches:
        try:
            items = await run_apify_actor(ACTOR_ID, inp, token, timeout_secs=180)
        except Exception as e:
            log.error(f"people_discovery {company}/{rel} failed: {e}")
            continue
        for raw in items:
            c = _extract(raw)
            if not c or not _relevant(c):
                continue
            url = c["linkedin_url"]
            if url not in found:   # hiring_manager search runs first → wins the rank
                c["relationship_type"] = rel
                c["target_company"] = company
                found[url] = c
    return list(found.values())


async def run_people_discovery(companies: list[str] | None = None) -> dict:
    """Discover people for the given companies (default: all 70) and upsert
    into contacts. Returns a summary."""
    from app import database as db

    config = load_apify_config()
    token = config.get("token")
    if not token:
        return {"success": False, "error": "No Apify token configured"}

    targets = companies or ALL_TARGETS
    client = db.get_db()
    discovered = 0
    inserted = 0
    per_company = {}

    for company in targets:
        people = await discover_for_company(company, token)
        per_company[company] = len(people)
        discovered += len(people)
        for c in people:
            try:
                # Upsert by linkedin_url (unique). Don't clobber an existing
                # outreach_status / message if we re-discover the same person.
                client.table("contacts").upsert({
                    "name": c["name"],
                    "title": c["title"],
                    "company": company,
                    "target_company": company,
                    "relationship_type": c["relationship_type"],
                    "linkedin_url": c["linkedin_url"],
                    "source": "people_discovery",
                    "is_relevant": True,
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                }, on_conflict="linkedin_url").execute()
                inserted += 1
            except Exception as e:
                log.warning(f"upsert contact failed ({c.get('linkedin_url')}): {e}")

    log.info(f"People discovery: {discovered} found across {len(targets)} companies")
    return {
        "success": True,
        "companies": len(targets),
        "discovered": discovered,
        "upserted": inserted,
        "per_company": per_company,
    }
