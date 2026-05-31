import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "server"))

import os
os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
os.environ.setdefault("HARNESS_READONLY", "1")

import pytest
from httpx import AsyncClient, ASGITransport
from src.server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
