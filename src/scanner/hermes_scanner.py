import os
import yaml
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

# Masking patterns
SENSITIVE_KEYS = ["SECRET", "API_KEY", "TOKEN", "PASSWORD", "KEY", "CRED", "AUTH"]

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

    def scan_all(self) -> List[Dict[str, Any]]:
        results = []
        
        results.extend(self._scan_skills())
        results.extend(self._scan_memory())
        results.extend(self._scan_mcp())
        results.extend(self._scan_root_context())
        results.extend(self._scan_hooks())
        
        return results

    def _scan_skills(self) -> List[Dict[str, Any]]:
        results = []
        skills_dir = self.hermes_dir / "skills"
        
        if not skills_dir.exists():
            return results
            
        for skill_file in skills_dir.rglob("SKILL.md"):
            item = {
                "type": "Skill",
                "name": skill_file.parent.name,
                "source_path": str(skill_file),
                "state": "ACTIVE",
                "summary": "",
                "metadata": {
                    "has_references": (skill_file.parent / "references").is_dir(),
                    "has_templates": (skill_file.parent / "templates").is_dir(),
                    "has_scripts": (skill_file.parent / "scripts").is_dir()
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
                    
                    meta = frontmatter.get("metadata", {})
                    if isinstance(meta, dict):
                        hermes_meta = meta.get("hermes", {})
                        if isinstance(hermes_meta, dict):
                            item["metadata"]["tags"] = hermes_meta.get("tags", [])
                            item["metadata"]["category"] = hermes_meta.get("category", "Uncategorized")
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

        # 3. Built-in memory dir
        memory_dir = self.hermes_dir / "memory"
        if memory_dir.exists():
             results.append({
                "type": "Memory Directory",
                "name": "Built-in Memory",
                "source_path": str(memory_dir),
                "state": "ACTIVE",
                "summary": "System memory files directory",
                "metadata": {
                    "file_count": len(list(memory_dir.rglob("*")))
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
            args = details.get("args", [])
            env = details.get("env", {})
            
            # Determine transport (heuristic)
            transport = "http" if "http" in str(command) or "url" in details else "stdio"
            
            item = {
                "type": "MCP Server",
                "name": name,
                "source_path": str(self.config_path),
                "state": "ACTIVE",
                "summary": f"MCP Server ({transport})",
                "metadata": {
                    "has_command": bool(command),
                    "command": command,
                    "args_count": len(args),
                    "has_env": bool(env),
                    "transport": transport,
                    "env": mask_env_dict(env)
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
            
        # 3. system_prompt in config
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
        hooks_dir = self.hermes_dir / "hooks"
        
        if not hooks_dir.exists():
            return results
            
        for hook_file in hooks_dir.iterdir():
            if not hook_file.is_file():
                continue
                
            fname = hook_file.name.lower()
            hook_type = "unknown"
            if "pre_tool" in fname or "pre" in fname:
                hook_type = "pre_tool"
            elif "post_tool" in fname or "post" in fname:
                hook_type = "post_tool"
            elif "session_start" in fname or "start" in fname:
                hook_type = "session_start"
            elif "session_end" in fname or "end" in fname:
                hook_type = "session_end"
                
            results.append({
                "type": "Hook",
                "name": hook_file.name,
                "source_path": str(hook_file),
                "state": "ACTIVE",
                "summary": f"Hook script ({hook_type})",
                "metadata": {
                    "hook_type": hook_type,
                    "extension": hook_file.suffix,
                    "size_bytes": hook_file.stat().st_size
                }
            })
            
        return results

if __name__ == "__main__":
    scanner = HermesScanner()
    scan_results = scanner.scan_all()
    print(json.dumps(scan_results, indent=2, ensure_ascii=False))
