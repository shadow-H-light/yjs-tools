from __future__ import annotations

import math
import re
import sqlite3

import httpx

from yjs_tools.journal.ingest import USER_AGENT
from yjs_tools.journal.models import Topic
from yjs_tools.journal.result import ScoredHit

OPENALEX_TOPICS = "https://api.openalex.org/topics"
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
    "的",
    "与",
    "及",
    "和",
    "中",
}
# 少量中英方向对照，方便在没有向量模型时用主题召回。
SYNONYMS = {
    "计算机视觉": "computer vision",
    "机器学习": "machine learning",
    "深度学习": "deep learning",
    "自然语言": "natural language processing",
    "自然语言处理": "natural language processing",
    "太阳能电池": "solar cell",
    "钙钛矿": "perovskite",
    "固态电池": "solid state battery",
    "计算社会科学": "computational social science",
    "生物信息": "bioinformatics",
    "材料科学": "materials science",
}

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


def looks_like_direction(query: str) -> bool:
    if any("\u4e00" <= ch <= "\u9fff" for ch in query):
        return True
    tokens = [
        t
        for t in TOKEN_RE.findall(query.lower())
        if t not in STOPWORDS and len(t) >= 2
    ]
    return len(tokens) >= 2


def expand_query(query: str) -> list[str]:
    raw = query.strip()
    phrases = [raw]
    key = re.sub(r"\s+", "", raw.lower())
    for zh, en in SYNONYMS.items():
        if zh in raw or zh.replace(" ", "") == key:
            phrases.append(en)
    tokens: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        for token in TOKEN_RE.findall(phrase.lower()):
            if token in STOPWORDS or len(token) < 2:
                continue
            if token not in seen:
                seen.add(token)
                tokens.append(token)
    return tokens or [raw.lower()]


def local_topic_hits(conn: sqlite3.Connection, tokens: list[str]) -> dict[int, ScoredHit]:
    hits: dict[int, ScoredHit] = {}
    if not tokens:
        return hits
    for token in tokens:
        like = f"%{token}%"
        rows = conn.execute(
            """
            SELECT journal_id, topic_id, topic_name, field_name, share
            FROM journal_topics
            WHERE topic_name LIKE ? COLLATE NOCASE
               OR IFNULL(field_name, '') LIKE ? COLLATE NOCASE
            """,
            (like, like),
        ).fetchall()
        for row in rows:
            hit = hits.setdefault(row["journal_id"], ScoredHit(journal_id=row["journal_id"]))
            topic = Topic(
                topic_id=row["topic_id"],
                topic_name=row["topic_name"],
                field_name=row["field_name"],
                share=row["share"],
            )
            if all(t.topic_id != topic.topic_id for t in hit.matched_topics):
                hit.matched_topics.append(topic)
                share = float(row["share"] or 0)
                hit.topic_score += 4.0 + math.log10(share + 1)
    return hits


def remote_topic_ids(query: str, timeout: float = 8.0) -> list[str]:
    try:
        response = httpx.get(
            OPENALEX_TOPICS,
            params={"search": query, "per_page": 8},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    ids: list[str] = []
    for item in response.json().get("results") or []:
        raw = item.get("id") or ""
        topic_id = raw.rsplit("/", 1)[-1]
        if topic_id:
            ids.append(topic_id)
    return ids


def topic_hits_by_ids(conn: sqlite3.Connection, topic_ids: list[str]) -> dict[int, ScoredHit]:
    hits: dict[int, ScoredHit] = {}
    if not topic_ids:
        return hits
    placeholders = ",".join("?" * len(topic_ids))
    rows = conn.execute(
        f"""
        SELECT journal_id, topic_id, topic_name, field_name, share
        FROM journal_topics
        WHERE topic_id IN ({placeholders})
        """,
        topic_ids,
    ).fetchall()
    for row in rows:
        hit = hits.setdefault(row["journal_id"], ScoredHit(journal_id=row["journal_id"]))
        topic = Topic(
            topic_id=row["topic_id"],
            topic_name=row["topic_name"],
            field_name=row["field_name"],
            share=row["share"],
        )
        if all(t.topic_id != topic.topic_id for t in hit.matched_topics):
            hit.matched_topics.append(topic)
            share = float(row["share"] or 0)
            hit.topic_score += 5.0 + math.log10(share + 1)
    return hits


def merge_hits(*groups: dict[int, ScoredHit]) -> dict[int, ScoredHit]:
    merged: dict[int, ScoredHit] = {}
    for group in groups:
        for journal_id, hit in group.items():
            current = merged.setdefault(journal_id, ScoredHit(journal_id=journal_id))
            current.name_score += hit.name_score
            current.topic_score += hit.topic_score
            for topic in hit.matched_topics:
                if all(t.topic_id != topic.topic_id for t in current.matched_topics):
                    current.matched_topics.append(topic)
    return merged


def quality_bonus(cited_by_count: int) -> float:
    return math.log10(cited_by_count + 1)


def match_mode_for(hits: dict[int, ScoredHit]) -> str:
    if not hits:
        return "none"
    has_name = any(h.name_score > 0 for h in hits.values())
    has_topic = any(h.topic_score > 0 for h in hits.values())
    if has_name and has_topic:
        return "mixed"
    if has_topic:
        return "topic"
    return "name"
