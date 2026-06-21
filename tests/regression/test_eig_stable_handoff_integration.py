from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_stable_handoff_integration import (
    EIGStableHandoffIntegrationConfig,
    run_eig_stable_handoff_integration,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_stable_handoff_integration_policy.json"


def test_eig_stable_handoff_integration_passes(tmp_path: Path) -> None:
    report = run_eig_stable_handoff_integration(
        EIGStableHandoffIntegrationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase304.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["required_doc_count"] >= 8
    assert report["summary"]["required_runtime_file_count"] == 4
    assert report["summary"]["required_script_count"] == 4
    assert report["summary"]["missing_marker_count"] == 0
    assert report["summary"]["phase305_ready"] is True
    assert report["scope_boundary"]["real_external_connector_execution_shipped"] is False


def test_eig_stable_handoff_integration_rejects_missing_marker(tmp_path: Path) -> None:
    policy = copy.deepcopy(json.loads(POLICY_PATH.read_text(encoding="utf-8")))
    policy["required_markers"]["README.getting-started.md"].append("marker that should not exist")
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = run_eig_stable_handoff_integration(
        EIGStableHandoffIntegrationConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "phase304.json",
        )
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "docs.marker_missing" for error in report["validation_errors"])
