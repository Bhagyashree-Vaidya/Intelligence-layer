"""JobPilot — Auto-Apply Service.

Submits job applications programmatically via ATS public APIs:
  - Greenhouse: POST /boards/{slug}/jobs/{id}
  - Lever:      POST /postings/{company}/{id}/apply
  - Ashby:      POST /posting-api/apply/application

Covers ~80% of tracked jobs (the rest use Workday/SmartRecruiters which
require browser-based apply — Phase 2 with Playwright).

Safety:
  - STRICT role filter: only applies to PM/TPM/product roles (configurable)
  - Picks the correct resume for each role category (PM resume for PM jobs, etc.)
  - Skips jobs already applied to
  - Max 1 application per company per run
  - Tracks every submission with full audit log
  - Rate-limited per ATS to avoid bans
  - Configurable exclude list (companies to skip)
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import get_settings
from app.logger import log
from app.services.role_classifier import (
    classify_role,
    get_resume_tag_for_role,
    ROLE_LABELS,
)

# ── ATS URL → Platform Detection ──────────────────────────────────────────────

# Map a job URL to the ATS platform so we know which API to call
_ATS_PATTERNS = {
    "greenhouse": re.compile(
        r"boards\.greenhouse\.io/(\w+)/jobs/(\d+)", re.IGNORECASE
    ),
    "greenhouse_alt": re.compile(
        r"job-boards\.greenhouse\.io/(\w+)/jobs/(\d+)", re.IGNORECASE
    ),
    "lever": re.compile(
        r"jobs\.lever\.co/([^/]+)/([a-f0-9-]+)", re.IGNORECASE
    ),
    "ashby": re.compile(
        r"jobs\.ashbyhq\.com/([^/]+)/([a-f0-9-]+)", re.IGNORECASE
    ),
}


def detect_ats(url: str) -> tuple[str | None, str | None, str | None]:
    """Detect ATS platform from a job URL.

    Returns: (platform, company_slug, job_id) or (None, None, None)
    """
    if not url:
        return None, None, None

    for platform, pattern in _ATS_PATTERNS.items():
        m = pattern.search(url)
        if m:
            ats = "greenhouse" if platform.startswith("greenhouse") else platform
            return ats, m.group(1), m.group(2)

    # Also detect by greenhouse_id prefix patterns
    return None, None, None


def detect_ats_from_job(job: dict) -> tuple[str, str | None, str | None]:
    """Detect ATS from job URL + fallback to greenhouse_id pattern."""
    url = job.get("url", "")
    platform, slug, job_id = detect_ats(url)

    if platform:
        return platform, slug, job_id

    # Fallback: check the URL domain
    if "greenhouse.io" in url:
        return "greenhouse", None, job.get("greenhouse_id", "")
    if "lever.co" in url:
        return "lever", None, job.get("greenhouse_id", "")
    if "ashbyhq.com" in url:
        return "ashby", None, job.get("greenhouse_id", "")

    return "unknown", None, None


# ── Profile → Application Data Builder ────────────────────────────────────────

def build_applicant_data(profile: dict) -> dict:
    """Convert user profile into a standardized applicant dict."""
    education = profile.get("education", [])
    if isinstance(education, str):
        try:
            education = json.loads(education)
        except Exception:
            education = []

    return {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "website": profile.get("website", ""),
        "github": profile.get("github", ""),
        "current_company": profile.get("current_company", ""),
        "current_title": profile.get("current_title", ""),
        "education": education,
        "cover_letter": profile.get("cover_letter_default", ""),
        "work_auth": profile.get("work_auth", ""),
        "sponsorship": profile.get("sponsorship", ""),
        "gender": profile.get("gender", ""),
        "race": profile.get("race", ""),
        "veteran": profile.get("veteran", ""),
        "disability": profile.get("disability", ""),
    }


# ── Greenhouse Application Submit ─────────────────────────────────────────────

async def apply_greenhouse(
    client: httpx.AsyncClient,
    company_slug: str,
    job_id: str,
    applicant: dict,
    resume_path: str | None = None,
) -> dict:
    """Submit application via Greenhouse public API.

    Greenhouse job application API:
      POST https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}
      Content-Type: multipart/form-data

    Required fields vary by company, but first_name, last_name, email
    are always required. We send everything we have.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs/{job_id}"

    # Greenhouse uses multipart form data
    form_data = {
        "first_name": applicant["first_name"],
        "last_name": applicant["last_name"],
        "email": applicant["email"],
    }

    # Optional standard fields
    if applicant.get("phone"):
        form_data["phone"] = applicant["phone"]
    if applicant.get("linkedin"):
        form_data["LinkedIn Profile"] = applicant["linkedin"]
    if applicant.get("website"):
        form_data["Website"] = applicant["website"]
    if applicant.get("github"):
        form_data["GitHub URL"] = applicant["github"]
    if applicant.get("current_company"):
        form_data["Current Company"] = applicant["current_company"]
    if applicant.get("current_title"):
        form_data["Current Title"] = applicant["current_title"]
    if applicant.get("cover_letter"):
        form_data["cover_letter"] = applicant["cover_letter"]

    # EEO / demographic fields (optional)
    if applicant.get("gender"):
        form_data["gender"] = applicant["gender"]
    if applicant.get("race"):
        form_data["race"] = applicant["race"]
    if applicant.get("veteran"):
        form_data["veteran_status"] = applicant["veteran"]

    files = {}
    if resume_path and Path(resume_path).exists():
        resume_file = Path(resume_path)
        files["resume"] = (resume_file.name, resume_file.read_bytes(), "application/pdf")

    try:
        resp = await client.post(
            url,
            data=form_data,
            files=files if files else None,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            return {"success": True, "status_code": resp.status_code, "ats": "greenhouse"}
        else:
            body = resp.text[:500]
            return {
                "success": False,
                "status_code": resp.status_code,
                "error": body,
                "ats": "greenhouse",
            }
    except Exception as e:
        return {"success": False, "error": str(e), "ats": "greenhouse"}


# ── Lever Application Submit ──────────────────────────────────────────────────

async def apply_lever(
    client: httpx.AsyncClient,
    company_slug: str,
    posting_id: str,
    applicant: dict,
    resume_path: str | None = None,
) -> dict:
    """Submit application via Lever public API.

    Lever posting apply API:
      POST https://api.lever.co/v0/postings/{company}/{id}/apply
      Content-Type: multipart/form-data

    Lever uses specific field names in its form.
    """
    url = f"https://api.lever.co/v0/postings/{company_slug}/{posting_id}/apply"

    form_data = {
        "name": f"{applicant['first_name']} {applicant['last_name']}".strip(),
        "email": applicant["email"],
        "org": applicant.get("current_company", ""),
    }

    # Lever puts LinkedIn/website/phone as "urls" or "phone"
    if applicant.get("phone"):
        form_data["phone"] = applicant["phone"]

    # Lever accepts multiple "urls" fields
    urls_data = []
    if applicant.get("linkedin"):
        urls_data.append(("urls[LinkedIn]", applicant["linkedin"]))
    if applicant.get("website"):
        urls_data.append(("urls[Portfolio]", applicant["website"]))
    if applicant.get("github"):
        urls_data.append(("urls[GitHub]", applicant["github"]))

    if applicant.get("cover_letter"):
        form_data["comments"] = applicant["cover_letter"]

    files = {}
    if resume_path and Path(resume_path).exists():
        resume_file = Path(resume_path)
        files["resume"] = (resume_file.name, resume_file.read_bytes(), "application/pdf")

    try:
        # Lever form data needs special handling for urls[]
        all_data = list(form_data.items()) + urls_data

        resp = await client.post(
            url,
            data=all_data,
            files=files if files else None,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "success": True,
                "status_code": resp.status_code,
                "ats": "lever",
                "application_id": result.get("applicationId", ""),
            }
        else:
            body = resp.text[:500]
            return {
                "success": False,
                "status_code": resp.status_code,
                "error": body,
                "ats": "lever",
            }
    except Exception as e:
        return {"success": False, "error": str(e), "ats": "lever"}


# ── Ashby Application Submit ─────────────────────────────────────────────────

async def apply_ashby(
    client: httpx.AsyncClient,
    company_slug: str,
    job_id: str,
    applicant: dict,
    resume_path: str | None = None,
) -> dict:
    """Submit application via Ashby public API.

    Ashby application API:
      POST https://api.ashbyhq.com/posting-api/apply/application
      Content-Type: multipart/form-data

    Ashby uses jobPostingId in the form body.
    """
    url = "https://api.ashbyhq.com/posting-api/apply/application"

    form_data = {
        "jobPostingId": job_id,
        "firstName": applicant["first_name"],
        "lastName": applicant["last_name"],
        "email": applicant["email"],
    }

    if applicant.get("phone"):
        form_data["phoneNumber"] = applicant["phone"]
    if applicant.get("linkedin"):
        form_data["linkedInUrl"] = applicant["linkedin"]
    if applicant.get("website"):
        form_data["websiteUrl"] = applicant["website"]
    if applicant.get("github"):
        form_data["githubUrl"] = applicant["github"]
    if applicant.get("current_company"):
        form_data["currentCompany"] = applicant["current_company"]
    if applicant.get("cover_letter"):
        form_data["coverLetter"] = applicant["cover_letter"]

    files = {}
    if resume_path and Path(resume_path).exists():
        resume_file = Path(resume_path)
        files["resume"] = (resume_file.name, resume_file.read_bytes(), "application/pdf")

    try:
        resp = await client.post(
            url,
            data=form_data,
            files=files if files else None,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "success": True,
                "status_code": resp.status_code,
                "ats": "ashby",
                "application_id": result.get("applicationId", result.get("id", "")),
            }
        else:
            body = resp.text[:500]
            return {
                "success": False,
                "status_code": resp.status_code,
                "error": body,
                "ats": "ashby",
            }
    except Exception as e:
        return {"success": False, "error": str(e), "ats": "ashby"}


# ── Unified Apply Dispatcher ─────────────────────────────────────────────────

async def submit_application(
    job: dict,
    applicant: dict,
    resume_path: str | None = None,
) -> dict:
    """Submit a job application to the appropriate ATS.

    Returns a result dict with success status, error details, etc.
    """
    platform, slug, job_id = detect_ats_from_job(job)

    if platform == "unknown" or not job_id:
        return {
            "success": False,
            "error": f"Unsupported ATS or could not parse job URL: {job.get('url', '')[:100]}",
            "ats": platform,
            "job_id": job.get("id"),
        }

    # If we couldn't parse the slug from URL, try to derive from company_config
    if not slug:
        slug = _guess_slug(job.get("company", ""), platform)
        if not slug:
            return {
                "success": False,
                "error": f"Could not determine {platform} company slug for {job.get('company', '')}",
                "ats": platform,
                "job_id": job.get("id"),
            }

    async with httpx.AsyncClient(
        headers={"User-Agent": "JobPilot/1.0 (auto-apply)"},
        follow_redirects=True,
    ) as client:
        if platform == "greenhouse":
            result = await apply_greenhouse(client, slug, job_id, applicant, resume_path)
        elif platform == "lever":
            result = await apply_lever(client, slug, job_id, applicant, resume_path)
        elif platform == "ashby":
            result = await apply_ashby(client, slug, job_id, applicant, resume_path)
        else:
            return {
                "success": False,
                "error": f"No apply handler for platform: {platform}",
                "ats": platform,
            }

    result["job_id"] = job.get("id")
    result["company"] = job.get("company", "")
    result["title"] = job.get("title", "")
    return result


def _guess_slug(company: str, platform: str) -> str | None:
    """Try to find the ATS slug from company_config.json."""
    config_file = Path(__file__).parent.parent / "data" / "company_config.json"
    if not config_file.exists():
        return None

    try:
        config = json.loads(config_file.read_text())
        platform_config = config.get(platform, {})
        # Search by company name (case-insensitive)
        company_lower = company.lower().replace(" ", "")
        for name, slug in platform_config.items():
            if name.lower().replace(" ", "") == company_lower:
                return slug if isinstance(slug, str) else slug.get("slug", slug.get("board", ""))
        return None
    except Exception:
        return None


# ── Role-Based Resume Picker ──────────────────────────────────────────────────

async def _pick_resume_for_role(role: str, resumes: list[dict], resume_dir: Path) -> tuple[dict | None, str | None]:
    """Pick the right resume for a role category.

    Matching order:
      1. Resume tagged with exact role (e.g. role_tags="pm" for PM jobs)
      2. Resume tagged with mapped role (e.g. "product" → uses "pm" resume)
      3. Default resume as last fallback
      4. None if no resumes at all

    Returns (resume_row, file_path) or (None, None).
    """
    resume_tag = get_resume_tag_for_role(role)

    # 1. Exact role tag match
    for r in resumes:
        tags = (r.get("role_tags") or "").lower().split(",")
        tags = [t.strip() for t in tags]
        if resume_tag in tags:
            path = resume_dir / r["filename"]
            if path.exists():
                return r, str(path)

    # 2. Broader role tag match (e.g. "product" role uses "pm" resume)
    if resume_tag != role:
        for r in resumes:
            tags = (r.get("role_tags") or "").lower().split(",")
            tags = [t.strip() for t in tags]
            if role in tags:
                path = resume_dir / r["filename"]
                if path.exists():
                    return r, str(path)

    # 3. Default resume fallback
    default = next((r for r in resumes if r.get("is_default")), None)
    if default:
        path = resume_dir / default["filename"]
        if path.exists():
            return default, str(path)

    # 4. Any resume at all
    for r in resumes:
        path = resume_dir / r["filename"]
        if path.exists():
            return r, str(path)

    return None, None


# ── Batch Auto-Apply Engine ───────────────────────────────────────────────────

# Default: only PM/TPM/product roles. Expand later.
DEFAULT_ENABLED_ROLES = ["pm", "tpm", "product"]

async def run_auto_apply(
    min_score: int = 0,
    max_applications: int = 50,
    exclude_companies: list[str] | None = None,
    enabled_roles: list[str] | None = None,
    one_per_company: bool = True,
    dry_run: bool = False,
) -> dict:
    """Find eligible jobs and submit applications.

    STRICT role filtering: only applies to jobs whose title matches one of
    the enabled_roles categories. Default = PM, TPM, product only.

    For each job, picks the role-specific resume (PM resume for PM jobs,
    TPM resume for TPM jobs, etc.). Falls back to default resume if no
    role-specific one is uploaded yet.

    Steps:
      1. Load profile + all resumes
      2. Query all un-applied jobs
      3. STRICT FILTER: classify each title → skip if role not in enabled_roles
      4. Filter to supported ATS (Greenhouse, Lever, Ashby)
      5. Deduplicate: pick the highest-scoring role per company
      6. Pick role-matched resume for each job
      7. Submit with rate limiting (2s between each)
      8. Track in applications + auto_apply_log tables

    No API keys needed — these are public application endpoints.

    Args:
        min_score: Minimum relevancy_score (default 0 = no score filter)
        max_applications: Max applications per run
        exclude_companies: Companies to skip
        enabled_roles: Role categories to apply for (default: pm, tpm, product)
        one_per_company: Max 1 application per company per run
        dry_run: Preview mode — find candidates but don't submit
    """
    from app import database as db

    settings = get_settings()
    allowed_roles = set(enabled_roles or DEFAULT_ENABLED_ROLES)
    exclude = set(c.strip().lower() for c in (exclude_companies or []) if c.strip())

    # Also parse exclude from settings
    if settings.auto_apply_exclude_companies:
        for c in settings.auto_apply_exclude_companies.split(","):
            if c.strip():
                exclude.add(c.strip().lower())

    # 1. Load profile
    profile = await db.get_profile()
    if not profile.get("first_name") or not profile.get("email"):
        return {
            "success": False,
            "error": "Profile incomplete — need at least first_name and email to auto-apply",
            "applied": 0,
            "skipped": 0,
        }
    applicant = build_applicant_data(profile)

    # 2. Load all resumes (for role-based matching)
    resumes = await db.get_resumes()
    resume_dir = Path(settings.resume_upload_dir)

    # 3. Get already-applied job IDs
    applied_ids = await db.get_applied_job_ids()

    # 4. Query un-applied jobs
    candidates = await db.get_auto_apply_candidates(
        min_score=min_score,
        exclude_ids=applied_ids,
        limit=max_applications * 10,  # Fetch extra — many will be filtered by role
    )

    # 5. STRICT ROLE FILTER + ATS filter + company dedup
    eligible = []
    skipped_role = 0
    skipped_ats = 0
    seen_companies: set[str] = set()

    for job in candidates:
        title = job.get("title", "")
        company_lower = (job.get("company") or "").lower()

        # Skip excluded companies
        if company_lower in exclude:
            continue

        # STRICT: classify the title — skip if not in allowed roles
        role = classify_role(title)
        if role is None or role not in allowed_roles:
            skipped_role += 1
            continue

        # One per company
        if one_per_company and company_lower in seen_companies:
            continue

        # Must be a supported ATS
        platform, slug, job_id = detect_ats_from_job(job)
        if platform not in ("greenhouse", "lever", "ashby") or not job_id:
            skipped_ats += 1
            continue

        # Attach role classification to the job for resume matching
        job["_role"] = role
        eligible.append(job)
        seen_companies.add(company_lower)

        if len(eligible) >= max_applications:
            break

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "applied": 0,
            "eligible": len(eligible),
            "skipped_wrong_role": skipped_role,
            "skipped_unsupported_ats": skipped_ats,
            "enabled_roles": list(allowed_roles),
            "role_labels": {r: ROLE_LABELS.get(r, r) for r in allowed_roles},
            "candidates": [
                {
                    "id": j["id"],
                    "company": j.get("company"),
                    "title": j.get("title"),
                    "role": j.get("_role"),
                    "score": j.get("relevancy_score"),
                    "ats": detect_ats_from_job(j)[0],
                    "url": j.get("url", ""),
                }
                for j in eligible
            ],
        }

    # 6. Submit applications with role-matched resumes
    results = []
    applied = 0
    failed = 0

    for job in eligible:
        role = job.get("_role", "pm")

        # Pick the right resume for this role
        resume_row, resume_path = await _pick_resume_for_role(role, resumes, resume_dir)

        try:
            result = await submit_application(job, applicant, resume_path)
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            result["role"] = role
            result["resume_used"] = resume_row.get("original_name", "") if resume_row else "none"

            if result.get("success"):
                await db.save_application(
                    job["id"],
                    resume_row["id"] if resume_row else None,
                    "applied",
                )
                await db.log_auto_apply(
                    job_id=job["id"],
                    status="applied",
                    ats=result.get("ats", ""),
                    response=json.dumps(result),
                )
                applied += 1
                log.info(
                    f"Auto-applied [{role}]: {job.get('company')} — {job.get('title')}"
                )
            else:
                await db.log_auto_apply(
                    job_id=job["id"],
                    status="failed",
                    ats=result.get("ats", ""),
                    response=json.dumps(result),
                )
                failed += 1
                log.warning(
                    f"Auto-apply failed [{role}]: {job.get('company')} — "
                    f"{result.get('error', '')[:100]}"
                )

            results.append(result)

        except Exception as e:
            failed += 1
            log.error(f"Auto-apply exception for job {job.get('id')}: {e}")
            results.append({
                "success": False, "error": str(e), "job_id": job.get("id"),
            })

        # Rate limit: 2s between applications to avoid ATS bans
        await asyncio.sleep(2)

    return {
        "success": True,
        "applied": applied,
        "failed": failed,
        "total_eligible": len(eligible),
        "skipped_wrong_role": skipped_role,
        "skipped_unsupported_ats": skipped_ats,
        "enabled_roles": list(allowed_roles),
        "results": results,
    }
