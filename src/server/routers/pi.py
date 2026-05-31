import os
import json
import shutil
import uuid
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Body

from services.config import HERMES_HOME, resolve_workspace_path
from services.pi import (
    pi_status, _run_pi_subprocess, get_pi_runs, get_pi_run_lock,
    READONLY_TOOLS, MOLD_TOOLS, PI_SESSIONS_DIR, RUNS_BASE_DIR,
)
from services.git import capture_git_audit
from routers.scan import build_response
from scanner.hermes_scanner import HermesScanner

router = APIRouter()


@router.get("/api/agent-runners")
def get_agent_runners(workspace: Optional[str] = None):
    pi = pi_status(workspace)
    return {
        "runners": [pi],
        "summary": {
            "total": 1,
            "ready": 1 if pi["installed"] else 0,
            "detect_only": 1,
        },
    }


@router.get("/api/pi/status")
def get_pi_status(workspace: Optional[str] = None):
    return pi_status(workspace)


@router.post("/api/pi/preview")
def preview_pi_run(req: Dict[str, Any] = Body(default={})):
    ws_path = resolve_workspace_path(req.get("workspace"))
    prompt = str(req.get("prompt") or "").strip()
    mode = str(req.get("mode") or "rpc").strip().lower()
    if mode not in {"rpc", "json", "print"}:
        raise HTTPException(status_code=400, detail="mode must be one of: rpc, json, print")

    status = pi_status(str(ws_path))
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


@router.post("/api/pi/runs")
def create_pi_run(req: Dict[str, Any] = Body(default={})):
    ws_path  = resolve_workspace_path(req.get("workspace"))
    prompt   = str(req.get("prompt") or "").strip()
    mode_req = str(req.get("mode") or "read_only").strip().lower()

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if mode_req != "read_only":
        raise HTTPException(
            status_code=400,
            detail="Only read_only mode is currently supported. Gated write mode is not yet enabled.",
        )

    pi = pi_status(str(ws_path))
    if not pi["installed"]:
        raise HTTPException(status_code=404, detail="pi CLI not found on PATH")

    run_id  = uuid.uuid4().hex[:12]
    run_dir = RUNS_BASE_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    pre_audit = capture_git_audit(ws_path)
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

    _PI_RUNS = get_pi_runs()
    _PI_RUN_LOCK = get_pi_run_lock()

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


@router.get("/api/pi/runs/{run_id}")
def get_pi_run(run_id: str):
    _PI_RUNS = get_pi_runs()
    _PI_RUN_LOCK = get_pi_run_lock()

    with _PI_RUN_LOCK:
        meta = _PI_RUNS.get(run_id)

    if meta is None:
        meta_path = RUNS_BASE_DIR / run_id / "meta.json"
        if not meta_path.exists():
            raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return meta


@router.get("/api/pi/runs/{run_id}/log")
def get_pi_run_log(run_id: str, tail: int = 200):
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


@router.post("/api/pi/runs/{run_id}/stop")
def stop_pi_run(run_id: str):
    _PI_RUNS = get_pi_runs()
    _PI_RUN_LOCK = get_pi_run_lock()

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


@router.post("/api/pi/mold")
def pi_mold_chat(req: Dict[str, Any] = Body(default={})):
    ws_path        = resolve_workspace_path(req.get("workspace"))
    prompt         = str(req.get("prompt") or "").strip()
    context        = str(req.get("context") or "")
    editing_name   = req.get("editing_file_name") or ""
    editing_content = req.get("editing_file_content") or ""
    session_file   = req.get("session_file") or None

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    pi = pi_status(str(ws_path))
    if not pi["installed"]:
        raise HTTPException(status_code=404, detail="pi CLI not found on PATH")

    PI_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if session_file:
        session_path = Path(session_file)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        session_path = PI_SESSIONS_DIR / f"mold-{ts}-{uuid.uuid4().hex[:6]}.jsonl"

    is_new_session = not session_path.exists()

    if is_new_session:
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()
        context_str = build_response(items).get("summary", {})

        from routers.mold import build_molder_context
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

    pre_audit = capture_git_audit(ws_path)
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

    _PI_RUNS = get_pi_runs()
    _PI_RUN_LOCK = get_pi_run_lock()

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
