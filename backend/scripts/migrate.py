"""Supabase schema migration — run this once to set up tables.

Usage:
    cd backend
    python -m scripts.migrate

Or paste the SQL directly into Supabase SQL Editor.
"""

SCHEMA_SQL = """
-- ═══════════════════════════════════════════════════════════════
-- JobPilot — Supabase Schema
-- ═══════════════════════════════════════════════════════════════

-- Profile (singleton row, id=1)
CREATE TABLE IF NOT EXISTS profile (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    first_name      TEXT DEFAULT '',
    last_name       TEXT DEFAULT '',
    email           TEXT DEFAULT '',
    phone           TEXT DEFAULT '',
    address         TEXT DEFAULT '',
    city            TEXT DEFAULT '',
    state           TEXT DEFAULT '',
    zip_code        TEXT DEFAULT '',
    country         TEXT DEFAULT 'United States',
    linkedin        TEXT DEFAULT '',
    website         TEXT DEFAULT '',
    github          TEXT DEFAULT '',
    current_company TEXT DEFAULT '',
    current_title   TEXT DEFAULT '',
    years_experience INTEGER DEFAULT 0,
    education       JSONB DEFAULT '[]',
    skills          TEXT DEFAULT '',
    cover_letter_default TEXT DEFAULT '',
    work_auth       TEXT DEFAULT 'Authorized',
    sponsorship     TEXT DEFAULT 'No',
    gender          TEXT DEFAULT '',
    race            TEXT DEFAULT '',
    veteran         TEXT DEFAULT '',
    disability      TEXT DEFAULT '',
    updated_at      TIMESTAMPTZ
);

-- Seed the singleton profile row
INSERT INTO profile (id) VALUES (1) ON CONFLICT DO NOTHING;

-- Resumes
CREATE TABLE IF NOT EXISTS resumes (
    id            SERIAL PRIMARY KEY,
    filename      TEXT NOT NULL,
    original_name TEXT NOT NULL,
    role_tags     TEXT DEFAULT '',
    is_default    BOOLEAN DEFAULT FALSE,
    uploaded_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    greenhouse_id   TEXT,
    company         TEXT NOT NULL,
    title           TEXT NOT NULL,
    location        TEXT DEFAULT '',
    department      TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    updated_at      TEXT DEFAULT '',
    first_published TEXT DEFAULT '',
    employment_type TEXT DEFAULT '',
    salary_range    TEXT DEFAULT '',
    scraped_at      TIMESTAMPTZ,
    relevancy_score INTEGER DEFAULT 0,
    keywords_matched JSONB DEFAULT '[]',
    UNIQUE(greenhouse_id, company)
);

CREATE INDEX IF NOT EXISTS idx_jobs_relevancy ON jobs(relevancy_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC);

-- Applications
CREATE TABLE IF NOT EXISTS applications (
    id          SERIAL PRIMARY KEY,
    job_id      INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id   INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    status      TEXT DEFAULT 'saved',
    applied_at  TIMESTAMPTZ DEFAULT NOW(),
    notes       TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

-- Helper function for distinct company count
CREATE OR REPLACE FUNCTION count_distinct_companies()
RETURNS TABLE(count BIGINT) AS $$
    SELECT COUNT(DISTINCT company) FROM jobs;
$$ LANGUAGE SQL;
"""


def main():
    print("=" * 60)
    print("  JobPilot — Supabase Schema")
    print("=" * 60)
    print()
    print("Paste the SQL below into your Supabase SQL Editor:")
    print("  https://supabase.com/dashboard → SQL Editor → New Query")
    print()
    print("-" * 60)
    print(SCHEMA_SQL)
    print("-" * 60)
    print()
    print("After running the SQL, your tables are ready.")


if __name__ == "__main__":
    main()
