"""SQLite database layer — profiles, resumes, jobs, applications."""

import aiosqlite
import json
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    first_name  TEXT DEFAULT '',
    last_name   TEXT DEFAULT '',
    email       TEXT DEFAULT '',
    phone       TEXT DEFAULT '',
    address     TEXT DEFAULT '',
    city        TEXT DEFAULT '',
    state       TEXT DEFAULT '',
    zip_code    TEXT DEFAULT '',
    country     TEXT DEFAULT 'United States',
    linkedin    TEXT DEFAULT '',
    website     TEXT DEFAULT '',
    github      TEXT DEFAULT '',
    current_company   TEXT DEFAULT '',
    current_title     TEXT DEFAULT '',
    years_experience  INTEGER DEFAULT 0,
    education   TEXT DEFAULT '[]',
    skills      TEXT DEFAULT '',
    cover_letter_default TEXT DEFAULT '',
    work_auth   TEXT DEFAULT 'Authorized',
    sponsorship TEXT DEFAULT 'No',
    gender      TEXT DEFAULT '',
    race        TEXT DEFAULT '',
    veteran     TEXT DEFAULT '',
    disability  TEXT DEFAULT '',
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS resumes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    original_name TEXT NOT NULL,
    role_tags     TEXT DEFAULT '',
    is_default    INTEGER DEFAULT 0,
    uploaded_at   TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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
    scraped_at      TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER REFERENCES jobs(id),
    resume_id   INTEGER REFERENCES resumes(id),
    status      TEXT DEFAULT 'saved',
    applied_at  TEXT,
    notes       TEXT DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_ghid_company
    ON jobs(greenhouse_id, company);
"""


async def get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        # Ensure default profile row exists
        await db.execute(
            "INSERT OR IGNORE INTO profile (id) VALUES (1)"
        )
        # Migrate: add new columns if they don't exist
        for col, typ, default in [
            ("relevancy_score", "INTEGER", "0"),
            ("keywords_matched", "TEXT", "''"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE jobs ADD COLUMN {col} {typ} DEFAULT {default}"
                )
            except Exception:
                pass  # Column already exists
        await db.commit()
    finally:
        await db.close()


# ── Profile ──────────────────────────────────────────────────────────────────

async def get_profile() -> dict:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM profile WHERE id = 1")
        row = await cursor.fetchone()
        if row:
            d = dict(row)
            d["education"] = json.loads(d.get("education") or "[]")
            return d
        return {}
    finally:
        await db.close()


async def update_profile(data: dict):
    db = await get_db()
    try:
        fields = [
            "first_name", "last_name", "email", "phone",
            "address", "city", "state", "zip_code", "country",
            "linkedin", "website", "github",
            "current_company", "current_title", "years_experience",
            "education", "skills", "cover_letter_default",
            "work_auth", "sponsorship", "gender", "race", "veteran", "disability",
        ]
        sets = []
        vals = []
        for f in fields:
            if f in data:
                sets.append(f"{f} = ?")
                val = data[f]
                if f == "education" and isinstance(val, list):
                    val = json.dumps(val)
                vals.append(val)
        sets.append("updated_at = ?")
        vals.append(datetime.now(timezone.utc).isoformat())
        vals.append(1)
        await db.execute(
            f"UPDATE profile SET {', '.join(sets)} WHERE id = ?", vals
        )
        await db.commit()
    finally:
        await db.close()


# ── Resumes ──────────────────────────────────────────────────────────────────

async def get_resumes() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM resumes ORDER BY is_default DESC, uploaded_at DESC")
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def add_resume(filename: str, original_name: str, role_tags: str, is_default: bool) -> int:
    db = await get_db()
    try:
        if is_default:
            await db.execute("UPDATE resumes SET is_default = 0")
        cursor = await db.execute(
            "INSERT INTO resumes (filename, original_name, role_tags, is_default, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (filename, original_name, role_tags, int(is_default), datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def delete_resume(resume_id: int) -> str | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT filename FROM resumes WHERE id = ?", (resume_id,))
        row = await cursor.fetchone()
        if row:
            await db.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
            await db.commit()
            return row["filename"]
        return None
    finally:
        await db.close()


async def get_resume_for_role(role_tag: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM resumes WHERE role_tags LIKE ? ORDER BY is_default DESC LIMIT 1",
            (f"%{role_tag}%",),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        # Fall back to default resume
        cursor = await db.execute(
            "SELECT * FROM resumes WHERE is_default = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ── Jobs ─────────────────────────────────────────────────────────────────────

async def upsert_jobs(jobs: list[dict]) -> int:
    db = await get_db()
    try:
        count = 0
        now = datetime.now(timezone.utc).isoformat()

        def s(v):
            """Coerce any non-string value to string for SQLite."""
            if v is None:
                return ""
            if isinstance(v, (dict, list)):
                return json.dumps(v)
            return str(v)

        for j in jobs:
            await db.execute("""
                INSERT INTO jobs (greenhouse_id, company, title, location, department,
                    url, description, updated_at, first_published,
                    employment_type, salary_range, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(greenhouse_id, company) DO UPDATE SET
                    title=excluded.title, location=excluded.location,
                    department=excluded.department, url=excluded.url,
                    description=excluded.description, updated_at=excluded.updated_at,
                    employment_type=excluded.employment_type,
                    salary_range=excluded.salary_range, scraped_at=excluded.scraped_at
            """, (
                s(j.get("greenhouse_id", j.get("id", ""))),
                s(j.get("company", "")), s(j.get("title", "")), s(j.get("location", "")),
                s(j.get("department", "")), s(j.get("url", "")),
                s(j.get("description", "")), s(j.get("updated_at", "")),
                s(j.get("first_published", "")), s(j.get("employment_type", "")),
                s(j.get("salary_range", "")), now,
            ))
            count += 1
        await db.commit()
        return count
    finally:
        await db.close()


async def search_jobs(
    query: str = "",
    company: str = "",
    location: str = "",
    role: str = "",
    freshness: str = "",
    sort: str = "relevancy",
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[dict], int]:
    """Search jobs with optional freshness filter and sort.

    Args:
        freshness: "24h", "48h", "7d", "30d", or "" for all
        sort: "relevancy", "date", or "company"
    """
    db = await get_db()
    try:
        conditions = []
        params = []

        if query:
            conditions.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if company:
            conditions.append("company LIKE ?")
            params.append(f"%{company}%")
        if location:
            conditions.append("location LIKE ?")
            params.append(f"%{location}%")
        if role:
            conditions.append("title LIKE ?")
            params.append(f"%{role}%")
        if freshness:
            hours_map = {"24h": 24, "48h": 48, "7d": 168, "30d": 720}
            hours = hours_map.get(freshness)
            if hours:
                conditions.append(
                    "updated_at >= datetime('now', ?)"
                )
                params.append(f"-{hours} hours")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Count
        cursor = await db.execute(f"SELECT COUNT(*) FROM jobs {where}", params)
        total = (await cursor.fetchone())[0]

        # Sort
        order = "relevancy_score DESC, updated_at DESC"
        if sort == "date":
            order = "updated_at DESC"
        elif sort == "company":
            order = "company ASC, relevancy_score DESC"

        # Fetch page
        offset = (page - 1) * per_page
        cursor = await db.execute(
            f"SELECT * FROM jobs {where} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        return rows, total
    finally:
        await db.close()


async def get_job(job_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ── Applications ─────────────────────────────────────────────────────────────

async def save_application(job_id: int, resume_id: int | None, status: str = "saved") -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO applications (job_id, resume_id, status, applied_at) VALUES (?, ?, ?, ?)",
            (job_id, resume_id, status, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def update_application_status(app_id: int, status: str):
    db = await get_db()
    try:
        await db.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
        await db.commit()
    finally:
        await db.close()


async def get_applications() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("""
            SELECT a.*, j.title, j.company, j.location, j.url, r.original_name as resume_name
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            LEFT JOIN resumes r ON a.resume_id = r.id
            ORDER BY a.applied_at DESC
        """)
        return [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()


async def get_applied_job_ids() -> set[int]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT job_id FROM applications")
        return {r[0] for r in await cursor.fetchall()}
    finally:
        await db.close()


async def get_stats() -> dict:
    db = await get_db()
    try:
        jobs_count = (await (await db.execute("SELECT COUNT(*) FROM jobs")).fetchone())[0]
        apps_count = (await (await db.execute("SELECT COUNT(*) FROM applications")).fetchone())[0]
        companies = (await (await db.execute("SELECT COUNT(DISTINCT company) FROM jobs")).fetchone())[0]
        return {"jobs": jobs_count, "applications": apps_count, "companies": companies}
    finally:
        await db.close()


async def get_application_stats() -> dict:
    """Return counts per status + KPI metrics for the Applied tracker page."""
    db = await get_db()
    try:
        # Total sent (anything not 'saved')
        sent = (await (await db.execute(
            "SELECT COUNT(*) FROM applications WHERE status != 'saved'"
        )).fetchone())[0]

        # Per-status counts
        cursor = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM applications GROUP BY status"
        )
        status_counts = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

        total = sum(status_counts.values())
        interviews = status_counts.get("interview", 0)
        offers = status_counts.get("offer", 0)
        screens = status_counts.get("screen", 0)

        # Reply rate: (interview + offer + screen + rejected) / sent
        responded = interviews + offers + screens + status_counts.get("rejected", 0)
        reply_rate = round((responded / sent * 100), 1) if sent > 0 else 0

        return {
            "total": total,
            "sent": sent,
            "reply_rate": reply_rate,
            "interviews": interviews,
            "offers": offers,
            "by_status": {
                "all": total,
                "saved": status_counts.get("saved", 0),
                "applied": status_counts.get("applied", 0),
                "screen": status_counts.get("screen", 0),
                "interview": interviews,
                "offer": offers,
                "rejected": status_counts.get("rejected", 0),
            },
        }
    finally:
        await db.close()


async def rescore_all_jobs(profile: dict):
    """Rescore every job in the DB against the current profile.

    Called when the profile changes or on demand from the dashboard.
    """
    import relevancy_engine as re_engine

    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, title, description, location, department FROM jobs")
        rows = await cursor.fetchall()
        for row in rows:
            job = dict(row)
            result = re_engine.score_job(job, profile)
            await db.execute(
                "UPDATE jobs SET relevancy_score = ?, keywords_matched = ? WHERE id = ?",
                (result["relevancy_score"], json.dumps(result["keywords_matched"]), job["id"]),
            )
        await db.commit()
        return len(rows)
    finally:
        await db.close()
