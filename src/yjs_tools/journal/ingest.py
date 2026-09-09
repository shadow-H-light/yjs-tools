from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

OPENALEX_SOURCES = "https://api.openalex.org/sources"
USER_AGENT = (
    "yjs-tools/xuankan "
    "(https://github.com/shadow-H-light/yjs-tools; "
    "mailto:shadow-H-light@users.noreply.github.com)"
)
SEED_QUERIES = (
    "Nature",
    "Science",
    "IEEE",
    "Lancet",
    "Cell",
    "Physical Review",
    "ACS",
    "Springer",
)


def ingest_openalex(
    conn: sqlite3.Connection,
    *,
    limit: int = 200,
    query: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    limit = max(1, min(limit, 2000))
    own_client = client is None
    client = client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})
    inserted = 0
    updated = 0
    seen: set[str] = set()

    try:
        queries = [query] if query else list(SEED_QUERIES)
        per_query = limit if query else max(8, limit // len(queries))
        for q in queries:
            if inserted + updated >= limit:
                break
            remaining = min(per_query, limit - inserted - updated)
            batch = _fetch_sources(client, query=q, limit=remaining)
            for source in batch:
                openalex_id = _short_id(source.get("id"))
                if not openalex_id or openalex_id in seen:
                    continue
                seen.add(openalex_id)
                was_insert = _upsert_source(conn, source)
                if was_insert:
                    inserted += 1
                else:
                    updated += 1
                if inserted + updated >= limit:
                    break
    finally:
        if own_client:
            client.close()

    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES('last_ingest_at', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
    conn.commit()
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


def _fetch_sources(
    client: httpx.Client,
    *,
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = "*"
    while len(results) < limit and cursor:
        params: dict[str, str] = {
            "filter": "type:journal,has_issn:true",
            "per_page": str(min(50, limit - len(results))),
            "cursor": cursor,
            "sort": "cited_by_count:desc",
        }
        if query:
            params["search"] = query
        url = f"{OPENALEX_SOURCES}?{urlencode(params)}"
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
        page = payload.get("results") or []
        results.extend(page)
        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not page:
            break
    return results[:limit]


def _upsert_source(conn: sqlite3.Connection, source: dict[str, Any]) -> bool:
    openalex_id = _short_id(source.get("id"))
    display_name = (source.get("display_name") or "").strip()
    if not openalex_id or not display_name:
        return False

    issns = source.get("issn") or []
    issn_l = source.get("issn_l") or (issns[0] if issns else None)
    stats = source.get("summary_stats") or {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    existing = conn.execute(
        "SELECT id FROM journals WHERE openalex_id = ?", (openalex_id,)
    ).fetchone()

    values = (
        display_name,
        issn_l,
        json.dumps(issns, ensure_ascii=False),
        source.get("host_organization_name") or source.get("publisher"),
        source.get("homepage_url"),
        1 if source.get("is_oa") else 0,
        int(source.get("works_count") or 0),
        int(source.get("cited_by_count") or 0),
        stats.get("2yr_mean_citedness"),
        source.get("country_code"),
        source.get("type"),
        now,
        openalex_id,
    )

    if existing:
        journal_id = existing["id"]
        conn.execute(
            """
            UPDATE journals SET
                display_name = ?, issn_l = ?, issns = ?, publisher = ?,
                homepage = ?, is_oa = ?, works_count = ?, cited_by_count = ?,
                citedness_2yr = ?, country_code = ?, type = ?, updated_at = ?
            WHERE openalex_id = ?
            """,
            values,
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO journals (
                display_name, issn_l, issns, publisher, homepage, is_oa,
                works_count, cited_by_count, citedness_2yr, country_code,
                type, updated_at, openalex_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        journal_id = cursor.lastrowid

    conn.execute("DELETE FROM journal_topics WHERE journal_id = ?", (journal_id,))
    for topic in (source.get("topics") or [])[:8]:
        topic_id = _short_id(topic.get("id"))
        topic_name = topic.get("display_name")
        if not topic_id or not topic_name:
            continue
        field = topic.get("field") or {}
        conn.execute(
            """
            INSERT OR REPLACE INTO journal_topics
                (journal_id, topic_id, topic_name, field_name, share)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                journal_id,
                topic_id,
                topic_name,
                field.get("display_name"),
                topic.get("count") or topic.get("score"),
            ),
        )
    return existing is None


def _short_id(value: str | None) -> str:
    if not value:
        return ""
    return value.rsplit("/", 1)[-1]
