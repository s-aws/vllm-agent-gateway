from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    SkillSelectionHardeningConfig,
    validate_catalog,
    validate_skill_selection_hardening,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "runtime" / "skill_selection_hardening_cases.json"


def load_cases() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def failed_errors(catalog: dict) -> list[str]:
    check = validate_catalog(catalog, cases_path=CASES_PATH)[0]
    return check["details"]["errors"]


def test_skill_selection_hardening_catalog_passes_contract() -> None:
    check = validate_catalog(load_cases(), cases_path=CASES_PATH)[0]

    assert check["status"] == "passed"
    assert check["details"]["case_count"] >= 6
    assert check["details"]["ready_count"] >= 3
    assert check["details"]["fail_closed_count"] >= 3


def test_skill_selection_hardening_catalog_rejects_missing_chat_markers() -> None:
    catalog = load_cases()
    mutated = copy.deepcopy(catalog)
    del mutated["cases"][0]["required_chat_markers"]

    errors = failed_errors(mutated)

    assert any("required_chat_markers must be a non-empty string array" in error for error in errors)


def test_skill_selection_hardening_catalog_rejects_ready_case_without_route_rule() -> None:
    catalog = load_cases()
    mutated = copy.deepcopy(catalog)
    mutated["cases"][0]["expected_route_rules"] = []

    errors = failed_errors(mutated)

    assert any("expected_route_rules must be a non-empty string array" in error for error in errors)


def test_skill_selection_hardening_direct_repeated_cases_pass(tmp_path: Path) -> None:
    target = tmp_path / "target-repo"
    target.mkdir()
    (target / "README.md").write_text("# Selector fixture\n", encoding="utf-8")
    report_path = tmp_path / "phase94-selection-report.json"

    report = validate_skill_selection_hardening(
        SkillSelectionHardeningConfig(
            config_root=REPO_ROOT,
            output_path=report_path,
            target_roots=(str(target),),
            repeat_count=2,
            include_direct=True,
            include_gateway=False,
            include_anythingllm=False,
        )
    )

    assert report["status"] == "passed"
    assert report_path.exists()
    assert report["summary"]["case_count"] == len(load_cases()["cases"])
    assert report["summary"]["repeat_count"] == 2
    assert report["summary"]["failed_check_ids"] == []
