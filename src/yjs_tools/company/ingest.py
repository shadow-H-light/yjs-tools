from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from yjs_tools.company.classify import CENTRAL_SOE_IDS, classify_ownership, size_band
from yjs_tools.http import create_client
from yjs_tools.journal.ingest import USER_AGENT, get_json, post_json

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
OPENALEX_WORKS = "https://api.openalex.org/works"

# Direct QIDs confirmed via EntityData / previous good search hits.
KNOWN_QIDS = (
    "Q208732",  # Huawei
    "Q160120",  # Huawei
    "Q860580",  # Tencent
    "Q1359568",  # Alibaba
    "Q55606242",  # ByteDance
    "Q18653563",  # CATL
    "Q1636958",  # Xiaomi
    "Q27423",  # BYD Auto
    "Q803824",  # BOE
    "Q648533",  # SMIC
    "Q1143211",  # Haier
    "Q14799",  # Lenovo
    "Q14772",  # Baidu
    "Q15907772",  # Meituan
    "Q557083",  # State Grid
    "Q81230",  # Siemens
    "Q20718",  # Samsung Electronics
    "Q713144",  # TSMC
    "Q300718",  # ASML
    "Q248",  # Intel
    "Q206162",  # Qualcomm
    "Q312",  # Apple
    "Q9366",  # Google
    "Q2283",  # Microsoft
    "Q182477",  # NVIDIA
    "Q128376",  # AMD
    "Q61064",  # Bosch
    "Q186079",  # Foxconn
    "Q197021",  # ZTE
    "Q17027991",  # Sunny Optical
    "Q5760704",  # Hikvision
    "Q16924332",  # DJI
    "Q19892610",  # Goertek
    "Q741618",  # China Mobile
    "Q1115363",  # COMAC
    "Q19840026",  # CRRC
    "Q795354",  # CNOOC
    "Q910401",  # SAIC
    "Q159433",  # 3M
)

SEED_NAMES = (
    "宁德时代",
    "京东方",
    "中芯国际",
    "台积电",
    "华为",
    "腾讯",
    "阿里巴巴",
    "字节跳动",
    "百度",
    "美团",
    "小米",
    "比亚迪",
    "海尔",
    "联想",
    "海康威视",
    "大疆",
    "舜宇光学",
    "歌尔",
    "北方华创",
    "中微公司",
    "韦尔股份",
    "立讯精密",
    "工业富联",
    "富士康",
    "中兴通讯",
    "大华股份",
    "科大讯飞",
    "汇川技术",
    "阳光电源",
    "隆基绿能",
    "通威股份",
    "亿纬锂能",
    "蔚来",
    "小鹏汽车",
    "理想汽车",
    "上汽集团",
    "一汽",
    "广汽",
    "长城汽车",
    "国家电网",
    "中国石油",
    "中国石化",
    "中国海油",
    "中国移动",
    "中国商飞",
    "中国中车",
    "中国建筑",
    "华虹半导体",
    "三安光电",
    "大族激光",
    "华工科技",
    "水晶光电",
    "永新光学",
    "蓝特光学",
    "福晶科技",
    "欧菲光",
    "瑞声科技",
    "Apple",
    "Microsoft",
    "Google",
    "NVIDIA",
    "TSMC",
    "ASML",
    "Intel",
    "Qualcomm",
    "Texas Instruments",
    "STMicroelectronics",
    "NXP",
    "Infineon",
    "Bosch",
    "Siemens",
    "Samsung Electronics",
    "Honeywell",
    "3M",
    "Applied Materials",
    "Tokyo Electron",
    "Lam Research",
    "Synopsys",
    "Cadence",
    "ARM",
    "美的集团",
    "格力电器",
    "海信",
    "TCL科技",
    "三一重工",
    "徐工机械",
    "中联重科",
    "万华化学",
    "恒瑞医药",
    "药明康德",
    "迈瑞医疗",
    "联影医疗",
    "石头科技",
    "科沃斯",
    "安克创新",
    "传音控股",
    "金山办公",
    "用友网络",
    "中科创达",
    "兆易创新",
    "圣邦股份",
    "澜起科技",
    "长电科技",
    "华天科技",
    "通富微电",
    "拓荆科技",
    "中微公司",
    "盛美上海",
    "华海清科",
    "先导智能",
    "晶盛机电",
    "捷佳伟创",
    "中科飞测",
    "维信诺",
    "深天马",
    "紫光国微",
    "复旦微电",
    "海格通信",
    "中国卫星",
    "伊利股份",
    "中国中免",
    "贵州茅台",
    "中信证券",
    "中国建筑",
    "中国中铁",
    "中国铁建",
    "中国交建",
    "中国电建",
    "国家能源集团",
    "中国中车",
)

JUNK_QIDS = {
    "Q977",  # Djibouti
    "Q180816",  # Dow Jones
    "Q2029273",  # Spanish gazette
    "Q641234",  # Riga arena
    "Q39177",  # arena
    "Q176788",  # political org
    "Q95097",  # Comacchio
    "Q1205755",  # youth institute
    "Q658624",  # forest
    "Q41252",  # Bydgoszcz
    "Q197689",  # Kaja
    "Q627217",  # Boe
    "Q95611555",  # Huawei AppGallery
}

# Wikidata P31 values that usually mean a firm, not a person or product.
COMPANY_INSTANCE_IDS = {
    "Q4830453",  # business
    "Q6881511",  # enterprise
    "Q783794",  # company
    "Q167037",  # corporation
    "Q891723",  # public company
    "Q219577",  # publicly listed company
    "Q270791",  # state-owned enterprise
    "Q161726",  # multinational corporation
    "Q1635405",  # technology company
    "Q1058914",  # software company
}
REJECT_INSTANCE_IDS = {
    "Q5",  # human
    "Q4167410",  # disambiguation
    "Q13442814",  # scholarly article
    "Q11424",  # film
    "Q3918",  # university
    "Q38723",  # higher education institution
    "Q2385804",  # educational institution
    "Q6256",  # country
    "Q3624078",  # sovereign state
    "Q515",  # city
    "Q1549591",  # big city
    "Q483110",  # stadium
    "Q7397",  # software
    "Q166142",  # application
    "Q35127",  # website
    "Q180816",  # stock market index (item itself)
    "Q16521",  # taxon
    "Q1656682",  # event
    "Q16510064",  # sporting event
    "Q215380",  # musical group
    "Q476300",  # competition
}


def ingest_wikidata(
    conn: sqlite3.Connection,
    *,
    limit: int = 400,
    query: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    limit = max(1, min(limit, 800))
    own = client is None
    client = client or create_client(headers={"User-Agent": USER_AGENT})
    inserted = 0
    updated = 0
    seen: set[str] = set()
    _drop_junk(conn)
    _purge_non_companies(conn, client)
    if query and query.strip():
        qids = _search_items(client, query.strip(), remaining=min(8, limit))
    else:
        qids = _catalog_qids(client, min(max(limit * 2, limit + 80), 800))
    try:
        for qid in qids:
            if inserted + updated >= limit:
                break
            if qid in seen or qid in JUNK_QIDS:
                continue
            seen.add(qid)
            entity = _fetch_entity(client, qid)
            if not entity:
                continue
            was_insert = _upsert_company(conn, entity, client=client)
            if was_insert is None:
                continue
            if was_insert:
                inserted += 1
                if inserted <= 15:
                    _link_universities(conn, client, qid)
            else:
                updated += 1
    finally:
        if own:
            client.close()
    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES('last_company_ingest_at', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
    conn.commit()
    return {
        "inserted": inserted,
        "updated": updated,
        "total": inserted + updated,
    }


def _drop_junk(conn: sqlite3.Connection) -> None:
    if not JUNK_QIDS:
        return
    placeholders = ",".join("?" * len(JUNK_QIDS))
    conn.execute(
        f"DELETE FROM companies WHERE wikidata_id IN ({placeholders})",
        tuple(JUNK_QIDS),
    )


def _purge_non_companies(conn: sqlite3.Connection, client: httpx.Client) -> None:
    rows = conn.execute("SELECT id, wikidata_id FROM companies").fetchall()
    for row in rows:
        qid = row["wikidata_id"]
        if str(qid).startswith("LOCAL-"):
            continue
        entity = _fetch_entity(client, qid)
        if entity is None:
            conn.execute("DELETE FROM companies WHERE id = ?", (row["id"],))
            continue
        instance_ids = set(_item_ids(entity, "P31"))
        if _is_company_entity(entity, instance_ids, qid, False):
            continue
        conn.execute("DELETE FROM companies WHERE id = ?", (row["id"],))


def _catalog_qids(client: httpx.Client, limit: int) -> list[str]:
    qids: list[str] = []
    seen: set[str] = set()

    def add(ids: list[str]) -> None:
        for qid in ids:
            if qid and qid not in seen and qid not in JUNK_QIDS:
                seen.add(qid)
                qids.append(qid)

    add(list(KNOWN_QIDS))
    per = 1
    for name in SEED_NAMES:
        if len(qids) >= limit:
            break
        add(_search_items(client, name, remaining=per))
    return qids[:limit]


def _sparql_company_ids(client: httpx.Client, limit: int) -> list[str]:
    if limit <= 0:
        return []
    sparql = f"""
    SELECT DISTINCT ?item WHERE {{
      VALUES ?class {{
        wd:Q4830453 wd:Q6881511 wd:Q891723 wd:Q270791 wd:Q161726 wd:Q1635405
      }}
      ?item wdt:P31 ?class .
      ?item wdt:P17 wd:Q148 .
      ?item wdt:P856 ?url .
    }}
    LIMIT {max(1, min(limit, 400))}
    """
    try:
        response = client.post(
            WIKIDATA_SPARQL,
            data={"query": sparql},
            headers={"Accept": "application/sparql-results+json"},
        )
        if response.status_code >= 400:
            return []
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    ids: list[str] = []
    for row in (payload.get("results") or {}).get("bindings") or []:
        uri = ((row.get("item") or {}).get("value") or "")
        qid = uri.rsplit("/", 1)[-1]
        if qid.startswith("Q"):
            ids.append(qid)
    return ids


def _search_items(client: httpx.Client, query: str, *, remaining: int) -> list[str]:
    try:
        payload = post_json(
            client,
            WIKIDATA_API,
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in query) else "en",
                "uselang": "zh",
                "type": "item",
                "limit": str(min(8, max(1, remaining))),
                "format": "json",
            },
            attempts=3,
            sleeper=lambda _s: None,
        )
    except httpx.HTTPError:
        return []
    ids = []
    for hit in payload.get("search") or []:
        qid = hit.get("id")
        if qid:
            ids.append(qid)
    return ids


def _fetch_entity(client: httpx.Client, qid: str) -> dict[str, Any] | None:
    url = f"{WIKIDATA_ENTITY}/{qid}.json"
    try:
        payload = get_json(client, url, attempts=3, sleeper=lambda _s: None)
    except httpx.HTTPError:
        return None
    return (payload.get("entities") or {}).get(qid)


def _is_company_entity(
    entity: dict[str, Any],
    instance_ids: set[str],
    qid: str,
    already_stored: bool,
) -> bool:
    if str(qid).startswith("LOCAL-"):
        return True
    if qid in JUNK_QIDS:
        return False
    if instance_ids & REJECT_INSTANCE_IDS:
        return False
    if instance_ids & COMPANY_INSTANCE_IDS:
        return True
    return bool(_item_ids(entity, "P414"))


def _upsert_company(
    conn: sqlite3.Connection,
    entity: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> bool | None:
    qid = entity.get("id")
    name = _label(entity)
    if not qid or not name:
        return None
    aliases = _aliases(entity)
    country_qid = _first_item(entity, "P17")
    instance_ids = set(_item_ids(entity, "P31"))
    existing = conn.execute(
        "SELECT is_central_soe, bianzhi, credit_code, salary_note FROM companies WHERE wikidata_id = ?",
        (qid,),
    ).fetchone()
    if not _is_company_entity(entity, instance_ids, qid, existing is not None):
        return None
    owner_ids = set(_item_ids(entity, "P127")) | set(_item_ids(entity, "P749"))
    imported_central = bool(existing["is_central_soe"]) if existing else False
    ownership, is_central, foreign_qid = classify_ownership(
        country_qid=country_qid,
        instance_ids=instance_ids,
        owner_ids=owner_ids,
        wikidata_id=qid,
        is_central_imported=imported_central,
    )
    employees = _quantity(entity, "P1128")
    employees_i = int(employees) if employees is not None else None
    need_ids = [x for x in [country_qid, foreign_qid, _first_item(entity, "P159"), *_item_ids(entity, "P452")[:8]] if x]
    labels = _resolve_labels(client, need_ids)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values = (
        name,
        json.dumps(aliases, ensure_ascii=False),
        _url(entity, "P856"),
        _string(entity, "P249") or _ticker_from_p414(entity),
        existing["credit_code"] if existing else None,
        _country_code(country_qid),
        labels.get(_first_item(entity, "P159") or "", None),
        ownership,
        1 if is_central else 0,
        existing["bianzhi"] if existing else None,
        size_band(employees_i),
        labels.get(foreign_qid or "", None),
        employees_i,
        _year(entity, "P571"),
        existing["salary_note"] if existing else None,
        now,
        qid,
    )
    if existing:
        conn.execute(
            """
            UPDATE companies SET
                display_name = ?, aliases = ?, homepage = ?, ticker = ?,
                credit_code = ?, country_code = ?, hq_city = ?, ownership = ?,
                is_central_soe = ?, bianzhi = ?, size_band = ?, foreign_origin = ?,
                employees = ?, founded_year = ?, salary_note = ?, updated_at = ?
            WHERE wikidata_id = ?
            """,
            values,
        )
        company_id = conn.execute(
            "SELECT id FROM companies WHERE wikidata_id = ?", (qid,)
        ).fetchone()["id"]
    else:
        cur = conn.execute(
            """
            INSERT INTO companies (
                display_name, aliases, homepage, ticker, credit_code, country_code,
                hq_city, ownership, is_central_soe, bianzhi, size_band, foreign_origin,
                employees, founded_year, salary_note, updated_at, wikidata_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        company_id = cur.lastrowid
    conn.execute("DELETE FROM company_industries WHERE company_id = ?", (company_id,))
    for q_ind in _item_ids(entity, "P452")[:8]:
        industry = labels.get(q_ind) or q_ind
        conn.execute(
            "INSERT OR IGNORE INTO company_industries(company_id, industry) VALUES (?, ?)",
            (company_id, industry),
        )
    revenue = _quantity(entity, "P2137")
    profit = _quantity(entity, "P2295")
    if revenue is not None or profit is not None:
        conn.execute(
            """
            INSERT OR REPLACE INTO company_finance
                (company_id, year, revenue, net_income, currency, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                datetime.now(timezone.utc).year,
                revenue,
                profit,
                "wikidata",
                "wikidata",
            ),
        )
    return existing is None


def _link_universities(conn: sqlite3.Connection, client: httpx.Client, qid: str) -> None:
    row = conn.execute(
        "SELECT id, display_name FROM companies WHERE wikidata_id = ?", (qid,)
    ).fetchone()
    if row is None:
        return
    name = row["display_name"]
    url = (
        f"{OPENALEX_WORKS}?filter=raw_affiliation_strings.search:{quote(name)}"
        f"&group_by=authorships.institutions.id&per_page=6"
    )
    try:
        payload = get_json(client, url, attempts=1, sleeper=lambda _s: None)
    except httpx.HTTPError:
        return
    conn.execute(
        "DELETE FROM company_universities WHERE company_id = ? AND source = 'openalex'",
        (row["id"],),
    )
    for group in (payload.get("group_by") or [])[:6]:
        uni = (group.get("key_display_name") or "").strip()
        count = group.get("count")
        if not uni or uni.lower() in {"unknown", "null"}:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO company_universities
                (company_id, university, relation, works_count, source)
            VALUES (?, ?, ?, ?, 'openalex')
            """,
            (row["id"], uni, "合作发文", int(count or 0)),
        )


def _label(entity: dict[str, Any]) -> str:
    labels = entity.get("labels") or {}
    for lang in ("zh", "zh-cn", "zh-hans", "en"):
        if lang in labels and labels[lang].get("value"):
            return labels[lang]["value"]
    if labels:
        return next(iter(labels.values())).get("value") or ""
    return ""


def _aliases(entity: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for lang in ("zh", "en"):
        for item in (entity.get("aliases") or {}).get(lang) or []:
            value = item.get("value")
            if value and value not in out:
                out.append(value)
    return out[:12]


def _item_ids(entity: dict[str, Any], prop: str) -> list[str]:
    ids: list[str] = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            ids.append(value["id"])
    return ids


def _first_item(entity: dict[str, Any], prop: str) -> str | None:
    ids = _item_ids(entity, prop)
    return ids[0] if ids else None


def _string(entity: dict[str, Any], prop: str) -> str | None:
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _url(entity: dict[str, Any], prop: str) -> str | None:
    return _string(entity, prop)


def _quantity(entity: dict[str, Any], prop: str) -> float | None:
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and "amount" in value:
            try:
                return float(str(value["amount"]).replace("+", ""))
            except ValueError:
                return None
    return None


def _year(entity: dict[str, Any], prop: str) -> int | None:
    for claim in (entity.get("claims") or {}).get(prop) or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            digits = "".join(ch for ch in value["time"][:5] if ch.isdigit())
            if len(digits) >= 4:
                year = int(digits[:4])
                if 1800 <= year <= 2100:
                    return year
    return None


def _resolve_labels(client: httpx.Client | None, qids: list[str]) -> dict[str, str]:
    unique = []
    seen: set[str] = set()
    for qid in qids:
        if qid and qid not in seen:
            seen.add(qid)
            unique.append(qid)
    if not unique:
        return {}
    if client is None:
        return {qid: qid for qid in unique}
    joined = "|".join(unique[:40])
    try:
        payload = post_json(
            client,
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": joined,
                "props": "labels",
                "languages": "zh|en",
                "format": "json",
            },
            attempts=3,
            sleeper=lambda _s: None,
        )
    except httpx.HTTPError:
        return {qid: qid for qid in unique}
    out: dict[str, str] = {}
    for qid, ent in (payload.get("entities") or {}).items():
        out[qid] = _label(ent) or qid
    for qid in unique:
        out.setdefault(qid, qid)
    return out


def _country_code(country_qid: str | None) -> str | None:
    mapping = {
        "Q148": "CN",
        "Q30": "US",
        "Q183": "DE",
        "Q17": "JP",
        "Q884": "KR",
        "Q55": "NL",
        "Q145": "GB",
        "Q142": "FR",
        "Q865": "TW",
        "Q8646": "HK",
    }
    return mapping.get(country_qid or "")


def _ticker_from_p414(entity: dict[str, Any]) -> str | None:
    for claim in (entity.get("claims") or {}).get("P414") or []:
        quals = claim.get("qualifiers") or {}
        for prop in ("P249", "P3744"):
            for q in quals.get(prop) or []:
                value = (q.get("datavalue") or {}).get("value")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None
