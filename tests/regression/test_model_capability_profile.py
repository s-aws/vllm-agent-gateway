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
from vllm_agent_gateway.model_capability_routing import ModelCapabilityTaskClass, route_task_class


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def test_prompt_skill_coverage_entries_map_to_model_capability_task_classes() -> None:
    coverage = json.loads((REPO_ROOT / "runtime" / "prompt_skill_coverage.json").read_text(encoding="utf-8"))
    entries = coverage["entries"]
    assert isinstance(entries, list)
    expected_by_prefix = {
        "l1_": {ModelCapabilityTaskClass.READ_ONLY_L1, ModelCapabilityTaskClass.DRAFT_ONLY_L1},
        "d1_": {ModelCapabilityTaskClass.DRAFT_ONLY_L1},
        "l2_": {ModelCapabilityTaskClass.L2_READ_ONLY},
    }
    checked = 0
    for entry in entries:
        route_rule = entry.get("route_rule")
        selected_workflow = entry.get("selected_workflow")
        if not isinstance(route_rule, str) or not isinstance(selected_workflow, str):
            continue
        if route_rule == "disposable_apply_terms":
            task_class = route_task_class(
                selected_workflow=selected_workflow,
                route_rules=[route_rule],
                mode="apply_disposable_copy",
                approval={"status": "approved_for_disposable_apply", "apply_allowed": True},
                packet_operations=[{"kind": "replace_text", "path": "README.md", "old": "a", "new": "b"}],
            )
            assert task_class == ModelCapabilityTaskClass.APPLY_PREP
            checked += 1
            continue
        for prefix, allowed in expected_by_prefix.items():
            if route_rule.startswith(prefix):
                task_class = route_task_class(
                    selected_workflow=selected_workflow,
                    route_rules=[route_rule],
                    mode="plan_only",
                    approval={},
                    packet_operations=[],
                )
                assert task_class in allowed, (entry.get("id"), route_rule, task_class)
                checked += 1
                break
    assert checked >= 30


def test_draft_only_l1_packet_design_approval_stays_draft_task_class() -> None:
    task_class = route_task_class(
        selected_workflow="execution_planning.plan",
        route_rules=["l1_small_text_edit_terms"],
        mode="implementation_prep",
        approval={
            "status": "approved_for_packet_design",
            "scope": "draft_text_edit_packet_design_only",
            "apply_allowed": False,
        },
        packet_operations=[],
    )

    assert task_class == ModelCapabilityTaskClass.DRAFT_ONLY_L1
