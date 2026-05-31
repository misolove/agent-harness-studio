import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path

SKILL_MD = """\
---
name: test-skill
description: A test skill
---
# Test Skill
Body content here.
"""


@pytest.mark.asyncio
async def test_install_skill_invalid_scheme(tmp_path, client):
    ws = tmp_path / ".hermes"
    ws.mkdir()
    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.resolve_workspace_path", return_value=ws):
        r = await client.post("/api/install/skill", json={"url": "ftp://example.com/skill.md"})
    assert r.status_code == 400
    assert "http" in r.json()["detail"]


@pytest.mark.asyncio
async def test_install_skill_no_hostname(tmp_path, client):
    ws = tmp_path / ".hermes"
    ws.mkdir()
    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.resolve_workspace_path", return_value=ws):
        r = await client.post("/api/install/skill", json={"url": "http:///skill.md"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_install_skill_readonly(client):
    r = await client.post("/api/install/skill", json={"url": "https://example.com/SKILL.md"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_install_skill_dry_run(tmp_path, client):
    ws = tmp_path / ".hermes"
    ws.mkdir()

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = SKILL_MD

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.httpx.AsyncClient", return_value=mock_client), \
         patch("routers.install.resolve_workspace_path", return_value=ws):
        r = await client.post("/api/install/skill", json={
            "url": "https://example.com/SKILL.md",
            "target_workspace": str(ws),
            "dry_run": True,
        })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "dry_run"
    assert body["slug"] == "test-skill"
    assert "path" in body
    assert body["would_overwrite"] is False


@pytest.mark.asyncio
async def test_install_skill_for_real(tmp_path, client):
    ws = tmp_path / ".hermes"
    ws.mkdir()

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = SKILL_MD

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.httpx.AsyncClient", return_value=mock_client), \
         patch("routers.install.resolve_workspace_path", return_value=ws), \
         patch("routers.install.is_git_repo", return_value=False), \
         patch("routers.install.log_audit_event"):
        r = await client.post("/api/install/skill", json={
            "url": "https://example.com/SKILL.md",
            "target_workspace": str(ws),
        })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "installed"
    assert body["slug"] == "test-skill"
    written = (ws / "skills" / "test-skill" / "SKILL.md").read_text()
    assert "test-skill" in written


@pytest.mark.asyncio
async def test_install_skill_name_override(tmp_path, client):
    ws = tmp_path / ".hermes"
    ws.mkdir()

    no_fm = "# Just a skill\nNo frontmatter here.\n"

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = no_fm

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.httpx.AsyncClient", return_value=mock_client), \
         patch("routers.install.resolve_workspace_path", return_value=ws), \
         patch("routers.install.is_git_repo", return_value=False), \
         patch("routers.install.log_audit_event"):
        r = await client.post("/api/install/skill", json={
            "url": "https://example.com/SKILL.md",
            "name": "my-custom-name",
        })
    assert r.status_code == 200
    assert r.json()["slug"] == "my-custom-name"


@pytest.mark.asyncio
async def test_install_skill_no_name_no_fm(client):
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = "# No frontmatter\n"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.httpx.AsyncClient", return_value=mock_client):
        r = await client.post("/api/install/skill", json={
            "url": "https://example.com/SKILL.md",
        })
    assert r.status_code == 400
    assert "name" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_install_skill_upstream_error(client):
    mock_resp = AsyncMock()
    mock_resp.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("routers.install.HARNESS_READONLY", False), \
         patch("routers.install.httpx.AsyncClient", return_value=mock_client):
        r = await client.post("/api/install/skill", json={
            "url": "https://example.com/missing.md",
        })
    assert r.status_code == 502


def test_normalize_github_url():
    from routers.install import _normalize_github_url

    assert "raw.githubusercontent.com" in _normalize_github_url(
        "https://github.com/owner/repo/blob/main/skills/foo/SKILL.md"
    )
    result = _normalize_github_url("https://github.com/owner/repo/tree/main/skills/foo")
    assert result.endswith("/skills/foo/SKILL.md")
    assert "raw.githubusercontent.com" in result

    assert _normalize_github_url("https://example.com/file.md") == "https://example.com/file.md"
