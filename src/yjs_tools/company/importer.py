from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from yjs_tools.company.classify import size_band
from yjs_tools.journal.importer import (
    MetricsImportError,
    _norm_header,
    _parse_xlsx,
    decode_csv_bytes,
)

HEADER_MAP = {
    "name": "name",
    "公司": "name",
    "公司名称": "name",
    "qid": "qid",
    "wikidata": "qid",
    "ticker": "ticker",
    "股票代码": "ticker",
    "creditcode": "credit_code",
    "统一社会信用代码": "credit_code",
    "ownership": "ownership",
    "所有制": "ownership",
    "类型": "ownership",
    "bianzhi": "bianzhi",
    "编制": "bianzhi",
    "central": "central",
    "央企": "central",
    "salary": "salary_note",
    "薪资": "salary_note",
    "note": "note",
    "备注": "note",
    "homepage": "homepage",
    "官网": "homepage",
    "website": "homepage",
    "industry": "industry",
    "行业": "industry",
    "education": "education",
    "学历": "education",
    "employees": "employees",
    "员工数": "employees",
    "origin": "foreign_origin",
    "外资归属": "foreign_origin",
    "jobtitle": "title",
    "title": "title",
    "岗位": "title",
    "major": "major",
    "专业": "major",
    "city": "city",
    "地点": "city",
    "城市": "city",
    "hq": "city",
    "总部": "city",
    "season": "season",
    "季节": "season",
    "start": "start_date",
    "开始": "start_date",
    "end": "end_date",
    "结束": "end_date",
    "headcount": "headcount",
    "人数": "headcount",
    "招录人数": "headcount",
    "year": "year",
    "年份": "year",
    "casetype": "case_type",
    "纠纷类型": "case_type",
    "summary": "summary",
    "摘要": "summary",
    "url": "url",
    "university": "university",
    "高校": "university",
    "relation": "relation",
    "关系": "relation",
}

OWNERSHIP_MAP = {
    "国企": "soe",
    "soe": "soe",
    "央企": "soe",
    "私企": "private",
    "民营": "private",
    "private": "private",
    "外企": "foreign",
    "外资": "foreign",
    "foreign": "foreign",
}


def list_company_batches(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, filename, year, kind, source, imported_at, matched, unmatched
        FROM company_import_batches
        ORDER BY imported_at DESC, id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def delete_company_batch(conn: sqlite3.Connection, batch_id: int) -> bool:
    cur = conn.execute("DELETE FROM company_import_batches WHERE id = ?", (batch_id,))
    conn.commit()
    return cur.rowcount > 0


def import_company_bytes(
    conn: sqlite3.Connection,
    raw: bytes,
    *,
    filename: str,
    year: int | None = None,
    kind: str = "companies",
    source: str = "csv",
) -> dict:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        rows = _parse_xlsx(raw, HEADER_MAP)
        if not rows:
            raise MetricsImportError("Excel 是空的")
    else:
        rows = _parse_csv(decode_csv_bytes(raw))
    return import_company_rows(
        conn, rows, filename=filename, year=year, kind=kind, source=source
    )


def import_company_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    year: int | None = None,
    kind: str = "companies",
    source: str = "csv",
) -> dict:
    return import_company_bytes(
        conn, path.read_bytes(), filename=path.name, year=year, kind=kind, source=source
    )


def import_company_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, str | None]],
    *,
    filename: str,
    year: int | None,
    kind: str,
    source: str,
) -> dict:
    if not rows:
        raise MetricsImportError("没有可导入的数据行")
    batch_year = year or _first_year(rows) or datetime.now(timezone.utc).year
    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """
        INSERT INTO company_import_batches
            (filename, year, kind, source, imported_at, matched, unmatched)
        VALUES (?, ?, ?, ?, ?, 0, 0)
        """,
        (filename, batch_year, kind or "companies", source or "csv", imported_at),
    )
    batch_id = cur.lastrowid
    matched = 0
    unmatched: list[str] = []
    kind = (kind or "companies").lower()
    if kind == "central":
        kind = "companies"
    for row in rows:
        company_id = _find_company(conn, row)
        if company_id is None and kind == "companies":
            company_id = _insert_company(conn, row)
        if company_id is None:
            unmatched.append(
                row.get("name") or row.get("ticker") or row.get("qid") or row.get("title") or ""
            )
            continue
        if kind == "jobs":
            if not row.get("title") or company_id is None:
                unmatched.append(row.get("title") or "")
                continue
            conn.execute(
                """
                INSERT INTO company_jobs (company_id, batch_id, title, major, city, education, year)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    batch_id,
                    row.get("title"),
                    row.get("major"),
                    row.get("city"),
                    row.get("education"),
                    _as_int(row.get("year")) or batch_year,
                ),
            )
            if row.get("season") or row.get("start_date") or row.get("headcount"):
                conn.execute(
                    """
                    INSERT INTO recruitment_rounds
                        (company_id, batch_id, year, season, start_date, end_date, headcount, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        batch_id,
                        _as_int(row.get("year")) or batch_year,
                        row.get("season") or "秋招",
                        row.get("start_date"),
                        row.get("end_date"),
                        _as_int(row.get("headcount")),
                        filename,
                    ),
                )
            matched += 1
            continue
        if kind == "disputes":
            if company_id is None:
                unmatched.append(row.get("name") or "")
                continue
            conn.execute(
                """
                INSERT INTO company_disputes (company_id, batch_id, year, case_type, summary, url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    batch_id,
                    _as_int(row.get("year")) or batch_year,
                    row.get("case_type"),
                    row.get("summary") or row.get("note"),
                    row.get("url"),
                ),
            )
            matched += 1
            continue
        if kind == "universities":
            if company_id is None or not row.get("university"):
                unmatched.append(row.get("university") or "")
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO company_universities
                    (company_id, university, relation, works_count, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    row.get("university"),
                    row.get("relation") or "导入",
                    None,
                    filename,
                ),
            )
            matched += 1
            continue
        updates = []
        params: list = []
        if row.get("credit_code"):
            updates.append("credit_code = ?")
            params.append(row["credit_code"])
        if row.get("bianzhi"):
            updates.append("bianzhi = ?")
            params.append(row["bianzhi"])
        if row.get("salary_note"):
            updates.append("salary_note = ?")
            params.append(row["salary_note"])
        if row.get("homepage"):
            updates.append("homepage = ?")
            params.append(row["homepage"])
        if row.get("city"):
            updates.append("hq_city = COALESCE(hq_city, ?)")
            params.append(row["city"])
        if row.get("foreign_origin"):
            updates.append("foreign_origin = ?")
            params.append(row["foreign_origin"])
        employees = _as_int(row.get("employees"))
        if employees is not None:
            updates.append("employees = ?")
            params.append(employees)
            band = size_band(employees)
            if band:
                updates.append("size_band = ?")
                params.append(band)
        ownership = OWNERSHIP_MAP.get((row.get("ownership") or "").strip().lower())
        if ownership:
            updates.append("ownership = ?")
            params.append(ownership)
        if _is_central(row):
            updates.append("is_central_soe = 1")
            updates.append("ownership = 'soe'")
        if row.get("note"):
            updates.append("salary_note = COALESCE(salary_note, ?)")
            params.append(row["note"])
        if updates:
            params.append(company_id)
            conn.execute(f"UPDATE companies SET {', '.join(updates)} WHERE id = ?", params)
        _add_industries(conn, company_id, row.get("industry"))
        matched += 1

    conn.execute(
        "UPDATE company_import_batches SET matched = ?, unmatched = ? WHERE id = ?",
        (matched, len(unmatched), batch_id),
    )
    conn.commit()
    return {
        "batch_id": batch_id,
        "filename": filename,
        "year": batch_year,
        "kind": kind,
        "matched": matched,
        "unmatched": len(unmatched),
        "unmatched_names": unmatched[:50],
    }


def _parse_csv(content: str) -> list[dict[str, str | None]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise MetricsImportError("无法读取表头")
    mapping = {}
    for raw in reader.fieldnames:
        mapped = HEADER_MAP.get(_norm_header(raw or ""))
        if mapped:
            mapping[raw] = mapped
    rows: list[dict[str, str | None]] = []
    for raw_row in reader:
        item: dict[str, str | None] = {}
        for raw_key, value in raw_row.items():
            mapped = mapping.get(raw_key)
            if mapped:
                item[mapped] = (value or "").strip() or None
        if any(item.values()):
            rows.append(item)
    return rows


def _insert_company(conn: sqlite3.Connection, row: dict[str, str | None]) -> int | None:
    name = (row.get("name") or "").strip()
    qid = (row.get("qid") or "").strip().upper()
    if not name:
        return None
    if qid and not qid.startswith("Q"):
        qid = ""
    wikidata_id = qid or _local_qid(name, row.get("ticker"))
    existing = conn.execute(
        "SELECT id FROM companies WHERE wikidata_id = ?", (wikidata_id,)
    ).fetchone()
    if existing:
        return int(existing["id"])
    ownership = OWNERSHIP_MAP.get((row.get("ownership") or "").strip().lower(), "unknown")
    central = _is_central(row)
    if central:
        ownership = "soe"
    employees = _as_int(row.get("employees"))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """
        INSERT INTO companies (
            wikidata_id, display_name, homepage, ticker, credit_code, hq_city,
            ownership, is_central_soe, bianzhi, size_band, foreign_origin,
            employees, salary_note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            wikidata_id,
            name,
            row.get("homepage"),
            row.get("ticker"),
            row.get("credit_code"),
            row.get("city"),
            ownership,
            1 if central else 0,
            row.get("bianzhi"),
            size_band(employees),
            row.get("foreign_origin"),
            employees,
            row.get("salary_note") or row.get("note"),
            now,
        ),
    )
    company_id = int(cur.lastrowid)
    _add_industries(conn, company_id, row.get("industry"))
    return company_id


def _add_industries(conn: sqlite3.Connection, company_id: int, raw: str | None) -> None:
    if not raw:
        return
    for part in raw.replace("；", ";").replace("、", ";").replace(",", ";").split(";"):
        industry = part.strip()
        if industry:
            conn.execute(
                "INSERT OR IGNORE INTO company_industries(company_id, industry) VALUES (?, ?)",
                (company_id, industry),
            )


def _is_central(row: dict[str, str | None]) -> bool:
    central = (row.get("central") or "").strip()
    ownership = (row.get("ownership") or "").strip()
    return central in {"1", "是", "央企", "true", "yes"} or ownership == "央企"


def _local_qid(name: str, ticker: str | None) -> str:
    base = (ticker or name).strip()
    slug = "".join(ch for ch in base if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")[:40]
    return f"LOCAL-{slug or 'co'}"


def _find_company(conn: sqlite3.Connection, row: dict[str, str | None]) -> int | None:
    qid = (row.get("qid") or "").strip().upper()
    if qid:
        hit = conn.execute(
            "SELECT id FROM companies WHERE wikidata_id = ?", (qid,)
        ).fetchone()
        if hit:
            return int(hit["id"])
    ticker = (row.get("ticker") or "").strip()
    if ticker:
        hit = conn.execute(
            "SELECT id FROM companies WHERE ticker = ? COLLATE NOCASE", (ticker,)
        ).fetchone()
        if hit:
            return int(hit["id"])
    name = (row.get("name") or "").strip()
    if name:
        hit = conn.execute(
            "SELECT id FROM companies WHERE display_name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if hit:
            return int(hit["id"])
        like = f"%{name}%"
        hit = conn.execute(
            """
            SELECT id FROM companies
            WHERE display_name LIKE ? COLLATE NOCASE
               OR IFNULL(aliases, '') LIKE ? COLLATE NOCASE
            LIMIT 1
            """,
            (like, like),
        ).fetchone()
        if hit:
            return int(hit["id"])
    return None


def _first_year(rows: list[dict]) -> int | None:
    for row in rows:
        year = _as_int(row.get("year"))
        if year and 1990 <= year <= 2100:
            return year
    return None


def _as_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return int(digits)
