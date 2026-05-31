import shutil
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from services.config import HARNESS_READONLY, log_audit_event
from routers.scan import _scanner_for_workspace, _scan_items_for_workspace

router = APIRouter()


@router.post("/api/actions/archive")
def archive_item(payload: dict):
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    source_path = payload.get("source_path")
    workspace = payload.get("workspace")

    if not source_path:
        raise HTTPException(status_code=400, detail="source_path required")

    src = Path(source_path).expanduser().resolve()
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {source_path}")

    from datetime import datetime
    ws_root = Path(workspace).expanduser().resolve() if workspace else src.parent
    ws_name = ws_root.name
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


@router.post("/api/actions/copy")
def copy_item_to_workspace(payload: dict):
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


@router.get("/api/recommendations")
def recommendations(workspace: str = None, days: int = 30):
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


@router.get("/api/usage/stats")
def usage_stats(workspace: str = None, days: int = 30):
    try:
        _, ws_path, _ = _scanner_for_workspace(workspace)
        from usage_tracker import get_usage_summary

        return get_usage_summary(str(ws_path), days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
