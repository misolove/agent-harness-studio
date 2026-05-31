import sqlite3

from fastapi import APIRouter, HTTPException

from services.config import DB_PATH

router = APIRouter()


@router.get("/api/audit/logs")
def get_audit_logs(limit: int = 50):
    if not DB_PATH.exists():
        return {"logs": []}
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT id, actor, action, target_path, details, created_at FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = c.fetchall()
        logs = [dict(r) for r in rows]
        conn.close()
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
