# Agent Runner: Pi Coding Agent Adapter

Last updated: 2026-05-27

This document is the handoff spec for connecting Agent Harness Studio's Chat/Agent Runner UI to Pi Coding Agent.

## Current Decision

Use the user's installed `pi` CLI first, through Pi RPC/JSON modes. Do not fork or embed `earendil-works/pi` yet.

Why:
- Studio backend is FastAPI/Python, so a subprocess RPC adapter is the smallest integration surface.
- The installed Pi already owns user config, provider choice, auth, extensions, skills, and sessions.
- Pi supports `--mode rpc`, `--mode json`, `--print`, `--tools`, and `--no-session`, which is enough for a safe first adapter.
- Forking or embedding the source/SDK adds update and packaging burden before we know which runtime controls Studio truly needs.

Move to the SDK/source path only after the CLI/RPC adapter proves insufficient for event fidelity, custom permissions, custom tools, or session lifecycle control.

## Local Pi State

Observed on 2026-05-26:

```text
pi executable: /opt/homebrew/bin/pi
pi version: 0.75.5
config dir: ~/.pi/agent
defaultProvider: zai
defaultModel: glm-5.1
auth.json: present but empty
models.json: present; currently still includes an ollama provider entry
session files detected: 5
```

The user's latest intent is to use Z.ai `glm-5.1` instead of local Ollama because local Ollama was slow.

## Implemented So Far

Backend:
- `GET /api/agent-runners`
- `GET /api/pi/status`
- `POST /api/pi/preview`
- `POST /api/pi/runs`
- `GET /api/pi/runs/{run_id}`
- `GET /api/pi/runs/{run_id}/log`
- `POST /api/pi/runs/{run_id}/stop`
- `POST /api/pi/mold`

Frontend:
- Sidebar card: `Agent Runner`
- Panel shows Pi installed/missing state, version, session count, auth/config presence, capabilities, safe execution path, and command preview.
- Agent Runner panel can launch read-only runs, poll status/logs, and show post-run diff audit.
- Chat Molder has an LLM/Pi Agent toggle. Pi mode uses persisted `--session` files and `--print` output for multi-turn chat.

The preview endpoint intentionally does not execute Pi. It returns:

```json
{
  "status": "preview",
  "will_execute": false,
  "command": ["pi", "--tools", "read,grep,find,ls", "--no-session", "--mode", "rpc", "..."]
}
```

Read-only run data is persisted under:

```text
~/.hermes/harness-studio-runs/pi/{run_id}/
  meta.json
  events.jsonl
  stdout.log
  stderr.log
  pre-audit.json
  post-audit.json
```

## Safety Model

The adapter should progress in three stages.

### Stage 1: Detect And Read-Only Chat

Allowed:
- Launch Pi in a subprocess only with read-only tools:
  `--tools read,grep,find,ls`
- Use `--no-session` for initial experiments unless explicit session persistence is needed.
- Stream RPC/JSON events into Studio.
- Show stdout/stderr and tool events in the UI.
- Run `GET /api/git/audit` before and after.

Blocked:
- `write`
- `edit`
- `bash`
- auto-commit
- background autonomous runs

Suggested first command:

```bash
pi --tools read,grep,find,ls --no-session --mode rpc "Summarize this repository and list safe verification commands."
```

### Stage 2: Gated Write Mode

Allowed only after explicit UI toggle/confirmation:
- `edit`
- `write`
- narrowly scoped `bash`

Required guardrails:
- Workspace must be inside `_get_allowed_roots()`.
- Capture pre-run git audit.
- Prefer clean worktree or explicit accepted dirty baseline.
- Capture full event log.
- Capture post-run git audit.
- Show diff before commit.
- Commit only with explicit user action or a clear separate automation policy.

### Stage 3: SDK Or Source Integration

Consider SDK/source only when one of these is true:
- RPC mode cannot expose enough event detail for the UI.
- Studio needs custom permission prompts per tool call.
- Studio needs custom tools directly wired to its scanner/audit APIs.
- Studio needs durable Pi sessions managed inside Studio rather than Pi's own session dir.
- Packaging subprocess Pi becomes less reliable than a Node sidecar.

If this happens, prefer a small Node sidecar over rewriting Pi behavior in Python.

## Current API Shape

Implemented:

```text
POST /api/pi/runs
  Create a read-only run.
  Body: { workspace, prompt, mode: "read_only" }
  Returns: { run_id, status, command, pre_audit }

GET /api/pi/runs/{run_id}
  Return run status, command, start/end timestamps, exit code.

GET /api/pi/runs/{run_id}/log
  Bounded stdout/stderr tail, similar to /api/read?tail=true.

POST /api/pi/runs/{run_id}/stop
  Stop the subprocess.

POST /api/pi/mold
  Start a Chat Molder Pi run with read, grep, find, ls, web_search and session persistence.
```

Still planned:

```text
GET /api/pi/runs/{run_id}/events
  SSE stream of normalized Pi RPC/JSON events.

GET /api/pi/runs/{run_id}/audit
  Dedicated audit endpoint if post_audit grows beyond run metadata.
```

Data model:

```text
~/.hermes/harness-studio-runs/pi/{run_id}/
  meta.json
  events.jsonl
  stdout.log
  stderr.log
  pre-audit.json
  post-audit.json
```

Keep these sidecar files ignored by git.

## UI Shape

Implemented:
- Status strip: provider/model/auth/runtime.
- Run controls: read-only run.
- Log panel: stdout/stderr tail.
- Safety pane: post-run audit summary.
- Chat Molder Pi toggle with session continuity and mentioned-file buttons.

Still planned:
- SSE live event stream instead of 2s polling.
- Stop button in the visible UI for active runs.
- Clear/export log actions.
- Gated write toggle: off by default, visually distinct, requires confirmation.

Important: `defaultProvider` and `defaultModel` from `~/.pi/agent/settings.json` are now shown directly in the UI.

## Implementation Notes

- Parse `~/.pi/agent/settings.json` for `defaultProvider`, `defaultModel`, `packages`, and `lastChangelogVersion`.
- Keep API keys masked; never return raw auth values.
- Avoid `shell=True`; build argv lists.
- Use async subprocess for real run streaming.
- Use bounded log reads/tails for large output.
- Treat `pi --help` output as capability discovery, not a stable API contract.

## Verification Checklist

Current smoke checks:

```bash
python3 -m py_compile src/server/app.py
cd src/ui && npm run build
curl -sf 'http://127.0.0.1:8766/api/pi/status?workspace=/Users/letitbe/letitbe/agent-harness-studio' | python3 -m json.tool
curl -sf -X POST 'http://127.0.0.1:8766/api/pi/preview' \
  -H 'Content-Type: application/json' \
  -d '{"workspace":"/Users/letitbe/letitbe/agent-harness-studio","mode":"rpc","prompt":"hello"}' \
  | python3 -m json.tool
```

For a real read-only run, use a disposable prompt and verify:
- no files changed,
- no unbounded process remains,
- events are persisted,
- UI can render the log without freezing.
