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

app = typer.Typer(help="选刊神器：本机国际刊检索。", no_args_is_help=True)


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
    limit: int = 200,
    query: Optional[str] = None,
    scope: str = "all",
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """从 OpenAlex 同步期刊。scope=all 含中文刊，intl 仅国际刊，cn 仅中文刊。"""
    conn = _db(db)
    try:
        result = ingest_openalex(conn, limit=limit, query=query, scope=scope)
        typer.echo(
            f"同步完成（{result.get('scope', scope)}）：新增 {result['inserted']}，"
            f"更新 {result['updated']}，合计 {result['total']}"
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
    """导入本地分区/影响因子 CSV。数字来自你提供的表，不是本工具测算。"""
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
            issn = j.issn_l or "-"
            official = "-"
            if j.official:
                bits = [f"{j.official.year}导入"]
                if j.official.jcr_quartile:
                    bits.append(f"JCR Q{j.official.jcr_quartile}")
                if j.official.impact_factor is not None:
                    bits.append(f"IF {j.official.impact_factor}")
                if j.official.cas_quartile:
                    bits.append(f"中科院{j.official.cas_quartile}区")
                official = " ".join(bits)
            matched = "；".join(t.topic_name for t in j.matched_topics[:3])
            extra = f"\t命中 {matched}" if matched else ""
            review = "暂无"
            if j.official and j.official.review_days is not None:
                review = f"审稿 {j.official.review_days} 天"
            typer.echo(
                f"{j.display_name}\t{issn}\t被引 {j.cited_by_count}\t{official}\t{review}{extra}"
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
        typer.echo(
            f"期刊 {s['journals']}（中文刊 {s.get('chinese_journals', 0)}）· "
            f"主题 {s['topics']} · "
            f"导入批次 {s['import_batches']} · 上次同步 {s['last_ingest_at'] or '尚未同步'}"
        )
    finally:
        conn.close()
