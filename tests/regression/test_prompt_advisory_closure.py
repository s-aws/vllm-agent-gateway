from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_field_round2 import materialize_blind_baseline_package
from vllm_agent_gateway.acceptance.prompt_advisory_closure import (
    DEFAULT_POLICY_PATH,
    PromptAdvisoryClosureConfig,
    build_prompt_advisory_closure_report,
    read_json_object,
    run_prompt_advisory_closure,
    sha256_file,
    validate_policy,
    validate_prompt_advisory_closure_report,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
ROUND2_POLICY_PATH = REPO_ROOT / "runtime" / "founder_field_round2_policy.json"
ROUND2_BASELINE_PATH = REPO_ROOT / "runtime" / "founder_field_round2_blind_baselines.json"
NON_GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp"
GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def round2_policy() -> dict[str, Any]:
    return read_json_object(ROUND2_POLICY_PATH)


def round2_baseline_source() -> dict[str, Any]:
    return read_json_object(ROUND2_BASELINE_PATH)


def baselines() -> dict[str, dict[str, Any]]:
    materialized = materialize_blind_baseline_package(
        policy=round2_policy(),
        baseline_package=round2_baseline_source(),
    )
    return {record["case_id"]: record for record in materialized["cases"]}


def phase158_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "transcript_quality_feedback_intake_report",
        "status": "passed",
        "accepted_findings": [
            {
                "finding_id": f"phase158-{case_id}-prompt-risk",
                "case_id": case_id,
                "category": "prompt_issue",
                "owner_path": "prompt_catalog_review",
                "message": f"Prompt risk for {case_id}.",
            }
            for case_id in policy()["required_advisory_case_ids"]
        ],
    }


def phase164_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "founder_field_round2_report",
        "phase": 164,
        "status": "passed",
        "quality_status": "advisory",
        "case_evidence": [
            {
                "case_id": case_id,
                "score": 94,
                "quality_classification": "advisory",
            }
            for case_id in policy()["required_advisory_case_ids"]
        ],
        "summary": {"classification_counts": {"advisory": 14, "blocker": 0}},
        "validation_errors": [],
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


def write_response(tmp_path: Path, case_id: str, *, text: str | None = None) -> dict[str, Any]:
    body = text if text is not None else response_text(baselines()[case_id])
    response_path = tmp_path / "responses" / f"{case_id}.txt"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(body, encoding="utf-8")
    return {
        "text_sha256": sha256_file(response_path),
        "text_sample": body[:1600],
        "response_artifact_path": str(response_path),
        "response_artifact_sha256": sha256_file(response_path),
        "response_artifact_bytes": response_path.stat().st_size,
    }


def field_case(tmp_path: Path, case_id: str, *, variant: str) -> dict[str, Any]:
    record = baselines()[case_id]
    prompt = record["prompt"]
    if variant == "refined":
        prompt = f"Refined prompt for {case_id}"
    artifact = write_response(tmp_path, case_id)
    return {
        "case_id": case_id,
        "target_root": record["target_root"],
        "prompt": prompt,
        "source_prompt": record["prompt"],
        "prompt_variant": variant,
        "baseline_target": record["ideal_answer_shape"],
        "expected_workflow": record["expected_workflow"],
        "expected_skill_id": record.get("expected_skill_id", ""),
        "expected_artifact_key": record.get("expected_artifact_key", ""),
        "status": "passed",
        "output_contract_status": "passed",
        "semantic_quality_status": "passed",
        "route_surface": "anythingllm_via_workflow_router_gateway",
        "run_id": f"workflow-router-{case_id.lower()}",
        "initial_difference": "No marker-level or semantic difference from the baseline target.",
        "suggested_prompt_if_missed": "",
        "refined_prompt": prompt if variant == "refined" else "",
        "prompt_risk": "Prompt risk.",
        **artifact,
    }


def field_report(tmp_path: Path, case_ids: list[str], *, variant: str, failed_case_ids: set[str] | None = None) -> dict[str, Any]:
    failed_case_ids = failed_case_ids or set()
    cases = [field_case(tmp_path, case_id, variant=variant) for case_id in case_ids]
    for case in cases:
        if case["case_id"] in failed_case_ids:
            case["status"] = "failed"
            case["output_contract_status"] = "failed"
            case["semantic_quality_status"] = "failed"
    fixture_state = {
        GIT_ROOT: {"hashes": {"README.md": "abc"}, "git_status": ""},
        NON_GIT_ROOT: {"hashes": {"README.md": "def"}, "git_status": None},
    }
    passed = sum(1 for case in cases if case["status"] == "passed")
    failed = len(cases) - passed
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


def build_report(
    tmp_path: Path,
    *,
    refined: dict[str, Any] | None = None,
    holdout: dict[str, Any] | None = None,
    phase158: dict[str, Any] | None = None,
    phase164: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_prompt_advisory_closure_report(
        config_root=REPO_ROOT,
        policy=policy(),
        round2_policy=round2_policy(),
        round2_baseline_source=round2_baseline_source(),
        phase158_report=phase158 or phase158_report(),
        phase164_report=phase164 or phase164_report(),
        refined_report=refined or field_report(tmp_path, policy()["required_advisory_case_ids"], variant="refined"),
        holdout_report=holdout or field_report(tmp_path, policy()["holdout_case_ids"], variant="original"),
        policy_path=POLICY_PATH,
        refined_report_path=None,
        holdout_report_path=None,
        phase158_report_path=None,
        phase164_report_path=None,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_prompt_advisory_closure_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_prompt_advisory_closure_report_passes_as_documented_guidance(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert report["status"] == "passed"
    assert report["summary"]["closure_count"] == 14
    assert report["summary"]["decision_counts"]["documented_guidance"] == 14
    assert report["summary"]["phase169_required"] is False
    assert all(record["silent_rewrite_performed"] is False for record in report["closure_records"])


def test_prompt_advisory_closure_accepts_refined_failures_as_product_gap_evidence(tmp_path: Path) -> None:
    refined = field_report(
        tmp_path,
        policy()["required_advisory_case_ids"],
        variant="refined",
        failed_case_ids={"P08"},
    )

    report = build_report(tmp_path, refined=refined)

    assert report["status"] == "passed"
    assert report["summary"]["decision_counts"]["product_gap_escalation"] == 1
    assert report["summary"]["phase169_required"] is True
    assert "refined.status" not in error_ids(report)
    assert "refined.cases[1].status" not in error_ids(report)


def test_prompt_advisory_closure_rejects_missing_refined_artifact(tmp_path: Path) -> None:
    refined = field_report(tmp_path, policy()["required_advisory_case_ids"], variant="refined")
    Path(refined["cases"][0]["response_artifact_path"]).unlink()

    report = build_report(tmp_path, refined=refined)

    assert report["status"] == "failed"
    assert "refined.cases[0].response_artifact_missing" in error_ids(report)


def test_prompt_advisory_closure_rejects_wrong_prompt_variant(tmp_path: Path) -> None:
    refined = field_report(tmp_path, policy()["required_advisory_case_ids"], variant="refined")
    refined["cases"][0]["prompt_variant"] = "original"

    report = build_report(tmp_path, refined=refined)

    assert report["status"] == "failed"
    assert "refined.cases[0].prompt_variant" in error_ids(report)


def test_prompt_advisory_closure_rejects_holdout_regression(tmp_path: Path) -> None:
    holdout = field_report(tmp_path, policy()["holdout_case_ids"], variant="original")
    holdout["cases"][0]["status"] = "failed"

    report = build_report(tmp_path, holdout=holdout)

    assert report["status"] == "failed"
    assert "holdout.cases[0].status" in error_ids(report)


def test_prompt_advisory_closure_rejects_fixture_mutation(tmp_path: Path) -> None:
    refined = field_report(tmp_path, policy()["required_advisory_case_ids"], variant="refined")
    refined["fixture_state_after"][GIT_ROOT]["hashes"]["README.md"] = "changed"

    report = build_report(tmp_path, refined=refined)

    assert report["status"] == "failed"
    assert "refined.fixture_state_changed" in error_ids(report)


def test_prompt_advisory_closure_rejects_missing_advisory_case(tmp_path: Path) -> None:
    source = phase158_report()
    source["accepted_findings"] = source["accepted_findings"][:-1]

    report = build_report(tmp_path, phase158=source)

    assert report["status"] == "failed"
    assert "phase158.advisory_ids" in error_ids(report)


def test_prompt_advisory_closure_rejects_hidden_summary_edit(tmp_path: Path) -> None:
    refined = field_report(tmp_path, policy()["required_advisory_case_ids"], variant="refined")
    holdout = field_report(tmp_path, policy()["holdout_case_ids"], variant="original")
    report = build_report(tmp_path, refined=refined, holdout=holdout)
    report["summary"]["closure_count"] = 999

    assert "report must match rebuilt prompt advisory closure report" in validate_prompt_advisory_closure_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        round2_policy=round2_policy(),
        round2_baseline_source=round2_baseline_source(),
        phase158_report=phase158_report(),
        phase164_report=phase164_report(),
        refined_report=refined,
        holdout_report=holdout,
        policy_path=POLICY_PATH,
        refined_report_path=None,
        holdout_report_path=None,
        phase158_report_path=None,
        phase164_report_path=None,
    )


def test_run_prompt_advisory_closure_writes_json_and_markdown(tmp_path: Path) -> None:
    policy_copy = copy.deepcopy(policy())
    phase158_path = tmp_path / "phase158.json"
    phase164_path = tmp_path / "phase164.json"
    refined_path = tmp_path / "refined.json"
    holdout_path = tmp_path / "holdout.json"
    policy_path = tmp_path / "policy.json"
    policy_copy["required_source_paths"]["phase158_feedback_report"] = str(phase158_path)
    policy_copy["required_source_paths"]["phase164_round2_report"] = str(phase164_path)
    write_json(phase158_path, phase158_report())
    write_json(phase164_path, phase164_report())
    write_json(refined_path, field_report(tmp_path, policy()["required_advisory_case_ids"], variant="refined"))
    write_json(holdout_path, field_report(tmp_path, policy()["holdout_case_ids"], variant="original"))
    write_json(policy_path, policy_copy)

    report = run_prompt_advisory_closure(
        PromptAdvisoryClosureConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            refined_field_report_path=refined_path,
            holdout_field_report_path=holdout_path,
            output_path=tmp_path / "closure.json",
            markdown_output_path=tmp_path / "closure.md",
        )
    )

    assert report["status"] == "passed"
    assert (tmp_path / "closure.json").exists()
    assert (tmp_path / "closure.md").exists()
