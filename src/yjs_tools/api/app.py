from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from yjs_tools import __version__
from yjs_tools.db import connect, init_db
from yjs_tools.errors import explain_error
from yjs_tools.journal import (
    compare_journals,
    decode_csv_bytes,
    delete_batch,
    get_journal,
    import_metrics_csv,
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


def _open_db(path: Path):
    conn = connect(path)
    init_db(conn)
    return conn


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path or DEFAULT_DB_PATH

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = _open_db(path)
        try:
            yield
        finally:
            app.state.db.close()

    app = FastAPI(
        title="选刊神器",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "db": str(path)}

    def db():
        conn = getattr(app.state, "db", None)
        if conn is None:
            conn = _open_db(path)
            app.state.db = conn
        return conn

    @app.exception_handler(httpx.HTTPError)
    async def httpx_error(_request: Request, exc: httpx.HTTPError):
        return JSONResponse(status_code=502, content={"detail": explain_error(exc)})

    @app.exception_handler(sqlite3.OperationalError)
    async def sqlite_error(_request: Request, exc: sqlite3.OperationalError):
        return JSONResponse(status_code=503, content={"detail": explain_error(exc)})

    @app.get("/api/stats")
    def api_stats():
        return stats(db())

    @app.get("/api/journals")
    def api_search(
        q: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=100),
        jcr: int | None = Query(default=None, ge=1, le=4),
        cas: int | None = Query(default=None, ge=1, le=4),
        year: int | None = Query(default=None, ge=1900, le=2100),
        warning: bool | None = Query(default=None),
    ):
        page = search_journals(
            db(),
            q,
            limit=limit,
            jcr_quartile=jcr,
            cas_quartile=cas,
            year=year,
            warning=warning,
            resolve_remote=True,
        )
        return page.to_dict(q)

    @app.get("/api/journals/{journal_id}")
    def api_detail(
        journal_id: int,
        year: int | None = Query(default=None, ge=1900, le=2100),
    ):
        journal = get_journal(db(), journal_id, year=year)
        if journal is None:
            raise HTTPException(status_code=404, detail="journal not found")
        return journal.to_dict()

    @app.get("/api/compare")
    def api_compare(
        ids: str = Query(...),
        year: int | None = Query(default=None, ge=1900, le=2100),
    ):
        try:
            journals = compare_journals(db(), parse_ids(ids), year=year)
        except (CompareError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"count": len(journals), "results": [j.to_dict() for j in journals]}

    @app.get("/api/export")
    def api_export(
        q: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=100),
        jcr: int | None = Query(default=None, ge=1, le=4),
        cas: int | None = Query(default=None, ge=1, le=4),
        year: int | None = Query(default=None, ge=1900, le=2100),
        ids: str | None = Query(default=None),
    ):
        try:
            if ids:
                journals = compare_journals(db(), parse_ids(ids), year=year)
            else:
                journals = search_journals(
                    db(),
                    q,
                    limit=limit,
                    jcr_quartile=jcr,
                    cas_quartile=cas,
                    year=year,
                    resolve_remote=True,
                ).journals
        except (CompareError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        csv_text = journals_to_csv(journals)
        return PlainTextResponse(
            csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=xuankan.csv"},
        )

    @app.post("/api/ingest")
    def api_ingest(
        limit: int = Query(default=200, ge=1, le=500),
        query: str | None = Query(default=None),
    ):
        result = ingest_openalex(db(), limit=limit, query=query)
        return {**result, "stats": stats(db())}

    @app.get("/api/imports")
    def api_list_imports():
        return {"results": list_batches(db())}

    @app.post("/api/imports")
    async def api_import(
        file: UploadFile = File(...),
        year: str | None = Form(default=None),
        source: str = Form(default="csv"),
    ):
        raw = await file.read()
        try:
            text = decode_csv_bytes(raw)
        except MetricsImportError as exc:
            raise HTTPException(status_code=400, detail=explain_error(exc)) from exc
        year_int = int(year) if year and year.strip() else None
        try:
            result = import_metrics_csv(
                db(),
                content=text,
                filename=file.filename or "upload.csv",
                year=year_int,
                source=source or "csv",
            )
        except MetricsImportError as exc:
            raise HTTPException(status_code=400, detail=explain_error(exc)) from exc
        return {**result, "stats": stats(db())}

    @app.delete("/api/imports/{batch_id}")
    def api_delete_import(batch_id: int):
        if not delete_batch(db(), batch_id):
            raise HTTPException(status_code=404, detail="import batch not found")
        return {"ok": True, "stats": stats(db())}

    if WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="ui")

    return app
