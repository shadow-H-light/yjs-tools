from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import uvicorn

from yjs_tools.api import create_app
from yjs_tools.db import connect, init_db
from yjs_tools.journal import (
    delete_batch,
    import_metrics_file,
    ingest_openalex,
    list_batches,
    search_journals,
    stats,
)
from yjs_tools.journal.importer import MetricsImportError
from yjs_tools.paths import DEFAULT_DB_PATH

app = typer.Typer(help="选刊神器：本机国际刊检索。", no_args_is_help=True)


def _db(db_path: Path):
    conn = connect(db_path)
    init_db(conn)
    return conn


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """启动本机服务。"""
    uvicorn.run(create_app(db), host=host, port=port, log_level="info")


@app.command()
def ingest(
    limit: int = 200,
    query: Optional[str] = None,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """从 OpenAlex 同步国际刊到本机 SQLite。"""
    conn = _db(db)
    try:
        result = ingest_openalex(conn, limit=limit, query=query)
        typer.echo(
            f"同步完成：新增 {result['inserted']}，更新 {result['updated']}，"
            f"合计 {result['total']}"
        )
        s = stats(conn)
        typer.echo(f"库中现有期刊 {s['journals']} 种")
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
    except MetricsImportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
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
    jcr: Optional[int] = None,
    cas: Optional[int] = None,
    year: Optional[int] = None,
    db: Path = DEFAULT_DB_PATH,
) -> None:
    """本机检索期刊。"""
    conn = _db(db)
    try:
        items = search_journals(
            conn,
            query,
            limit=limit,
            jcr_quartile=jcr,
            cas_quartile=cas,
            year=year,
        )
        if not items:
            typer.echo("没有匹配的期刊。先运行 xuankan ingest，或放宽筛选。")
            raise typer.Exit(code=1)
        for j in items:
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
            typer.echo(
                f"{j.display_name}\t{issn}\t被引 {j.cited_by_count}\t{official}"
            )
    finally:
        conn.close()


@app.command()
def stat(db: Path = DEFAULT_DB_PATH) -> None:
    """查看本机库规模。"""
    conn = _db(db)
    try:
        s = stats(conn)
        typer.echo(
            f"期刊 {s['journals']} · 主题 {s['topics']} · "
            f"导入批次 {s['import_batches']} · 上次同步 {s['last_ingest_at'] or '尚未同步'}"
        )
    finally:
        conn.close()
