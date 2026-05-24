#!/usr/bin/env bash
# Agent Harness Studio — Auto-start via LaunchAgent
# Designed for macOS launchctl: RunAtLoad + KeepAlive
set -e

PROJECT_ROOT="/Users/letitbe/letitbe/agent-harness-studio"
FRONTEND_DIR="$PROJECT_ROOT/src/ui"
LOG_DIR="$HOME/Library/Logs/agent-harness-studio"

mkdir -p "$LOG_DIR"

echo "[$(date)] ╔══════════════════════════════════════════╗"
echo "[$(date)] ║   Agent Harness Studio — Starting...    ║"
echo "[$(date)] ╚══════════════════════════════════════════╝"

# Activate virtualenv
source "$PROJECT_ROOT/.venv/bin/activate"

# Ensure Node deps
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[$(date)] 📦 Installing Node dependencies..."
  cd "$FRONTEND_DIR" && npm install
fi

# ── Harness Target ─────────────────────────
# 실데이터 (기본값) — ~/.hermes가 git repo이면 모든 변경이 커밋으로 기록됩니다.
HARNESS_HOME="${HERMES_HOME:-/Users/letitbe/.hermes}"
# 샌드박스로 전환: HERMES_HOME=/Users/letitbe/.hermes/sandbox ./run.sh
# 읽기 전용 모드: HARNESS_READONLY=1 ./run.sh

# ── Clean up stale port occupants ──────────
for PORT in 8766 5173; do
  OLD_PID=$(lsof -ti tcp:$PORT 2>/dev/null || true)
  if [ -n "$OLD_PID" ]; then
    echo "[$(date)] 🧹 Killing stale process on port $PORT (PID $OLD_PID)"
    kill $OLD_PID 2>/dev/null || true
    sleep 1
  fi
done

# ── Start Backend ──────────────────────────
echo "[$(date)] 🚀 Starting Backend on http://127.0.0.1:8766 (HERMES_HOME=$HARNESS_HOME)"
cd "$PROJECT_ROOT"
HERMES_HOME="$HARNESS_HOME" \
HARNESS_READONLY="${HARNESS_READONLY:-0}" \
  python -m uvicorn src.server.app:app \
    --host 127.0.0.1 \
    --port 8766 \
    --log-level info &
BACKEND_PID=$!

# ── Start Frontend ─────────────────────────
echo "[$(date)] 🚀 Starting Frontend on http://localhost:5173"
cd "$FRONTEND_DIR"
npx vite --host localhost --port 5173 &
FRONTEND_PID=$!

# ── Health Check (after brief wait) ────────
sleep 6
HEALTH_OK=true

if curl -sf http://127.0.0.1:8766/docs -o /dev/null 2>/dev/null; then
  echo "[$(date)] ✅ Backend healthy"
else
  echo "[$(date)] ⚠️  Backend not responding yet"
  HEALTH_OK=false
fi

if curl -sf http://localhost:5173 -o /dev/null 2>/dev/null; then
  echo "[$(date)] ✅ Frontend healthy"
else
  echo "[$(date)] ⚠️  Frontend not responding yet"
  HEALTH_OK=false
fi

echo "[$(date)] PIDs: Backend=$BACKEND_PID Frontend=$FRONTEND_PID"

# ── Wait for any child to exit ─────────────
# When one dies, kill the other so KeepAlive restarts the whole stack cleanly.
while kill -0 $BACKEND_PID 2>/dev/null && kill -0 $FRONTEND_PID 2>/dev/null; do
  sleep 5
done

DEAD=""
kill -0 $BACKEND_PID 2>/dev/null || DEAD="backend"
kill -0 $FRONTEND_PID 2>/dev/null || DEAD="frontend"

echo "[$(date)] 🛑 $DEAD exited. Killing remaining processes..."
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
wait 2>/dev/null || true
echo "[$(date)] Stack shut down. KeepAlive will restart."
exit 1
