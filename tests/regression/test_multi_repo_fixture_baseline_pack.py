from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.multi_repo_fixture_baseline_pack import (
    DEFAULT_POLICY_PATH,
    MultiRepoFixtureBaselinePackConfig,
    read_json_object,
    validate_multi_repo_fixture_baseline_pack,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def test_phase209_policy_passes() -> None:
    errors, fixture_proof = validate_policy(policy())

    assert errors == []
    assert fixture_proof["head"] == "d3cecac670e3dd185cd3289feecae6ec69bab0b3"
    assert fixture_proof["clean"] is True


def test_phase209_validator_writes_report(tmp_path: Path) -> None:
    report = validate_multi_repo_fixture_baseline_pack(
        MultiRepoFixtureBaselinePackConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase209-report.json",
            markdown_output_path=tmp_path / "phase209-report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 5
    assert report["summary"]["phase210_ready"] is True
    assert (tmp_path / "phase209-report.json").is_file()
    assert (tmp_path / "phase209-report.md").read_text(encoding="utf-8").startswith("# Multi-Repo Fixture Baseline Pack")


def test_phase209_rejects_missing_required_category() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"] = [case for case in mutated["cases"] if case["category"] != "change_surface"]

    errors, _ = validate_policy(mutated)

    assert any("policy.cases missing required categories: change_surface" in error for error in errors)


def test_phase209_rejects_rubric_not_100_points() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["blind_baseline"]["scoring_rubric"][0]["points"] = 1

    errors, _ = validate_policy(mutated)

    assert any("scoring_rubric points must total 100" in error for error in errors)


def test_phase209_rejects_missing_no_commit_boundary() -> None:
    mutated = copy.deepcopy(policy())
    mutated["fixture"]["forbidden_operations"].remove("push_to_staterail")

    errors, _ = validate_policy(mutated)

    assert any("fixture.forbidden_operations must include push_to_staterail" in error for error in errors)


def test_phase209_rejects_missing_source_hint() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["source_hints"] = ["missing/source.py"]

    errors, _ = validate_policy(mutated)

    assert any("source_hints path does not exist in fixture: missing/source.py" in error for error in errors)


def test_phase209_rejects_wrong_fixture_commit() -> None:
    mutated = copy.deepcopy(policy())
    mutated["fixture"]["expected_commit"] = "0000000000000000000000000000000000000000"

    errors, _ = validate_policy(mutated)

    assert any("does not match expected_commit" in error for error in errors)
