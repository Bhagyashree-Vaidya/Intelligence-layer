# JobPilot Intelligence Layer — Context Document

## What Is This

JobPilot is an end-to-end job application automation platform that scrapes open roles from 250+ companies across 8 ATS platforms, scores them against your profile, and auto-fills applications through a Chrome extension. The "intelligence layer" is the combination of relevancy scoring, recruiter discovery, personalized outreach, and smart Q&A that sits between raw job data and human decision-making.

## Problem Statement

Applying to jobs at scale involves:
1. **Discovery** — Finding relevant openings across dozens of company career pages, each using a different ATS
2. **Evaluation** — Determining which of thousands of results actually match your skills, seniority, and location
3. **Outreach** — Identifying the right recruiter or hiring manager and crafting a personalized message
4. **Application** — Filling out repetitive forms with the same information across hundreds of applications
5. **Tracking** — Keeping a pipeline of where each application stands

JobPilot automates or augments every step.

## Core Intelligence Components

### 1. Multi-ATS Scraper (`scraper_service.py`)

Scrapes 6 ATS platforms via their public JSON APIs without needing a browser:

| ATS | Endpoint Pattern | Companies |
|-----|-----------------|-----------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` | ~150 |
| Lever | `api.lever.co/v0/postings/{slug}` | ~40 |
| Ashby | `jobs.ashbyhq.com/api/non-user-graphql` | ~20 |
| SmartRecruiters | `careers.smartrecruiters.com/{slug}` | ~15 |
| Workday | `{company}.wd5.myworkdaysite.com/wday/cxs/...` | ~10 |
| Workable | `apply.workable.com/api/v3/accounts/{slug}/jobs` | ~15 |

Each scraper normalizes output to a common schema: `{greenhouse_id, company, title, location, department, url, description, updated_at, employment_type, salary_range}`.

### 2. Big Tech Scrapers (`bigtech_scrapers.py`)

Proprietary career sites that don't use standard ATS platforms:

- **Apple** — Parses SSR hydration data from `jobs.apple.com`. The page embeds JSON inside a JavaScript string literal with nested escape sequences (`\"`, `\\`, `\n`). A custom `unescape_js_string()` function processes the raw string character-by-character to handle this correctly.
- **Amazon** — Uses `amazon.jobs` search API with location defaulting to "United States"
- **Netflix** — Uses Lever public API (dual-listed)
- **Meta, Google, Microsoft** — Identified as `BROWSER_ONLY_SCRAPERS`, requiring Playwright for JavaScript rendering

### 3. Apify Integration (`apify_service.py`)

For platforms that actively block scraping (LinkedIn, Indeed), JobPilot delegates to Apify actors:

- **LinkedIn**: `curious_coder~linkedin-jobs-scraper` — Takes a LinkedIn search URL (not raw keywords). The URL is constructed with params: `keywords`, `location`, `f_TPR` (time range), `f_E` (experience level).
- **Indeed**: `misceres~indeed-scraper`

Key design decision: the LinkedIn actor returns a different JSON schema than documented. The actual format uses `id` (not `jobId`), `company` (not `companyName`), and `seniorityLevel` (not `experienceLevel`). The `flatten_linkedin_job()` function maps this correctly.

### 4. US Location Filter

Applied as a post-filter on ALL scraper output. Uses a two-pass regex approach:

1. **Positive match**: 50 US state abbreviations, full state names, "United States", "USA", "Remote"
2. **Negative match**: 60+ foreign countries and cities (Bangalore, London, Singapore, Dubai, etc.)

A job passes if it matches the positive pattern OR doesn't match the negative pattern. This purged ~4,250 foreign jobs from the initial index.

### 5. Relevancy Engine (`relevancy_engine.py`)

Scores each job 0-100 against the user's profile using four weighted dimensions:

- **Title match (40pts)**: Maps user's `current_title` to a role family (e.g., "Product Manager" maps to 10+ regex patterns including PM, TPM, APM, GPM, etc.), then checks if the job title matches
- **Skills match (35pts)**: Compares user's comma-separated `skills` against the job description using 25+ skill aliases with regex patterns (e.g., "javascript" also matches "js", "typescript", "ts")
- **Experience level (10pts)**: Extracts seniority from job title (intern, junior, senior, staff, etc.) and checks if user's years fall within the expected range
- **Location (15pts)**: Rewards city match (15), remote (12), state match (10), or other US (3)

Also extracts two types of keywords:
- Matched skills (no prefix) — skills the user has that appear in the job
- Nice-to-have skills (`+` prefix) — skills in the job the user doesn't have

### 6. Answer Engine (`answer_engine.py`)

Template-based system for screening question answers with company-specific context for 60+ companies. Two-tier priority:
1. User overrides in `data/answers.yaml`
2. Built-in templates using company mission/vibe context

### 7. Outreach Generator

Generates personalized LinkedIn messages using profile data + company context from a dictionary of 25+ company mission statements. Builds LinkedIn People Search URLs for finding recruiters and hiring managers.

## Design System: Neumorphic UI

The interface uses a soft, tactile neumorphic design language:

- **Background**: Cool blue-gray `#e0e5ec` everywhere
- **Raised elements** (cards, buttons): Dual outer shadows — dark `#a3b1c6` bottom-right, white `#ffffff` top-left
- **Pressed elements** (inputs, active states): Dual inset shadows — same colors but inverted
- **Sidebar**: Dark neumorphic variant (`#2d3440` base) with matching dark shadow pairs
- **No borders anywhere** — all separation through shadows only
- **Typography**: Geist (UI), Newsreader (display), JetBrains Mono (stats)
- **Accent**: `#6c63ff` indigo-violet primary, amber/emerald/rose semantics

Key neumorphic patterns:
```css
--neu-raised:  6px 6px 14px #a3b1c6, -6px -6px 14px #ffffff;
--neu-pressed: inset 4px 4px 8px #a3b1c6, inset -4px -4px 8px #ffffff;
```

## Database Schema

SQLite with WAL journal mode. Four tables:
- `profile` — Singleton (id=1), stores all autofill data
- `resumes` — File references with role tags for automatic selection
- `jobs` — ~8,480 indexed jobs with relevancy scores
- `applications` — Pipeline tracker with 6 status stages

Unique constraint: `(greenhouse_id, company)` prevents duplicates across scraper runs.

Migration pattern: `ALTER TABLE ... ADD COLUMN` wrapped in try/except for idempotent column additions.

## Chrome Extension

Manifest V3 extension that:
1. Reads profile + resume data from `GET /api/profile`
2. Injects content script on job application pages
3. Auto-fills form fields by matching label text to profile fields
4. Sends screening questions to `POST /api/answers` for smart responses
5. Tracks applied jobs via `POST /api/track/:id`

## File Structure

```
job_app/
  app.py                 FastAPI application (25 routes)
  database.py            SQLite layer (aiosqlite)
  scraper_service.py     Multi-ATS scraper (6 platforms)
  bigtech_scrapers.py    Apple/Amazon/Netflix scrapers
  apify_service.py       LinkedIn/Indeed via Apify
  relevancy_engine.py    Scoring + recruiter + outreach
  answer_engine.py       Smart Q&A for screening questions
  company_config.json    250+ company slug mappings
  requirements.txt       Python dependencies
  data/
    answers.yaml         User answer overrides
    apify_config.yaml    Apify token + actor config
    resumes/             Uploaded resume files
    jobs.db              SQLite database
  static/
    app.css              Neumorphic design system
  templates/
    base.html            Shell (sidebar + topbar)
    dashboard.html       Job browser + match rings
    applications.html    Pipeline tracker + KPI strip
    profile.html         Form + completeness meter
  extension/
    manifest.json        Chrome Manifest V3
    background.js        Service worker
    content.js           DOM injection auto-filler
    popup.html/js        Extension popup
```

## Current State

- **8,480 jobs indexed** across 250+ companies
- **US-only filter active** — foreign jobs purged
- **Relevancy scoring works** but needs profile data (current_title, skills) to be meaningful
- **Neumorphic UI v3** implemented across all 4 pages
- **3 scrapers active**: ATS, Big Tech (Apple/Amazon/Netflix), Apify LinkedIn
- **3 scrapers need Playwright**: Meta, Google, Microsoft
