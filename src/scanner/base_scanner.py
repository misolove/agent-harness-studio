import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

SENSITIVE_KEYS = ["SECRET", "API_KEY", "TOKEN", "PASSWORD", "KEY", "CRED", "AUTH"]
TOKEN_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".sh", ".txt"}
TOKEN_EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "checkpoints",
    "cache",
    "logs",
    "node_modules",
    "sessions",
    "state",
}
TOKEN_EXCLUDED_SUFFIXES = {".bak", ".db", ".lock", ".sqlite", ".sqlite3", ".pb", ".pbtxt", ".bin", ".proto"}
MAX_TOKEN_ESTIMATE_FILE = 50000
MAX_TOKEN_ESTIMATE_DIR = 50000
MAX_TOKEN_ESTIMATE_FILES_PER_DIR = 100
METADATA_TOKEN_ITEM_TYPES = {"Memory Config", "Root Context", "MCP Server", "Hook"}

def mask_sensitive_value(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    key_upper = key.upper()
    if any(s in key_upper for s in SENSITIVE_KEYS):
        return "REDACTED"
    return value

def mask_env_dict(env_dict: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(env_dict, dict):
        return env_dict
    return {k: mask_sensitive_value(k, v) for k, v in env_dict.items()}

def mask_sensitive_mapping(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: mask_sensitive_mapping(mask_sensitive_value(k, v)) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_sensitive_mapping(v) for v in data]
    return data

def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def resolve_representative_file(path: Path) -> Optional[Path]:
    """Return the best editable file for a harness path that may be a directory/symlink."""
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        resolved = path
    if resolved.is_file():
        return resolved
    if not resolved.is_dir():
        return None
    preferred_names = [
        "SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "README.md",
        "plugin.yaml",
        "plugin.yml",
        "plugin.json",
        "config.toml",
        "config.json",
        "settings.json",
    ]
    for name in preferred_names:
        candidate = resolved / name
        if candidate.is_file():
            return candidate
    for pattern in ("*.md", "*.mdc", "*.toml", "*.yaml", "*.yml", "*.json", "*.rules", "*.txt", "*.py", "*.sh"):
        matches = sorted(resolved.glob(pattern))
        if matches:
            return matches[0]
    return None

class BaseHarnessScanner:
    """Abstract base class for all agent workspace scanners."""

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)

    def _finalize_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Annotate paths consistently and add token estimates."""
        for item in items:
            source_path = item.get("source_path")
            if source_path:
                path = Path(source_path)
                representative = resolve_representative_file(path)
                metadata = item.setdefault("metadata", {})
                should_preserve_directory = item.get("type") == "Memory Directory" or metadata.get("preserve_directory")
                if should_preserve_directory:
                    if representative:
                        metadata["representative_file"] = str(representative)
                elif representative and representative != path:
                    metadata["original_source_path"] = str(path)
                    metadata["representative_file"] = str(representative)
                    item["source_path"] = str(representative)
                metadata["is_directory"] = Path(item["source_path"]).is_dir()
            item["token_estimate"] = self._estimate_tokens_for_item(item)
        return items

    def _estimate_tokens_for_item(self, item: Dict[str, Any]) -> int:
        if item.get("type") in {"Memory State"}:
            return 0
        if item.get("metadata", {}).get("prompt_injected") is False:
            return 0
        if item.get("type") == "Skill":
            metadata = item.get("metadata", {})
            payload = {
                "category": metadata.get("category"),
                "name": item.get("name"),
            }
            return max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4)
        if item.get("type") == "Memory Config":
            payload = {
                "type": item.get("type"),
                "name": item.get("name"),
                "summary": item.get("summary"),
            }
            return max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4)
        if item.get("type") in {"Cron Job", "Hook", "MCP Server", "Plugin", "Skill Bundle"}:
            payload = {
                "type": item.get("type"),
                "name": item.get("name"),
                "summary": item.get("summary"),
                "state": item.get("state"),
                "metadata": item.get("metadata", {}),
            }
            return min(1000, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4)
        source_path = item.get("source_path")
        if not source_path:
            return 0
        path = Path(source_path)
        if not path.exists():
            return 0
        if any(part in TOKEN_EXCLUDED_DIRS for part in path.parts):
            return 0
        if path.is_file():
            try:
                if path.suffix in TOKEN_EXCLUDED_SUFFIXES:
                    return 0
                if path.suffix in TOKEN_TEXT_SUFFIXES:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    return min(MAX_TOKEN_ESTIMATE_FILE, max(0, len(content) // 4))
                else:
                    return min(MAX_TOKEN_ESTIMATE_FILE, max(0, path.stat().st_size // 4))
            except Exception:
                return 0
        elif path.is_dir():
            total = 0
            scanned = 0
            try:
                for f in path.rglob("*"):
                    if scanned >= MAX_TOKEN_ESTIMATE_FILES_PER_DIR or total >= MAX_TOKEN_ESTIMATE_DIR:
                        break
                    if any(part in TOKEN_EXCLUDED_DIRS for part in f.parts):
                        continue
                    if f.is_file() and f.suffix in TOKEN_TEXT_SUFFIXES and f.suffix not in TOKEN_EXCLUDED_SUFFIXES:
                        total += min(MAX_TOKEN_ESTIMATE_FILE, len(f.read_text(encoding="utf-8", errors="ignore")) // 4)
                        scanned += 1
            except Exception:
                pass
            return min(MAX_TOKEN_ESTIMATE_DIR, total)
        return 0

    def scan_all(self) -> List[Dict[str, Any]]:
        """Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement scan_all()")
