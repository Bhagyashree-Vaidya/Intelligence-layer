-- Migration 007: Night Shift queue + toggle
-- Run in Supabase SQL Editor.
--
-- Night Shift = browser-automation auto-apply that FILLS forms (via the Chrome
-- extension) and parks them for the user's morning review. It NEVER submits and
-- NEVER touches Tier-1 (Top-20) companies.
--
-- Adds:
--   1. night_shift_queue   — jobs filled & awaiting review (the review inbox)
--   2. night_shift_settings — the ON/OFF toggle + nightly cap (feature flag)
--
-- 100% ADDITIVE. Rollback at bottom.


-- ═══════════════════════════════════════════════════════════════════════════
-- 1. night_shift_queue — the morning review inbox
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS night_shift_queue (
    id            BIGSERIAL PRIMARY KEY,
    job_id        INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    company       TEXT,
    title         TEXT,
    url           TEXT,
    role          TEXT,                    -- pm, tpm, product (from classifier)
    resume_id     INTEGER REFERENCES resumes(id),
    tier          TEXT DEFAULT 'tier_2',   -- always tier_2 (tier_1 is blocked)

    -- Lifecycle:
    --   queued    → selected by Night Shift, not yet filled
    --   filled    → extension filled the form, awaiting user review (NOT submitted)
    --   submitted → user reviewed & submitted
    --   error     → fill failed (fires the bell)
    --   skipped   → user dismissed it
    status        TEXT DEFAULT 'queued',
    error_message TEXT DEFAULT '',
    fill_screenshot TEXT DEFAULT '',       -- optional path/url to a proof screenshot

    queued_at     TIMESTAMPTZ DEFAULT NOW(),
    filled_at     TIMESTAMPTZ,
    reviewed_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_nsq_status ON night_shift_queue (status, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_nsq_job ON night_shift_queue (job_id);
-- Prevent re-queuing the same job while one is still open.
CREATE UNIQUE INDEX IF NOT EXISTS idx_nsq_job_open
    ON night_shift_queue (job_id)
    WHERE status IN ('queued', 'filled');


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. night_shift_settings — the toggle (single row, id=1)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS night_shift_settings (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled         BOOLEAN DEFAULT FALSE,   -- OFF by default — the dark/light toggle
    max_per_night   INTEGER DEFAULT 20,      -- user chose 20
    min_fit_score   INTEGER DEFAULT 0,       -- only queue jobs above this AI fit score
    enabled_roles   TEXT DEFAULT 'pm,tpm,product',
    last_run_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed the single settings row, OFF.
INSERT INTO night_shift_settings (id, enabled, max_per_night)
VALUES (1, FALSE, 20)
ON CONFLICT (id) DO NOTHING;


-- ═══════════════════════════════════════════════════════════════════════════
-- 3. RLS — match existing tables (service role bypasses)
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE night_shift_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE night_shift_settings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access on night_shift_queue') THEN
    CREATE POLICY "Service role full access on night_shift_queue" ON night_shift_queue FOR ALL USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access on night_shift_settings') THEN
    CREATE POLICY "Service role full access on night_shift_settings" ON night_shift_settings FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK
-- ═══════════════════════════════════════════════════════════════════════════
-- DROP TABLE IF EXISTS night_shift_queue;
-- DROP TABLE IF EXISTS night_shift_settings;
