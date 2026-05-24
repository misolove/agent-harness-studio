import os
import yaml
import json
from pathlib import Path
from datetime import datetime

class HermesScanner:
    """A prototype scanner to detect and parse Hermes agent harness components."""
    
    def __init__(self):
        self.home_dir = Path.home()
        self.hermes_dir = self.home_dir / ".hermes"
        
    def scan_all(self):
        print(f"[*] Starting Harness Scan for Hermes Agent at {self.hermes_dir}")
        
        # 1. Config
        self._scan_config()
        
        # 2. Skills
        self._scan_skills()
        
        # 3. MCP Servers
        self._scan_mcp()

        # 4. Built-in Memory (System memory files)
        self._scan_memory()
        
        print("[*] Scan Complete.")
        
    def _scan_config(self):
        print("\n--- [CONFIG] ---")
        config_path = self.hermes_dir / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    provider = config.get('provider', 'unknown')
                    model = config.get('model', 'unknown')
                    print(f"✅ Found config.yaml: Active Model = {provider}/{model}")
            except Exception as e:
                print(f"❌ Error parsing config.yaml: {e}")
        else:
            print("⚠️ config.yaml not found.")
            
    def _scan_skills(self):
        print("\n--- [SKILLS] ---")
        skills_dir = self.hermes_dir / "skills"
        if skills_dir.exists():
            skill_files = list(skills_dir.rglob("SKILL.md"))
            print(f"✅ Found {len(skill_files)} installed skills.")
            for sf in skill_files[:3]:  # preview up to 3
                print(f"  - {sf.parent.name}")
            if len(skill_files) > 3:
                print(f"  - ...and {len(skill_files) - 3} more.")
        else:
            print("⚠️ Skills directory not found.")
            
    def _scan_mcp(self):
        print("\n--- [MCP SERVERS] ---")
        config_path = self.hermes_dir / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                mcp = config.get('mcp_servers', {})
                if mcp:
                    print(f"✅ Found {len(mcp)} MCP servers configured.")
                    for name, details in list(mcp.items())[:3]:
                        print(f"  - {name} (command: {details.get('command', 'unknown')})")
                else:
                    print("⚠️ No MCP servers found in config.yaml.")

    def _scan_memory(self):
        print("\n--- [MEMORY] ---")
        # Just check for standard locations (like memory_manifest.md or similar)
        manifest = self.hermes_dir / "memory_manifest.md"
        if manifest.exists():
            print(f"✅ Found memory_manifest.md ({os.path.getsize(manifest)} bytes)")
        else:
            print("⚠️ memory_manifest.md not found.")

if __name__ == "__main__":
    scanner = HermesScanner()
    scanner.scan_all()
