from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from yjs_tools.journal.issn import normalize_issn

HEADER_MAP = {
    "issn": "issn",
    "issnl": "issn",
    "刊号": "issn",
    "eissn": "eissn",
    "eissn号": "eissn",
    "电子issn": "eissn",
    "year": "year",
    "年份": "year",
    "jcrquartile": "jcr_quartile",
    "jcrq": "jcr_quartile",
    "jcr": "jcr_quartile",
    "jcr分区": "jcr_quartile",
    "分区": "jcr_quartile",
    "quartile": "jcr_quartile",
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

_XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


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
    return import_metrics_rows(
        conn,
        _parse_csv(content),
        filename=filename,
        year=year,
        source=source,
    )


def import_metrics_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, str | None]],
    *,
    filename: str,
    year: int | None = None,
    source: str = "csv",
) -> dict:
    if not rows:
        raise MetricsImportError("没有可导入的数据行")

    rows = _collapse_metric_rows(rows)
    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch_year = year or _first_year(rows)
    if batch_year is None:
        raise MetricsImportError("请提供 --year，或在表中加入 year / 年份列")

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
        journal_id = _find_journal_id_for_row(conn, row)
        issn = normalize_issn(row.get("issn") or "") or normalize_issn(row.get("eissn") or "")
        if journal_id is None:
            unmatched.append(issn or row.get("issn") or row.get("eissn") or "")
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


def import_metrics_bytes(
    conn: sqlite3.Connection,
    raw: bytes,
    *,
    filename: str,
    year: int | None = None,
    source: str = "csv",
) -> dict:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        try:
            rows = _parse_xlsx(raw)
        except (KeyError, zipfile.BadZipFile, ET.ParseError, IndexError) as exc:
            raise MetricsImportError("无法读取 Excel，请确认是 .xlsx 文件。") from exc
        return import_metrics_rows(
            conn, rows, filename=filename, year=year, source=source
        )
    return import_metrics_csv(
        conn,
        content=decode_csv_bytes(raw),
        filename=filename,
        year=year,
        source=source,
    )


def import_metrics_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    year: int | None = None,
    source: str = "csv",
) -> dict:
    return import_metrics_bytes(
        conn,
        path.read_bytes(),
        filename=path.name,
        year=year,
        source=source,
    )


def _parse_csv(content: str) -> list[dict[str, str | None]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise MetricsImportError("无法读取表头")
    mapping = _header_mapping(reader.fieldnames)
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


def _header_mapping(
    fieldnames: list[str | None],
    header_map: dict[str, str] | None = None,
) -> dict[str, str]:
    table = header_map or HEADER_MAP
    mapping: dict[str, str] = {}
    for raw in fieldnames:
        if not raw:
            continue
        mapped = table.get(_norm_header(raw))
        if mapped:
            mapping[raw] = mapped
    if header_map is None and "issn" not in mapping.values() and "eissn" not in mapping.values():
        raise MetricsImportError("缺少 ISSN 列（issn / 刊号 / EISSN）")
    return mapping


def _parse_xlsx(
    raw: bytes, header_map: dict[str, str] | None = None
) -> list[dict[str, str | None]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        strings = _xlsx_strings(zf)
        sheet = _xlsx_first_sheet(zf)
        table = _xlsx_rows(zf, sheet, strings)
    if not table:
        raise MetricsImportError("Excel 是空的")
    headers = [(cell or "").strip() for cell in table[0]]
    mapping = _header_mapping(headers, header_map)
    rows: list[dict[str, str | None]] = []
    for line in table[1:]:
        item: dict[str, str | None] = {}
        for index, raw_key in enumerate(headers):
            mapped = mapping.get(raw_key)
            if not mapped:
                continue
            value = line[index] if index < len(line) else None
            text = str(value).strip() if value is not None else ""
            item[mapped] = text or None
        if any(item.values()):
            rows.append(item)
    return rows


def _xlsx_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out: list[str] = []
    for si in root.findall("m:si", _XLSX_NS):
        out.append("".join(t.text or "" for t in si.findall(".//{*}t")))
    return out


def _xlsx_first_sheet(zf: zipfile.ZipFile) -> str:
    names = [
        n
        for n in zf.namelist()
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    ]
    if not names:
        raise MetricsImportError("Excel 里没有工作表")
    return sorted(names)[0]


def _xlsx_col_index(cell_ref: str) -> int:
    col = 0
    for ch in cell_ref:
        if not ch.isalpha():
            break
        col = col * 26 + (ord(ch.upper()) - 64)
    return col - 1


def _xlsx_rows(zf: zipfile.ZipFile, sheet_path: str, strings: list[str]) -> list[list[str | None]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: list[list[str | None]] = []
    for row in root.findall("m:sheetData/m:row", _XLSX_NS):
        cells: dict[int, str | None] = {}
        max_col = 0
        for cell in row.findall("m:c", _XLSX_NS):
            ref = cell.attrib.get("r", "A1")
            col = _xlsx_col_index(ref)
            max_col = max(max_col, col)
            value = None
            v = cell.find("m:v", _XLSX_NS)
            is_ = cell.find("m:is", _XLSX_NS)
            kind = cell.attrib.get("t")
            if kind == "s" and v is not None and v.text:
                value = strings[int(v.text)]
            elif kind == "inlineStr" and is_ is not None:
                value = "".join(t.text or "" for t in is_.findall(".//{*}t"))
            elif v is not None:
                value = v.text
            cells[col] = value
        rows.append([cells.get(i) for i in range(max_col + 1)])
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


def _collapse_metric_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    groups: dict[str, dict[str, str | None]] = {}
    index: dict[str, str] = {}
    leftovers: list[dict[str, str | None]] = []

    for row in rows:
        keys = [
            issn
            for issn in (
                normalize_issn(row.get("issn") or ""),
                normalize_issn(row.get("eissn") or ""),
            )
            if issn
        ]
        if not keys:
            leftovers.append(row)
            continue
        gid = next((index[k] for k in keys if k in index), None)
        if gid is None:
            gid = keys[0]
            groups[gid] = dict(row)
        else:
            groups[gid] = _merge_metric_row(groups[gid], row)
        for key in keys:
            index[key] = gid
    return list(groups.values()) + leftovers


def _merge_metric_row(
    current: dict[str, str | None], incoming: dict[str, str | None]
) -> dict[str, str | None]:
    merged = dict(current)
    for key in ("issn", "eissn", "impact_factor", "impact_factor_5", "year"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    current_q = _as_quartile(current.get("jcr_quartile"))
    incoming_q = _as_quartile(incoming.get("jcr_quartile"))
    if incoming_q is not None and (current_q is None or incoming_q < current_q):
        merged["jcr_quartile"] = incoming.get("jcr_quartile")
    current_cas = _as_quartile(current.get("cas_quartile"))
    incoming_cas = _as_quartile(incoming.get("cas_quartile"))
    if incoming_cas is not None and (current_cas is None or incoming_cas < current_cas):
        merged["cas_quartile"] = incoming.get("cas_quartile")
    return merged


def _find_journal_id_for_row(conn: sqlite3.Connection, row: dict[str, str | None]) -> int | None:
    for raw in (row.get("issn"), row.get("eissn")):
        issn = normalize_issn(raw or "")
        if not issn:
            continue
        found = _find_journal_id(conn, issn)
        if found is not None:
            return found
    return None


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
    if key in {"n/a", "na", "none", "-", "无"}:
        return None
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
