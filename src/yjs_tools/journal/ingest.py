from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from yjs_tools.http import create_client
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
RETRY_ATTEMPTS = 6
RETRY_STATUSES = {429, 500, 502, 503, 504}
ENRICH_CAP = 400
Sleeper = Callable[[float], None]


def ingest_openalex(
    conn: sqlite3.Connection,
    *,
    limit: int = 800,
    query: str | None = None,
    scope: str = "all",
    name_search: bool = False,
    client: httpx.Client | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, int]:
    limit = max(1, min(limit, 2000))
    scope = scope if scope in SCOPES else "all"
    own_client = client is None
    wait = sleeper or time.sleep
    client = client or create_client(headers={"User-Agent": USER_AGENT})
    inserted = 0
    updated = 0
    completed = 0
    seen: set[str] = set()

    try:
        jobs = _ingest_jobs(limit, query, scope, name_search=name_search)
        for job in jobs:
            if inserted + updated >= limit:
                break
            remaining = min(job["limit"], limit - inserted - updated)
            try:
                batch = _fetch_sources(
                    client,
                    query=job["query"],
                    limit=remaining,
                    extra_filter=job["filter"],
                    name_search=bool(job.get("name_search")),
                    sleeper=wait,
                )
            except httpx.HTTPError:
                continue
            for source in batch:
                openalex_id = _short_id(source.get("id"))
                if not openalex_id or openalex_id in seen:
                    continue
                seen.add(openalex_id)
                filled, fetched = source, False
                if query is None:
                    filled, fetched = _complete_source(client, source, sleeper=wait)
                if fetched:
                    completed += 1
                was_insert = _upsert_source(conn, filled)
                if was_insert:
                    inserted += 1
                else:
                    updated += 1
                if inserted + updated >= limit:
                    break
        enriched = {"fetched": 0, "updated": 0}
        if query is None:
            enriched = enrich_incomplete_journals(
                conn, client=client, sleeper=wait, skip_ids=seen
            )
        completed += int(enriched.get("fetched") or 0)
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
    missing = _count_missing_identity(conn)
    return {
        "inserted": inserted,
        "updated": updated,
        "total": inserted + updated,
        "scope": scope,
        "completed": completed,
        "missing_issn": missing["issn"],
        "missing_homepage": missing["homepage"],
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
        top = limit if scope == "intl" else max(40, (limit * 3) // 5)
        jobs.append({"query": None, "filter": None, "limit": top})
        seed_budget = max(18, limit // 6)
        per = max(6, seed_budget // len(SEED_QUERIES))
        for q in SEED_QUERIES:
            jobs.append({"query": q, "filter": None, "limit": per})
    if scope in {"all", "cn"}:
        cn_top = limit if scope == "cn" else max(24, limit // 5)
        jobs.append(
            {
                "query": None,
                "filter": "country_code:cn",
                "limit": cn_top,
            }
        )
        per = max(5, max(16, cn_top // 3) // len(CHINESE_SEED_QUERIES))
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
    sleeper: Sleeper | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = "*"
    source_filter = "type:journal,has_issn:true"
    if extra_filter:
        source_filter = f"{source_filter},{extra_filter}"
    if query and name_search:
        source_filter = f"{source_filter},display_name.search:{query}"
    wait = sleeper or time.sleep
    while len(results) < limit and cursor:
        params: dict[str, str] = {
            "filter": source_filter,
            "per_page": str(min(200, limit - len(results))),
            "cursor": cursor,
            "sort": "cited_by_count:desc",
        }
        if query and not name_search:
            params["search"] = query
        url = f"{OPENALEX_SOURCES}?{urlencode(params)}"
        payload = get_json(client, url, sleeper=wait)
        page = payload.get("results") or []
        results.extend(page)
        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not page:
            break
    return results[:limit]


def get_json(
    client: httpx.Client,
    url: str,
    *,
    attempts: int = RETRY_ATTEMPTS,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    wait = sleeper or time.sleep
    response: httpx.Response | None = None
    last_error: Exception | None = None
    for index in range(max(1, attempts)):
        try:
            response = client.get(url)
        except httpx.RequestError as exc:
            last_error = exc
            if index == attempts - 1:
                raise
            wait(_backoff(index, response=None))
            continue
        if response.status_code < 400:
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        last_error = httpx.HTTPStatusError(
            f"{response.status_code} {response.reason_phrase}",
            request=response.request,
            response=response,
        )
        if response.status_code not in RETRY_STATUSES or index == attempts - 1:
            response.raise_for_status()
        wait(_backoff(index, response=response))
    if response is not None:
        response.raise_for_status()
    if last_error:
        raise last_error
    return {}


def post_json(
    client: httpx.Client,
    url: str,
    data: dict[str, str],
    *,
    attempts: int = RETRY_ATTEMPTS,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    wait = sleeper or time.sleep
    response: httpx.Response | None = None
    last_error: Exception | None = None
    for index in range(max(1, attempts)):
        try:
            response = client.post(url, data=data)
        except httpx.RequestError as exc:
            last_error = exc
            if index == attempts - 1:
                raise
            wait(_backoff(index, response=None))
            continue
        if response.status_code < 400:
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        last_error = httpx.HTTPStatusError(
            f"{response.status_code} {response.reason_phrase}",
            request=response.request,
            response=response,
        )
        if response.status_code not in RETRY_STATUSES or index == attempts - 1:
            response.raise_for_status()
        wait(_backoff(index, response=response))
    if response is not None:
        response.raise_for_status()
    if last_error:
        raise last_error
    return {}


def _backoff(index: int, *, response: httpx.Response | None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(20.0, max(0.4, float(retry_after)))
            except ValueError:
                pass
        if response.status_code == 429:
            return min(20.0, 2.0 * (2**index))
    return min(8.0, 0.4 * (2**index))


def _complete_source(
    client: httpx.Client,
    source: dict[str, Any],
    *,
    sleeper: Sleeper | None = None,
) -> tuple[dict[str, Any], bool]:
    if not _missing_required_openalex(source):
        return source, False
    openalex_id = _short_id(source.get("id"))
    if not openalex_id:
        return source, False
    try:
        detailed = get_json(
            client, f"{OPENALEX_SOURCES}/{openalex_id}", sleeper=sleeper
        )
    except httpx.HTTPError:
        return source, True
    return _merge_source(source, detailed), True


def enrich_incomplete_journals(
    conn: sqlite3.Connection,
    *,
    client: httpx.Client | None = None,
    sleeper: Sleeper | None = None,
    skip_ids: set[str] | None = None,
    limit: int = ENRICH_CAP,
) -> dict[str, int]:
    own_client = client is None
    wait = sleeper or time.sleep
    client = client or create_client(headers={"User-Agent": USER_AGENT})
    skip = skip_ids or set()
    fetched = 0
    updated = 0
    try:
        rows = conn.execute(
            """
            SELECT openalex_id FROM journals
            WHERE (issn_l IS NULL OR issn_l = '')
               OR (homepage IS NULL OR homepage = '')
            ORDER BY cited_by_count DESC
            LIMIT ?
            """,
            (max(1, min(limit, ENRICH_CAP)),),
        ).fetchall()
        for row in rows:
            openalex_id = row["openalex_id"]
            if not openalex_id or openalex_id in skip:
                continue
            try:
                detailed = get_json(
                    client, f"{OPENALEX_SOURCES}/{openalex_id}", sleeper=wait
                )
            except httpx.HTTPError:
                fetched += 1
                continue
            fetched += 1
            if not detailed:
                continue
            _upsert_source(conn, detailed)
            updated += 1
    finally:
        if own_client:
            client.close()
    return {"fetched": fetched, "updated": updated}


def _missing_required_openalex(source: dict[str, Any]) -> bool:
    issns = source.get("issn") or []
    issn_l = (source.get("issn_l") or (issns[0] if issns else "") or "").strip()
    homepage = (source.get("homepage_url") or "").strip()
    cited = source.get("cited_by_count")
    return not issn_l or not homepage or cited is None


def _merge_source(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _count_missing_identity(conn: sqlite3.Connection) -> dict[str, int]:
    issn = conn.execute(
        "SELECT COUNT(*) FROM journals WHERE issn_l IS NULL OR issn_l = ''"
    ).fetchone()[0]
    homepage = conn.execute(
        "SELECT COUNT(*) FROM journals WHERE homepage IS NULL OR homepage = ''"
    ).fetchone()[0]
    return {"issn": int(issn), "homepage": int(homepage)}


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

    topics = source.get("topics") or []
    if existing and not topics:
        return False
    conn.execute("DELETE FROM journal_topics WHERE journal_id = ?", (journal_id,))
    for topic in topics[:8]:
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
