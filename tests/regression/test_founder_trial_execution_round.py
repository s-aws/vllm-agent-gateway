from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_trial_execution_round import (
    DEFAULT_POLICY_PATH,
    FounderTrialExecutionRoundConfig,
    build_founder_trial_execution_round_report,
    read_json_object,
    required_case_ids,
    run_founder_trial_execution_round,
    validate_founder_trial_execution_round_report,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
NON_GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def trial_pack_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "release_candidate_founder_trial_pack_report",
        "phase": 195,
        "status": "passed",
        "summary": {"validation_error_count": 0},
    }


def readiness_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "v1_product_readiness_reassessment_report",
        "phase": 196,
        "status": "passed",
        "recommendation": "release_for_broader_founder_beta",
        "summary": {"validation_error_count": 0},
    }


def response_text(case_id: str) -> str:
    return "\n".join(
        [
            "Answer:",
            "selected_workflow: code_investigation.plan",
            "I completed workflow_router.plan.",
            f"run_id: workflow-router-{case_id.lower()}",
            "Related tests:",
            "Recommended commands:",
        ]
    )


def write_response(tmp_path: Path, case_id: str) -> dict[str, Any]:
    path = tmp_path / "responses" / f"{case_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response_text(case_id), encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "response_artifact_path": str(path),
        "response_artifact_sha256": digest,
        "response_artifact_bytes": path.stat().st_size,
        "text_sha256": digest,
    }


def fake_case(tmp_path: Path, case_id: str, *, failed: bool = False) -> dict[str, Any]:
    target_root = NON_GIT_ROOT if case_id == "P13" else GIT_ROOT
    return {
        "case_id": case_id,
        "target_root": target_root,
        "prompt": f"In {target_root}, run {case_id}.",
        "expected_workflow": "task.decompose" if case_id == "P22" else "code_investigation.plan",
        "status": "failed" if failed else "passed",
        "output_contract_status": "failed" if failed else "passed",
        "semantic_quality_status": "failed" if failed else "passed",
        "route_surface": "anythingllm_via_workflow_router_gateway",
        "run_id": f"workflow-router-{case_id.lower()}",
        "initial_difference": "No marker-level or semantic difference from the baseline target." if not failed else "missing expected answer detail",
        "suggested_prompt_if_missed": "" if not failed else "Ask for evidence explicitly.",
        "prompt_risk": "Known ambiguity." if case_id in {"P01", "P08", "P17", "P21"} else "",
        **write_response(tmp_path, case_id),
    }


def fake_field_report(tmp_path: Path, *, failed_case_id: str | None = None) -> dict[str, Any]:
    cases = [fake_case(tmp_path, case_id, failed=case_id == failed_case_id) for case_id in required_case_ids(policy())]
    fixture_state = {
        GIT_ROOT: {"hashes": {"README.md": "abc"}, "git_status": ""},
        NON_GIT_ROOT: {"hashes": {"README.md": "def"}, "git_status": None},
    }
    return {
        "schema_version": 1,
        "kind": "founder_field_prompt_evaluation",
        "status": "failed" if failed_case_id else "passed",
        "created_at": "20260611T000000000000Z",
        "anythingllm_api_base_url": "http://127.0.0.1:3001",
        "workspace": "my-workspace",
        "anythingllm_preflight": {"status": "passed"},
        "fixture_state_before": fixture_state,
        "fixture_state_after": copy.deepcopy(fixture_state),
        "cases": cases,
        "summary": {"passed": len(cases) - (1 if failed_case_id else 0), "failed": 1 if failed_case_id else 0},
        "errors": [],
    }


def sources(tmp_path: Path, field_report: dict[str, Any] | None = None) -> dict[str, tuple[Path, dict[str, Any]]]:
    trial_path = tmp_path / "trial.json"
    readiness_path = tmp_path / "readiness.json"
    field_path = tmp_path / "field.json"
    write_json(trial_path, trial_pack_report())
    write_json(readiness_path, readiness_report())
    write_json(field_path, field_report or fake_field_report(tmp_path))
    return {
        "trial_pack": (trial_path, read_json_object(trial_path)),
        "readiness": (readiness_path, read_json_object(readiness_path)),
        "field_report": (field_path, read_json_object(field_path)),
    }


def build_report(tmp_path: Path, field_report: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_founder_trial_execution_round_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=sources(tmp_path, field_report),
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_founder_trial_execution_round_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_founder_trial_execution_round_report_passes_with_advisories(tmp_path: Path) -> None:
    report = build_report(tmp_path)

    assert report["status"] == "passed"
    assert report["quality_status"] == "advisory"
    assert report["summary"]["case_count"] == 14
    assert report["summary"]["classification_counts"]["advisory"] == 4
    assert report["summary"]["classification_counts"]["blocker"] == 0
    assert report["summary"]["phase198_required"] is True


def test_founder_trial_execution_round_records_blocker_without_invalidating_evidence(tmp_path: Path) -> None:
    report = build_report(tmp_path, fake_field_report(tmp_path, failed_case_id="P02"))

    assert report["status"] == "passed"
    assert report["quality_status"] == "failed"
    assert report["summary"]["classification_counts"]["blocker"] == 1
    assert report["summary"]["phase198_required"] is True


def test_founder_trial_execution_round_rejects_wrong_case_order(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    field["cases"] = list(reversed(field["cases"]))

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.case_ids" in error_ids(report)


def test_founder_trial_execution_round_rejects_fixture_mutation(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    field["fixture_state_after"][GIT_ROOT]["git_status"] = " M README.md"

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.fixture_state_changed" in error_ids(report)


def test_founder_trial_execution_round_rejects_missing_response_artifact(tmp_path: Path) -> None:
    field = fake_field_report(tmp_path)
    Path(field["cases"][0]["response_artifact_path"]).unlink()

    report = build_report(tmp_path, field)

    assert report["status"] == "failed"
    assert "field.cases[0].response_artifact_missing" in error_ids(report)


def test_founder_trial_execution_round_rejects_wrong_readiness_decision(tmp_path: Path) -> None:
    test_sources = sources(tmp_path)
    path, readiness = test_sources["readiness"]
    readiness["recommendation"] = "blocked_stale_or_invalid_evidence"
    test_sources["readiness"] = (path, readiness)

    report = build_founder_trial_execution_round_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=test_sources,
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert report["status"] == "failed"
    assert "readiness.recommendation" in error_ids(report)


def test_founder_trial_execution_round_rejects_hidden_summary_edit(tmp_path: Path) -> None:
    test_sources = sources(tmp_path)
    report = build_founder_trial_execution_round_report(
        config_root=REPO_ROOT,
        policy=policy(),
        sources=test_sources,
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )
    report["summary"]["case_count"] = 99

    errors = validate_founder_trial_execution_round_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        sources=test_sources,
        source_load_errors=[],
        policy_path=POLICY_PATH,
    )

    assert "report must match rebuilt founder trial execution round" in errors


def test_project_founder_trial_execution_round_passes_when_field_report_exists(tmp_path: Path) -> None:
    field_report_path = REPO_ROOT / policy()["field_report_path"]
    if not field_report_path.is_file():
        return

    report = run_founder_trial_execution_round(
        FounderTrialExecutionRoundConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 14
    assert (tmp_path / "report.md").exists()
