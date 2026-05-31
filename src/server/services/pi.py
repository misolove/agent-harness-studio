import os
import json
import shutil
import uuid
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .config import HERMES_HOME, resolve_workspace_path, get_allowed_roots
from .git import is_git_repo, capture_git_audit, git_commit_file

PI_AGENT_DIR = Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi" / "agent"))).expanduser()
PI_ENV_KEYS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY",
    "MISTRAL_API_KEY", "XAI_API_KEY", "HUGGINGFACE_API_KEY",
    "OLLAMA_HOST",
]

RUNS_BASE_DIR = HERMES_HOME / "harness-studio-runs" / "pi"
PI_SESSIONS_DIR = RUNS_BASE_DIR / "sessions"
READONLY_TOOLS = "read,grep,find,ls"
MOLD_TOOLS = "read,grep,find,ls,web_search"

_PI_ENV_CANDIDATES: List[Path] = [
    Path.home() / "hermes-memory-pointer-architecture" / ".env",
    HERMES_HOME / ".env",
    Path.home() / ".pi" / ".env",
]

_PI_RUNS: Dict[str, Dict[str, Any]] = {}
_PI_RUN_LOCK = threading.Lock()


def _get_pi_subprocess_env() -> Dict[str, str]:
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
                    if key and key not in env:
                        env[key] = val
            except Exception:
                pass
            break
    return env


def _pi_read_settings() -> Dict[str, Any]:
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


def pi_status(workspace: Optional[str] = None) -> Dict[str, Any]:
    ws_path = resolve_workspace_path(workspace)
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
            "is_git_repo": is_git_repo(ws_path),
            "branch": git_current_branch(ws_path) if is_git_repo(ws_path) else None,
            "commit_count": git_commit_count(ws_path) if is_git_repo(ws_path) else None,
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


def _run_pi_subprocess(run_id: str, cmd: List[str], run_dir: Path) -> None:
    stdout_log = run_dir / "stdout.log"
    stderr_log = run_dir / "stderr.log"
    events_log = run_dir / "events.jsonl"
    meta_path = run_dir / "meta.json"
    proc: Optional[subprocess.Popen] = None

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

        with open(stdout_log, "w", encoding="utf-8") as out_f:
            assert proc.stdout is not None
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

        ws_path = Path(_PI_RUNS.get(run_id, {}).get("workspace", str(HERMES_HOME)))
        post_audit = capture_git_audit(ws_path)
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


def get_pi_runs():
    return _PI_RUNS


def get_pi_run_lock():
    return _PI_RUN_LOCK


# Need git functions available in this module
from .git import git_current_branch, git_commit_count  # noqa: E402
