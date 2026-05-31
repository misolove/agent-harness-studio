import re
import subprocess
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, Body

from services.config import (
    HERMES_HOME, HARNESS_READONLY,
    resolve_hermes_path, get_workspace_for_path,
    ensure_harness_gitignore, log_audit_event, backup_file,
)
from services.git import (
    is_git_repo, git_commit_file, git_current_branch,
    capture_git_audit,
)

router = APIRouter()


@router.post("/api/git/init")
def git_init(req: dict = Body(default={})):
    workspace_str = req.get("workspace")
    if not workspace_str:
        ws_path = HERMES_HOME
    else:
        ws_path = Path(workspace_str).expanduser().resolve()

    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")
    if is_git_repo(ws_path):
        return {"status": "already_git_repo", "branch": git_current_branch(ws_path)}

    try:
        subprocess.run(["git", "init"], cwd=str(ws_path), check=True, capture_output=True)

        ensure_harness_gitignore(ws_path)

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
        return {"status": "initialized", "initial_commit": short_hash, "branch": git_current_branch(ws_path)}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.decode() if e.stderr else str(e))


@router.get("/api/git/log")
def git_log(path: Optional[str] = None, limit: int = 30, workspace: Optional[str] = None):
    if path:
        ws_path = get_workspace_for_path(Path(path))
    elif workspace:
        ws_path = Path(workspace).expanduser().resolve()
    else:
        ws_path = HERMES_HOME

    if not is_git_repo(ws_path):
        return {"is_git_repo": False, "commits": []}

    cmd = [
        "git", "log",
        f"--max-count={limit}",
        "--pretty=format:%H|%h|%s|%ai|%an",
    ]
    if path:
        try:
            rel = resolve_hermes_path(Path(path)).relative_to(ws_path)
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


@router.get("/api/git/diff")
def git_diff(commit_hash: str, path: Optional[str] = None, workspace: Optional[str] = None):
    if path:
        ws_path = get_workspace_for_path(Path(path))
    elif workspace:
        ws_path = Path(workspace).expanduser().resolve()
    else:
        ws_path = HERMES_HOME

    if not is_git_repo(ws_path):
        return {"is_git_repo": False, "diff": ""}

    cmd = ["git", "show", "--stat", "--patch", commit_hash]
    if path:
        try:
            rel = resolve_hermes_path(Path(path)).relative_to(ws_path)
            cmd += ["--", str(rel)]
        except ValueError:
            pass

    result = subprocess.run(cmd, cwd=str(ws_path), capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=404, detail=f"Commit not found: {commit_hash}")
    return {"diff": result.stdout}


@router.get("/api/git/audit")
def git_audit(workspace: Optional[str] = None) -> Dict[str, Any]:
    import re as _re
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME

    if not is_git_repo(ws_path):
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
        path = line[3:].strip().split(" -> ")[-1]
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


@router.post("/api/git/rollback")
def git_rollback(path: str = Body(...), commit_hash: str = Body(...)):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    target_path = resolve_hermes_path(Path(path))
    ws_path = get_workspace_for_path(target_path)

    try:
        rel = target_path.relative_to(ws_path)
    except ValueError:
        raise HTTPException(status_code=403, detail="File outside allowed workspaces")

    bkup = backup_file(target_path)

    result = subprocess.run(
        ["git", "checkout", commit_hash, "--", str(rel)],
        cwd=str(ws_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if bkup:
            target_path.write_text(Path(bkup).read_text(encoding="utf-8"), encoding="utf-8")
        raise HTTPException(status_code=500, detail=result.stderr.strip())

    git_commit_file(target_path, f"harness-studio: rollback {rel} to {commit_hash[:7]}")

    log_audit_event("user", "git_rollback", str(target_path), f"Commit hash: {commit_hash}")

    return {"status": "restored", "to_commit": commit_hash, "backup": bkup}
