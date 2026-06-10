from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.local_model_regression_watchlist import (
    build_local_model_regression_watchlist_report,
    read_json_object,
    resolve_path,
    validate_local_model_regression_watchlist_report,
    validate_watchlist,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WATCHLIST_PATH = REPO_ROOT / "runtime" / "local_model_regression_watchlist.json"


def watchlist() -> dict[str, Any]:
    return read_json_object(WATCHLIST_PATH)


def prompt_pack_and_catalog(payload: dict[str, Any]) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    prompt_pack_path = resolve_path(REPO_ROOT, payload["prompt_pack_path"])
    prompt_pack = read_json_object(prompt_pack_path)
    prompt_catalog_path = resolve_path(REPO_ROOT, prompt_pack["catalog_path"])
    prompt_catalog = read_json_object(prompt_catalog_path)
    return prompt_pack_path, prompt_pack, prompt_catalog_path, prompt_catalog


def project_report(payload: dict[str, Any] | None = None, *, require_artifacts: bool = False) -> dict[str, Any]:
    current = payload or watchlist()
    prompt_pack_path, prompt_pack, prompt_catalog_path, prompt_catalog = prompt_pack_and_catalog(current)
    return build_local_model_regression_watchlist_report(
        config_root=REPO_ROOT,
        watchlist=current,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        watchlist_path=WATCHLIST_PATH,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
        require_artifacts=require_artifacts,
    )


def validate_report(
    report: dict[str, Any],
    payload: dict[str, Any] | None = None,
    *,
    require_artifacts: bool = False,
) -> list[str]:
    current = payload or watchlist()
    prompt_pack_path, prompt_pack, prompt_catalog_path, prompt_catalog = prompt_pack_and_catalog(current)
    return validate_local_model_regression_watchlist_report(
        report,
        config_root=REPO_ROOT,
        watchlist=current,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        watchlist_path=WATCHLIST_PATH,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
        require_artifacts=require_artifacts,
    )


def test_project_local_model_regression_watchlist_passes() -> None:
    payload = watchlist()
    _prompt_pack_path, prompt_pack, _prompt_catalog_path, prompt_catalog = prompt_pack_and_catalog(payload)
    assert validate_watchlist(
        payload,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        config_root=REPO_ROOT,
        require_artifacts=True,
    ) == []
    report = project_report(payload, require_artifacts=True)
    assert validate_report(report, payload, require_artifacts=True) == []
    assert report["status"] == "passed"
    assert report["summary"]["watch_item_count"] == 14
    assert report["summary"]["covered_prompt_pack_case_count"] == report["summary"]["prompt_pack_case_count"]
    assert report["summary"]["smoke_case_count"] == 4
    assert report["summary"]["expanded_read_only_case_count"] == 10
    assert report["summary"]["blocker_watch_count"] == 4
    assert report["sources"]["prompt_catalog"]["sha256"]


def test_watchlist_rejects_missing_prompt_pack_case_coverage() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"] = [item for item in payload["items"] if item["case_ids"] != ["P22"]]
    report = project_report(payload)
    assert any("missing prompt pack case(s): P22" in error for error in report["errors"])


def test_watchlist_rejects_duplicate_case_assignment() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][1]["case_ids"] = ["P01"]
    report = project_report(payload)
    assert any("missing prompt pack case(s): P02" in error for error in report["errors"])
    assert any("duplicates prompt pack case(s): P01" in error for error in report["errors"])


def test_watchlist_rejects_orphan_case_id() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][0]["case_ids"] = ["PX999"]
    report = project_report(payload)
    assert any("contains orphan case(s): PX999" in error for error in report["errors"])


def test_watchlist_rejects_unknown_related_gate() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][0]["related_gates"].append("made_up_gate")
    report = project_report(payload)
    assert any("references unknown gate" in error for error in report["errors"])


def test_watchlist_rejects_missing_gate_artifact() -> None:
    payload = copy.deepcopy(watchlist())
    payload["gate_catalog"][0]["artifact_path"] = "runtime-state/missing-gate.json"
    report = project_report(payload, require_artifacts=True)
    assert any("artifact_path does not exist" in error for error in report["errors"])


def test_watchlist_rejects_invalid_repair_owner() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][0]["repair_owner"] = "local model magic"
    report = project_report(payload)
    assert any("repair_owner is not an allowed Priority 0 owner" in error for error in report["errors"])


def test_watchlist_rejects_free_form_symptom() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][0]["expected_symptoms"] = ["answer seems worse", "less useful"]
    report = project_report(payload)
    assert any("expected_symptoms must use deterministic" in error for error in report["errors"])


def test_watchlist_rejects_smoke_case_not_blocker() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][0]["severity"] = "advisory"
    report = project_report(payload)
    assert any("severity must be blocker for smoke cases" in error for error in report["errors"])


def test_watchlist_rejects_expanded_case_as_blocker() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][4]["severity"] = "blocker"
    report = project_report(payload)
    assert any("severity must be lower than smoke severity" in error for error in report["errors"])


def test_watchlist_rejects_required_marker_drift_from_catalog() -> None:
    payload = copy.deepcopy(watchlist())
    payload["items"][0]["required_markers"] = payload["items"][0]["required_markers"][:-1]
    report = project_report(payload)
    assert any("required_markers must match prompt catalog" in error for error in report["errors"])


def test_watchlist_rejects_missing_workflow_coverage() -> None:
    payload = copy.deepcopy(watchlist())
    prompt_pack_path, prompt_pack, prompt_catalog_path, prompt_catalog = prompt_pack_and_catalog(payload)
    broken_catalog = copy.deepcopy(prompt_catalog)
    for case in broken_catalog["cases"]:
        if case["case_id"] == "P05":
            case["expected_workflow"] = "code_investigation.plan"
    report = build_local_model_regression_watchlist_report(
        config_root=REPO_ROOT,
        watchlist=payload,
        prompt_pack=prompt_pack,
        prompt_catalog=broken_catalog,
        watchlist_path=WATCHLIST_PATH,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
    )
    assert any("workflow code_context.lookup" in error for error in report["errors"])


def test_watchlist_rejects_missing_frozen_root_coverage() -> None:
    payload = copy.deepcopy(watchlist())
    prompt_pack_path, prompt_pack, prompt_catalog_path, prompt_catalog = prompt_pack_and_catalog(payload)
    broken_catalog = copy.deepcopy(prompt_catalog)
    for case in broken_catalog["cases"]:
        if case["case_id"] == "P13":
            case["target_root"] = "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
    report = build_local_model_regression_watchlist_report(
        config_root=REPO_ROOT,
        watchlist=payload,
        prompt_pack=prompt_pack,
        prompt_catalog=broken_catalog,
        watchlist_path=WATCHLIST_PATH,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
    )
    assert any("missing required target roots" in error for error in report["errors"])


def test_watchlist_rejects_hidden_summary_change() -> None:
    report = project_report()
    report["summary"]["watch_item_count"] = 99
    errors = validate_report(report)
    assert any("report.summary must match rebuilt local model regression watchlist report" in error for error in errors)


def test_watchlist_rejects_stale_prompt_catalog_hash() -> None:
    report = project_report()
    report["sources"]["prompt_catalog"]["sha256"] = "0" * 64
    errors = validate_report(report)
    assert any("report.sources must match rebuilt local model regression watchlist report" in error for error in errors)
