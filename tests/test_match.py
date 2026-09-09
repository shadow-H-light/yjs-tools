from __future__ import annotations

import sqlite3

from yjs_tools.db import init_db
from yjs_tools.journal.ingest import _upsert_source
from yjs_tools.journal.search import search_journals


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S1",
            "display_name": "Obscure Letters",
            "issn_l": "1111-2222",
            "issn": ["1111-2222"],
            "host_organization_name": "Example Press",
            "is_oa": False,
            "works_count": 10,
            "cited_by_count": 50,
            "summary_stats": {},
            "type": "journal",
            "topics": [
                {
                    "id": "https://openalex.org/T10905",
                    "display_name": "Computer Vision",
                    "field": {"display_name": "Computer Science"},
                    "count": 20,
                }
            ],
        },
    )
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S2",
            "display_name": "Nature",
            "issn_l": "0028-0836",
            "issn": ["0028-0836"],
            "host_organization_name": "Springer Nature",
            "is_oa": False,
            "works_count": 1,
            "cited_by_count": 9000,
            "summary_stats": {},
            "type": "journal",
            "topics": [
                {
                    "id": "https://openalex.org/T11801",
                    "display_name": "Multidisciplinary",
                    "field": {"display_name": "General"},
                    "count": 12,
                }
            ],
        },
    )
    conn.commit()
    return conn


def test_direction_query_hits_topic_not_just_name():
    conn = _conn()
    page = search_journals(conn, "computer vision")
    names = [j.display_name for j in page.journals]
    assert "Obscure Letters" in names
    assert page.match_mode in {"topic", "mixed"}
    hit = next(j for j in page.journals if j.display_name == "Obscure Letters")
    assert hit.matched_topics
    assert hit.matched_topics[0].topic_name == "Computer Vision"
    assert page.hint


def test_chinese_synonym_maps_to_english_topic():
    conn = _conn()
    page = search_journals(conn, "计算机视觉")
    names = [j.display_name for j in page.journals]
    assert "Obscure Letters" in names
    assert page.match_mode == "topic"
