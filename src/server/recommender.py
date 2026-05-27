"""Usage-aware recommendations for harness cleanup actions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


TEXT_SUFFIXES = {".md", ".mdc", ".txt", ".yaml", ".yml", ".json", ".toml", ".py", ".sh"}
SKILL_TYPES = {"Skill", "Skill Bundle"}
AGENT_TYPES = {"Subagent"}


def _clean_key(value: Any) -> str:
    return str(value or "").strip()


def _key_candidates(item: Dict[str, Any], *, agent: bool = False) -> List[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    source_path = item.get("source_path")
    candidates = [
        metadata.get("skill_id"),
        metadata.get("agent_id"),
        metadata.get("subagent_type"),
        item.get("name"),
    ]

    if source_path:
        path = Path(str(source_path))
        if path.name in {"SKILL.md", "AGENTS.md", "agent.md", "CLAUDE.md"}:
            candidates.append(path.parent.name)
        candidates.extend([path.stem, path.name])
        if agent:
            candidates.append(path.stem)

    seen = set()
    normalized = []
    for candidate in candidates:
        key = _clean_key(candidate)
        if key and key not in seen:
            normalized.append(key)
            seen.add(key)
    return normalized


def _lookup_usage(
    usage_map: Dict[str, Dict[str, Any]],
    candidates: Iterable[str],
) -> Tuple[str | None, Dict[str, Any]]:
    candidate_list = [c for c in candidates if c]
    candidate_lower = {c.lower() for c in candidate_list}
    for key in candidate_list:
        if key in usage_map:
            return key, usage_map[key]

    lower_index = {str(key).lower(): key for key in usage_map}
    for key in candidate_lower:
        if key in lower_index:
            matched = lower_index[key]
            return matched, usage_map[matched]

    for usage_key, stats in usage_map.items():
        usage_tail = str(usage_key).split(":")[-1].lower()
        if usage_tail in candidate_lower:
            return usage_key, stats

    return None, {"count": 0, "last_used": None, "sessions": 0}


def _file_token_estimate(item: Dict[str, Any]) -> int:
    source_path = item.get("source_path")
    if not source_path:
        return 0
    path = Path(str(source_path)).expanduser()
    if not path.exists() or not path.is_file():
        return 0
    try:
        if path.suffix in TEXT_SUFFIXES:
            return max(0, len(path.read_text(encoding="utf-8", errors="ignore")) // 4)
        return max(0, path.stat().st_size // 4)
    except Exception:
        return 0


def _effective_tokens(item: Dict[str, Any]) -> int:
    scanned = item.get("token_estimate") or 0
    try:
        scanned = int(scanned)
    except (TypeError, ValueError):
        scanned = 0
    return max(scanned, _file_token_estimate(item))


def _days_old(item: Dict[str, Any], now_ts: float) -> int | None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    modified_at = metadata.get("modified_at")
    if not modified_at:
        return None
    try:
        return int((now_ts - float(modified_at)) / 86400)
    except (TypeError, ValueError):
        return None


def _high_value_threshold(usage: Dict[str, Any]) -> int:
    counts = [
        int(value.get("count", 0) or 0)
        for value in {**usage.get("skills", {}), **usage.get("agents", {})}.values()
    ]
    if not counts:
        return 0
    counts.sort(reverse=True)
    index = max(0, len(counts) // 10 - 1)
    return counts[index]


def _usage_window_days(usage: Dict[str, Any]) -> int:
    cutoff_date = usage.get("cutoff_date")
    if not cutoff_date:
        return 30
    try:
        cutoff = datetime.fromisoformat(str(cutoff_date).replace("Z", "+00:00"))
        now = datetime.now(cutoff.tzinfo or timezone.utc)
        return max(1, int((now - cutoff).total_seconds() / 86400))
    except Exception:
        return 30


def build_recommendations(
    items: List[Dict[str, Any]],
    usage: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Combine scanner items and usage telemetry into cleanup recommendations."""
    if usage.get("unsupported"):
        return []

    skill_usage = usage.get("skills", {})
    agent_usage = usage.get("agents", {})
    high_threshold = _high_value_threshold(usage)
    stale_days = max(30, min(90, _usage_window_days(usage)))
    now_ts = datetime.now().timestamp()
    recs: List[Dict[str, Any]] = []

    for item in items:
        item_type = item.get("type", "")
        source_path = item.get("source_path") or ""

        if item_type in SKILL_TYPES:
            usage_key, stats = _lookup_usage(skill_usage, _key_candidates(item))
        elif item_type in AGENT_TYPES or "agent" in str(source_path).lower():
            usage_key, stats = _lookup_usage(agent_usage, _key_candidates(item, agent=True))
        else:
            continue

        count = int(stats.get("count", 0) or 0)
        tokens = _effective_tokens(item)
        days_old = _days_old(item, now_ts)
        last_used = stats.get("last_used")

        category = None
        reason = ""
        confidence = 0.0

        if high_threshold > 0 and count >= high_threshold:
            category = "HIGH_VALUE"
            reason = f"지난 30일간 {count}회 호출 (상위 10%) - 보존 권장"
            confidence = 0.95
        elif count == 0 and days_old is not None and days_old >= stale_days:
            category = "STALE_UNUSED"
            reason = f"{days_old}일간 수정 없음 + 최근 {stale_days}일간 0회 호출"
            confidence = 0.92
        elif count == 0 and tokens >= 1000:
            category = "ARCHIVE"
            reason = f"지난 30일간 0회 호출됨 ({tokens:,} tokens 정리 가능)"
            confidence = 0.80
        elif tokens >= 5000 and count <= 2:
            category = "HEAVY_UNUSED"
            reason = f"대용량 ({tokens:,} tokens)인데 30일간 {count}회만 호출"
            confidence = 0.65

        if not category:
            continue

        recs.append(
            {
                "item": {**item, "token_estimate": tokens},
                "category": category,
                "confidence": confidence,
                "reason": reason,
                "usage_count": count,
                "last_used": last_used,
                "potential_savings": 0 if category == "HIGH_VALUE" else tokens,
                "usage_key": usage_key,
            }
        )

    recs.sort(key=lambda rec: (-rec["confidence"], -rec["potential_savings"]))
    return recs
