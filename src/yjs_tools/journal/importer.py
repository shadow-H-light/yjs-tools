from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from yjs_tools.journal.issn import normalize_issn

HEADER_MAP = {
    "issn": "issn",
    "issnl": "issn",
    "刊号": "issn",
    "year": "year",
    "年份": "year",
    "jcrquartile": "jcr_quartile",
    "jcrq": "jcr_quartile",
    "jcr": "jcr_quartile",
    "jcr分区": "jcr_quartile",
    "impactfactor": "impact_factor",
    "if": "impact_factor",
    "jif": "impact_factor",
    "影响因子": "impact_factor",
    "impactfactor5": "impact_factor_5",
    "if5": "impact_factor_5",
    "jif5": "impact_factor_5",
    "五年影响因子": "impact_factor_5",
    "casquartile": "cas_quartile",
    "cas": "cas_quartile",
    "casq": "cas_quartile",
    "中科院分区": "cas_quartile",
    "中科院": "cas_quartile",
    "warning": "warning",
    "预警": "warning",
    "reviewdays": "review_days",
    "reviewday": "review_days",
    "审稿时长": "review_days",
    "审稿天数": "review_days",
    "reviewweeks": "review_weeks",
    "审稿周数": "review_weeks",
}

QUARTILE_MAP = {
    "1": 1,
    "q1": 1,
    "一区": 1,
    "1区": 1,
    "2": 2,
    "q2": 2,
    "二区": 2,
    "2区": 2,
    "3": 3,
    "q3": 3,
    "三区": 3,
    "3区": 3,
    "4": 4,
    "q4": 4,
    "四区": 4,
    "4区": 4,
}


class MetricsImportError(ValueError):
    pass


def list_batches(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, filename, year, source, imported_at, matched, unmatched
        FROM import_batches
        ORDER BY imported_at DESC, id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def delete_batch(conn: sqlite3.Connection, batch_id: int) -> bool:
    cur = conn.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
    conn.commit()
    return cur.rowcount > 0


def import_metrics_csv(
    conn: sqlite3.Connection,
    *,
    content: str,
    filename: str,
    year: int | None = None,
    source: str = "csv",
) -> dict:
    rows = _parse_csv(content)
    if not rows:
        raise MetricsImportError("CSV 没有数据行")
    if "issn" not in rows[0]:
        raise MetricsImportError("缺少 ISSN 列（issn / 刊号）")

    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch_year = year or _first_year(rows)
    if batch_year is None:
        raise MetricsImportError("请提供 --year，或在 CSV 中加入 year / 年份列")

    cur = conn.execute(
        """
        INSERT INTO import_batches (filename, year, source, imported_at, matched, unmatched)
        VALUES (?, ?, ?, ?, 0, 0)
        """,
        (filename, batch_year, source or "csv", imported_at),
    )
    batch_id = cur.lastrowid
    matched = 0
    unmatched: list[str] = []

    for row in rows:
        issn = normalize_issn(row.get("issn") or "")
        if not issn:
            unmatched.append(row.get("issn") or "")
            continue
        journal_id = _find_journal_id(conn, issn)
        if journal_id is None:
            unmatched.append(issn)
            continue
        row_year = _as_year(row.get("year")) or batch_year
        conn.execute(
            """
            INSERT INTO journal_metrics (
                batch_id, journal_id, year, jcr_quartile, impact_factor,
                impact_factor_5, cas_quartile, warning, review_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                journal_id,
                row_year,
                _as_quartile(row.get("jcr_quartile")),
                _as_float(row.get("impact_factor")),
                _as_float(row.get("impact_factor_5")),
                _as_quartile(row.get("cas_quartile")),
                1 if _as_bool(row.get("warning")) else 0,
                _as_review_days(row.get("review_days"), row.get("review_weeks")),
            ),
        )
        matched += 1

    conn.execute(
        "UPDATE import_batches SET matched = ?, unmatched = ? WHERE id = ?",
        (matched, len(unmatched), batch_id),
    )
    conn.commit()
    return {
        "batch_id": batch_id,
        "filename": filename,
        "year": batch_year,
        "source": source or "csv",
        "matched": matched,
        "unmatched": len(unmatched),
        "unmatched_issns": unmatched[:50],
    }


def decode_csv_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise MetricsImportError(
        "CSV 编码无法识别，请用 Excel「另存为」UTF-8 CSV 后再导入。"
    )


def import_metrics_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    year: int | None = None,
    source: str = "csv",
) -> dict:
    text = decode_csv_bytes(path.read_bytes())
    return import_metrics_csv(
        conn,
        content=text,
        filename=path.name,
        year=year,
        source=source,
    )


def _parse_csv(content: str) -> list[dict[str, str | None]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise MetricsImportError("无法读取表头")
    mapping = {}
    for raw in reader.fieldnames:
        key = _norm_header(raw)
        mapped = HEADER_MAP.get(key)
        if mapped:
            mapping[raw] = mapped
    if "issn" not in mapping.values():
        raise MetricsImportError("缺少 ISSN 列（issn / 刊号）")
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


def _norm_header(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
    )


def _find_journal_id(conn: sqlite3.Connection, issn: str) -> int | None:
    row = conn.execute(
        "SELECT id, issn_l, issns FROM journals WHERE issn_l = ?",
        (issn,),
    ).fetchone()
    if row:
        return int(row["id"])
    needle = issn.lower()
    for row in conn.execute("SELECT id, issns FROM journals WHERE issns LIKE ?", (f"%{issn}%",)):
        issns = [normalize_issn(x) for x in json.loads(row["issns"] or "[]")]
        if needle in {x.lower() for x in issns if x}:
            return int(row["id"])
    return None


def _first_year(rows: list[dict]) -> int | None:
    for row in rows:
        year = _as_year(row.get("year"))
        if year:
            return year
    return None


def _as_year(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) >= 4:
        year = int(digits[:4])
        if 1900 <= year <= 2100:
            return year
    return None


def _as_quartile(value: str | None) -> int | None:
    if not value:
        return None
    key = str(value).strip().lower().replace(" ", "")
    return QUARTILE_MAP.get(key)


def _as_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _as_bool(value: str | None) -> bool:
    if not value:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "预警"}


def _as_review_days(days: str | None, weeks: str | None) -> int | None:
    parsed = _as_int(days)
    if parsed is not None:
        return parsed
    week_count = _as_float(weeks)
    if week_count is None:
        return None
    return int(round(week_count * 7))


def _as_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return int(digits)
