from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.disposable_apply_expansion import (
    DEFAULT_CASES_PATH,
    DisposableApplyExpansionConfig,
    read_json_object,
    validate_catalog,
    validate_disposable_apply_expansion,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_disposable_apply_expansion_catalog_passes_contract() -> None:
    catalog = read_json_object(REPO_ROOT / DEFAULT_CASES_PATH)
    checks = validate_catalog(catalog, cases_path=REPO_ROOT / DEFAULT_CASES_PATH)
    assert checks[0]["status"] == "passed"


def test_disposable_apply_expansion_catalog_rejects_missing_operation_set() -> None:
    catalog = read_json_object(REPO_ROOT / DEFAULT_CASES_PATH)
    mutated = copy.deepcopy(catalog)
    del mutated["cases"][0]["operation_set"]
    checks = validate_catalog(mutated, cases_path=REPO_ROOT / DEFAULT_CASES_PATH)
    assert checks[0]["status"] == "failed"
    assert any("operation_set" in error for error in checks[0]["details"]["errors"])


def test_disposable_apply_expansion_direct_cases_pass(tmp_path: Path) -> None:
    report = validate_disposable_apply_expansion(
        DisposableApplyExpansionConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase98-direct.json",
            include_direct=True,
            include_gateway=False,
            include_anythingllm=False,
            include_port_health=False,
        )
    )
    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 3
    assert report["summary"]["failed_check_ids"] == []


def test_disposable_apply_expansion_case_filter_runs_append_only_case(tmp_path: Path) -> None:
    report = validate_disposable_apply_expansion(
        DisposableApplyExpansionConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase101-append-only.json",
            case_ids=("DAE-001",),
            include_direct=True,
            include_gateway=False,
            include_anythingllm=False,
            include_port_health=False,
            include_protected_source_refusal=False,
        )
    )

    assert report["status"] == "passed"
    assert report["selected_case_ids"] == ["DAE-001"]
    assert report["summary"]["case_count"] == 1
    assert report["summary"]["protected_source_refusal_enabled"] is False
    assert report["summary"]["failed_check_ids"] == []
