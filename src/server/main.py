import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn

from services.config import (
    HARNESS_API_TOKEN,
    HARNESS_CORS_ORIGINS,
    HARNESS_HOME,
    HARNESS_HOST,
    HARNESS_READONLY,
    init_db,
)

init_db()

logger = logging.getLogger("agent-harness-studio")

print(f"=====================================")
print(f"🚀 AGENT HARNESS STUDIO STARTING")
print(f"📁 Target HERMES_HOME: {HERMES_HOME}")
print(f"=====================================")

app = FastAPI(
    title="Agent Harness Studio API",
    description="Scans and serves Hermes agent harness configuration",
    version="0.2.0",
)


def _error_response(status_code: int, detail: str, error_type: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "error_type": error_type})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return _error_response(exc.status_code, str(exc.detail), type(exc).__name__)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return _error_response(422, str(exc), "ValueError")


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError):
    return _error_response(404, str(exc), "FileNotFoundError")


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _error_response(500, str(exc), type(exc).__name__)


app.add_middleware(
    CORSMiddleware,
    allow_origins=HARNESS_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    public_paths = {"/health", "/docs", "/openapi.json"}
    if HARNESS_API_TOKEN and request.method != "OPTIONS" and request.url.path not in public_paths:
        auth_header = request.headers.get("authorization", "")
        token_header = request.headers.get("x-harness-token", "")
        bearer = f"Bearer {HARNESS_API_TOKEN}"
        if auth_header != bearer and token_header != HARNESS_API_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


from routers import (
    scan, env, files, git, mold, pi, web, sessions, convert, actions, audit, watch, toggle, install
)

app.include_router(scan.router)
app.include_router(env.router)
app.include_router(files.router)
app.include_router(git.router)
app.include_router(mold.router)
app.include_router(pi.router)
app.include_router(web.router)
app.include_router(sessions.router)
app.include_router(convert.router)
app.include_router(actions.router)
app.include_router(audit.router)
app.include_router(watch.router)
app.include_router(toggle.router)
app.include_router(install.router)


if __name__ == "__main__":
    uvicorn.run("src.server.main:app", host=HARNESS_HOST, port=8766, reload=True)
