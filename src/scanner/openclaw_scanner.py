import json
import yaml
from pathlib import Path
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner

class OpenClawScanner(BaseHarnessScanner):
    """Scanner to detect OpenClaw harness components (~/.openclaw)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Config & MCP Servers
        config_path = self.workspace_dir / "openclaw.json"
        if config_path.exists():
            results.append({
                "type": "Config",
                "name": "openclaw.json",
                "source_path": str(config_path),
                "state": "ACTIVE",
                "summary": "OpenClaw process config (not LLM context)",
                "metadata": {
                    "size_bytes": config_path.stat().st_size,
                    "exists": True,
                    "on_demand": True
                }
            })
            
            # Check for MCP servers if any are embedded in openclaw.json
            try:
                content = json.loads(config_path.read_text(encoding="utf-8"))
                mcp_servers = content.get("mcpServers", {})
                if isinstance(mcp_servers, dict):
                    for mcp_name, mcp_config in mcp_servers.items():
                        results.append({
                            "type": "MCP Server",
                            "name": mcp_name,
                            "source_path": str(config_path),
                            "state": "ACTIVE",
                            "summary": f"MCP: {mcp_config.get('command', 'unknown')}",
                            "metadata": {"command": mcp_config.get("command")}
                        })
            except Exception:
                pass

        # 2. Root Contexts
        core_files = ["SOUL.md", "AGENTS.md", "USER.md", "MEMORY.md", "BOOTSTRAP.md", "PROMPT.md"]
        for md_name in core_files:
            md_path = self.workspace_dir / md_name
            if md_path.exists():
                results.append({
                    "type": "Root Context",
                    "name": md_name,
                    "source_path": str(md_path),
                    "state": "ACTIVE",
                    "summary": f"OpenClaw core context ({md_name})",
                    "metadata": {
                        "size_bytes": md_path.stat().st_size,
                        "exists": True
                    }
                })
            
        # 3. Skills
        for skills_name in ["skills", "plugin-skills"]:
            skills_dir = self.workspace_dir / skills_name
            if skills_dir.exists():
                for skill_dir in skills_dir.iterdir():
                    if skill_dir.is_dir():
                        results.append({
                            "type": "Skill",
                            "name": skill_dir.name,
                            "source_path": str(skill_dir),
                            "state": "ACTIVE",
                            "summary": "OpenClaw skill definition",
                            "metadata": {
                                "category": skills_name.capitalize(),
                            }
                        })

        # 4. Plugins & Agents
        for plugin_name in ["plugins", "agents"]:
            plugin_dir = self.workspace_dir / plugin_name
            if plugin_dir.exists():
                for item in plugin_dir.iterdir():
                    type_str = "Plugin" if plugin_name == "plugins" else "Skill Bundle"
                    results.append({
                        "type": type_str,
                        "name": item.name,
                        "source_path": str(item),
                        "state": "ACTIVE",
                        "summary": f"OpenClaw {type_str}",
                        "metadata": {}
                    })

        # 5. Hooks / Tools
        scripts_dir = self.workspace_dir / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.iterdir():
                if script_file.is_file():
                    results.append({
                        "type": "Hook",
                        "name": script_file.name,
                        "source_path": str(script_file),
                        "state": "ACTIVE",
                        "summary": "Executable tool/script",
                        "metadata": {
                            "executable": True,
                        }
                    })

        # 6. Memory Directory
        memory_dir = self.workspace_dir / "memory"
        if memory_dir.exists():
            md_files = [f for f in memory_dir.glob("*.md")]
            if md_files:
                results.append({
                    "type": "Memory Directory",
                    "name": "OpenClaw Memory",
                    "source_path": str(memory_dir),
                    "state": "ACTIVE",
                    "summary": f"{len(md_files)} historical memory files",
                    "metadata": {
                        "dir_name": "memory",
                        "md_files": [f.name for f in md_files],
                    }
                })

        # Memory State (delivery queues, locks, etc)
        for state_dir_name in ["delivery-queue", "session-delivery-queue", "locks"]:
            state_dir = self.workspace_dir / state_dir_name
            if state_dir.exists():
                results.append({
                    "type": "Memory State",
                    "name": state_dir_name,
                    "source_path": str(state_dir),
                    "state": "ACTIVE",
                    "summary": f"OpenClaw internal state ({state_dir_name})",
                    "metadata": {}
                })
        
        for state_file in self.workspace_dir.glob("*.sqlite"):
            results.append({
                "type": "Memory State",
                "name": state_file.name,
                "source_path": str(state_file),
                "state": "ACTIVE",
                "summary": "OpenClaw SQLite state database",
                "metadata": {
                    "size_bytes": state_file.stat().st_size
                }
            })

        # 7. Cron Jobs
        cron_dir = self.workspace_dir / "cron"
        if cron_dir.exists():
            for cron_file in cron_dir.iterdir():
                if cron_file.is_file():
                    results.append({
                        "type": "Cron Job",
                        "name": cron_file.name,
                        "source_path": str(cron_file),
                        "state": "ACTIVE",
                        "summary": "Automated background task",
                        "metadata": {}
                    })

        return self._finalize_items(results)
