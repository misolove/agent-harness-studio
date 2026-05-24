import sys
import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load project-local .env (never commit secrets)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Add src/ to path so we can import scanner
sys.path.insert(0, str(Path(__file__).parent.parent))

# Determine Harness Home — allow override for testing
DEFAULT_HERMES_HOME = Path.home() / ".hermes"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(DEFAULT_HERMES_HOME)))

print(f"=====================================")
print(f"🚀 AGENT HARNESS STUDIO STARTING")
print(f"📁 Target HERMES_HOME: {HERMES_HOME}")
print(f"=====================================")

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from scanner.hermes_scanner import HermesScanner

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

# Initialize OpenAI client for 9router
def get_llm_client():
    config_path = HERMES_HOME / "config.yaml"
    base_url = "http://127.0.0.1:20128/v1"
    api_key = "dummy" # 9router may not strictly require one, or we pull from config
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = yaml.safe_load(f)
                if c.get("base_url"):
                    base_url = c["base_url"]
                # Hermes config structure fallback
                custom = c.get("providers", {}).get("custom", {})
                for k, v in custom.items():
                    if "20128" in str(v.get("base_url")):
                        base_url = v.get("base_url")
                        api_key = v.get("api_key", api_key)
        except Exception:
            pass
            
    return OpenAI(base_url=base_url, api_key=api_key)

# Section type mapping
SECTION_TYPE_MAP: Dict[str, List[str]] = {
    "skills":  ["Skill"],
    "memory":  ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
    "mcp":     ["MCP Server"],
    "context": ["Root Context"],
    "hooks":   ["Hook"],
    "config":  ["Memory Config", "Root Context", "MCP Server"],
}

def build_response(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a standardised response envelope with a summary."""
    summary: Dict[str, int] = {}
    for item in items:
        t = item.get("type", "Unknown")
        # Group into our 6 dashboard sections
        if t == "Skill":
            summary["skills"] = summary.get("skills", 0) + 1
        elif t.startswith("Memory"):
            summary["memory"] = summary.get("memory", 0) + 1
        elif t == "MCP Server":
            summary["mcp"] = summary.get("mcp", 0) + 1
        elif t == "Root Context":
            summary["context"] = summary.get("context", 0) + 1
        elif t == "Hook":
            summary["hooks"] = summary.get("hooks", 0) + 1
        else:
            summary["config"] = summary.get("memory", 0) + summary.get("context", 0) + summary.get("mcp", 0)
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

MOLDER_SYSTEM_PROMPT = """You are a Harness Molder — an expert at designing and modifying AI agent harness configurations.

The user will describe what they want their agent to do or change. You must respond with a JSON object describing the action to take.

Your response MUST be a valid JSON object with this structure:
{
  "action": "CREATE_SKILL" | "UPDATE_SKILL" | "UPDATE_CONFIG" | "ADD_MCP" | "SUGGESTION",
  "name": "skill-or-item-name (kebab-case)",
  "description": "Short description of what this does",
  "message": "Human-readable explanation of what you're proposing",
  "content": "The full file content to create or replace (YAML frontmatter + Markdown body for skills)",
  "diff_summary": "Brief summary of changes in plain language"
}

For CREATE_SKILL: provide complete SKILL.md content with YAML frontmatter (name, description, metadata.hermes.tags, metadata.hermes.category) followed by detailed markdown instructions.
For UPDATE_SKILL: provide the updated content.
For SUGGESTION: use message field to explain what should be done manually.
For ADD_MCP: provide the MCP server config as YAML in content.

Always respond with ONLY the JSON object, no other text."""

@app.post("/api/mold")
def mold_harness(prompt: str = Body(..., embed=True)):
    """
    Chat Molder: Uses LLM to generate/modify harness items based on natural language prompt.
    Connects to local 9router (OpenAI-compatible API) for LLM inference.
    """
    raw = ""
    try:
        client = get_llm_client()
        
        # Build context from current harness state
        scanner = HermesScanner(str(HERMES_HOME))
        items = scanner.scan_all()
        
        # Summarize current harness for LLM context
        skill_names = [i["name"] for i in items if i["type"] == "Skill"][:20]
        mcp_names = [i["name"] for i in items if i["type"] == "MCP Server"]
        
        context_msg = f"""Current harness state:
- Skills installed ({len(skill_names)} shown): {', '.join(skill_names)}
- MCP servers: {', '.join(mcp_names)}

User request: {prompt}"""

        response = client.chat.completions.create(
            model="qwen",
            messages=[
                {"role": "system", "content": MOLDER_SYSTEM_PROMPT},
                {"role": "user", "content": context_msg}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        raw = response.choices[0].message.content or ""
        raw = raw.strip()
        
        # Try to parse as JSON
        # Handle markdown code blocks
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        
        result = json.loads(raw)
        
        # Build a git-style diff from content
        diff_lines = []
        if result.get("content"):
            action = result.get("action", "CREATE_SKILL")
            name = result.get("name", "unknown")
            if "SKILL" in action:
                path = f"skills/{name}/SKILL.md"
            elif "MCP" in action:
                path = "config.yaml (mcp_servers section)"
            else:
                path = f"config.yaml"
            
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
        # LLM didn't return valid JSON — return raw text as suggestion
        fallback_msg = raw if raw else "LLM response was not valid JSON"
        return {
            "status": "success",
            "action": "SUGGESTION",
            "name": "",
            "message": fallback_msg,
            "content": "",
            "diff": "",
            "diff_summary": "LLM returned non-structured output. See message.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {str(e)}")

@app.post("/api/save")
def save_item(path: str = Body(...), content: str = Body(...)):
    """Save an edited harness item (Skill, Context, Config)."""
    target_path = Path(path)
    
    # Security: only allow saving within HERMES_HOME
    if not str(target_path.resolve()).startswith(str(HERMES_HOME.resolve())):
        raise HTTPException(status_code=403, detail="Access denied: outside .hermes")

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding='utf-8')
        return {"status": "saved", "path": str(target_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/env")
def get_env():
    """Return current environment info for UI badge."""
    return {
        "hermes_home": str(HERMES_HOME),
        "is_sandbox": HERMES_HOME.name == "sandbox"
    }

@app.post("/api/web/scrape")
def web_scrape(url: str = Body(..., embed=True)):
    """
    Web Context Scraper powered by Firecrawl.

    Requires FIRECRAWL_API_KEY in the project .env or process environment.
    """
    if not url:
        return {"status": "error", "message": "URL is required"}

    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return {
            "status": "missing_api_key",
            "message": "Set FIRECRAWL_API_KEY in .env to enable real web scraping.",
            "url": url,
        }

    try:
        from firecrawl import FirecrawlApp

        app_fc = FirecrawlApp(api_key=api_key)
        scrape_fn = getattr(app_fc, "scrape_url", None) or getattr(app_fc, "scrape")
        result = scrape_fn(url, formats=["markdown"])

        # Firecrawl SDK may return dict-like or object-like results depending on version.
        if hasattr(result, "dict"):
            result_data: Dict[str, Any] = result.dict()
        elif hasattr(result, "model_dump"):
            result_data = result.model_dump()
        elif isinstance(result, dict):
            result_data = result
        else:
            result_data = {"raw": str(result)}

        data_block = result_data.get("data") if isinstance(result_data.get("data"), dict) else {}
        markdown = result_data.get("markdown") or data_block.get("markdown") or ""
        metadata = result_data.get("metadata") or data_block.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        title = metadata.get("title") or result_data.get("title") or url

        return {
            "status": "ok",
            "url": url,
            "title": title,
            "markdown": markdown,
            "metadata": metadata,
            "source": "firecrawl",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "url": url,
            "source": "firecrawl",
        }


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8766, reload=True)
