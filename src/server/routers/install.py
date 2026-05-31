import re
import yaml
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.config import (
    HERMES_HOME, HARNESS_READONLY,
    resolve_workspace_path, backup_file, log_audit_event,
)
from services.git import is_git_repo, git_commit_file

router = APIRouter()

_MAX_CONTENT_SIZE = 2 * 1024 * 1024
_FETCH_TIMEOUT = 30


def _normalize_github_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host != "github.com":
        return url
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return url
    owner, repo = parts[0], parts[1]
    rest = "/".join(parts[2:])
    if rest == "" or rest == "blob" or rest.startswith("blob/"):
        path_after_blob = rest.removeprefix("blob/")
        if not path_after_blob:
            return url
        branch = "main"
        segs = path_after_blob.split("/")
        if segs and segs[0] in ("main", "master", "develop"):
            branch = segs[0]
            path_after_blob = "/".join(segs[1:])
        if path_after_blob:
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path_after_blob}"
    if rest == "" or rest == "tree" or rest.startswith("tree/"):
        path_after_tree = rest.removeprefix("tree/")
        if not path_after_tree:
            return url
        branch = "main"
        segs = path_after_tree.split("/")
        if segs and segs[0] in ("main", "master", "develop"):
            branch = segs[0]
            path_after_tree = "/".join(segs[1:])
        if path_after_tree:
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path_after_tree}/SKILL.md"
    return url


def _extract_skill_name(content: str) -> Optional[str]:
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    try:
        fm = yaml.safe_load(match.group(1))
    except Exception:
        return None
    if isinstance(fm, dict) and fm.get("name"):
        return str(fm["name"]).strip()
    return None


class InstallRequest(BaseModel):
    url: str
    target_workspace: str = ""
    name: str = ""
    dry_run: bool = False


@router.post("/api/install/skill")
async def install_skill(req: InstallRequest):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    parsed = urlparse(req.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must be http or https")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: no hostname")

    fetch_url = _normalize_github_url(req.url)

    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
        try:
            resp = await client.get(fetch_url)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Upstream returned {resp.status_code}")

    content = resp.text
    if len(content) > _MAX_CONTENT_SIZE:
        raise HTTPException(status_code=413, detail="Content exceeds 2 MB limit")

    skill_name = req.name.strip() if req.name.strip() else _extract_skill_name(content)
    if not skill_name:
        raise HTTPException(
            status_code=400,
            detail="Could not determine skill name from frontmatter. Provide 'name' in request.",
        )

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", skill_name.strip().lower()).strip("-._") or "installed-skill"

    target_ws = resolve_workspace_path(req.target_workspace or str(HERMES_HOME))
    dest_dir = target_ws / "skills" / slug
    dest_file = dest_dir / "SKILL.md"

    resolved = dest_file.resolve(strict=False)
    for root in [target_ws.resolve(), HERMES_HOME.resolve()]:
        try:
            resolved.relative_to(root)
            break
        except ValueError:
            continue
    else:
        raise HTTPException(status_code=403, detail="Target path is outside allowed roots")

    if req.dry_run:
        return {
            "status": "dry_run",
            "skill_name": skill_name,
            "slug": slug,
            "fetch_url": fetch_url,
            "path": str(dest_file),
            "would_overwrite": dest_file.exists(),
            "content_preview": content[:2000],
            "content_length": len(content),
        }

    bkup = backup_file(dest_file) if dest_file.exists() else None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(content, encoding="utf-8")

    git_result = None
    if is_git_repo(target_ws):
        git_result = git_commit_file(dest_file, f"harness-studio: install skill {slug}")

    log_audit_event("user", "install_skill", str(dest_file), f"URL: {req.url}")

    return {
        "status": "installed",
        "skill_name": skill_name,
        "slug": slug,
        "fetch_url": fetch_url,
        "path": str(dest_file),
        "backup": bkup,
        "git": git_result,
    }
