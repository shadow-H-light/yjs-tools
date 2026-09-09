from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from yjs_tools.db import init_db
from yjs_tools.journal.ingest import _upsert_source
from yjs_tools.journal.search import get_journal, search_journals, stats


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def _source(**overrides) -> dict:
    data = {
        "id": "https://openalex.org/S137773608",
        "display_name": "Nature",
        "issn_l": "0028-0836",
        "issn": ["0028-0836", "1476-4687"],
        "host_organization_name": "Springer Nature",
        "homepage_url": "https://www.nature.com/nature",
        "is_oa": False,
        "works_count": 500000,
        "cited_by_count": 9000000,
        "summary_stats": {"2yr_mean_citedness": 50.1},
        "country_code": "GB",
        "type": "journal",
        "topics": [
            {
                "id": "https://openalex.org/T11801",
                "display_name": "Multidisciplinary",
                "field": {"display_name": "General"},
                "count": 12,
            }
        ],
    }
    data.update(overrides)
    return data


def test_search_by_name_and_issn():
    conn = _conn()
    _upsert_source(conn, _source())
    _upsert_source(
        conn,
        _source(
            id="https://openalex.org/S3880285",
            display_name="IEEE Transactions on Pattern Analysis and Machine Intelligence",
            issn_l="0162-8828",
            issn=["0162-8828"],
            host_organization_name="IEEE",
            cited_by_count="2000000",
            topics=[
                {
                    "id": "https://openalex.org/T10905",
                    "display_name": "Computer Vision",
                    "field": {"display_name": "Computer Science"},
                    "count": 8,
                }
            ],
        ),
    )
    conn.commit()

    by_name = search_journals(conn, "nature").journals
    assert [j.display_name for j in by_name] == ["Nature"]
    assert by_name[0].issn_l == "0028-0836"
    assert by_name[0].topics[0].topic_name == "Multidisciplinary"

    by_issn = search_journals(conn, "0028-0836").journals
    assert by_issn[0].display_name == "Nature"

    by_issn_compact = search_journals(conn, "00280836").journals
    assert by_issn_compact[0].display_name == "Nature"

    by_token = search_journals(conn, "pattern analysis").journals
    assert "IEEE" in by_token[0].display_name

    empty = search_journals(conn, "").journals
    assert empty[0].display_name == "Nature"

    detail = get_journal(conn, by_name[0].id)
    assert detail is not None
    assert detail.publisher == "Springer Nature"
    assert stats(conn)["journals"] == 2


def test_ingest_fixture_roundtrip(tmp_path: Path):
    fixture = Path(__file__).with_name("fixtures") / "openalex_sources.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    conn = _conn()
    for source in payload["results"]:
        _upsert_source(conn, source)
    conn.commit()

    hits = search_journals(conn, "science").journals
    names = {j.display_name.lower() for j in hits}
    assert any("science" in name for name in names)
