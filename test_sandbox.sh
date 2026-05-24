#!/bin/bash

# Agent Harness Studio - Sandbox Testing Script
# This script runs the app in a isolated environment to prevent actual data modification.

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
echo "Note: Any changes made in the UI will happen in the sandbox directory."
echo ""

# Run backend and frontend (background)
export HERMES_HOME="$SANDBOX_DIR"

# Source venv if exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# Start Backend
python3 "$PROJECT_ROOT/src/server/app.py" &
BACKEND_PID=$!

# Start Frontend
cd "$PROJECT_ROOT/src/ui" && npm run dev &
FRONTEND_PID=$!

echo "Dashboard running at http://localhost:5173"
echo "Press Ctrl+C to stop and cleanup."

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID; echo 'Exiting...'" SIGINT SIGTERM

wait
