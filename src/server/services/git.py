import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import get_workspace_for_path, get_allowed_roots


def is_git_repo(workspace: Path) -> bool:
    r = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(workspace),
        capture_output=True,
    )
    return r.returncode == 0


def git_commit_file(file_path: Path, message: str) -> Dict[str, Any]:
    workspace = get_workspace_for_path(file_path)
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


def git_current_branch(workspace: Path) -> Optional[str]:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def git_commit_count(workspace: Path) -> Optional[int]:
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


def capture_git_audit(ws_path: Path) -> Dict[str, Any]:
    if not is_git_repo(ws_path):
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
    from datetime import datetime, timezone
    return {
        "is_git_repo": True,
        "changed_files": changed,
        "file_count": len(changed),
        "stat": stat_r.stdout[:3000],
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
