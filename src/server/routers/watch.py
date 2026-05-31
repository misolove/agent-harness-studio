import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Set, Dict

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from services.config import resolve_workspace_path

router = APIRouter()

POLL_INTERVAL = 3.0
WATCHDOG_AVAILABLE = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent

    WATCHDOG_AVAILABLE = True
except ImportError:
    pass


def _build_snapshot(root: Path) -> Dict[str, float]:
    snapshot: Dict[str, float] = {}
    if not root.exists():
        return snapshot
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            full = Path(dirpath) / fname
            try:
                snapshot[str(full)] = full.stat().st_mtime
            except OSError:
                continue
    return snapshot


def _diff_snapshots(
    old: Dict[str, float], new: Dict[str, float]
) -> list[dict]:
    events: list[dict] = []
    old_keys: Set[str] = set(old.keys())
    new_keys: Set[str] = set(new.keys())

    for p in new_keys - old_keys:
        events.append({"event": "created", "path": p})

    for p in old_keys - new_keys:
        events.append({"event": "deleted", "path": p})

    for p in old_keys & new_keys:
        if old[p] != new[p]:
            events.append({"event": "modified", "path": p})

    return events


if WATCHDOG_AVAILABLE:

    class _WatchdogHandler(FileSystemEventHandler):
        def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
            super().__init__()
            self._queue = queue
            self._loop = loop

        def _push(self, event_type: str, src_path: str):
            evt = {"event": event_type, "path": src_path}
            self._loop.call_soon_threadsafe(self._queue.put_nowait, evt)

        def on_created(self, event: FileSystemEvent):
            self._push("created", event.src_path)

        def on_deleted(self, event: FileSystemEvent):
            self._push("deleted", event.src_path)

        def on_modified(self, event: FileSystemEvent):
            self._push("modified", event.src_path)

        def on_moved(self, event: FileSystemEvent):
            self._push("moved", event.src_path)


async def _polling_generator(root: Path, request: Request):
    snapshot = _build_snapshot(root)
    try:
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(POLL_INTERVAL)
            if await request.is_disconnected():
                break
            new_snapshot = _build_snapshot(root)
            changes = _diff_snapshots(snapshot, new_snapshot)
            snapshot = new_snapshot
            for change in changes:
                line = f"data: {json.dumps(change)}\n\n"
                yield line
    except asyncio.CancelledError:
        pass


async def _watchdog_generator(root: Path, request: Request):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()
    handler = _WatchdogHandler(queue, loop)

    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()

    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if evt is None:
                break
            line = f"data: {json.dumps(evt)}\n\n"
            yield line
    except asyncio.CancelledError:
        pass
    finally:
        observer.stop()
        observer.join(timeout=2)


@router.get("/api/watch/events")
async def watch_events(
    request: Request,
    workspace: str = Query(default=""),
):
    root = resolve_workspace_path(workspace if workspace else None)
    if not root.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Directory not found: {root}")

    if WATCHDOG_AVAILABLE:
        gen = _watchdog_generator(root, request)
    else:
        gen = _polling_generator(root, request)

    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/watch/status")
async def watch_status():
    return {
        "watchdog_available": WATCHDOG_AVAILABLE,
        "mode": "watchdog" if WATCHDOG_AVAILABLE else "polling",
        "poll_interval": POLL_INTERVAL,
    }
