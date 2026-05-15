# JobPilot Intelligence Layer — Knowledge Graph

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        JobPilot Platform                            │
│                                                                     │
│  ┌───────────────┐    ┌──────────────┐    ┌─────────────────────┐  │
│  │  Chrome Ext.   │───▶│  FastAPI App  │◀──│  Neumorphic UI      │  │
│  │  (Auto-fill)   │    │  (app.py)     │    │  (Jinja2 + CSS)     │  │
│  └───────────────┘    └──────┬───────┘    └─────────────────────┘  │
│                              │                                      │
│          ┌───────────────────┼───────────────────┐                  │
│          ▼                   ▼                   ▼                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐         │
│  │  Scraper      │  │  Relevancy   │  │  Answer Engine    │         │
│  │  Layer        │  │  Engine      │  │  (Smart Q&A)      │         │
│  └──────┬───────┘  └──────────────┘  └──────────────────┘         │
│         │                                                           │
│  ┌──────┴────────────────────────────────┐                         │
│  │         Data Ingestion Pipeline        │                         │
│  │                                        │                         │
│  │  ┌────────────┐  ┌────────────────┐   │                         │
│  │  │ ATS APIs   │  │ Big Tech Sites │   │                         │
│  │  │ Greenhouse │  │ Apple          │   │                         │
│  │  │ Lever      │  │ Amazon         │   │                         │
│  │  │ Ashby      │  │ Meta *         │   │                         │
│  │  │ SmartRecr. │  │ Google *       │   │                         │
│  │  │ Workday    │  │ Microsoft *    │   │                         │
│  │  │ Workable   │  │ Netflix        │   │                         │
│  │  └────────────┘  └────────────────┘   │                         │
│  │                                        │                         │
│  │  ┌───────────────────────────────────┐│                         │
│  │  │ Apify (paid scrapers)             ││                         │
│  │  │ LinkedIn (curious_coder~...)      ││                         │
│  │  │ Indeed   (misceres~...)           ││                         │
│  │  └───────────────────────────────────┘│                         │
│  └───────────────────────────────────────┘                         │
│                              │                                      │
│                              ▼                                      │
│                     ┌──────────────┐                                │
│                     │  SQLite DB   │                                │
│                     │  (WAL mode)  │                                │
│                     └──────────────┘                                │
│                                                                     │
│  * = requires Playwright (BROWSER_ONLY)                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Entity Relationship Map

```
PROFILE (1)
  ├── first_name, last_name, email, phone
  ├── address, city, state, zip_code, country
  ├── current_company, current_title, years_experience
  ├── linkedin, website, github
  ├── skills (comma-separated → relevancy scoring)
  ├── work_auth, sponsorship
  ├── gender, veteran, disability (EEO)
  ├── cover_letter_default
  └── education (JSON)
       │
       │ one-to-many
       ▼
RESUMES (N)
  ├── filename, original_name
  ├── role_tags (comma-separated: "pm,swe,ux")
  └── is_default (boolean)
       │
       │ referenced by
       ▼
APPLICATIONS (N)
  ├── job_id → JOBS.id
  ├── resume_id → RESUMES.id (nullable)
  ├── status: saved|applied|screen|interview|offer|rejected
  ├── applied_at (ISO timestamp)
  └── notes
       │
       │ references
       ▼
JOBS (N) — ~8,480 indexed
  ├── greenhouse_id (external unique ID)
  ├── company, title, location, department
  ├── url, description
  ├── employment_type, salary_range
  ├── updated_at, first_published, scraped_at
  ├── relevancy_score (0-100, computed)
  └── keywords_matched (JSON array, computed)
```

## Module Dependency Graph

```
app.py ──────────────┬──▶ database.py ──▶ SQLite (aiosqlite)
  │                  │
  ├──▶ scraper_service.py ──▶ httpx (async)
  │     └── ATS APIs: Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Workable
  │
  ├──▶ bigtech_scrapers.py ──▶ httpx
  │     └── Apple (SSR hydration), Amazon, Netflix
  │     └── US location filter (regex: 50 states + 60 foreign exclusions)
  │
  ├──▶ apify_service.py ──▶ httpx → Apify REST API
  │     └── LinkedIn (curious_coder~linkedin-jobs-scraper)
  │     └── Indeed (misceres~indeed-scraper)
  │     └── Config: data/apify_config.yaml
  │
  ├──▶ relevancy_engine.py (pure Python, no I/O)
  │     ├── score_job()        → {relevancy_score, keywords_matched, color}
  │     ├── get_recruiter_urls() → LinkedIn People Search URLs
  │     ├── generate_outreach_message() → personalized message draft
  │     └── compute_freshness()  → {hours_ago, label, badge_color}
  │
  ├──▶ answer_engine.py ──▶ pyyaml
  │     └── Template-based Q&A for 60+ company contexts
  │     └── Reads: data/answers.yaml (user overrides)
  │
  └──▶ templates/ (Jinja2)
        ├── base.html        → shell (neumorphic sidebar + topbar)
        ├── dashboard.html   → job browser with match rings
        ├── applications.html → pipeline tracker with KPI strip
        └── profile.html     → form + completeness meter
```

## Relevancy Scoring Algorithm

```
Total Score: 0-100 points

  ┌─────────────────────────────────────────────────────┐
  │ TITLE MATCH (0-40 pts)                              │
  │  ├── 40 pts: job title matches user's role family   │
  │  ├── 15 pts: role family found in description only  │
  │  └──  0 pts: no match                               │
  │                                                     │
  │ ROLE_FAMILIES dictionary maps titles like            │
  │ "product manager" → 10+ regex patterns              │
  │ (pm, tpm, apm, spm, gpm, product lead, etc.)        │
  ├─────────────────────────────────────────────────────┤
  │ SKILLS MATCH (0-35 pts)                             │
  │  ├── ratio = matched_skills / user_skills            │
  │  ├── score = round(35 * ratio)                       │
  │  └── SKILL_ALIASES: 25+ skills with regex variants  │
  │      e.g. "python" → [\bpython\b]                   │
  │      e.g. "javascript" → [\bjs\b, \btypescript\b]  │
  ├─────────────────────────────────────────────────────┤
  │ EXPERIENCE LEVEL (0-10 pts)                         │
  │  ├── 10 pts: user years within seniority range      │
  │  ├──  5 pts: within 2 years of range boundary       │
  │  └──  0 pts: out of range                           │
  │                                                     │
  │ SENIORITY_MAP: intern(0-0), junior(0-2),            │
  │ senior(5-15), staff(7-20), principal(10-25)         │
  ├─────────────────────────────────────────────────────┤
  │ LOCATION (0-15 pts)                                 │
  │  ├── 15 pts: user city matches                       │
  │  ├── 12 pts: "remote" in location                    │
  │  ├── 10 pts: user state matches                      │
  │  └──  3 pts: US but different area                   │
  └─────────────────────────────────────────────────────┘

  COLOR:  >=75 green  |  >=50 yellow  |  >=30 orange  |  <30 gray
```

## Data Flow: Job Scraping Pipeline

```
User clicks "Fetch new jobs"
         │
         ▼
  POST /api/scrape/all
         │
         ├── 1. ATS Scrape (scraper_service.py)
         │     ├── Load company_config.json (250+ companies)
         │     ├── For each company, call ATS-specific endpoint
         │     ├── Filter: title matches ROLE_FILTERS
         │     ├── Filter: is_us_location() → regex positive + negative
         │     └── Output: list[dict] with normalized fields
         │
         ├── 2. Big Tech Scrape (bigtech_scrapers.py)
         │     ├── Apple: parse SSR hydration JSON (unescape_js_string)
         │     ├── Amazon: amazon.jobs JSON API
         │     ├── Netflix: Lever-based public API
         │     └── All: US-only filter applied
         │
         ├── 3. Apify LinkedIn (apify_service.py)
         │     ├── Build LinkedIn search URL with f_TPR=r604800
         │     ├── POST to Apify actor, wait for results
         │     ├── Flatten: {id, company, title, location, ...}
         │     └── US-only filter applied
         │
         ├── 4. Upsert to SQLite
         │     └── ON CONFLICT(greenhouse_id, company) DO UPDATE
         │
         └── 5. Rescore All Jobs
               ├── Load profile from DB
               ├── For each job: relevancy_engine.score_job()
               └── UPDATE jobs SET relevancy_score, keywords_matched
```

## API Endpoint Map

```
PAGES (GET, HTML)
  /                    → Dashboard (job browser)
  /applications        → Application tracker
  /profile             → Profile & resume management

PROFILE API
  GET  /api/profile           → Chrome extension reads autofill data
  POST /api/profile           → Save profile form

RESUME API
  POST /api/resumes/upload    → Upload PDF/DOCX
  POST /api/resumes/:id/delete → Delete resume

SCRAPER API
  POST /api/scrape            → ATS-only scrape
  POST /api/scrape/bigtech    → Big Tech scrape
  POST /api/scrape/apify      → LinkedIn/Indeed via Apify
  POST /api/scrape/all        → Run ALL scrapers + rescore
  GET  /api/scrape/status     → Poll scrape progress

APPLICATION TRACKING
  POST /api/track/:job_id          → Save/track a job
  POST /api/applications/:id/status → Update application status

INTELLIGENCE
  POST /api/rescore                → Rescore all jobs
  GET  /api/jobs/:id/recruiter     → LinkedIn recruiter search URLs
  POST /api/jobs/:id/message       → Generate outreach message
  POST /api/answers                → Smart screening Q&A
  GET  /api/answers/config         → Read answers.yaml
```

## Technology Stack

```
BACKEND                          FRONTEND
──────────────────────           ──────────────────────
Python 3.13                      Jinja2 templates
FastAPI (async ASGI)             Neumorphic CSS (custom)
aiosqlite (SQLite + WAL)        Geist sans + Newsreader serif
httpx (async HTTP)               JetBrains Mono (code)
PyYAML (config)                  Vanilla JS (no framework)
Apify REST API                   SVG icons (inline)

CHROME EXTENSION                 INFRASTRUCTURE
──────────────────────           ──────────────────────
Manifest V3                      SQLite (WAL journal)
content.js (DOM injection)       Local dev (uvicorn)
background.js (service worker)   No Docker required
popup.html (status panel)        No external DB needed
```
