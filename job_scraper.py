#!/usr/bin/env python3
"""
Job Scraper — Playwright + Greenhouse Boards
Scrapes jobs from 500+ companies using headless Chromium, filters by role and recency.

Usage:
    python job_scraper.py                           # All roles, last 24h
    python job_scraper.py --hours 48                # Last 48 hours
    python job_scraper.py --roles pm ux             # Only PM and UX roles
    python job_scraper.py --companies airbnb stripe  # Specific companies
    python job_scraper.py --list-roles              # Show available role filters

Requirements:
    pip install playwright
    python -m playwright install chromium
"""

import argparse
import asyncio
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
DEFAULT_CONCURRENCY = 10
DEFAULT_HOURS = 24
SLUGS_FILE = Path(__file__).parent / "company_slugs.txt"

ROLE_FILTERS = {
    "pm": {
        "label": "Product Manager",
        "patterns": [
            r"\bproduct\s+manager\b",
            r"\btechnical\s+product\s+manager\b",
            r"\bassociate\s+product\s+manager\b",
            r"\bsenior\s+product\s+manager\b",
            r"\bstaff\s+product\s+manager\b",
            r"\bgroup\s+product\s+manager\b",
            r"\bprincipal\s+product\s+manager\b",
            r"\bdirector.*product\s+manage",
            r"\bvp.*product\b",
            r"\bhead\s+of\s+product\b",
            r"\bchief\s+product\b",
            r"\bproduct\s+lead\b",
            r"\bproduct\s+owner\b",
        ],
    },
    "product": {
        "label": "Product (broad)",
        "patterns": [
            r"^product\b",
            r"\bproduct$",
            r"\bproduct\s+analyst\b",
            r"\bproduct\s+strategy\b",
            r"\bproduct\s+ops\b",
            r"\bproduct\s+operations\b",
            r"\bproduct\s+marketing\b",
        ],
    },
    "tpm": {
        "label": "Technical/Program Manager",
        "patterns": [
            r"\btechnical\s+program\s+manager\b",
            r"\bprogram\s+manager\b",
            r"\btpm\b",
            r"\bagile\s+program\s+manager\b",
        ],
    },
    "ux": {
        "label": "UX Design & Research",
        "patterns": [
            r"\bux\s+designer\b",
            r"\bux\s+design\b",
            r"\bux\s+researcher\b",
            r"\bux\s+research\b",
            r"\buser\s+experience\s+designer\b",
            r"\buser\s+experience\s+researcher\b",
            r"\bproduct\s+designer\b",
            r"\bsenior\s+product\s+designer\b",
            r"\bstaff\s+product\s+designer\b",
            r"\bux/ui\b",
            r"\bui/ux\b",
        ],
    },
    "swe": {
        "label": "Software Engineer",
        "patterns": [
            r"\bsoftware\s+development\s+engineer\b",
            r"\bsde\b",
            r"\bswe\b",
            r"\bsoftware\s+engineer\b",
            r"\bfrontend\s+engineer\b",
            r"\bbackend\s+engineer\b",
            r"\bfull[\s\-]?stack\s+engineer\b",
            r"\bplatform\s+engineer\b",
        ],
    },
    "presales": {
        "label": "Pre-sales & Solutions",
        "patterns": [
            r"\bpre[\-\s]?sales\b",
            r"\bsolutions\s+engineer\b",
            r"\bsolutions\s+consultant\b",
            r"\bsales\s+engineer\b",
            r"\bproduct\s+consultant\b",
            r"\btechnical\s+consultant\b",
            r"\bsolutions\s+architect\b",
        ],
    },
}

ALL_PATTERNS = []
for group in ROLE_FILTERS.values():
    ALL_PATTERNS.extend(group["patterns"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def load_companies(slugs_file: Path, override: list[str] | None = None) -> list[str]:
    if override:
        return override
    if not slugs_file.exists():
        print(f"Error: {slugs_file} not found", file=sys.stderr)
        sys.exit(1)
    return [l.strip() for l in slugs_file.read_text().splitlines() if l.strip()]


def compile_patterns(role_keys: list[str] | None) -> list[re.Pattern]:
    if role_keys:
        patterns = []
        for key in role_keys:
            if key not in ROLE_FILTERS:
                print(f"Unknown role filter: {key}. Use --list-roles.", file=sys.stderr)
                sys.exit(1)
            patterns.extend(ROLE_FILTERS[key]["patterns"])
    else:
        patterns = ALL_PATTERNS
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def matches_title(title: str, compiled: list[re.Pattern]) -> bool:
    return any(p.search(title) for p in compiled)


def parse_timestamp(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def is_recent(ts_str: str, cutoff: datetime) -> bool:
    ts = parse_timestamp(ts_str)
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts >= cutoff


def strip_html(html: str) -> str:
    if not html:
        return ""
    text = unescape(html)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li>", "\n• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def flatten_job(job: dict, company: str) -> dict:
    loc = job.get("location", {})
    location = loc.get("name", "") if isinstance(loc, dict) else str(loc or "")
    departments = job.get("departments") or []
    offices = job.get("offices") or []
    metadata = {m.get("name", ""): m.get("value") for m in (job.get("metadata") or [])}

    return {
        "company": company,
        "title": job.get("title", ""),
        "location": location,
        "department": ", ".join(d.get("name", "") for d in departments),
        "url": job.get("absolute_url", ""),
        "updated_at": job.get("updated_at", ""),
        "first_published": job.get("first_published", ""),
        "employment_type": metadata.get("Employment Type", ""),
        "salary_range": metadata.get("Salary Range", metadata.get("Compensation Range", "")),
        "description": strip_html(job.get("content", "")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Playwright scraper
# ──────────────────────────────────────────────────────────────────────────────


async def fetch_company(context: BrowserContext, company: str, semaphore: asyncio.Semaphore) -> tuple[str, list[dict]]:
    async with semaphore:
        page = await context.new_page()
        url = f"{BASE_URL}/{company}/jobs?content=true"
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response and response.ok:
                text = await page.inner_text("body")
                data = json.loads(text)
                return company, data.get("jobs", [])
            return company, []
        except Exception:
            return company, []
        finally:
            await page.close()


async def fetch_job_detail(context: BrowserContext, company: str, job_id: int, semaphore: asyncio.Semaphore) -> dict | None:
    async with semaphore:
        page = await context.new_page()
        url = f"{BASE_URL}/{company}/jobs/{job_id}?questions=true"
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response and response.ok:
                text = await page.inner_text("body")
                return json.loads(text)
            return None
        except Exception:
            return None
        finally:
            await page.close()


async def scrape_all(
    companies: list[str],
    compiled_patterns: list[re.Pattern],
    cutoff: datetime,
    concurrency: int,
    location_filter: str | None = None,
    detailed: bool = False,
    headless: bool = True,
) -> tuple[list[dict], dict]:
    stats = {"total_companies": len(companies), "total_jobs": 0, "errors": 0, "scanned": 0, "matched": 0}
    matched = []
    semaphore = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        # Fetch all companies concurrently (bounded by semaphore)
        tasks = [fetch_company(context, c, semaphore) for c in companies]
        results = []

        # Process in batches to show progress
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)

            stats["scanned"] = len(results)
            current_matches = sum(1 for _ in matched)
            print(
                f"  [{stats['scanned']}/{len(companies)}] scraped, {len(matched)} matches so far",
                file=sys.stderr,
            )

        # Process results
        for company, jobs in results:
            if not jobs:
                stats["errors"] += 1
                continue

            stats["total_jobs"] += len(jobs)

            for job in jobs:
                title = job.get("title", "")
                updated = job.get("updated_at", "")

                if not matches_title(title, compiled_patterns):
                    continue
                if not is_recent(updated, cutoff):
                    continue

                flat = flatten_job(job, company)

                if location_filter and location_filter.lower() not in flat["location"].lower():
                    continue

                matched.append(flat)

        # Optionally fetch full details for matched jobs
        if detailed and matched:
            print(f"\n  Fetching details for {len(matched)} matched jobs...", file=sys.stderr)
            detail_tasks = []
            for job in matched:
                job_id = None
                if job["url"]:
                    m = re.search(r"gh_jid=(\d+)", job["url"])
                    if m:
                        job_id = int(m.group(1))
                if job_id:
                    detail_tasks.append((job, fetch_job_detail(context, job["company"], job_id, semaphore)))

            for job, coro in detail_tasks:
                detail = await coro
                if detail:
                    updated = flatten_job(detail, job["company"])
                    job.update(updated)

            print(f"  Done fetching details", file=sys.stderr)

        await context.close()
        await browser.close()

    matched.sort(key=lambda j: j["updated_at"], reverse=True)
    stats["matched"] = len(matched)
    return matched, stats


# ──────────────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────────────


def save_results(jobs: list[dict], output: str, fmt: str):
    out = Path(output)

    if fmt in ("json", "both"):
        path = out.with_suffix(".json")
        path.write_text(json.dumps(jobs, indent=2, default=str), encoding="utf-8")
        print(f"  Saved {path}", file=sys.stderr)

    if fmt in ("csv", "both"):
        if not jobs:
            return
        path = out.with_suffix(".csv")
        fields = list(jobs[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(jobs)
        print(f"  Saved {path}", file=sys.stderr)


def print_summary(jobs: list[dict], stats: dict):
    from collections import Counter

    print("\n" + "=" * 60, file=sys.stderr)
    print("  JOB SCRAPER RESULTS (Playwright)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  Companies scraped:  {stats['scanned']}", file=sys.stderr)
    print(f"  Errors/empty:       {stats['errors']}", file=sys.stderr)
    print(f"  Total jobs scanned: {stats['total_jobs']}", file=sys.stderr)
    print(f"  Matching jobs:      {stats['matched']}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    if not jobs:
        return

    print("\n  TOP COMPANIES:", file=sys.stderr)
    for company, count in Counter(j["company"] for j in jobs).most_common(15):
        print(f"    {count:4d}  {company}", file=sys.stderr)

    print("\n  TOP TITLES:", file=sys.stderr)
    for title, count in Counter(j["title"] for j in jobs).most_common(15):
        print(f"    {count:4d}  {title}", file=sys.stderr)

    print("\n  TOP LOCATIONS:", file=sys.stderr)
    for loc, count in Counter(j["location"] for j in jobs if j["location"]).most_common(10):
        print(f"    {count:4d}  {loc}", file=sys.stderr)

    print("", file=sys.stderr)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Greenhouse job boards with Playwright",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python job_scraper.py                             # All roles, last 24h
  python job_scraper.py --hours 48                  # Last 48 hours
  python job_scraper.py --roles pm tpm ux           # PM, TPM, UX roles
  python job_scraper.py --location "San Francisco"
  python job_scraper.py --companies airbnb stripe --roles swe
  python job_scraper.py --list-roles
  python job_scraper.py --headed                    # Show browser window
        """,
    )
    parser.add_argument("--companies", nargs="+", help="Specific company slugs (overrides slugs file)")
    parser.add_argument("--slugs-file", type=Path, default=SLUGS_FILE, help="Path to company slugs file")
    parser.add_argument("--roles", nargs="+", help="Role filters: pm, product, tpm, ux, swe, presales")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="Look back N hours (default: 24)")
    parser.add_argument("--location", type=str, help="Filter by location (e.g. 'Remote', 'New York')")
    parser.add_argument("-o", "--output", default="filtered_jobs", help="Output filename (default: filtered_jobs)")
    parser.add_argument("-f", "--format", choices=["json", "csv", "both"], default="both")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Parallel browser tabs (default: 10)")
    parser.add_argument("--detailed", action="store_true", help="Fetch full details for each matched job")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode (visible)")
    parser.add_argument("--list-roles", action="store_true", help="Show role filter options")
    args = parser.parse_args()

    if args.list_roles:
        print("\nAvailable role filters (use with --roles):\n")
        for key, cfg in ROLE_FILTERS.items():
            print(f"  {key:10s}  {cfg['label']}")
            for p in cfg["patterns"][:3]:
                print(f"              e.g. {p}")
            if len(cfg["patterns"]) > 3:
                print(f"              ... +{len(cfg['patterns']) - 3} more")
            print()
        return

    companies = load_companies(args.slugs_file, args.companies)
    compiled = compile_patterns(args.roles)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    role_desc = ", ".join(args.roles) if args.roles else "all"
    print(f"\nJob Scraper (Playwright)", file=sys.stderr)
    print(f"  Companies:   {len(companies)}", file=sys.stderr)
    print(f"  Roles:       {role_desc}", file=sys.stderr)
    print(f"  Window:      last {args.hours}h (since {cutoff.strftime('%Y-%m-%d %H:%M UTC')})", file=sys.stderr)
    if args.location:
        print(f"  Location:    {args.location}", file=sys.stderr)
    print(f"  Concurrency: {args.concurrency} tabs", file=sys.stderr)
    print(f"  Browser:     {'headed' if args.headed else 'headless'}", file=sys.stderr)
    print("", file=sys.stderr)

    jobs, stats = asyncio.run(scrape_all(
        companies, compiled, cutoff,
        concurrency=args.concurrency,
        location_filter=args.location,
        detailed=args.detailed,
        headless=not args.headed,
    ))

    print_summary(jobs, stats)

    if jobs:
        save_results(jobs, args.output, args.format)
    else:
        print("No matching jobs found.", file=sys.stderr)


if __name__ == "__main__":
    main()
