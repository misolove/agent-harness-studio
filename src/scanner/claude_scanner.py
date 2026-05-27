import json
import yaml
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner, mask_env_dict, mask_sensitive_mapping

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
        seen_mcp_servers = set()
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
                
                try:
                    content = json.loads(settings_path.read_text(encoding="utf-8"))
                    mcp_servers = content.get("mcpServers", {}) or content.get("mcp_servers", {})
                    if isinstance(mcp_servers, dict):
                        for mcp_name, mcp_config in mcp_servers.items():
                            if mcp_name in seen_mcp_servers or not isinstance(mcp_config, dict):
                                continue
                            seen_mcp_servers.add(mcp_name)
                            transport = "http" if mcp_config.get("url") else "stdio"
                            enabled = mcp_config.get("enabled", True)
                            results.append({
                                "type": "MCP Server",
                                "name": mcp_name,
                                "source_path": str(settings_path),
                                "state": "ACTIVE" if enabled else "INACTIVE",
                                "summary": f"Claude MCP ({transport})",
                                "metadata": {
                                    "transport": transport,
                                    "command": mcp_config.get("command"),
                                    "args": mcp_config.get("args", []),
                                    "url": mcp_config.get("url"),
                                    "env": mask_env_dict(mcp_config.get("env", {})),
                                    "raw": mask_sensitive_mapping(mcp_config),
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
                            "metadata": {"category": skill_folder, "skill_id": rule_file.stem}
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
                                "metadata": {"category": skill_folder, "skill_id": rule_file.name}
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

        # 6. Commands & Plugins — commands는 Slash Command, plugins는 Plugin으로 분리
        for plugin_folder in ["commands", "plugins"]:
            commands_dir = claude_dir / plugin_folder
            if commands_dir.exists():
                item_type = "Command" if plugin_folder == "commands" else "Plugin"
                for cmd_file in commands_dir.iterdir():
                    if cmd_file.is_file() or cmd_file.is_dir():
                        results.append({
                            "type": item_type,
                            "name": cmd_file.stem,
                            "source_path": str(cmd_file),
                            "state": "ACTIVE",
                            "summary": f"Slash command" if item_type == "Command" else "Plugin extension",
                            "metadata": {"folder": plugin_folder}
                        })

        # 7. Agents — Claude Code 공식 명칭은 Subagent (not Skill Bundle)
        agents_dir = claude_dir / "agents"
        if agents_dir.exists():
            for agent_file in agents_dir.rglob("*.md"):
                if not agent_file.is_file():
                    continue
                relative_path = agent_file.relative_to(agents_dir)
                results.append({
                    "type": "Subagent",
                    "name": agent_file.stem,
                    "source_path": str(agent_file),
                    "state": "ACTIVE",
                    "summary": "Claude Code subagent persona",
                    "metadata": {
                        "on_demand": True,
                        "subagent_type": agent_file.stem,
                        "relative_path": str(relative_path),
                    }
                })

        return self._finalize_items(results)
