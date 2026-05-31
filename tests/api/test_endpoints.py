import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_workspaces(client):
    response = await client.get("/api/workspaces")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert all("id" in ws and "path" in ws for ws in data)


@pytest.mark.asyncio
async def test_env(client):
    response = await client.get("/api/env")
    assert response.status_code == 200
    data = response.json()
    assert "is_readonly" in data
    assert "is_git_repo" in data
    assert "context_length" in data
    assert isinstance(data["context_length"], int)
    assert data["context_length"] > 0


@pytest.mark.asyncio
async def test_scan_all(client):
    response = await client.get("/api/scan")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert data["total"] == len(data["items"])


@pytest.mark.asyncio
async def test_scan_skills_section(client):
    response = await client.get("/api/scan/skills")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 0
    for item in data["items"]:
        assert item["type"] == "Skill"


@pytest.mark.asyncio
async def test_scan_invalid_section(client):
    response = await client.get("/api/scan/invalid_section")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_scan_mcp_section(client):
    response = await client.get("/api/scan/mcp")
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["type"] == "MCP Server"


@pytest.mark.asyncio
async def test_scan_hooks_section(client):
    response = await client.get("/api/scan/hooks")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_scan_memory_section(client):
    response = await client.get("/api/scan/memory")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_scan_context_section(client):
    response = await client.get("/api/scan/context")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_audit_logs(client):
    response = await client.get("/api/audit/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)


@pytest.mark.asyncio
async def test_llm_provider(client):
    response = await client.get("/api/llm/provider")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "model" in data


@pytest.mark.asyncio
async def test_agent_runners(client):
    response = await client.get("/api/agent-runners")
    assert response.status_code == 200
    data = response.json()
    assert "runners" in data
    assert isinstance(data["runners"], list)


@pytest.mark.asyncio
async def test_readonly_save_blocked(client):
    response = await client.post("/api/save", json={
        "path": "/tmp/test_readonly",
        "content": "test"
    })
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_readonly_rollback_blocked(client):
    response = await client.post("/api/rollback", json={
        "path": str(Path.home() / ".hermes" / "config.yaml")
    })
    assert response.status_code in (403, 422)


@pytest.mark.asyncio
async def test_read_file_not_found(client):
    hermes_home = str(Path.home() / ".hermes")
    response = await client.get(f"/api/read?path={hermes_home}/nonexistent_file_12345_test")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_git_log_not_repo(client):
    response = await client.get("/api/git/log?workspace=/tmp")
    assert response.status_code == 200
    data = response.json()
    assert data["is_git_repo"] == False


@pytest.mark.asyncio
async def test_hermes_reference(client):
    response = await client.get("/api/reference/hermes")
    assert response.status_code == 200
    data = response.json()
    assert "reference_url" in data
    assert "context" in data
