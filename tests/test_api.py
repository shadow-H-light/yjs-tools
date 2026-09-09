from pathlib import Path

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
