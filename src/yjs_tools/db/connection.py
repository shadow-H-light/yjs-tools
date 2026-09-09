from __future__ import annotations

import sqlite3
from pathlib import Path

from yjs_tools.paths import DEFAULT_DB_PATH, ensure_data_dir

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    if path != Path(":memory:"):
        ensure_data_dir()
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    _migrate_existing_columns(conn)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate_existing_columns(conn)
    conn.commit()


def _migrate_existing_columns(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "journal_metrics" in tables:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(journal_metrics)")}
        if "review_days" not in columns:
            conn.execute("ALTER TABLE journal_metrics ADD COLUMN review_days INTEGER")
    if "journals" in tables:
        journal_cols = {row[1] for row in conn.execute("PRAGMA table_info(journals)")}
        if "alternate_titles" not in journal_cols:
            conn.execute("ALTER TABLE journals ADD COLUMN alternate_titles TEXT")
        if "is_chinese" not in journal_cols:
            conn.execute(
                "ALTER TABLE journals ADD COLUMN is_chinese INTEGER NOT NULL DEFAULT 0"
            )
