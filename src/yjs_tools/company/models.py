from __future__ import annotations

from dataclasses import dataclass, field


OWNERSHIP_LABELS = {
    "soe": "国企",
    "private": "私企",
    "foreign": "外企",
    "unknown": "暂无",
}

SIZE_LABELS = {
    "large": "大厂",
    "medium": "中厂",
    "small": "小厂",
}


@dataclass
class Job:
    title: str
    major: str | None = None
    city: str | None = None
    education: str | None = None
    year: int | None = None


@dataclass
class RecruitmentRound:
    year: int
    season: str
    start_date: str | None = None
    end_date: str | None = None
    headcount: int | None = None
    source: str | None = None


@dataclass
class Finance:
    year: int
    revenue: float | None = None
    net_income: float | None = None
    currency: str | None = None
    source: str | None = None


@dataclass
class Dispute:
    year: int | None
    case_type: str | None
    summary: str | None
    url: str | None = None


@dataclass
class UniversityLink:
    university: str
    relation: str | None = None
    works_count: int | None = None
    source: str | None = None


@dataclass
class Company:
    id: int
    wikidata_id: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    homepage: str | None = None
    ticker: str | None = None
    credit_code: str | None = None
    country_code: str | None = None
    hq_city: str | None = None
    ownership: str = "unknown"
    is_central_soe: bool = False
    bianzhi: str | None = None
    size_band: str | None = None
    foreign_origin: str | None = None
    employees: int | None = None
    founded_year: int | None = None
    salary_note: str | None = None
    industries: list[str] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
    rounds: list[RecruitmentRound] = field(default_factory=list)
    finance: list[Finance] = field(default_factory=list)
    disputes: list[Dispute] = field(default_factory=list)
    universities: list[UniversityLink] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    match_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "wikidata_id": self.wikidata_id,
            "display_name": self.display_name,
            "aliases": self.aliases,
            "homepage": self.homepage,
            "ticker": self.ticker,
            "credit_code": self.credit_code,
            "country_code": self.country_code,
            "hq_city": self.hq_city,
            "ownership": self.ownership,
            "ownership_label": OWNERSHIP_LABELS.get(self.ownership, "暂无"),
            "is_central_soe": self.is_central_soe,
            "bianzhi": self.bianzhi,
            "size_band": self.size_band,
            "size_label": SIZE_LABELS.get(self.size_band or "", None),
            "foreign_origin": self.foreign_origin,
            "employees": self.employees,
            "founded_year": self.founded_year,
            "salary_note": self.salary_note,
            "industries": self.industries,
            "jobs": [j.__dict__ for j in self.jobs],
            "rounds": [r.__dict__ for r in self.rounds],
            "finance": [f.__dict__ for f in self.finance],
            "disputes": [d.__dict__ for d in self.disputes],
            "universities": [u.__dict__ for u in self.universities],
            "matched": self.matched,
            "match_score": self.match_score,
        }
