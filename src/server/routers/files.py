from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Body

from services.config import (
    HERMES_HOME, HARNESS_READONLY, DB_PATH,
    resolve_hermes_path, backup_file, log_audit_event,
    get_workspace_for_path,
)
from services.git import is_git_repo, git_commit_file

router = APIRouter()


@router.get("/api/read")
def read_file(path: str, allow_missing: bool = False, max_bytes: int = 0, tail: bool = False):
    target_path = resolve_hermes_path(Path(path))
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


@router.post("/api/save")
def save_item(
    path: str = Body(...),
    content: str = Body(...),
    commit_message: str = Body(""),
):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode (HARNESS_READONLY=1). Set HARNESS_READONLY=0 to enable writes.")

    target_path = resolve_hermes_path(Path(path))

    try:
        backup_path = backup_file(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        git_result = None
        workspace = get_workspace_for_path(target_path)
        if is_git_repo(workspace):
            rel = target_path.relative_to(workspace)
            msg = commit_message.strip() or f"harness-studio: save {rel}"
            git_result = git_commit_file(target_path, msg)

        log_audit_event("user", "save", str(target_path), f"Git status: {bool(git_result)}")

        return {
            "status": "saved",
            "path": str(target_path),
            "backup": backup_path,
            "git": git_result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rollback")
def rollback_item(path: str = Body(...)):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    target_path = resolve_hermes_path(Path(path))

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


@router.get("/health")
def health():
    return {"status": "ok"}
