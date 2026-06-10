from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_field_round2 import (
    DEFAULT_POLICY_PATH,
    FounderFieldRound2Config,
    build_founder_field_round2_report,
    materialize_blind_baseline_package,
    prompt_sha256,
    read_json_object,
    run_founder_field_round2,
    sha256_file,
    validate_baseline_package,
    validate_founder_field_round2_report,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
BASELINE_SOURCE_PATH = REPO_ROOT / "runtime" / "founder_field_round2_blind_baselines.json"
NON_GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp"
GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def baseline_source() -> dict[str, Any]:
    return read_json_object(BASELINE_SOURCE_PATH)


def materialized_baseline() -> dict[str, Any]:
    return materialize_blind_baseline_package(policy=policy(), baseline_package=baseline_source())


def readiness_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "post_restart_runtime_readiness_report",
        "status": "passed",
        "decision": "ready_after_restart",
    }


def phase158_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "transcript_quality_feedback_intake_report",
        "status": "passed",
        "accepted_findings": [
            {
                "case_id": case_id,
                "category": "prompt_issue",
                "owner_path": "prompt_catalog_review",
            }
            for case_id in policy()["required_advisory_case_ids"]
        ],
    }


def response_text(record: dict[str, Any]) -> str:
    markers = [
        "I completed workflow_router.plan.",
        "workflow_router.plan completed",
        "run_id: workflow-router-test",
        "Result:",
        "- Selected workflow:",
        "- Selected skills:",
        "- Selected tools:",
        "- Next action:",
        "- Verification:",
        "Artifacts:",
        f"selected_workflow: {record['expected_workflow']}",
        "Evidence",
        "Evidence files:",
        "Related tests:",
        "Recommended commands:",
        "Source refs:",
        "Verification:",
    ]
    markers.extend(record["must_have_markers"])
    if record.get("expected_skill_id"):
        markers.append(record["expected_skill_id"])
    if record.get("expected_artifact_key"):
        markers.append(record["expected_artifact_key"])
    return "\n".join(dict.fromkeys(markers)) + "\n"


def write_response(tmp_path: Path, record: dict[str, Any], *, text: str | None = None) -> dict[str, Any]:
    body = response_text(record) if text is None else text
    response_path = tmp_path / "responses" / f"{record['case_id']}.txt"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(body, encoding="utf-8")
    return {
        "text_sha256": sha256_file(response_path),
        "text_sample": body[:1600],
        "response_artifact_path": str(response_path),
        "response_artifact_sha256": sha256_file(response_path),
        "response_artifact_bytes": response_path.stat().st_size,
    }


def fake_case(tmp_path: Path, record: dict[str, Any], *, status: str = "passed") -> dict[str, Any]:
    artifact = write_response(tmp_path, record)
    return {
        "case_id": record["case_id"],
        "target_root": record["target_root"],
        "prompt": record["prompt"],
        "baseline_target": record["ideal_answer_shape"],
        "expected_workflow": record["expected_workflow"],
        "expected_skill_id": record.get("expected_skill_id", ""),
        "expected_artifact_key": record.get("expected_artifact_key", ""),
        "status": status,
        "output_contract_status": "passed" if status == "passed" else "failed",
        "semantic_quality_status": "passed" if status == "passed" else "failed",
        "route_surface": "anythingllm_via_workflow_router_gateway",
        "run_id": f"workflow-router-{record['case_id'].lower()}",
        "initial_difference": "No marker-level or semantic difference from the baseline target.",
        "suggested_prompt_if_missed": "",
        "refined_prompt": "",
        "prompt_risk": "Known prompt ambiguity." if record["case_id"] in policy()["required_advisory_case_ids"] else "",
        **artifact,
    }


def fake_field_report(tmp_path: Path, *, failed_case_id: str | None = None) -> dict[str, Any]:
    baseline = materialized_baseline()
    cases = [
        fake_case(tmp_path, record, status="failed" if record["case_id"] == failed_case_id else "passed")
        for record in baseline["cases"]
    ]
    passed = sum(1 for item in cases if item["status"] == "passed")
    failed = len(cases) - passed
    fixture_state = {
        GIT_ROOT: {"hashes": {"README.md": "abc"}, "git_status": ""},
        NON_GIT_ROOT: {"hashes": {"README.md": "def"}, "git_status": None},
    }
    return {
        "schema_version": 1,
        "kind": "founder_field_prompt_evaluation",
        "status": "passed" if failed == 0 else "failed",
        "created_at": "20260610T000001000000Z",
        "anythingllm_api_base_url": "http://127.0.0.1:3001",
        "workspace": "my-workspace",
        "cases": cases,
        "summary": {"passed": passed, "failed": failed},
        "anythingllm_preflight": {"status": "passed"},
        "fixture_state_before": fixture_state,
        "fixture_state_after": copy.deepcopy(fixture_state),
        "errors": [],
    }


def build_report(tmp_path: Path, field_report: dict[str, Any] | None = None, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_founder_field_round2_report(
        config_root=REPO_ROOT,
        policy=policy(),
        baseline_package=baseline or materialized_baseline(),
        field_report=field_report or fake_field_report(tmp_path),
        readiness_report=readiness_report(),
        phase158_report=phase158_report(),
        policy_path=POLICY_PATH,
        baseline_path=BASELINE_SOURCE_PATH,
        field_report_path=None,
        readiness_report_path=None,
        phase158_report_path=None,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_founder_field_round2_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_founder_field_round2_blind_baseline_materializes_and_passes() -> None:
    baseline = materialized_baseline()

    assert validate_baseline_package(policy=policy(), baseline_package=baseline, field_report=None) == []
    assert baseline["local_model_output_seen_by_blind_agent"] is False
    assert all(record["prompt_sha256"] == prompt_sha256(record["prompt"]) for record in baseline["cases"])


def test_founder_field_round2_report_passes_with_advisories(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert report["status"] == "passed"
    assert report["quality_status"] == "advisory"
    assert report["summary"]["case_count"] == 16
    assert report["summary"]["classification_counts"]["advisory"] == 14
    assert report["summary"]["classification_counts"]["pass"] == 2
    assert report["summary"]["phase165_required"] is True
    assert report["summary"]["phase169_required"] is False


def test_founder_field_round2_records_quality_blocker_without_invalidating_evidence(tmp_path: Path) -> None:
    report = build_report(tmp_path, fake_field_report(tmp_path, failed_case_id="P02"))

    assert report["status"] == "passed"
    assert report["quality_status"] == "failed"
    assert report["summary"]["classification_counts"]["blocker"] == 1
    assert report["summary"]["phase169_required"] is True


def test_founder_field_round2_rejects_baseline_output_leak(tmp_path: Path) -> None:
    baseline = materialized_baseline()
    baseline["cases"][0]["run_id"] = "workflow-router-leak"

    report = build_report(tmp_path, baseline=baseline)

    assert report["status"] == "failed"
    assert "baseline.cases[0].local_output_leak" in error_ids(report)


def test_founder_field_round2_rejects_late_blind_baseline(tmp_path: Path) -> None:
    baseline = materialized_baseline()
    baseline["generated_at"] = "20260610T999999000000Z"

    report = build_report(tmp_path, baseline=baseline)

    assert report["status"] == "failed"
    assert "baseline.generated_after_field_run" in error_ids(report)


def test_founder_field_round2_rejects_missing_full_response_artifact(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    Path(field["cases"][0]["response_artifact_path"]).unlink()

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.cases[0].response_artifact_missing" in error_ids(report)


def test_founder_field_round2_rejects_response_hash_mismatch(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    field["cases"][0]["response_artifact_sha256"] = "0" * 64

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.cases[0].response_artifact_hash" in error_ids(report)


def test_founder_field_round2_rejects_missing_route_surface(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    field["cases"][0]["route_surface"] = "direct_gateway"

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.cases[0].route_surface" in error_ids(report)


def test_founder_field_round2_rejects_fixture_mutation(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    field["fixture_state_after"][GIT_ROOT]["hashes"]["README.md"] = "changed"

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.fixture_state_changed" in error_ids(report)


def test_founder_field_round2_rejects_hidden_summary_edit(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    baseline = materialized_baseline()
    report = build_report(tmp_path, field, baseline)
    report["summary"]["case_count"] = 999

    assert "report must match rebuilt founder field round 2 report" in validate_founder_field_round2_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        baseline_package=baseline,
        field_report=field,
        readiness_report=readiness_report(),
        phase158_report=phase158_report(),
        policy_path=POLICY_PATH,
        baseline_path=BASELINE_SOURCE_PATH,
        field_report_path=None,
        readiness_report_path=None,
        phase158_report_path=None,
    )


def test_run_founder_field_round2_writes_json_and_markdown(tmp_path: Path) -> None:
    policy_copy = copy.deepcopy(policy())
    readiness_path = tmp_path / "readiness.json"
    phase158_path = tmp_path / "phase158.json"
    baseline_path = tmp_path / "baseline.json"
    field_path = tmp_path / "field.json"
    policy_path = tmp_path / "policy.json"
    policy_copy["post_restart_readiness_report_path"] = str(readiness_path)
    policy_copy["phase158_feedback_report_path"] = str(phase158_path)
    write_json(readiness_path, readiness_report())
    write_json(phase158_path, phase158_report())
    write_json(baseline_path, materialized_baseline())
    write_json(field_path, fake_field_report(tmp_path))
    write_json(policy_path, policy_copy)

    report = run_founder_field_round2(
        FounderFieldRound2Config(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            baseline_path=baseline_path,
            field_report_path=field_path,
            output_path=tmp_path / "round2.json",
            markdown_output_path=tmp_path / "round2.md",
        )
    )

    assert report["status"] == "passed"
    assert (tmp_path / "round2.json").exists()
    assert (tmp_path / "round2.md").exists()
