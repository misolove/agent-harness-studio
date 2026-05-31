import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, cast

import yaml
import httpx
from openai import OpenAI
from dotenv import load_dotenv, set_key

from .config import HERMES_HOME, PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")
ENV_PATH = PROJECT_ROOT / ".env"

_HERMES_API_KEY_NAMES = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY",
    "NOUS_API_KEY", "TOGETHER_API_KEY", "GROQ_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY",
]


def get_llm_provider_config() -> Dict[str, Any]:
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "harness-model")
    if base_url:
        return {
            "provider": os.environ.get("LLM_PROVIDER_NAME", "Custom"),
            "source": "env",
            "base_url": base_url,
            "model": model,
            "api_key_set": bool(os.environ.get("LLM_API_KEY")),
            "editable": True,
        }

    config_path = HERMES_HOME / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                c = yaml.safe_load(f)
                custom = c.get("providers", {}).get("custom", {})
                for key, v in custom.items():
                    if "base_url" in v:
                        return {
                            "provider": key,
                            "source": "hermes-config",
                            "base_url": v["base_url"],
                            "model": model,
                            "api_key_set": bool(v.get("api_key")),
                            "editable": True,
                        }
        except Exception:
            pass

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return {
            "provider": "OpenAI",
            "source": "env",
            "base_url": "",
            "model": os.environ.get("LLM_MODEL", "gpt-4o"),
            "api_key_set": True,
            "editable": True,
        }

    return {
        "provider": "llm-proxy",
        "source": "default",
        "base_url": "http://localhost:20128/v1",
        "model": model,
        "api_key_set": False,
        "editable": True,
    }


def get_llm_client():
    config = get_llm_provider_config()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "dummy"
    if config["base_url"]:
        return OpenAI(base_url=config["base_url"], api_key=api_key, http_client=httpx.Client(timeout=60.0)), config["model"]
    return OpenAI(api_key=api_key, http_client=httpx.Client(timeout=60.0)), config["model"]


async def call_llm_async(messages: List[Dict[str, Any]], model: str = None, temperature: float = 0.7, max_tokens: int = 2000) -> str:
    config = get_llm_provider_config()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "dummy"
    effective_model = model or config["model"]
    base_url = config["base_url"] or "https://api.openai.com/v1"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": effective_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""


def detect_hermes_auth_path(hermes_home: Path) -> dict:
    config_path = hermes_home / "config.yaml"
    auth_json_path = hermes_home / "auth.json"
    env_path = hermes_home / ".env"

    custom_endpoint: Optional[str] = None
    aux_models_missing: List[str] = []
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            for val in (cfg.get("providers") or {}).values():
                if isinstance(val, dict) and val.get("base_url"):
                    custom_endpoint = str(val["base_url"])
                    break
            aux = cfg.get("auxiliary") or cfg.get("aux_models") or {}
            for role in ("vision", "web_extract", "compression"):
                if not aux.get(role):
                    aux_models_missing.append(role)
        except Exception:
            pass

    oauth_active = auth_json_path.exists() and auth_json_path.stat().st_size > 10

    env_keys_found: List[str] = []
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k = line.split("=", 1)[0].strip()
                        if k in _HERMES_API_KEY_NAMES:
                            env_keys_found.append(k)
        except Exception:
            pass
    for k in _HERMES_API_KEY_NAMES:
        if os.environ.get(k) and k not in env_keys_found:
            env_keys_found.append(k)

    if custom_endpoint:
        return {"auth_path": "custom", "auth_label": "Custom Endpoint",
                "auth_detail": custom_endpoint, "aux_models_missing": aux_models_missing}
    if oauth_active:
        return {"auth_path": "oauth", "auth_label": "OAuth (auth.json)",
                "auth_detail": str(auth_json_path), "aux_models_missing": aux_models_missing}
    if env_keys_found:
        return {"auth_path": "env", "auth_label": ".env API Key",
                "auth_detail": ", ".join(env_keys_found[:3]), "aux_models_missing": aux_models_missing}
    return {"auth_path": "none", "auth_label": "No Auth",
            "auth_detail": None, "aux_models_missing": aux_models_missing}


_AGENT_CONTEXT_DEFAULTS = {
    "claude": 200000,
    "gemini": 1048576,
    "antigravity": 1048576,
    "cursor": 128000,
    "openclaw": 200000,
    "studio": 128000,
}


def _detect_claude_context(ws_path: Path):
    try:
        settings = ws_path / "settings.json"
        if not settings.exists():
            return None
        data = json.loads(settings.read_text(encoding="utf-8"))
        model = (data.get("model") or "").lower()
        if not model:
            return None
        if "[1m]" in model or "opus" in model or model == "best":
            return 1000000
        if "sonnet" in model or "haiku" in model:
            return 200000
    except Exception:
        pass
    return None


def detect_context_length(ws_path: Path) -> dict:
    name = ws_path.name.lstrip(".")

    cfg_path = ws_path / "config.yaml"
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            model_cfg = cfg.get("model", {})
            model_name = model_cfg.get("default", "")
            base_url = model_cfg.get("base_url", "")

            direct = (cfg.get("context_length") or
                      model_cfg.get("context_length") or
                      cfg.get("agent", {}).get("context_length"))
            if direct:
                return {"context_length": int(direct), "source": "detected"}

            cache_path = ws_path / "context_length_cache.yaml"
            if cache_path.exists():
                cache = yaml.safe_load(cache_path.read_text(encoding="utf-8")) or {}
                cl_map = cache.get("context_lengths", {})
                key = f"{model_name}@{base_url}"
                if key in cl_map and cl_map[key]:
                    return {"context_length": int(cl_map[key]), "source": "detected"}
                for k, v in cl_map.items():
                    if k.startswith(model_name + "@") and v:
                        return {"context_length": int(v), "source": "detected"}

            if base_url:
                import re as _re
                import urllib.request as _req
                proxy_base = _re.sub(r"/v1/?$", "", base_url.rstrip("/"))
                try:
                    with _req.urlopen(f"{proxy_base}/v1/models", timeout=2) as resp:
                        data = json.loads(resp.read())
                        for m in data.get("data", []):
                            if m.get("id") == model_name:
                                cl = (m.get("context_length") or m.get("max_tokens")
                                      or m.get("context_window"))
                                if cl:
                                    return {"context_length": int(cl), "source": "detected"}
                except Exception:
                    pass
        except Exception:
            pass

    toml_path = ws_path / "config.toml"
    if toml_path.exists():
        try:
            import re as _re
            txt = toml_path.read_text(encoding="utf-8")
            m = _re.search(r"model_context_window\s*=\s*(\d+)", txt)
            if m:
                return {"context_length": int(m.group(1)), "source": "detected"}
        except Exception:
            pass

    if name == "claude":
        cl = _detect_claude_context(ws_path)
        if cl:
            return {"context_length": cl, "source": "detected"}

    if name in _AGENT_CONTEXT_DEFAULTS:
        return {"context_length": _AGENT_CONTEXT_DEFAULTS[name], "source": "estimated"}

    return {"context_length": 128000, "source": "default"}
