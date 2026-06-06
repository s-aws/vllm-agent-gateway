from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.model_capability_profile import (
    CapabilityStatus,
    ModelCapabilityProfileConfig,
    ProfileStatus,
    TaskPolicyStatus,
    run_model_capability_profile,
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def acceptance_report(status: str = "passed") -> dict:
    return {
        "kind": "v1_acceptance_report",
        "status": status,
        "profile": "release-candidate",
        "founder_field_summary": {"status": "passed", "summary": {"passed": 34, "failed": 0}, "errors": []},
        "suite_runs": [
            {"id": "representative_l1", "status": "passed", "returncode": 0},
            {"id": "representative_l2", "status": "passed", "returncode": 0},
            {"id": "controlled_apply", "status": "passed", "returncode": 0},
            {"id": "inline_format_a", "status": "passed", "returncode": 0},
        ],
        "errors": [],
    }


def portability_report(acceptance_path: Path, *, status: str = "passed", failures: list[dict] | None = None) -> dict:
    return {
        "kind": "model_portability_report",
        "schema_version": 1,
        "status": status,
        "candidate": {
            "candidate_id": "local-model",
            "candidate_model_base_url": "http://127.0.0.1:8000/v1",
        },
        "candidate_model_probe": {"status": "passed", "model_ids": ["local-model-id"]},
        "acceptance_report": {
            "status": status,
            "founder_field_summary": {"status": "passed", "summary": {"passed": 34, "failed": 0}, "errors": []},
        },
        "acceptance_report_path": str(acceptance_path),
        "classification_summary": {
            "classifier": 0,
            "harness": 0,
            "model_quality": 0,
            "prompt": 0,
            "unknown": 0,
        },
        "classified_failures": failures or [],
    }


def test_model_capability_profile_derives_advisory_policy_from_passing_portability_report(tmp_path: Path) -> None:
    acceptance_path = tmp_path / "acceptance.json"
    portability_path = tmp_path / "portability.json"
    output_path = tmp_path / "profile.json"
    write_json(acceptance_path, acceptance_report())
    write_json(portability_path, portability_report(acceptance_path))

    profile = run_model_capability_profile(
        ModelCapabilityProfileConfig(
            config_root=tmp_path,
            portability_report_path=portability_path,
            output_path=output_path,
        )
    )

    assert profile["kind"] == "model_capability_profile"
    assert profile["status"] == ProfileStatus.WARNING.value
    assert profile["capabilities"]["route_stability"]["status"] == CapabilityStatus.PROVEN.value
    assert profile["capabilities"]["output_contract_reliability"]["status"] == CapabilityStatus.PROVEN.value
    assert profile["capabilities"]["semantic_answer_quality"]["status"] == CapabilityStatus.PROVEN.value
    assert profile["capabilities"]["latency"]["status"] == CapabilityStatus.UNKNOWN.value
    assert profile["capabilities"]["safe_apply_readiness"]["status"] == CapabilityStatus.PARTIALLY_PROVEN.value
    assert profile["task_policy"]["read_only_l1"]["status"] == TaskPolicyStatus.APPROVED.value
    assert profile["task_policy"]["l2_read_only"]["status"] == TaskPolicyStatus.APPROVED.value
    assert profile["task_policy"]["real_apply"]["status"] == TaskPolicyStatus.NOT_APPROVED.value
    assert profile["task_policy"]["automatic_model_selection"]["status"] == TaskPolicyStatus.NOT_APPROVED.value
    assert output_path.exists()
    assert Path(profile["markdown_report_path"]).exists()


def test_model_capability_profile_marks_failed_model_evidence_not_proven(tmp_path: Path) -> None:
    acceptance_path = tmp_path / "acceptance.json"
    portability_path = tmp_path / "portability.json"
    output_path = tmp_path / "profile.json"
    failures = [
        {
            "source": "suite_runs[route_suite]",
            "classification": "classifier",
            "message": "expected_workflow code_investigation.plan but selected_workflow task.decompose",
        },
        {
            "source": "suite_runs[semantic_suite]",
            "classification": "model_quality",
            "message": "semantic_quality_status failed with missing_semantic_markers",
        },
        {
            "source": "health",
            "classification": "harness",
            "message": "timed out waiting for body bytes",
        },
    ]
    write_json(acceptance_path, acceptance_report(status="failed"))
    report = portability_report(acceptance_path, status="failed", failures=failures)
    report["classification_summary"] = {"classifier": 1, "harness": 1, "model_quality": 1, "prompt": 0, "unknown": 0}
    report["acceptance_report"]["founder_field_summary"]["status"] = "failed"
    write_json(portability_path, report)

    profile = run_model_capability_profile(
        ModelCapabilityProfileConfig(
            config_root=tmp_path,
            portability_report_path=portability_path,
            output_path=output_path,
        )
    )

    assert profile["status"] == ProfileStatus.FAILED.value
    assert profile["capabilities"]["route_stability"]["status"] == CapabilityStatus.NOT_PROVEN.value
    assert profile["capabilities"]["semantic_answer_quality"]["status"] == CapabilityStatus.NOT_PROVEN.value
    assert profile["capabilities"]["timeout_behavior"]["status"] == CapabilityStatus.NOT_PROVEN.value
    assert profile["task_policy"]["read_only_l1"]["status"] == TaskPolicyStatus.NOT_APPROVED.value
    assert profile["task_policy"]["apply_prep"]["status"] == TaskPolicyStatus.NOT_APPROVED.value
