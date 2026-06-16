from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance import large_context_500k_candidate_decision_gate as phase276
from vllm_agent_gateway.acceptance.large_context_500k_candidate_decision_gate import (
    DEFAULT_POLICY_PATH,
    LargeContext500kCandidateDecisionGateConfig,
    read_json_object,
    validate_large_context_500k_candidate_decision_gate,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        text
        or "\n".join(
            [
                "500k-token project usability candidate",
                "384k stable",
                "raw 500k prompt",
                "does not promote 500k to stable",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_roadmap(config_root: Path, *, missing_phase: int | None = None) -> None:
    lines = []
    for phase in range(270, 276):
        lines.extend(
            [
                f"### Approved Phase {phase}: Synthetic Phase {phase}",
                "",
                "Status: Approved." if phase == missing_phase else "Status: Complete.",
                "",
            ]
        )
    write_doc(config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", "\n".join(lines))


def phase275_report(**summary_overrides: object) -> dict:
    summary = {
        "decision": "phase275_clean_clone_500k_candidate_ready",
        "error_count": 0,
        "gate_count": 7,
        "passed_gate_count": 7,
        "controller_preflight_status": "passed",
        "controller_clone_root_allowed": True,
        "phase273_response_count": 18,
        "phase273_gateway_response_count": 9,
        "phase273_anythingllm_response_count": 9,
        "phase273_critical_or_high_finding_count": 0,
        "phase273_json_default_parity_status": "passed",
        "phase274_decision": "no_repair_required",
        "phase274_phase275_ready": True,
        "runtime_state_ignored": True,
        "source_branch": "codex/m14-release-clone-proof",
        "source_remote_origin_url": "https://github.com/s-aws/vllm-agent-gateway.git",
        "source_dirty_line_count_before": 0,
        "source_dirty_line_count_after": 0,
        "phase276_ready": True,
    }
    summary.update(summary_overrides)
    return {
        "kind": "large_context_500k_clean_clone_replay_report",
        "status": "passed",
        "decision": "phase275_clean_clone_500k_candidate_ready",
        "summary": summary,
        "gates": {
            "controller_preflight": {"status": "passed", "summary": {}},
            "docs_index": {"status": "passed", "summary": {}},
            "phase270_candidate_rebaseline": {"status": "passed", "summary": {}},
            "phase271_fixture_index_readiness": {"status": "passed", "summary": {}},
            "phase272_stale_index_rejection": {"status": "passed", "summary": {}},
            "phase273_live_acceptance": {
                "status": "passed",
                "summary": {
                    "candidate_estimated_project_tokens": 500000,
                    "raw_prompt_stuffing_allowed": False,
                    "strategy_ids": [
                        "artifact_paging",
                        "chunked_investigation",
                        "refusal",
                        "retrieval",
                        "summarization",
                    ],
                },
            },
            "phase274_answer_quality_repair": {"status": "passed", "summary": {}},
        },
    }


def config_root(
    tmp_path: Path,
    *,
    missing_phase: int | None = None,
    missing_phase275: bool = False,
    phase275_summary_overrides: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    write_roadmap(root, missing_phase=missing_phase)
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        write_doc(root / raw_path)
    phase275_path = root / "runtime-state" / "phase275" / "phase275-report.json"
    if not missing_phase275:
        phase276.write_json(phase275_path, phase275_report(**(phase275_summary_overrides or {})))
    policy_path = root / "policy.json"
    phase276.write_json(policy_path, policy_value)
    return root, policy_path, phase275_path


def test_phase276_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase276_synthetic_ship_when_phase275_proof_and_health_pass(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase275_path = config_root(tmp_path)
    monkeypatch.setattr(phase276, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_500k_candidate_decision_gate(
        LargeContext500kCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase275_report_path=phase275_path,
            output_path="runtime-state/phase276/report.json",
            markdown_output_path="runtime-state/phase276/report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] == "ship"
    assert report["summary"]["phase277_ready"] is True
    assert report["blockers"] == []


def test_phase276_synthetic_hold_when_only_runtime_health_fails(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase275_path = config_root(tmp_path)
    monkeypatch.setattr(phase276, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": None, "passed": False, "error": "down"})

    report = validate_large_context_500k_candidate_decision_gate(
        LargeContext500kCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase275_report_path=phase275_path,
            output_path="runtime-state/phase276/report.json",
            markdown_output_path="runtime-state/phase276/report.md",
        )
    )

    assert report["decision"] == "hold"
    assert report["summary"]["runtime_health_blocker_count"] == len(policy()["required_runtime_health"])


def test_phase276_synthetic_repair_when_phase275_report_missing(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase275_path = config_root(tmp_path, missing_phase275=True)
    monkeypatch.setattr(phase276, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_500k_candidate_decision_gate(
        LargeContext500kCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase275_report_path=phase275_path,
            output_path="runtime-state/phase276/report.json",
            markdown_output_path="runtime-state/phase276/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase275_report.missing" for item in report["blockers"])


def test_phase276_synthetic_repair_when_strategy_missing(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase275_path = config_root(tmp_path)
    report_data = phase275_report()
    report_data["gates"]["phase273_live_acceptance"]["summary"]["strategy_ids"] = ["retrieval"]
    phase276.write_json(phase275_path, report_data)
    monkeypatch.setattr(phase276, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_500k_candidate_decision_gate(
        LargeContext500kCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase275_report_path=phase275_path,
            output_path="runtime-state/phase276/report.json",
            markdown_output_path="runtime-state/phase276/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase275.phase273.strategy_ids" for item in report["blockers"])


def test_phase276_synthetic_repair_when_required_phase_incomplete(tmp_path: Path, monkeypatch) -> None:
    root, policy_path, phase275_path = config_root(tmp_path, missing_phase=275)
    monkeypatch.setattr(phase276, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    report = validate_large_context_500k_candidate_decision_gate(
        LargeContext500kCandidateDecisionGateConfig(
            config_root=root,
            policy_path=policy_path,
            phase275_report_path=phase275_path,
            output_path="runtime-state/phase276/report.json",
            markdown_output_path="runtime-state/phase276/report.md",
        )
    )

    assert report["decision"] == "repair_required"
    assert any(item["id"] == "phase.275.status" for item in report["blockers"])


def test_phase276_policy_rejects_raw_500k_promotion_rule_disabled() -> None:
    mutated = copy.deepcopy(policy())
    mutated["decision_rules"]["do_not_promote_raw_500k_prompt_serving"] = False

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.decision_rules.do_not_promote_raw_500k_prompt_serving" for item in errors)
