from __future__ import annotations

import sqlite3

from yjs_tools.db import init_db
from yjs_tools.journal.importer import delete_batch, import_metrics_csv, list_batches
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
            "id": "https://openalex.org/S137773608",
            "display_name": "Nature",
            "issn_l": "0028-0836",
            "issn": ["0028-0836", "1476-4687"],
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
            "id": "https://openalex.org/S123",
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
    conn.commit()
    return conn


CSV = """issn,year,jcr_quartile,impact_factor,cas_quartile,warning
0028-0836,2025,Q1,50.5,1,0
2169-3536,2025,2,3.4,三区,0
0000-000X,2025,Q4,0.1,4,1
"""


def test_import_filter_and_delete():
    conn = _conn()
    before = search_journals(conn, "nature")
    assert before[0].official is None

    result = import_metrics_csv(
        conn,
        content=CSV,
        filename="sample.csv",
        source="sample",
    )
    assert result["matched"] == 2
    assert result["unmatched"] == 1

    nature = search_journals(conn, "nature")[0]
    assert nature.official is not None
    assert nature.official.jcr_quartile == 1
    assert nature.official.impact_factor == 50.5
    assert nature.official.cas_quartile == 1
    assert nature.official.filename == "sample.csv"

    q1 = search_journals(conn, jcr_quartile=1)
    assert [j.display_name for j in q1] == ["Nature"]

    cas3 = search_journals(conn, cas_quartile=3)
    assert [j.display_name for j in cas3] == ["IEEE Access"]

    batches = list_batches(conn)
    assert len(batches) == 1
    assert delete_batch(conn, batches[0]["id"]) is True
    assert search_journals(conn, "nature")[0].official is None
    assert search_journals(conn, jcr_quartile=1) == []
