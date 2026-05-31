import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Git router
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_git_init_readonly(client):
    response = await client.post("/api/git/init", json={})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_git_log_not_repo(client):
    response = await client.get("/api/git/log?workspace=/tmp")
    assert response.status_code == 200
    data = response.json()
    assert data["is_git_repo"] is False
    assert isinstance(data["commits"], list)
    assert len(data["commits"]) == 0


@pytest.mark.asyncio
async def test_git_log_with_path(client):
    response = await client.get("/api/git/log?workspace=/tmp")
    assert response.status_code == 200
    data = response.json()
    assert "is_git_repo" in data
    assert "commits" in data


@pytest.mark.asyncio
async def test_git_diff_missing_hash(client):
    response = await client.get("/api/git/diff")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_git_diff_invalid_hash_non_repo(client):
    response = await client.get("/api/git/diff?commit_hash=deadbeef&workspace=/tmp")
    assert response.status_code == 200
    data = response.json()
    assert data["is_git_repo"] is False


@pytest.mark.asyncio
async def test_git_audit_non_repo(client):
    response = await client.get("/api/git/audit?workspace=/tmp")
    assert response.status_code == 200
    data = response.json()
    assert data["is_git_repo"] is False
    assert data["risk"] == "unknown"
    assert data["file_count"] == 0
    assert isinstance(data["changed_files"], list)
    assert isinstance(data["warnings"], list)


@pytest.mark.asyncio
async def test_git_rollback_readonly(client):
    hermes_home = str(Path.home() / ".hermes")
    response = await client.post("/api/git/rollback", json={
        "path": f"{hermes_home}/config.yaml",
        "commit_hash": "abc1234",
    })
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Convert router
# ---------------------------------------------------------------------------

HERMES_SKILL = """---
name: test-skill
description: A test skill for conversion
metadata:
  hermes:
    tags: [test, conversion]
    category: testing
---

# Test Skill

This is a test skill body.
"""


@pytest.mark.asyncio
async def test_convert_skill_hermes_to_claude(client):
    response = await client.post("/api/convert/skill", json={
        "content": HERMES_SKILL,
        "target": "claude",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["target"] == "claude"
    assert "---" in data["content"]
    assert "test-skill" in data["content"]


@pytest.mark.asyncio
async def test_convert_skill_roundtrip(client):
    to_claude = await client.post("/api/convert/skill", json={
        "content": HERMES_SKILL,
        "target": "claude",
    })
    assert to_claude.status_code == 200
    claude_content = to_claude.json()["content"]

    to_hermes = await client.post("/api/convert/skill", json={
        "content": claude_content,
        "target": "hermes",
    })
    assert to_hermes.status_code == 200
    hermes_content = to_hermes.json()["content"]
    assert "---" in hermes_content
    assert "test-skill" in hermes_content
    assert "hermes:" in hermes_content


@pytest.mark.asyncio
async def test_convert_skill_unsupported_target(client):
    response = await client.post("/api/convert/skill", json={
        "content": HERMES_SKILL,
        "target": "invalid_target",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_convert_skill_empty_content(client):
    response = await client.post("/api/convert/skill", json={
        "content": "",
        "target": "claude",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_convert_skill_no_frontmatter(client):
    response = await client.post("/api/convert/skill", json={
        "content": "Just plain text with no frontmatter at all.",
        "target": "claude",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_convert_inject_readonly(client):
    response = await client.post("/api/convert/skill/inject", json={
        "source_path": "/tmp/nonexistent_skill.md",
        "dry_run": True,
    })
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Mold router
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mold_missing_prompt(client):
    response = await client.post("/api/mold", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_mold_chat_mode(client):
    response = await client.post("/api/mold", json={
        "prompt": "Hello, what can you do?",
    })
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "action" in data
        assert "message" in data


@pytest.mark.asyncio
async def test_mold_with_history(client):
    response = await client.post("/api/mold", json={
        "prompt": "내 스킬 목록 보여줘",
        "history": [
            {"role": "user", "text": "안녕"},
            {"role": "assistant", "text": "안녕하세요!"},
        ],
    })
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "action" in data


@pytest.mark.asyncio
async def test_hermes_reference(client):
    response = await client.get("/api/reference/hermes")
    assert response.status_code == 200
    data = response.json()
    assert "reference_url" in data
    assert "context" in data
    assert "source" in data
    assert "hermes-agent" in data["reference_url"]


@pytest.mark.asyncio
async def test_llm_provider_get(client):
    response = await client.get("/api/llm/provider")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "model" in data


# ---------------------------------------------------------------------------
# Actions router
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_actions_archive_missing_source(client):
    response = await client.post("/api/actions/archive", json={
        "source_path": "/tmp/nonexistent_test_item_12345",
    })
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_actions_archive_no_source_path(client):
    response = await client.post("/api/actions/archive", json={})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_actions_copy_missing_source(client):
    response = await client.post("/api/actions/copy", json={
        "source_path": "/tmp/nonexistent_test_item_12345",
        "target_workspace": str(Path.home() / ".hermes"),
    })
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_actions_copy_missing_params(client):
    response = await client.post("/api/actions/copy", json={})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Files router
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_readonly_blocked(client):
    response = await client.post("/api/save", json={
        "path": "/tmp/test_readonly_routers",
        "content": "test content",
    })
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_rollback_readonly_blocked(client):
    response = await client.post("/api/rollback", json={
        "path": str(Path.home() / ".hermes" / "config.yaml"),
    })
    assert response.status_code in (403, 422)


@pytest.mark.asyncio
async def test_read_file_not_found(client):
    hermes_home = str(Path.home() / ".hermes")
    response = await client.get(f"/api/read?path={hermes_home}/nonexistent_test_file_xyz.md")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_file_allow_missing(client):
    hermes_home = str(Path.home() / ".hermes")
    response = await client.get(
        f"/api/read?path={hermes_home}/nonexistent_test_file_xyz.md&allow_missing=true"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["missing"] is True
    assert data["content"] == ""
