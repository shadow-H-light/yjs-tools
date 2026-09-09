from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import httpx
import typer
import uvicorn

from yjs_tools import __version__
from yjs_tools.api import create_app
from yjs_tools.db import connect, init_db
from yjs_tools.errors import explain_error
from yjs_tools.company import (
    companies_to_csv,
    company_stats,
    compare_companies,
    delete_company_batch,
    import_company_file,
    ingest_wikidata,
    list_company_batches,
    search_companies,
)
from yjs_tools.journal import (
    compare_journals,
    delete_batch,
    import_metrics_file,
    ingest_openalex,
    journals_to_csv,
    list_batches,
    parse_ids,
    search_journals,
    stats,
)
from yjs_tools.journal.compare import CompareError
from yjs_tools.journal.importer import MetricsImportError
from yjs_tools.paths import DEFAULT_DB_PATH, WEB_DIST

app = typer.Typer(help="本机研究生工具：选刊神器与公司查询。", no_args_is_help=True)
gongsi_app = typer.Typer(help="公司查询。", no_args_is_help=True)
app.add_typer(gongsi_app, name="gongsi")


def _version_flag(value: bool) -> None:
    if value:
        typer.echo(f"xuankan {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="显示版本。",
        callback=_version_flag,
        is_eager=True,
    ),
) -> None:
    return


def _fail(exc: BaseException) -> None:
    typer.echo(explain_error(exc), err=True)
    raise typer.Exit(code=1) from exc


def _db(db_path: Path):
    try:
        conn = connect(db_path)
        init_db(conn)
        return conn
    except Exception as exc:
        _fail(exc)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """启动本机服务。"""
    if not WEB_DIST.exists():
        typer.echo(
            "未找到 web/dist。先执行：cd web && npm install && npm run build\n"
            "或另开终端 npm run dev（http://127.0.0.1:5173）。API 仍可用。",
            err=True,
        )
    uvicorn.run(create_app(db), host=host, port=port, log_level="info")


@app.command()
def ingest(
    limit: int = 800,
    query: Optional[str] = None,
    scope: str = "all",
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """从 OpenAlex 全面同步期刊。ISSN、主页、被引缺失时重试；影响因子/分区需另导入 CSV。scope=all/intl/cn。"""
    conn = _db(db)
    try:
        result = ingest_openalex(conn, limit=limit, query=query, scope=scope)
        typer.echo(
            f"同步完成（{result.get('scope', scope)}）：新增 {result['inserted']}，"
            f"更新 {result['updated']}，合计 {result['total']}"
            f"；补全请求 {result.get('completed', 0)} 次"
        )
        missing_issn = result.get("missing_issn")
        missing_home = result.get("missing_homepage")
        if missing_issn or missing_home:
            typer.echo(
                f"仍缺 ISSN {missing_issn or 0} 种、主页 {missing_home or 0} 种"
                "（OpenAlex 本身没有的会显示暂无；影响因子/分区需导入 CSV）"
            )
        s = stats(conn)
        typer.echo(
            f"库中现有期刊 {s['journals']} 种，其中中文刊 {s.get('chinese_journals', 0)} 种"
        )
    except (httpx.HTTPError, OSError, sqlite3.OperationalError) as exc:
        _fail(exc)
    finally:
        conn.close()


@app.command("import")
def import_csv(
    csv_path: Path = typer.Argument(..., exists=True, readable=True),
    year: Optional[int] = None,
    source: str = "csv",
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """导入本地分区/影响因子 CSV 或 xlsx。数字来自你提供的表，不是本工具测算。"""
    conn = _db(db)
    try:
        result = import_metrics_file(conn, csv_path, year=year, source=source)
        typer.echo(
            f"导入完成：匹配 {result['matched']}，未匹配 {result['unmatched']}，"
            f"批次 #{result['batch_id']}（{result['year']}）"
        )
        if result["unmatched_issns"]:
            typer.echo("未入库 ISSN：" + ", ".join(result["unmatched_issns"][:20]))
    except (MetricsImportError, UnicodeDecodeError, OSError, sqlite3.OperationalError) as exc:
        _fail(exc)
    finally:
        conn.close()


@app.command("imports")
def imports_cmd(db: Path = DEFAULT_DB_PATH) -> None:
    """列出已导入批次。"""
    conn = _db(db)
    try:
        batches = list_batches(conn)
        if not batches:
            typer.echo("还没有导入批次。")
            return
        for batch in batches:
            typer.echo(
                f"#{batch['id']}\t{batch['year']}\t{batch['filename']}\t"
                f"匹配 {batch['matched']} / 未匹配 {batch['unmatched']}"
            )
    finally:
        conn.close()


@app.command("import-delete")
def import_delete(batch_id: int, db: Path = DEFAULT_DB_PATH) -> None:
    """删除一个导入批次，对应官方指标一并去掉。"""
    conn = _db(db)
    try:
        if not delete_batch(conn, batch_id):
            typer.echo("没有这个批次。", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"已删除批次 #{batch_id}")
    finally:
        conn.close()


@app.command()
def search(
    query: str = typer.Argument(default=""),
    limit: int = 10,
    by: str = "auto",
    region: str = "all",
    sort: str = "relevance",
    jcr: Optional[int] = None,
    cas: Optional[int] = None,
    year: Optional[int] = None,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """本机检索期刊。by=auto/name/topic/issn；region=all/cn/intl。"""
    conn = _db(db)
    try:
        page = search_journals(
            conn,
            query,
            limit=limit,
            jcr_quartile=jcr,
            cas_quartile=cas,
            year=year,
            resolve_remote=True,
            by=by,
            region=region,
            sort=sort,
        )
        if not page.journals:
            typer.echo("没有匹配的期刊。先运行 xuankan ingest，或放宽筛选。")
            raise typer.Exit(code=1)
        if page.hint:
            typer.echo(page.hint)
        for j in page.journals:
            issn = j.issn_l or "暂无"
            link = j.homepage or "暂无"
            factor = "暂无"
            quartile = "暂无"
            if j.official:
                if j.official.impact_factor is not None:
                    factor = str(j.official.impact_factor)
                bits = []
                if j.official.jcr_quartile:
                    bits.append(f"JCR Q{j.official.jcr_quartile}")
                if j.official.cas_quartile:
                    bits.append(f"中科院{j.official.cas_quartile}区")
                if bits:
                    quartile = " ".join(bits)
            matched = "；".join(t.topic_name for t in j.matched_topics[:3])
            extra = f"\t命中 {matched}" if matched else ""
            review = ""
            if j.official and j.official.review_days is not None:
                review = f"\t审稿 {j.official.review_days} 天"
            typer.echo(
                f"{j.display_name}\t编号 {issn}/{j.openalex_id}\t链接 {link}\t"
                f"影响因子 {factor}\t被引 {j.cited_by_count}\t分区 {quartile}"
                f"{review}{extra}"
            )
    finally:
        conn.close()


@app.command()
def compare(
    ids: str,
    year: Optional[int] = None,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """并排对比 2–4 本刊，期刊 id 用逗号分隔。"""
    conn = _db(db)
    try:
        journals = compare_journals(conn, parse_ids(ids), year=year)
        for j in journals:
            review = "暂无"
            if j.official and j.official.review_days is not None:
                review = f"{j.official.review_days} 天"
            jcr = (
                f"Q{j.official.jcr_quartile}"
                if j.official and j.official.jcr_quartile
                else "暂无"
            )
            factor = (
                str(j.official.impact_factor)
                if j.official and j.official.impact_factor is not None
                else "暂无"
            )
            cas = (
                f"{j.official.cas_quartile}区"
                if j.official and j.official.cas_quartile
                else "暂无"
            )
            typer.echo(
                f"{j.display_name}\t{j.issn_l or '-'}\tJCR {jcr}\tIF {factor}\t"
                f"中科院 {cas}\t审稿 {review}"
            )
    except (CompareError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()


@app.command("export")
def export_cmd(
    query: str = "",
    out: Path = Path("xuankan-export.csv"),
    ids: Optional[str] = None,
    by: str = "auto",
    region: str = "all",
    jcr: Optional[int] = None,
    cas: Optional[int] = None,
    limit: int = 20,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """把检索结果或对比列表导出为 CSV。缺审稿写暂无。"""
    conn = _db(db)
    try:
        if ids:
            journals = compare_journals(conn, parse_ids(ids))
        else:
            journals = search_journals(
                conn,
                query,
                limit=limit,
                jcr_quartile=jcr,
                cas_quartile=cas,
                resolve_remote=True,
                by=by,
                region=region,
            ).journals
        out.write_text(journals_to_csv(journals), encoding="utf-8")
        typer.echo(f"已写入 {out}（{len(journals)} 行）")
    except (CompareError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()


@app.command()
def stat(db: Path = DEFAULT_DB_PATH) -> None:
    """查看本机库规模。"""
    conn = _db(db)
    try:
        s = stats(conn)
        cs = company_stats(conn)
        typer.echo(
            f"期刊 {s['journals']}（中文刊 {s.get('chinese_journals', 0)}）· "
            f"主题 {s['topics']} · "
            f"导入批次 {s['import_batches']} · 上次同步 {s['last_ingest_at'] or '尚未同步'}"
        )
        typer.echo(
            f"公司 {cs['companies']} · 岗位 {cs['jobs']} · "
            f"公司导入 {cs['import_batches']} · 上次同步 {cs['last_ingest_at'] or '尚未同步'}"
        )
    finally:
        conn.close()


@gongsi_app.command("ingest")
def gongsi_ingest(
    limit: int = 400,
    query: Optional[str] = None,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """从 Wikidata 同步企业公开档案。"""
    conn = _db(db)
    try:
        result = ingest_wikidata(conn, limit=limit, query=query)
        typer.echo(
            f"公司同步完成：新增 {result['inserted']}，更新 {result['updated']}，合计 {result['total']}"
        )
        s = company_stats(conn)
        typer.echo(f"库中现有公司 {s['companies']} 家，岗位 {s['jobs']} 条")
    except (httpx.HTTPError, OSError, sqlite3.OperationalError) as exc:
        _fail(exc)
    finally:
        conn.close()


@gongsi_app.command("import")
def gongsi_import(
    csv_path: Path = typer.Argument(..., exists=True, readable=True),
    year: Optional[int] = None,
    kind: str = "companies",
    source: str = "csv",
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """导入公司名单 / 岗位校招 / 纠纷 / 高校表。kind=companies|jobs|disputes|universities"""
    conn = _db(db)
    try:
        result = import_company_file(conn, csv_path, year=year, kind=kind, source=source)
        typer.echo(
            f"导入完成：匹配 {result['matched']}，未匹配 {result['unmatched']}，"
            f"批次 #{result['batch_id']}（{result['kind']}）"
        )
    except (MetricsImportError, OSError, sqlite3.OperationalError) as exc:
        _fail(exc)
    finally:
        conn.close()


@gongsi_app.command("search")
def gongsi_search(
    query: str = typer.Argument(default=""),
    limit: int = 10,
    by: str = "auto",
    ownership: Optional[str] = None,
    city: Optional[str] = None,
    season: Optional[str] = None,
    size: Optional[str] = None,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """检索公司。by=auto/name/industry/code/major/job。"""
    conn = _db(db)
    try:
        page = search_companies(
            conn,
            query,
            limit=limit,
            by=by,
            ownership=ownership,
            city=city,
            season=season,
            size=size,
        )
        if page.hint:
            typer.echo(page.hint)
        if not page.companies:
            typer.echo("没有匹配的公司。先运行 xuankan gongsi ingest。")
            raise typer.Exit(code=1)
        labels = {"soe": "国企", "private": "私企", "foreign": "外企"}
        for c in page.companies:
            kind = "央企" if c.is_central_soe else labels.get(c.ownership, "暂无")
            loc = c.jobs[0].city if c.jobs and c.jobs[0].city else (c.hq_city or "暂无")
            typer.echo(
                f"{c.display_name}\t{kind}\t编号 {c.wikidata_id}"
                f"\t地点 {loc}\t链接 {c.homepage or '暂无'}"
            )
    finally:
        conn.close()


@gongsi_app.command("compare")
def gongsi_compare(ids: str, db: Path = DEFAULT_DB_PATH) -> None:
    """对比 2–4 家公司。"""
    conn = _db(db)
    try:
        companies = compare_companies(conn, parse_ids(ids))
        for c in companies:
            typer.echo(
                f"{c.display_name}\t{c.ownership}\t编制 {c.bianzhi or '暂无'}\t"
                f"薪资 {c.salary_note or '暂无'}"
            )
    except (CompareError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()


@gongsi_app.command("import-delete")
def gongsi_import_delete(batch_id: int, db: Path = DEFAULT_DB_PATH) -> None:
    """删除一个公司导入批次。"""
    conn = _db(db)
    try:
        if not delete_company_batch(conn, batch_id):
            typer.echo("没有这个批次。", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"已删除公司批次 #{batch_id}")
    finally:
        conn.close()


@gongsi_app.command("imports")
def gongsi_imports(db: Path = DEFAULT_DB_PATH) -> None:
    conn = _db(db)
    try:
        batches = list_company_batches(conn)
        if not batches:
            typer.echo("还没有公司导入批次。")
            return
        for batch in batches:
            typer.echo(
                f"#{batch['id']}\t{batch['kind']}\t{batch['filename']}\t"
                f"匹配 {batch['matched']} / 未匹配 {batch['unmatched']}"
            )
    finally:
        conn.close()
