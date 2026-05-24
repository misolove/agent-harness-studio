#!/usr/bin/env bash
# Agent Harness Studio — Start Backend + Frontend
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/src/server"
FRONTEND_DIR="$PROJECT_ROOT/src/ui"

echo "╔══════════════════════════════════════════╗"
echo "║   Agent Harness Studio — Starting...    ║"
echo "╚══════════════════════════════════════════╝"

# Check dependencies
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found"
  exit 1
fi

if ! command -v node &>/dev/null; then
  echo "ERROR: node not found"
  exit 1
fi

# Install Python deps if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "📦 Installing Python dependencies..."
  pip3 install -r "$PROJECT_ROOT/requirements.txt"
fi

# Install Node deps if needed
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "📦 Installing Node dependencies..."
  cd "$FRONTEND_DIR" && npm install
fi

cleanup() {
  echo ""
  echo "🛑 Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

# Start Backend
echo "🚀 Starting Backend on http://127.0.0.1:8765"
cd "$PROJECT_ROOT"
python3 "$BACKEND_DIR/app.py" &
BACKEND_PID=$!

# Start Frontend
echo "🚀 Starting Frontend on http://localhost:5173"
cd "$FRONTEND_DIR"
npx vite --host localhost --port 5173 &
FRONTEND_PID=$!

echo ""
echo "✅ Agent Harness Studio is running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://127.0.0.1:8765"
echo "   API Docs: http://127.0.0.1:8765/docs"
echo ""
echo "Press Ctrl+C to stop."

wait
