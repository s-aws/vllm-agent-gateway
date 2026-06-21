from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig3_privacy_evalops import (
    EIG3PrivacyEvalOpsConfig,
    run_eig3_privacy_evalops,
)
from vllm_agent_gateway.acceptance.eig3_sensitive_data import read_json_object


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig3_privacy_evalops_policy.json"
PACK_PATH = REPO_ROOT / "runtime" / "eig3_privacy_evalops_prompt_pack.json"
FIXTURE_PATH = REPO_ROOT / "runtime" / "eig3_sensitive_data_fixtures.json"


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_with_pack(tmp_path: Path, pack: dict[str, object], policy: dict[str, object] | None = None) -> dict[str, object]:
    pack_path = tmp_path / "pack.json"
    policy_path = tmp_path / "policy.json"
    write_json(pack_path, pack)
    write_json(policy_path, policy or read_json_object(POLICY_PATH))
    return run_eig3_privacy_evalops(
        EIG3PrivacyEvalOpsConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            pack_path=pack_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report.get("validation_errors")
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def committed_pack() -> dict[str, object]:
    return read_json_object(PACK_PATH)


def test_eig3_privacy_evalops_accepts_committed_pack(tmp_path: Path) -> None:
    report = run_eig3_privacy_evalops(
        EIG3PrivacyEvalOpsConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase301-report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 16
    assert report["summary"]["archetype_count"] == 3
    assert report["summary"]["dimension_count"] == 8
    assert report["summary"]["phase302_ready"] is True
    assert report["summary"]["raw_source_content_retained_in_report"] is False


def test_eig3_privacy_evalops_rejects_late_blind_baseline(tmp_path: Path) -> None:
    pack = committed_pack()
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    case = copy.deepcopy(eval_cases[0])
    assert isinstance(case, dict)
    case["blind_baseline"]["collected_before_local_output"] = False
    eval_cases[0] = case

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "case.blind_baseline_order" in error_ids(report)


def test_eig3_privacy_evalops_rejects_missing_holdout_for_archetype(tmp_path: Path) -> None:
    pack = committed_pack()
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    pack["eval_cases"] = [
        case
        for case in eval_cases
        if not (isinstance(case, dict) and case.get("archetype") == "secret_like" and case.get("role") == "holdout")
    ]

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "coverage.holdouts" in error_ids(report)


def test_eig3_privacy_evalops_rejects_raw_fixture_leak_in_case_text(tmp_path: Path) -> None:
    pack = committed_pack()
    fixture_pack = read_json_object(FIXTURE_PATH)
    fixtures = {item["id"]: item for item in fixture_pack["fixtures"]}
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    case = copy.deepcopy(eval_cases[0])
    assert isinstance(case, dict)
    case["prompt"] = fixtures["EIG3-PII-R1"]["text"]
    eval_cases[0] = case

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "case.raw_sensitive_leak" in error_ids(report)


def test_eig3_privacy_evalops_rejects_chat_exposed_case_without_anythingllm_proof(tmp_path: Path) -> None:
    pack = committed_pack()
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    case = copy.deepcopy(eval_cases[0])
    assert isinstance(case, dict)
    case["chat_exposed"] = True
    eval_cases[0] = case

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "case.local_stack.natural_workflow" in error_ids(report)


def test_eig3_privacy_evalops_accepts_chat_exposed_case_with_required_surfaces(tmp_path: Path) -> None:
    pack = committed_pack()
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    case = copy.deepcopy(eval_cases[0])
    assert isinstance(case, dict)
    case["chat_exposed"] = True
    case["local_stack_results"].extend(
        [
            {
                "output_summary": "Workflow-router gateway proof passed without exposing raw sensitive values.",
                "status": "passed",
                "surface": "workflow_router_gateway",
            },
            {
                "output_summary": "AnythingLLM proof passed without exposing raw sensitive values.",
                "status": "passed",
                "surface": "anythingllm",
            },
        ]
    )
    eval_cases[0] = case

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "passed"


def test_eig3_privacy_evalops_rejects_unresolved_high_finding(tmp_path: Path) -> None:
    pack = committed_pack()
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    case = copy.deepcopy(eval_cases[0])
    assert isinstance(case, dict)
    case["findings"] = [{"id": "sample", "severity": "high", "status": "accepted"}]
    eval_cases[0] = case

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "case.finding.blocking" in error_ids(report)
    assert "release_decision.blocking_failures" in error_ids(report)


def test_eig3_privacy_evalops_rejects_missing_required_dimension_coverage(tmp_path: Path) -> None:
    pack = committed_pack()
    eval_cases = pack["eval_cases"]
    assert isinstance(eval_cases, list)
    for case in eval_cases:
        if isinstance(case, dict):
            case["dimensions"] = [item for item in case["dimensions"] if item != "stale_memory_use"]
            case["scores"] = [item for item in case["scores"] if item.get("dimension") != "stale_memory_use"]

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "coverage.dimensions" in error_ids(report)
