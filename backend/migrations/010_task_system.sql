-- Migration 010: Daily/Weekly task system
-- The pivot from "build the platform" to "do the human work daily".
--
-- task_log records each tick of a daily/weekly checklist item, keyed by date,
-- so progress persists, streaks are visible, and the weekly CIOS review can see
-- what actually got done. Generated artifacts (memo, PM concept, article) are
-- stored too so they're not lost.
--
-- 100% ADDITIVE. Rollback at bottom.

CREATE TABLE IF NOT EXISTS task_log (
    id          BIGSERIAL PRIMARY KEY,
    task_key    TEXT NOT NULL,            -- e.g. 'outreach_5', 'strategy_memo', 'pm_concept'
    cadence     TEXT NOT NULL DEFAULT 'daily',  -- daily | weekly
    period      DATE NOT NULL,            -- the day (daily) or week-start Monday (weekly)
    done        BOOLEAN DEFAULT TRUE,
    notes       TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (task_key, period)
);

CREATE INDEX IF NOT EXISTS idx_task_log_period ON task_log (period DESC);

-- Generated artifacts (strategy memos, PM concepts, LinkedIn drafts, case studies)
CREATE TABLE IF NOT EXISTS artifacts (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,            -- strategy_memo | pm_concept | linkedin_article | case_study | teardown
    company     TEXT DEFAULT '',
    target_name TEXT DEFAULT '',          -- the human it's meant for (memo)
    target_url  TEXT DEFAULT '',          -- their LinkedIn
    title       TEXT DEFAULT '',
    body        TEXT DEFAULT '',
    used        BOOLEAN DEFAULT FALSE,    -- did you actually send/post it
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts (kind, created_at DESC);

-- ROLLBACK:
-- DROP TABLE IF EXISTS artifacts;
-- DROP TABLE IF EXISTS task_log;
