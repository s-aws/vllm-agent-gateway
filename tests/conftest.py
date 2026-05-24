from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_TMP_ROOT = REPO_ROOT / ".tmp_pytest"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "test"


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """Use a repo-local temp root because some Windows temp dirs are locked down."""

    LOCAL_TMP_ROOT.mkdir(exist_ok=True)
    path = LOCAL_TMP_ROOT / f"{safe_name(request.node.name)}-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
