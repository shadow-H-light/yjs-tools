from __future__ import annotations

import sqlite3

import pytest

from yjs_tools.db import init_db
from yjs_tools.journal.compare import (
    CompareError,
    compare_journals,
    journals_to_csv,
)
from yjs_tools.journal.importer import import_metrics_csv
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
            "display_name": "Nature",
            "issn_l": "0028-0836",
            "issn": ["0028-0836"],
            "host_organization_name": "Springer Nature",
            "is_oa": False,
            "works_count": 1,
            "cited_by_count": 9,
            "summary_stats": {},
            "type": "journal",
            "topics": [],
        },
    )
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S2",
            "display_name": "IEEE Access",
            "issn_l": "2169-3536",
            "issn": ["2169-3536"],
            "host_organization_name": "IEEE",
            "is_oa": True,
            "works_count": 1,
            "cited_by_count": 2,
            "summary_stats": {},
            "type": "journal",
            "topics": [],
        },
    )
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S3",
            "display_name": "Science",
            "issn_l": "0036-8075",
            "issn": ["0036-8075"],
            "host_organization_name": "AAAS",
            "is_oa": False,
            "works_count": 1,
            "cited_by_count": 8,
            "summary_stats": {},
            "type": "journal",
            "topics": [],
        },
    )
    conn.commit()
    return conn


CSV = """issn,year,jcr_quartile,impact_factor,cas_quartile,review_days
0028-0836,2025,Q1,50.5,1,7
2169-3536,2025,Q2,3.4,3,
0036-8075,2025,Q1,44.7,1,21
"""


def test_compare_and_export_missing_review():
    conn = _conn()
    import_metrics_csv(conn, content=CSV, filename="sample.csv", source="sample")
    nature = search_journals(conn, "nature").journals[0]
    access = search_journals(conn, "ieee access").journals[0]
    science = search_journals(conn, "science").journals[0]

    assert nature.official and nature.official.review_days == 7
    assert access.official and access.official.review_days is None
    assert science.official and science.official.review_days == 21

    with pytest.raises(CompareError):
        compare_journals(conn, [nature.id])

    compared = compare_journals(conn, [nature.id, access.id, science.id])
    assert [j.display_name for j in compared] == ["Nature", "IEEE Access", "Science"]
    csv_text = journals_to_csv(compared)
    assert "Nature" in csv_text
    assert "7" in csv_text
    assert "暂无" in csv_text
