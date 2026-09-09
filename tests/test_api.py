from pathlib import Path

import sqlite3

from fastapi.testclient import TestClient

from yjs_tools.api import create_app
from yjs_tools.db import connect, init_db
from yjs_tools.journal.ingest import _upsert_source


def test_search_api(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    conn = connect(db_path)
    init_db(conn)
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S137773608",
            "display_name": "Nature",
            "issn_l": "0028-0836",
            "issn": ["0028-0836"],
            "host_organization_name": "Springer Nature",
            "homepage_url": "https://www.nature.com/nature",
            "is_oa": False,
            "works_count": 1,
            "cited_by_count": 9,
            "summary_stats": {},
            "type": "journal",
            "topics": [],
        },
    )
    conn.commit()
    conn.close()

    with TestClient(create_app(db_path)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        assert health.json()["version"] == "0.1.0"

        bad = client.post(
            "/api/imports",
            files={"file": ("bad.csv", b"name,year\nNature,2025", "text/csv")},
        )
        assert bad.status_code == 400
        assert "ISSN" in bad.json()["detail"]

        found = client.get("/api/journals", params={"q": "nature"})
        assert found.status_code == 200
        body = found.json()
        assert body["count"] == 1
        assert body["results"][0]["display_name"] == "Nature"
        assert body["results"][0]["issn_l"] == "0028-0836"


def test_init_db_migrates_is_chinese(tmp_path: Path):
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE journals (
            id INTEGER PRIMARY KEY,
            openalex_id TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            issn_l TEXT,
            issns TEXT,
            publisher TEXT,
            homepage TEXT,
            is_oa INTEGER NOT NULL DEFAULT 0,
            works_count INTEGER NOT NULL DEFAULT 0,
            cited_by_count INTEGER NOT NULL DEFAULT 0,
            citedness_2yr REAL,
            country_code TEXT,
            type TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    init_db(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(journals)")}
    assert "is_chinese" in columns
    assert "alternate_titles" in columns
    conn.close()
