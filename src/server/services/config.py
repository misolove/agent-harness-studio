import os
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_HERMES_HOME = Path.home() / ".hermes"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(DEFAULT_HERMES_HOME)))
HARNESS_READONLY = os.environ.get("HARNESS_READONLY", "").lower() in ("1", "true", "yes")
DB_PATH = HERMES_HOME / "harness_studio.db"


def get_allowed_roots():
    return [
        PROJECT_ROOT.resolve(),
        HERMES_HOME.resolve(),
        (Path.home() / ".claude").resolve(),
        (Path.home() / ".cursor").resolve(),
        (Path.home() / ".codex").resolve(),
        (Path.home() / ".openclaw").resolve(),
        (Path.home() / ".gemini").resolve(),
    ]


def get_workspace_for_path(path: Path) -> Path:
    from fastapi import HTTPException
    resolved = path.expanduser().resolve(strict=False)
    for root in get_allowed_roots():
        try:
            resolved.relative_to(root)
            return root
        except ValueError:
            continue
    return HERMES_HOME


def resolve_workspace_path(workspace: Optional[str] = None) -> Path:
    from fastapi import HTTPException
    if not workspace:
        return HERMES_HOME.resolve()
    resolved = Path(workspace).expanduser().resolve(strict=False)
    for root in get_allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Access denied: outside allowed agent workspaces")


def resolve_hermes_path(path: Path) -> Path:
    from fastapi import HTTPException
    resolved = path.expanduser().resolve(strict=False)
    for root in get_allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="Access denied: outside allowed agent workspaces")


def ensure_harness_gitignore(workspace: Optional[Path] = None) -> None:
    if HARNESS_READONLY:
        return
    target_workspace = workspace or HERMES_HOME
    gitignore = target_workspace / ".gitignore"
    wanted = ["*.bak.*", ".env", "*.log", "harness_studio.db*"]
    try:
        existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
        merged = list(existing)
        changed = False
        for pattern in wanted:
            if pattern not in existing:
                merged.append(pattern)
                changed = True
        if changed:
            gitignore.parent.mkdir(parents=True, exist_ok=True)
            gitignore.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    except Exception as e:
        print(f"Failed to update .gitignore for Harness Studio state: {e}")


def init_db():
    if HARNESS_READONLY:
        return
    try:
        HERMES_HOME.mkdir(parents=True, exist_ok=True)
        ensure_harness_gitignore()
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT,
                action TEXT,
                target_path TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to initialize SQLite DB: {e}")


def log_audit_event(actor: str, action: str, target_path: str, details: str = ""):
    if HARNESS_READONLY:
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_events (actor, action, target_path, details) VALUES (?, ?, ?, ?)",
            (actor, action, target_path, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to log audit event: {e}")


def backup_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + f".bak.{ts}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup)
