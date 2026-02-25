"""SQLite database layer for candidates, quota, and search run tracking."""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from src.core.schemas import ScoredCandidate

_CANDIDATES_TABLE = """
CREATE TABLE IF NOT EXISTS candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    company         TEXT    NOT NULL DEFAULT '',
    location        TEXT    NOT NULL DEFAULT '',
    url             TEXT    NOT NULL,
    is_easy_apply   INTEGER NOT NULL DEFAULT 0,
    workplace_type  TEXT    NOT NULL DEFAULT '',
    posted_time     TEXT    NOT NULL DEFAULT '',
    description_snippet TEXT NOT NULL DEFAULT '',
    score           REAL    NOT NULL DEFAULT 0.0,
    status          TEXT    NOT NULL DEFAULT 'new',
    found_at        TEXT    NOT NULL,
    UNIQUE(external_id, platform)
);
"""

_QUOTA_TABLE = """
CREATE TABLE IF NOT EXISTS quota (
    platform         TEXT NOT NULL,
    date             TEXT NOT NULL,
    searches_run     INTEGER NOT NULL DEFAULT 0,
    candidates_found INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, date)
);
"""

_SEARCH_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS search_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    filters_json    TEXT NOT NULL,
    raw_count       INTEGER NOT NULL,
    filtered_count  INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL
);
"""


def init_db(path: str | Path) -> sqlite3.Connection:
    """Create the database and tables, returning a connection."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_CANDIDATES_TABLE)
    conn.execute(_QUOTA_TABLE)
    conn.execute(_SEARCH_RUNS_TABLE)
    conn.commit()
    return conn


def upsert_candidate(conn: sqlite3.Connection, scored: ScoredCandidate) -> bool:
    """Insert a candidate, ignoring if (external_id, platform) already exists.

    Returns True if a new row was inserted, False if it was a duplicate.
    """
    c = scored.candidate
    try:
        conn.execute(
            """
            INSERT INTO candidates
                (external_id, platform, title, company, location, url,
                 is_easy_apply, workplace_type, posted_time, description_snippet,
                 score, found_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c.external_id,
                c.platform,
                c.title,
                c.company,
                c.location,
                c.url,
                int(c.is_easy_apply),
                c.workplace_type,
                c.posted_time,
                c.description_snippet,
                scored.score,
                c.found_at.isoformat(),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def is_candidate_seen(
    conn: sqlite3.Connection,
    external_id: str,
    platform: str,
    ttl_days: int = 30,
) -> bool:
    """Check if a candidate was already stored within the TTL window."""
    cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
    row = conn.execute(
        """
        SELECT 1 FROM candidates
        WHERE external_id = ? AND platform = ? AND found_at >= ?
        LIMIT 1
        """,
        (external_id, platform, cutoff),
    ).fetchone()
    return row is not None


def get_quota(
    conn: sqlite3.Connection,
    platform: str,
    target_date: date | None = None,
) -> tuple[int, int]:
    """Return (searches_run, candidates_found) for today (or given date)."""
    d = (target_date or date.today()).isoformat()
    row = conn.execute(
        "SELECT searches_run, candidates_found FROM quota WHERE platform = ? AND date = ?",
        (platform, d),
    ).fetchone()
    if row is None:
        return (0, 0)
    return (row["searches_run"], row["candidates_found"])


def update_quota(
    conn: sqlite3.Connection,
    platform: str,
    searches_delta: int = 0,
    candidates_delta: int = 0,
    target_date: date | None = None,
) -> None:
    """Increment quota counters for today (or given date). Creates row if needed."""
    d = (target_date or date.today()).isoformat()
    conn.execute(
        """
        INSERT INTO quota (platform, date, searches_run, candidates_found)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(platform, date)
        DO UPDATE SET
            searches_run = searches_run + excluded.searches_run,
            candidates_found = candidates_found + excluded.candidates_found
        """,
        (platform, d, searches_delta, candidates_delta),
    )
    conn.commit()


def insert_search_run(
    conn: sqlite3.Connection,
    platform: str,
    keyword: str,
    filters_json: str,
    raw_count: int,
    filtered_count: int,
    started_at: datetime,
    finished_at: datetime,
) -> int:
    """Record a completed search run. Returns the row ID."""
    cursor = conn.execute(
        """
        INSERT INTO search_runs
            (platform, keyword, filters_json, raw_count, filtered_count, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            platform,
            keyword,
            filters_json,
            raw_count,
            filtered_count,
            started_at.isoformat(),
            finished_at.isoformat(),
        ),
    )
    conn.commit()
    return cursor.lastrowid or 0
