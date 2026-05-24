import json
import yaml
from pathlib import Path
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner

class AntigravityScanner(BaseHarnessScanner):
    """Scanner to detect Antigravity harness components (~/.gemini/config/plugins and ~/.gemini/antigravity)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        config_dir = self.workspace_dir.parent / "config"
        plugins_dir = config_dir / "plugins"

        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                
                # 1. Plugin Manifest
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
                
                # 2. Skills
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

                # 3. Agents / Personas
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

        # 4. Global Personas
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

        for item in results:
            item["token_estimate"] = self._estimate_tokens_for_item(item)

        return results
