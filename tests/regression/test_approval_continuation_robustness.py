from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.approval_continuation_robustness import (
    ApprovalContinuationRobustnessConfig,
    run_approval_continuation_robustness,
    validate_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_approval_continuation_robustness_catalog_passes_contract() -> None:
    cases_path = REPO_ROOT / "runtime" / "approval_continuation_robustness_cases.json"
    catalog = json.loads(cases_path.read_text(encoding="utf-8"))

    result = validate_catalog(catalog, cases_path=cases_path)

    assert result["status"] == "passed"


def test_approval_continuation_robustness_direct_validator_passes(tmp_path: Path) -> None:
    config = ApprovalContinuationRobustnessConfig(
        config_root=REPO_ROOT,
        output_path=tmp_path / "phase97-direct.json",
        target_roots=(str(tmp_path / "unused-a"), str(tmp_path / "unused-b")),
        include_direct=True,
        include_gateway=False,
        include_anythingllm=False,
    )

    report = run_approval_continuation_robustness(config)

    assert report["status"] == "passed"
    assert report["summary"]["direct_enabled"] is True
    assert any(check["id"] == "direct.approval_continuation" and check["status"] == "passed" for check in report["checks"])


def test_approval_continuation_robustness_catalog_rejects_missing_case() -> None:
    catalog = {
        "schema_version": 1,
        "kind": "approval_continuation_robustness_cases",
        "phase": 97,
        "cases": [{"case_id": "APR-001"}],
    }

    result = validate_catalog(catalog, cases_path=Path("runtime/approval_continuation_robustness_cases.json"))

    assert result["status"] == "failed"
    assert any("APR-002" in error for error in result["details"]["errors"])
