from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from yjs_tools.api import create_app
from yjs_tools.company.classify import classify_ownership, size_band
from yjs_tools.company.importer import import_company_bytes
from yjs_tools.company.ingest import ingest_wikidata
from yjs_tools.company.search import search_companies
from yjs_tools.db import init_db


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def test_classify_central_soe_without_bianzhi():
    ownership, central, foreign = classify_ownership(
        country_qid="Q148",
        instance_ids={"Q270791"},
        owner_ids=set(),
        wikidata_id="Q557083",
    )
    assert ownership == "soe"
    assert central is True
    assert foreign is None


def test_classify_foreign_origin():
    ownership, central, foreign = classify_ownership(
        country_qid="Q183",
        instance_ids=set(),
        owner_ids=set(),
        wikidata_id="Q81230",
    )
    assert ownership == "foreign"
    assert central is False
    assert foreign == "Q183"


def test_size_band_thresholds():
    assert size_band(100000) == "large"
    assert size_band(2000) == "medium"
    assert size_band(80) == "small"
    assert size_band(None) is None


def test_import_companies_jobs_and_search_major():
    conn = _conn()
    companies = Path("examples/companies-sample.csv").read_bytes()
    jobs = Path("examples/jobs-sample.csv").read_bytes()
    company_result = import_company_bytes(
        conn, companies, filename="companies-sample.csv", year=2026, kind="companies"
    )
    job_result = import_company_bytes(
        conn, jobs, filename="jobs-sample.csv", year=2026, kind="jobs"
    )
    assert company_result["matched"] == 4
    assert job_result["matched"] == 4

    grid = search_companies(conn, "国家电网", by="name").companies[0]
    assert grid.is_central_soe is True
    assert grid.ownership == "soe"
    assert grid.bianzhi is None

    huawei = search_companies(conn, "光学工程", by="major").companies
    assert any(c.display_name.startswith("华为") for c in huawei)
    optics = next(c for c in huawei if c.display_name.startswith("华为"))
    assert any("光学" in (job.title or "") for job in optics.jobs)
    assert optics.salary_note and "样例" in optics.salary_note

    autumn = search_companies(conn, "", season="秋招")
    assert autumn.total >= 2


def test_ingest_wikidata_mock():
    conn = _conn()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = (request.content or b"").decode("utf-8", "ignore")
        if "wbsearchentities" in url or "wbsearchentities" in body:
            return httpx.Response(
                200,
                json={"search": [{"id": "Q208732"}]},
            )
        if "EntityData/Q208732" in url:
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q208732": {
                            "id": "Q208732",
                            "labels": {
                                "zh": {"value": "华为"},
                                "en": {"value": "Huawei"},
                            },
                            "aliases": {"zh": [{"value": "华为技术"}]},
                            "claims": {
                                "P17": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {"id": "Q148"},
                                                "type": "wikibase-entityid",
                                            }
                                        }
                                    }
                                ],
                                "P31": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {"id": "Q4830453"},
                                                "type": "wikibase-entityid",
                                            }
                                        }
                                    }
                                ],
                                "P856": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": "https://www.huawei.com",
                                                "type": "string",
                                            }
                                        }
                                    }
                                ],
                                "P1128": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {"amount": "+194000"},
                                                "type": "quantity",
                                            }
                                        }
                                    }
                                ],
                                "P452": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {"id": "Q11661"},
                                                "type": "wikibase-entityid",
                                            }
                                        }
                                    }
                                ],
                            },
                        }
                    }
                },
            )
        if "wbgetentities" in url or "wbgetentities" in body:
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q148": {"id": "Q148", "labels": {"zh": {"value": "中国"}}},
                        "Q11661": {
                            "id": "Q11661",
                            "labels": {"zh": {"value": "信息技术"}},
                        },
                    }
                },
            )
        if "openalex.org/works" in url:
            return httpx.Response(
                200,
                json={
                    "group_by": [
                        {
                            "key_display_name": "Tsinghua University",
                            "count": 12,
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "unexpected"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ingest_wikidata(conn, limit=1, query="Huawei", client=client)
    assert result["inserted"] == 1
    page = search_companies(conn, "华为", by="name")
    company = page.companies[0]
    assert company.display_name == "华为"
    assert company.homepage == "https://www.huawei.com"
    assert company.ownership == "private"
    assert company.is_central_soe is False
    assert company.bianzhi is None
    assert company.size_band == "large"
    assert "信息技术" in company.industries
    assert company.universities[0].university == "Tsinghua University"


def test_ingest_skips_humans():
    conn = _conn()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = (request.content or b"").decode("utf-8", "ignore")
        if "wbsearchentities" in url or "wbsearchentities" in body:
            return httpx.Response(200, json={"search": [{"id": "Q5"}]})
        if "EntityData/Q5" in url:
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q5": {
                            "id": "Q5",
                            "labels": {"en": {"value": "human"}},
                            "claims": {
                                "P31": [
                                    {
                                        "mainsnak": {
                                            "datavalue": {
                                                "value": {"id": "Q5"},
                                                "type": "wikibase-entityid",
                                            }
                                        }
                                    }
                                ]
                            },
                        }
                    }
                },
            )
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ingest_wikidata(conn, limit=1, query="human", client=client)
    assert result["total"] == 0
    assert search_companies(conn, "human").companies == []


def test_company_api(tmp_path: Path):
    db_path = tmp_path / "gongsi.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    import_company_bytes(
        conn,
        Path("examples/companies-sample.csv").read_bytes(),
        filename="companies-sample.csv",
        year=2026,
        kind="companies",
    )
    conn.close()

    with TestClient(create_app(db_path)) as client:
        stats = client.get("/api/companies/stats")
        assert stats.status_code == 200
        assert stats.json()["companies"] == 4
        found = client.get("/api/companies", params={"q": "华为", "by": "name"})
        assert found.status_code == 200
        assert found.json()["count"] == 1
        company_id = found.json()["results"][0]["id"]
        detail = client.get(f"/api/companies/{company_id}")
        assert detail.status_code == 200
        assert detail.json()["display_name"].startswith("华为")
        compare = client.get("/api/companies/compare", params={"ids": "1,2"})
        assert compare.status_code == 200
        assert compare.json()["count"] == 2
        page1 = client.get("/api/companies", params={"limit": 2, "offset": 0})
        page2 = client.get("/api/companies", params={"limit": 2, "offset": 2})
        assert page1.json()["total"] == 4
        assert len(page1.json()["results"]) == 2
        assert len(page2.json()["results"]) == 2
        assert {r["id"] for r in page1.json()["results"]}.isdisjoint(
            {r["id"] for r in page2.json()["results"]}
        )
