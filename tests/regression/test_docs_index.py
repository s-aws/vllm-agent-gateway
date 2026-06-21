from pathlib import Path

import pytest

from vllm_agent_gateway.docs_index import docs_index_report


REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.serial


def test_docs_index_links_project_markdown_docs() -> None:
    report = docs_index_report(REPO_ROOT)

    assert report["status"] == "passed", report["orphaned_docs"]
    assert report["expected_count"] >= 1
    assert report["linked_count"] >= report["expected_count"]
