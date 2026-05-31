from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException

from services.config import HERMES_HOME, PROJECT_ROOT
from scanner.antigravity_scanner import AntigravityScanner
from scanner.claude_scanner import ClaudeScanner
from scanner.codex_scanner import CodexScanner
from scanner.cursor_scanner import CursorScanner
from scanner.gemini_cli_scanner import GeminiCliScanner
from scanner.hermes_scanner import HermesScanner
from scanner.openclaw_scanner import OpenClawScanner
from scanner.studio_scanner import StudioScanner

router = APIRouter()

LOG_FILE_SUFFIXES = {".log", ".out", ".err", ".jsonl", ".ndjson"}
LOG_DIR_NAMES = {"logs", "log", "sessions", "runs", "traces"}
LOG_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv"}

SECTION_TYPE_MAP: Dict[str, List[str]] = {
    "skills":   ["Skill"],
    "bundles":  ["Skill Bundle"],
    "memory":   ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
    "mcp":      ["MCP Server"],
    "context":  ["Root Context"],
    "hooks":    ["Hook"],
    "config":   ["Config", "Memory Config", "Root Context", "MCP Server"],
    "cron":     ["Cron Job"],
    "plugins":  ["Plugin"],
    "logs":     ["Log File"],
    "sessions":    ["Session Summary"],
    "statedb":     ["State DB"],
    "checkpoints": ["Checkpoint"],
    "agent-runners": ["Agent Runner"],
}


def _discover_log_items(workspace: Path, limit: int = 80) -> List[Dict[str, Any]]:
    candidates: Dict[Path, Dict[str, Any]] = {}

    def add_file(path: Path, category: str) -> None:
        try:
            resolved = path.resolve(strict=False)
            if not resolved.is_file():
                return
            if resolved.suffix.lower() not in LOG_FILE_SUFFIXES:
                return
            if any(part in LOG_EXCLUDED_DIRS for part in resolved.parts):
                return
            stat = resolved.stat()
            candidates[resolved] = {
                "type": "Log File",
                "name": resolved.name,
                "source_path": str(resolved),
                "state": "ACTIVE",
                "summary": f"{category} log, {stat.st_size:,} bytes",
                "metadata": {
                    "category": category,
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "relative_path": str(resolved.relative_to(workspace)) if resolved.is_relative_to(workspace) else str(resolved),
                },
            }
        except Exception:
            return

    for child in workspace.iterdir() if workspace.exists() and workspace.is_dir() else []:
        if child.is_file():
            add_file(child, "Workspace root")
        elif child.is_dir() and child.name in LOG_DIR_NAMES:
            for path in child.rglob("*"):
                add_file(path, child.name)

    for relative in ("logs", ".logs", "sessions", "state", ".omx/logs"):
        root = workspace / relative
        if root.exists() and root.is_dir():
            for path in root.rglob("*"):
                add_file(path, relative)

    return sorted(
        candidates.values(),
        key=lambda item: item.get("metadata", {}).get("modified_at", 0),
        reverse=True,
    )[:limit]


def _enrich_file_metadata(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for item in items:
        source_path = item.get("source_path")
        if not source_path:
            continue
        try:
            path = Path(str(source_path)).expanduser().resolve(strict=False)
            if not path.exists() or not path.is_file():
                continue
            stat = path.stat()
            metadata = item.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.setdefault("size_bytes", stat.st_size)
                metadata.setdefault("modified_at", stat.st_mtime)
        except Exception:
            continue
    return items


def _scanner_for_workspace(workspace: Optional[str]):
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME.resolve()
    home = Path.home().resolve()
    known = {
        (home / ".hermes").resolve(): HermesScanner,
        (home / ".claude").resolve(): ClaudeScanner,
        (home / ".cursor").resolve(): CursorScanner,
        (home / ".codex").resolve(): CodexScanner,
        (home / ".openclaw").resolve(): OpenClawScanner,
        (home / ".gemini").resolve(): GeminiCliScanner,
        (home / ".gemini" / "antigravity").resolve(): AntigravityScanner,
        PROJECT_ROOT.resolve(): StudioScanner,
    }
    scanner_cls = known.get(ws_path)
    if scanner_cls is None:
        if ws_path.name == ".claude":
            scanner_cls = ClaudeScanner
        elif ws_path.name == ".cursor":
            scanner_cls = CursorScanner
        elif ws_path.name == ".codex":
            scanner_cls = CodexScanner
        elif ws_path.name == ".openclaw":
            scanner_cls = OpenClawScanner
        elif ws_path.name == ".gemini":
            scanner_cls = GeminiCliScanner
        elif ws_path.name == "antigravity" and ws_path.parent.name == ".gemini":
            scanner_cls = AntigravityScanner
        elif ws_path == PROJECT_ROOT.resolve():
            scanner_cls = StudioScanner
        else:
            scanner_cls = HermesScanner
    return scanner_cls(str(ws_path)), ws_path, scanner_cls.__name__


def _scan_items_for_workspace(workspace: Optional[str] = None):
    scanner, ws_path, scanner_name = _scanner_for_workspace(workspace)
    items = scanner.scan_all()
    items.extend(_discover_log_items(ws_path))
    _enrich_file_metadata(items)
    return items, ws_path, scanner_name


def build_response(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = _enrich_file_metadata(items)
    summary: Dict[str, int] = {}
    for item in items:
        t = item.get("type", "Unknown")
        if t == "Skill":
            if item.get("state") != "ARCHIVED":
                summary["skills"] = summary.get("skills", 0) + 1
            summary["skills_archived"] = summary.get("skills_archived", 0) + (1 if item.get("state") == "ARCHIVED" else 0)
        elif t == "Skill Bundle":
            summary["bundles"] = summary.get("bundles", 0) + 1
        elif t.startswith("Memory"):
            summary["memory"] = summary.get("memory", 0) + 1
        elif t == "MCP Server":
            summary["mcp"] = summary.get("mcp", 0) + 1
        elif t == "Root Context":
            summary["context"] = summary.get("context", 0) + 1
        elif t == "Hook":
            summary["hooks"] = summary.get("hooks", 0) + 1
        elif t == "Cron Job":
            summary["cron"] = summary.get("cron", 0) + 1
        elif t == "Plugin":
            summary["plugins"] = summary.get("plugins", 0) + 1
        elif t == "Log File":
            summary["logs"] = summary.get("logs", 0) + 1
        elif t == "Session Summary":
            summary["sessions"] = summary.get("sessions", 0) + 1
        elif t == "State DB":
            summary["statedb"] = summary.get("statedb", 0) + 1
        elif t == "Checkpoint":
            summary["checkpoints"] = summary.get("checkpoints", 0) + 1
        elif t == "Agent Runner":
            summary["agent-runners"] = summary.get("agent-runners", 0) + 1
        elif t == "Config":
            summary["config"] = summary.get("config", 0) + 1
        else:
            summary["config"] = summary.get("config", 0) + 1
    summary["web"] = 0

    return {"summary": summary, "items": items, "total": len(items)}


@router.get("/api/workspaces")
def get_workspaces():
    return [
        {"id": "hermes", "name": "Hermes", "path": str(Path.home() / ".hermes")},
        {"id": "claude", "name": "Claude Code", "path": str(Path.home() / ".claude")},
        {"id": "cursor", "name": "Cursor", "path": str(Path.home() / ".cursor")},
        {"id": "codex", "name": "Codex", "path": str(Path.home() / ".codex")},
        {"id": "openclaw", "name": "OpenClaw", "path": str(Path.home() / ".openclaw")},
        {"id": "gemini", "name": "Gemini CLI", "path": str(Path.home() / ".gemini")},
        {"id": "antigravity", "name": "Antigravity", "path": str(Path.home() / ".gemini" / "antigravity")},
        {"id": "studio", "name": "Harness Studio", "path": str(PROJECT_ROOT)},
    ]


@router.get("/api/scan")
def scan_all(workspace: str = None):
    items, ws_path, scanner_name = _scan_items_for_workspace(workspace)
    response = build_response(items)
    response["workspace"] = str(ws_path)
    response["scanner"] = scanner_name
    return response


@router.get("/api/scan/{section}")
def scan_section(section: str, workspace: str = None):
    section = section.lower()
    if section not in SECTION_TYPE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown section '{section}'. Valid sections: {list(SECTION_TYPE_MAP.keys())}",
        )

    all_items, ws_path, scanner_name = _scan_items_for_workspace(workspace)
    allowed_types = SECTION_TYPE_MAP[section]
    filtered = [i for i in all_items if i.get("type") in allowed_types]
    response = build_response(filtered)
    response["workspace"] = str(ws_path)
    response["scanner"] = scanner_name
    return response
