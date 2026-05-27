import json
import yaml
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner, mask_env_dict, mask_sensitive_mapping

class AntigravityScanner(BaseHarnessScanner):
    """Scanner to detect Antigravity harness components (~/.gemini/config/plugins and ~/.gemini/antigravity)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []

        # 1. Local Antigravity configs and MCP servers (2.0: agyhub_summaries_proto.pb 추가)
        for config_name in ["mcp_config.json", "settings.json", "antigravity_state.pbtxt", "agyhub_summaries_proto.pb"]:
            config_file = self.workspace_dir / config_name
            if not config_file.exists():
                continue
            results.append({
                "type": "Config",
                "name": config_file.name,
                "source_path": str(config_file),
                "state": "ACTIVE",
                "summary": "Antigravity configuration/state",
                "metadata": {
                    "size_bytes": config_file.stat().st_size,
                    "exists": True
                }
            })
            if config_file.suffix == ".json":
                try:
                    content = json.loads(config_file.read_text(encoding="utf-8"))
                    mcp_servers = content.get("mcpServers", {}) or content.get("mcp_servers", {})
                    if isinstance(mcp_servers, dict):
                        for mcp_name, mcp_config in mcp_servers.items():
                            if not isinstance(mcp_config, dict):
                                continue
                            transport = "http" if mcp_config.get("url") else "stdio"
                            enabled = mcp_config.get("enabled", True)
                            results.append({
                                "type": "MCP Server",
                                "name": mcp_name,
                                "source_path": str(config_file),
                                "state": "ACTIVE" if enabled else "INACTIVE",
                                "summary": f"Antigravity MCP ({transport})",
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

        # Antigravity 2.0: html_artifacts, scratch 추가
        for state_dir_name in ["knowledge", "conversations", "implicit", "brain", "context_state", "annotations", "html_artifacts", "scratch"]:
            state_dir = self.workspace_dir / state_dir_name
            if state_dir.exists():
                file_count = sum(1 for p in state_dir.iterdir() if p.is_file())
                results.append({
                    "type": "Memory State",
                    "name": state_dir_name,
                    "source_path": str(state_dir),
                    "state": "ACTIVE",
                    "summary": f"Antigravity state directory ({file_count} files)",
                    "metadata": {"dir_name": state_dir_name, "file_count": file_count}
                })

        config_dir = self.workspace_dir.parent / "config"
        plugins_dir = config_dir / "plugins"

        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                
                # Plugin Manifest
                plugin_json = plugin_dir / "plugin.json"
                if plugin_json.exists():
                    metadata = {"category": "Plugins"}
                    summary = "Antigravity plugin"
                    try:
                        content = json.loads(plugin_json.read_text(encoding="utf-8"))
                        if "description" in content:
                            summary = content["description"]
                        if "version" in content:
                            metadata["version"] = content["version"]
                    except Exception:
                        pass

                    results.append({
                        "type": "Plugin",
                        "name": plugin_dir.name,
                        "source_path": str(plugin_json),
                        "state": "ACTIVE",
                        "summary": summary,
                        "metadata": metadata
                    })
                
                # Skills
                skills_dir = plugin_dir / "skills"
                if skills_dir.exists():
                    for skill_dir in skills_dir.iterdir():
                        if not skill_dir.is_dir():
                            continue
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists():
                            metadata = {"category": "Skills", "plugin": plugin_dir.name}
                            summary = f"Skill ({plugin_dir.name})"
                            try:
                                content = skill_md.read_text(encoding="utf-8")
                                if content.startswith("---"):
                                    parts = content.split("---", 2)
                                    if len(parts) >= 3:
                                        frontmatter = yaml.safe_load(parts[1])
                                        if isinstance(frontmatter, dict):
                                            metadata.update(frontmatter)
                                            if "description" in frontmatter:
                                                summary = frontmatter["description"]
                            except Exception:
                                pass

                            results.append({
                                "type": "Skill",
                                "name": skill_dir.name,
                                "source_path": str(skill_md),
                                "state": "ACTIVE",
                                "summary": summary,
                                "metadata": metadata
                            })

                # Agents / Personas
                agents_dir = plugin_dir / "agents"
                if agents_dir.exists():
                    for agent_file in agents_dir.iterdir():
                        if agent_file.is_file():
                            results.append({
                                "type": "Skill Bundle",
                                "name": agent_file.stem,
                                "source_path": str(agent_file),
                                "state": "ACTIVE",
                                "summary": f"Agent Persona ({plugin_dir.name})",
                                "metadata": {}
                            })

        # Global Personas
        personas_dir = config_dir / "personas"
        if personas_dir.exists():
            for persona_file in personas_dir.iterdir():
                if persona_file.is_file():
                    results.append({
                        "type": "Skill Bundle",
                        "name": persona_file.stem,
                        "source_path": str(persona_file),
                        "state": "ACTIVE",
                        "summary": "Global Agent Persona",
                        "metadata": {}
                    })

        return self._finalize_items(results)
