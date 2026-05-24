import json
import yaml
from pathlib import Path
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner

class ClaudeScanner(BaseHarnessScanner):
    """Scanner to detect Claude Code harness components (~/.claude or project/.claude)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Root Context (CLAUDE.md & CLAUDE.local.md & CLAUDE-omc.md)
        for md_name in ["CLAUDE.md", "CLAUDE.local.md", "CLAUDE-omc.md"]:
            md_path = self.workspace_dir / md_name
            if md_path.exists():
                results.append({
                    "type": "Root Context",
                    "name": md_name,
                    "source_path": str(md_path),
                    "state": "ACTIVE",
                    "summary": f"Claude Code project context ({md_name})",
                    "metadata": {
                        "size_bytes": md_path.stat().st_size,
                        "exists": True
                    }
                })
        
        claude_dir = self.workspace_dir / ".claude"
        if not claude_dir.exists():
            claude_dir = self.workspace_dir

        # 2. Config & MCP Servers
        for config_name in ["settings.json", "settings.local.json", "mcp.json"]:
            settings_path = claude_dir / config_name
            if settings_path.exists():
                results.append({
                    "type": "Config",
                    "name": config_name,
                    "source_path": str(settings_path),
                    "state": "ACTIVE",
                    "summary": "Claude settings/config",
                    "metadata": {
                        "size_bytes": settings_path.stat().st_size,
                        "exists": True
                    }
                })
                
                # Extract MCP servers
                if config_name == "mcp.json":
                    try:
                        content = json.loads(settings_path.read_text(encoding="utf-8"))
                        mcp_servers = content.get("mcpServers", {})
                        for mcp_name, mcp_config in mcp_servers.items():
                            results.append({
                                "type": "MCP Server",
                                "name": mcp_name,
                                "source_path": str(settings_path),
                                "state": "ACTIVE",
                                "summary": f"MCP: {mcp_config.get('command', 'unknown')}",
                                "metadata": {
                                    "command": mcp_config.get("command")
                                }
                            })
                    except Exception:
                        pass

        # 3. Rules & Skills
        for skill_folder in ["rules", "skills"]:
            rules_dir = claude_dir / skill_folder
            if rules_dir.exists():
                for rule_file in rules_dir.iterdir():
                    if rule_file.is_file() and rule_file.suffix == ".md":
                        results.append({
                            "type": "Skill",
                            "name": rule_file.stem,
                            "source_path": str(rule_file),
                            "state": "ACTIVE",
                            "summary": "Claude contextual rule/skill",
                            "metadata": {"category": skill_folder}
                        })
                    elif rule_file.is_dir():
                        skill_md = rule_file / "SKILL.md"
                        if skill_md.exists():
                            results.append({
                                "type": "Skill",
                                "name": rule_file.name,
                                "source_path": str(skill_md),
                                "state": "ACTIVE",
                                "summary": "Claude structured skill",
                                "metadata": {"category": skill_folder}
                            })

        # 4. Hooks
        hooks_dir = claude_dir / "hooks"
        if hooks_dir.exists():
            for hook_file in hooks_dir.iterdir():
                if hook_file.is_file():
                    results.append({
                        "type": "Hook",
                        "name": hook_file.name,
                        "source_path": str(hook_file),
                        "state": "ACTIVE",
                        "summary": "Lifecycle hook script",
                        "metadata": {
                            "executable": True,
                        }
                    })

        # 5. Memory
        memory_dir = claude_dir / "agent-memory"
        if not memory_dir.exists():
            memory_dir = claude_dir / "memory"
        if memory_dir.exists():
            md_files = [f for f in memory_dir.iterdir() if f.suffix == ".md" and f.is_file()]
            if md_files:
                results.append({
                    "type": "Memory Directory",
                    "name": "Claude Memory",
                    "source_path": str(memory_dir),
                    "state": "ACTIVE",
                    "summary": f"{len(md_files)} memory files",
                    "metadata": {
                        "dir_name": memory_dir.name,
                        "md_files": [f.name for f in md_files],
                    }
                })

        # Memory State (jsonl, stats)
        for state_file_name in ["history.jsonl", ".session-stats.json", "stats-cache.json"]:
            state_file = claude_dir / state_file_name
            if state_file.exists():
                results.append({
                    "type": "Memory State",
                    "name": state_file_name,
                    "source_path": str(state_file),
                    "state": "ACTIVE",
                    "summary": "Claude runtime memory state",
                    "metadata": {
                        "size_bytes": state_file.stat().st_size
                    }
                })

        # 6. Commands (Plugins) & Plugins
        for plugin_folder in ["commands", "plugins"]:
            commands_dir = claude_dir / plugin_folder
            if commands_dir.exists():
                for cmd_file in commands_dir.iterdir():
                    if cmd_file.is_file() or cmd_file.is_dir():
                        results.append({
                            "type": "Plugin",
                            "name": cmd_file.stem,
                            "source_path": str(cmd_file),
                            "state": "ACTIVE",
                            "summary": f"Custom {plugin_folder}",
                            "metadata": {}
                        })

        # 7. Agents (Skill Bundles)
        agents_dir = claude_dir / "agents"
        if agents_dir.exists():
            for agent_file in agents_dir.iterdir():
                results.append({
                    "type": "Skill Bundle",
                    "name": agent_file.stem,
                    "source_path": str(agent_file),
                    "state": "ACTIVE",
                    "summary": "Subagent persona",
                    "metadata": {}
                })

        for item in results:
            item["token_estimate"] = self._estimate_tokens_for_item(item)

        return results
