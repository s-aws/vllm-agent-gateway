from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance import v1_release_candidate_decision_gate as gate
from vllm_agent_gateway.acceptance.v1_release_candidate_decision_gate import (
    V1ReleaseCandidateDecisionGateConfig,
    validate_policy,
    validate_v1_release_candidate_decision_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "v1_release_candidate_decision_gate_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        text
        or "Raw 1M-token prompt serving is not claimed\nAdvanced broad refactor orchestration is not released\nnot a production deployment\n",
        encoding="utf-8",
    )


def write_roadmap(config_root: Path, *, missing_phase: int | None = None) -> None:
    lines = []
    for phase in range(232, 244):
        lines.extend(
            [
                f"### Approved Phase {phase}: Synthetic Phase {phase}",
                "",
                "Status: Approved." if phase == missing_phase else "Status: Complete.",
                "",
            ]
        )
    write_doc(config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", "\n".join(lines))


def write_required_docs(config_root: Path, policy_value: dict) -> None:
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        write_doc(config_root / raw_path)


def write_required_reports(config_root: Path, policy_value: dict) -> None:
    for item in policy_value["required_machine_reports"]:
        payload = {
            "kind": item["expected_kind"],
            "status": item["expected_status"],
            "summary": copy.deepcopy(item.get("expected_summary", {})),
        }
        write_json(config_root / item["path"], payload)


def config_root(tmp_path: Path, *, missing_phase: int | None = None, missing_report: bool = False) -> tuple[Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    write_roadmap(root, missing_phase=missing_phase)
    write_required_docs(root, policy_value)
    if not missing_report:
        write_required_reports(root, policy_value)
    policy_path = root / "policy.json"
    write_json(policy_path, policy_value)
    return root, policy_path


def test_phase244_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase244_synthetic_ship_when_all_required_proof_and_health_pass(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = config_root(tmp_path)
    monkeypatch.setattr(gate, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_v1_release_candidate_decision_gate(
        V1ReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase244/report.json",
            markdown_output_path="runtime-state/phase244/report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] == "ship"
    assert report["blockers"] == []


def test_phase244_synthetic_hold_when_only_runtime_health_fails(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = config_root(tmp_path)
    monkeypatch.setattr(gate, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": None, "passed": False, "error": "down"})

    report = validate_v1_release_candidate_decision_gate(
        V1ReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase244/report.json",
            markdown_output_path="runtime-state/phase244/report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] == "hold"
    assert report["summary"]["runtime_health_blocker_count"] == len(policy()["required_runtime_health"])


def test_phase244_synthetic_repair_when_phase_is_incomplete(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = config_root(tmp_path, missing_phase=243)
    monkeypatch.setattr(gate, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_v1_release_candidate_decision_gate(
        V1ReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase244/report.json",
            markdown_output_path="runtime-state/phase244/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase.243.status" for item in report["blockers"])


def test_phase244_synthetic_repair_when_required_machine_report_missing(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = config_root(tmp_path, missing_report=True)
    monkeypatch.setattr(gate, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_v1_release_candidate_decision_gate(
        V1ReleaseCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase244/report.json",
            markdown_output_path="runtime-state/phase244/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["source"] == "phase242_baseline_corpus" for item in report["blockers"])


def test_phase244_project_gate_writes_report_without_requiring_live_health() -> None:
    report = validate_v1_release_candidate_decision_gate(
        V1ReleaseCandidateDecisionGateConfig(
            config_root=REPO_ROOT,
            run_live_health=False,
            require_artifacts=False,
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] in {"ship", "hold", "repair_required"}
    assert report["summary"]["phase_count"] == 12
