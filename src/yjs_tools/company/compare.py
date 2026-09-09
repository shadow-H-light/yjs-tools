from __future__ import annotations

import csv
import io
import sqlite3

from yjs_tools.company.models import Company
from yjs_tools.company.search import get_company
from yjs_tools.journal.compare import CompareError, parse_ids

MISSING = "暂无"


def compare_companies(conn: sqlite3.Connection, ids: list[int]) -> list[Company]:
    if not 2 <= len(ids) <= 4:
        raise CompareError("请选择 2–4 家公司进行对比")
    companies: list[Company] = []
    missing: list[int] = []
    for company_id in ids:
        company = get_company(conn, company_id)
        if company is None:
            missing.append(company_id)
        else:
            companies.append(company)
    if missing:
        raise CompareError("找不到公司：" + ",".join(str(i) for i in missing))
    return companies


def companies_to_csv(companies: list[Company]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "name",
            "ownership",
            "central_soe",
            "size_band",
            "foreign_origin",
            "bianzhi",
            "ticker",
            "wikidata_id",
            "hq_city",
            "homepage",
            "salary_note",
            "industries",
            "jobs",
            "universities",
        ]
    )
    for company in companies:
        writer.writerow(
            [
                company.display_name,
                company.ownership,
                "yes" if company.is_central_soe else "no",
                company.size_band or MISSING,
                company.foreign_origin or MISSING,
                company.bianzhi or MISSING,
                company.ticker or "",
                company.wikidata_id,
                company.hq_city or MISSING,
                company.homepage or "",
                company.salary_note or MISSING,
                ";".join(company.industries),
                ";".join(j.title for j in company.jobs),
                ";".join(u.university for u in company.universities),
            ]
        )
    return buffer.getvalue()
