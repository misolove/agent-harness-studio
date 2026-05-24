import sys
import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, cast
import subprocess
import json
import re
import sqlite3
from openai import OpenAI
from dotenv import load_dotenv

# Load project-local .env (never commit secrets)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Add src/ and src/server/ to path so we can import scanner and scrapers
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Determine Harness Home — allow override for testing
DEFAULT_HERMES_HOME = Path.home() / ".hermes"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(DEFAULT_HERMES_HOME)))

# HARNESS_READONLY=1 → 모든 쓰기 API 차단. 실수 방지용.
HARNESS_READONLY = os.environ.get("HARNESS_READONLY", "").lower() in ("1", "true", "yes")

# --- SQLite Audit Log Helper ---
DB_PATH = HERMES_HOME / "harness_studio.db"

def _ensure_harness_gitignore() -> None:
    """Keep Harness Studio's local audit DB out of user-managed Hermes git history."""
    if HARNESS_READONLY:
        return
    gitignore = HERMES_HOME / ".gitignore"
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
        _ensure_harness_gitignore()
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

init_db()

# --- Git Integration Helpers ---

def _hermes_is_git_repo() -> bool:
    """Check if HERMES_HOME is a git repository."""
    r = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(HERMES_HOME),
        capture_output=True,
    )
    return r.returncode == 0


def _git_commit_file(file_path: Path, message: str) -> Dict[str, Any]:
    """Stage one file and create a commit in HERMES_HOME. Returns result dict."""
    try:
        rel = file_path.resolve(strict=False).relative_to(HERMES_HOME.resolve())
    except ValueError:
        return {"committed": False, "error": "File outside HERMES_HOME"}

    add = subprocess.run(
        ["git", "add", str(rel)],
        cwd=str(HERMES_HOME),
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        return {"committed": False, "error": add.stderr.strip()}

    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(HERMES_HOME),
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        if "nothing to commit" in commit.stdout or "nothing to commit" in commit.stderr:
            return {"committed": False, "note": "Nothing to commit"}
        return {"committed": False, "error": commit.stderr.strip()}

    short_hash = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(HERMES_HOME),
        capture_output=True,
        text=True,
    ).stdout.strip()

    return {"committed": True, "hash": short_hash, "message": message}


def _git_current_branch() -> Optional[str]:
    r = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(HERMES_HOME),
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def _git_commit_count() -> Optional[int]:
    r = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(HERMES_HOME),
        capture_output=True,
        text=True,
    )
    try:
        return int(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError:
        return None

print(f"=====================================")
print(f"🚀 AGENT HARNESS STUDIO STARTING")
print(f"📁 Target HERMES_HOME: {HERMES_HOME}")
print(f"=====================================")

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from scanner.hermes_scanner import HermesScanner
from scrapers import HybridScraper, ScrapRequest, PhaseStatus


app = FastAPI(
    title="Agent Harness Studio API",
    description="Scans and serves Hermes agent harness configuration",
    version="0.1.0",
)

# CORS — allow Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client for 9router (with fallback to OpenAI API)
def get_llm_client():
    import socket
    router_online = False
    try:
        s = socket.create_connection(("127.0.0.1", 20128), timeout=0.5)
        s.close()
        router_online = True
    except Exception:
        pass

    if router_online:
        config_path = HERMES_HOME / "config.yaml"
        base_url = "http://127.0.0.1:20128/v1"
        api_key = "dummy"

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    c = yaml.safe_load(f)
                    if c.get("base_url"):
                        base_url = c["base_url"]
                    custom = c.get("providers", {}).get("custom", {})
                    for k, v in custom.items():
                        if "20128" in str(v.get("base_url")):
                            base_url = v.get("base_url")
                            api_key = v.get("api_key", api_key)
            except Exception:
                pass

        return OpenAI(base_url=base_url, api_key=api_key), "letitbe"
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return OpenAI(api_key=api_key), "gpt-4o"
        else:
            return OpenAI(base_url="http://127.0.0.1:20128/v1", api_key="dummy"), "letitbe"

# Section type mapping
SECTION_TYPE_MAP: Dict[str, List[str]] = {
    "skills":  ["Skill"],
    "bundles": ["Skill Bundle"],
    "memory":  ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
    "mcp":     ["MCP Server"],
    "context": ["Root Context"],
    "hooks":   ["Hook"],
    "config":  ["Memory Config", "Root Context", "MCP Server"],
    "cron":    ["Cron Job"],
    "plugins": ["Plugin"],
}

def build_response(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a standardised response envelope with a summary."""
    summary: Dict[str, int] = {}
    for item in items:
        t = item.get("type", "Unknown")
        # Group into our 6 dashboard sections
        if t == "Skill":
            summary["skills"] = summary.get("skills", 0) + 1
        elif t == "Skill Bundle":
            summary["bundles"] = summary.get("bundles", 0) + 1
        elif t.startswith("Memory"):
            summary["memory"] = summary.get("memory", 0) + 1
        elif t == "MCP Server":
            summary["mcp"] = summary.get("mcp", 0) + 1
        elif t == "Root Context":
            summary["context"] = summary.get("context", 0) + 1
        elif t == "Hook":
            summary["hooks"] = summary.get("hooks", 0) + 1
        elif t == "Cron Job":
            summary["cron"] = summary.get("cron", 0) + 1
        elif t == "Plugin":
            summary["plugins"] = summary.get("plugins", 0) + 1
        else:
            summary["config"] = summary.get("config", 0) + 1
    summary["web"] = 0 # Placeholder for Web Context count

    return {"summary": summary, "items": items, "total": len(items)}


@app.get("/api/scan")
def scan_all():
    """Return full harness scan results."""
    try:
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()
        return build_response(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scan/{section}")
def scan_section(section: str):
    """Return scan results for a specific section.

    Valid sections: skills, memory, mcp, context, hooks, config
    """
    section = section.lower()
    if section not in SECTION_TYPE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown section '{section}'. Valid sections: {list(SECTION_TYPE_MAP.keys())}",
        )

    try:
        scanner = HermesScanner(str(HERMES_HOME))
        all_items = scanner.scan_all()
        allowed_types = SECTION_TYPE_MAP[section]
        filtered = [i for i in all_items if i.get("type") in allowed_types]
        return build_response(filtered)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Chat Molder & Editing API ---

HERMES_AGENT_REFERENCE_URL = "https://github.com/NousResearch/hermes-agent"

HERMES_REFERENCE_CONTEXT = f"""# Canonical Hermes Agent Reference

Agent Harness Studio treats `nousresearch/hermes-agent` as the default upstream
reference for Hermes behavior and schema decisions.

Reference URL: {HERMES_AGENT_REFERENCE_URL}

## Hermes Mental Model
- Hermes is an open-source agent framework by Nous Research with a learning loop,
  skills, memory, MCP servers, hooks, cron jobs, plugins, and gateway integrations.
- The user harness normally lives in `~/.hermes`; this app uses `HERMES_HOME` to
  override that location for sandboxing or tests.
- The primary user configuration file is `~/.hermes/config.yaml`.

## Canonical Harness Surfaces
- Skills: `~/.hermes/skills/**/SKILL.md`, plus external directories configured
  by `skills.external_dirs`.
- Skill metadata: YAML frontmatter with `name`, `description`, and
  `metadata.hermes` fields such as `tags`, `category`, `related_skills`, and
  config requirements.
- Skill bundles: `~/.hermes/skill-bundles/*.yaml`, grouping skills into reusable
  workflow packs.
- MCP servers: `config.yaml` key `mcp_servers`; supports stdio servers with
  `command`/`args`/`env` and HTTP servers with `url`/`headers`. Common metadata
  includes `enabled`, `tools.include`, `tools.exclude`, `auth`, `sampling`, and
  timeout settings.
- Hooks: shell hooks from `config.yaml` `hooks`, gateway hooks under
  `~/.hermes/hooks/<name>/HOOK.yaml` with optional `handler.py`, and plugin
  provided hooks.
- Memory: `config.yaml` memory settings, `memory_manifest.md`, `memories/`, and
  state files/databases under `state/`.
- Cron: scheduled jobs under `~/.hermes/cron/jobs.json`.
- Plugins: `~/.hermes/plugins/*/plugin.yaml`.
- Root context: `AGENTS.md`, `SOUL.md`, and `config.yaml` `system_prompt` shape
  the agent's long-lived behavior.

## Molder Safety Rules
- Prefer small, schema-valid edits over broad rewrites.
- Never invent non-Hermes schema keys when a known Hermes key exists.
- Never expose or fabricate secrets, tokens, API keys, or private paths.
- If a requested change targets a surface that this app cannot safely apply yet,
  return `SUGGESTION` with concrete manual guidance instead of fake content.
- If general LLM knowledge conflicts with this reference, follow the Hermes
  reference context and the current scanned harness state.
"""


MOLDER_SYSTEM_PROMPT = """You are a Harness Molder — an AI assistant for the Agent Harness Studio.
You help users understand, create, and modify Hermes Agent harness configurations.
You MUST respond in Korean (한국어) regardless of the language the user writes in.
You MUST use the provided Hermes Agent reference context as your default baseline.
When the user asks about Hermes behavior, schema, or file locations, reason from
`nousresearch/hermes-agent` and the current scanned harness context first.

## Response Modes

### Mode 1: Conversation (default)
If the user is asking a question, requesting an explanation, or having a general conversation:
- Respond with plain Korean text in a JSON object:
{
  "action": "CHAT",
  "message": "한국어 답변 내용"
}

### Mode 2: Harness Modification
ONLY when the user explicitly asks to create, modify, add, or change a harness item:
{
  "action": "CREATE_SKILL" | "UPDATE_SKILL" | "UPDATE_CONFIG" | "ADD_MCP",
  "name": "skill-or-item-name (kebab-case)",
  "description": "Short description",
  "message": "한국어로 무엇을 제안하는지 설명",
  "content": "Full file content (YAML frontmatter + Markdown body for skills)",
  "diff_summary": "변경 요약"
}

### Mode 3: Suggestion
When the user needs manual action or clarification:
{
  "action": "SUGGESTION",
  "message": "한국어로 제안 내용 설명"
}

## Skill File Schema (for CREATE/UPDATE_SKILL only)
The SKILL.md frontmatter MUST use this exact schema:
---
name: <kebab-case-name>
description: <short description>
metadata:
  hermes:
    tags: [tag-one, tag-two]
    category: <category>
---
Never write `hermese`, `hermes_agent`, `hermesAgent`. The key is exactly `metadata.hermes`.

## Rules
1. ALWAYS respond in Korean (한국어).
2. For questions/explanations → use CHAT mode (no content field needed).
3. For creation/modification requests → use CREATE_SKILL/UPDATE_SKILL mode.
4. Be concise but helpful. Use the Hermes reference and harness context provided.
5. If the user says something short or ambiguous like "줘", "해줘", "만들어줘", infer intent from the conversation context and the currently selected harness item.
6. If the requested change is for MCP/config/hooks/memory and the app does not provide a safe structured apply flow, use SUGGESTION instead of pretending the change can be applied as a skill.
7. Do not invent installed skill, MCP, or hook capabilities. When explaining current harness items, use only the names, summaries, states, and metadata in the current harness snapshot. If the snapshot is insufficient, say that the item must be opened/read for exact details.
8. Match the user's energy. For greetings or short casual turns, answer in 1-2 natural Korean sentences. Do not repeat onboarding menus unless the user asks what the app can do.
9. Avoid emoji-heavy or marketing-style responses. Use plain, grounded Korean. Markdown tables are okay only when they genuinely improve scanability.
10. The final message labeled `# Current User Request` is the task to answer now. Conversation history is only background. Never answer an older user request when the current request asks for something different.
11. For large inventories, do not dump everything. If there are more than 25 items, summarize by category and show at most 12 representative rows, then offer a focused drilldown. Keep ordinary answers under about 500 Korean words unless the user explicitly asks for exhaustive detail.
12. Format for readability: short intro, compact headings, bullets or a small table, then a short takeaway. Avoid long single paragraphs.
13. When listing items, use real Markdown syntax that the UI can render:
    - Section headings must start with `### `.
    - Item rows should use `- **item-name**: short explanation`.
    - Small comparisons may use a Markdown table with a header row and separator row.
    - Do not use bare label lines such as `MCP 서버 목록` without a Markdown heading marker.
14. For skills specifically, if the snapshot says there are many skills, present category counts plus up to 12 representative skills. Do not list every provided skill summary unless the user explicitly asks for an exhaustive list.

Always respond with ONLY the JSON object, no other text."""


def build_molder_context(items: List[Dict[str, Any]], selected_context: str = "") -> str:
    """Build compact, model-agnostic harness context for the Chat Molder."""
    summary = build_response(items).get("summary", {})

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        by_type.setdefault(item.get("type", "Unknown"), []).append(item)

    def names(item_type: str, limit: int = 20) -> str:
        values = [item.get("name", "") for item in by_type.get(item_type, []) if item.get("name")]
        shown = values[:limit]
        suffix = f" ... (+{len(values) - limit})" if len(values) > limit else ""
        return ", ".join(shown) + suffix if shown else "none"

    def compact_text(value: str, limit: int = 220) -> str:
        text = re.sub(r"\s+", " ", (value or "").strip())
        return text[: limit - 1].rstrip() + "…" if len(text) > limit else text

    skill_category_counts: Dict[str, int] = {}
    for item in by_type.get("Skill", []):
        metadata = item.get("metadata", {}) or {}
        category = metadata.get("category") or metadata.get("path_category") or "uncategorized"
        skill_category_counts[category] = skill_category_counts.get(category, 0) + 1

    skill_category_summary = ", ".join(
        f"{category}={count}"
        for category, count in sorted(skill_category_counts.items(), key=lambda entry: (-entry[1], entry[0]))[:20]
    )

    skill_lines = []
    for item in by_type.get("Skill", [])[:12]:
        metadata = item.get("metadata", {}) or {}
        category = metadata.get("category") or metadata.get("path_category") or "uncategorized"
        summary_text = compact_text(item.get("summary") or "No summary available.")
        skill_lines.append(
            f"- {item.get('name')} [{item.get('state', 'UNKNOWN')}/{category}]: {summary_text}"
        )

    bundle_lines = []
    for item in by_type.get("Skill Bundle", [])[:20]:
        metadata = item.get("metadata", {}) or {}
        bundle_skills = metadata.get("skills") or []
        skill_hint = f" skills={', '.join(bundle_skills[:8])}" if bundle_skills else ""
        bundle_lines.append(
            f"- {item.get('name')} [{item.get('state', 'UNKNOWN')}]: {compact_text(item.get('summary') or '')}{skill_hint}"
        )

    mcp_lines = []
    for item in by_type.get("MCP Server", [])[:20]:
        metadata = item.get("metadata", {}) or {}
        status = item.get("status", "UNKNOWN")
        transport = metadata.get("transport") or ("http" if metadata.get("url") else "stdio")
        summary_text = compact_text(item.get("summary") or "")
        mcp_lines.append(f"- {item.get('name')} [{status}/{transport}]: {summary_text}")

    hook_lines = []
    for item in by_type.get("Hook", [])[:20]:
        metadata = item.get("metadata", {}) or {}
        hook_type = metadata.get("hook_type") or metadata.get("source") or "hook"
        summary_text = compact_text(item.get("summary") or "")
        hook_lines.append(f"- {item.get('name')} [{item.get('status', 'UNKNOWN')}/{hook_type}]: {summary_text}")

    context_parts = [
        "# Current Harness Snapshot",
        f"HERMES_HOME: {HERMES_HOME}",
        f"Read-only mode: {HARNESS_READONLY}",
        f"Selected UI context: {selected_context or 'none'}",
        f"Summary counts: {json.dumps(summary, ensure_ascii=False, sort_keys=True)}",
        f"Skill category counts: {skill_category_summary or 'none'}",
        "Representative skills with scanned summaries (do not exceed these unless user asks for exhaustive detail):",
        "\n".join(skill_lines) if skill_lines else "none",
        "Skill bundles:",
        "\n".join(bundle_lines) if bundle_lines else names("Skill Bundle", 20),
        "MCP servers:",
        "\n".join(mcp_lines) if mcp_lines else "none",
        "Hooks:",
        "\n".join(hook_lines) if hook_lines else "none",
        f"Plugins: {names('Plugin', 20)}",
        f"Cron jobs: {names('Cron Job', 20)}",
        f"Root context: {names('Root Context', 20)}",
        f"Memory surfaces: {names('Memory Config', 10)}; {names('Memory Manifest', 10)}; {names('Memory Directory', 10)}",
    ]
    return "\n".join(context_parts)


@app.get("/api/reference/hermes")
def hermes_reference():
    """Return the canonical Hermes reference context injected into Chat Molder."""
    return {
        "reference_url": HERMES_AGENT_REFERENCE_URL,
        "context": HERMES_REFERENCE_CONTEXT,
        "source": "nousresearch/hermes-agent",
    }


def normalize_skill_content(content: str, name: str, description: str = "") -> str:
    """Repair common LLM-generated SKILL.md schema issues before preview/apply.

    The LLM is useful for drafting, but the harness owns the schema. This keeps
    generated skills indexable by Hermes even when the model misspells keys.
    """
    if not content:
        return content

    repaired = content.replace("hermese:", "hermes:")
    repaired = repaired.replace("hermes_agent:", "hermes:")
    repaired = repaired.replace("hermesAgent:", "hermes:")

    # If frontmatter is missing entirely, wrap the draft in valid SKILL.md metadata.
    if not repaired.lstrip().startswith("---"):
        safe_name = name or "generated-skill"
        safe_description = description or "Generated skill"
        return f"""---
name: {safe_name}
description: {safe_description}
metadata:
  hermes:
    tags: [generated]
    category: general
---

{repaired.strip()}
"""

    # If frontmatter exists but lacks metadata.hermes, add a minimal block before closing ---.
    parts = repaired.split("---", 2)
    if len(parts) >= 3:
        fm = parts[1]
        body = parts[2]
        if "metadata:" not in fm:
            fm = fm.rstrip() + "\nmetadata:\n  hermes:\n    tags: [generated]\n    category: general\n"
        elif "hermes:" not in fm:
            fm = fm.rstrip() + "\n  hermes:\n    tags: [generated]\n    category: general\n"
        repaired = f"---{fm}---{body}"

    return repaired

def validate_molder_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and annotate an LLM-generated molder proposal."""
    action = result.get("action", "SUGGESTION")
    if "SKILL" in action and result.get("content"):
        before = result["content"]
        after = normalize_skill_content(
            before,
            result.get("name", "generated-skill"),
            result.get("description", "Generated skill"),
        )
        result["content"] = after
        if before != after:
            result["diff_summary"] = (result.get("diff_summary", "") + "\nServer-side validation repaired SKILL.md frontmatter schema.").strip()
    return result


def strip_json_code_fence(text: str) -> str:
    """Remove common Markdown fences around model JSON."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    if cleaned.startswith("json\n"):
        cleaned = cleaned[5:].strip()
    return cleaned


def extract_json_string_field(text: str, field: str) -> Optional[str]:
    """Best-effort extraction for truncated JSON strings such as {"message": "..."}."""
    pattern = f'"{field}"'
    field_index = text.find(pattern)
    if field_index < 0:
        return None

    colon_index = text.find(":", field_index + len(pattern))
    if colon_index < 0:
        return None

    quote_index = text.find('"', colon_index + 1)
    if quote_index < 0:
        return None

    out: List[str] = []
    index = quote_index + 1
    while index < len(text):
        char = text[index]
        if char == '"':
            break
        if char == "\\" and index + 1 < len(text):
            escaped = text[index + 1]
            if escaped == "n":
                out.append("\n")
                index += 2
                continue
            if escaped == "t":
                out.append("\t")
                index += 2
                continue
            if escaped == "r":
                index += 2
                continue
            if escaped in ('"', "\\", "/"):
                out.append(escaped)
                index += 2
                continue
            if escaped == "u" and index + 5 < len(text):
                hex_value = text[index + 2:index + 6]
                try:
                    out.append(chr(int(hex_value, 16)))
                    index += 6
                    continue
                except ValueError:
                    pass
        out.append(char)
        index += 1

    recovered = "".join(out).strip()
    return recovered or None


def parse_molder_json(raw: str) -> Dict[str, Any]:
    """Parse model JSON, recovering CHAT messages from truncated JSON when possible."""
    cleaned = strip_json_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {"action": "CHAT", "message": str(parsed)}
    except json.JSONDecodeError:
        try:
            parsed, _ = json.JSONDecoder().raw_decode(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    recovered_message = extract_json_string_field(cleaned, "message")
    if recovered_message:
        return {
            "action": "CHAT",
            "message": recovered_message.rstrip() + "\n\n(응답이 길어 일부가 잘렸습니다. 더 좁은 범위로 다시 물어보면 이어서 정리할 수 있어요.)",
            "_recovered_from_truncated_json": True,
        }
    raise json.JSONDecodeError("Could not parse molder JSON", cleaned, 0)


def normalize_history_text(text: str) -> str:
    """Keep leaked JSON envelopes out of future model context."""
    cleaned = strip_json_code_fence(text)
    if cleaned.lstrip().startswith("{") and '"message"' in cleaned:
        recovered = extract_json_string_field(cleaned, "message")
        if recovered:
            return recovered
    return text


@app.post("/api/mold")
def mold_harness(
    prompt: str = Body(..., embed=True),
    context: str = Body("", embed=True),
    history: Optional[list] = Body(None, embed=True),
):
    """
    Chat Molder: Conversational AI assistant for harness management.
    Supports both Q&A (CHAT mode) and harness modification (CREATE/UPDATE mode).
    """
    raw = ""
    try:
        client, model_name = get_llm_client()

        # Build context from current harness state
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()

        context_str = build_molder_context(items, context)

        # Build message history for multi-turn conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": MOLDER_SYSTEM_PROMPT},
            {"role": "system", "content": HERMES_REFERENCE_CONTEXT},
        ]

        # Add conversation history
        for msg in (history or [])[-10:]:  # Keep last 10 messages for context
            role = msg.get("role", "user")
            text = normalize_history_text(msg.get("text", ""))
            if role == "user":
                messages.append({"role": "user", "content": f"# Historical User Turn\n{text}"})
            else:
                messages.append({"role": "assistant", "content": f"# Historical Assistant Turn\n{text}"})

        messages.append({
            "role": "user",
            "content": (
                f"{context_str}\n\n"
                "# Current User Request\n"
                f"{prompt}\n\n"
                "Answer this current request directly. Use the history only to resolve references."
            ),
        })

        response = client.chat.completions.create(
            model=model_name,
            messages=cast(Any, messages),
            temperature=0.7,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content or ""
        result = parse_molder_json(raw)

        # Handle CHAT mode — just return the message
        action = result.get("action", "CHAT")
        if action == "CHAT" or (action not in ("CREATE_SKILL", "UPDATE_SKILL", "UPDATE_CONFIG", "ADD_MCP") and not result.get("content")):
            return {
                "status": "success",
                "action": "CHAT",
                "name": "",
                "message": result.get("message", raw),
                "content": "",
                "diff": "",
                "diff_summary": "",
            }

        result = validate_molder_result(result)

        # Build diff for modification actions
        diff_lines = []
        if result.get("content"):
            act = result.get("action", "CREATE_SKILL")
            name = result.get("name", "unknown")
            if "SKILL" in act:
                path = f"skills/{name}/SKILL.md"
            elif "MCP" in act:
                path = "config.yaml (mcp_servers section)"
            else:
                path = "config.yaml"

            diff_lines.append(f"+++ b/{path}")
            for line in result["content"].split("\n"):
                diff_lines.append(f"+{line}")

        return {
            "status": "success",
            "action": result.get("action", "SUGGESTION"),
            "name": result.get("name", ""),
            "description": result.get("description", ""),
            "message": result.get("message", ""),
            "content": result.get("content", ""),
            "diff": "\n".join(diff_lines),
            "diff_summary": result.get("diff_summary", ""),
        }

    except json.JSONDecodeError:
        fallback_msg = "응답 형식을 정리하지 못했습니다. 질문 범위를 조금 좁혀서 다시 말씀해주세요."
        return {
            "status": "success",
            "action": "CHAT",
            "name": "",
            "message": fallback_msg,
            "content": "",
            "diff": "",
            "diff_summary": "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {str(e)}")

def _resolve_hermes_path(path: Path) -> Path:
    """Resolve a user-supplied path and ensure it is contained by HERMES_HOME."""
    hermes_root = HERMES_HOME.resolve()
    resolved = path.expanduser().resolve(strict=False)
    try:
        resolved.relative_to(hermes_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: outside .hermes")
    return resolved


def _assert_within_hermes(path: Path) -> None:
    """Raise 403 if path resolves outside HERMES_HOME."""
    _resolve_hermes_path(path)


def _backup(path: Path) -> Optional[str]:
    """Copy existing file to .bak.{timestamp}. Returns backup path or None."""
    if not path.exists():
        return None
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.name + f".bak.{ts}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup)


@app.get("/api/read")
def read_file(path: str, allow_missing: bool = False):
    """Read a harness file for editing. Only files within HERMES_HOME are accessible."""
    target_path = _resolve_hermes_path(Path(path))
    if not target_path.exists():
        if allow_missing:
            return {"content": "", "path": str(target_path), "missing": True}
        raise HTTPException(status_code=404, detail="File not found")
    try:
        return {"content": target_path.read_text(encoding="utf-8"), "path": str(target_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/save")
def save_item(
    path: str = Body(...),
    content: str = Body(...),
    commit_message: str = Body(""),
):
    """Save a harness item. Auto-backs up and git-commits if HERMES_HOME is a git repo."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode (HARNESS_READONLY=1). Set HARNESS_READONLY=0 to enable writes.")

    target_path = _resolve_hermes_path(Path(path))

    try:
        backup_path = _backup(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        git_result = None
        if _hermes_is_git_repo():
            rel = target_path.relative_to(HERMES_HOME)
            msg = commit_message.strip() or f"harness-studio: save {rel}"
            git_result = _git_commit_file(target_path, msg)

        log_audit_event("user", "save", str(target_path), f"Git status: {bool(git_result)}")

        return {
            "status": "saved",
            "path": str(target_path),
            "backup": backup_path,
            "git": git_result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rollback")
def rollback_item(path: str = Body(...)):
    """Restore the most recent .bak.* backup of a file."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    target_path = _resolve_hermes_path(Path(path))

    backups = sorted(
        target_path.parent.glob(target_path.name + ".bak.*"),
        reverse=True,
    )
    if not backups:
        raise HTTPException(status_code=404, detail="No backup found for this file")

    latest = backups[0]
    try:
        target_path.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
        latest.unlink()
        log_audit_event("user", "rollback", str(target_path), f"Backup used: {latest}")
        return {"status": "rolled_back", "from_backup": str(latest), "remaining_backups": len(backups) - 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/env")
def get_env():
    """Return current environment info for UI badge."""
    is_git = _hermes_is_git_repo()
    return {
        "hermes_home": str(HERMES_HOME),
        "is_sandbox": HERMES_HOME.name == "sandbox",
        "is_readonly": HARNESS_READONLY,
        "is_git_repo": is_git,
        "git_branch": _git_current_branch() if is_git else None,
        "git_commit_count": _git_commit_count() if is_git else None,
    }


# --- Git API ---

@app.post("/api/git/init")
def git_init():
    """Initialize a git repo in HERMES_HOME and create an initial commit."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")
    if _hermes_is_git_repo():
        return {"status": "already_git_repo", "branch": _git_current_branch()}

    try:
        subprocess.run(["git", "init"], cwd=str(HERMES_HOME), check=True, capture_output=True)

        # .gitignore: exclude backup sidecar files and secrets
        _ensure_harness_gitignore()

        subprocess.run(["git", "add", "-A"], cwd=str(HERMES_HOME), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "harness-studio: initial commit"],
            cwd=str(HERMES_HOME),
            check=True,
            capture_output=True,
        )
        short_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(HERMES_HOME),
            capture_output=True,
            text=True,
        ).stdout.strip()
        log_audit_event("user", "git_init", str(HERMES_HOME), f"Git repo initialized. Initial commit: {short_hash}")
        return {"status": "initialized", "initial_commit": short_hash, "branch": _git_current_branch()}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr.decode() if e.stderr else str(e))


@app.get("/api/git/log")
def git_log(path: Optional[str] = None, limit: int = 30):
    """Return git commit history, optionally filtered to a specific file."""
    if not _hermes_is_git_repo():
        return {"is_git_repo": False, "commits": []}

    cmd = [
        "git", "log",
        f"--max-count={limit}",
        "--pretty=format:%H|%h|%s|%ai|%an",
    ]
    if path:
        try:
            rel = _resolve_hermes_path(Path(path)).relative_to(HERMES_HOME.resolve())
            cmd += ["--", str(rel)]
        except ValueError:
            pass

    result = subprocess.run(cmd, cwd=str(HERMES_HOME), capture_output=True, text=True)
    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "message": parts[2],
                "date": parts[3],
                "author": parts[4],
            })
    return {"is_git_repo": True, "commits": commits}


@app.get("/api/git/diff")
def git_diff(commit_hash: str, path: Optional[str] = None):
    """Return the diff introduced by a specific commit (optionally for one file)."""
    if not _hermes_is_git_repo():
        return {"is_git_repo": False, "diff": ""}

    cmd = ["git", "show", "--stat", "--patch", commit_hash]
    if path:
        try:
            rel = _resolve_hermes_path(Path(path)).relative_to(HERMES_HOME.resolve())
            cmd += ["--", str(rel)]
        except ValueError:
            pass

    result = subprocess.run(cmd, cwd=str(HERMES_HOME), capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=404, detail=f"Commit not found: {commit_hash}")
    return {"diff": result.stdout}


@app.post("/api/git/rollback")
def git_rollback(path: str = Body(...), commit_hash: str = Body(...)):
    """Restore a file to the state at a specific commit hash."""
    if HARNESS_READONLY:
        raise HTTPException(status_code=403, detail="Read-only mode")

    target_path = _resolve_hermes_path(Path(path))

    try:
        rel = target_path.relative_to(HERMES_HOME.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="File outside HERMES_HOME")

    backup_path = _backup(target_path)

    result = subprocess.run(
        ["git", "checkout", commit_hash, "--", str(rel)],
        cwd=str(HERMES_HOME),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # restore from backup on failure
        if backup_path:
            target_path.write_text(Path(backup_path).read_text(encoding="utf-8"), encoding="utf-8")
        raise HTTPException(status_code=500, detail=result.stderr.strip())

    # commit the restoration so history stays linear
    _git_commit_file(target_path, f"harness-studio: rollback {rel} to {commit_hash[:7]}")

    log_audit_event("user", "git_rollback", str(target_path), f"Commit hash: {commit_hash}")

    return {"status": "restored", "to_commit": commit_hash, "backup": backup_path}


@app.post("/api/web/scrape")
async def web_scrape(url: str = Body(..., embed=True)):
    """
    Hybrid Web Context Scraper (Firecrawl -> Jina -> TLS -> Browser).
    Escalates through 4 phases until content is successfully extracted.
    """
    if not url:
        return {"status": "error", "message": "URL is required"}

    try:
        scraper = HybridScraper()
        result = await scraper.scrape(ScrapRequest(url=url))

        # Convert Pydantic result to dict for FastAPI response
        response = result.model_dump()

        # UI expectation mapping: if successful, status should be "ok"
        if result.status == PhaseStatus.SUCCESS:
            response["status"] = "ok"
            response["source"] = result.phase_used
        else:
            response["status"] = "error"
            response["message"] = "All scraping phases failed."

        return response
    except Exception as e:
        return {
            "status": "error",
            "message": f"Hybrid pipeline crash: {str(e)}",
            "url": url,
            "source": "hybrid",
        }


@app.get("/api/audit/logs")
def get_audit_logs(limit: int = 50):
    """Retrieve audit logs from the SQLite database."""
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


@app.post("/api/convert/skill")
def convert_skill(
    content: str = Body(..., embed=True),
    target: str = Body(..., embed=True), # 'hermes' or 'claude'
):
    """Convert SKILL.md frontmatter between Hermes and Claude Code formats."""
    if not content:
        raise HTTPException(status_code=400, detail="Content is empty")

    # Try parsing frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise HTTPException(status_code=400, detail="No frontmatter found in content")

    frontmatter_str = match.group(1)
    body = content[match.end():]

    try:
        frontmatter = yaml.safe_load(frontmatter_str) or {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frontmatter YAML: {e}")

    name = frontmatter.get("name", "converted-skill")
    description = frontmatter.get("description", "")

    if target == "claude":
        # Claude Code format standard style frontmatter: simple flat key-value
        new_fm = {
            "name": name,
            "description": description,
            "tags": [],
            "category": "general"
        }
        # Copy values if exists
        meta = frontmatter.get("metadata", {})
        if isinstance(meta, dict):
            hermes_meta = meta.get("hermes", {})
            if isinstance(hermes_meta, dict):
                new_fm["tags"] = hermes_meta.get("tags", [])
                new_fm["category"] = hermes_meta.get("category", "general")

        # If there are other custom keys, carry them over
        for k, v in frontmatter.items():
            if k not in ("name", "description", "metadata"):
                new_fm[k] = v

    elif target == "hermes":
        # Hermes format: uses nested metadata.hermes
        tags = frontmatter.get("tags", ["converted"])
        category = frontmatter.get("category", "general")

        new_fm = {
            "name": name,
            "description": description,
            "metadata": {
                "hermes": {
                    "tags": tags if isinstance(tags, list) else [tags],
                    "category": category
                }
            }
        }
        # Copy other keys
        for k, v in frontmatter.items():
            if k not in ("name", "description", "tags", "category", "metadata"):
                new_fm[k] = v
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported target format: {target}")

    new_fm_str = yaml.safe_dump(new_fm, sort_keys=False, allow_unicode=True)
    new_content = f"---\n{new_fm_str}---\n{body}"

    return {"content": new_content, "target": target}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8766, reload=True)
