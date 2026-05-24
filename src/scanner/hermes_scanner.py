import os
import yaml
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

# Masking patterns
SENSITIVE_KEYS = ["SECRET", "API_KEY", "TOKEN", "PASSWORD", "KEY", "CRED", "AUTH"]
TOKEN_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".sh", ".txt"}
TOKEN_EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "checkpoints",
    "cache",
    "logs",
    "node_modules",
    "sessions",
    "state",
}
TOKEN_EXCLUDED_SUFFIXES = {".bak", ".db", ".lock", ".sqlite", ".sqlite3"}
MAX_TOKEN_ESTIMATE_FILE = 50000
MAX_TOKEN_ESTIMATE_DIR = 50000
MAX_TOKEN_ESTIMATE_FILES_PER_DIR = 100
METADATA_TOKEN_ITEM_TYPES = {
    "Cron Job",
    "Hook",
    "MCP Server",
    "Plugin",
    "Skill",
    "Skill Bundle",
}

def mask_sensitive_value(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value

    key_upper = key.upper()
    if any(s in key_upper for s in SENSITIVE_KEYS):
        return "REDACTED"
    return value

def mask_env_dict(env_dict: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(env_dict, dict):
        return env_dict
    return {k: mask_sensitive_value(k, v) for k, v in env_dict.items()}

def mask_sensitive_mapping(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: mask_sensitive_mapping(mask_sensitive_value(k, v)) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_sensitive_mapping(v) for v in data]
    return data

def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

class HermesScanner:
    """Advanced scanner to detect and parse Hermes agent harness components."""

    def __init__(self, hermes_dir: Optional[str] = None):
        self.home_dir = Path.home()
        self.hermes_dir = Path(hermes_dir) if hermes_dir else self.home_dir / ".hermes"
        self.config_path = self.hermes_dir / "config.yaml"

        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _estimate_tokens_for_item(self, item: Dict[str, Any]) -> int:
        if item.get("type") in {"Memory State"}:
            return 0
        if item.get("type") in METADATA_TOKEN_ITEM_TYPES:
            payload = {
                "type": item.get("type"),
                "name": item.get("name"),
                "summary": item.get("summary"),
                "state": item.get("state"),
                "metadata": item.get("metadata", {}),
            }
            return min(1000, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4)
        source_path = item.get("source_path")
        if not source_path:
            return 0
        path = Path(source_path)
        if not path.exists():
            return 0
        if any(part in TOKEN_EXCLUDED_DIRS for part in path.parts):
            return 0
        if path.is_file():
            try:
                if path.suffix in TOKEN_EXCLUDED_SUFFIXES:
                    return 0
                if path.suffix in TOKEN_TEXT_SUFFIXES:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    return min(MAX_TOKEN_ESTIMATE_FILE, max(0, len(content) // 4))
                else:
                    return min(MAX_TOKEN_ESTIMATE_FILE, max(0, path.stat().st_size // 4))
            except Exception:
                return 0
        elif path.is_dir():
            total = 0
            scanned = 0
            try:
                for f in path.rglob("*"):
                    if scanned >= MAX_TOKEN_ESTIMATE_FILES_PER_DIR or total >= MAX_TOKEN_ESTIMATE_DIR:
                        break
                    if any(part in TOKEN_EXCLUDED_DIRS for part in f.parts):
                        continue
                    if f.is_file() and f.suffix in TOKEN_TEXT_SUFFIXES and f.suffix not in TOKEN_EXCLUDED_SUFFIXES:
                        total += min(MAX_TOKEN_ESTIMATE_FILE, len(f.read_text(encoding="utf-8", errors="ignore")) // 4)
                        scanned += 1
            except Exception:
                pass
            return min(MAX_TOKEN_ESTIMATE_DIR, total)
        return 0

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []

        results.extend(self._scan_skills())
        results.extend(self._scan_skill_bundles())
        results.extend(self._scan_memory())
        results.extend(self._scan_mcp())
        results.extend(self._scan_root_context())
        results.extend(self._scan_hooks())
        results.extend(self._scan_cron())
        results.extend(self._scan_plugins())

        for item in results:
            item["token_estimate"] = self._estimate_tokens_for_item(item)

        return results

    def _resolve_config_path(self, raw_path: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(str(raw_path)))
        path = Path(expanded)
        if not path.is_absolute():
            path = self.hermes_dir / path
        return path

    def _configured_external_skill_dirs(self) -> List[Path]:
        skills_config = self.config.get("skills", {})
        if not isinstance(skills_config, dict):
            return []
        dirs = []
        seen = set()
        for raw_dir in _as_list(skills_config.get("external_dirs")):
            if not raw_dir:
                continue
            path = self._resolve_config_path(str(raw_dir)).resolve()
            if path in seen or not path.is_dir():
                continue
            seen.add(path)
            dirs.append(path)
        return dirs

    def _disabled_skill_names(self) -> Dict[str, Any]:
        skills_config = self.config.get("skills", {})
        if not isinstance(skills_config, dict):
            return {"global": set(), "platform": {}}
        platform_disabled = skills_config.get("platform_disabled", {})
        if not isinstance(platform_disabled, dict):
            platform_disabled = {}
        return {
            "global": {str(v).strip() for v in _as_list(skills_config.get("disabled")) if str(v).strip()},
            "platform": {
                str(platform): {str(v).strip() for v in _as_list(values) if str(v).strip()}
                for platform, values in platform_disabled.items()
            },
        }

    def _scan_skills(self) -> List[Dict[str, Any]]:
        results = []
        skill_roots = [("local", self.hermes_dir / "skills")]
        skill_roots.extend(("external", path) for path in self._configured_external_skill_dirs())
        disabled = self._disabled_skill_names()

        for source_kind, skills_dir in skill_roots:
            if not skills_dir.exists():
                continue

            for skill_file in skills_dir.rglob("SKILL.md"):
                results.append(self._scan_skill_file(skill_file, skills_dir, source_kind, disabled))

        return results

    def _scan_skill_file(
        self,
        skill_file: Path,
        skills_root: Path,
        source_kind: str,
        disabled: Dict[str, Any],
    ) -> Dict[str, Any]:
        rel_parts = skill_file.relative_to(skills_root).parts
        category_from_path = "/".join(rel_parts[:-2]) if len(rel_parts) > 2 else None
        skill_dir = skill_file.parent
        name_from_path = skill_dir.name

        item = {
            "type": "Skill",
            "name": name_from_path,
            "source_path": str(skill_file),
            "state": "ACTIVE",
            "summary": "",
            "metadata": {
                "source": source_kind,
                "category": category_from_path or "Uncategorized",
                "path_category": category_from_path,
                "has_references": (skill_dir / "references").is_dir(),
                "has_templates": (skill_dir / "templates").is_dir(),
                "has_scripts": (skill_dir / "scripts").is_dir(),
            }
        }

        try:
            content = skill_file.read_text(encoding='utf-8')

            # Extract YAML frontmatter
            frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)

            if frontmatter_match:
                frontmatter_str = frontmatter_match.group(1)
                frontmatter = yaml.safe_load(frontmatter_str) or {}

                item["name"] = frontmatter.get("name", item["name"])
                item["summary"] = frontmatter.get("description", "")

                platforms = frontmatter.get("platforms", [])
                item["metadata"]["platforms"] = _as_list(platforms) if platforms else []
                item["metadata"]["version"] = frontmatter.get("version")

                meta = frontmatter.get("metadata", {})
                if isinstance(meta, dict):
                    hermes_meta = meta.get("hermes", {})
                    if isinstance(hermes_meta, dict):
                        item["metadata"]["tags"] = hermes_meta.get("tags", [])
                        item["metadata"]["category"] = hermes_meta.get("category", category_from_path or "Uncategorized")
                        item["metadata"]["requires_toolsets"] = hermes_meta.get("requires_toolsets", [])
                        item["metadata"]["fallback_for_toolsets"] = hermes_meta.get("fallback_for_toolsets", [])
                        item["metadata"]["requires_tools"] = hermes_meta.get("requires_tools", [])
                        item["metadata"]["fallback_for_tools"] = hermes_meta.get("fallback_for_tools", [])

            global_disabled = disabled.get("global", set())
            platform_disabled = disabled.get("platform", {})
            disabled_platforms = sorted(
                platform for platform, names in platform_disabled.items()
                if item["name"] in names or name_from_path in names
            )
            if item["name"] in global_disabled or name_from_path in global_disabled:
                item["state"] = "INACTIVE"
                item["metadata"]["disabled"] = True
                item["metadata"]["disabled_scope"] = "global"
            elif disabled_platforms:
                item["state"] = "INACTIVE"
                item["metadata"]["disabled"] = True
                item["metadata"]["disabled_scope"] = "platform"
                item["metadata"]["disabled_platforms"] = disabled_platforms
            else:
                item["metadata"]["disabled"] = False
        except Exception as e:
            item["state"] = "ERROR"
            item["summary"] = f"Parse error: {str(e)}"

        return item

    def _scan_skill_bundles(self) -> List[Dict[str, Any]]:
        results = []
        bundles_dir = self.hermes_dir / "skill-bundles"
        if not bundles_dir.exists():
            return results

        for bundle_file in sorted(list(bundles_dir.glob("*.yaml")) + list(bundles_dir.glob("*.yml"))):
            item = {
                "type": "Skill Bundle",
                "name": bundle_file.stem,
                "source_path": str(bundle_file),
                "state": "ACTIVE",
                "summary": "",
                "metadata": {}
            }
            try:
                data = yaml.safe_load(bundle_file.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    raise ValueError("Bundle YAML must be a mapping")
                skills = data.get("skills", [])
                if not isinstance(skills, list):
                    raise ValueError("skills must be a list")
                item["name"] = str(data.get("name") or bundle_file.stem)
                item["summary"] = data.get("description") or f"{len(skills)} skills"
                item["metadata"] = {
                    "skills": skills,
                    "skills_count": len(skills),
                    "has_instruction": bool(data.get("instruction")),
                }
            except Exception as e:
                item["state"] = "ERROR"
                item["summary"] = f"Parse error: {str(e)}"
            results.append(item)

        return results

    def _scan_memory(self) -> List[Dict[str, Any]]:
        results = []

        # 1. config.yaml -> memory
        memory_config = self.config.get("memory", {})
        if memory_config:
            results.append({
                "type": "Memory Config",
                "name": "Configured Profile",
                "source_path": str(self.config_path),
                "state": "ACTIVE",
                "summary": "User profile memory settings from config.yaml",
                "metadata": memory_config
            })

        # 2. memory_manifest.md
        manifest_path = self.hermes_dir / "memory_manifest.md"
        if manifest_path.exists():
            results.append({
                "type": "Memory Manifest",
                "name": "Manifest File",
                "source_path": str(manifest_path),
                "state": "ACTIVE",
                "summary": "Global memory manifest description",
                "metadata": {
                    "size_bytes": manifest_path.stat().st_size
                }
            })

        # 3. Memory dirs — hermes uses "memories/" (also checks legacy "memory/")
        for dir_name, label in [("memories", "Agent Memories"), ("memory", "Built-in Memory")]:
            memory_dir = self.hermes_dir / dir_name
            if not memory_dir.exists():
                continue
            md_files = [f for f in memory_dir.iterdir() if f.suffix == ".md" and f.is_file()]
            all_files = [f for f in memory_dir.rglob("*") if f.is_file() and f.suffix != ".lock"]
            results.append({
                "type": "Memory Directory",
                "name": label,
                "source_path": str(memory_dir),
                "state": "ACTIVE",
                "summary": f"{len(md_files)}개 메모리 파일 ({dir_name}/)",
                "metadata": {
                    "dir_name": dir_name,
                    "file_count": len(all_files),
                    "md_files": [f.name for f in md_files],
                }
            })

        # 4. State dir
        state_dir = self.hermes_dir / "state"
        if state_dir.exists():
            state_files = [f.name for f in state_dir.iterdir() if f.is_file()]
            results.append({
                "type": "Memory State",
                "name": "State Directory",
                "source_path": str(state_dir),
                "state": "ACTIVE",
                "summary": "Persistent state files",
                "metadata": {
                    "files": state_files
                }
            })

        return results

    def _scan_mcp(self) -> List[Dict[str, Any]]:
        results = []
        mcp_servers = self.config.get("mcp_servers", {})

        if not isinstance(mcp_servers, dict):
            return results

        for name, details in mcp_servers.items():
            if not isinstance(details, dict):
                continue

            command = details.get("command")
            url = details.get("url")
            args = details.get("args", [])
            env = details.get("env", {})
            enabled = details.get("enabled", True)
            tools = details.get("tools", {})

            transport = "http" if url else "stdio"

            state = "ACTIVE" if enabled is not False else "INACTIVE"
            state_reason = ""
            if not command and not url:
                state = "ERROR"
                state_reason = "command 또는 url 필드 없음"
            elif command and command.startswith("/"):
                cmd_path = self._resolve_config_path(command)
                if not cmd_path.exists():
                    state = "ERROR"
                    state_reason = f"파일 없음: {command}"

            item = {
                "type": "MCP Server",
                "name": name,
                "source_path": str(self.config_path),
                "state": state,
                "summary": f"MCP Server ({transport})" + (f" — {state_reason}" if state_reason else ""),
                "metadata": {
                    "has_command": bool(command),
                    "command": command,
                    "url": url,
                    "args_count": len(args),
                    "has_env": bool(env),
                    "has_headers": bool(details.get("headers")),
                    "transport": transport,
                    "enabled": enabled,
                    "state_reason": state_reason,
                    "env": mask_env_dict(env),
                    "headers": mask_sensitive_mapping(details.get("headers", {})),
                    "auth": details.get("auth"),
                    "timeout": details.get("timeout"),
                    "connect_timeout": details.get("connect_timeout"),
                    "supports_parallel_tool_calls": details.get("supports_parallel_tool_calls"),
                    "tools": tools if isinstance(tools, dict) else {},
                    "sampling": mask_sensitive_mapping(details.get("sampling", {})),
                }
            }
            results.append(item)

        return results

    def _scan_root_context(self) -> List[Dict[str, Any]]:
        results = []

        # 1. Global AGENTS.md
        global_agents = self.hermes_dir / "AGENTS.md"
        if global_agents.exists():
            results.append({
                "type": "Root Context",
                "name": "Global AGENTS.md",
                "source_path": str(global_agents),
                "state": "ACTIVE",
                "summary": "Global agent behavior definition",
                "metadata": {
                     "size_bytes": global_agents.stat().st_size
                }
            })

        # 2. Project AGENTS.md
        project_agents = self.hermes_dir / "hermes-agent" / "AGENTS.md"
        if project_agents.exists():
            results.append({
                "type": "Root Context",
                "name": "Project AGENTS.md",
                "source_path": str(project_agents),
                "state": "ACTIVE",
                "summary": "Project-specific agent behavior definition",
                "metadata": {
                     "size_bytes": project_agents.stat().st_size
                }
            })

        # 3. SOUL.md (Persona definition)
        soul_md = self.hermes_dir / "SOUL.md"
        if soul_md.exists():
            results.append({
                "type": "Root Context",
                "name": "SOUL.md",
                "source_path": str(soul_md),
                "state": "ACTIVE",
                "summary": "에이전트 페르소나 및 정체성 정의",
                "metadata": {
                    "size_bytes": soul_md.stat().st_size,
                    "exists": True
                }
            })
        else:
            results.append({
                "type": "Root Context",
                "name": "SOUL.md",
                "source_path": str(soul_md),
                "state": "INACTIVE",
                "summary": "에이전트 페르소나 설정 파일 (미구성 - 클릭하여 생성)",
                "metadata": {
                    "size_bytes": 0,
                    "exists": False
                }
            })

        # 4. system_prompt in config
        system_prompt = self.config.get("system_prompt")
        developer = self.config.get("developer")

        if system_prompt or developer:
            results.append({
                "type": "Root Context",
                "name": "Configured Prompts",
                "source_path": str(self.config_path),
                "state": "ACTIVE",
                "summary": "System/Developer prompts in config.yaml",
                "metadata": {
                    "has_system_prompt": bool(system_prompt),
                    "has_developer_section": bool(developer)
                }
            })

        return results

    def _scan_hooks(self) -> List[Dict[str, Any]]:
        results = []

        # 1. config.yaml hooks (primary — hermes stores hooks here by type)
        config_hooks = self.config.get("hooks", {})
        if isinstance(config_hooks, dict):
            for hook_type, entries in config_hooks.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    command = entry.get("command", "")
                    name = Path(command).name if command else hook_type
                    script_path = self._resolve_config_path(command) if command else None
                    state = "ACTIVE"
                    size = None
                    if script_path and script_path.exists():
                        try:
                            size = script_path.stat().st_size
                        except Exception:
                            pass
                    elif script_path:
                        state = "ERROR"
                    results.append({
                        "type": "Hook",
                        "name": name,
                        "source_path": command or str(self.config_path),
                        "state": state,
                        "summary": f"{hook_type} hook",
                        "metadata": {
                            "hook_type": hook_type,
                            "hook_system": "shell",
                            "command": command,
                            "matcher": entry.get("matcher"),
                            "timeout": entry.get("timeout"),
                            "extension": Path(command).suffix if command else "",
                            "size_bytes": size,
                        }
                    })

        # 2. Gateway hooks: hooks/<name>/HOOK.yaml + handler.py
        hooks_dir = self.hermes_dir / "hooks"
        if hooks_dir.exists():
            for hook_dir in hooks_dir.iterdir():
                if not hook_dir.is_dir():
                    continue
                manifest = hook_dir / "HOOK.yaml"
                handler = hook_dir / "handler.py"
                if not manifest.exists():
                    continue
                try:
                    meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                    if not isinstance(meta, dict):
                        raise ValueError("HOOK.yaml must be a mapping")
                    events = meta.get("events", [])
                    if not isinstance(events, list):
                        events = [events]
                    state = "ACTIVE" if handler.exists() else "ERROR"
                    results.append({
                        "type": "Hook",
                        "name": meta.get("name", hook_dir.name),
                        "source_path": str(manifest),
                        "state": state,
                        "summary": meta.get("description") or f"Gateway hook ({len(events)} events)",
                        "metadata": {
                            "hook_system": "gateway",
                            "events": events,
                            "events_count": len(events),
                            "handler_path": str(handler),
                            "has_handler": handler.exists(),
                        }
                    })
                except Exception as e:
                    results.append({
                        "type": "Hook",
                        "name": hook_dir.name,
                        "source_path": str(manifest),
                        "state": "ERROR",
                        "summary": f"Parse error: {e}",
                        "metadata": {"hook_system": "gateway"},
                    })

            # 3. Legacy file-drop hooks
            for hook_file in hooks_dir.iterdir():
                if not hook_file.is_file():
                    continue
                fname = hook_file.name.lower()
                hook_type = "unknown"
                if "pre_tool" in fname or "pre" in fname:
                    hook_type = "pre_tool_call"
                elif "post_tool" in fname or "post" in fname:
                    hook_type = "post_tool_call"
                elif "session_start" in fname or "start" in fname:
                    hook_type = "session_start"
                elif "session_end" in fname or "end" in fname:
                    hook_type = "session_end"
                results.append({
                    "type": "Hook",
                    "name": hook_file.name,
                    "source_path": str(hook_file),
                    "state": "ACTIVE",
                    "summary": f"{hook_type} hook",
                    "metadata": {
                        "hook_type": hook_type,
                        "hook_system": "file",
                        "command": str(hook_file),
                        "matcher": None,
                        "timeout": None,
                        "extension": hook_file.suffix,
                        "size_bytes": hook_file.stat().st_size,
                    }
                })

        return results

    def _scan_cron(self) -> List[Dict[str, Any]]:
        results = []
        jobs_path = self.hermes_dir / "cron" / "jobs.json"
        if not jobs_path.exists():
            return results

        try:
            with open(jobs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return results

        jobs = data if isinstance(data, list) else data.get("jobs", [])
        for job in jobs:
            if not isinstance(job, dict):
                continue
            state_val = job.get("state", "unknown")
            enabled = job.get("enabled", True)
            if not enabled and state_val == "unknown":
                state_val = "disabled"
            state = "ACTIVE" if state_val in ("scheduled", "running") else "PAUSED" if state_val == "paused" else "DONE" if state_val == "completed" else state_val.upper()
            results.append({
                "type": "Cron Job",
                "name": job.get("name", job.get("id", "Unknown")),
                "source_path": str(jobs_path),
                "state": state,
                "summary": f"{job.get('schedule_display', '')} — last: {job.get('last_status', 'n/a')}",
                "metadata": {
                    "id": job.get("id"),
                    "schedule": job.get("schedule_display", ""),
                    "enabled": enabled,
                    "cron_state": state_val,
                    "last_status": job.get("last_status"),
                    "last_error": job.get("last_error"),
                    "last_run_at": job.get("last_run_at"),
                    "next_run_at": job.get("next_run_at"),
                    "completed_count": (job.get("repeat") or {}).get("completed", 0),
                }
            })

        return results

    def _scan_plugins(self) -> List[Dict[str, Any]]:
        results = []
        plugins_dir = self.hermes_dir / "plugins"
        if not plugins_dir.exists():
            return results

        for entry in plugins_dir.iterdir():
            if not entry.is_dir():
                continue
            manifest = entry / "plugin.yaml"
            if not manifest.exists():
                continue
            try:
                with open(manifest, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
            except Exception as e:
                results.append({
                    "type": "Plugin",
                    "name": entry.name,
                    "source_path": str(manifest),
                    "state": "ERROR",
                    "summary": f"Parse error: {e}",
                    "metadata": {}
                })
                continue

            tools = _as_list(meta.get("provides_tools"))
            provides_hooks = _as_list(meta.get("provides_hooks"))
            hooks = _as_list(meta.get("hooks"))
            all_hooks = provides_hooks + hooks
            results.append({
                "type": "Plugin",
                "name": meta.get("name", entry.name),
                "source_path": str(manifest),
                "state": "ACTIVE",
                "summary": meta.get("description", ""),
                "metadata": {
                    "version": meta.get("version", ""),
                    "author": meta.get("author", ""),
                    "kind": meta.get("kind", ""),
                    "platforms": meta.get("platforms", []),
                    "tools_count": len(tools),
                    "hooks_count": len(all_hooks),
                    "provides_tools": tools,
                    "provides_hooks": provides_hooks,
                    "hooks": hooks,
                }
            })

        return results


if __name__ == "__main__":
    scanner = HermesScanner()
    scan_results = scanner.scan_all()
    print(json.dumps(scan_results, indent=2, ensure_ascii=False))
