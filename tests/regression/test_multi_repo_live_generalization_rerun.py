from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (
    fixture_state,
    read_json_object,
)
from vllm_agent_gateway.acceptance.multi_repo_live_generalization_rerun import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PREFLIGHT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    MultiRepoLiveGeneralizationRerunConfig,
    validate_multi_repo_live_generalization_rerun,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def test_phase212_policy_preflight_passes() -> None:
    errors, phase209_policy, phase211_report = validate_policy(policy(), config_root=REPO_ROOT)

    assert errors == []
    assert len(phase209_policy["cases"]) == 5
    assert phase211_report["status"] == "passed"


def test_phase212_validator_writes_preflight_report(tmp_path: Path) -> None:
    report = validate_multi_repo_live_generalization_rerun(
        MultiRepoLiveGeneralizationRerunConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase212-report.json",
            markdown_output_path=tmp_path / "phase212-report.md",
            live=False,
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["summary"]["target_case_count"] == 5
    assert report["summary"]["holdout_case_count"] == 4
    assert report["summary"]["repository_count"] == 3
    assert (tmp_path / "phase212-report.json").is_file()
    assert (tmp_path / "phase212-report.md").read_text(encoding="utf-8").startswith("# Multi-Repo Live Generalization Rerun")


def test_phase212_default_preflight_does_not_overwrite_live_report_path() -> None:
    report = validate_multi_repo_live_generalization_rerun(
        MultiRepoLiveGeneralizationRerunConfig(config_root=REPO_ROOT, live=False)
    )

    assert report["status"] == "preflight_passed"
    assert Path(report["report_path"]).name == DEFAULT_PREFLIGHT_OUTPUT_PATH.name
    assert Path(report["report_path"]).name != DEFAULT_OUTPUT_PATH.name


def test_phase212_policy_rejects_missing_required_coinbase_plain_root() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_target_roots"] = [
        "/mnt/c/staterail_testing_repo_frozen_tmp.github",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    ]

    errors, _, _ = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("/mnt/c/coinbase_testing_repo_frozen_tmp" in error for error in errors)


def test_phase212_policy_rejects_missing_holdouts() -> None:
    mutated = copy.deepcopy(policy())
    mutated["holdout_cases"] = mutated["holdout_cases"][:1]

    errors, _, _ = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("holdout_cases below minimum_holdout_case_count" in error for error in errors)


def test_non_git_fixture_state_hashes_case_hints(tmp_path: Path) -> None:
    target = tmp_path / "plain-fixture"
    source = target / "core" / "service.py"
    test_file = target / "tests" / "test_service.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    source.write_text("def service():\n    return 1\n", encoding="utf-8")
    test_file.write_text("def test_service():\n    assert True\n", encoding="utf-8")

    state = fixture_state(
        {
            "target_root": str(target),
            "source_hints": ["core/service.py"],
            "test_hints": ["tests/test_service.py"],
        }
    )

    assert state["mode"] == "path_hashes"
    assert sorted(state["hashes"]) == ["core/service.py", "tests/test_service.py"]
