from __future__ import annotations

from yjs_tools.journal.lexicon import TOKEN_RE, ZH_TO_EN, expand_query

MAJOR_TO_JOBS: dict[str, tuple[str, ...]] = {
    "光学工程": ("光学", "optical", "工艺", "process", "激光", "光电"),
    "光学": ("光学", "optical", "光电", "laser"),
    "集成电路": ("集成电路", "ic", "芯片", "chip", "半导体", "semiconductor", "工艺"),
    "微电子": ("微电子", "集成电路", "芯片", "工艺", "device"),
    "电子科学与技术": ("电子", "embedded", "硬件", "电路", "射频"),
    "电子信息": ("电子", "嵌入式", "通信", "软件"),
    "计算机": ("软件", "算法", "后端", "开发", "computer"),
    "软件工程": ("软件", "开发", "后端", "测试"),
    "自动化": ("自动化", "控制", "嵌入式", "plc"),
    "机械工程": ("机械", "结构", "工艺", "设备"),
    "材料": ("材料", "工艺", "失效", "materials"),
    "化学": ("化学", "工艺", "分析", "研发"),
    "生物": ("生物", "医药", "临床", "biotech"),
    "仪器": ("仪器", "传感器", "测量", "sensor"),
    "传感器": ("传感器", "sensor", "sensing", "器件"),
}


def expand_major(query: str) -> list[str]:
    raw = (query or "").strip()
    terms = [raw] if raw else []
    expansion = expand_query(raw)
    terms.extend(expansion.english_terms)
    terms.extend(expansion.tokens)
    for key, jobs in MAJOR_TO_JOBS.items():
        if key in raw or raw in key:
            terms.extend(jobs)
    for zh, en in ZH_TO_EN.items():
        if zh in raw:
            terms.extend(en)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        token = term.strip().lower()
        if token and token not in seen:
            seen.add(token)
            out.append(term.strip())
    return out[:16]


def tokens(query: str) -> list[str]:
    return [m.group(0) for m in TOKEN_RE.finditer(query or "")]
