from __future__ import annotations

import sqlite3

import httpx
from typer.testing import CliRunner

from yjs_tools.cli import app
from yjs_tools.errors import explain_error
from yjs_tools.journal.importer import MetricsImportError, decode_csv_bytes


def test_explain_network_and_lock():
    assert "OpenAlex" in explain_error(httpx.ConnectError("fail"))
    assert "超时" in explain_error(httpx.TimeoutException("timeout"))
    assert "占用" in explain_error(sqlite3.OperationalError("database is locked"))
    assert "ISSN" in explain_error(MetricsImportError("缺少 ISSN 列（issn / 刊号）"))
    assert "UTF-8" in explain_error(UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"))


def test_decode_utf8_and_gbk():
    assert "0028-0836" in decode_csv_bytes("issn\n0028-0836\n".encode("utf-8"))
    gbk = "issn,刊号\n0028-0836\n".encode("gbk")
    assert "0028-0836" in decode_csv_bytes(gbk)


def test_cli_version():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
