from __future__ import annotations

import sqlite3

import httpx
import pytest

from yjs_tools.db import init_db
from yjs_tools.journal.ingest import (
    _complete_source,
    _ingest_jobs,
    _upsert_source,
    enrich_incomplete_journals,
    get_json,
    ingest_openalex,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def test_ingest_jobs_cover_top_journals_and_chinese():
    jobs = _ingest_jobs(800, None, "all")
    assert jobs[0]["query"] is None
    assert jobs[0]["filter"] is None
    assert any(job["filter"] == "country_code:cn" for job in jobs)
    assert any(job["query"] == "Sensors" for job in jobs)


def test_get_json_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = get_json(client, "https://api.openalex.org/sources", sleeper=lambda _s: None)
    assert payload == {"ok": True}
    assert calls["n"] == 3


def test_get_json_retries_on_429():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, json={"error": "slow"})
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = get_json(client, "https://api.openalex.org/sources", sleeper=lambda _s: None)
    assert payload == {"ok": True}
    assert calls["n"] == 2


def test_complete_source_fetches_detail_when_homepage_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/S1")
        return httpx.Response(
            200,
            json={
                "id": "https://openalex.org/S1",
                "display_name": "Demo",
                "issn_l": "1111-1111",
                "homepage_url": "https://example.org/demo",
                "cited_by_count": 12,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    filled, fetched = _complete_source(
        client,
        {
            "id": "https://openalex.org/S1",
            "display_name": "Demo",
            "issn_l": "1111-1111",
            "cited_by_count": 12,
        },
        sleeper=lambda _s: None,
    )
    assert fetched is True
    assert filled["homepage_url"] == "https://example.org/demo"


def test_ingest_openalex_completes_and_upserts():
    list_payload = {
        "results": [
            {
                "id": "https://openalex.org/S9",
                "display_name": "Demo Journal",
                "issn_l": "1234-5678",
                "issn": ["1234-5678"],
                "cited_by_count": 3,
                "type": "journal",
                "topics": [],
            }
        ],
        "meta": {},
    }
    detail = {
        "id": "https://openalex.org/S9",
        "display_name": "Demo Journal",
        "issn_l": "1234-5678",
        "issn": ["1234-5678"],
        "homepage_url": "https://example.org/demo",
        "cited_by_count": 3,
        "type": "journal",
        "topics": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.openalex.org/sources?"):
            return httpx.Response(200, json=list_payload)
        if url.endswith("/S9"):
            return httpx.Response(200, json=detail)
        return httpx.Response(404, json={"error": "missing"})

    conn = _conn()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ingest_openalex(
        conn, limit=1, client=client, sleeper=lambda _s: None
    )
    assert result["inserted"] == 1
    row = conn.execute("SELECT homepage, issn_l FROM journals").fetchone()
    assert row["issn_l"] == "1234-5678"
    assert row["homepage"] == "https://example.org/demo"


def test_enrich_incomplete_journals_refetches_missing_homepage():
    conn = _conn()
    _upsert_source(
        conn,
        {
            "id": "https://openalex.org/S2",
            "display_name": "Need Home",
            "issn_l": "2222-2222",
            "issn": ["2222-2222"],
            "cited_by_count": 1,
            "topics": [],
        },
    )
    conn.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "https://openalex.org/S2",
                "display_name": "Need Home",
                "issn_l": "2222-2222",
                "homepage_url": "https://example.org/home",
                "cited_by_count": 1,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    enrich_incomplete_journals(conn, client=client, sleeper=lambda _s: None)
    row = conn.execute("SELECT homepage FROM journals").fetchone()
    assert row["homepage"] == "https://example.org/home"


def test_get_json_gives_up_after_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "busy"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        get_json(
            client,
            "https://api.openalex.org/sources",
            attempts=3,
            sleeper=lambda _s: None,
        )
