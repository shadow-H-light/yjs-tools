from __future__ import annotations

from dataclasses import dataclass, field

from yjs_tools.journal.models import Journal, Topic


@dataclass
class SearchPage:
    journals: list[Journal]
    match_mode: str
    embedding_enabled: bool = False
    hint: str | None = None

    def to_dict(self, query: str) -> dict:
        return {
            "query": query,
            "count": len(self.journals),
            "match_mode": self.match_mode,
            "embedding_enabled": self.embedding_enabled,
            "hint": self.hint,
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
