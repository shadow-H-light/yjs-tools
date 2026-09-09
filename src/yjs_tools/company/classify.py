from __future__ import annotations

# Wikidata Q-ids treated as state ownership.
SOE_INSTANCE_IDS = {
    "Q270791",  # state-owned enterprise
    "Q11691",
    "Q15090352",
    "Q4314967",
}
CHINA_IDS = {"Q148", "Q22502"}  # PRC, mainland
GREATER_CHINA_IDS = CHINA_IDS | {"Q8646", "Q14773", "Q865"}  # HK MO TW
SASAC_IDS = {"Q1142005", "Q986729"}

# Well-known SASAC central SOEs (Wikidata). Only IDs confirmed by EntityData.
CENTRAL_SOE_IDS = {
    "Q557083",  # State Grid
    "Q1115363",  # COMAC
}

SIZE_LARGE = 10000
SIZE_MEDIUM = 1000


def size_band(employees: int | None) -> str | None:
    if employees is None:
        return None
    if employees >= SIZE_LARGE:
        return "large"
    if employees >= SIZE_MEDIUM:
        return "medium"
    return "small"


def classify_ownership(
    *,
    country_qid: str | None,
    instance_ids: set[str],
    owner_ids: set[str],
    wikidata_id: str,
    is_central_imported: bool = False,
) -> tuple[str, bool, str | None]:
    """Return (ownership, is_central_soe, foreign_origin_qid)."""
    is_central = wikidata_id in CENTRAL_SOE_IDS or is_central_imported
    soe = bool(instance_ids & SOE_INSTANCE_IDS) or bool(owner_ids & SASAC_IDS) or is_central
    if soe or (country_qid in CHINA_IDS and is_central):
        return "soe", is_central or bool(owner_ids & SASAC_IDS), None
    if country_qid and country_qid not in GREATER_CHINA_IDS:
        return "foreign", False, country_qid
    if country_qid in GREATER_CHINA_IDS - CHINA_IDS:
        return "foreign", False, country_qid
    if country_qid in CHINA_IDS:
        return "private", False, None
    return "unknown", False, country_qid
