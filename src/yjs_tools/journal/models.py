from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Topic:
    topic_id: str
    topic_name: str
    field_name: str | None = None
    share: float | None = None


@dataclass
class OfficialMetrics:
    year: int
    jcr_quartile: int | None = None
    impact_factor: float | None = None
    impact_factor_5: float | None = None
    cas_quartile: int | None = None
    warning: bool = False
    review_days: int | None = None
    filename: str | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "jcr_quartile": self.jcr_quartile,
            "impact_factor": self.impact_factor,
            "impact_factor_5": self.impact_factor_5,
            "cas_quartile": self.cas_quartile,
            "warning": self.warning,
            "review_days": self.review_days,
            "filename": self.filename,
            "source": self.source,
        }


@dataclass
class Journal:
    id: int
    openalex_id: str
    display_name: str
    issn_l: str | None
    issns: list[str]
    publisher: str | None
    homepage: str | None
    is_oa: bool
    works_count: int
    cited_by_count: int
    citedness_2yr: float | None
    country_code: str | None
    type: str | None
    alternate_titles: list[str] = field(default_factory=list)
    is_chinese: bool = False
    topics: list[Topic] = field(default_factory=list)
    official: OfficialMetrics | None = None
    matched_topics: list[Topic] = field(default_factory=list)
    match_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "openalex_id": self.openalex_id,
            "display_name": self.display_name,
            "issn_l": self.issn_l,
            "issns": self.issns,
            "publisher": self.publisher,
            "homepage": self.homepage,
            "is_oa": self.is_oa,
            "works_count": self.works_count,
            "cited_by_count": self.cited_by_count,
            "citedness_2yr": self.citedness_2yr,
            "country_code": self.country_code,
            "type": self.type,
            "alternate_titles": self.alternate_titles,
            "is_chinese": self.is_chinese,
            "match_score": self.match_score,
            "topics": [
                {
                    "topic_id": t.topic_id,
                    "topic_name": t.topic_name,
                    "field_name": t.field_name,
                    "share": t.share,
                }
                for t in self.topics
            ],
            "matched_topics": [
                {
                    "topic_id": t.topic_id,
                    "topic_name": t.topic_name,
                    "field_name": t.field_name,
                    "share": t.share,
                }
                for t in self.matched_topics
            ],
            "official": self.official.to_dict() if self.official else None,
        }
