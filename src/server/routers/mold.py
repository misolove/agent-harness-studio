import os
import re
import json
import html
from pathlib import Path
from typing import List, Dict, Any, Optional, cast
from urllib.parse import unquote, urlparse, parse_qs

from fastapi import APIRouter, HTTPException, Body
from openai import OpenAI
from dotenv import set_key
import httpx

from services.config import HERMES_HOME, HARNESS_READONLY, PROJECT_ROOT
from services.llm import get_llm_provider_config, get_llm_client, call_llm_async, ENV_PATH
from routers.scan import build_response, _scan_items_for_workspace
from scanner.hermes_scanner import HermesScanner

router = APIRouter()

MOLDER_AUTO_WEB_SEARCH = os.environ.get("MOLDER_AUTO_WEB_SEARCH", "1").lower() not in ("0", "false", "no")
MOLDER_WEB_SEARCH_TIMEOUT = float(os.environ.get("MOLDER_WEB_SEARCH_TIMEOUT", "8"))
MOLDER_WEB_SEARCH_LIMIT = int(os.environ.get("MOLDER_WEB_SEARCH_LIMIT", "5"))

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
15. If a `# Web Search Context` section is present, use it to answer external, current, or unknown-project questions. Cite the result titles/domains in Korean instead of claiming you cannot browse. If the search context is empty or failed, say that automatic search did not return enough evidence.

Always respond with ONLY the JSON object, no other text."""


def build_molder_context(items: List[Dict[str, Any]], selected_context: str = "") -> str:
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
        return text[: limit - 1].rstrip() + "\u2026" if len(text) > limit else text

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


def should_auto_web_search(prompt: str) -> bool:
    if not MOLDER_AUTO_WEB_SEARCH:
        return False
    text = (prompt or "").lower()
    explicit = [
        "웹검색",
        "웹 검색",
        "검색해",
        "찾아봐",
        "찾아줘",
        "확인해",
        "알아봐",
        "구글",
        "github",
        "깃허브",
        "최신",
        "원래 뭐",
        "뭐하는",
        "무슨 프로젝트",
    ]
    if any(term in text for term in explicit):
        return True
    if re.search(r"\b[a-z][a-z0-9_-]*(llama|mcp|agent|sdk|server)\b", text, re.I):
        return True
    return False


def _decode_duckduckgo_url(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    if parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return html.unescape(url)


def web_search_context(query: str, limit: int = MOLDER_WEB_SEARCH_LIMIT) -> str:
    query = re.sub(r"\s+", " ", (query or "").strip())
    if not query:
        return ""
    try:
        with httpx.Client(
            timeout=MOLDER_WEB_SEARCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "AgentHarnessStudio/0.1"},
        ) as client:
            response = client.get("https://html.duckduckgo.com/html/", params={"q": query})
            response.raise_for_status()
        body = response.text
    except Exception as e:
        return f"# Web Search Context\nQuery: {query}\nSearch failed: {e}"

    results = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    for href, raw_title in pattern.findall(body):
        title = re.sub(r"<.*?>", "", raw_title)
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        url = _decode_duckduckgo_url(href)
        domain = urlparse(url).netloc
        if not title or not url:
            continue
        results.append({"title": title, "url": url, "domain": domain})
        if len(results) >= limit:
            break

    if not results:
        return f"# Web Search Context\nQuery: {query}\nNo search results parsed."

    lines = [
        "# Web Search Context",
        f"Query: {query}",
        "Use these results as external evidence. Do not overclaim beyond titles/snippets unless the URL is opened elsewhere.",
    ]
    for idx, result in enumerate(results, start=1):
        lines.append(f"{idx}. {result['title']} ({result['domain']}) - {result['url']}")
    return "\n".join(lines)


def normalize_skill_content(content: str, name: str, description: str = "") -> str:
    if not content:
        return content

    repaired = content.replace("hermese:", "hermes:")
    repaired = repaired.replace("hermes_agent:", "hermes:")
    repaired = repaired.replace("hermesAgent:", "hermes:")

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
    cleaned = strip_json_code_fence(text)
    if cleaned.lstrip().startswith("{") and '"message"' in cleaned:
        recovered = extract_json_string_field(cleaned, "message")
        if recovered:
            return recovered
    return text


@router.get("/api/llm/provider")
def get_llm_provider():
    return get_llm_provider_config()


@router.post("/api/llm/provider")
def update_llm_provider(config: Dict[str, Any] = Body(...)):
    provider = str(config.get("provider") or "Custom").strip()
    base_url = str(config.get("base_url") or "").strip()
    model = str(config.get("model") or "harness-model").strip()
    api_key = config.get("api_key")

    if not model:
        raise HTTPException(status_code=400, detail="model is required")
    if base_url and not re.match(r"^https?://", base_url):
        raise HTTPException(status_code=400, detail="base_url must start with http:// or https://")

    ENV_PATH.touch(exist_ok=True)
    updates = {
        "LLM_PROVIDER_NAME": provider,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    }
    for key, value in updates.items():
        os.environ[key] = value
        set_key(str(ENV_PATH), key, value)

    if isinstance(api_key, str) and api_key.strip():
        os.environ["LLM_API_KEY"] = api_key.strip()
        set_key(str(ENV_PATH), "LLM_API_KEY", api_key.strip())

    return get_llm_provider_config()


@router.get("/api/reference/hermes")
def hermes_reference():
    return {
        "reference_url": HERMES_AGENT_REFERENCE_URL,
        "context": HERMES_REFERENCE_CONTEXT,
        "source": "nousresearch/hermes-agent",
    }


@router.post("/api/mold")
async def mold_harness(
    prompt: str = Body(..., embed=True),
    context: str = Body("", embed=True),
    history: Optional[list] = Body(None, embed=True),
    editing_file_name: Optional[str] = Body(None, embed=True),
    editing_file_content: Optional[str] = Body(None, embed=True),
):
    raw = ""
    try:
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()

        context_str = build_molder_context(items, context)

        if editing_file_name and editing_file_content:
            context_str += f"\n\n[USER IS CURRENTLY EDITING FILE]\nFile Name: {editing_file_name}\nContent Preview:\n{editing_file_content[:5000]}"

        search_context = ""
        if should_auto_web_search(prompt):
            search_context = web_search_context(prompt)
            context_str += f"\n\n{search_context}"

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": MOLDER_SYSTEM_PROMPT},
            {"role": "system", "content": HERMES_REFERENCE_CONTEXT},
        ]

        for msg in (history or [])[-10:]:
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

        raw = await call_llm_async(messages)

        result = parse_molder_json(raw)

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
                "web_search": bool(search_context),
            }

        result = validate_molder_result(result)

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
            "web_search": bool(search_context),
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
