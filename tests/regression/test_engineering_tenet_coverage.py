from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.engineering_tenet_coverage import (
    DEFAULT_MATRIX_PATH,
    EngineeringTenetCoverageConfig,
    EXPECTED_TENETS,
    run_engineering_tenet_coverage,
    validate_matrix,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_project_matrix() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_MATRIX_PATH).read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_report(tmp_path: Path, matrix: dict[str, object]) -> dict[str, object]:
    matrix_path = write_json(tmp_path / "matrix.json", matrix)
    return run_engineering_tenet_coverage(
        EngineeringTenetCoverageConfig(
            config_root=tmp_path,
            matrix_path=matrix_path,
            output_path=tmp_path / "tenet-coverage.json",
            markdown_output_path=tmp_path / "tenet-coverage.md",
        )
    )


def test_project_engineering_tenet_coverage_matrix_passes() -> None:
    report = run_engineering_tenet_coverage(
        EngineeringTenetCoverageConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "engineering-tenet-coverage" / "unit-project.json",
            markdown_output_path=REPO_ROOT / "runtime-state" / "engineering-tenet-coverage" / "unit-project.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["tenet_count"] == len(EXPECTED_TENETS)  # type: ignore[index]
    assert report["summary"]["status_counts"]["covered"] == len(EXPECTED_TENETS)  # type: ignore[index]
    assert report["summary"]["status_counts"]["partially_covered"] == 0  # type: ignore[index]
    assert report["summary"]["status_counts"]["not_covered"] == 0  # type: ignore[index]


def test_engineering_tenet_coverage_rejects_missing_tenet(tmp_path: Path) -> None:
    matrix = load_project_matrix()
    matrix["entries"] = matrix["entries"][:-1]  # type: ignore[index]

    report = run_report(tmp_path, matrix)

    assert report["status"] == "failed"
    assert any("missing tenet IDs: T20" in error for error in report["errors"])  # type: ignore[index]


def test_engineering_tenet_coverage_rejects_duplicate_tenet(tmp_path: Path) -> None:
    matrix = load_project_matrix()
    entries = matrix["entries"]  # type: ignore[index]
    matrix["entries"] = [*entries, copy.deepcopy(entries[0])]  # type: ignore[index]

    report = run_report(tmp_path, matrix)

    assert report["status"] == "failed"
    assert any("duplicated" in error for error in report["errors"])  # type: ignore[index]


def test_engineering_tenet_coverage_rejects_unsupported_status() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["status"] = "mostly_done"  # type: ignore[index]

    errors = validate_matrix(matrix)

    assert any("supported coverage status" in error for error in errors)


def test_engineering_tenet_coverage_rejects_missing_evidence_for_partial_entry() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["chat_visible_evidence"] = []  # type: ignore[index]

    errors = validate_matrix(matrix)

    assert any("covered entries must define chat-visible evidence" in error for error in errors)


def test_engineering_tenet_coverage_rejects_unapproved_advanced_refactor_dependency() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["dependencies"] = ["advanced_refactor"]  # type: ignore[index]

    errors = validate_matrix(matrix, REPO_ROOT)

    assert any("advanced-refactor" in error for error in errors)


def test_engineering_tenet_coverage_rejects_unknown_workflow_reference() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["current_workflows"] = ["release_adherence.report"]  # type: ignore[index]

    errors = validate_matrix(matrix, REPO_ROOT)

    assert any("current_workflows contains unknown reference" in error for error in errors)


def test_engineering_tenet_coverage_rejects_unknown_tool_reference() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["tools"] = ["git_status"]  # type: ignore[index]

    errors = validate_matrix(matrix, REPO_ROOT)

    assert any("tools contains unknown reference" in error for error in errors)


def test_engineering_tenet_coverage_rejects_missing_live_validator_path() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["live_validators"] = ["scripts/validate_missing_tenet_gate.py"]  # type: ignore[index]

    errors = validate_matrix(matrix, REPO_ROOT)

    assert any("live_validators path does not exist" in error for error in errors)


def test_engineering_tenet_coverage_rejects_unknown_eval_case_reference() -> None:
    matrix = load_project_matrix()
    matrix["entries"][0]["eval_cases"] = ["L1-001"]  # type: ignore[index]

    errors = validate_matrix(matrix, REPO_ROOT)

    assert any("eval_cases contains unknown reference" in error for error in errors)
