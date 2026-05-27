import json
import yaml
from pathlib import Path
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner

class CursorScanner(BaseHarnessScanner):
    """Scanner to detect Cursor harness components (.cursorrules, .cursor/rules/*.mdc)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Root Context (.cursorrules)
        cursorrules = self.workspace_dir / ".cursorrules"
        if cursorrules.exists():
            results.append({
                "type": "Root Context",
                "name": ".cursorrules",
                "source_path": str(cursorrules),
                "state": "ACTIVE",
                "summary": "Cursor legacy root rules",
                "metadata": {
                    "size_bytes": cursorrules.stat().st_size,
                    "exists": True
                }
            })
            
        # 2. Modular Rules (.cursor/rules/*.mdc)
        candidate_rule_dirs = [self.workspace_dir / ".cursor" / "rules", self.workspace_dir / "rules"]
        seen_rule_dirs = set()
        for rules_dir in candidate_rule_dirs:
            if not rules_dir.exists() or rules_dir in seen_rule_dirs:
                continue
            seen_rule_dirs.add(rules_dir)
            for rule_file in rules_dir.glob("*.mdc"):
                metadata = {"category": "MDC Rules"}
                summary = "Modular Cursor Rule"
                try:
                    content = rule_file.read_text(encoding="utf-8")
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
                    "name": rule_file.stem,
                    "source_path": str(rule_file),
                    "state": "ACTIVE",
                    "summary": summary,
                    "metadata": metadata
                })

        # 3. Global Skills (skills-cursor)
        for skills_name in ["skills-cursor", "skills"]:
            global_skills = self.workspace_dir / skills_name
            if global_skills.exists():
                for skill_dir in global_skills.iterdir():
                    if skill_dir.is_dir():
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists():
                            metadata = {"category": "Global Skills"}
                            summary = "Cursor Global Skill"
                            try:
                                content = skill_md.read_text(encoding="utf-8")
                                if content.startswith("---"):
                                    parts = content.split("---", 2)
                                    if len(parts) >= 3:
                                        frontmatter = yaml.safe_load(parts[1])
                                        if isinstance(frontmatter, dict):
                                            metadata.update(frontmatter)
                                            summary = frontmatter.get("description", summary)
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

        # 4. Plugins
        for plugins_name in ["plugins", "extensions"]:
            plugins_dir = self.workspace_dir / plugins_name
            if plugins_dir.exists():
                for plugin_dir in plugins_dir.iterdir():
                    if plugin_dir.is_dir():
                        results.append({
                            "type": "Plugin",
                            "name": plugin_dir.name,
                            "source_path": str(plugin_dir),
                            "state": "ACTIVE",
                            "summary": "Cursor Global Plugin/Extension",
                            "metadata": {}
                        })

        # 5. Config and State
        for config_name in ["argv.json", "ide_state.json"]:
            config_file = self.workspace_dir / config_name
            if config_file.exists():
                item_type = "Config" if config_name == "argv.json" else "Memory State"
                results.append({
                    "type": item_type,
                    "name": config_file.name,
                    "source_path": str(config_file),
                    "state": "ACTIVE",
                    "summary": f"Cursor {item_type}",
                    "metadata": {
                        "size_bytes": config_file.stat().st_size
                    }
                })

        return self._finalize_items(results)
