-- Migration 008: Persistent resume storage (Supabase Storage)
-- Run in Supabase SQL Editor.
--
-- Fixes the /tmp-wipe bug: resume FILES were stored on the Fly machine's /tmp,
-- which is erased on every restart (auto_stop_machines=suspend) — so files
-- vanished while DB rows remained, leaving Night Shift nothing to attach.
--
-- Files now live in the private Supabase Storage bucket 'resumes'. This column
-- records the object path within that bucket. Old 'filename' column is kept for
-- backward compatibility (local-disk fallback).
--
-- 100% ADDITIVE. Rollback at bottom.

ALTER TABLE resumes ADD COLUMN IF NOT EXISTS storage_path TEXT DEFAULT '';

-- (Bucket 'resumes' is created separately via storage.buckets insert.)

-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK
-- ═══════════════════════════════════════════════════════════════════════════
-- ALTER TABLE resumes DROP COLUMN IF EXISTS storage_path;
