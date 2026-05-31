import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from services.config import HERMES_HOME

router = APIRouter()


@router.get("/api/sessions/messages")
def get_session_messages(session_id: str, workspace: str = None):
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME.resolve()
    state_db = ws_path / "state.db"
    if not state_db.exists():
        raise HTTPException(status_code=404, detail="state.db not found")
    try:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        sess = conn.execute(
            "SELECT id, title, model, started_at, ended_at, message_count, estimated_cost_usd FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        msgs = conn.execute(
            "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id LIMIT 100",
            (session_id,),
        ).fetchall()
        conn.close()
        return {
            "session": dict(sess),
            "messages": [dict(m) for m in msgs],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/sessions/list")
def get_sessions_list(workspace: str = None, limit: int = 50, offset: int = 0):
    ws_path = Path(workspace).expanduser().resolve() if workspace else HERMES_HOME.resolve()
    state_db = ws_path / "state.db"
    if not state_db.exists():
        raise HTTPException(status_code=404, detail="state.db not found")
    try:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE title IS NOT NULL AND title != ''"
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT id, title, model, started_at, message_count, estimated_cost_usd
               FROM sessions WHERE title IS NOT NULL AND title != ''
               ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        conn.close()
        return {
            "sessions": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
