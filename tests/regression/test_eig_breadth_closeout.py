from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_breadth_closeout import (
    EIGBreadthCloseoutConfig,
    run_eig_breadth_closeout,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_breadth_closeout_policy.json"


def test_eig_breadth_closeout_offline_passes(tmp_path: Path) -> None:
    report = run_eig_breadth_closeout(
        EIGBreadthCloseoutConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase296.json",
            run_live_runtime=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["required_doc_count"] >= 15
    assert report["summary"]["required_runtime_file_count"] == 8
    assert report["summary"]["phase_report_count"] == 7
    assert report["summary"]["failed_phase_report_count"] == 0
    assert report["summary"]["coverage_missing_count"] == 0
    assert report["summary"]["source_connector_registry_changed"] is False
    assert report["summary"]["phase296_closeout_ready"] is True
    assert all(report["coverage"]["coverage"].values())


def test_eig_breadth_closeout_rejects_missing_doc_policy_entry(tmp_path: Path) -> None:
    policy = copy.deepcopy(json.loads(POLICY_PATH.read_text(encoding="utf-8")))
    policy["required_docs"] = list(policy["required_docs"]) + ["docs/does-not-exist-eig.md"]
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = run_eig_breadth_closeout(
        EIGBreadthCloseoutConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "phase296.json",
            run_live_runtime=False,
        )
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "docs.missing" for error in report["validation_errors"])
