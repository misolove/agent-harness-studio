import os
import sqlite3
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
        if item.get("metadata", {}).get("prompt_injected") is False:
            return 0
        if item.get("type") == "Skill":
            metadata = item.get("metadata", {})
            payload = {
                "category": metadata.get("category"),
                "name": item.get("name"),
            }
            return max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4)
        if item.get("type") == "Memory Config":
            payload = {
                "type": item.get("type"),
                "name": item.get("name"),
                "summary": item.get("summary"),
            }
            return max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4)
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
        results.extend(self._scan_sessions())
        results.extend(self._scan_statedb())
        results.extend(self._scan_checkpoints())

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

        # 심링크 추적 시 제외할 디렉토리 (.archive는 ARCHIVED로 표시하려고 일부러 포함)
        excluded_dirs = {
            "venv", ".venv", ".git", "__pycache__", "node_modules",
            ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages",
            ".tox", ".nox", ".github", ".hub",
        }

        for source_kind, skills_dir in skill_roots:
            if not skills_dir.exists():
                continue

            # rglob은 심링크 디렉토리를 따라가지 않아 ~/.agents/skills 공유 스킬을 놓친다.
            # Hermes(iter_skill_index_files)와 동일하게 followlinks=True로 추적.
            seen_resolved = set()
            for root, dirs, files in os.walk(skills_dir, followlinks=True):
                dirs[:] = [d for d in dirs if d not in excluded_dirs]
                if "SKILL.md" not in files:
                    continue
                skill_file = Path(root) / "SKILL.md"
                try:
                    resolved = skill_file.resolve()
                except Exception:
                    resolved = skill_file
                if resolved in seen_resolved:  # 심링크 순환/중복 방지
                    continue
                seen_resolved.add(resolved)
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

        # 숨김 디렉토리(.archive 등 .으로 시작)의 스킬은 아카이브(비활성) 처리.
        # Hermes curator가 stale/archive_after_days 정책으로 옮긴 스킬들.
        is_archived = any(p.startswith(".") for p in rel_parts[:-1])

        item = {
            "type": "Skill",
            "name": name_from_path,
            "source_path": str(skill_file),
            "state": "ARCHIVED" if is_archived else "ACTIVE",
            "summary": "",
            "metadata": {
                "source": source_kind,
                "archived": is_archived,
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
            if is_archived:
                pass  # 아카이브 상태 유지 (disabled 판정보다 우선)
            elif item["name"] in global_disabled or name_from_path in global_disabled:
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
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = ""
            results.append({
                "type": "Memory Manifest",
                "name": "Manifest File",
                "source_path": str(manifest_path),
                "state": "ACTIVE",
                "summary": "Global memory manifest description",
                "metadata": {
                    "size_bytes": manifest_path.stat().st_size,
                    "content": content
                }
            })

        # 3. Memory dirs — hermes uses "memories/" (also checks legacy "memory/")
        for dir_name, label in [("memories", "Agent Memories"), ("memory", "Built-in Memory")]:
            memory_dir = self.hermes_dir / dir_name
            if not memory_dir.exists():
                continue
            md_files = [f for f in memory_dir.rglob("*.md") if f.is_file() and not f.name.endswith(".lock")]
            all_files = [f for f in memory_dir.rglob("*") if f.is_file() and f.suffix != ".lock"]
            
            md_contents = {}
            md_rel_paths = []
            for f in md_files:
                rel = str(f.relative_to(memory_dir))
                md_rel_paths.append(rel)
                try:
                    with open(f, "r", encoding="utf-8") as file_obj:
                        md_contents[rel] = file_obj.read()
                except Exception:
                    md_contents[rel] = ""
                    
            results.append({
                "type": "Memory Directory",
                "name": label,
                "source_path": str(memory_dir),
                "state": "ACTIVE",
                "summary": f"{len(md_files)}개 메모리 파일 ({dir_name}/)",
                "metadata": {
                    "dir_name": dir_name,
                    "file_count": len(all_files),
                    "md_files": md_rel_paths,
                    "md_contents": md_contents,
                }
            })

        # 4. State dir
        state_dir = self.hermes_dir / "state"
        if state_dir.exists():
            state_files = [f.name for f in state_dir.iterdir() if f.is_file() and f.name != ".DS_Store"]
            state_contents = {}
            for f in state_dir.iterdir():
                if f.is_file() and f.name != ".DS_Store":
                    try:
                        with open(f, "r", encoding="utf-8") as file_obj:
                            text = file_obj.read()
                            # 미리보기 1000자로 제한
                            state_contents[f.name] = text[:1000] + ("..." if len(text) > 1000 else "")
                    except Exception:
                        state_contents[f.name] = "<binary or unreadable>"
                        
            results.append({
                "type": "Memory State",
                "name": "State Directory",
                "source_path": str(state_dir),
                "state": "ACTIVE",
                "summary": "Persistent state files",
                "metadata": {
                    "files": state_files,
                    "contents": state_contents
                }
            })
            
        # 5. Reflections dir
        reflections_dir = self.hermes_dir / "reflections"
        if reflections_dir.exists():
            ref_files = [f for f in reflections_dir.rglob("*.md") if f.is_file()]
            ref_contents = {}
            ref_rel_paths = []
            for f in ref_files:
                rel = str(f.relative_to(reflections_dir))
                ref_rel_paths.append(rel)
                try:
                    with open(f, "r", encoding="utf-8") as file_obj:
                        text = file_obj.read()
                        ref_contents[rel] = text
                except Exception:
                    ref_contents[rel] = ""
                    
            results.append({
                "type": "Memory Directory",
                "name": "Reflections",
                "source_path": str(reflections_dir),
                "state": "ACTIVE",
                "summary": f"{len(ref_files)}개 회고 파일 (reflections/)",
                "metadata": {
                    "dir_name": "reflections",
                    "file_count": len(ref_files),
                    "md_files": ref_rel_paths,
                    "md_contents": ref_contents,
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

        # 2. Project context. Hermes loads .hermes.md/HERMES.md before AGENTS.md,
        # so the payload estimate should mirror the actual prompt builder.
        project_context_dir = self.hermes_dir / "hermes-agent"
        project_pointer = None
        for pointer_name in [".hermes.md", "HERMES.md"]:
            candidate = project_context_dir / pointer_name
            if candidate.exists():
                project_pointer = candidate
                break

        if project_pointer:
            results.append({
                "type": "Root Context",
                "name": project_pointer.name,
                "source_path": str(project_pointer),
                "state": "ACTIVE",
                "summary": "Project context pointer loaded before AGENTS.md",
                "metadata": {
                     "size_bytes": project_pointer.stat().st_size,
                     "prompt_injected": True,
                     "supersedes": "AGENTS.md",
                }
            })

        project_agents = self.hermes_dir / "hermes-agent" / "AGENTS.md"
        if project_agents.exists():
            results.append({
                "type": "Root Context",
                "name": "Project AGENTS.md",
                "source_path": str(project_agents),
                "state": "REFERENCE" if project_pointer else "ACTIVE",
                "summary": (
                    "Full project guide; read on demand when .hermes.md is insufficient"
                    if project_pointer else
                    "Project-specific agent behavior definition"
                ),
                "metadata": {
                     "size_bytes": project_agents.stat().st_size,
                     "prompt_injected": not bool(project_pointer),
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


    def _scan_sessions(self) -> List[Dict[str, Any]]:
        """state.db sessions 테이블 집계 통계를 반환."""
        state_db = self.hermes_dir / "state.db"
        if not state_db.exists():
            return []
        try:
            conn = sqlite3.connect(str(state_db))
            conn.row_factory = sqlite3.Row
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_sessions,
                    MIN(started_at) as first_session,
                    MAX(started_at) as last_session,
                    SUM(COALESCE(message_count, 0)) as total_messages,
                    SUM(COALESCE(tool_call_count, 0)) as total_tool_calls,
                    SUM(COALESCE(estimated_cost_usd, 0)) as total_cost_usd,
                    SUM(COALESCE(input_tokens, 0)) as total_input_tokens,
                    SUM(COALESCE(output_tokens, 0)) as total_output_tokens
                FROM sessions
            """).fetchone()
            models = [
                {"model": row[0], "count": row[1]}
                for row in conn.execute("""
                    SELECT model, COUNT(*) as cnt FROM sessions
                    WHERE model IS NOT NULL
                    GROUP BY model ORDER BY cnt DESC LIMIT 8
                """).fetchall()
            ]
            sources = [
                {"source": row[0], "count": row[1]}
                for row in conn.execute("""
                    SELECT source, COUNT(*) as cnt FROM sessions
                    WHERE source IS NOT NULL
                    GROUP BY source ORDER BY cnt DESC
                """).fetchall()
            ]
            recent = [
                {
                    "id": row[0],
                    "title": row[1],
                    "model": row[2],
                    "started_at": row[3],
                    "message_count": row[4],
                    "cost_usd": row[5],
                }
                for row in conn.execute("""
                    SELECT id, title, model, started_at, message_count, estimated_cost_usd
                    FROM sessions WHERE title IS NOT NULL AND title != ''
                    ORDER BY started_at DESC LIMIT 5
                """).fetchall()
            ]
            conn.close()
            total_s = int(stats["total_sessions"] or 0)
            total_m = int(stats["total_messages"] or 0)
            return [{
                "type": "Session Summary",
                "name": "Sessions",
                "source_path": str(state_db),
                "state": "ACTIVE",
                "summary": f"{total_s:,}개 세션 / {total_m:,}개 메시지",
                "metadata": {
                    "total_sessions": total_s,
                    "total_messages": total_m,
                    "total_tool_calls": int(stats["total_tool_calls"] or 0),
                    "total_cost_usd": round(float(stats["total_cost_usd"] or 0), 4),
                    "total_input_tokens": int(stats["total_input_tokens"] or 0),
                    "total_output_tokens": int(stats["total_output_tokens"] or 0),
                    "first_session": stats["first_session"],
                    "last_session": stats["last_session"],
                    "models": models,
                    "sources": sources,
                    "recent_sessions": recent,
                },
            }]
        except Exception as e:
            return [{
                "type": "Session Summary",
                "name": "Sessions",
                "source_path": str(state_db),
                "state": "ERROR",
                "summary": f"DB 읽기 오류: {e}",
                "metadata": {},
            }]

    def _scan_statedb(self) -> List[Dict[str, Any]]:
        """~/.hermes/*.db SQLite 파일들의 테이블 구조 스캔."""
        results = []
        db_descriptions = {
            "state.db": "에이전트 세션·메시지 DB",
            "kanban.db": "칸반 태스크 DB",
            "harness_studio.db": "Harness Studio 감사 로그 DB",
        }
        for db_name, description in db_descriptions.items():
            db_path = self.hermes_dir / db_name
            if not db_path.exists():
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                tables_raw = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name NOT LIKE '%_fts%'"
                    " AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                tables = []
                for (tname,) in tables_raw:
                    count = conn.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
                    cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{tname}")').fetchall()]
                    tables.append({"name": tname, "rows": count, "columns": cols[:8]})
                conn.close()
                size_bytes = db_path.stat().st_size
                total_rows = sum(t["rows"] for t in tables)
                results.append({
                    "type": "State DB",
                    "name": db_name,
                    "source_path": str(db_path),
                    "state": "ACTIVE",
                    "summary": description,
                    "metadata": {
                        "db_name": db_name,
                        "size_bytes": size_bytes,
                        "tables": tables,
                        "table_count": len(tables),
                        "total_rows": total_rows,
                    },
                })
            except Exception as e:
                results.append({
                    "type": "State DB",
                    "name": db_name,
                    "source_path": str(db_path),
                    "state": "ERROR",
                    "summary": f"DB 읽기 오류: {e}",
                    "metadata": {},
                })
        return results


    def _scan_checkpoints(self) -> List[Dict[str, Any]]:
        """~/.hermes/checkpoints/store/projects/ 프로젝트 체크포인트 스캔."""
        import datetime
        projects_dir = self.hermes_dir / "checkpoints" / "store" / "projects"
        if not projects_dir.exists():
            return []
        results = []

        def ts_to_str(ts: Any) -> Optional[str]:
            if not ts:
                return None
            try:
                return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return str(ts)

        for proj_file in sorted(projects_dir.glob("*.json")):
            try:
                data = json.loads(proj_file.read_text(encoding="utf-8"))
                proj_id = proj_file.stem
                workdir = data.get("workdir", "(알 수 없음)")
                created = ts_to_str(data.get("created_at"))
                touched = ts_to_str(data.get("last_touch"))
                results.append({
                    "type": "Checkpoint",
                    "name": proj_id[:20],
                    "source_path": str(proj_file),
                    "state": "ACTIVE",
                    "summary": workdir,
                    "metadata": {
                        "project_id": proj_id,
                        "workdir": workdir,
                        "created_at": created,
                        "last_touch": touched,
                    },
                })
            except Exception as e:
                results.append({
                    "type": "Checkpoint",
                    "name": proj_file.stem[:20],
                    "source_path": str(proj_file),
                    "state": "ERROR",
                    "summary": f"파싱 오류: {e}",
                    "metadata": {},
                })
        return results


if __name__ == "__main__":
    scanner = HermesScanner()
    scan_results = scanner.scan_all()
    print(json.dumps(scan_results, indent=2, ensure_ascii=False))
