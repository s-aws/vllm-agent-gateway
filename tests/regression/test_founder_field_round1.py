from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_field_round1 import (
    DEFAULT_POLICY_PATH,
    FounderFieldRound1Config,
    build_founder_field_round1_report,
    read_json_object,
    run_founder_field_round1,
    validate_founder_field_round1_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
NON_GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp"
GIT_ROOT = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
SKILL_BY_CASE = {
    "P27": "handler-branch-tracer",
    "P28": "handler-branch-tracer",
    "P29": "table-schema-isolator",
    "P30": "table-schema-isolator",
    "P31": "runtime-entrypoint-disambiguator",
    "P32": "runtime-entrypoint-disambiguator",
    "P33": "change-boundary-summarizer",
    "P34": "change-boundary-summarizer",
}


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def target_root_for_case(case_id: str) -> str:
    return NON_GIT_ROOT if case_id in {"P13", "P28", "P30", "P32", "P34"} else GIT_ROOT


def workflow_for_case(case_id: str) -> str:
    if case_id in {"P05", "P12"}:
        return "code_context.lookup"
    if case_id == "P22":
        return "task.decompose"
    return "code_investigation.plan"


def fake_case(case_id: str, *, status: str = "passed", prompt_risk: str = "") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "target_root": target_root_for_case(case_id),
        "prompt": f"In {target_root_for_case(case_id)}, run founder field prompt {case_id}.",
        "baseline_target": f"Baseline for {case_id}",
        "expected_workflow": workflow_for_case(case_id),
        "expected_skill_id": SKILL_BY_CASE.get(case_id, ""),
        "expected_artifact_key": "",
        "status": status,
        "output_contract_status": "passed" if status == "passed" else "failed",
        "semantic_quality_status": "passed" if status == "passed" else "failed",
        "run_id": f"workflow-router-{case_id.lower()}",
        "text_sha256": "a" * 64,
        "initial_difference": "No marker-level or semantic difference from the baseline target."
        if status == "passed"
        else "Response missed semantic answer concepts.",
        "suggested_prompt_if_missed": "" if status == "passed" else "Ask for concrete evidence.",
        "prompt_risk": prompt_risk,
    }


def fake_field_report(*, failed_case_id: str | None = None, prompt_risk_case_id: str | None = "P01") -> dict[str, Any]:
    cases = []
    for case_id in policy()["required_case_ids"]:
        cases.append(
            fake_case(
                case_id,
                status="failed" if case_id == failed_case_id else "passed",
                prompt_risk="Ambiguous wording requires founder review." if case_id == prompt_risk_case_id else "",
            )
        )
    fixture_state = {
        GIT_ROOT: {"hashes": {"README.md": "abc"}, "git_status": ""},
        NON_GIT_ROOT: {"hashes": {"README.md": "def"}, "git_status": None},
    }
    passed = sum(1 for item in cases if item["status"] == "passed")
    failed = len(cases) - passed
    return {
        "schema_version": 1,
        "kind": "founder_field_prompt_evaluation",
        "status": "passed" if failed == 0 else "failed",
        "created_at": "20260610T000000000000Z",
        "anythingllm_api_base_url": "http://127.0.0.1:3001",
        "workspace": "my-workspace",
        "cases": cases,
        "summary": {"passed": passed, "failed": failed},
        "anythingllm_preflight": {"status": "passed"},
        "fixture_state_before": fixture_state,
        "fixture_state_after": copy.deepcopy(fixture_state),
        "errors": [],
    }


def build_report(source_report: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_founder_field_round1_report(
        config_root=REPO_ROOT,
        policy=policy(),
        source_report=source_report or fake_field_report(),
        policy_path=POLICY_PATH,
        field_report_path=None,
    )


def validate_report(report: dict[str, Any], source_report: dict[str, Any] | None = None) -> list[str]:
    return validate_founder_field_round1_report(
        report,
        config_root=REPO_ROOT,
        policy=policy(),
        source_report=source_report or fake_field_report(),
        policy_path=POLICY_PATH,
        field_report_path=None,
    )


def error_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["validation_errors"]}


def test_founder_field_round1_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_founder_field_round1_report_passes_with_advisory_cases() -> None:
    report = build_report()

    assert report["status"] == "passed"
    assert report["quality_status"] == "advisory"
    assert report["summary"]["case_count"] == 30
    assert report["summary"]["advisory_case_count"] == 1
    assert report["phase158_required"] is True
    assert set(report["summary"]["target_roots"]) == {GIT_ROOT, NON_GIT_ROOT}


def test_founder_field_round1_quality_blockers_route_to_phase158_without_contract_failure() -> None:
    report = build_report(fake_field_report(failed_case_id="P07", prompt_risk_case_id=None))

    assert report["status"] == "passed"
    assert report["quality_status"] == "failed"
    assert report["summary"]["blocker_case_count"] == 1
    assert report["phase158_required"] is True


def test_founder_field_round1_rejects_missing_run_id() -> None:
    source = fake_field_report()
    source["cases"][0]["run_id"] = "unknown"

    report = build_report(source)

    assert report["status"] == "failed"
    assert "source.cases[0].run_id_unknown" in error_ids(report)


def test_founder_field_round1_rejects_fixture_mutation() -> None:
    source = fake_field_report()
    source["fixture_state_after"][GIT_ROOT]["hashes"]["README.md"] = "changed"

    report = build_report(source)

    assert report["status"] == "failed"
    assert "source.fixture_state_changed" in error_ids(report)


def test_founder_field_round1_rejects_wrong_case_set() -> None:
    source = fake_field_report()
    source["cases"] = source["cases"][:19]

    report = build_report(source)

    assert report["status"] == "failed"
    assert "source.case_ids" in error_ids(report)
    assert "source.too_few_cases" in error_ids(report)


def test_founder_field_round1_rejects_runner_errors() -> None:
    source = fake_field_report()
    source["errors"] = ["AnythingLLM preflight failed"]

    report = build_report(source)

    assert report["status"] == "failed"
    assert "source.errors" in error_ids(report)


def test_founder_field_round1_rejects_hidden_summary_edit() -> None:
    source = fake_field_report()
    report = build_report(source)
    report["summary"]["case_count"] = 999

    assert "report must match rebuilt founder field round 1 report" in validate_report(report, source)


def test_run_founder_field_round1_writes_json_and_markdown(tmp_path: Path) -> None:
    field_report = tmp_path / "field.json"
    field_report.write_text(str(), encoding="utf-8")
    field_report.write_text(
        __import__("json").dumps(fake_field_report(), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    report = run_founder_field_round1(
        FounderFieldRound1Config(
            config_root=REPO_ROOT,
            policy_path=POLICY_PATH,
            field_report_path=field_report,
            output_path=tmp_path / "round.json",
            markdown_output_path=tmp_path / "round.md",
        )
    )

    assert report["status"] == "passed"
    assert (tmp_path / "round.json").exists()
    assert (tmp_path / "round.md").exists()
