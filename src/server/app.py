import sys
import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, cast
import subprocess
import json
import re
import sqlite3
import html
import shutil
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse, parse_qs
from openai import OpenAI
from dotenv import load_dotenv, set_key
import httpx

# Load project-local .env (never commit secrets)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
ENV_PATH = PROJECT_ROOT / ".env"

# Add src/ and src/server/ to path so we can import scanner and scrapers
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Determine Harness Home — allow override for testing
DEFAULT_HERMES_HOME = Path.home() / ".hermes"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(DEFAULT_HERMES_HOME)))
MOLDER_AUTO_WEB_SEARCH = os.environ.get("MOLDER_AUTO_WEB_SEARCH", "1").lower() not in ("0", "false", "no")
MOLDER_WEB_SEARCH_TIMEOUT = float(os.environ.get("MOLDER_WEB_SEARCH_TIMEOUT", "8"))
MOLDER_WEB_SEARCH_LIMIT = int(os.environ.get("MOLDER_WEB_SEARCH_LIMIT", "5"))

# HARNESS_READONLY=1 → 모든 쓰기 API 차단. 실수 방지용.
HARNESS_READONLY = os.environ.get("HARNESS_READONLY", "").lower() in ("1", "true", "yes")

# --- SQLite Audit Log Helper ---
DB_PATH = HERMES_HOME / "harness_studio.db"

def _ensure_harness_gitignore(workspace: Optional[Path] = None) -> None:
    """Keep Harness Studio sidecar files out of user-managed git history."""
    if HARNESS_READONLY:
        return
    target_workspace = workspace or HERMES_HOME
    gitignore = target_workspace / ".gitignore"
    wanted = ["*.bak.*", ".env", "*.log", "harness_studio.db*"]
    try:
        existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
        merged = list(existing)
        changed = False
        for pattern in wanted:
            if pattern not in existing:
                merged.append(pattern)
                changed = True
        if changed:
            gitignore.parent.mkdir(parents=True, exist_ok=True)
            gitignore.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    except Exception as e:
        print(f"Failed to update .gitignore for Harness Studio state: {e}")

def init_db():
    if HARNESS_READONLY:
        return
    try:
        HERMES_HOME.mkdir(parents=True, exist_ok=True)
        _ensure_harness_gitignore()
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT,
                action TEXT,
                target_path TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to initialize SQLite DB: {e}")

def log_audit_event(actor: str, action: str, target_path: str, details: str = ""):
    if HARNESS_READONLY:
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_events (actor, action, target_path, details) VALUES (?, ?, ?, ?)",
            (actor, action, target_path, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to log audit event: {e}")

init_db()

# --- Git Integration Helpers ---

def _get_allowed_roots() -> list[Path]:
    return [
        PROJECT_ROOT.resolve(),
        HERMES_HOME.resolve(),
        (Path.home() / ".claude").resolve(),
        (Path.home() / ".cursor").resolve(),
        (Path.home() / ".codex").resolve(),
        (Path.home() / ".openclaw").resolve(),
        (Path.home() / ".gemini").resolve(),
    ]

def _get_workspace_for_path(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root)
            return root
        except ValueError:
            continue
    return HERMES_HOME


def _resolve_workspace_path(workspace: Optional[str] = None) -> Path:
    """Resolve a workspace parameter and keep it inside known local agent roots."""
    if not workspace:
        return HERMES_HOME.resolve()
    resolved = Path(workspace).expanduser().resolve(strict=False)
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Access denied: outside allowed agent workspaces")


def _is_git_repo(workspace: Path) -> bool:
    """Check if the workspace is a git repository."""
    r = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(workspace),
        capture_output=True,
    )
    return r.returncode == 0


def _git_commit_file(file_path: Path, message: str) -> Dict[str, Any]:
    """Stage one file and create a commit in the appropriate workspace. Returns result dict."""
    workspace = _get_workspace_for_path(file_path)
    try:
        rel = file_path.resolve(strict=False).relative_to(workspace)
    except ValueError:
        return {"committed": False, "error": "File outside allowed workspaces"}

    add = subprocess.run(
        ["git", "add", str(rel)],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        return {"committed": False, "error": add.stderr.strip()}

    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        if "nothing to commit" in commit.stdout or "nothing to commit" in commit.stderr:
            return {"committed": False, "note": "Nothing to commit"}
        return {"committed": False, "error": commit.stderr.strip()}

    short_hash = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    ).stdout.strip()

    return {"committed": True, "hash": short_hash, "message": message}


def _git_current_branch(workspace: Path) -> Optional[str]:
    """Return current branch name, or None if error."""
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def _git_commit_count(workspace: Path) -> Optional[int]:
    """Return total number of commits, or None."""
    r = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    try:
        return int(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError:
        return None

print(f"=====================================")
print(f"🚀 AGENT HARNESS STUDIO STARTING")
print(f"📁 Target HERMES_HOME: {HERMES_HOME}")
print(f"=====================================")

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from scanner.antigravity_scanner import AntigravityScanner
from scanner.claude_scanner import ClaudeScanner
from scanner.codex_scanner import CodexScanner
from scanner.cursor_scanner import CursorScanner
from scanner.gemini_cli_scanner import GeminiCliScanner
from scanner.hermes_scanner import HermesScanner
from scanner.openclaw_scanner import OpenClawScanner
from scanner.studio_scanner import StudioScanner
from scrapers import HybridScraper, ScrapRequest, PhaseStatus


app = FastAPI(
    title="Agent Harness Studio API",
    description="Scans and serves Hermes agent harness configuration",
    version="0.1.0",
)

# CORS — allow Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_llm_provider_config() -> Dict[str, Any]:
    """Return the effective Chat Molder LLM provider without exposing secrets."""
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "harness-model")
    if base_url:
        return {
            "provider": os.environ.get("LLM_PROVIDER_NAME", "Custom"),
            "source": "env",
            "base_url": base_url,
            "model": model,
            "api_key_set": bool(os.environ.get("LLM_API_KEY")),
            "editable": True,
        }

    config_path = HERMES_HOME / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = yaml.safe_load(f)
                custom = c.get("providers", {}).get("custom", {})
                for key, v in custom.items():
                    if "base_url" in v:
                        return {
                            "provider": key,
                            "source": "hermes-config",
                            "base_url": v["base_url"],
                            "model": model,
                            "api_key_set": bool(v.get("api_key")),
                            "editable": True,
                        }
        except Exception:
            pass

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return {
            "provider": "OpenAI",
            "source": "env",
            "base_url": "",
            "model": os.environ.get("LLM_MODEL", "gpt-4o"),
            "api_key_set": True,
            "editable": True,
        }

    return {
        "provider": "llm-proxy",
        "source": "default",
        "base_url": "http://localhost:20128/v1",
        "model": model,
        "api_key_set": False,
        "editable": True,
    }


# Initialize OpenAI client for LLM proxy (with fallback to OpenAI API)
def get_llm_client():
    config = get_llm_provider_config()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "dummy"
    if config["base_url"]:
        return OpenAI(base_url=config["base_url"], api_key=api_key), config["model"]
    return OpenAI(api_key=api_key), config["model"]


@app.get("/api/llm/provider")
def get_llm_provider():
    return get_llm_provider_config()


@app.post("/api/llm/provider")
def update_llm_provider(config: Dict[str, Any] = Body(...)):
    """Persist Chat Molder LLM provider settings to project .env and apply immediately."""
    provider = str(config.get("provider") or "Custom").strip()
    base_url = str(config.get("base_url") or "").strip()
    model = str(config.get("model") or "harness-model").strip()
    api_key = config.get("api_key")

    if not model:
        raise HTTPException(status_code=400, detail="model is required")
    if base_url and not re.match(r"^https?://", base_url):
        raise HTTPException(status_code=400, detail="base_url must start with http:// or https://")

    ENV_PATH.touch(exist_ok=True)
    updates = {
        "LLM_PROVIDER_NAME": provider,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    }
    for key, value in updates.items():
        os.environ[key] = value
        set_key(str(ENV_PATH), key, value)

    if isinstance(api_key, str) and api_key.strip():
        os.environ["LLM_API_KEY"] = api_key.strip()
        set_key(str(ENV_PATH), "LLM_API_KEY", api_key.strip())

    return get_llm_provider_config()

# Section type mapping
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

PI_AGENT_DIR = Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi" / "agent"))).expanduser()
PI_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "XAI_API_KEY",
    "HUGGINGFACE_API_KEY",
    "OLLAMA_HOST",
]

# Pi run infrastructure ──────────────────────────────────────────────────────
RUNS_BASE_DIR    = HERMES_HOME / "harness-studio-runs" / "pi"
PI_SESSIONS_DIR  = RUNS_BASE_DIR / "sessions"
READONLY_TOOLS   = "read,grep,find,ls"
MOLD_TOOLS       = "read,grep,find,ls,web_search"   # Chat Molder용 — web_search 포함
BLOCKED_TOOLS    = {"write", "edit", "bash"}

# Candidate .env files to load into Pi subprocess environment (first found wins)
_PI_ENV_CANDIDATES: List[Path] = [
    Path.home() / "hermes-memory-pointer-architecture" / ".env",
    HERMES_HOME / ".env",
    Path.home() / ".pi" / ".env",
]

def _get_pi_subprocess_env() -> Dict[str, str]:
    """Return os.environ merged with any .env file found at candidate paths."""
    env = os.environ.copy()
    for candidate in _PI_ENV_CANDIDATES:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in env:   # don't override existing env vars
                        env[key] = val
            except Exception:
                pass
            break  # only load first found
    return env

# In-memory run registry (process-local, ephemeral across restarts)
_PI_RUNS: Dict[str, Dict[str, Any]] = {}
_PI_RUN_LOCK = threading.Lock()


def _pi_read_settings() -> Dict[str, Any]:
    """Parse ~/.pi/agent/settings.json for provider/model info (safe fields only)."""
    settings_path = PI_AGENT_DIR / "settings.json"
    if not settings_path.exists():
        return {}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            "defaultProvider": data.get("defaultProvider"),
            "defaultModel": data.get("defaultModel"),
            "packages": data.get("packages", []),
            "lastChangelogVersion": data.get("lastChangelogVersion"),
        }
    except Exception:
        return {}


def _capture_git_audit(ws_path: Path) -> Dict[str, Any]:
    """Minimal git status snapshot for pre/post run audit."""
    if not _is_git_repo(ws_path):
        return {"is_git_repo": False, "changed_files": [], "file_count": 0, "stat": ""}
    status_r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ws_path), capture_output=True, text=True,
    )
    stat_r = subprocess.run(
        ["git", "diff", "--stat", "HEAD"],
        cwd=str(ws_path), capture_output=True, text=True,
    )
    changed: List[Dict[str, Any]] = []
    for line in status_r.stdout.splitlines():
        if len(line) < 4:
            continue
        code = line[:2].strip()
        path = line[3:].strip().split(" -> ")[-1]
        changed.append({"status": code, "path": path})
    return {
        "is_git_repo": True,
        "changed_files": changed,
        "file_count": len(changed),
        "stat": stat_r.stdout[:3000],
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_pi_subprocess(run_id: str, cmd: List[str], run_dir: Path) -> None:
    """Execute Pi in a background thread; persist stdout/stderr/RPC events."""
    stdout_log  = run_dir / "stdout.log"
    stderr_log  = run_dir / "stderr.log"
    events_log  = run_dir / "events.jsonl"
    meta_path   = run_dir / "meta.json"
    proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]

    def _save_meta() -> None:
        with _PI_RUN_LOCK:
            meta = dict(_PI_RUNS.get(run_id, {}))
        try:
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    with _PI_RUN_LOCK:
        _PI_RUNS[run_id]["status"] = "running"
        _PI_RUNS[run_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        pi_env = _get_pi_subprocess_env()
        with open(stderr_log, "w", encoding="utf-8") as err_f:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=err_f,
                text=True,
                bufsize=1,
                env=pi_env,
            )

        with _PI_RUN_LOCK:
            _PI_RUNS[run_id]["pid"] = proc.pid

        # Stream stdout line-by-line; parse RPC/JSON events
        with open(stdout_log, "w", encoding="utf-8") as out_f:
            assert proc.stdout is not None  # guaranteed by PIPE
            for line in proc.stdout:
                out_f.write(line)
                out_f.flush()
                stripped = line.strip()
                if stripped.startswith("{"):
                    try:
                        event = json.loads(stripped)
                        with open(events_log, "a", encoding="utf-8") as ef:
                            ef.write(json.dumps(event, ensure_ascii=False) + "\n")
                    except Exception:
                        pass

        proc.wait(timeout=120)
        exit_code = proc.returncode

        # Capture post-audit
        ws_path = Path(_PI_RUNS.get(run_id, {}).get("workspace", str(HERMES_HOME)))
        post_audit = _capture_git_audit(ws_path)
        (run_dir / "post-audit.json").write_text(
            json.dumps(post_audit, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        with _PI_RUN_LOCK:
            _PI_RUNS[run_id]["status"] = "done" if exit_code == 0 else "error"
            _PI_RUNS[run_id]["exit_code"] = exit_code
            _PI_RUNS[run_id]["ended_at"] = datetime.now(timezone.utc).isoformat()
            _PI_RUNS[run_id]["post_audit"] = post_audit

    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        with _PI_RUN_LOCK:
            _PI_RUNS[run_id]["status"] = "timeout"
            _PI_RUNS[run_id]["ended_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        with _PI_RUN_LOCK:
            _PI_RUNS[run_id]["status"] = "error"
            _PI_RUNS[run_id]["error"] = str(exc)
            _PI_RUNS[run_id]["ended_at"] = datetime.now(timezone.utc).isoformat()
    finally:
        _save_meta()


def _run_command_probe(cmd: List[str], timeout: float = 4.0) -> Dict[str, Any]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "Timed out"}
    except Exception as e:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(e)}


def _json_file_summary(path: Path) -> Dict[str, Any]:
    exists = path.exists()
    summary: Dict[str, Any] = {"exists": exists, "path": str(path)}
    if not exists:
        return summary
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            summary["keys"] = sorted(data.keys())
            summary["entry_count"] = len(data)
            summary["configured"] = any(bool(v) for v in data.values())
        else:
            summary["entry_count"] = len(data) if isinstance(data, list) else 1
            summary["configured"] = bool(data)
    except Exception as e:
        summary["error"] = str(e)
    return summary


def _count_pi_sessions(session_dir: Path) -> int:
    if not session_dir.exists() or not session_dir.is_dir():
        return 0
    try:
        return sum(1 for p in session_dir.rglob("*") if p.is_file())
    except Exception:
        return 0


def _pi_status(workspace: Optional[str] = None) -> Dict[str, Any]:
    ws_path = _resolve_workspace_path(workspace)
    executable = shutil.which("pi")
    installed = bool(executable)
    version = None
    help_text = ""
    probes: Dict[str, Any] = {}

    if installed:
        version_probe = _run_command_probe(["pi", "--version"])
        help_probe = _run_command_probe(["pi", "--help"])
        probes = {"version": version_probe, "help": help_probe}
        version = (version_probe.get("stdout") or version_probe.get("stderr") or "").splitlines()[0:1]
        version = version[0] if version else None
        help_text = f"{help_probe.get('stdout', '')}\n{help_probe.get('stderr', '')}"

    settings = _json_file_summary(PI_AGENT_DIR / "settings.json")
    auth = _json_file_summary(PI_AGENT_DIR / "auth.json")
    models = _json_file_summary(PI_AGENT_DIR / "models.json")
    provider_info = _pi_read_settings()
    env_keys = [key for key in PI_ENV_KEYS if os.environ.get(key)]
    supports_rpc = "--mode <mode>" in help_text and "rpc" in help_text
    supports_json = "--mode <mode>" in help_text and "json" in help_text
    supports_print = "--print" in help_text or "-p" in help_text

    return {
        "id": "pi",
        "name": "Pi Coding Agent",
        "state": "READY" if installed else "MISSING",
        "installed": installed,
        "executable": executable,
        "version": version,
        "provider_info": provider_info,
        "workspace": str(ws_path),
        "workspace_git": {
            "is_git_repo": _is_git_repo(ws_path),
            "branch": _git_current_branch(ws_path) if _is_git_repo(ws_path) else None,
            "commit_count": _git_commit_count(ws_path) if _is_git_repo(ws_path) else None,
        },
        "config": {
            "agent_dir": str(PI_AGENT_DIR),
            "settings": settings,
            "auth": auth,
            "models": models,
            "session_count": _count_pi_sessions(PI_AGENT_DIR / "sessions"),
            "env_keys_present": env_keys,
            "auth_configured": bool(auth.get("configured") or env_keys),
        },
        "capabilities": {
            "interactive_tui": installed,
            "print_mode": installed and supports_print,
            "json_mode": installed and supports_json,
            "rpc_mode": installed and supports_rpc,
            "read_only_tool_allowlist": installed and "--tools" in help_text,
            "tools": ["read", "write", "edit", "bash", "grep", "find", "ls"],
        },
        "safety": {
            "execution_api_enabled": False,
            "current_stage": "detect-only",
            "recommended_next": [
                "Start with RPC/json event ingestion using --tools read,grep,find,ls and --no-session.",
                "Before each run, capture git audit baseline and require a clean or explicitly accepted diff.",
                "After each run, show stdout/stderr logs and git diff before any commit.",
            ],
            "blocked_actions": ["interactive launch", "autonomous write/edit/bash execution"],
        },
        "probes": probes,
    }

LOG_FILE_SUFFIXES = {".log", ".out", ".err", ".jsonl", ".ndjson"}
LOG_DIR_NAMES = {"logs", "log", "sessions", "runs", "traces"}
LOG_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv"}


def _discover_log_items(workspace: Path, limit: int = 80) -> List[Dict[str, Any]]:
    """Find real runtime/event log files for a workspace without scanning huge trees."""
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
    """Add common file stats so UI sorting works across scanner implementations."""
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
    """Select the agent-specific scanner for a configured workspace path."""
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
    """Run the same full scan shape used by /api/scan for internal consumers."""
    scanner, ws_path, scanner_name = _scanner_for_workspace(workspace)
    items = scanner.scan_all()
    items.extend(_discover_log_items(ws_path))
    _enrich_file_metadata(items)
    return items, ws_path, scanner_name

def build_response(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a standardised response envelope with a summary."""
    items = _enrich_file_metadata(items)
    summary: Dict[str, int] = {}
    for item in items:
        t = item.get("type", "Unknown")
        # Group into our 6 dashboard sections
        if t == "Skill":
            summary["skills"] = summary.get("skills", 0) + 1
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
    summary["web"] = 0 # Placeholder for Web Context count

    return {"summary": summary, "items": items, "total": len(items)}


@app.get("/api/workspaces")
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


@app.get("/api/agent-runners")
def get_agent_runners(workspace: Optional[str] = None):
    pi = _pi_status(workspace)
    return {
        "runners": [pi],
        "summary": {
            "total": 1,
            "ready": 1 if pi["installed"] else 0,
            "detect_only": 1,
        },
    }


@app.get("/api/pi/status")
def get_pi_status(workspace: Optional[str] = None):
    return _pi_status(workspace)


@app.post("/api/pi/preview")
def preview_pi_run(req: Dict[str, Any] = Body(default={})):
    """Return a safe command plan for Pi without launching the agent."""
    # TODO(agent-runner): replace preview-only flow with an async read-only RPC
    # subprocess that persists events/logs and captures pre/post git audit.
    ws_path = _resolve_workspace_path(req.get("workspace"))
    prompt = str(req.get("prompt") or "").strip()
    mode = str(req.get("mode") or "rpc").strip().lower()
    if mode not in {"rpc", "json", "print"}:
        raise HTTPException(status_code=400, detail="mode must be one of: rpc, json, print")

    status = _pi_status(str(ws_path))
    if not status["installed"]:
        raise HTTPException(status_code=404, detail="pi CLI not found on PATH")

    mode_args = ["--mode", "rpc"] if mode == "rpc" else ["--mode", "json"]
    if mode == "print":
        mode_args = ["-p"]

    command = ["pi", "--tools", "read,grep,find,ls", "--no-session", *mode_args]
    if prompt:
        command.append(prompt)

    return {
        "status": "preview",
        "will_execute": False,
        "workspace": str(ws_path),
        "command": command,
        "safety_note": "Execution is intentionally disabled in this endpoint. Use it to review the first safe runner command before adding a gated run API.",
    }


@app.post("/api/pi/runs")
def create_pi_run(req: Dict[str, Any] = Body(default={})):
    """Start a Pi read-only RPC run in a background thread.

    Allowed tools: read, grep, find, ls (READONLY_TOOLS).
    write / edit / bash are blocked until gated-write mode is explicitly enabled.
    """
    ws_path  = _resolve_workspace_path(req.get("workspace"))
    prompt   = str(req.get("prompt") or "").strip()
    mode_req = str(req.get("mode") or "read_only").strip().lower()

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if mode_req != "read_only":
        raise HTTPException(
            status_code=400,
            detail="Only read_only mode is currently supported. Gated write mode is not yet enabled.",
        )

    pi = _pi_status(str(ws_path))
    if not pi["installed"]:
        raise HTTPException(status_code=404, detail="pi CLI not found on PATH")

    run_id  = uuid.uuid4().hex[:12]
    run_dir = RUNS_BASE_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Pre-run git audit
    pre_audit = _capture_git_audit(ws_path)
    (run_dir / "pre-audit.json").write_text(
        json.dumps(pre_audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    command = [
        "pi",
        "--tools", READONLY_TOOLS,
        "--no-session",
        "--mode", "rpc",
        prompt,
    ]

    meta: Dict[str, Any] = {
        "run_id": run_id,
        "command": command,
        "workspace": str(ws_path),
        "prompt": prompt,
        "mode": mode_req,
        "status": "queued",
        "pid": None,
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "pre_audit": pre_audit,
        "post_audit": None,
    }

    with _PI_RUN_LOCK:
        _PI_RUNS[run_id] = meta

    threading.Thread(
        target=_run_pi_subprocess,
        args=(run_id, command, run_dir),
        daemon=True,
        name=f"pi-run-{run_id}",
    ).start()

    return {
        "run_id": run_id,
        "status": "queued",
        "command": command,
        "workspace": str(ws_path),
        "pre_audit": pre_audit,
    }


@app.get("/api/pi/runs/{run_id}")
def get_pi_run(run_id: str):
    """Return current status and metadata of a Pi run."""
    with _PI_RUN_LOCK:
        meta = _PI_RUNS.get(run_id)

    # Fallback: try persisted meta.json on disk
    if meta is None:
        meta_path = RUNS_BASE_DIR / run_id / "meta.json"
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return meta


@app.get("/api/pi/runs/{run_id}/log")
def get_pi_run_log(run_id: str, tail: int = 200):
    """Return the last N lines of stdout + stderr for a Pi run."""
    run_dir = RUNS_BASE_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")

    def _read_tail(path: Path, n: int) -> str:
        if not path.exists():
            return ""
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except Exception:
            return ""

    return {
        "run_id": run_id,
        "stdout": _read_tail(run_dir / "stdout.log", tail),
        "stderr": _read_tail(run_dir / "stderr.log", tail),
        "events_count": sum(1 for _ in (run_dir / "events.jsonl").open() if (run_dir / "events.jsonl").exists()) if (run_dir / "events.jsonl").exists() else 0,
    }


@app.post("/api/pi/runs/{run_id}/stop")
def stop_pi_run(run_id: str):
    """Kill a running Pi subprocess by SIGTERM."""
    with _PI_RUN_LOCK:
        meta = _PI_RUNS.get(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    pid = meta.get("pid")
    if not pid:
        return {"run_id": run_id, "action": "noop", "reason": "no pid recorded"}
    try:
        import signal
        os.kill(pid, signal.SIGTERM)
        with _PI_RUN_LOCK:
            _PI_RUNS[run_id]["status"] = "stopped"
        return {"run_id": run_id, "action": "sigterm_sent", "pid": pid}
    except ProcessLookupError:
        return {"run_id": run_id, "action": "noop", "reason": "process already gone"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pi/mold")
def pi_mold_chat(req: Dict[str, Any] = Body(default={})):
    """Pi-powered Chat Molder.

    Routes the user message through the Pi coding agent (read-only tools) so
    it can search the workspace, read files, and answer with full context
    awareness — unlike the direct LLM path which has no tool access.

    Same request shape as POST /api/mold plus an optional 'workspace' field.
    Returns {run_id, status} immediately; poll GET /api/pi/runs/{id} and
    GET /api/pi/runs/{id}/log for the live answer.
    """
    ws_path        = _resolve_workspace_path(req.get("workspace"))
    prompt         = str(req.get("prompt") or "").strip()
    context        = str(req.get("context") or "")
    editing_name   = req.get("editing_file_name") or ""
    editing_content = req.get("editing_file_content") or ""
    session_file   = req.get("session_file") or None  # None = new conversation

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    pi = _pi_status(str(ws_path))
    if not pi["installed"]:
        raise HTTPException(status_code=404, detail="pi CLI not found on PATH")

    # Resolve session path
    PI_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if session_file:
        session_path = Path(session_file)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        session_path = PI_SESSIONS_DIR / f"mold-{ts}-{uuid.uuid4().hex[:6]}.jsonl"

    is_new_session = not session_path.exists()

    # --- Build Pi command ---
    if is_new_session:
        # First turn: inject full harness context in the prompt
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()
        context_str = build_molder_context(items, context)[:8000]

        if editing_name and editing_content:
            context_str += (
                f"\n\n[USER IS CURRENTLY EDITING FILE]\n"
                f"File: {editing_name}\n"
                f"Content:\n{editing_content[:2000]}"
            )

        first_prompt = "\n".join([
            "You are an AI assistant for Agent Harness Studio.",
            "You help manage the Hermes agent harness at ~/.hermes.",
            "You can read files and search the web to give accurate answers.",
            "When you suggest file modifications, clearly state the file path and the exact change needed.",
            "",
            "## Harness Context",
            context_str,
            "",
            "## User Request",
            prompt,
        ])

        command = [
            "pi",
            "--tools", MOLD_TOOLS,
            "--session", str(session_path),
            "--print",
            first_prompt,
        ]
    else:
        # Continuation: Pi already knows the context from session history
        command = [
            "pi",
            "--tools", MOLD_TOOLS,
            "--session", str(session_path),
            "--continue",
            "--print",
            prompt,
        ]

    run_id  = uuid.uuid4().hex[:12]
    run_dir = RUNS_BASE_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    pre_audit = _capture_git_audit(ws_path)
    (run_dir / "pre-audit.json").write_text(
        json.dumps(pre_audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    meta: Dict[str, Any] = {
        "run_id": run_id,
        "command": ["pi", "--tools", MOLD_TOOLS, "--session", "<session>", "--print", "<prompt>"],
        "workspace": str(ws_path),
        "prompt": prompt[:200],
        "mode": "mold",
        "session_file": str(session_path),
        "is_new_session": is_new_session,
        "status": "queued",
        "pid": None,
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "pre_audit": pre_audit,
        "post_audit": None,
    }

    with _PI_RUN_LOCK:
        _PI_RUNS[run_id] = meta

    threading.Thread(
        target=_run_pi_subprocess,
        args=(run_id, command, run_dir),
        daemon=True,
        name=f"pi-mold-{run_id}",
    ).start()

    return {
        "run_id": run_id,
        "status": "queued",
        "session_file": str(session_path),
        "is_new_session": is_new_session,
    }


@app.get("/api/scan")
def scan_all(workspace: str = None):
    """Return full harness scan results."""
    try:
        items, ws_path, scanner_name = _scan_items_for_workspace(workspace)
        response = build_response(items)
        response["workspace"] = str(ws_path)
        response["scanner"] = scanner_name
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scan/{section}")
def scan_section(section: str, workspace: str = None):
    """Return scan results for a specific section.

    Valid sections: skills, memory, mcp, context, hooks, config
    """
    section = section.lower()
    if section not in SECTION_TYPE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown section '{section}'. Valid sections: {list(SECTION_TYPE_MAP.keys())}",
        )

    try:
        all_items, ws_path, scanner_name = _scan_items_for_workspace(workspace)
        allowed_types = SECTION_TYPE_MAP[section]
        filtered = [i for i in all_items if i.get("type") in allowed_types]
        response = build_response(filtered)
        response["workspace"] = str(ws_path)
        response["scanner"] = scanner_name
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Chat Molder & Editing API ---

HERMES_AGENT_REFERENCE_URL = "https://github.com/NousResearch/hermes-agent"

HERMES_REFERENCE_CONTEXT = f"""# Canonical Hermes Agent Reference

Agent Harness Studio treats `nousresearch/hermes-agent` as the default upstream
reference for Hermes behavior and schema decisions.

Reference URL: {HERMES_AGENT_REFERENCE_URL}

## Hermes Mental Model
- Hermes is an open-source agent framework by Nous Research with a learning loop,
  skills, memory, MCP servers, hooks, cron jobs, plugins, and gateway integrations.
- The user harness normally lives in `~/.hermes`; this app uses `HERMES_HOME` to
  override that location for sandboxing or tests.
- The primary user configuration file is `~/.hermes/config.yaml`.

## Canonical Harness Surfaces
- Skills: `~/.hermes/skills/**/SKILL.md`, plus external directories configured
  by `skills.external_dirs`.
- Skill metadata: YAML frontmatter with `name`, `description`, and
  `metadata.hermes` fields such as `tags`, `category`, `related_skills`, and
  config requirements.
- Skill bundles: `~/.hermes/skill-bundles/*.yaml`, grouping skills into reusable
  workflow packs.
- MCP servers: `config.yaml` key `mcp_servers`; supports stdio servers with
  `command`/`args`/`env` and HTTP servers with `url`/`headers`. Common metadata
  includes `enabled`, `tools.include`, `tools.exclude`, `auth`, `sampling`, and
  timeout settings.
- Hooks: shell hooks from `config.yaml` `hooks`, gateway hooks under
  `~/.hermes/hooks/<name>/HOOK.yaml` with optional `handler.py`, and plugin
  provided hooks.
- Memory: `config.yaml` memory settings, `memory_manifest.md`, `memories/`, and
  state files/databases under `state/`.
- Cron: scheduled jobs under `~/.hermes/cron/jobs.json`.
- Plugins: `~/.hermes/plugins/*/plugin.yaml`.
- Root context: `AGENTS.md`, `SOUL.md`, and `config.yaml` `system_prompt` shape
  the agent's long-lived behavior.

## Molder Safety Rules
- Prefer small, schema-valid edits over broad rewrites.
- Never invent non-Hermes schema keys when a known Hermes key exists.
- Never expose or fabricate secrets, tokens, API keys, or private paths.
- If a requested change targets a surface that this app cannot safely apply yet,
  return `SUGGESTION` with concrete manual guidance instead of fake content.
- If general LLM knowledge conflicts with this reference, follow the Hermes
  reference context and the current scanned harness state.
"""


MOLDER_SYSTEM_PROMPT = """You are a Harness Molder — an AI assistant for the Agent Harness Studio.
You help users understand, create, and modify Hermes Agent harness configurations.
You MUST respond in Korean (한국어) regardless of the language the user writes in.
You MUST use the provided Hermes Agent reference context as your default baseline.
When the user asks about Hermes behavior, schema, or file locations, reason from
`nousresearch/hermes-agent` and the current scanned harness context first.

## Response Modes

### Mode 1: Conversation (default)
If the user is asking a question, requesting an explanation, or having a general conversation:
- Respond with plain Korean text in a JSON object:
{
  "action": "CHAT",
  "message": "한국어 답변 내용"
}

### Mode 2: Harness Modification
ONLY when the user explicitly asks to create, modify, add, or change a harness item:
{
  "action": "CREATE_SKILL" | "UPDATE_SKILL" | "UPDATE_CONFIG" | "ADD_MCP",
  "name": "skill-or-item-name (kebab-case)",
  "description": "Short description",
  "message": "한국어로 무엇을 제안하는지 설명",
  "content": "Full file content (YAML frontmatter + Markdown body for skills)",
  "diff_summary": "변경 요약"
}

### Mode 3: Suggestion
When the user needs manual action or clarification:
{
  "action": "SUGGESTION",
  "message": "한국어로 제안 내용 설명"
}

## Skill File Schema (for CREATE/UPDATE_SKILL only)
The SKILL.md frontmatter MUST use this exact schema:
---
name: <kebab-case-name>
description: <short description>
metadata:
  hermes:
    tags: [tag-one, tag-two]
    category: <category>
---
Never write `hermese`, `hermes_agent`, `hermesAgent`. The key is exactly `metadata.hermes`.

## Rules
1. ALWAYS respond in Korean (한국어).
2. For questions/explanations → use CHAT mode (no content field needed).
3. For creation/modification requests → use CREATE_SKILL/UPDATE_SKILL mode.
4. Be concise but helpful. Use the Hermes reference and harness context provided.
5. If the user says something short or ambiguous like "줘", "해줘", "만들어줘", infer intent from the conversation context and the currently selected harness item.
6. If the requested change is for MCP/config/hooks/memory and the app does not provide a safe structured apply flow, use SUGGESTION instead of pretending the change can be applied as a skill.
7. Do not invent installed skill, MCP, or hook capabilities. When explaining current harness items, use only the names, summaries, states, and metadata in the current harness snapshot. If the snapshot is insufficient, say that the item must be opened/read for exact details.
8. Match the user's energy. For greetings or short casual turns, answer in 1-2 natural Korean sentences. Do not repeat onboarding menus unless the user asks what the app can do.
9. Avoid emoji-heavy or marketing-style responses. Use plain, grounded Korean. Markdown tables are okay only when they genuinely improve scanability.
10. The final message labeled `# Current User Request` is the task to answer now. Conversation history is only background. Never answer an older user request when the current request asks for something different.
11. For large inventories, do not dump everything. If there are more than 25 items, summarize by category and show at most 12 representative rows, then offer a focused drilldown. Keep ordinary answers under about 500 Korean words unless the user explicitly asks for exhaustive detail.
12. Format for readability: short intro, compact headings, bullets or a small table, then a short takeaway. Avoid long single paragraphs.
13. When listing items, use real Markdown syntax that the UI can render:
    - Section headings must start with `### `.
    - Item rows should use `- **item-name**: short explanation`.
    - Small comparisons may use a Markdown table with a header row and separator row.
    - Do not use bare label lines such as `MCP 서버 목록` without a Markdown heading marker.
14. For skills specifically, if the snapshot says there are many skills, present category counts plus up to 12 representative skills. Do not list every provided skill summary unless the user explicitly asks for an exhaustive list.
15. If a `# Web Search Context` section is present, use it to answer external, current, or unknown-project questions. Cite the result titles/domains in Korean instead of claiming you cannot browse. If the search context is empty or failed, say that automatic search did not return enough evidence.

Always respond with ONLY the JSON object, no other text."""


def build_molder_context(items: List[Dict[str, Any]], selected_context: str = "") -> str:
    """Build compact, model-agnostic harness context for the Chat Molder."""
    summary = build_response(items).get("summary", {})

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        by_type.setdefault(item.get("type", "Unknown"), []).append(item)

    def names(item_type: str, limit: int = 20) -> str:
        values = [item.get("name", "") for item in by_type.get(item_type, []) if item.get("name")]
        shown = values[:limit]
        suffix = f" ... (+{len(values) - limit})" if len(values) > limit else ""
        return ", ".join(shown) + suffix if shown else "none"

    def compact_text(value: str, limit: int = 220) -> str:
        text = re.sub(r"\s+", " ", (value or "").strip())
        return text[: limit - 1].rstrip() + "…" if len(text) > limit else text

    skill_category_counts: Dict[str, int] = {}
    for item in by_type.get("Skill", []):
        metadata = item.get("metadata", {}) or {}
        category = metadata.get("category") or metadata.get("path_category") or "uncategorized"
        skill_category_counts[category] = skill_category_counts.get(category, 0) + 1

    skill_category_summary = ", ".join(
        f"{category}={count}"
        for category, count in sorted(skill_category_counts.items(), key=lambda entry: (-entry[1], entry[0]))[:20]
    )

    skill_lines = []
    for item in by_type.get("Skill", [])[:12]:
        metadata = item.get("metadata", {}) or {}
        category = metadata.get("category") or metadata.get("path_category") or "uncategorized"
        summary_text = compact_text(item.get("summary") or "No summary available.")
        skill_lines.append(
            f"- {item.get('name')} [{item.get('state', 'UNKNOWN')}/{category}]: {summary_text}"
        )

    bundle_lines = []
    for item in by_type.get("Skill Bundle", [])[:20]:
        metadata = item.get("metadata", {}) or {}
        bundle_skills = metadata.get("skills") or []
        skill_hint = f" skills={', '.join(bundle_skills[:8])}" if bundle_skills else ""
        bundle_lines.append(
            f"- {item.get('name')} [{item.get('state', 'UNKNOWN')}]: {compact_text(item.get('summary') or '')}{skill_hint}"
        )

    mcp_lines = []
    for item in by_type.get("MCP Server", [])[:20]:
        metadata = item.get("metadata", {}) or {}
        status = item.get("status", "UNKNOWN")
        transport = metadata.get("transport") or ("http" if metadata.get("url") else "stdio")
        summary_text = compact_text(item.get("summary") or "")
        mcp_lines.append(f"- {item.get('name')} [{status}/{transport}]: {summary_text}")

    hook_lines = []
    for item in by_type.get("Hook", [])[:20]:
        metadata = item.get("metadata", {}) or {}
        hook_type = metadata.get("hook_type") or metadata.get("source") or "hook"
        summary_text = compact_text(item.get("summary") or "")
        hook_lines.append(f"- {item.get('name')} [{item.get('status', 'UNKNOWN')}/{hook_type}]: {summary_text}")

    context_parts = [
        "# Current Harness Snapshot",
        f"HERMES_HOME: {HERMES_HOME}",
        f"Read-only mode: {HARNESS_READONLY}",
        f"Selected UI context: {selected_context or 'none'}",
        f"Summary counts: {json.dumps(summary, ensure_ascii=False, sort_keys=True)}",
        f"Skill category counts: {skill_category_summary or 'none'}",
        "Representative skills with scanned summaries (do not exceed these unless user asks for exhaustive detail):",
        "\n".join(skill_lines) if skill_lines else "none",
        "Skill bundles:",
        "\n".join(bundle_lines) if bundle_lines else names("Skill Bundle", 20),
        "MCP servers:",
        "\n".join(mcp_lines) if mcp_lines else "none",
        "Hooks:",
        "\n".join(hook_lines) if hook_lines else "none",
        f"Plugins: {names('Plugin', 20)}",
        f"Cron jobs: {names('Cron Job', 20)}",
        f"Root context: {names('Root Context', 20)}",
        f"Memory surfaces: {names('Memory Config', 10)}; {names('Memory Manifest', 10)}; {names('Memory Directory', 10)}",
    ]
    return "\n".join(context_parts)


def should_auto_web_search(prompt: str) -> bool:
    """Heuristic gate for when Chat Molder should augment with web results."""
    if not MOLDER_AUTO_WEB_SEARCH:
        return False
    text = (prompt or "").lower()
    explicit = [
        "웹검색",
        "웹 검색",
        "검색해",
        "찾아봐",
        "찾아줘",
        "확인해",
        "알아봐",
        "구글",
        "github",
        "깃허브",
        "최신",
        "원래 뭐",
        "뭐하는",
        "무슨 프로젝트",
    ]
    if any(term in text for term in explicit):
        return True
    # Unknown package/project names often need an external lookup.
    if re.search(r"\b[a-z][a-z0-9_-]*(llama|mcp|agent|sdk|server)\b", text, re.I):
        return True
    return False


def _decode_duckduckgo_url(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    if parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return html.unescape(url)


def web_search_context(query: str, limit: int = MOLDER_WEB_SEARCH_LIMIT) -> str:
    """Best-effort lightweight web search context for Chat Molder."""
    query = re.sub(r"\s+", " ", (query or "").strip())
    if not query:
        return ""
    try:
        with httpx.Client(
            timeout=MOLDER_WEB_SEARCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "AgentHarnessStudio/0.1"},
        ) as client:
            response = client.get("https://html.duckduckgo.com/html/", params={"q": query})
            response.raise_for_status()
        body = response.text
    except Exception as e:
        return f"# Web Search Context\nQuery: {query}\nSearch failed: {e}"

    results = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    for href, raw_title in pattern.findall(body):
        title = re.sub(r"<.*?>", "", raw_title)
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        url = _decode_duckduckgo_url(href)
        domain = urlparse(url).netloc
        if not title or not url:
            continue
        results.append({"title": title, "url": url, "domain": domain})
        if len(results) >= limit:
            break

    if not results:
        return f"# Web Search Context\nQuery: {query}\nNo search results parsed."

    lines = [
        "# Web Search Context",
        f"Query: {query}",
        "Use these results as external evidence. Do not overclaim beyond titles/snippets unless the URL is opened elsewhere.",
    ]
    for idx, result in enumerate(results, start=1):
        lines.append(f"{idx}. {result['title']} ({result['domain']}) - {result['url']}")
    return "\n".join(lines)


@app.get("/api/reference/hermes")
def hermes_reference():
    """Return the canonical Hermes reference context injected into Chat Molder."""
    return {
        "reference_url": HERMES_AGENT_REFERENCE_URL,
        "context": HERMES_REFERENCE_CONTEXT,
        "source": "nousresearch/hermes-agent",
    }


def normalize_skill_content(content: str, name: str, description: str = "") -> str:
    """Repair common LLM-generated SKILL.md schema issues before preview/apply.

    The LLM is useful for drafting, but the harness owns the schema. This keeps
    generated skills indexable by Hermes even when the model misspells keys.
    """
    if not content:
        return content

    repaired = content.replace("hermese:", "hermes:")
    repaired = repaired.replace("hermes_agent:", "hermes:")
    repaired = repaired.replace("hermesAgent:", "hermes:")

    # If frontmatter is missing entirely, wrap the draft in valid SKILL.md metadata.
    if not repaired.lstrip().startswith("---"):
        safe_name = name or "generated-skill"
        safe_description = description or "Generated skill"
        return f"""---
name: {safe_name}
description: {safe_description}
metadata:
  hermes:
    tags: [generated]
    category: general
---

{repaired.strip()}
"""

    # If frontmatter exists but lacks metadata.hermes, add a minimal block before closing ---.
    parts = repaired.split("---", 2)
    if len(parts) >= 3:
        fm = parts[1]
        body = parts[2]
        if "metadata:" not in fm:
            fm = fm.rstrip() + "\nmetadata:\n  hermes:\n    tags: [generated]\n    category: general\n"
        elif "hermes:" not in fm:
            fm = fm.rstrip() + "\n  hermes:\n    tags: [generated]\n    category: general\n"
        repaired = f"---{fm}---{body}"

    return repaired

def validate_molder_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and annotate an LLM-generated molder proposal."""
    action = result.get("action", "SUGGESTION")
    if "SKILL" in action and result.get("content"):
        before = result["content"]
        after = normalize_skill_content(
            before,
            result.get("name", "generated-skill"),
            result.get("description", "Generated skill"),
        )
        result["content"] = after
        if before != after:
            result["diff_summary"] = (result.get("diff_summary", "") + "\nServer-side validation repaired SKILL.md frontmatter schema.").strip()
    return result


def strip_json_code_fence(text: str) -> str:
    """Remove common Markdown fences around model JSON."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    if cleaned.startswith("json\n"):
        cleaned = cleaned[5:].strip()
    return cleaned


def extract_json_string_field(text: str, field: str) -> Optional[str]:
    """Best-effort extraction for truncated JSON strings such as {"message": "..."}."""
    pattern = f'"{field}"'
    field_index = text.find(pattern)
    if field_index < 0:
        return None

    colon_index = text.find(":", field_index + len(pattern))
    if colon_index < 0:
        return None

    quote_index = text.find('"', colon_index + 1)
    if quote_index < 0:
        return None

    out: List[str] = []
    index = quote_index + 1
    while index < len(text):
        char = text[index]
        if char == '"':
            break
        if char == "\\" and index + 1 < len(text):
            escaped = text[index + 1]
            if escaped == "n":
                out.append("\n")
                index += 2
                continue
            if escaped == "t":
                out.append("\t")
                index += 2
                continue
            if escaped == "r":
                index += 2
                continue
            if escaped in ('"', "\\", "/"):
                out.append(escaped)
                index += 2
                continue
            if escaped == "u" and index + 5 < len(text):
                hex_value = text[index + 2:index + 6]
                try:
                    out.append(chr(int(hex_value, 16)))
                    index += 6
                    continue
                except ValueError:
                    pass
        out.append(char)
        index += 1

    recovered = "".join(out).strip()
    return recovered or None


def parse_molder_json(raw: str) -> Dict[str, Any]:
    """Parse model JSON, recovering CHAT messages from truncated JSON when possible."""
    cleaned = strip_json_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {"action": "CHAT", "message": str(parsed)}
    except json.JSONDecodeError:
        try:
            parsed, _ = json.JSONDecoder().raw_decode(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    recovered_message = extract_json_string_field(cleaned, "message")
    if recovered_message:
        return {
            "action": "CHAT",
            "message": recovered_message.rstrip() + "\n\n(응답이 길어 일부가 잘렸습니다. 더 좁은 범위로 다시 물어보면 이어서 정리할 수 있어요.)",
            "_recovered_from_truncated_json": True,
        }
    raise json.JSONDecodeError("Could not parse molder JSON", cleaned, 0)


def normalize_history_text(text: str) -> str:
    """Keep leaked JSON envelopes out of future model context."""
    cleaned = strip_json_code_fence(text)
    if cleaned.lstrip().startswith("{") and '"message"' in cleaned:
        recovered = extract_json_string_field(cleaned, "message")
        if recovered:
            return recovered
    return text


@app.post("/api/mold")
def mold_harness(
    prompt: str = Body(..., embed=True),
    context: str = Body("", embed=True),
    history: Optional[list] = Body(None, embed=True),
    editing_file_name: Optional[str] = Body(None, embed=True),
    editing_file_content: Optional[str] = Body(None, embed=True),
):
    """
    Chat Molder: Conversational AI assistant for harness management.
    Supports both Q&A (CHAT mode) and harness modification (CREATE/UPDATE mode).
    """
    raw = ""
    try:
        client, model_name = get_llm_client()

        # Build context from current harness state
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()

        context_str = build_molder_context(items, context)

        if editing_file_name and editing_file_content:
            context_str += f"\n\n[USER IS CURRENTLY EDITING FILE]\nFile Name: {editing_file_name}\nContent Preview:\n{editing_file_content[:5000]}"

        search_context = ""
        if should_auto_web_search(prompt):
            search_context = web_search_context(prompt)
            context_str += f"\n\n{search_context}"

        # Build message history for multi-turn conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": MOLDER_SYSTEM_PROMPT},
            {"role": "system", "content": HERMES_REFERENCE_CONTEXT},
        ]

        # Add conversation history
        for msg in (history or [])[-10:]:  # Keep last 10 messages for context
            role = msg.get("role", "user")
            text = normalize_history_text(msg.get("text", ""))
            if role == "user":
                messages.append({"role": "user", "content": f"# Historical User Turn\n{text}"})
            else:
                messages.append({"role": "assistant", "content": f"# Historical Assistant Turn\n{text}"})

        messages.append({
            "role": "user",
            "content": (
                f"{context_str}\n\n"
                "# Current User Request\n"
                f"{prompt}\n\n"
                "Answer this current request directly. Use the history only to resolve references."
            ),
        })

        response = client.chat.completions.create(
            model=model_name,
            messages=cast(Any, messages),
            temperature=0.7,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content or ""
        result = parse_molder_json(raw)

        # Handle CHAT mode — just return the message
        action = result.get("action", "CHAT")
        if action == "CHAT" or (action not in ("CREATE_SKILL", "UPDATE_SKILL", "UPDATE_CONFIG", "ADD_MCP") and not result.get("content")):
            return {
                "status": "success",
                "action": "CHAT",
                "name": "",
                "message": result.get("message", raw),
                "content": "",
                "diff": "",
                "diff_summary": "",
                "web_search": bool(search_context),
            }

        result = validate_molder_result(result)

        # Build diff for modification actions
        diff_lines = []
        if result.get("content"):
            act = result.get("action", "CREATE_SKILL")
            name = result.get("name", "unknown")
            if "SKILL" in act:
                path = f"skills/{name}/SKILL.md"
            elif "MCP" in act:
                path = "config.yaml (mcp_servers section)"
            else:
                path = "config.yaml"

            diff_lines.append(f"+++ b/{path}")
            for line in result["content"].split("\n"):
                diff_lines.append(f"+{line}")

        return {
            "status": "success",
            "action": result.get("action", "SUGGESTION"),
            "name": result.get("name", ""),
            "description": result.get("description", ""),
            "message": result.get("message", ""),
            "content": result.get("content", ""),
            "diff": "\n".join(diff_lines),
            "diff_summary": result.get("diff_summary", ""),
            "web_search": bool(search_context),
        }

    except json.JSONDecodeError:
        fallback_msg = "응답 형식을 정리하지 못했습니다. 질문 범위를 조금 좁혀서 다시 말씀해주세요."
        return {
            "status": "success",
            "action": "CHAT",
            "name": "",
            "message": fallback_msg,
            "content": "",
            "diff": "",
            "diff_summary": "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {str(e)}")

def _resolve_hermes_path(path: Path) -> Path:
    """Resolve a user-supplied path and ensure it is contained by one of the allowed workspaces."""
    resolved = path.expanduser().resolve(strict=False)
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Access denied: outside allowed agent workspaces")


def _assert_within_hermes(path: Path) -> None:
    """Raise 403 if path resolves outside HERMES_HOME."""
    _resolve_hermes_path(path)


def _backup(path: Path) -> Optional[str]:
    """Copy existing file to .bak.{timestamp}. Returns backup path or None."""
    if not path.exists():
        return None
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + f".bak.{ts}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup)


@app.get("/api/read")
def read_file(path: str, allow_missing: bool = False, max_bytes: int = 0, tail: bool = False):
    """Read a harness file. Large log viewers can request a bounded tail."""
    target_path = _resolve_hermes_path(Path(path))
    if not target_path.exists():
        if allow_missing:
            return {"content": "", "path": str(target_path), "missing": True}
        raise HTTPException(status_code=404, detail="File not found")
    try:
        size = target_path.stat().st_size
        if max_bytes and max_bytes > 0 and size > max_bytes:
            with target_path.open("rb") as f:
                if tail:
                    f.seek(max(0, size - max_bytes))
                chunk = f.read(max_bytes)
            content = chunk.decode("utf-8", errors="replace")
            if tail:
                content = f"[Showing last {len(chunk):,} of {size:,} bytes]\n\n{content}"
            else:
                content = f"{content}\n\n[Truncated after {len(chunk):,} of {size:,} bytes]"
            return {
                "content": content,
                "path": str(target_path),
                "truncated": True,
                "tail": tail,
                "size_bytes": size,
                "bytes_read": len(chunk),
            }
        return {
            "content": target_path.read_text(encoding="utf-8", errors="replace"),
            "path": str(target_path),
            "truncated": False,
            "size_bytes": size,
            "bytes_read": size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/save")
def save_item(
    path: str = Body(...),
    content: str = Body(...),
    commit_message: str = Body(""),
):
    """Save a harness item. Auto-backs up and git-commits if HERMES_HOME is a git repo."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode (HARNESS_READONLY=1). Set HARNESS_READONLY=0 to enable writes.")

    target_path = _resolve_hermes_path(Path(path))

    try:
        backup_path = _backup(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        git_result = None
        workspace = _get_workspace_for_path(target_path)
        if _is_git_repo(workspace):
            rel = target_path.relative_to(workspace)
            msg = commit_message.strip() or f"harness-studio: save {rel}"
            git_result = _git_commit_file(target_path, msg)

        log_audit_event("user", "save", str(target_path), f"Git status: {bool(git_result)}")

        return {
            "status": "saved",
            "path": str(target_path),
            "backup": backup_path,
            "git": git_result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rollback")
def rollback_item(path: str = Body(...)):
    """Restore the most recent .bak.* backup of a file."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    target_path = _resolve_hermes_path(Path(path))

    backups = sorted(
        target_path.parent.glob(target_path.name + ".bak.*"),
        reverse=True,
    )
    if not backups:
        raise HTTPException(status_code=404, detail="No backup found for this file")

    latest = backups[0]
    try:
        target_path.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
        latest.unlink()
        log_audit_event("user", "rollback", str(target_path), f"Backup used: {latest}")
        return {"status": "rolled_back", "from_backup": str(latest), "remaining_backups": len(backups) - 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/env")
def get_env(workspace: str = None):
    """Return current environment info for UI badge."""
    if workspace:
        ws_path = Path(workspace).expanduser().resolve()
    else:
        ws_path = HERMES_HOME
    is_git = _is_git_repo(ws_path)
    return {
        "hermes_home": str(HERMES_HOME),
        "is_sandbox": HERMES_HOME.name == "sandbox",
        "is_readonly": HARNESS_READONLY,
        "is_git_repo": is_git,
        "git_branch": _git_current_branch(ws_path) if is_git else None,
        "git_commit_count": _git_commit_count(ws_path) if is_git else None,
    }


# --- Git API ---

from pydantic import BaseModel
class GitInitRequest(BaseModel):
    workspace: str

@app.post("/api/git/init")
def git_init(req: dict = Body(default={})):
    """Initialize a git repo in workspace and create an initial commit."""
    workspace_str = req.get("workspace")
    if not workspace_str:
        ws_path = HERMES_HOME
    else:
        ws_path = Path(workspace_str).expanduser().resolve()

    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")
    if _is_git_repo(ws_path):
        return {"status": "already_git_repo", "branch": _git_current_branch(ws_path)}

    try:
        subprocess.run(["git", "init"], cwd=str(ws_path), check=True, capture_output=True)

        # .gitignore: exclude backup sidecar files and secrets
        _ensure_harness_gitignore(ws_path)

        subprocess.run(["git", "add", "-A"], cwd=str(ws_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "harness-studio: initial commit"],
            cwd=str(ws_path),
            check=True,
            capture_output=True,
        )
        short_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ws_path),
            capture_output=True,
            text=True,
        ).stdout.strip()
        log_audit_event("user", "git_init", str(ws_path), f"Git repo initialized. Initial commit: {short_hash}")
        return {"status": "initialized", "initial_commit": short_hash, "branch": _git_current_branch(ws_path)}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.decode() if e.stderr else str(e))


@app.get("/api/git/log")
def git_log(path: Optional[str] = None, limit: int = 30, workspace: Optional[str] = None):
    """Return git commit history, optionally filtered to a specific file."""
    if path:
        ws_path = _get_workspace_for_path(Path(path))
    elif workspace:
        ws_path = Path(workspace).expanduser().resolve()
    else:
        ws_path = HERMES_HOME

    if not _is_git_repo(ws_path):
        return {"is_git_repo": False, "commits": []}

    cmd = [
        "git", "log",
        f"--max-count={limit}",
        "--pretty=format:%H|%h|%s|%ai|%an",
    ]
    if path:
        try:
            rel = _resolve_hermes_path(Path(path)).relative_to(ws_path)
            cmd += ["--", str(rel)]
        except ValueError:
            pass

    result = subprocess.run(cmd, cwd=str(ws_path), capture_output=True, text=True)
    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "message": parts[2],
                "date": parts[3],
                "author": parts[4],
            })
    return {"is_git_repo": True, "commits": commits}


@app.get("/api/git/diff")
def git_diff(commit_hash: str, path: Optional[str] = None, workspace: Optional[str] = None):
    """Return the diff introduced by a specific commit (optionally for one file)."""
    if path:
        ws_path = _get_workspace_for_path(Path(path))
    elif workspace:
        ws_path = Path(workspace).expanduser().resolve()
    else:
        ws_path = HERMES_HOME

    if not _is_git_repo(ws_path):
        return {"is_git_repo": False, "diff": ""}

    cmd = ["git", "show", "--stat", "--patch", commit_hash]
    if path:
        try:
            rel = _resolve_hermes_path(Path(path)).relative_to(ws_path)
            cmd += ["--", str(rel)]
        except ValueError:
            pass

    result = subprocess.run(cmd, cwd=str(ws_path), capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=404, detail=f"Commit not found: {commit_hash}")
    return {"diff": result.stdout}


@app.get("/api/git/audit")
def git_audit(workspace: Optional[str] = None) -> Dict[str, Any]:
    """Audit working-tree changes and return a risk assessment.

    Risk levels:
      high   — protected file touched, 10+ files changed, or deletions at scale
      medium — 5+ files changed, or any deletion
      low    — small focused changeset
      clean  — no uncommitted changes
    """
    import re as _re
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME

    if not _is_git_repo(ws_path):
        return {"is_git_repo": False, "changed_files": [], "stat": "", "warnings": [], "risk": "unknown", "file_count": 0}

    status_r = subprocess.run(["git", "status", "--porcelain"], cwd=str(ws_path), capture_output=True, text=True)
    stat_r   = subprocess.run(["git", "diff", "--stat", "HEAD"],   cwd=str(ws_path), capture_output=True, text=True)

    HIGH_RISK = [
        r".*\.lock$", r"package\.json$", r"package-lock\.json$", r"yarn\.lock$",
        r"poetry\.lock$", r"Pipfile\.lock$", r"Cargo\.lock$",
        r"pyproject\.toml$", r"setup\.py$", r"setup\.cfg$",
        r"requirements.*\.txt$", r"constraints.*\.txt$",
        r"Dockerfile.*$", r"docker-compose.*\.(yml|yaml)$",
        r"\.env$", r"\.env\..+", r".+\.env$",
        r"Makefile$", r"justfile$",
        r".+\.generated\..+", r".+_generated\..+",
        r"\.github/.+", r"\.circleci/.+",
    ]

    changed_files: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for line in status_r.stdout.splitlines():
        if len(line) < 4:
            continue
        code = line[:2].strip()
        path = line[3:].strip().split(" -> ")[-1]  # handle renames
        is_protected = any(_re.search(p, path) for p in HIGH_RISK)
        changed_files.append({"status": code, "path": path, "protected": is_protected})
        if is_protected:
            warnings.append(f"Protected file modified: {path}")

    file_count   = len(changed_files)
    has_protected = any(f["protected"] for f in changed_files)
    del_count    = sum(1 for f in changed_files if "D" in f["status"])

    if file_count > 10:
        warnings.append(f"Large changeset: {file_count} files modified")
    if del_count:
        warnings.append(f"{del_count} file(s) deleted")

    if has_protected or file_count > 10:
        risk = "high"
    elif file_count > 5 or del_count > 0:
        risk = "medium"
    elif file_count > 0:
        risk = "low"
    else:
        risk = "clean"

    return {
        "is_git_repo": True,
        "changed_files": changed_files,
        "stat": stat_r.stdout.strip(),
        "warnings": warnings,
        "risk": risk,
        "file_count": file_count,
    }


@app.post("/api/git/rollback")
def git_rollback(path: str = Body(...), commit_hash: str = Body(...)):
    """Restore a file to the state at a specific commit hash."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    target_path = _resolve_hermes_path(Path(path))
    ws_path = _get_workspace_for_path(target_path)

    try:
        rel = target_path.relative_to(ws_path)
    except ValueError:
        raise HTTPException(status_code=403, detail="File outside allowed workspaces")

    backup_path = _backup(target_path)

    result = subprocess.run(
        ["git", "checkout", commit_hash, "--", str(rel)],
        cwd=str(ws_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # restore from backup on failure
        if backup_path:
            target_path.write_text(Path(backup_path).read_text(encoding="utf-8"), encoding="utf-8")
        raise HTTPException(status_code=500, detail=result.stderr.strip())

    # commit the restoration so history stays linear
    _git_commit_file(target_path, f"harness-studio: rollback {rel} to {commit_hash[:7]}")

    log_audit_event("user", "git_rollback", str(target_path), f"Commit hash: {commit_hash}")

    return {"status": "restored", "to_commit": commit_hash, "backup": backup_path}


@app.post("/api/web/scrape")
async def web_scrape(url: str = Body(..., embed=True)):
    """
    Hybrid Web Context Scraper (Firecrawl -> Jina -> TLS -> Browser).
    Escalates through 4 phases until content is successfully extracted.
    """
    if not url:
        return {"status": "error", "message": "URL is required"}

    try:
        scraper = HybridScraper()
        result = await scraper.scrape(ScrapRequest(url=url))

        # Convert Pydantic result to dict for FastAPI response
        response = result.model_dump()

        # UI expectation mapping: if successful, status should be "ok"
        if result.status == PhaseStatus.SUCCESS:
            response["status"] = "ok"
            response["source"] = result.phase_used
        else:
            response["status"] = "error"
            response["message"] = "All scraping phases failed."

        return response
    except Exception as e:
        return {
            "status": "error",
            "message": f"Hybrid pipeline crash: {str(e)}",
            "url": url,
            "source": "hybrid",
        }


@app.get("/api/audit/logs")
def get_audit_logs(limit: int = 50):
    """Retrieve audit logs from the SQLite database."""
    if not DB_PATH.exists():
        return {"logs": []}
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT id, actor, action, target_path, details, created_at FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = c.fetchall()
        logs = [dict(r) for r in rows]
        conn.close()
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _split_skill_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise HTTPException(status_code=400, detail="No frontmatter found in content")
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frontmatter YAML: {e}")
    if not isinstance(frontmatter, dict):
        raise HTTPException(status_code=400, detail="Frontmatter must be a YAML mapping")
    return frontmatter, content[match.end():]


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = re.split(r"[,;\n]+", value) if any(sep in value for sep in [",", ";", "\n"]) else value.split()
    else:
        raw = [value]
    return [str(v).strip() for v in raw if str(v).strip()]


def _slugify_skill_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return slug or "converted-skill"


def _tool_name_for_hermes(value: str) -> str:
    base = re.sub(r"\(.*\)$", "", value.strip()).strip()
    lower = base.lower()
    mapping = {
        "read": "read",
        "write": "write",
        "edit": "edit",
        "grep": "grep",
        "glob": "glob",
        "bash": "bash",
        "webfetch": "web_fetch",
        "websearch": "web_search",
    }
    return mapping.get(lower, base)


def _convert_skill_content(
    content: str,
    target: str,
    source_agent: Optional[str] = None,
    source_path: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """Convert SKILL.md frontmatter between Hermes and Claude Code formats."""
    if not content:
        raise HTTPException(status_code=400, detail="Content is empty")

    frontmatter, body = _split_skill_frontmatter(content)
    metadata = frontmatter.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    hermes_meta = metadata.get("hermes", {})
    hermes_meta = hermes_meta if isinstance(hermes_meta, dict) else {}

    name = str(frontmatter.get("name") or "converted-skill")
    description = frontmatter.get("description", "")
    if target == "claude":
        new_fm: Dict[str, Any] = {
            "name": name,
            "description": description,
            "tags": hermes_meta.get("tags", []),
            "category": hermes_meta.get("category", metadata.get("category", "general")),
        }
        for key, value in frontmatter.items():
            if key not in ("name", "description", "metadata"):
                new_fm[key] = value
    elif target == "hermes":
        category = (
            hermes_meta.get("category")
            or metadata.get("category")
            or frontmatter.get("category")
            or "converted"
        )
        tags = (
            hermes_meta.get("tags")
            or metadata.get("tags")
            or frontmatter.get("tags")
            or ["converted"]
        )
        allowed_tools = _listify(frontmatter.get("allowed-tools") or frontmatter.get("allowed_tools"))
        requires_tools = _listify(hermes_meta.get("requires_tools"))
        for tool in allowed_tools:
            mapped = _tool_name_for_hermes(tool)
            if mapped and mapped not in requires_tools:
                requires_tools.append(mapped)

        new_hermes_meta: Dict[str, Any] = {
            "tags": _listify(tags),
            "category": str(category),
        }
        if requires_tools:
            new_hermes_meta["requires_tools"] = requires_tools
        related = hermes_meta.get("related_skills") or metadata.get("related-skills") or metadata.get("related_skills")
        if related:
            new_hermes_meta["related_skills"] = _listify(related)
        if source_agent or source_path:
            new_hermes_meta["converted_from"] = {
                "agent": source_agent or "unknown",
                "source_path": source_path,
                "converted_at": datetime.now(timezone.utc).isoformat(),
            }

        new_fm = {
            "name": name,
            "description": description,
            "metadata": {"hermes": new_hermes_meta},
        }
        version = frontmatter.get("version") or metadata.get("version")
        if version:
            new_fm["version"] = version
        platforms = frontmatter.get("platforms")
        if platforms:
            new_fm["platforms"] = platforms
        for key in ("license", "triggers", "progressive_disclosure"):
            if key in frontmatter:
                new_fm[key] = frontmatter[key]
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported target format: {target}")

    new_fm_str = yaml.safe_dump(new_fm, sort_keys=False, allow_unicode=True)
    return f"---\n{new_fm_str}---\n{body}", new_fm


@app.post("/api/convert/skill")
def convert_skill(
    content: str = Body(..., embed=True),
    target: str = Body(..., embed=True), # 'hermes' or 'claude'
):
    """Convert SKILL.md frontmatter between Hermes and Claude Code formats."""
    new_content, _ = _convert_skill_content(content, target)
    return {"content": new_content, "target": target}


@app.post("/api/convert/skill/inject")
def inject_converted_skill(payload: dict):
    """Convert a source SKILL.md and inject it into a Hermes skills directory."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    source_path = payload.get("source_path")
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path required")

    src = _resolve_hermes_path(Path(source_path))
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=404, detail=f"Not found: {source_path}")

    target_ws = _resolve_workspace_path(payload.get("target_workspace") or str(Path.home() / ".hermes"))
    if target_ws.name != ".hermes":
        raise HTTPException(status_code=400, detail="target_workspace must be a Hermes workspace")
    overwrite = bool(payload.get("overwrite", False))
    dry_run = bool(payload.get("dry_run", False))
    source_agent = payload.get("source_agent") or "claude-code"

    content = src.read_text(encoding="utf-8", errors="replace")
    converted, frontmatter = _convert_skill_content(
        content,
        "hermes",
        source_agent=source_agent,
        source_path=str(src),
    )
    skill_name = _slugify_skill_name(str(frontmatter.get("name") or src.parent.name))
    dest_dir = target_ws / "skills" / skill_name
    dest_file = dest_dir / "SKILL.md"

    if dry_run:
        return {
            "status": "dry_run",
            "skill_name": skill_name,
            "source": str(src),
            "path": str(dest_file),
            "would_overwrite": dest_file.exists(),
            "content": converted,
        }

    if dest_file.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Target Hermes skill already exists",
                "path": str(dest_file),
                "skill_name": skill_name,
            },
        )

    backup_path = _backup(dest_file) if dest_file.exists() else None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(converted, encoding="utf-8")

    copied_assets = []
    for dirname in ("references", "templates", "scripts", "modules", "assets"):
        src_asset = src.parent / dirname
        if not src_asset.exists() or not src_asset.is_dir():
            continue
        dest_asset = dest_dir / dirname
        if dest_asset.exists():
            if not overwrite:
                continue
            shutil.rmtree(dest_asset)
        shutil.copytree(src_asset, dest_asset)
        copied_assets.append(dirname)

    git_result = None
    if _is_git_repo(target_ws):
        rel_dir = dest_dir.relative_to(target_ws)
        add = subprocess.run(
            ["git", "add", str(rel_dir)],
            cwd=str(target_ws),
            capture_output=True,
            text=True,
        )
        if add.returncode == 0:
            commit = subprocess.run(
                ["git", "commit", "-m", f"harness-studio: inject skill {skill_name}"],
                cwd=str(target_ws),
                capture_output=True,
                text=True,
            )
            git_result = {
                "committed": commit.returncode == 0,
                "stdout": commit.stdout.strip(),
                "stderr": commit.stderr.strip(),
            }
        else:
            git_result = {"committed": False, "error": add.stderr.strip()}

    log_audit_event("user", "inject_skill", str(dest_file), f"Source: {src}; assets: {copied_assets}")
    return {
        "status": "injected",
        "skill_name": skill_name,
        "source": str(src),
        "path": str(dest_file),
        "backup": backup_path,
        "copied_assets": copied_assets,
        "git": git_result,
    }


@app.get("/api/sessions/messages")
def get_session_messages(session_id: str, workspace: str = None):
    """Fetch messages for a specific session from state.db."""
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME.resolve()
    state_db = ws_path / "state.db"
    if not state_db.exists():
        raise HTTPException(status_code=404, detail="state.db not found")
    try:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        sess = conn.execute(
            "SELECT id, title, model, started_at, ended_at, message_count, estimated_cost_usd FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        msgs = conn.execute(
            "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id LIMIT 100",
            (session_id,),
        ).fetchall()
        conn.close()
        return {
            "session": dict(sess),
            "messages": [dict(m) for m in msgs],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/list")
def get_sessions_list(workspace: str = None, limit: int = 50, offset: int = 0):
    """state.db에서 세션 목록을 페이지네이션으로 반환."""
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME.resolve()
    state_db = ws_path / "state.db"
    if not state_db.exists():
        raise HTTPException(status_code=404, detail="state.db not found")
    try:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE title IS NOT NULL AND title != ''"
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT id, title, model, started_at, message_count, estimated_cost_usd
               FROM sessions WHERE title IS NOT NULL AND title != ''
               ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        conn.close()
        return {
            "sessions": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/usage/stats")
def usage_stats(workspace: str = None, days: int = 30):
    """Return Skill/Subagent invocation telemetry for a workspace."""
    try:
        _, ws_path, _ = _scanner_for_workspace(workspace)
        from usage_tracker import get_usage_summary

        return get_usage_summary(str(ws_path), days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations")
def recommendations(workspace: str = None, days: int = 30):
    """Return usage-aware cleanup recommendations for a workspace."""
    try:
        from recommender import build_recommendations
        from usage_tracker import get_usage_summary

        items, ws_path, scanner_name = _scan_items_for_workspace(workspace)
        usage = get_usage_summary(str(ws_path), days)
        recs = build_recommendations(items, usage)
        category_counts: Dict[str, int] = {}
        for rec in recs:
            category = rec.get("category", "UNKNOWN")
            category_counts[category] = category_counts.get(category, 0) + 1
        return {
            "workspace": str(ws_path),
            "scanner": scanner_name,
            "recommendations": recs,
            "category_counts": category_counts,
            "usage": usage,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/actions/archive")
def archive_item(payload: dict):
    """Archive (move) a harness item to a dated backup folder."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    source_path = payload.get("source_path")
    workspace = payload.get("workspace")

    if not source_path:
        raise HTTPException(status_code=400, detail="source_path required")

    src = Path(source_path).expanduser().resolve()
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {source_path}")

    ws_root = Path(workspace).expanduser().resolve() if workspace else src.parent
    ws_name = ws_root.name  # e.g. ".claude", ".codex"
    archive_root = Path.home() / f"{ws_name}-archive" / datetime.now().strftime("%Y%m%d")

    try:
        rel = src.relative_to(ws_root)
        dest = archive_root / rel
    except ValueError:
        dest = archive_root / src.name

    dest.parent.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        shutil.copytree(str(src), str(dest))
        shutil.rmtree(str(src))
    else:
        shutil.move(str(src), str(dest))

    log_audit_event("user", "archive", str(src), f"Archived to {dest}")
    return {"archived_to": str(dest), "original": str(src)}


@app.post("/api/actions/copy")
def copy_item_to_workspace(payload: dict):
    """Copy a harness item to another workspace."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    source_path = payload.get("source_path")
    target_workspace = payload.get("target_workspace")
    target_subdir = payload.get("target_subdir", "")

    if not source_path or not target_workspace:
        raise HTTPException(status_code=400, detail="source_path and target_workspace required")

    src = Path(source_path).expanduser().resolve()
    target_ws = Path(target_workspace).expanduser().resolve()

    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {source_path}")
    if not target_ws.exists():
        raise HTTPException(status_code=404, detail=f"Target workspace not found: {target_workspace}")

    dest_dir = (target_ws / target_subdir) if target_subdir else target_ws
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        dest = dest_dir / f"{src.stem}_copy{src.suffix}"

    if src.is_dir():
        shutil.copytree(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest))

    log_audit_event("user", "copy", str(src), f"Copied to {dest}")
    return {"copied_to": str(dest), "original": str(src)}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8766, reload=True)
