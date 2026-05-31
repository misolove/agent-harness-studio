import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.config import (
    HARNESS_READONLY, resolve_hermes_path, backup_file,
    log_audit_event, get_workspace_for_path,
)
from services.git import is_git_repo, git_commit_file

router = APIRouter()

VALID_SECTIONS = ("mcp_servers", "hooks")


class ToggleRequest(BaseModel):
    path: str
    section: str
    name: str
    enabled: bool


@router.post("/api/toggle")
async def toggle_item(req: ToggleRequest):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode (HARNESS_READONLY=1)")

    if req.section not in VALID_SECTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid section '{req.section}'. Must be one of: {VALID_SECTIONS}",
        )

    target_path = resolve_hermes_path(Path(req.path))

    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Config file not found: {target_path}")

    try:
        raw = target_path.read_text(encoding="utf-8")
        config = yaml.safe_load(raw) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse YAML: {e}")

    section_data = config.get(req.section)
    if not section_data or not isinstance(section_data, dict):
        raise HTTPException(
            status_code=404,
            detail=f"Section '{req.section}' not found in {target_path.name}",
        )

    if req.name not in section_data:
        raise HTTPException(
            status_code=404,
            detail=f"'{req.name}' not found in {req.section}",
        )

    entry = section_data[req.name]
    if not isinstance(entry, dict):
        raise HTTPException(
            status_code=422,
            detail=f"'{req.name}' in {req.section} is not a mapping and cannot be toggled",
        )

    entry["enabled"] = req.enabled

    backup_path = backup_file(target_path)

    try:
        target_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")

    git_result = None
    workspace = get_workspace_for_path(target_path)
    if is_git_repo(workspace):
        rel = target_path.relative_to(workspace)
        git_result = git_commit_file(
            target_path,
            f"harness-studio: toggle {req.section}.{req.name} enabled={req.enabled}",
        )

    log_audit_event(
        "user", "toggle", str(target_path),
        f"{req.section}.{req.name} enabled={req.enabled}",
    )

    return {
        "status": "toggled",
        "section": req.section,
        "name": req.name,
        "enabled": req.enabled,
        "path": str(target_path),
        "backup": backup_path,
        "git": git_result,
    }
