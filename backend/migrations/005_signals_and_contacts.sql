-- Migration 005: Social Signals + Contacts + pgvector
-- Run this in Supabase SQL Editor (Dashboard → SQL → New Query)
--
-- Adds:
--   1. pgvector extension for semantic search
--   2. linkedin_posts table for classified hiring signals
--   3. contacts table for networking targets
--   4. New columns on jobs table for AI enrichment + scoring


-- ═══════════════════════════════════════════════════════════════════════════
-- 1. Enable pgvector extension
-- ═══════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. LinkedIn Posts — classified hiring signals
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS linkedin_posts (
    id              BIGSERIAL PRIMARY KEY,
    post_url        TEXT UNIQUE NOT NULL,
    content         TEXT,
    author_name     TEXT,
    author_title    TEXT,
    author_url      TEXT,
    author_company  TEXT,
    platform        TEXT DEFAULT 'linkedin',

    -- Engagement metrics
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    reposts         INTEGER DEFAULT 0,

    -- Timestamps
    posted_at       TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),

    -- AI classification results
    hiring_intent       INTEGER DEFAULT 0,       -- 0-100
    role_mentioned      TEXT DEFAULT '',
    company_mentioned   TEXT DEFAULT '',
    seniority_level     TEXT DEFAULT '',          -- entry, mid, senior, staff, director, vp
    is_recruiter        BOOLEAN DEFAULT FALSE,
    outreach_viability  INTEGER DEFAULT 0,       -- 0-100
    urgency_score       INTEGER DEFAULT 0,       -- 0-100
    suggested_action    TEXT DEFAULT 'skip',      -- apply, connect, message, skip
    ai_reason           TEXT DEFAULT '',

    -- Embedding for semantic search (1536 dims = text-embedding-3-small)
    embedding           vector(1536),

    -- User actions
    outreach_sent       BOOLEAN DEFAULT FALSE,
    outreach_message    TEXT,
    outreach_sent_at    TIMESTAMPTZ,
    user_notes          TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_hiring_intent
    ON linkedin_posts (hiring_intent DESC);
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_suggested_action
    ON linkedin_posts (suggested_action);
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_scraped_at
    ON linkedin_posts (scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_author_url
    ON linkedin_posts (author_url);


-- ═══════════════════════════════════════════════════════════════════════════
-- 3. Contacts — people discovered from hiring signals
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS contacts (
    id                      BIGSERIAL PRIMARY KEY,
    name                    TEXT NOT NULL,
    title                   TEXT,
    company                 TEXT,
    linkedin_url            TEXT UNIQUE,
    email                   TEXT,

    -- Source tracking
    source                  TEXT DEFAULT 'linkedin_signal',  -- linkedin_signal, manual, referral
    is_recruiter            BOOLEAN DEFAULT FALSE,

    -- Interaction tracking
    first_seen_at           TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at            TIMESTAMPTZ DEFAULT NOW(),
    interaction_count       INTEGER DEFAULT 1,
    latest_post_url         TEXT,
    latest_role_mentioned   TEXT,

    -- Outreach status
    outreach_status         TEXT DEFAULT 'none',  -- none, drafted, sent, replied, meeting
    outreach_message        TEXT,
    outreach_sent_at        TIMESTAMPTZ,
    response_received_at    TIMESTAMPTZ,

    -- User notes
    notes                   TEXT,
    tags                    TEXT,    -- comma-separated tags

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_company
    ON contacts (company);
CREATE INDEX IF NOT EXISTS idx_contacts_outreach_status
    ON contacts (outreach_status);
CREATE INDEX IF NOT EXISTS idx_contacts_last_seen
    ON contacts (last_seen_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- 4. Add AI enrichment + scoring columns to jobs table
-- ═══════════════════════════════════════════════════════════════════════════

-- Enrichment columns (filled by enrich_worker)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pm_keywords        JSONB DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS required_skills    JSONB DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS preferred_skills   JSONB DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS inferred_seniority TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pm_specialization  TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS technical_depth    INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS leadership_score   INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS remote_type        TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS visa_likelihood    INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS enriched_at        TIMESTAMPTZ;

-- AI scoring columns (filled by score_worker)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_overall_fit         INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_ats_score           INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_pm_transition_fit   INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_visa_probability    INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_response_probability INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_missing_skills      JSONB DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_resume_advice       TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_scored_at           TIMESTAMPTZ;

-- Embedding for semantic job search
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Index for finding un-enriched and un-scored jobs
CREATE INDEX IF NOT EXISTS idx_jobs_enriched_at ON jobs (enriched_at) WHERE enriched_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_ai_scored_at ON jobs (ai_scored_at) WHERE ai_scored_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_ai_overall_fit ON jobs (ai_overall_fit DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- 5. RLS (Row Level Security) — disabled for service role access
-- ═══════════════════════════════════════════════════════════════════════════
-- We use supabase_service_role_key so RLS is bypassed.
-- If you later add user auth, enable RLS and add policies.

ALTER TABLE linkedin_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (IF NOT EXISTS not supported for policies)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access on linkedin_posts') THEN
    CREATE POLICY "Service role full access on linkedin_posts" ON linkedin_posts FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access on contacts') THEN
    CREATE POLICY "Service role full access on contacts" ON contacts FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;
