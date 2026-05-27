"""Agent session log parser for usage-aware harness recommendations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Dict


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _new_bucket() -> Dict[str, Any]:
    return {"count": 0, "last_used": None, "sessions": set()}


def _bump(bucket: Dict[str, Any], session_id: str, timestamp: str) -> None:
    bucket["count"] += 1
    bucket["sessions"].add(session_id)
    if not bucket["last_used"] or timestamp > bucket["last_used"]:
        bucket["last_used"] = timestamp


def _finalize_buckets(buckets: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        key: {
            "count": value["count"],
            "last_used": value["last_used"],
            "sessions": len(value["sessions"]),
        }
        for key, value in buckets.items()
    }


def parse_claude_sessions(days: int = 30) -> Dict[str, Any]:
    """Parse Claude Code JSONL sessions for Skill and Agent invocations."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    log_dir = Path.home() / ".claude" / "projects"

    skills: Dict[str, Dict[str, Any]] = defaultdict(_new_bucket)
    agents: Dict[str, Dict[str, Any]] = defaultdict(_new_bucket)
    total_sessions: set[str] = set()

    if not log_dir.exists():
        return {
            "skills": {},
            "agents": {},
            "total_sessions": 0,
            "cutoff_date": cutoff.isoformat(),
        }

    for jsonl in log_dir.rglob("*.jsonl"):
        fallback_session_id = jsonl.stem
        try:
            with jsonl.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    timestamp = data.get("timestamp")
                    parsed_ts = _parse_iso_timestamp(timestamp)
                    if not parsed_ts or parsed_ts < cutoff:
                        continue

                    session_id = data.get("sessionId") or data.get("session_id") or fallback_session_id
                    total_sessions.add(session_id)

                    if data.get("type") != "assistant":
                        continue

                    message = data.get("message", {})
                    content = message.get("content", []) if isinstance(message, dict) else []
                    if not isinstance(content, list):
                        continue

                    for entry in content:
                        if not isinstance(entry, dict) or entry.get("type") != "tool_use":
                            continue
                        tool_name = entry.get("name")
                        tool_input = entry.get("input", {}) or {}
                        if not isinstance(tool_input, dict):
                            continue

                        if tool_name == "Skill":
                            skill_name = tool_input.get("skill")
                            if skill_name:
                                _bump(skills[str(skill_name)], str(session_id), str(timestamp))
                        elif tool_name == "Agent":
                            agent_name = tool_input.get("subagent_type")
                            if agent_name:
                                _bump(agents[str(agent_name)], str(session_id), str(timestamp))
        except (OSError, PermissionError):
            continue

    return {
        "skills": _finalize_buckets(skills),
        "agents": _finalize_buckets(agents),
        "total_sessions": len(total_sessions),
        "cutoff_date": cutoff.isoformat(),
    }


def parse_codex_history(days: int = 30) -> Dict[str, Any]:
    """Parse Codex prompt history. Tool/skill invocations are not available."""
    cutoff_epoch = (datetime.now() - timedelta(days=days)).timestamp()
    path = Path.home() / ".codex" / "history.jsonl"
    if not path.exists():
        return {"prompt_count": 0, "session_count": 0, "last_used": None}

    sessions = set()
    prompt_count = 0
    last_ts = None

    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = data.get("ts")
                if not isinstance(ts, (int, float)) or ts < cutoff_epoch:
                    continue
                session_id = data.get("session_id")
                if session_id:
                    sessions.add(session_id)
                prompt_count += 1
                if last_ts is None or ts > last_ts:
                    last_ts = ts
    except (OSError, PermissionError):
        pass

    return {
        "prompt_count": prompt_count,
        "session_count": len(sessions),
        "last_used": datetime.fromtimestamp(last_ts).isoformat() if last_ts else None,
    }


def get_usage_summary(workspace: str, days: int = 30) -> Dict[str, Any]:
    """Return usage summary for a workspace path."""
    ws = Path(workspace).expanduser().resolve()
    home = Path.home().resolve()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if ws == (home / ".claude").resolve():
        return {"agent": "claude", "unsupported": False, **parse_claude_sessions(days)}
    if ws == (home / ".codex").resolve():
        return {
            "agent": "codex",
            "unsupported": False,
            "skills": {},
            "agents": {},
            "total_sessions": 0,
            "cutoff_date": cutoff_date,
            **parse_codex_history(days),
        }
    return {
        "agent": ws.name,
        "unsupported": True,
        "skills": {},
        "agents": {},
        "total_sessions": 0,
        "cutoff_date": cutoff_date,
    }
