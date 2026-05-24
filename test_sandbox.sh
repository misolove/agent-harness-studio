#!/bin/bash

# Agent Harness Studio - Sandbox Testing Script
# Runs the app in an isolated fake HERMES_HOME so real ~/.hermes is never modified.
# Backend port: 8766 (8765 is reserved by Agent Cat local connector)

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
SANDBOX_DIR="$PROJECT_ROOT/tests/sandbox"
REAL_HERMES="$HOME/.hermes"

echo "=== 🛠️ Setting up Sandbox Environment ==="
mkdir -p "$SANDBOX_DIR/skills"

# 1. Copy real config to sandbox so LLM (9router) connection works
if [ -f "$REAL_HERMES/config.yaml" ]; then
    echo "📋 Copying config.yaml to sandbox..."
    cp "$REAL_HERMES/config.yaml" "$SANDBOX_DIR/"
else
    echo "⚠️ No real config.yaml found. LLM integration might fail."
    echo "Creating dummy config..."
    echo "base_url: http://127.0.0.1:20128/v1" > "$SANDBOX_DIR/config.yaml"
fi

# 2. Create a dummy test skill in sandbox
echo "📝 Creating test skill in sandbox..."
mkdir -p "$SANDBOX_DIR/skills/sandbox-tester"
cat <<EOF > "$SANDBOX_DIR/skills/sandbox-tester/SKILL.md"
---
name: sandbox-tester
description: A dummy skill for testing purposes in sandbox mode.
metadata:
  hermes:
    category: test
    tags: [sandbox, dev]
---
# Sandbox Tester
This is a test skill. Modifying this will NOT affect your real Hermes setup.
EOF

# 3. Export HERMES_HOME and run
echo ""
echo "=== 🚀 Launching Studio in SANDBOX MODE ==="
echo "Targeting: $SANDBOX_DIR"
echo "Backend: http://127.0.0.1:8766"
echo "Frontend: http://localhost:5173"
echo "Note: Any changes made in the UI will happen in the sandbox directory."
echo ""

export HERMES_HOME="$SANDBOX_DIR"

# Source venv if exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# Start Backend
python3 "$PROJECT_ROOT/src/server/app.py" &
BACKEND_PID=$!

# Start Frontend
cd "$PROJECT_ROOT/src/ui" && npx vite --host localhost --port 5173 &
FRONTEND_PID=$!

echo "Dashboard running at http://localhost:5173"
echo "Press Ctrl+C to stop and cleanup."

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Exiting...'" SIGINT SIGTERM

wait
