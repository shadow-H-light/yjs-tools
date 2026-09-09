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


def test_sensor_topic_and_search_type():
    conn = _conn()
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S9",
            "display_name": "IEEE Transactions on Industrial Electronics",
            "issn_l": "0278-0046",
            "issn": ["0278-0046"],
            "host_organization_name": "IEEE",
            "is_oa": False,
            "works_count": 10,
            "cited_by_count": 800,
            "summary_stats": {},
            "type": "journal",
            "topics": [
                {
                    "id": "https://openalex.org/T11900",
                    "display_name": "Sensors and Sensing",
                    "field": {"display_name": "Engineering"},
                    "count": 30,
                }
            ],
        },
    )
    conn.commit()
    by_topic = search_journals(conn, "sensor", by="topic")
    assert any("Industrial Electronics" in j.display_name for j in by_topic.journals)
    assert by_topic.journals[0].matched_topics

    by_zh = search_journals(conn, "传感器", by="topic")
    assert any("Industrial Electronics" in j.display_name for j in by_zh.journals)

    by_name = search_journals(conn, "sensor", by="name")
    assert all("Industrial Electronics" not in j.display_name for j in by_name.journals)


def test_topic_search_hits_famous_sensor_journal_names():
    conn = _conn()
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S1530437",
            "display_name": "IEEE Sensors Journal",
            "issn_l": "1530-437X",
            "issn": ["1530-437X"],
            "host_organization_name": "IEEE",
            "is_oa": False,
            "works_count": 20,
            "cited_by_count": 5000,
            "summary_stats": {},
            "type": "journal",
            "topics": [
                {
                    "id": "https://openalex.org/T1",
                    "display_name": "Photonic and Optical Devices",
                    "field": {"display_name": "Engineering"},
                    "count": 12,
                }
            ],
        },
    )
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S02602288",
            "display_name": "Sensor Review",
            "issn_l": "0260-2288",
            "issn": ["0260-2288"],
            "host_organization_name": "Emerald",
            "is_oa": False,
            "works_count": 8,
            "cited_by_count": 800,
            "summary_stats": {},
            "type": "journal",
            "topics": [],
        },
    )
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/SMST",
            "display_name": "Measurement Science and Technology",
            "issn_l": "0957-0233",
            "issn": ["0957-0233"],
            "host_organization_name": "IOP",
            "is_oa": False,
            "works_count": 15,
            "cited_by_count": 3000,
            "summary_stats": {},
            "type": "journal",
            "topics": [],
        },
    )
    conn.commit()
    names = {j.display_name for j in search_journals(conn, "传感器", by="topic").journals}
    assert "IEEE Sensors Journal" in names
    assert "Sensor Review" in names
    assert "Measurement Science and Technology" in names
    assert "Nature" not in names
