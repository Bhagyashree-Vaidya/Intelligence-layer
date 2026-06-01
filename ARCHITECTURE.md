# JobPilot v5 — Career Intelligence Platform Architecture

> From job scraper to AI-powered career intelligence engine.
> Single-user, startup-friendly, no Kubernetes, no microservices.
> Social signals first — the best opportunities appear socially before ATS saturation.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Tech Stack](#tech-stack)
3. [Repository Structure](#repository-structure)
4. [Database Schema](#database-schema)
5. [Backend Architecture](#backend-architecture)
6. [Worker Architecture](#worker-architecture)
7. [AI Orchestration](#ai-orchestration)
8. [Scraping Architecture](#scraping-architecture)
9. [Feature: Job Intelligence](#feature-job-intelligence)
10. [Feature: Application Tracker](#feature-application-tracker)
11. [Feature: LinkedIn Hiring Intelligence](#feature-linkedin-hiring-intelligence)
12. [Feature: Memory + Learning System](#feature-memory--learning-system)
13. [Feature: Skill Graph Engine](#feature-skill-graph-engine)
14. [Feature: Resume Intelligence](#feature-resume-intelligence)
15. [Frontend Architecture](#frontend-architecture)
16. [Infrastructure + Deployment](#infrastructure--deployment)
17. [Security](#security)
18. [Local Development](#local-development)
19. [Migration from v4](#migration-from-v4)
20. [Phase Plan](#phase-plan)

---

## System Overview

```
hire.shreevaidya.com (Vercel)
        │
        ▼
jobs.shreevaidya.com (Fly.io)
  ┌─────┴─────────────────────────────┐
  │  Fastify API Server               │
  │  ├── REST routes                   │
  │  ├── WebSocket (scrape progress)   │
  │  └── AI orchestrator               │
  └──────────┬────────────────────────┘
             │
     ┌───────┼───────┐
     ▼       ▼       ▼
  Redis    Supabase  External APIs
  (Queue)  (Postgres) (Claude, OpenAI,
     │                 Apify, Firecrawl,
     ▼                 Browserbase)
  BullMQ Workers
  ├── scrape-jobs
  ├── enrich-job
  ├── score-job
  ├── generate-resume
  ├── linkedin-intel
  ├── apply-job
  └── learn-outcome
```

### Core Loop

```
Observe → Analyze → Score → Strategize → Execute → Learn → Improve
   │         │        │         │           │        │        │
 scrape   enrich    score    prioritize   apply   track    retrain
 jobs     with AI   against  + recommend  + fill  outcome  scoring
          metadata  profile  next moves   forms   signals  weights
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui | App Router, RSC, great DX, instant deploys on Vercel |
| Backend | **FastAPI + Python 3.13** | Already running, async-native, Pydantic validation, OpenAPI docs free |
| Database | Supabase (Postgres 15 + pgvector) | Managed, real-time, RLS, vector search built-in |
| Queue | **Redis + arq** | Lightweight async Python job queue, Redis persistence, retries, cron |
| AI - Reasoning | Claude API (claude-sonnet-4-20250514) | Best at nuanced analysis, long-context, structured reasoning |
| AI - Extraction | OpenAI (gpt-4o-mini) | Fast, cheap, great at structured JSON extraction |
| AI - Embeddings | OpenAI (text-embedding-3-small) | 1536-dim vectors, cheap at scale, pgvector-compatible |
| Browser | **Playwright (Python)** + Browserbase | First-class Python SDK, Browserbase for cloud sessions |
| Scraping | Apify, Firecrawl, httpx | Anti-bot managed actors, structured extraction, async HTTP |
| Validation | **Pydantic v2** | Already in use, fastest Python validation, JSON schema gen |
| Logging | **structlog** | Structured JSON logs, async-friendly, production-grade |
| Container | Docker | Already working on Fly.io, no changes needed |

---

## Repository Structure

```
intelligence-layer/
├── frontend/                    # Next.js app → Vercel
│   ├── src/
│   │   ├── app/                 # App Router pages
│   │   │   ├── page.tsx         # Dashboard / Job Intelligence
│   │   │   ├── applied/         # Application Tracker
│   │   │   ├── signals/         # Social Signals (LinkedIn Intelligence)
│   │   │   ├── skills/          # Skill Graph
│   │   │   ├── profile/         # Profile + Resumes
│   │   │   └── layout.tsx       # Root layout + sidebar
│   │   ├── components/
│   │   │   ├── ui/              # shadcn/ui primitives
│   │   │   ├── jobs/            # Job cards, filters, scoring rings
│   │   │   ├── applications/    # Pipeline tracker, status cards
│   │   │   ├── signals/         # Social signal cards, outreach
│   │   │   ├── skills/          # Skill graph visualizations
│   │   │   └── shared/          # Sidebar, TopBar, MatchRing
│   │   ├── lib/
│   │   │   ├── api.ts           # Typed API client
│   │   │   ├── hooks.ts         # React hooks
│   │   │   └── utils.ts         # Helpers
│   │   └── styles/
│   │       └── globals.css      # Tailwind + custom tokens
│   ├── public/
│   ├── extension/               # Chrome Manifest V3 extension
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── package.json
│
├── backend/                     # FastAPI → Fly.io (PYTHON — no rewrite)
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + lifespan
│   │   ├── config.py            # Pydantic Settings (env validation)
│   │   ├── logger.py            # structlog setup
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── jobs.py          # CRUD + search + scoring
│   │   │   ├── profile.py       # Profile + resumes
│   │   │   ├── scraper.py       # Scrape triggers + status + WS
│   │   │   ├── applications.py  # Application tracking
│   │   │   ├── signals.py       # Social signals (LinkedIn intel)
│   │   │   ├── skills.py        # Skill graph queries
│   │   │   └── answers.py       # Answer generation
│   │   ├── services/
│   │   │   ├── ai/
│   │   │   │   ├── orchestrator.py    # Route to Claude vs OpenAI
│   │   │   │   ├── claude_client.py   # anthropic SDK wrapper
│   │   │   │   ├── openai_client.py   # openai SDK wrapper
│   │   │   │   ├── embeddings.py      # Vector gen + pgvector search
│   │   │   │   └── prompts/           # Versioned prompt templates
│   │   │   │       ├── enrich_job.py
│   │   │   │       ├── score_job.py
│   │   │   │       ├── classify_signal.py
│   │   │   │       ├── resume_gen.py
│   │   │   │       ├── cover_letter.py
│   │   │   │       └── outreach_gen.py
│   │   │   ├── scrapers/
│   │   │   │   ├── greenhouse.py      # Greenhouse JSON API
│   │   │   │   ├── lever.py           # Lever JSON API
│   │   │   │   ├── ashby.py           # Ashby JSON API
│   │   │   │   ├── workday.py         # Workday hidden API
│   │   │   │   ├── smartrecruiters.py
│   │   │   │   ├── workable.py
│   │   │   │   ├── bigtech.py         # Apple, Google, Meta, Amazon
│   │   │   │   ├── apify_runner.py    # Apify actor runner
│   │   │   │   ├── firecrawl.py       # Firecrawl extraction
│   │   │   │   ├── linkedin_posts.py  # LinkedIn social signal scraper
│   │   │   │   └── registry.py        # Source registry + config
│   │   │   ├── scoring/
│   │   │   │   ├── relevancy.py       # Multi-dimensional scoring
│   │   │   │   ├── ats_score.py       # ATS keyword match
│   │   │   │   ├── visa_score.py      # Visa sponsorship likelihood
│   │   │   │   └── signal_score.py    # Social signal priority scoring
│   │   │   ├── resume/
│   │   │   │   ├── generator.py       # AI resume variant generator
│   │   │   │   ├── optimizer.py       # ATS keyword optimizer
│   │   │   │   └── renderer.py        # PDF rendering
│   │   │   ├── signals/
│   │   │   │   ├── classifier.py      # AI post classification
│   │   │   │   ├── people.py          # HM/recruiter discovery
│   │   │   │   └── outreach.py        # Message generation
│   │   │   ├── learning/
│   │   │   │   ├── memory.py          # Persistent memory + RAG
│   │   │   │   ├── feedback.py        # Outcome feedback processor
│   │   │   │   └── patterns.py        # Pattern detection
│   │   │   └── skills/
│   │   │       ├── graph.py           # Skill graph builder
│   │   │       ├── trends.py          # Trending skills detector
│   │   │       └── gaps.py            # Gap analysis
│   │   ├── workers/
│   │   │   ├── __init__.py            # arq worker bootstrap
│   │   │   ├── scrape.py             # Job scraping worker
│   │   │   ├── enrich.py             # AI job enrichment
│   │   │   ├── score.py              # Scoring pipeline
│   │   │   ├── signals.py            # Social signal collection + classify
│   │   │   ├── resume.py             # Resume generation
│   │   │   ├── apply.py              # Application execution (Playwright)
│   │   │   └── learn.py              # Learning/feedback
│   │   ├── db/
│   │   │   ├── client.py             # Supabase client (existing)
│   │   │   └── queries/              # Domain-specific query modules
│   │   │       ├── jobs.py
│   │   │       ├── applications.py
│   │   │       ├── signals.py
│   │   │       ├── skills.py
│   │   │       └── memory.py
│   │   └── data/                     # Config files
│   │       ├── company_config.json
│   │       ├── apify_config.yaml
│   │       └── answers.yaml
│   ├── scripts/
│   │   └── migrate.py               # SQL migrations
│   ├── Dockerfile
│   ├── fly.toml
│   ├── requirements.txt
│   └── .env.example
│
├── docker-compose.yml           # Local dev (Redis + app)
├── ARCHITECTURE.md
├── .gitignore
└── README.md
```

---

## Database Schema

### Migration 001 — Base (migrate from v4)

```sql
-- ══════════════════════════════════════════════════════════════
-- JobPilot v5 — Base Schema
-- ══════════════════════════════════════════════════════════════

-- Profile (singleton, id=1)
CREATE TABLE profile (
    id                SERIAL PRIMARY KEY,
    first_name        TEXT DEFAULT '',
    last_name         TEXT DEFAULT '',
    email             TEXT DEFAULT '',
    phone             TEXT DEFAULT '',
    address           TEXT DEFAULT '',
    city              TEXT DEFAULT '',
    state             TEXT DEFAULT '',
    zip_code          TEXT DEFAULT '',
    country           TEXT DEFAULT 'United States',
    linkedin          TEXT DEFAULT '',
    website           TEXT DEFAULT '',
    github            TEXT DEFAULT '',
    current_company   TEXT DEFAULT '',
    current_title     TEXT DEFAULT '',
    years_experience  INTEGER DEFAULT 0,
    education         JSONB DEFAULT '[]',
    skills            TEXT DEFAULT '',
    target_roles      TEXT[] DEFAULT '{}',       -- NEW: target role keywords
    target_locations  TEXT[] DEFAULT '{}',       -- NEW: preferred locations
    visa_required     BOOLEAN DEFAULT FALSE,     -- NEW: needs sponsorship
    cover_letter_default TEXT DEFAULT '',
    work_auth         TEXT DEFAULT 'Authorized',
    sponsorship       TEXT DEFAULT 'No',
    gender            TEXT DEFAULT '',
    race              TEXT DEFAULT '',
    veteran           TEXT DEFAULT '',
    disability        TEXT DEFAULT '',
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO profile (id) VALUES (1) ON CONFLICT DO NOTHING;

-- Companies (normalized)
CREATE TABLE companies (
    id                SERIAL PRIMARY KEY,
    name              TEXT UNIQUE NOT NULL,
    domain            TEXT,
    careers_url       TEXT,
    ats_platform      TEXT,                     -- greenhouse, lever, workday, etc.
    size_band         TEXT,                     -- startup, mid, large, enterprise
    industry          TEXT,
    visa_friendly     BOOLEAN,
    hiring_velocity   INTEGER DEFAULT 0,        -- jobs posted in last 30 days
    response_rate     REAL DEFAULT 0,           -- historical response rate
    avg_time_to_hear  INTEGER,                  -- days
    notes             TEXT DEFAULT '',
    metadata          JSONB DEFAULT '{}',
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs (enriched)
CREATE TABLE jobs (
    id                SERIAL PRIMARY KEY,
    external_id       TEXT,                     -- greenhouse_id, lever_id, etc.
    company_id        INTEGER REFERENCES companies(id),
    company_name      TEXT NOT NULL,            -- denormalized for speed
    source            TEXT NOT NULL,            -- greenhouse, lever, linkedin, etc.
    title             TEXT NOT NULL,
    location          TEXT DEFAULT '',
    remote_type       TEXT DEFAULT '',          -- remote, hybrid, onsite
    department        TEXT DEFAULT '',
    url               TEXT DEFAULT '',
    description       TEXT DEFAULT '',
    salary_min        INTEGER,
    salary_max        INTEGER,
    salary_currency   TEXT DEFAULT 'USD',
    employment_type   TEXT DEFAULT '',          -- full-time, contract, intern
    posted_at         TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ,
    scraped_at        TIMESTAMPTZ DEFAULT NOW(),

    -- AI-enriched fields (populated by enrich worker)
    enriched          BOOLEAN DEFAULT FALSE,
    pm_keywords       TEXT[] DEFAULT '{}',
    required_skills   TEXT[] DEFAULT '{}',
    preferred_skills  TEXT[] DEFAULT '{}',
    inferred_seniority TEXT DEFAULT '',         -- entry, mid, senior, staff, director
    pm_specialization TEXT DEFAULT '',          -- growth, platform, data, technical, etc.
    product_area      TEXT DEFAULT '',
    technical_depth   INTEGER DEFAULT 0,       -- 0-100
    leadership_score  INTEGER DEFAULT 0,       -- 0-100
    stakeholder_intensity INTEGER DEFAULT 0,   -- 0-100
    execution_intensity INTEGER DEFAULT 0,     -- 0-100
    strategic_intensity INTEGER DEFAULT 0,     -- 0-100
    visa_likelihood   INTEGER DEFAULT 0,       -- 0-100
    enrichment_raw    JSONB DEFAULT '{}',      -- full AI response stored

    -- Scoring (populated by score worker)
    scored            BOOLEAN DEFAULT FALSE,
    overall_fit       INTEGER DEFAULT 0,       -- 0-100
    ats_score         INTEGER DEFAULT 0,
    pm_transition_fit INTEGER DEFAULT 0,
    response_probability INTEGER DEFAULT 0,
    resume_alignment  INTEGER DEFAULT 0,
    technical_match   INTEGER DEFAULT 0,
    leadership_match  INTEGER DEFAULT 0,
    missing_skills    TEXT[] DEFAULT '{}',
    resume_recommendations TEXT DEFAULT '',
    recommended_resume_id INTEGER,
    scoring_raw       JSONB DEFAULT '{}',      -- full scoring breakdown

    -- People intelligence
    hiring_manager    TEXT DEFAULT '',
    hm_linkedin       TEXT DEFAULT '',
    recruiter_name    TEXT DEFAULT '',
    recruiter_linkedin TEXT DEFAULT '',
    recruiter_email   TEXT DEFAULT '',
    team_name         TEXT DEFAULT '',
    alumni_overlaps   TEXT[] DEFAULT '{}',
    referral_likelihood INTEGER DEFAULT 0,

    -- Embedding for semantic search
    embedding         vector(1536),

    UNIQUE(external_id, source)
);

CREATE INDEX idx_jobs_company ON jobs(company_id);
CREATE INDEX idx_jobs_source ON jobs(source);
CREATE INDEX idx_jobs_overall_fit ON jobs(overall_fit DESC);
CREATE INDEX idx_jobs_posted ON jobs(posted_at DESC);
CREATE INDEX idx_jobs_enriched ON jobs(enriched) WHERE enriched = FALSE;
CREATE INDEX idx_jobs_scored ON jobs(scored) WHERE scored = FALSE;
CREATE INDEX idx_jobs_embedding ON jobs USING ivfflat (embedding vector_cosine_ops);

-- Resumes
CREATE TABLE resumes (
    id                SERIAL PRIMARY KEY,
    version_name      TEXT NOT NULL,            -- "pm_resume_v14", "technical_pm_v3"
    filename          TEXT NOT NULL,
    original_name     TEXT NOT NULL,
    role_tags         TEXT[] DEFAULT '{}',
    target_companies  TEXT[] DEFAULT '{}',      -- optimized for these companies
    ats_keywords      TEXT[] DEFAULT '{}',      -- keywords this version targets
    is_default        BOOLEAN DEFAULT FALSE,
    is_ai_generated   BOOLEAN DEFAULT FALSE,
    parent_resume_id  INTEGER REFERENCES resumes(id),
    generation_prompt TEXT DEFAULT '',          -- prompt used to generate
    uploaded_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Applications (enhanced tracking)
CREATE TABLE applications (
    id                SERIAL PRIMARY KEY,
    job_id            INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id         INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    status            TEXT DEFAULT 'saved',
    -- Status flow: saved → applied → oa_sent → screen → interview → offer → accepted
    --              Any stage can → rejected | withdrawn
    applied_at        TIMESTAMPTZ,
    status_changed_at TIMESTAMPTZ DEFAULT NOW(),
    cover_letter_used TEXT DEFAULT '',
    outreach_sent     BOOLEAN DEFAULT FALSE,
    outreach_channel  TEXT DEFAULT '',          -- linkedin, email, referral
    recruiter_response TEXT DEFAULT '',
    rejection_reason  TEXT DEFAULT '',
    oa_link           TEXT DEFAULT '',          -- online assessment link
    interview_rounds  INTEGER DEFAULT 0,
    follow_up_date    TIMESTAMPTZ,
    notes             TEXT DEFAULT '',
    metadata          JSONB DEFAULT '{}',

    UNIQUE(job_id)                              -- one application per job
);

CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_applied ON applications(applied_at DESC);
```

### Migration 002 — LinkedIn Intelligence

```sql
-- LinkedIn hiring posts
CREATE TABLE linkedin_posts (
    id                SERIAL PRIMARY KEY,
    linkedin_url      TEXT UNIQUE,
    author_name       TEXT NOT NULL,
    author_title      TEXT DEFAULT '',
    author_company    TEXT DEFAULT '',
    author_linkedin   TEXT DEFAULT '',
    content           TEXT NOT NULL,
    posted_at         TIMESTAMPTZ,
    scraped_at        TIMESTAMPTZ DEFAULT NOW(),
    likes             INTEGER DEFAULT 0,
    comments          INTEGER DEFAULT 0,
    reposts           INTEGER DEFAULT 0,

    -- AI-classified
    classified        BOOLEAN DEFAULT FALSE,
    hiring_intent     INTEGER DEFAULT 0,       -- 0-100
    role_mentioned    TEXT DEFAULT '',
    company_mentioned TEXT DEFAULT '',
    seniority_level   TEXT DEFAULT '',
    is_recruiter      BOOLEAN DEFAULT FALSE,
    outreach_viability INTEGER DEFAULT 0,      -- 0-100
    urgency_score     INTEGER DEFAULT 0,       -- 0-100
    classification_raw JSONB DEFAULT '{}',

    -- Generated outreach
    outreach_message  TEXT DEFAULT '',
    networking_priority INTEGER DEFAULT 0,     -- 0-100

    embedding         vector(1536)
);

CREATE INDEX idx_linkedin_hiring_intent ON linkedin_posts(hiring_intent DESC);
CREATE INDEX idx_linkedin_scraped ON linkedin_posts(scraped_at DESC);

-- Contacts (hiring managers, recruiters, connections)
CREATE TABLE contacts (
    id                SERIAL PRIMARY KEY,
    name              TEXT NOT NULL,
    title             TEXT DEFAULT '',
    company           TEXT DEFAULT '',
    linkedin_url      TEXT UNIQUE,
    email             TEXT DEFAULT '',
    contact_type      TEXT DEFAULT '',          -- recruiter, hm, alumni, connection
    relationship      TEXT DEFAULT 'none',      -- none, 1st, 2nd, alumni
    school_overlap    TEXT DEFAULT '',
    company_overlap   TEXT DEFAULT '',
    last_interaction  TIMESTAMPTZ,
    outreach_sent     BOOLEAN DEFAULT FALSE,
    outreach_response TEXT DEFAULT '',          -- none, positive, negative, no_response
    notes             TEXT DEFAULT '',
    metadata          JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_contacts_company ON contacts(company);
CREATE INDEX idx_contacts_type ON contacts(contact_type);
```

### Migration 003 — Learning + Memory

```sql
-- Application outcomes (learning signal)
CREATE TABLE outcomes (
    id                SERIAL PRIMARY KEY,
    application_id    INTEGER REFERENCES applications(id),
    job_id            INTEGER REFERENCES jobs(id),
    company_name      TEXT NOT NULL,
    role_title        TEXT NOT NULL,
    resume_version    TEXT NOT NULL,
    outcome           TEXT NOT NULL,            -- applied, rejected, screen, interview, offer
    stage_reached     TEXT DEFAULT '',
    days_to_response  INTEGER,
    rejection_reason  TEXT DEFAULT '',
    missing_keywords  TEXT[] DEFAULT '{}',
    successful_keywords TEXT[] DEFAULT '{}',
    recruiter_feedback TEXT DEFAULT '',
    lessons           TEXT DEFAULT '',          -- AI-generated lesson from this outcome
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_outcomes_company ON outcomes(company_name);
CREATE INDEX idx_outcomes_outcome ON outcomes(outcome);

-- Persistent memory (RAG-searchable)
CREATE TABLE memory (
    id                SERIAL PRIMARY KEY,
    category          TEXT NOT NULL,            -- resume, targeting, company, skill, pattern
    key               TEXT NOT NULL,
    content           TEXT NOT NULL,
    confidence        REAL DEFAULT 0.5,         -- 0.0 to 1.0
    source            TEXT DEFAULT '',          -- which outcome/signal produced this
    embedding         vector(1536),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(category, key)
);

CREATE INDEX idx_memory_category ON memory(category);
CREATE INDEX idx_memory_embedding ON memory USING ivfflat (embedding vector_cosine_ops);

-- Scoring weight overrides (learned from outcomes)
CREATE TABLE scoring_weights (
    id                SERIAL PRIMARY KEY,
    dimension         TEXT UNIQUE NOT NULL,     -- ats_score, pm_fit, visa, etc.
    base_weight       REAL NOT NULL DEFAULT 1.0,
    learned_weight    REAL NOT NULL DEFAULT 1.0,
    last_calibrated   TIMESTAMPTZ DEFAULT NOW(),
    sample_size       INTEGER DEFAULT 0
);
```

### Migration 004 — Skill Graph

```sql
-- Skills catalog
CREATE TABLE skills (
    id                SERIAL PRIMARY KEY,
    name              TEXT UNIQUE NOT NULL,     -- "roadmapping", "A/B testing", etc.
    category          TEXT DEFAULT '',          -- technical, leadership, domain, tool
    aliases           TEXT[] DEFAULT '{}',      -- alternate spellings/names
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Skill demand tracking (aggregated from job descriptions)
CREATE TABLE skill_demand (
    id                SERIAL PRIMARY KEY,
    skill_id          INTEGER REFERENCES skills(id),
    period            TEXT NOT NULL,            -- "2025-W20", "2025-05"
    demand_count      INTEGER DEFAULT 0,        -- how many jobs mentioned it
    avg_salary_min    INTEGER,
    avg_salary_max    INTEGER,
    visa_correlation  REAL DEFAULT 0,           -- correlation with visa-friendly
    seniority_distribution JSONB DEFAULT '{}', -- {entry: 10, mid: 40, senior: 50}
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(skill_id, period)
);

-- User skill gaps (computed)
CREATE TABLE skill_gaps (
    id                SERIAL PRIMARY KEY,
    skill_id          INTEGER REFERENCES skills(id),
    gap_type          TEXT DEFAULT 'missing',   -- missing, weak, trending
    frequency         INTEGER DEFAULT 0,        -- how often it appears in target jobs
    impact_score      INTEGER DEFAULT 0,        -- 0-100, how much it'd improve matches
    recommendation    TEXT DEFAULT '',           -- upskilling suggestion
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(skill_id)
);
```

### Enable pgvector

```sql
-- Run once in Supabase SQL Editor
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Backend Architecture

### Server Bootstrap (`app/main.py`)

```
FastAPI App (already running on Fly.io)
├── Middleware
│   ├── CORSMiddleware (existing)
│   └── rate limiting (slowapi)
├── Routes
│   ├── /health
│   ├── /api/jobs/*
│   ├── /api/profile/*
│   ├── /api/scrape/*
│   ├── /api/applications/*
│   ├── /api/signals/*          # NEW: social signals
│   ├── /api/skills/*           # NEW: skill graph
│   ├── /api/answers/*
│   └── /api/ws/* (WebSocket)
├── Services (business logic)
└── arq Workers (run as separate process, same Docker image)
```

### Config Validation (`app/config.py`) — Already Exists

```python
# Pydantic Settings — validates at import time, fails fast
class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str = ""
    claude_api: str = ""
    apify_token: str = ""
    firecrawl_api_key: str = ""
    browserbase_api_key: str = ""
    redis_url: str = "redis://localhost:6379"
    frontend_url: str = "https://hire.shreevaidya.com"
    backend_url: str = "https://jobs.shreevaidya.com"
    environment: str = "production"
    log_level: str = "INFO"
    port: int = 8000
```

---

## Worker Architecture

### Why arq over Celery?

arq is async-native (asyncio), lightweight, uses Redis directly, supports
cron scheduling, retries, and job results — without Celery's broker complexity.
Perfect for a single-user app.

### Queue Design

```python
# app/workers/__init__.py — arq worker configuration
class WorkerSettings:
    functions = [
        scrape_source,       # Scrape one source/company
        collect_signals,     # Scrape LinkedIn hiring posts
        classify_signal,     # AI-classify a social signal
        enrich_job,          # AI-extract metadata from job
        score_job,           # Multi-dimensional scoring
        generate_resume,     # AI resume variant
        execute_apply,       # Playwright application
        process_outcome,     # Learn from result
    ]
    cron_jobs = [
        cron(scrape_all,    hour=6, minute=0),   # Daily 6 AM scrape
        cron(collect_signals, hour={8,12,18}),    # 3x daily signal scan
        cron(detect_trends,  weekday=0, hour=9),  # Weekly skill trends
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 300  # 5 min per job
```

### Worker Lifecycle

```
Docker runs two processes (via supervisord or Procfile):
  1. uvicorn app.main:app          # API server
  2. arq app.workers.WorkerSettings # Background workers

Both share the same codebase, same config, same Docker image.
arq persists jobs in Redis — survives restarts.
Failed jobs retry 3x with exponential backoff.
```

### Queue Jobs

```
Redis (arq)
├── scrape_source        # { source: "greenhouse", company: "stripe" }
├── collect_signals      # { hashtags: ["#hiring"], max_posts: 50 }
├── classify_signal      # { post_id: 456 }
├── enrich_job           # { job_id: 1234 }
├── score_job            # { job_id: 1234 }
├── generate_resume      # { job_id: 1234, style: "technical_pm" }
├── execute_apply        # { job_id: 1234, resume_id: 5 }
└── process_outcome      # { application_id: 789, outcome: "rejected" }
```

---

## AI Orchestration

### Routing Logic

```
                    ┌─────────────────┐
                    │  AI Orchestrator │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Claude API     OpenAI API    OpenAI Embeddings
         (Reasoning)    (Extraction)  (Vectors)
              │              │              │
     ┌────────┤        ┌─────┤        ┌─────┤
     │        │        │     │        │     │
  Resume   Cover    Enrich  Score  Semantic Memory
  Rewrite  Letter   Job     Job    Search   RAG
  Hiring   Outreach Extract Rank
  Analysis Message  Skills  Match
```

### When to Use What

| Task | Model | Why |
|------|-------|-----|
| Job description enrichment | **gpt-4o-mini** | Fast structured JSON extraction, cheap at volume |
| Multi-dimensional scoring | **gpt-4o-mini** | Numeric scoring with structured output |
| Resume rewriting | **Claude Sonnet** | Nuanced writing, tone, persuasion |
| Cover letter generation | **Claude Sonnet** | Personalization, company voice matching |
| Hiring post classification | **gpt-4o-mini** | Fast classification, structured output |
| Recruiter outreach message | **Claude Sonnet** | Natural, non-generic writing |
| Outcome analysis / lessons | **Claude Sonnet** | Pattern recognition, strategic reasoning |
| Skill gap analysis | **Claude Sonnet** | Long-context analysis across job corpus |
| Embedding generation | **text-embedding-3-small** | Vector search, RAG retrieval |

### Prompt Management

Prompts live in `src/services/ai/prompts/` as TypeScript template functions:
- Versioned (can A/B test)
- Typed inputs/outputs with Zod schemas
- Include few-shot examples inline
- Return structured JSON (not free text)

Example pattern:

```typescript
// src/services/ai/prompts/enrich-job.ts
export const enrichJobPrompt = (job: RawJob) => ({
  system: `You are a PM career analyst. Extract structured metadata...`,
  user: `Analyze this job posting:\n\nTitle: ${job.title}\nCompany: ${job.company}\n...`,
  schema: enrichmentSchema, // Zod schema for response validation
});
```

---

## Scraping Architecture

### Source Registry

```typescript
// src/services/scrapers/registry.ts
const SOURCES = {
  greenhouse:      { type: 'api',     scraper: GreenhouseScraper,      rateLimit: '10/s' },
  lever:           { type: 'api',     scraper: LeverScraper,           rateLimit: '10/s' },
  ashby:           { type: 'api',     scraper: AshbyScraper,           rateLimit: '10/s' },
  smartrecruiters: { type: 'api',     scraper: SmartRecruitersScraper, rateLimit: '5/s'  },
  workday:         { type: 'api',     scraper: WorkdayScraper,         rateLimit: '3/s'  },
  workable:        { type: 'api',     scraper: WorkableScraper,        rateLimit: '5/s'  },
  apple:           { type: 'http',    scraper: AppleScraper,           rateLimit: '2/s'  },
  google:          { type: 'http',    scraper: GoogleScraper,          rateLimit: '2/s'  },
  meta:            { type: 'http',    scraper: MetaScraper,            rateLimit: '2/s'  },
  amazon:          { type: 'http',    scraper: AmazonScraper,          rateLimit: '2/s'  },
  microsoft:       { type: 'http',    scraper: MicrosoftScraper,       rateLimit: '2/s'  },
  netflix:         { type: 'http',    scraper: NetflixScraper,         rateLimit: '2/s'  },
  linkedin:        { type: 'apify',   actor: 'bebity/linkedin-jobs-scraper' },
  wellfound:       { type: 'firecrawl' },
  yc_jobs:         { type: 'firecrawl', url: 'https://www.ycombinator.com/jobs' },
};
```

### Scraping Pipeline

```
Trigger (API call or cron)
    │
    ▼
Fan out to scrape-jobs queue
    │ (one job per source+company)
    ▼
Scrape Worker
    ├── API sources → httpx/fetch call
    ├── HTTP sources → fetch + parse JSON from XHR
    ├── Apify sources → start actor → poll → fetch results
    ├── Firecrawl sources → extract endpoint
    └── Browser sources → Playwright via Browserbase
    │
    ▼
Normalize to common Job schema
    │
    ▼
Upsert to Supabase (dedupe by external_id + source)
    │
    ▼
Queue enrich-job for each new/updated job
    │
    ▼
Enrich Worker (AI extraction)
    │
    ▼
Queue score-job
    │
    ▼
Score Worker (compute all scoring dimensions)
    │
    ▼
Generate embedding → store in jobs.embedding
```

### Anti-Bot Strategy

| Source | Method |
|--------|--------|
| Greenhouse, Lever, Ashby | Public JSON APIs — no anti-bot |
| Workday | Hidden JSON API — rotate User-Agent |
| Big Tech career pages | Direct HTTP with headers |
| LinkedIn | Apify managed actors + Bright Data proxies |
| Dynamic/protected sites | Playwright via Browserbase (cloud browsers) |

---

## Feature: Job Intelligence

### Job Card Data Model (what the frontend renders)

```typescript
interface JobCard {
  id: number;
  title: string;
  company: string;
  location: string;
  remoteType: 'remote' | 'hybrid' | 'onsite';
  salary?: { min: number; max: number; currency: string };
  postedAt: string;
  source: string;
  url: string;

  // AI Scores (0-100)
  scores: {
    overallFit: number;
    atsScore: number;
    pmTransitionFit: number;
    visaProbability: number;
    responseProbability: number;
    resumeAlignment: number;
    technicalMatch: number;
    leadershipMatch: number;
  };

  // Enrichment
  pmKeywords: string[];
  requiredSkills: string[];
  missingSkills: string[];
  inferredSeniority: string;
  pmSpecialization: string;

  // People
  hiringManager?: { name: string; linkedin: string };
  recruiter?: { name: string; linkedin: string; email?: string };
  alumniOverlaps: string[];
  referralLikelihood: number;

  // Recommendations
  resumeRecommendations: string;
  recommendedResumeId?: number;
}
```

### Filters

- Text search (title, company, description — uses embedding similarity)
- Company, location, remote type
- Seniority level
- PM specialization
- Score thresholds (overall fit > X)
- Visa-friendly only
- Has hiring manager
- Freshness (24h, 48h, 7d, 30d)
- Sort by: overall fit, ATS score, posted date, response probability

---

## Feature: Application Tracker

### Status Pipeline

```
saved → applied → oa_sent → screen → interview → offer → accepted
                                                       → rejected (from any stage)
                                                       → withdrawn (from any stage)
```

### Tracked Metrics

- Resume version used per application
- Cover letter text used
- Time between stages
- Recruiter response (yes/no/days)
- Outreach sent (channel, response)
- OA link + completion status
- Interview rounds count
- Rejection reason (if available)
- Follow-up reminders

### Aggregate Analytics

```typescript
interface ApplicationAnalytics {
  total: number;
  sent: number;
  replyRate: number;          // % that got any response
  interviewRate: number;       // % that reached interview
  offerRate: number;           // % that got offers
  avgDaysToResponse: number;
  avgDaysToRejection: number;
  topPerformingResume: string; // version with highest response rate
  bestResponseCompanies: string[];
  worstResponseCompanies: string[];
  resumeConversionRates: Record<string, number>; // per resume version
  weeklyApplicationRate: number[];                // trend line
}
```

---

## Feature: LinkedIn Hiring Intelligence

### Collection

Scrape LinkedIn posts containing hiring signals:
- Hashtags: #hiring, #techhiring, #pmjobs, #productjobs, etc.
- Keywords: "we're hiring", "join my team", "open role", "looking for"

Use Apify LinkedIn actors + Browserbase for authenticated scraping.

### AI Classification (per post)

```typescript
interface LinkedInClassification {
  hiringIntent: number;       // 0-100
  roleMentioned: string;
  companyMentioned: string;
  seniorityLevel: string;
  isRecruiter: boolean;
  outreachViability: number;  // 0-100
  urgencyScore: number;       // 0-100
  suggestedAction: 'apply' | 'connect' | 'message' | 'skip';
  outreachDraft: string;
  networkingPriority: number; // 0-100
}
```

### Outreach Generation

For high-priority posts, Claude generates:
- Personalized connection request message
- Follow-up message if already connected
- Referral request if mutual connection exists

---

## Feature: Memory + Learning System

### Memory Architecture

```
Application Outcome
    │
    ▼
Learn Worker
    ├── Extract signals (keywords, resume version, company, result)
    ├── Update scoring_weights table (calibrate future scoring)
    ├── Generate lesson via Claude ("This resume version lacked X")
    ├── Store in memory table with embedding
    └── Update company response_rate in companies table
```

### RAG-Powered Memory Retrieval

When generating a resume or scoring a job:
1. Create embedding of the current context (job description, company)
2. Search `memory` table for relevant past learnings
3. Include top-k memories in the AI prompt as context

Example memory entries:

```
Category: "resume"
Key: "amazon_rejection_v14"
Content: "Resume version pm_resume_v14 was rejected by Amazon. Post-mortem:
          missing 'roadmapping' and 'experimentation' keywords that appeared
          in 3 of last 5 Amazon PM postings. Next version should emphasize
          data-driven experimentation framework experience."
Confidence: 0.85
```

### Feedback Signals

| Signal | Source | Updates |
|--------|--------|---------|
| Application rejected | Manual status update | scoring_weights, memory, company stats |
| Got interview | Manual status update | successful resume keywords, company patterns |
| No response after 14 days | Automatic | response_probability model weights |
| Resume converted | Application → screen | resume keyword effectiveness |
| Recruiter replied to outreach | Manual | outreach viability model |

---

## Feature: Skill Graph Engine

### How It Works

1. **Extract**: Every enriched job has `required_skills` and `preferred_skills`
2. **Aggregate**: Count skill frequency across all target jobs per week/month
3. **Compare**: Match against user's profile skills
4. **Identify gaps**: Skills that appear frequently in target jobs but not in profile
5. **Rank impact**: Which missing skill would improve the most job matches

### Skill Graph API Response

```typescript
interface SkillGraphData {
  topSkills: Array<{
    name: string;
    demandCount: number;
    trend: 'rising' | 'stable' | 'falling';
    avgSalaryImpact: number;
    youHaveIt: boolean;
  }>;
  gaps: Array<{
    skill: string;
    frequency: number;       // % of target jobs requiring it
    impactScore: number;     // how much it'd improve matches
    recommendation: string;  // "Take AWS Solutions Architect cert"
  }>;
  strengths: Array<{
    skill: string;
    matchRate: number;       // % of jobs where this matches
  }>;
}
```

---

## Feature: Resume Intelligence

### Resume Variant Pipeline

```
User triggers "Generate resume for [Job]"
    │
    ▼
Fetch: job enrichment + scoring + profile + memory
    │
    ▼
Claude generates tailored resume variant
    ├── Optimizes for ATS keywords from job
    ├── Incorporates learning from past outcomes
    ├── Emphasizes matching skills
    ├── Addresses gap areas with adjacent experience
    └── Generates version name + metadata
    │
    ▼
Store in resumes table (is_ai_generated = true)
    │
    ▼
Render to PDF (or return structured content for frontend)
```

### ATS Score Computation

```
ATS Score = weighted sum of:
  - Keyword match rate (required_skills ∩ resume_keywords) × 40%
  - Format compliance (section headers, no tables) × 15%
  - Length appropriateness × 10%
  - Skill ordering (most relevant first) × 15%
  - Action verb density × 10%
  - Quantification density (numbers, %, $) × 10%
```

---

## Frontend Architecture

### Pages

| Route | Page | Data Source |
|-------|------|------------|
| `/` | Job Intelligence Dashboard | `GET /api/jobs` |
| `/applied` | Application Tracker | `GET /api/applications` |
| `/linkedin` | LinkedIn Hiring Intelligence | `GET /api/linkedin` |
| `/skills` | Skill Graph | `GET /api/skills` |
| `/profile` | Profile + Resumes | `GET /api/profile` |

### Component Library

Use **shadcn/ui** primitives:
- `Card`, `Badge`, `Button`, `Input`, `Select`
- `Tabs`, `Table`, `Dialog`, `Tooltip`
- `Progress`, `Separator`, `ScrollArea`
- `DropdownMenu`, `Command` (search palette)

Custom components:
- `ScoreRing` — circular score visualization (0-100)
- `ScoreBar` — horizontal score breakdown
- `JobCard` — rich job card with inline scores
- `PipelineTracker` — application status pipeline
- `SkillRadar` — radar chart for skill dimensions
- `TrendSparkline` — mini trend charts

### Design System

- **Tailwind CSS** with custom design tokens
- Dark mode support via `next-themes`
- Preserve neumorphic aesthetic from v4 as an option
- Primary: shadcn/ui defaults (clean, professional)

---

## Infrastructure + Deployment

### Docker Compose (Local Dev)

```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports: ['6379:6379']

  backend:
    build: ./backend
    ports: ['8000:8000']
    env_file: ./backend/.env
    depends_on: [redis]
    volumes:
      - ./backend/app:/app/app  # hot reload with uvicorn --reload

  # Frontend runs outside Docker (next dev is faster native)
```

### Production Dockerfile (updated for workers)

```dockerfile
FROM python:3.13-slim

# System deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 \
    libgtk-3-0 libxshmfence1 fonts-liberation \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium  # for browser automation

COPY . .

# supervisord runs both API + worker
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

```ini
; supervisord.conf
[supervisord]
nodaemon=true

[program:api]
command=uvicorn app.main:app --host 0.0.0.0 --port 8000
autorestart=true

[program:worker]
command=arq app.workers.WorkerSettings
autorestart=true
```

### Production

| Service | Host | Config |
|---------|------|--------|
| Frontend | Vercel | Root dir: `frontend/`, auto-deploy from `main` |
| Backend | Fly.io | `fly.toml`, Docker build, 1x shared-cpu, 512MB RAM |
| Redis | Fly.io (Upstash) or Upstash.com | Managed Redis, free tier available |
| Database | Supabase | Managed Postgres, pgvector enabled |
| Browser | Browserbase | Cloud Playwright sessions |
| Proxies | Bright Data | Residential proxies for LinkedIn |

### Fly.io Config

```toml
app = "intelligence-layer"
primary_region = "sjc"

[build]
  dockerfile = "Dockerfile"

[env]
  NODE_ENV = "production"
  FRONTEND_URL = "https://hire.shreevaidya.com"
  BACKEND_URL = "https://jobs.shreevaidya.com"
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

[[http_service.checks]]
  interval = "15s"
  timeout = "5s"
  method = "GET"
  path = "/health"

[[vm]]
  size = "shared-cpu-1x"
  memory = "1gb"           # 1GB for Playwright + workers
```

### DNS (Vercel manages nameservers)

| Type | Name | Value | Purpose |
|------|------|-------|---------|
| `A` | `@` | Vercel auto | Portfolio |
| `CNAME` | `hire` | `cname.vercel-dns.com` | Frontend |
| `A` | `jobs` | `66.241.124.231` | Backend (Fly) |
| `AAAA` | `jobs` | `2a09:8280:1::118:dacd:0` | Backend (Fly IPv6) |
| `CAA` | `@` | `0 issue "letsencrypt.org"` | TLS for Fly |

---

## Security

- `SUPABASE_SERVICE_ROLE_KEY` — backend only, never in frontend
- `NEXT_PUBLIC_*` — only public keys exposed to browser
- All AI API keys — Fly.io secrets (encrypted at rest)
- CORS — locked to `hire.shreevaidya.com`, `intelligence-layer-two.vercel.app`, `localhost:3000`
- Redis — password-protected, internal Fly network or Upstash TLS
- Rate limiting — Fastify rate-limit plugin on all routes
- Input validation — Zod schemas on every route handler
- No user auth needed — single-user app, but add API key header for extra safety

---

## Local Development

```bash
# 1. Start Redis
docker compose up redis -d

# 2. Backend API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in keys, set REDIS_URL=redis://localhost:6379
uvicorn app.main:app --reload --port 8000

# 3. Backend Workers (separate terminal)
cd backend && source .venv/bin/activate
arq app.workers.WorkerSettings    # processes queue jobs

# 4. Frontend
cd frontend
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:3000
```

---

## Migration from v4

### What Carries Over (no rewrite needed)

| v4 Component | v5 Status |
|-------------|-----------|
| `scraper_service.py` (Greenhouse, Lever, etc.) | **Kept as-is**, refactored into separate modules later |
| `bigtech_scrapers.py` (Apple, Google, etc.) | **Kept as-is** |
| `apify_service.py` | **Kept as-is**, add LinkedIn post actor |
| `relevancy_engine.py` | **Kept**, extended with multi-dimensional scoring |
| `answer_engine.py` | **Kept**, company context preserved, AI-enhanced |
| `database.py` (Supabase queries) | **Kept**, add new query modules alongside |
| `company_config.json` | **Kept** |
| `main.py`, routes, config | **Kept**, add new routes incrementally |
| Frontend React pages | **Kept**, add new tabs + shadcn/ui over time |
| Chrome extension | **Kept as-is** |

### Data Migration

```sql
-- v4 jobs → v5 jobs (additive, no breaking changes)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'greenhouse';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS remote_type TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS enriched BOOLEAN DEFAULT FALSE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scored BOOLEAN DEFAULT FALSE;
ALTER TABLE jobs RENAME COLUMN greenhouse_id TO external_id;
-- ... (add new columns with defaults — existing data untouched)

-- Re-enrich + re-score existing 1,879 jobs via workers
UPDATE jobs SET enriched = FALSE, scored = FALSE;
```

---

## Phase Plan

### Phase 1 — Social Signals + Queue Infrastructure (Weeks 1-3)

**Goal**: Social signal pipeline is the highest-ROI feature. Build it first
alongside the queue infrastructure that everything else depends on.

Why signals first:
- Best opportunities appear socially BEFORE ATS saturation
- Recruiter posts, founder posts, PM leader posts = less competition
- Candidates who respond to social signals get replies faster
- Referral paths are visible in social context

- [ ] Redis + arq worker setup (replaces asyncio.create_task)
- [ ] Docker Compose for local dev (Redis + backend)
- [ ] Supabase migration: linkedin_posts, contacts tables + pgvector
- [ ] LinkedIn post scraper (Apify linkedin-posts actor)
- [ ] AI signal classifier (Claude: hiring intent, urgency, outreach viability)
- [ ] People intelligence: extract HM/recruiter from posts
- [ ] Outreach message generator (Claude)
- [ ] Signals API routes (`/api/signals/*`)
- [ ] Frontend: Social Signals tab (cards, priority scores, outreach drafts)
- [ ] Connect signals to existing jobs (link post → ATS listing when match found)
- [ ] Deploy updated backend to Fly.io

### Phase 2 — Job Intelligence + AI Enrichment (Weeks 4-6)

**Goal**: Transform raw job listings into AI-enriched intelligence.

- [ ] AI orchestrator (route Claude vs OpenAI by task)
- [ ] Job enrichment worker (extract skills, seniority, PM specialization)
- [ ] Multi-dimensional scoring (overall fit, ATS, visa, response probability)
- [ ] Embedding generation + pgvector semantic search
- [ ] People intelligence for ATS jobs (HM/recruiter discovery)
- [ ] Supabase migration: expanded jobs columns, scoring fields
- [ ] Expand scraping: Firecrawl, Wellfound, YC Jobs
- [ ] Browserbase integration for anti-bot sites
- [ ] Frontend: enriched job cards with score breakdown
- [ ] Frontend: semantic search + advanced filters

### Phase 3 — Resume Intelligence + Application Engine (Weeks 7-9)

**Goal**: AI-powered resume variants, ATS optimization, smarter tracking.

- [ ] Resume variant generator (Claude, per-job optimization)
- [ ] ATS keyword scoring algorithm
- [ ] Cover letter generator (company-aware, from answer_engine context)
- [ ] PDF resume renderer
- [ ] Enhanced application tracking (OA, stages, follow-ups, outreach)
- [ ] Semi-automated application via Playwright + Browserbase
- [ ] Supabase migration: enhanced resumes, applications columns
- [ ] Frontend: resume panel, variant comparison, ATS score preview
- [ ] Frontend: enhanced pipeline tracker with analytics

### Phase 4 — Learning System + Skill Graph (Weeks 10-13)

**Goal**: The system gets smarter over time. Feedback loops close the loop.

- [ ] Outcome tracking pipeline (learn from rejections, interviews, offers)
- [ ] Persistent memory with embeddings (RAG-searchable lessons)
- [ ] Scoring weight calibration from real outcomes
- [ ] Skill graph builder (aggregate from enriched jobs)
- [ ] Trending skills detector + gap analysis
- [ ] Upskilling recommendations
- [ ] Frontend: Skill Graph tab (radar charts, gap analysis)
- [ ] Frontend: Analytics dashboard (conversion rates, trends)
- [ ] Frontend: shadcn/ui polish + dark mode
- [ ] Chrome extension v2 with enrichment data overlay

---

## Architecture Decisions

### Why stay in Python instead of rewriting to TypeScript?
The v4 backend already works. FastAPI is async-native, Pydantic handles validation,
every AI SDK (anthropic, openai) has first-class Python support, and Playwright has
a full Python API. Rewriting to TypeScript costs 3 weeks and gains nothing. The
only TypeScript stays in the frontend where Next.js needs it.

### Why social signals before more ATS sources?
The best opportunities appear socially BEFORE ATS saturation. A recruiter posting
"#hiring PM" on LinkedIn means the role is fresh, competition is low, and a direct
message gets 10x the response rate of a cold ATS application. Raw job count is
table stakes (you already have 1,879). Signal quality is the differentiator.

### Why arq over Celery?
arq is async-native (works with FastAPI's event loop), uses Redis directly (no
separate broker), supports cron scheduling, and is ~10x lighter than Celery.
For a single-user app, Celery's complexity is overkill.

### Why arq over asyncio.create_task?
The v4 approach loses jobs on restart, has no retry logic, no visibility, no
rate limiting, and no cron. arq gives all of that with Redis persistence.

### Why pgvector in Supabase instead of Pinecone/Weaviate?
Supabase already has pgvector. One database, one bill, one connection. Vector
search at this scale (thousands, not millions) works fine in Postgres.

### Why Claude for writing, OpenAI for extraction?
Claude produces more natural, persuasive prose (resumes, cover letters, outreach).
OpenAI's structured output mode is faster and cheaper for JSON extraction at scale.

### Why Browserbase over self-hosted Playwright?
Running Chromium on Fly.io's 512MB-1GB VMs is fragile. Browserbase gives cloud
browser sessions with residential IPs and anti-detection. Worth it for LinkedIn
scraping and application automation where anti-bot is aggressive.

### Why not microservices?
Single-user app. One FastAPI process + one arq worker process handles everything.
Modularity comes from clean Python packages, not separate deployments.
