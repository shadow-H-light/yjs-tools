from __future__ import annotations

import json
import re
import sqlite3

from dataclasses import dataclass, field

from yjs_tools.company.lexicon import expand_major
from yjs_tools.company.models import (
    Company,
    Dispute,
    Finance,
    Job,
    RecruitmentRound,
    UniversityLink,
)

FTS_SAFE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
SEARCH_BY = {"auto", "name", "industry", "code", "major", "job"}
OWNERSHIPS = {"soe", "private", "foreign"}
SEASONS = {"秋招", "春招", "实习"}


@dataclass
class CompanyPage:
    companies: list[Company]
    match_mode: str
    search_by: str = "auto"
    hint: str | None = None
    total: int = 0

    def to_dict(self, query: str) -> dict:
        return {
            "query": query,
            "count": len(self.companies),
            "total": self.total if self.total else len(self.companies),
            "match_mode": self.match_mode,
            "search_by": self.search_by,
            "hint": self.hint,
            "results": [c.to_dict() for c in self.companies],
        }


def company_stats(conn: sqlite3.Connection) -> dict:
    count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    last = conn.execute(
        "SELECT value FROM meta WHERE key = 'last_company_ingest_at'"
    ).fetchone()
    batches = conn.execute("SELECT COUNT(*) FROM company_import_batches").fetchone()[0]
    jobs = conn.execute("SELECT COUNT(*) FROM company_jobs").fetchone()[0]
    return {
        "companies": count,
        "jobs": jobs,
        "import_batches": batches,
        "last_ingest_at": last[0] if last else None,
    }


def search_companies(
    conn: sqlite3.Connection,
    query: str = "",
    *,
    limit: int = 20,
    offset: int = 0,
    by: str = "auto",
    ownership: str | None = None,
    city: str | None = None,
    season: str | None = None,
    central: bool | None = None,
    size: str | None = None,
) -> CompanyPage:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    by = by if by in SEARCH_BY else "auto"
    q = query.strip()
    where = ["1=1"]
    params: list = []
    if ownership in OWNERSHIPS:
        where.append("c.ownership = ?")
        params.append(ownership)
    if central is True:
        where.append("c.is_central_soe = 1")
    if size in {"large", "medium", "small"}:
        where.append("c.size_band = ?")
        params.append(size)
    if city:
        where.append(
            "(c.hq_city LIKE ? OR EXISTS (SELECT 1 FROM company_jobs j WHERE j.company_id = c.id AND j.city LIKE ?))"
        )
        like = f"%{city}%"
        params.extend([like, like])
    if season in SEASONS:
        where.append(
            "EXISTS (SELECT 1 FROM recruitment_rounds r WHERE r.company_id = c.id AND r.season = ?)"
        )
        params.append(season)

    matched_map: dict[int, list[str]] = {}
    if q:
        ids = _query_ids(conn, q, by)
        if not ids:
            return CompanyPage(companies=[], match_mode=by, search_by=by, total=0)
        placeholders = ",".join("?" * len(ids))
        where.append(f"c.id IN ({placeholders})")
        params.extend(ids)
        matched_map = _matched_terms(conn, q, by, ids)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM companies c WHERE {where_sql}", params
    ).fetchone()[0]
    order_sql = (
        "c.is_central_soe DESC, "
        "CASE WHEN c.employees IS NULL THEN 1 ELSE 0 END, "
        "c.employees DESC, c.display_name COLLATE NOCASE"
    )
    if q and ids:
        order_sql = (
            "CASE c.id "
            + " ".join(f"WHEN {int(cid)} THEN {rank}" for rank, cid in enumerate(ids))
            + " END, "
            + order_sql
        )
    rows = conn.execute(
        f"""
        SELECT c.* FROM companies c
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    companies = [_hydrate(conn, row) for row in rows]
    for company in companies:
        company.matched = matched_map.get(company.id, [])
        company.match_score = float(len(company.matched))
    return CompanyPage(
        companies=companies,
        match_mode=by if q else "browse",
        search_by=by,
        total=int(total),
        hint=_hint(by, q, companies),
    )


def _hint(by: str, q: str, companies) -> str | None:
    if not q:
        return None
    if by in {"major", "job"} and all(not c.jobs for c in companies):
        return "当前按专业/岗位词匹配行业与名称。导入校招岗位表后会更准。"
    if by in {"major", "industry"}:
        return "当前是行业/专业词匹配，未启用向量模型。"
    return None


def get_company(conn: sqlite3.Connection, company_id: int) -> Company | None:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        return None
    return _hydrate(conn, row)


def _query_ids(conn: sqlite3.Connection, query: str, by: str) -> list[int]:
    compact = query.replace(" ", "")
    if by == "code" or (by == "auto" and _looks_like_code(compact)):
        return [
            r["id"]
            for r in conn.execute(
                """
                SELECT id FROM companies
                WHERE ticker = ? COLLATE NOCASE
                   OR wikidata_id = ? COLLATE NOCASE
                   OR IFNULL(credit_code, '') = ?
                """,
                (compact, compact.upper() if compact[:1] in "Qq" else compact, compact),
            )
        ]
    terms = expand_major(query) if by in {"auto", "major", "job", "industry"} else [query]
    found: dict[int, int] = {}
    if by in {"auto", "name", "industry", "major"}:
        for term in [query, *terms[:6]]:
            like = f"%{term}%"
            fts = _fts_query(term)
            if fts:
                for row in conn.execute(
                    """
                    SELECT c.id FROM companies_fts
                    JOIN companies c ON c.id = companies_fts.rowid
                    WHERE companies_fts MATCH ?
                    """,
                    (fts,),
                ):
                    found[row["id"]] = found.get(row["id"], 0) + 3
            for row in conn.execute(
                """
                SELECT id FROM companies
                WHERE display_name LIKE ? COLLATE NOCASE
                   OR IFNULL(aliases, '') LIKE ? COLLATE NOCASE
                """,
                (like, like),
            ):
                found[row["id"]] = found.get(row["id"], 0) + 2
            if by != "name":
                for row in conn.execute(
                    """
                    SELECT company_id FROM company_industries
                    WHERE industry LIKE ? COLLATE NOCASE
                    """,
                    (like,),
                ):
                    found[row["company_id"]] = found.get(row["company_id"], 0) + 4
    if by in {"auto", "major", "job"}:
        for term in terms:
            like = f"%{term}%"
            for row in conn.execute(
                """
                SELECT company_id FROM company_jobs
                WHERE title LIKE ? COLLATE NOCASE
                   OR IFNULL(major, '') LIKE ? COLLATE NOCASE
                   OR IFNULL(city, '') LIKE ? COLLATE NOCASE
                """,
                (like, like, like),
            ):
                found[row["company_id"]] = found.get(row["company_id"], 0) + 5
    return [cid for cid, _ in sorted(found.items(), key=lambda kv: -kv[1])]


def _matched_terms(conn: sqlite3.Connection, query: str, by: str, ids: list[int]) -> dict[int, list[str]]:
    terms = expand_major(query)
    out: dict[int, list[str]] = {i: [] for i in ids}
    if not ids:
        return out
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT company_id, industry FROM company_industries WHERE company_id IN ({placeholders})",
        ids,
    ).fetchall()
    jobs = conn.execute(
        f"SELECT company_id, title, major FROM company_jobs WHERE company_id IN ({placeholders})",
        ids,
    ).fetchall()
    for row in rows:
        for term in terms:
            if term.lower() in (row["industry"] or "").lower():
                if term not in out[row["company_id"]]:
                    out[row["company_id"]].append(term)
    for row in jobs:
        blob = f"{row['title']} {row['major'] or ''}"
        for term in terms:
            if term.lower() in blob.lower() and term not in out[row["company_id"]]:
                out[row["company_id"]].append(term)
    return out


def _looks_like_code(value: str) -> bool:
    if value.upper().startswith("Q") and value[1:].isdigit():
        return True
    if len(value) in {5, 6} and value.isalnum():
        return True
    if len(value) == 18 and value.isalnum():
        return True
    return False


def _fts_query(raw: str) -> str:
    tokens = [t for t in FTS_SAFE.split(raw.lower()) if t]
    if not tokens:
        return ""
    return " AND ".join(f"{t}*" for t in tokens[:6])


def _hydrate(conn: sqlite3.Connection, row: sqlite3.Row) -> Company:
    aliases = []
    if row["aliases"]:
        try:
            aliases = json.loads(row["aliases"])
        except json.JSONDecodeError:
            aliases = []
    industries = [
        r["industry"]
        for r in conn.execute(
            "SELECT industry FROM company_industries WHERE company_id = ? ORDER BY industry",
            (row["id"],),
        )
    ]
    jobs = [
        Job(title=r["title"], major=r["major"], city=r["city"], education=r["education"], year=r["year"])
        for r in conn.execute(
            "SELECT title, major, city, education, year FROM company_jobs WHERE company_id = ? LIMIT 20",
            (row["id"],),
        )
    ]
    rounds = [
        RecruitmentRound(
            year=r["year"],
            season=r["season"],
            start_date=r["start_date"],
            end_date=r["end_date"],
            headcount=r["headcount"],
            source=r["source"],
        )
        for r in conn.execute(
            """
            SELECT year, season, start_date, end_date, headcount, source
            FROM recruitment_rounds WHERE company_id = ?
            ORDER BY year DESC LIMIT 8
            """,
            (row["id"],),
        )
    ]
    finance = [
        Finance(
            year=r["year"],
            revenue=r["revenue"],
            net_income=r["net_income"],
            currency=r["currency"],
            source=r["source"],
        )
        for r in conn.execute(
            "SELECT year, revenue, net_income, currency, source FROM company_finance WHERE company_id = ?",
            (row["id"],),
        )
    ]
    disputes = [
        Dispute(year=r["year"], case_type=r["case_type"], summary=r["summary"], url=r["url"])
        for r in conn.execute(
            "SELECT year, case_type, summary, url FROM company_disputes WHERE company_id = ? LIMIT 10",
            (row["id"],),
        )
    ]
    universities = [
        UniversityLink(
            university=r["university"],
            relation=r["relation"],
            works_count=r["works_count"],
            source=r["source"],
        )
        for r in conn.execute(
            """
            SELECT university, relation, works_count, source
            FROM company_universities WHERE company_id = ?
            ORDER BY works_count DESC LIMIT 8
            """,
            (row["id"],),
        )
    ]
    return Company(
        id=row["id"],
        wikidata_id=row["wikidata_id"],
        display_name=row["display_name"],
        aliases=aliases if isinstance(aliases, list) else [],
        homepage=row["homepage"],
        ticker=row["ticker"],
        credit_code=row["credit_code"],
        country_code=row["country_code"],
        hq_city=row["hq_city"],
        ownership=row["ownership"] or "unknown",
        is_central_soe=bool(row["is_central_soe"]),
        bianzhi=row["bianzhi"],
        size_band=row["size_band"],
        foreign_origin=row["foreign_origin"],
        employees=row["employees"],
        founded_year=row["founded_year"],
        salary_note=row["salary_note"],
        industries=industries,
        jobs=jobs,
        rounds=rounds,
        finance=finance,
        disputes=disputes,
        universities=universities,
    )
