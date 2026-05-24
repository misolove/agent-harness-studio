"""
Agent Harness Studio - FastAPI Backend
Serves scan results from HermesScanner via REST API.
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add src/ to path so we can import scanner
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
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
            summary["config"] = summary.get("config", 0) + 1

    return {"summary": summary, "items": items, "total": len(items)}


@app.get("/api/scan")
def scan_all():
    """Return full harness scan results."""
    try:
        scanner = HermesScanner()
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
        scanner = HermesScanner()
        all_items = scanner.scan_all()
        allowed_types = SECTION_TYPE_MAP[section]
        filtered = [i for i in all_items if i.get("type") in allowed_types]
        return build_response(filtered)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=True)
