from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from yjs_tools.journal.lexicon import CJK_RE

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
    "Sensors",
)
CHINESE_SEED_QUERIES = (
    "学报",
    "中华",
    "中国科学",
    "Chinese Journal",
)
CHINESE_COUNTRIES = {"CN", "TW", "HK", "MO"}
SCOPES = {"all", "cn", "intl"}


def ingest_openalex(
    conn: sqlite3.Connection,
    *,
    limit: int = 200,
    query: str | None = None,
    scope: str = "all",
    name_search: bool = False,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    limit = max(1, min(limit, 2000))
    scope = scope if scope in SCOPES else "all"
    own_client = client is None
    client = client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})
    inserted = 0
    updated = 0
    seen: set[str] = set()

    try:
        jobs = _ingest_jobs(limit, query, scope, name_search=name_search)
        for job in jobs:
            if inserted + updated >= limit:
                break
            remaining = min(job["limit"], limit - inserted - updated)
            batch = _fetch_sources(
                client,
                query=job["query"],
                limit=remaining,
                extra_filter=job["filter"],
                name_search=bool(job.get("name_search")),
            )
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
    return {
        "inserted": inserted,
        "updated": updated,
        "total": inserted + updated,
        "scope": scope,
    }


def _ingest_jobs(
    limit: int,
    query: str | None,
    scope: str,
    name_search: bool = False,
) -> list[dict]:
    if query:
        extra = "country_code:cn" if scope == "cn" else None
        return [
            {
                "query": query,
                "filter": extra,
                "limit": limit,
                "name_search": name_search,
            }
        ]
    jobs: list[dict] = []
    if scope in {"all", "intl"}:
        intl_limit = limit if scope == "intl" else max(8, (limit * 2) // 3)
        per = max(8, intl_limit // len(SEED_QUERIES))
        for q in SEED_QUERIES:
            jobs.append({"query": q, "filter": None, "limit": per})
    if scope in {"all", "cn"}:
        cn_budget = limit if scope == "cn" else max(20, limit // 3)
        jobs.append(
            {
                "query": None,
                "filter": "country_code:cn",
                "limit": max(12, cn_budget // 2),
            }
        )
        per = max(6, (cn_budget // 2) // len(CHINESE_SEED_QUERIES))
        for q in CHINESE_SEED_QUERIES:
            jobs.append({"query": q, "filter": "country_code:cn", "limit": per})
    return jobs


def _fetch_sources(
    client: httpx.Client,
    *,
    query: str | None,
    limit: int,
    extra_filter: str | None = None,
    name_search: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = "*"
    source_filter = "type:journal,has_issn:true"
    if extra_filter:
        source_filter = f"{source_filter},{extra_filter}"
    if query and name_search:
        source_filter = f"{source_filter},display_name.search:{query}"
    while len(results) < limit and cursor:
        params: dict[str, str] = {
            "filter": source_filter,
            "per_page": str(min(50, limit - len(results))),
            "cursor": cursor,
            "sort": "cited_by_count:desc",
        }
        if query and not name_search:
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
    titles = [t for t in (source.get("alternate_titles") or []) if t]
    is_chinese = 1 if _is_chinese_journal(source, display_name, titles) else 0

    existing = conn.execute(
        "SELECT id FROM journals WHERE openalex_id = ?", (openalex_id,)
    ).fetchone()

    values = (
        display_name,
        issn_l,
        json.dumps(issns, ensure_ascii=False),
        json.dumps(titles, ensure_ascii=False),
        source.get("host_organization_name") or source.get("publisher"),
        source.get("homepage_url"),
        1 if source.get("is_oa") else 0,
        int(source.get("works_count") or 0),
        int(source.get("cited_by_count") or 0),
        stats.get("2yr_mean_citedness"),
        source.get("country_code"),
        source.get("type"),
        is_chinese,
        now,
        openalex_id,
    )

    if existing:
        journal_id = existing["id"]
        conn.execute(
            """
            UPDATE journals SET
                display_name = ?, issn_l = ?, issns = ?, alternate_titles = ?,
                publisher = ?, homepage = ?, is_oa = ?, works_count = ?,
                cited_by_count = ?, citedness_2yr = ?, country_code = ?,
                type = ?, is_chinese = ?, updated_at = ?
            WHERE openalex_id = ?
            """,
            values,
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO journals (
                display_name, issn_l, issns, alternate_titles, publisher, homepage,
                is_oa, works_count, cited_by_count, citedness_2yr, country_code,
                type, is_chinese, updated_at, openalex_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _is_chinese_journal(source: dict[str, Any], display_name: str, titles: list[str]) -> bool:
    code = (source.get("country_code") or "").upper()
    if code in CHINESE_COUNTRIES:
        return True
    publisher = source.get("host_organization_name") or source.get("publisher") or ""
    blob = " ".join([display_name, publisher, *titles])
    return bool(CJK_RE.search(blob))


def _short_id(value: str | None) -> str:
    if not value:
        return ""
    return value.rsplit("/", 1)[-1]
