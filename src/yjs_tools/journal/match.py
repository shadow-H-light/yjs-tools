from __future__ import annotations

import math
import sqlite3

import httpx

from yjs_tools.journal.ingest import USER_AGENT
from yjs_tools.journal.lexicon import (
    QueryExpansion,
    expand_query,
    looks_like_journal_title,
    should_resolve_remote,
)
from yjs_tools.journal.models import Topic
from yjs_tools.journal.result import ScoredHit

OPENALEX_TOPICS = "https://api.openalex.org/topics"

__all__ = [
    "QueryExpansion",
    "expand_query",
    "local_topic_hits",
    "looks_like_journal_title",
    "match_mode_for",
    "merge_hits",
    "quality_bonus",
    "remote_topic_ids",
    "should_resolve_remote",
    "topic_hits_by_ids",
]


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


def remote_topic_ids(
    queries: str | list[str],
    timeout: float = 8.0,
) -> list[str]:
    phrases = [queries] if isinstance(queries, str) else list(queries)
    ids: list[str] = []
    seen: set[str] = set()
    for phrase in phrases[:3]:
        text = (phrase or "").strip()
        if not text:
            continue
        try:
            response = httpx.get(
                OPENALEX_TOPICS,
                params={"search": text, "per_page": 8},
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        for item in response.json().get("results") or []:
            raw = item.get("id") or ""
            topic_id = raw.rsplit("/", 1)[-1]
            if topic_id and topic_id not in seen:
                seen.add(topic_id)
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
