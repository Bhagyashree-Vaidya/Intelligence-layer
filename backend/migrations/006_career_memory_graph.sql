-- Migration 006: Career Memory Graph — feedback loop + durable insights
-- Run this in Supabase SQL Editor (Dashboard → SQL → New Query)
--
-- Closes the gap found in the schema audit: 6,457 jobs but 0 recorded
-- outcomes, and applications.status overwrites its own history.
--
-- Adds:
--   1. application_events  — append-only outcome timeline (the feedback loop)
--   2. insights            — durable learned facts (Curator memory, anti-rot)
--   3. company_conversion  — read-only VIEW for conversion analytics
--
-- 100% ADDITIVE: no existing table or column is altered or dropped.
-- Rollback is at the bottom of this file.


-- ═══════════════════════════════════════════════════════════════════════════
-- 1. application_events — append-only outcome timeline
-- ═══════════════════════════════════════════════════════════════════════════
-- Every status transition (applied → screen → interview → offer/rejected) is
-- recorded as its own timestamped row instead of overwriting applications.status.
-- This is what makes time-to-callback, trends, and conversion rates computable.

CREATE TABLE IF NOT EXISTS application_events (
    id          BIGSERIAL PRIMARY KEY,
    app_id      BIGINT REFERENCES applications(id) ON DELETE CASCADE,
    from_status TEXT,                       -- previous status (NULL for first event)
    to_status   TEXT NOT NULL,              -- saved, applied, screen, interview, offer, rejected
    channel     TEXT DEFAULT '',            -- email, linkedin, portal, referral
    occurred_at TIMESTAMPTZ DEFAULT NOW(),
    notes       TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_app_events_app
    ON application_events (app_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_app_events_to_status
    ON application_events (to_status);


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. insights — durable learned facts (Agent 8: Memory Curator)
-- ═══════════════════════════════════════════════════════════════════════════
-- Promoted, long-lived conclusions so the system never re-derives the same
-- insight. Confidence grows as evidence accumulates.

CREATE TABLE IF NOT EXISTS insights (
    id             BIGSERIAL PRIMARY KEY,
    statement      TEXT NOT NULL,           -- "Resume v3: 37% callback vs v1: 0%"
    kind           TEXT DEFAULT '',         -- resume, company, channel, role, skill
    confidence     NUMERIC DEFAULT 0.5,     -- 0-1, grows with evidence_count
    evidence_count INTEGER DEFAULT 1,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insights_kind ON insights (kind);
CREATE INDEX IF NOT EXISTS idx_insights_confidence ON insights (confidence DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- 3. company_conversion — read-only conversion analytics (Agent 7)
-- ═══════════════════════════════════════════════════════════════════════════
-- A VIEW, not a table: nothing writes it, nothing can corrupt it, and it can be
-- dropped at any time. Promote to a materialized table only if it gets slow.

CREATE OR REPLACE VIEW company_conversion AS
SELECT
    j.company,
    COUNT(DISTINCT a.id)                                              AS applications,
    COUNT(DISTINCT e.app_id) FILTER (
        WHERE e.to_status IN ('screen', 'interview', 'offer')
    )                                                                 AS responses,
    ROUND(
        100.0 * COUNT(DISTINCT e.app_id) FILTER (
            WHERE e.to_status IN ('screen', 'interview', 'offer')
        ) / NULLIF(COUNT(DISTINCT a.id), 0),
        1
    )                                                                 AS response_rate
FROM applications a
JOIN jobs j                    ON j.id = a.job_id
LEFT JOIN application_events e ON e.app_id = a.id
GROUP BY j.company;


-- ═══════════════════════════════════════════════════════════════════════════
-- 4. resume_conversion — read-only callback-rate-by-resume (Agent 4 input)
-- ═══════════════════════════════════════════════════════════════════════════
-- Directly answers "which resume version gets callbacks?"

CREATE OR REPLACE VIEW resume_conversion AS
SELECT
    r.id          AS resume_id,
    r.original_name,
    COUNT(DISTINCT a.id)                                              AS applications,
    COUNT(DISTINCT e.app_id) FILTER (
        WHERE e.to_status IN ('screen', 'interview', 'offer')
    )                                                                 AS callbacks,
    ROUND(
        100.0 * COUNT(DISTINCT e.app_id) FILTER (
            WHERE e.to_status IN ('screen', 'interview', 'offer')
        ) / NULLIF(COUNT(DISTINCT a.id), 0),
        1
    )                                                                 AS callback_rate
FROM resumes r
LEFT JOIN applications a        ON a.resume_id = r.id
LEFT JOIN application_events e  ON e.app_id = a.id
GROUP BY r.id, r.original_name;


-- ═══════════════════════════════════════════════════════════════════════════
-- 5. RLS — match existing tables (service-role access bypasses RLS)
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE application_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access on application_events') THEN
    CREATE POLICY "Service role full access on application_events" ON application_events FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access on insights') THEN
    CREATE POLICY "Service role full access on insights" ON insights FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK (run these to fully undo this migration)
-- ═══════════════════════════════════════════════════════════════════════════
-- DROP VIEW IF EXISTS resume_conversion;
-- DROP VIEW IF EXISTS company_conversion;
-- DROP TABLE IF EXISTS insights;
-- DROP TABLE IF EXISTS application_events;
