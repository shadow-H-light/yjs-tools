from __future__ import annotations

from dataclasses import dataclass, field

from yjs_tools.journal.models import Journal, Topic


@dataclass
class SearchPage:
    journals: list[Journal]
    match_mode: str
    embedding_enabled: bool = False
    hint: str | None = None
    search_by: str = "auto"
    query_language: str | None = None
    expanded_terms: list[str] = field(default_factory=list)
    total: int = 0
    filled: int = 0

    def to_dict(self, query: str) -> dict:
        return {
            "query": query,
            "count": len(self.journals),
            "total": self.total if self.total else len(self.journals),
            "match_mode": self.match_mode,
            "search_by": self.search_by,
            "query_language": self.query_language,
            "expanded_terms": self.expanded_terms,
            "embedding_enabled": self.embedding_enabled,
            "hint": self.hint,
            "filled": self.filled,
            "results": [j.to_dict() for j in self.journals],
        }


@dataclass
class ScoredHit:
    journal_id: int
    name_score: float = 0.0
    topic_score: float = 0.0
    matched_topics: list[Topic] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.name_score + self.topic_score
