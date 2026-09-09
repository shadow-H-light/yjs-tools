from __future__ import annotations

import csv
import io
import sqlite3

from yjs_tools.journal.models import Journal
from yjs_tools.journal.search import get_journal

MISSING = "暂无"


class CompareError(ValueError):
    pass


def parse_ids(raw: str) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value not in seen:
            seen.add(value)
            ids.append(value)
    return ids


def compare_journals(
    conn: sqlite3.Connection,
    ids: list[int],
    year: int | None = None,
) -> list[Journal]:
    if not 2 <= len(ids) <= 4:
        raise CompareError("请选择 2–4 本期刊进行对比")
    journals: list[Journal] = []
    missing: list[int] = []
    for journal_id in ids:
        journal = get_journal(conn, journal_id, year=year)
        if journal is None:
            missing.append(journal_id)
        else:
            journals.append(journal)
    if missing:
        raise CompareError("找不到期刊：" + ",".join(str(i) for i in missing))
    return journals


def journals_to_csv(journals: list[Journal]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "name",
            "issn",
            "publisher",
            "cited_by_count",
            "openalex_2yr_citedness",
            "jcr_quartile",
            "impact_factor",
            "cas_quartile",
            "review_days",
            "is_oa",
            "homepage",
            "source_year",
        ]
    )
    for journal in journals:
        official = journal.official
        writer.writerow(
            [
                journal.display_name,
                journal.issn_l or "",
                journal.publisher or "",
                journal.cited_by_count,
                journal.citedness_2yr if journal.citedness_2yr is not None else "",
                official.jcr_quartile if official and official.jcr_quartile else MISSING,
                official.impact_factor if official and official.impact_factor is not None else MISSING,
                official.cas_quartile if official and official.cas_quartile else MISSING,
                official.review_days if official and official.review_days is not None else MISSING,
                "yes" if journal.is_oa else "no",
                journal.homepage or "",
                official.year if official else "",
            ]
        )
    return buffer.getvalue()
