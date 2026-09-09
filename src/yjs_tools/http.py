from __future__ import annotations

import os
import sys

import httpx


def ssl_verify() -> bool:
    """Campus/proxy SSL inspection often breaks certifi; default to OS-friendly TLS."""
    flag = os.environ.get("YJS_SSL_INSECURE", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return False
    if flag in {"0", "false", "no"}:
        return True
    # Windows Python does not use the system CA store; MITM proxies then fail.
    return sys.platform != "win32"


def create_client(
    *,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        headers=headers or {},
        verify=ssl_verify(),
    )
