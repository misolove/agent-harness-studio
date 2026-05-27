import json
from typing import Dict, List, Any
from .base_scanner import BaseHarnessScanner

class CodexScanner(BaseHarnessScanner):
    """Scanner to detect Codex harness components (.codex/config.toml, AGENTS.md)."""

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Config (.codex/config.toml or ~/.codex/config.toml)
        config_toml = self.workspace_dir / "config.toml"
        if config_toml.exists():
            results.append({
                "type": "Config",
                "name": "config.toml",
                "source_path": str(config_toml),
                "state": "ACTIVE",
                "summary": "Codex configuration",
                "metadata": {
                    "size_bytes": config_toml.stat().st_size,
                    "exists": True
                }
            })

        # 2. Root Context (AGENTS.md, AGENTS.override.md)
        for md_name in ["AGENTS.md", "AGENTS.override.md"]:
            md_path = self.workspace_dir / md_name
            if md_path.exists():
                results.append({
                    "type": "Root Context",
                    "name": md_name,
                    "source_path": str(md_path),
                    "state": "ACTIVE",
                    "summary": "Codex behavioral guidance",
                    "metadata": {
                        "size_bytes": md_path.stat().st_size,
                        "exists": True
                    }
                })

        # 3. Skills & Rules
        for skill_dir_name in ["rules", "skills"]:
            skills_dir = self.workspace_dir / skill_dir_name
            if skills_dir.exists():
                for item in skills_dir.iterdir():
                    if item.is_file() and item.suffix in {".md", ".rules", ".txt", ".toml"}:
                        results.append({
                            "type": "Skill",
                            "name": item.stem,
                            "source_path": str(item),
                            "state": "ACTIVE",
                            "summary": "Codex granular rule",
                            "metadata": {
                                "category": skill_dir_name.capitalize(),
                            }
                        })
                    elif item.is_dir():
                        results.append({
                            "type": "Skill",
                            "name": item.name,
                            "source_path": str(item),
                            "state": "ACTIVE",
                            "summary": "Codex skill bundle",
                            "metadata": {
                                "category": skill_dir_name.capitalize(),
                            }
                        })

        # 4. Context / Memory (docs, specs, sqlite, jsonl)
        for docs_dir_name in ["docs", "agent_docs", "specs"]:
            docs_dir = self.workspace_dir / docs_dir_name
            if docs_dir.exists():
                md_files = [f for f in docs_dir.glob("*.md")]
                if md_files:
                    results.append({
                        "type": "Memory Directory",
                        "name": f"Codex {docs_dir_name.capitalize()}",
                        "source_path": str(docs_dir),
                        "state": "ACTIVE",
                        "summary": f"{len(md_files)} reference files",
                        "metadata": {
                            "dir_name": docs_dir_name,
                            "md_files": [f.name for f in md_files],
                        }
                    })

        for state_file in self.workspace_dir.glob("*.sqlite"):
            results.append({
                "type": "Memory State",
                "name": state_file.name,
                "source_path": str(state_file),
                "state": "ACTIVE",
                "summary": "Codex SQLite database",
                "metadata": {
                    "size_bytes": state_file.stat().st_size
                }
            })

        sqlite_dir = self.workspace_dir / "sqlite"
        if sqlite_dir.exists():
            for state_file in sqlite_dir.glob("*.db"):
                results.append({
                    "type": "Memory State",
                    "name": state_file.name,
                    "source_path": str(state_file),
                    "state": "ACTIVE",
                    "summary": "Codex SQLite database",
                    "metadata": {
                        "size_bytes": state_file.stat().st_size
                    }
                })

        for state_name in ["history.jsonl", "models_cache.json", ".codex-global-state.json", "session_index.jsonl"]:
            state_file = self.workspace_dir / state_name
            if state_file.exists():
                results.append({
                    "type": "Memory State",
                    "name": state_name,
                    "source_path": str(state_file),
                    "state": "ACTIVE",
                    "summary": "Codex memory state",
                    "metadata": {
                        "size_bytes": state_file.stat().st_size
                    }
                })

        # 5. Hooks
        hooks_file = self.workspace_dir / "hooks.json"
        if hooks_file.exists():
            try:
                content = json.loads(hooks_file.read_text(encoding="utf-8"))
                hooks_dict = content.get("hooks", {})
                for event_name, hook_list in hooks_dict.items():
                    for idx, hook_group in enumerate(hook_list):
                        matcher = hook_group.get("matcher", "all")
                        results.append({
                            "type": "Hook",
                            "name": f"{event_name}_{idx}",
                            "source_path": str(hooks_file),
                            "state": "ACTIVE",
                            "summary": f"Hook for {event_name} ({matcher})",
                            "metadata": {
                                "event": event_name,
                                "matcher": matcher
                            }
                        })
            except Exception:
                pass

        # 6. Agents
        agents_dir = self.workspace_dir / "agents"
        if agents_dir.exists():
            for agent_file in agents_dir.iterdir():
                results.append({
                    "type": "Skill Bundle",
                    "name": agent_file.name,
                    "source_path": str(agent_file),
                    "state": "ACTIVE",
                    "summary": "Codex agent",
                    "metadata": {"on_demand": True}
                })

        # 7. Plugins
        plugins_dir = self.workspace_dir / "plugins"
        if plugins_dir.exists():
            for plugin_file in plugins_dir.iterdir():
                results.append({
                    "type": "Plugin",
                    "name": plugin_file.name,
                    "source_path": str(plugin_file),
                    "state": "ACTIVE",
                    "summary": "Codex plugin",
                    "metadata": {}
                })

        return self._finalize_items(results)
