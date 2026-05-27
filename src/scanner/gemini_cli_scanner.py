import json
import yaml
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner, mask_env_dict, mask_sensitive_mapping

class GeminiCliScanner(BaseHarnessScanner):
    """Scanner to detect Gemini CLI harness components (~/.gemini)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Configs & MCP Servers
        seen_mcp_servers = set()
        for config_name in ["settings.json", "projects.json", "state.json", "config.yaml", "config.json", "config/mcp_config.json", "config/config.json"]:
            config_file = self.workspace_dir / config_name
            if config_file.exists():
                results.append({
                    "type": "Config",
                    "name": config_file.name,
                    "source_path": str(config_file),
                    "state": "ACTIVE",
                    "summary": f"Gemini CLI Global {config_name.split('.')[0]}",
                    "metadata": {
                        "size_bytes": config_file.stat().st_size,
                        "exists": True
                    }
                })
                
                try:
                    content = json.loads(config_file.read_text(encoding="utf-8"))
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
                                "source_path": str(config_file),
                                "state": "ACTIVE" if enabled else "INACTIVE",
                                "summary": f"Gemini MCP ({transport})",
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

        # 2. Root Context
        gemini_md = self.workspace_dir / "GEMINI.md"
        if gemini_md.exists():
            results.append({
                "type": "Root Context",
                "name": "GEMINI.md",
                "source_path": str(gemini_md),
                "state": "ACTIVE",
                "summary": "Gemini CLI Root Context",
                "metadata": {
                    "size_bytes": gemini_md.stat().st_size,
                    "exists": True
                }
            })

        # 3. Global Plugins and Skills (~/.gemini/config/plugins)
        config_dir = self.workspace_dir / "config"
        plugins_dir = config_dir / "plugins"

        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                
                # Skills within plugins
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

        # 4. Local User Skills (~/.gemini/skills)
        user_skills_dir = self.workspace_dir / "skills"
        if user_skills_dir.exists():
            for skill_dir in user_skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        results.append({
                            "type": "Skill",
                            "name": skill_dir.name,
                            "source_path": str(skill_md),
                            "state": "ACTIVE",
                            "summary": "User-defined Skill",
                            "metadata": {
                                "category": "Local Skills"
                            }
                        })

        return self._finalize_items(results)
