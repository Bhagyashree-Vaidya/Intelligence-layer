# JobPilot Intelligence Layer — Playbook

## Quick Start

```bash
# 1. Install dependencies
cd job_app
pip install -r requirements.txt

# 2. Start the server
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload

# 3. Open in browser
open http://127.0.0.1:8000
```

The first launch auto-creates the SQLite database with empty tables. Fill in your profile at `/profile` before scraping — the relevancy engine needs `current_title` and `skills` to score jobs meaningfully.

## Day-to-Day Workflow

### Morning Routine

1. **Open dashboard** → Click **Fetch new jobs** (runs all scrapers)
2. **Review top matches** → Jobs sorted by relevancy score (green = 75%+)
3. **Click Apply** → Opens company page, Chrome extension auto-fills
4. **Track applications** → `/applications` page shows your pipeline

### Profile Setup (Do This First)

Navigate to `/profile` and fill in:

| Field | Why It Matters |
|-------|---------------|
| **Current Title** | Powers the title-match scoring (40pts). Set to your target role. |
| **Skills** | Comma-separated list. Each skill is matched against job descriptions (35pts). |
| **City / State** | Location preference scoring (15pts). |
| **Years of Experience** | Checked against seniority level in job titles (10pts). |
| **Cover Letter** | Auto-pasted by Chrome extension on application forms. |

The completeness meter on the right sidebar shows what's missing.

### Scraping Strategy

**Full scrape** (`POST /api/scrape/all`):
- Runs ATS (250+ companies) → Big Tech → Apify LinkedIn in sequence
- Auto-rescores all jobs after scraping
- Takes 2-5 minutes depending on Apify queue

**Targeted scrape options** (from the scrape modal):
- **Look back**: 24h / 48h / 7 days — filters by `updated_at`
- **Role filters**: Comma-separated keys: `pm,swe,ux,tpm,presales`

**Freshness controls** on the dashboard filter bar:
- 24h / 48h / 7 days / 30 days / All

### Rescoring Jobs

Click **Rescore** in the topbar to re-run relevancy scoring against your current profile. Do this after:
- Updating your profile (especially skills or current_title)
- Bulk importing new jobs
- Changing role focus

### Finding Recruiters

Each job card has two action buttons:
- **Recruiter** → Opens LinkedIn People Search for "recruiter {company}"
- **Message** → Generates a personalized outreach message with:
  - Your background and top 3 skills
  - Company-specific mission hook (25+ companies)
  - LinkedIn links to find the recruiter and hiring manager

Copy the message, paste on LinkedIn, personalize the name.

### Application Tracking

The `/applications` page tracks your pipeline:

| Stage | Pipeline Bar | Meaning |
|-------|-------------|---------|
| Saved | 0/5 segments | Bookmarked, not applied |
| Applied | 1/5 segments | Application submitted |
| Screen | 2/5 segments | Recruiter screen scheduled |
| Interview | 3/5 segments | Interview loop active |
| Offer | 4/5 segments | Offer received |
| Rejected | 5/5 segments | Closed |

Change status via the dropdown on each row's status chip.

KPI strip shows: Total sent, Reply rate, Interviews, Offers, Streak.

## Chrome Extension Setup

```
1. Open chrome://extensions
2. Enable Developer Mode (toggle in top-right)
3. Click "Load unpacked"
4. Select the job_app/extension/ folder
5. Pin the JobPilot icon in your toolbar
```

The extension calls `http://127.0.0.1:8000/api/profile` to get autofill data. The server must be running.

**How auto-fill works:**
- Content script scans the page for form fields
- Matches field labels to profile data (first_name, email, etc.)
- Fills in values automatically
- Sends screening questions to the answer engine
- Reports application via `POST /api/track/:id`

## Apify Configuration

### Setup

Edit `job_app/data/apify_config.yaml`:

```yaml
token: apify_api_YOUR_TOKEN_HERE

actors:
  linkedin:
    id: curious_coder~linkedin-jobs-scraper
    scrapeCompany: false
  indeed:
    id: misceres~indeed-scraper
```

Get your token from: https://console.apify.com/account/integrations

### LinkedIn Actor Notes

The `curious_coder~linkedin-jobs-scraper` actor takes LinkedIn search URLs, not raw keywords. JobPilot builds these automatically:

```
https://www.linkedin.com/jobs/search/?keywords={term}&location=United+States&f_TPR=r604800&f_E=2%2C3%2C4
```

- `f_TPR=r604800` = posted in last 7 days
- `f_E=2,3,4` = Associate, Mid-Senior, Director level

## Customizing Answer Templates

Edit `job_app/data/answers.yaml` to override default screening question answers:

```yaml
# Pattern-matched questions
- pattern: "why.*want.*work"
  answer: "Your custom 'why this company' answer..."

- pattern: "salary|compensation"
  answer: "150,000"

- pattern: "years.*experience"
  answer: "6"
```

The answer engine checks `answers.yaml` first, then falls back to company-specific templates for 60+ companies.

## Adding New Companies

### ATS-based companies

Edit `job_app/company_config.json`:

```json
{
  "company_name": {
    "ats": "greenhouse",
    "slug": "companyname"
  }
}
```

Supported ATS values: `greenhouse`, `lever`, `ashby`, `smartrecruiters`, `workday`, `workable`.

### Finding the slug

- Greenhouse: `boards.greenhouse.io/{slug}`
- Lever: `jobs.lever.co/{slug}`
- Ashby: `jobs.ashbyhq.com/{slug}`

## Troubleshooting

### All jobs scored 0%

Your profile is missing `current_title` and/or `skills`. Fill them in at `/profile`, then click **Rescore**.

### Apple scraper returns no results

Apple uses SSR hydration with nested JSON escaping. If the page structure changes, the `unescape_js_string()` function in `bigtech_scrapers.py` may need updating. Check the raw HTML for `window.__staticRouterHydrationData`.

### Foreign jobs appearing

The US location filter should catch most cases. If you see foreign jobs:
1. Check if the location string matches a known pattern
2. Add the country/city to `_FOREIGN_PAT` in `bigtech_scrapers.py`
3. Run: `DELETE FROM jobs WHERE location LIKE '%Bangalore%'`

### Apify scrape fails

- Verify your token in `data/apify_config.yaml`
- Check Apify dashboard for actor run status
- The actor may have usage limits on the free tier

### Workday companies return empty

Some Workday instances (Uber, DoorDash, Coinbase, Snap, Box, Canva, Bumble) block `httpx` requests. These need Playwright-based scraping (not yet implemented).

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite over Postgres | Zero-config, single-user app, WAL mode handles concurrent reads |
| No ORM (raw SQL) | Simpler debugging, full control over upsert logic |
| httpx over requests | Async support matches FastAPI's async handlers |
| No React/Vue | Server-rendered Jinja2 keeps the stack simple; JS only for interactivity |
| Neumorphic CSS | Distinctive visual identity; single CSS file, no build step |
| Regex scoring over ML | Deterministic, explainable, fast; no training data needed |
| Apify over direct scraping | LinkedIn/Indeed actively block; paid actors are more reliable |

## Performance Notes

- **Scraping 250+ companies**: ~90 seconds (ATS APIs are fast)
- **Rescoring 8,480 jobs**: ~2 seconds (pure Python regex)
- **Page load**: <200ms (SQLite + Jinja2 render)
- **Database size**: ~15MB for 8,480 jobs with descriptions
