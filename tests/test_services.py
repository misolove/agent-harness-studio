import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "server"))

import os
os.environ.setdefault("HERMES_HOME", str(Path(__file__).resolve().parents[1] / "tests" / "sandbox"))

from services.config import (
    get_allowed_roots,
    resolve_workspace_path,
    HARNESS_READONLY,
)
from services.git import is_git_repo


def test_allowed_roots():
    roots = get_allowed_roots()
    assert len(roots) >= 2
    paths = [str(r) for r in roots]
    assert any(".hermes" in p for p in paths)


def test_is_git_repo():
    assert is_git_repo(Path(__file__).resolve().parents[1])


def test_is_not_git_repo():
    assert not is_git_repo(Path("/tmp"))
