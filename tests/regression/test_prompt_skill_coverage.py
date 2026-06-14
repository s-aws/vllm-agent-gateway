from __future__ import annotations

import json
import shutil
from pathlib import Path

from vllm_agent_gateway.skills.prompt_coverage import PromptCoverageConfig, validate_prompt_coverage


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def copy_prompt_coverage_root(tmp_path: Path) -> Path:
    root = tmp_path / "coverage-root"
    shutil.copytree(REPO_ROOT / "runtime", root / "runtime")
    shutil.copytree(REPO_ROOT / "docs", root / "docs")
    for name in ("README.controlled-apply.md", "README.task-decomposition.md"):
        shutil.copy2(REPO_ROOT / name, root / name)
    router_path = root / "vllm_agent_gateway" / "controllers" / "workflow_router" / "plan.py"
    router_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "vllm_agent_gateway" / "controllers" / "workflow_router" / "plan.py", router_path)
    return root


def test_project_prompt_skill_coverage_registry_passes(tmp_path: Path) -> None:
    report = validate_prompt_coverage(
        PromptCoverageConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "coverage-report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["entry_count"] >= 30
    assert report["summary"]["gap_count"] >= 1
    assert report["summary"]["error_count"] == 0


def test_prompt_skill_coverage_records_multi_repo_fixture_targets() -> None:
    manifest = json.loads((REPO_ROOT / "runtime" / "prompt_skill_coverage.json").read_text(encoding="utf-8"))
    entries = {item["id"]: item for item in manifest["entries"]}

    assert entries["FX-001"]["status"] == "implemented"
    assert entries["FX-001"]["fixture_targets"][0]["fixture_id"] == "python-service-generalization"
    assert entries["FX-001"]["route_rule"] == "l1_endpoint_route_lookup_terms"
    assert entries["FX-001"]["additional_route_rules"] == ["l1_data_model_lookup_terms"]
    assert entries["FX-001"]["eval_case_ids"] == [
        "phase230_python_service_endpoint_route_lookup",
        "phase230_python_service_data_model_lookup",
    ]
    assert entries["FX-002"]["status"] == "planned"
    assert entries["FX-002"]["fixture_targets"][0]["fixture_id"] == "node-cli-generalization"
    assert "hardcoded" in entries["FX-002"]["fixture_targets"][0]["behavior"]


def test_prompt_skill_coverage_rejects_stale_skill_id(tmp_path: Path) -> None:
    root = copy_prompt_coverage_root(tmp_path)
    coverage_path = root / "runtime" / "prompt_skill_coverage.json"
    manifest = json.loads(coverage_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["skill_ids"] = ["missing-skill"]
    write_json(coverage_path, manifest)

    report = validate_prompt_coverage(
        PromptCoverageConfig(
            config_root=root,
            output_path=tmp_path / "coverage-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any("unknown skill_id" in error["message"] for error in report["errors"])


def test_prompt_skill_coverage_rejects_missing_route_rule(tmp_path: Path) -> None:
    root = copy_prompt_coverage_root(tmp_path)
    coverage_path = root / "runtime" / "prompt_skill_coverage.json"
    manifest = json.loads(coverage_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["route_rule"] = "l1_missing_route_terms"
    write_json(coverage_path, manifest)

    report = validate_prompt_coverage(
        PromptCoverageConfig(
            config_root=root,
            output_path=tmp_path / "coverage-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any("route_rule must exist" in error["message"] for error in report["errors"])
    assert any("founder field rule is not covered" in error["message"] for error in report["errors"])


def test_prompt_skill_coverage_requires_deferred_advanced_refactor_gap(tmp_path: Path) -> None:
    root = copy_prompt_coverage_root(tmp_path)
    coverage_path = root / "runtime" / "prompt_skill_coverage.json"
    manifest = json.loads(coverage_path.read_text(encoding="utf-8"))
    manifest["gap_backlog"] = [gap for gap in manifest["gap_backlog"] if gap["id"] != "GAP-ADV-REFACTOR-SINGLE-PATH"]
    write_json(coverage_path, manifest)

    report = validate_prompt_coverage(
        PromptCoverageConfig(
            config_root=root,
            output_path=tmp_path / "coverage-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any(error["entry_id"] == "GAP-ADV-REFACTOR-SINGLE-PATH" for error in report["errors"])
