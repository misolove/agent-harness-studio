import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "server"))

import os
os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))

from scanner.hermes_scanner import HermesScanner


def test_hermes_scanner_instantiation():
    scanner = HermesScanner()
    assert scanner.hermes_dir.exists()


def test_hermes_scanner_scan_all():
    scanner = HermesScanner()
    results = scanner.scan_all()
    assert isinstance(results, list)
    for item in results:
        assert "type" in item
        assert "name" in item
        assert "state" in item
        assert "source_path" in item
        assert "token_estimate" in item


def test_hermes_scanner_skills():
    scanner = HermesScanner()
    results = scanner._scan_skills()
    assert isinstance(results, list)
    for skill in results:
        assert skill["type"] == "Skill"
        assert skill["state"] in ("ACTIVE", "INACTIVE", "ARCHIVED", "ERROR")
        assert "metadata" in skill
        assert "category" in skill["metadata"]


def test_hermes_scanner_mcp():
    scanner = HermesScanner()
    results = scanner._scan_mcp()
    assert isinstance(results, list)
    for mcp in results:
        assert mcp["type"] == "MCP Server"
        assert "transport" in mcp["metadata"]


def test_hermes_scanner_hooks():
    scanner = HermesScanner()
    results = scanner._scan_hooks()
    assert isinstance(results, list)


def test_hermes_scanner_memory():
    scanner = HermesScanner()
    results = scanner._scan_memory()
    assert isinstance(results, list)


def test_hermes_scanner_root_context():
    scanner = HermesScanner()
    results = scanner._scan_root_context()
    assert isinstance(results, list)
    for item in results:
        assert item["type"] == "Root Context"


def test_hermes_scanner_plugins():
    scanner = HermesScanner()
    results = scanner._scan_plugins()
    assert isinstance(results, list)


def test_hermes_scanner_cron():
    scanner = HermesScanner()
    results = scanner._scan_cron()
    assert isinstance(results, list)


def test_mask_sensitive():
    from scanner.hermes_scanner import mask_sensitive_value, mask_env_dict
    assert mask_sensitive_value("API_KEY", "sk-secret") == "REDACTED"
    assert mask_sensitive_value("NORMAL_VAR", "visible") == "visible"
    env = {"API_KEY": "secret", "PORT": "8080"}
    masked = mask_env_dict(env)
    assert masked["API_KEY"] == "REDACTED"
    assert masked["PORT"] == "8080"
