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
    topics: list[Topic] = field(default_factory=list)
    official: OfficialMetrics | None = None

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
            "topics": [
                {
                    "topic_id": t.topic_id,
                    "topic_name": t.topic_name,
                    "field_name": t.field_name,
                    "share": t.share,
                }
                for t in self.topics
            ],
            "official": self.official.to_dict() if self.official else None,
        }
