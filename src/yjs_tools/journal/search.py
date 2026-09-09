from __future__ import annotations

import json
import re
import sqlite3

from yjs_tools.journal.issn import looks_like_issn, normalize_issn
from yjs_tools.journal.match import (
    expand_query,
    looks_like_direction,
    local_topic_hits,
    match_mode_for,
    merge_hits,
    quality_bonus,
    remote_topic_ids,
    topic_hits_by_ids,
)
from yjs_tools.journal.models import Journal, OfficialMetrics, Topic
from yjs_tools.journal.result import ScoredHit, SearchPage

FTS_SAFE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
TOPIC_HINT = "当前是主题匹配，未启用向量模型。命中主题会标在每条结果上。"


def stats(conn: sqlite3.Connection) -> dict:
    journal_count = conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0]
    topic_count = conn.execute(
        "SELECT COUNT(DISTINCT topic_id) FROM journal_topics"
    ).fetchone()[0]
    last_ingest = conn.execute(
        "SELECT value FROM meta WHERE key = 'last_ingest_at'"
    ).fetchone()
    batch_count = conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
    years = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT year FROM journal_metrics ORDER BY year DESC"
        )
    ]
    return {
        "journals": journal_count,
        "topics": topic_count,
        "last_ingest_at": last_ingest[0] if last_ingest else None,
        "import_batches": batch_count,
        "metric_years": years,
        "has_official_metrics": batch_count > 0,
        "embedding_enabled": False,
    }


def search_journals(
    conn: sqlite3.Connection,
    query: str = "",
    limit: int = 20,
    *,
    jcr_quartile: int | None = None,
    cas_quartile: int | None = None,
    year: int | None = None,
    warning: bool | None = None,
    resolve_remote: bool = False,
) -> SearchPage:
    limit = max(1, min(limit, 100))
    q = query.strip()
    join_sql, join_params = _metrics_join(year)
    filter_sql, filter_params = _metrics_where(jcr_quartile, cas_quartile, warning)
    extra_and = filter_sql.replace("WHERE", "AND", 1) if filter_sql else ""

    if not q:
        sql = f"""
            SELECT journals.* FROM journals
            {join_sql}
            {filter_sql}
            ORDER BY journals.cited_by_count DESC, journals.display_name
            LIMIT ?
        """
        rows = conn.execute(sql, [*join_params, *filter_params, limit]).fetchall()
        journals = [_hydrate(conn, row, year) for row in rows]
        return SearchPage(journals=journals, match_mode="browse")

    compact = q.replace(" ", "")
    issn = normalize_issn(compact) if looks_like_issn(compact) else None
    if issn:
        sql = f"""
            SELECT journals.* FROM journals
            {join_sql}
            WHERE (journals.issn_l = ? OR journals.issns LIKE ?)
            {extra_and}
            ORDER BY journals.cited_by_count DESC
            LIMIT ?
        """
        rows = conn.execute(
            sql, [*join_params, issn, f"%{issn}%", *filter_params, limit]
        ).fetchall()
        journals = [_hydrate(conn, row, year) for row in rows]
        return SearchPage(journals=journals, match_mode="issn")

    name_hits = _name_hits(conn, q)
    topic_hits = local_topic_hits(conn, expand_query(q))
    if resolve_remote and looks_like_direction(q):
        remote_ids = remote_topic_ids(q)
        topic_hits = merge_hits(topic_hits, topic_hits_by_ids(conn, remote_ids))
    merged = merge_hits(name_hits, topic_hits)
    if not merged:
        return SearchPage(
            journals=[],
            match_mode="none",
            hint=TOPIC_HINT,
        )

    allowed = _allowed_journal_ids(
        conn, join_sql, join_params, extra_and, filter_params
    )
    if allowed is not None:
        merged = {jid: hit for jid, hit in merged.items() if jid in allowed}
    ranked = sorted(
        merged.values(),
        key=lambda hit: (
            hit.total + quality_bonus(_citation(conn, hit.journal_id)),
            _citation(conn, hit.journal_id),
        ),
        reverse=True,
    )[:limit]

    journals = []
    for hit in ranked:
        journal = get_journal(conn, hit.journal_id, year=year)
        if journal is None:
            continue
        journal.match_score = round(hit.total, 3)
        journal.matched_topics = hit.matched_topics[:6]
        journals.append(journal)

    mode = match_mode_for(merged)
    hint = TOPIC_HINT if mode in {"topic", "mixed"} else None
    return SearchPage(journals=journals, match_mode=mode, hint=hint)


def get_journal(
    conn: sqlite3.Connection,
    journal_id: int,
    year: int | None = None,
) -> Journal | None:
    row = conn.execute(
        "SELECT * FROM journals WHERE id = ?", (journal_id,)
    ).fetchone()
    if row is None:
        return None
    return _hydrate(conn, row, year)


def _name_hits(conn: sqlite3.Connection, query: str) -> dict[int, ScoredHit]:
    hits: dict[int, ScoredHit] = {}
    fts = _fts_query(query)
    rows = []
    if fts:
        rows = conn.execute(
            """
            SELECT j.id, j.display_name, j.cited_by_count
            FROM journals_fts
            JOIN journals j ON j.id = journals_fts.rowid
            WHERE journals_fts MATCH ?
            """,
            (fts,),
        ).fetchall()
    if not rows:
        like = f"%{query}%"
        rows = conn.execute(
            """
            SELECT id, display_name, cited_by_count FROM journals
            WHERE display_name LIKE ? COLLATE NOCASE
               OR publisher LIKE ? COLLATE NOCASE
            """,
            (like, like),
        ).fetchall()
    q_low = query.lower()
    for row in rows:
        score = 2.0
        name = (row["display_name"] or "").lower()
        if name == q_low:
            score = 8.0
        elif name.startswith(q_low):
            score = 5.0
        hits[row["id"]] = ScoredHit(journal_id=row["id"], name_score=score)
    return hits


def _allowed_journal_ids(
    conn: sqlite3.Connection,
    join_sql: str,
    join_params: list,
    extra_and: str,
    filter_params: list,
) -> set[int] | None:
    if not extra_and and not filter_params:
        return None
    sql = f"""
        SELECT journals.id FROM journals
        {join_sql}
        {extra_and.replace("AND", "WHERE", 1) if extra_and.startswith("AND") else extra_and}
    """
    # extra_and is "AND m.jcr..." when filters exist; convert to WHERE
    if extra_and:
        sql = f"""
            SELECT journals.id FROM journals
            {join_sql}
            WHERE {extra_and.removeprefix("AND ").strip()}
        """
    rows = conn.execute(sql, [*join_params, *filter_params]).fetchall()
    return {row[0] for row in rows}


def _citation(conn: sqlite3.Connection, journal_id: int) -> int:
    row = conn.execute(
        "SELECT cited_by_count FROM journals WHERE id = ?", (journal_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def _metrics_join(year: int | None) -> tuple[str, list]:
    sql = """
        LEFT JOIN journal_metrics m ON m.id = (
            SELECT m2.id FROM journal_metrics m2
            WHERE m2.journal_id = journals.id
    """
    params: list = []
    if year is not None:
        sql += " AND m2.year = ? "
        params.append(year)
    sql += " ORDER BY m2.year DESC, m2.id DESC LIMIT 1)"
    return sql, params


def _metrics_where(
    jcr_quartile: int | None,
    cas_quartile: int | None,
    warning: bool | None,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if jcr_quartile is not None:
        clauses.append("m.jcr_quartile = ?")
        params.append(jcr_quartile)
    if cas_quartile is not None:
        clauses.append("m.cas_quartile = ?")
        params.append(cas_quartile)
    if warning is True:
        clauses.append("m.warning = 1")
    elif warning is False:
        clauses.append("(m.warning = 0 OR m.warning IS NULL)")
    if not clauses:
        return "", []
    return "WHERE " + " AND ".join(clauses), params


def _hydrate(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    year: int | None = None,
) -> Journal:
    topics = [
        Topic(
            topic_id=t["topic_id"],
            topic_name=t["topic_name"],
            field_name=t["field_name"],
            share=t["share"],
        )
        for t in conn.execute(
            """
            SELECT topic_id, topic_name, field_name, share
            FROM journal_topics
            WHERE journal_id = ?
            ORDER BY share IS NULL, share DESC, topic_name
            """,
            (row["id"],),
        ).fetchall()
    ]
    official = _load_official(conn, row["id"], year)
    issns = json.loads(row["issns"] or "[]")
    return Journal(
        id=row["id"],
        openalex_id=row["openalex_id"],
        display_name=row["display_name"],
        issn_l=row["issn_l"],
        issns=issns,
        publisher=row["publisher"],
        homepage=row["homepage"],
        is_oa=bool(row["is_oa"]),
        works_count=row["works_count"],
        cited_by_count=row["cited_by_count"],
        citedness_2yr=row["citedness_2yr"],
        country_code=row["country_code"],
        type=row["type"],
        topics=topics,
        official=official,
    )


def _load_official(
    conn: sqlite3.Connection,
    journal_id: int,
    year: int | None,
) -> OfficialMetrics | None:
    sql = """
        SELECT m.year, m.jcr_quartile, m.impact_factor, m.impact_factor_5,
               m.cas_quartile, m.warning, b.filename, b.source
        FROM journal_metrics m
        JOIN import_batches b ON b.id = m.batch_id
        WHERE m.journal_id = ?
    """
    params: list = [journal_id]
    if year is not None:
        sql += " AND m.year = ?"
        params.append(year)
    sql += " ORDER BY m.year DESC, m.id DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return OfficialMetrics(
        year=row["year"],
        jcr_quartile=row["jcr_quartile"],
        impact_factor=row["impact_factor"],
        impact_factor_5=row["impact_factor_5"],
        cas_quartile=row["cas_quartile"],
        warning=bool(row["warning"]),
        filename=row["filename"],
        source=row["source"],
    )


def _fts_query(raw: str) -> str:
    tokens = [t for t in FTS_SAFE.split(raw.lower()) if t]
    if not tokens:
        return ""
    return " AND ".join(f"{t}*" for t in tokens)
