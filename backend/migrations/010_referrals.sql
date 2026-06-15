-- Migration 010: Referral tab support
-- Adds relationship_type to contacts so the Referral tab can rank people by
-- how useful they are for a warm intro at a Top-70 company.
--
-- relationship_type values (ranked, best first):
--   alum          — University of Washington alum at the company (highest reply rate)
--   hiring_manager— owns/posts the PM/Program role
--   team_senior   — senior/manager on the team the role sits in
--   referrer      — could plausibly refer
--   recruiter     — TA / recruiter (paid to respond, flooded)
--   peer / other  — everything else
--
-- 100% ADDITIVE. Rollback at bottom.

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS relationship_type TEXT DEFAULT '';
-- Which Top-70 target this contact maps to (normalized canonical name).
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS target_company TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_contacts_target_company ON contacts (target_company);
CREATE INDEX IF NOT EXISTS idx_contacts_relationship ON contacts (relationship_type);

-- ROLLBACK:
-- ALTER TABLE contacts DROP COLUMN IF EXISTS relationship_type;
-- ALTER TABLE contacts DROP COLUMN IF EXISTS target_company;
