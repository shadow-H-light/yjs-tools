from __future__ import annotations

import sqlite3

import httpx

from yjs_tools.journal.importer import MetricsImportError


def explain_error(exc: BaseException) -> str:
    if isinstance(exc, MetricsImportError):
        return str(exc)
    if isinstance(exc, UnicodeDecodeError):
        return "CSV 编码无法识别，请用 Excel「另存为」UTF-8 CSV 后再导入。"
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        if "locked" in text:
            return "数据库正被占用。请先关掉另一个 xuankan serve 窗口，或结束占用 data/xuankan.sqlite 的进程。"
        return f"数据库无法打开：{exc}"
    if isinstance(exc, httpx.ConnectError):
        return "无法连接 OpenAlex 或 Wikidata，请检查网络后重试。"
    if isinstance(exc, httpx.TimeoutException):
        return "OpenAlex 或 Wikidata 请求超时，请稍后重试，或把 --limit 调小。"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else "?"
        return f"OpenAlex / Wikidata 返回 HTTP {code}，请稍后重试。"
    if isinstance(exc, httpx.HTTPError):
        return "同步 OpenAlex 或 Wikidata 失败，请检查网络后重试。"
    return str(exc)
