from __future__ import annotations

import json
import re
import sqlite3

from yjs_tools.journal.issn import looks_like_issn, normalize_issn
from yjs_tools.journal.models import Journal, OfficialMetrics, Topic

FTS_SAFE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


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
) -> list[Journal]:
    limit = max(1, min(limit, 100))
    q = query.strip()
    join_sql, join_params = _metrics_join(year)
    filter_sql, filter_params = _metrics_where(jcr_quartile, cas_quartile, warning)

    if not q:
        sql = f"""
            SELECT journals.* FROM journals
            {join_sql}
            {filter_sql}
            ORDER BY journals.cited_by_count DESC, journals.display_name
            LIMIT ?
        """
        rows = conn.execute(sql, [*join_params, *filter_params, limit]).fetchall()
        return [_hydrate(conn, row, year) for row in rows]

    compact = q.replace(" ", "")
    issn = normalize_issn(compact) if looks_like_issn(compact) else None
    if issn:
        sql = f"""
            SELECT journals.* FROM journals
            {join_sql}
            WHERE (journals.issn_l = ? OR journals.issns LIKE ?)
            {filter_sql.replace("WHERE", "AND", 1) if filter_sql else ""}
            ORDER BY journals.cited_by_count DESC
            LIMIT ?
        """
        rows = conn.execute(
            sql, [*join_params, issn, f"%{issn}%", *filter_params, limit]
        ).fetchall()
        if rows:
            return [_hydrate(conn, row, year) for row in rows]

    fts = _fts_query(q)
    if fts:
        sql = f"""
            SELECT journals.* FROM journals
            JOIN journals_fts ON journals.id = journals_fts.rowid
            {join_sql}
            WHERE journals_fts MATCH ?
            {filter_sql.replace("WHERE", "AND", 1) if filter_sql else ""}
            ORDER BY journals.cited_by_count DESC
            LIMIT ?
        """
        rows = conn.execute(sql, [*join_params, fts, *filter_params, limit]).fetchall()
        if rows:
            return [_hydrate(conn, row, year) for row in rows]

    like = f"%{q}%"
    extra_and = filter_sql.replace("WHERE", "AND", 1) if filter_sql else ""
    sql = f"""
        SELECT journals.* FROM journals
        {join_sql}
        WHERE (
            journals.display_name LIKE ? COLLATE NOCASE
            OR journals.publisher LIKE ? COLLATE NOCASE
            OR journals.issn_l LIKE ?
            OR EXISTS (
                SELECT 1 FROM journal_topics t
                WHERE t.journal_id = journals.id
                  AND t.topic_name LIKE ? COLLATE NOCASE
            )
        )
        {extra_and}
        ORDER BY journals.cited_by_count DESC
        LIMIT ?
    """
    rows = conn.execute(
        sql, [*join_params, like, like, like, like, *filter_params, limit]
    ).fetchall()
    return [_hydrate(conn, row, year) for row in rows]


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
