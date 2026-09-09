from __future__ import annotations

import re

ISSN_RE = re.compile(r"^\d{4}-?\d{3}[\dXx]$")


def normalize_issn(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"[\s\-]", "", str(value)).upper()
    if len(compact) != 8:
        return None
    if not compact[:7].isdigit() or compact[7] not in "0123456789X":
        return None
    return f"{compact[:4]}-{compact[4:]}"


def looks_like_issn(value: str) -> bool:
    return normalize_issn(value) is not None
