from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from services.config import HERMES_HOME, HARNESS_READONLY
from services.git import is_git_repo, git_current_branch, git_commit_count
from services.llm import detect_hermes_auth_path, detect_context_length

router = APIRouter()


@router.get("/api/env")
def get_env(workspace: str = None):
    if workspace:
        ws_path = Path(workspace).expanduser().resolve()
    else:
        ws_path = HERMES_HOME
    is_git = is_git_repo(ws_path)
    auth_status = detect_hermes_auth_path(ws_path)
    ctx = detect_context_length(ws_path)
    return {
        "hermes_home": str(HERMES_HOME),
        "is_sandbox": HERMES_HOME.name == "sandbox",
        "is_readonly": HARNESS_READONLY,
        "is_git_repo": is_git,
        "git_branch": git_current_branch(ws_path) if is_git else None,
        "git_commit_count": git_commit_count(ws_path) if is_git else None,
        "auth_path": auth_status["auth_path"],
        "auth_label": auth_status["auth_label"],
        "auth_detail": auth_status["auth_detail"],
        "aux_models_missing": auth_status["aux_models_missing"],
        "context_length": ctx["context_length"],
        "context_length_source": ctx["source"],
    }
