from __future__ import annotations

import re
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
    "journal",
    "international",
    "research",
    "the",
    "的",
    "与",
    "及",
    "和",
    "中",
}

TITLE_MARKERS = (
    "journal",
    "transactions",
    "letters",
    "proceedings",
    "bulletin",
    "review of",
    "学报",
    "杂志",
    "通报",
    "汇刊",
    "季刊",
    "月刊",
    "weekly",
)

# 中文方向 → 英文主题词。检索时双向展开。
ZH_TO_EN: dict[str, tuple[str, ...]] = {
    "传感器": ("sensors", "sensor", "sensing"),
    "传感": ("sensors", "sensor", "sensing"),
    "计算机视觉": ("computer vision",),
    "机器学习": ("machine learning",),
    "深度学习": ("deep learning",),
    "自然语言处理": ("natural language processing",),
    "自然语言": ("natural language processing",),
    "太阳能电池": ("solar cell",),
    "钙钛矿": ("perovskite",),
    "固态电池": ("solid state battery",),
    "计算社会科学": ("computational social science",),
    "生物信息": ("bioinformatics",),
    "材料科学": ("materials science",),
    "无线通信": ("wireless communication", "wireless communications"),
    "光学": ("optics", "optical"),
    "激光": ("laser", "lasers"),
    "人工智能": ("artificial intelligence", "machine learning"),
    "机器人": ("robotics", "robot"),
    "控制": ("control systems", "control"),
    "能源": ("energy",),
    "电池": ("battery", "batteries"),
    "纳米": ("nano", "nanomaterials", "nanotechnology"),
    "医学": ("medicine", "medical"),
    "药学": ("pharmacy", "pharmacology"),
    "化学": ("chemistry", "chemical"),
    "物理": ("physics",),
    "力学": ("mechanics",),
    "环境": ("environment", "environmental"),
    "地质": ("geology",),
    "农学": ("agriculture", "agronomy"),
    "经济": ("economics",),
    "管理": ("management",),
    "教育": ("education",),
    "心理学": ("psychology",),
}

VENUE_QUERIES: dict[str, tuple[str, ...]] = {
    "sensor": (
        "Sensors",
        "IEEE Sensors",
        "Sensor Review",
        "Measurement Science and Technology",
        "Sensors and Actuators",
        "ACS Sensors",
    ),
}

EN_ALIASES: dict[str, tuple[str, ...]] = {
    "sensor": ("sensors", "sensing"),
    "sensors": ("sensor", "sensing"),
    "sensing": ("sensor", "sensors"),
    "transducer": ("sensor", "sensors"),
    "mst": ("measurement",),
    "optic": ("optics", "optical"),
    "optics": ("optical", "optic"),
    "optical": ("optics",),
}


@dataclass
class QueryExpansion:
    raw: str
    language: str
    tokens: list[str] = field(default_factory=list)
    remote_queries: list[str] = field(default_factory=list)
    english_terms: list[str] = field(default_factory=list)
    chinese_terms: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def has_cjk(self) -> bool:
        return self.language in {"zh", "mixed"}


def detect_language(query: str) -> str:
    has_cjk = bool(CJK_RE.search(query))
    has_latin = bool(re.search(r"[a-zA-Z]", query))
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "zh"
    if has_latin:
        return "en"
    return "other"


def looks_like_journal_title(query: str) -> bool:
    lowered = query.strip().lower()
    return any(marker in lowered for marker in TITLE_MARKERS)


def expand_query(query: str) -> QueryExpansion:
    raw = query.strip()
    language = detect_language(raw)
    phrases: list[str] = [raw]
    chinese_terms: list[str] = []
    english_terms: list[str] = []

    compact = re.sub(r"\s+", "", raw)
    for zh, english in sorted(ZH_TO_EN.items(), key=lambda item: len(item[0]), reverse=True):
        if zh in raw or zh == compact:
            chinese_terms.append(zh)
            phrases.extend(english)
            english_terms.extend(english)
            break

    if language == "zh" and not english_terms:
        chinese_terms.append(compact or raw)

    tokens: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        for token in TOKEN_RE.findall(phrase.lower()):
            if token in STOPWORDS or len(token) < 2:
                continue
            _add_token(token, tokens, seen)
            for alias in EN_ALIASES.get(token, ()):
                _add_token(alias, tokens, seen)
            for variant in _english_variants(token):
                _add_token(variant, tokens, seen)

    remote: list[str] = []
    for item in [*english_terms, *tokens[:4], raw]:
        text = item.strip()
        if text and text.lower() not in {x.lower() for x in remote}:
            remote.append(text)

    note = None
    if language == "zh" and english_terms:
        shown = " / ".join(dict.fromkeys(english_terms))
        note = f"已将「{raw}」识别为主题，同时检索 {shown}。"
    elif language == "zh":
        note = f"已将「{raw}」识别为中文主题词，按主题匹配期刊。"

    return QueryExpansion(
        raw=raw,
        language=language,
        tokens=tokens or [raw.lower()],
        remote_queries=remote[:5],
        english_terms=list(dict.fromkeys(english_terms)),
        chinese_terms=list(dict.fromkeys(chinese_terms)),
        note=note,
    )


def should_resolve_remote(expansion: QueryExpansion, by: str) -> bool:
    if by == "topic":
        return True
    if by != "auto":
        return False
    if looks_like_journal_title(expansion.raw):
        return False
    if expansion.has_cjk:
        return True
    ascii_tokens = [t for t in expansion.tokens if t.isascii() and t not in STOPWORDS]
    if any(t in EN_ALIASES for t in ascii_tokens):
        return True
    raw_tokens = [
        t
        for t in TOKEN_RE.findall(expansion.raw.lower())
        if t not in STOPWORDS and len(t) >= 2
    ]
    return len(raw_tokens) >= 2


def backfill_queries(expansion: QueryExpansion) -> list[str]:
    blob = " ".join(
        [expansion.raw, *expansion.tokens, *expansion.english_terms]
    ).lower()
    queries: list[str] = []
    if any(key in blob for key in ("sensor", "sensing", "传感")):
        queries.extend(VENUE_QUERIES["sensor"])
    for term in expansion.english_terms:
        if term and term.lower() not in {q.lower() for q in queries}:
            queries.append(term)
    if expansion.raw and expansion.raw.lower() not in {q.lower() for q in queries}:
        if not expansion.has_cjk:
            queries.append(expansion.raw)
    return queries[:6]


def _add_token(token: str, tokens: list[str], seen: set[str]) -> None:
    if token in STOPWORDS or len(token) < 2 or token in seen:
        return
    seen.add(token)
    tokens.append(token)


def _english_variants(token: str) -> list[str]:
    if not token.isascii() or not token.isalpha() or len(token) < 4:
        return []
    variants = []
    if token.endswith("ies") and len(token) > 4:
        variants.append(token[:-3] + "y")
    elif token.endswith("es") and len(token) > 4:
        variants.append(token[:-2])
    elif token.endswith("s") and not token.endswith("ss"):
        variants.append(token[:-1])
    else:
        variants.append(token + "s")
    return variants
