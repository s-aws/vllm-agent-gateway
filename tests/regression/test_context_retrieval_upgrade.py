from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.context_retrieval_upgrade import (
    ContextRetrievalUpgradeConfig,
    validate_catalog,
    validate_context_retrieval_upgrade,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "runtime" / "context_retrieval_upgrade_cases.json"


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def make_coinbase_like_target(tmp_path: Path) -> Path:
    target = tmp_path / "coinbase-like"
    write_text(
        target / "core" / "stealth_order_manager.py",
        "class StealthOrderManager:\n"
        "    def find_stealth_order_by_placed_order_id(self, placed_order_id):\n"
        "        return placed_order_id\n",
    )
    write_text(target / "configuration.py", "COINBASE_API_KEY = 'test'\n")
    write_text(
        target / "tests" / "unit" / "test_order_id_and_followup_rules.py",
        "def test_find_stealth_order_by_placed_order_id():\n"
        "    assert 'placed_order_id'\n",
    )
    write_text(target / "README.md", "# Coinbase-like fixture\n")
    return target


def test_context_retrieval_upgrade_catalog_passes_contract() -> None:
    catalog = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    checks = validate_catalog(catalog, cases_path=CASES_PATH)
    assert checks[0]["status"] == "passed"


def test_context_retrieval_upgrade_catalog_rejects_missing_context_sources() -> None:
    catalog = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    broken = copy.deepcopy(catalog)
    broken["cases"][0]["expected_context_sources"] = []
    checks = validate_catalog(broken, cases_path=CASES_PATH)
    assert checks[0]["status"] == "failed"
    assert "expected_context_sources" in json.dumps(checks[0]["details"]["errors"])


def test_context_retrieval_upgrade_direct_cases_pass(tmp_path: Path) -> None:
    coinbase_target = make_coinbase_like_target(tmp_path)
    output_path = tmp_path / "context-report.json"
    report = validate_context_retrieval_upgrade(
        ContextRetrievalUpgradeConfig(
            config_root=REPO_ROOT,
            cases_path=CASES_PATH,
            output_path=output_path,
            target_roots=(str(coinbase_target),),
            include_direct=True,
            include_gateway=False,
            include_anythingllm=False,
            include_port_health=False,
        )
    )
    assert report["status"] == "passed"
    assert output_path.exists()
    assert report["summary"]["failed_check_ids"] == []
    assert report["generated_fixtures"]["non_coinbase"]
    assert report["generated_fixtures"]["unsupported_empty"]
