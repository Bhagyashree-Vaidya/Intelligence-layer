-- Migration 009: System-audit fixes (2026-06-04)
--
-- Addresses Supabase advisor findings from the full system audit:
--   1. ERROR security_definer_view — recreate the 2 conversion views with
--      security_invoker so they run with the caller's permissions.
--   2. INFO unindexed_foreign_keys — cover the 3 flagged FKs.
--   3. WARN rls_policy_always_true — drop the USING(true) policies. The
--      backend uses the SERVICE ROLE key, which bypasses RLS entirely, so
--      these policies protected nothing while granting anon/authenticated
--      full access. Dropping them leaves RLS enabled with no policies =
--      deny-all for anon (the most secure state). Verified the frontend
--      never queries Supabase directly (all data flows through the API).
--
-- Rollback at bottom.


-- ═══════════════════════════════════════════════════════════════════════════
-- 1. Views → security_invoker (fixes the only ERROR-level advisor finding)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW company_conversion
WITH (security_invoker = on) AS
SELECT
    j.company,
    COUNT(DISTINCT a.id) AS applications,
    COUNT(DISTINCT e.app_id) FILTER (
        WHERE e.to_status IN ('screen', 'interview', 'offer')
    ) AS responses,
    ROUND(
        100.0 * COUNT(DISTINCT e.app_id) FILTER (
            WHERE e.to_status IN ('screen', 'interview', 'offer')
        ) / NULLIF(COUNT(DISTINCT a.id), 0),
        1
    ) AS response_rate
FROM applications a
JOIN jobs j ON j.id = a.job_id
LEFT JOIN application_events e ON e.app_id = a.id
GROUP BY j.company;

CREATE OR REPLACE VIEW resume_conversion
WITH (security_invoker = on) AS
SELECT
    r.id AS resume_id,
    r.original_name,
    COUNT(DISTINCT a.id) AS applications,
    COUNT(DISTINCT e.app_id) FILTER (
        WHERE e.to_status IN ('screen', 'interview', 'offer')
    ) AS callbacks,
    ROUND(
        100.0 * COUNT(DISTINCT e.app_id) FILTER (
            WHERE e.to_status IN ('screen', 'interview', 'offer')
        ) / NULLIF(COUNT(DISTINCT a.id), 0),
        1
    ) AS callback_rate
FROM resumes r
LEFT JOIN applications a ON a.resume_id = r.id
LEFT JOIN application_events e ON e.app_id = a.id
GROUP BY r.id, r.original_name;


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. Cover the unindexed foreign keys
-- ═══════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_applications_job_id    ON applications (job_id);
CREATE INDEX IF NOT EXISTS idx_applications_resume_id ON applications (resume_id);
CREATE INDEX IF NOT EXISTS idx_nsq_resume_id          ON night_shift_queue (resume_id);


-- ═══════════════════════════════════════════════════════════════════════════
-- 3. Drop the no-op permissive policies (service role bypasses RLS anyway)
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS "Service role full access on linkedin_posts"      ON linkedin_posts;
DROP POLICY IF EXISTS "Service role full access on contacts"            ON contacts;
DROP POLICY IF EXISTS "Service role full access on application_events"  ON application_events;
DROP POLICY IF EXISTS "Service role full access on insights"            ON insights;
DROP POLICY IF EXISTS "Service role full access on night_shift_queue"   ON night_shift_queue;
DROP POLICY IF EXISTS "Service role full access on night_shift_settings" ON night_shift_settings;


-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK
-- ═══════════════════════════════════════════════════════════════════════════
-- Views: re-run the CREATE OR REPLACE VIEW statements from migration 006
--        (without the security_invoker option).
-- Indexes: DROP INDEX IF EXISTS idx_applications_job_id,
--          idx_applications_resume_id, idx_nsq_resume_id;
-- Policies: re-run the CREATE POLICY blocks from migrations 005/006/007.
