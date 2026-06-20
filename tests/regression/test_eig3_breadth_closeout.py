from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig3_breadth_closeout import (
    EIG3BreadthCloseoutConfig,
    run_eig3_breadth_closeout,
)
from vllm_agent_gateway.acceptance.eig3_sensitive_data import read_json_object


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig3_breadth_closeout_policy.json"


def test_eig3_breadth_closeout_no_live_passes(tmp_path: Path) -> None:
    report = run_eig3_breadth_closeout(
        EIG3BreadthCloseoutConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase303.json",
            run_live_runtime=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["required_doc_count"] >= 10
    assert report["summary"]["required_runtime_file_count"] == 6
    assert report["summary"]["failed_phase_report_count"] == 0
    assert report["summary"]["phase303_closeout_ready"] is True


def test_eig3_breadth_closeout_rejects_missing_doc_policy_entry(tmp_path: Path) -> None:
    policy = copy.deepcopy(read_json_object(POLICY_PATH))
    policy["required_docs"] = list(policy["required_docs"]) + ["docs/does-not-exist-eig3.md"]
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = run_eig3_breadth_closeout(
        EIG3BreadthCloseoutConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "phase303.json",
            run_live_runtime=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "failed"
    assert any(error["id"] == "docs.missing" for error in report["validation_errors"])
