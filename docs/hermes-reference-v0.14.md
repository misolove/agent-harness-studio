# Hermes Agent v0.14.0 Reference & Handoff Guide

> **Context for AI Agents**: This document summarizes the core architecture, philosophy, and v0.14.0 updates of Hermes Agent based on Blake Crosley's 2026 practical guide. Use this document as the ground truth for understanding how Hermes structures its state, memory, and configurations when developing features for **Agent Harness Studio**.

## 1. Core Philosophy: Breaking Vendor Lock-in
Unlike Claude Code (Anthropic), Codex CLI (OpenAI), or Gemini CLI (Google), Hermes is an open-source, self-improving AI agent.
- **Goal**: Maintain persistent identity, memory, and learned skills across different LLM providers.
- **Learning-by-doing**: Skills created or refined during problem-solving remain available regardless of the underlying LLM backend.

## 2. The 5 Core Systems

When analyzing or modifying Hermes via Agent Harness Studio, every feature maps to one of these five systems:

### A. Provider Resolution (Authentication)
Hermes uses strictly three paths for authentication. Studio should recognize these when parsing configurations:
1. **`.env` (API Keys)**: Used for OpenRouter, DeepSeek, Google, etc.
2. **`auth.json` (OAuth)**: Interactively created via `hermes model`. Uses device code flow (Nous Portal, Anthropic, Codex Copilot).
3. **Custom Endpoints (`config.yaml`)**: Any OpenAI-compatible `/v1/chat/completions` endpoint (Ollama, vLLM, llama.cpp, etc.).
*Note: Auxiliary models (vision, web extract, compression) must be explicitly configured or they silently degrade.*

### B. Configuration Hierarchy
Settings are applied in this order (highest to lowest priority):
1. CLI Arguments
2. Environment Variables
3. `config.yaml` (General settings, toolsets, memory)
4. `.env` (Secrets)
5. Built-in defaults

**Identity vs. Project Rules**:
- `SOUL.md`: Global persona, tone, and communication defaults (System prompt slot 1).
- `AGENTS.md`: Project-specific architecture, coding rules, and deployment notes.

### C. Tools & Toolsets System
- Grouped logically (web, terminal, browser, media, memory, automation, etc.).
- **Terminal Backends**: Commands can run in `local`, `docker`, `ssh`, `singularity`, `modal`, or `daytona`.
- **Background Processes**: Explicit tracking (`session_id`, `pid`) for long-running tasks.

### D. Skill System (Procedural Memory)
- **Progressive Disclosure**: Loads only metadata by default. Fetches full content `skill_view(name)` only when needed to save context window tokens.
- **Self-Creation**: Automatically triggered when completing complex tasks (5+ tools), overcoming errors, or discovering new workflows.
- **Skills Hub**: Remote registry installation with strict security scanning.

### E. Gateway + Cron + Profiles
- **Gateway**: A single process bridging 22 messaging platforms (Telegram, Slack, Discord, etc.). All platforms use the exact same AIAgent conversation loop as the CLI.
- **Cron**: First-class AI scheduled tasks. Cron jobs run through LLM agents, not just shell scripts.
- **Profiles**: Isolated environments (e.g., `work` vs `personal`), each with its own `$HERMES_HOME`, config, skills, and memory.

## 3. Persistent Memory
Hermes strictly limits persistent memory injected into the system prompt to preserve prefix caching:
- `MEMORY.md`: Agent's notes (environment facts, rules, learned lessons). Limit: 2,200 chars.
- `USER.md`: User profile (preferences, style). Limit: 1,375 chars.
- For deep history, Hermes relies on SQLite FTS5 (`session_search`) and external providers (Mem0, Honcho, etc.).

## 4. Notable v0.14.0 Updates for Studio Integration
- **`hermes proxy`**: Converts OAuth subscriptions (Claude Pro, ChatGPT Pro) into local OpenAI-compatible endpoints.
- **Multi-Agent Kanban**: Persistent boards, zombie detection, hallucination gates, and `/goal` (multi-turn loop) / `/handoff` (live session transfer).
- **Security**: Strict secret redaction, prompt-injection scanning for cron jobs.

---

## 💡 Implications for Agent Harness Studio
When developing or extending Agent Harness Studio, subagents should:
1. **Differentiate SOUL vs AGENTS**: Studio UI should guide users to edit `SOUL.md` for personality and `AGENTS.md` for project rules.
2. **Profile Awareness**: Ensure the scanner can handle custom profile paths (`~/.hermes-<name>`) instead of hardcoding `~/.hermes`.
3. **Auxiliary Model Auditing**: Add a feature to the "Diff Audit" or "Scanner" to warn users if auxiliary models (vision, web) are missing or misconfigured in `config.yaml`.
4. **Proxy & Auth Visualization**: Visually distinguish which of the 3 authentication paths is currently active for the main model.