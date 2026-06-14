from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.skill_library_scaling_readiness_inventory import (
    SkillLibraryScalingReadinessInventoryConfig,
    validate_policy,
    validate_skill_library_scaling_readiness_inventory,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "skill_library_scaling_readiness_inventory_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_phase229_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase229_policy_rejects_advanced_refactor_scope() -> None:
    mutated = copy.deepcopy(policy())
    mutated["selection_rules"]["advanced_refactor_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.selection_rules.advanced_refactor_allowed" for item in errors)


def test_phase229_policy_rejects_manual_skill_injection() -> None:
    mutated = copy.deepcopy(policy())
    mutated["selection_rules"]["manual_skill_injection_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.selection_rules.manual_skill_injection_allowed" for item in errors)


def test_phase229_rejects_recommended_candidate_that_is_not_fixture_level(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["phase230_recommended_candidate_id"] = "L1-001"
    path = tmp_path / "policy.json"
    write_json(path, mutated)

    report = validate_skill_library_scaling_readiness_inventory(
        SkillLibraryScalingReadinessInventoryConfig(
            config_root=REPO_ROOT,
            policy_path=path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "phase230_recommended_candidate_id" for item in report["validation_errors"])


def test_phase229_project_report_passes() -> None:
    report = validate_skill_library_scaling_readiness_inventory(
        SkillLibraryScalingReadinessInventoryConfig(config_root=REPO_ROOT)
    )

    assert report["status"] == "passed"
    assert report["summary"]["implemented_count"] >= 39
    assert report["summary"]["planned_count"] == 1
    assert report["summary"]["phase230_recommended_candidate_id"] == "FX-001"
    assert report["summary"]["phase230_recommended_candidate_status"] == "implemented"
    assert report["summary"]["new_runtime_skill_required"] is False
    assert report["summary"]["phase230_ready"] is True
