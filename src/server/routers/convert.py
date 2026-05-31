import re
import shutil
import subprocess
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Body

from services.config import (
    HERMES_HOME, HARNESS_READONLY,
    resolve_hermes_path, resolve_workspace_path,
    backup_file, log_audit_event, get_workspace_for_path,
)
from services.git import is_git_repo

router = APIRouter()


def _split_skill_frontmatter(content: str) -> tuple:
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
) -> tuple:
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


@router.post("/api/convert/skill")
def convert_skill(
    content: str = Body(..., embed=True),
    target: str = Body(..., embed=True),
):
    new_content, _ = _convert_skill_content(content, target)
    return {"content": new_content, "target": target}


@router.post("/api/convert/skill/inject")
def inject_converted_skill(payload: dict):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    source_path = payload.get("source_path")
    if not source_path:
        raise HTTPException(status_code=400, detail="source_path required")

    src = resolve_hermes_path(Path(source_path))
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=404, detail=f"Not found: {source_path}")

    target_ws = resolve_workspace_path(payload.get("target_workspace") or str(Path.home() / ".hermes"))
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

    bkup = backup_file(dest_file) if dest_file.exists() else None
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
    if is_git_repo(target_ws):
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
        "backup": bkup,
        "copied_assets": copied_assets,
        "git": git_result,
    }
