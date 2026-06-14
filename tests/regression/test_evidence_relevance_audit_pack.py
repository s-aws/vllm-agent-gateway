from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.evidence_relevance_audit_pack import (
    DEFAULT_POLICY_PATH,
    EvidenceRelevanceAuditPackConfig,
    read_json_object,
    validate_evidence_relevance_audit_pack,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def test_phase206_policy_passes() -> None:
    assert validate_policy(policy(), config_root=REPO_ROOT) == []


def test_phase206_validator_writes_report(tmp_path: Path) -> None:
    report = validate_evidence_relevance_audit_pack(
        EvidenceRelevanceAuditPackConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase206-report.json",
            markdown_output_path=tmp_path / "phase206-report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 4
    assert report["summary"]["phase207_ready"] is True
    assert (tmp_path / "phase206-report.json").is_file()
    assert (tmp_path / "phase206-report.md").read_text(encoding="utf-8").startswith("# Evidence Relevance Audit Pack")
    assert len(report["source_report_proofs"]) == 2
    assert "## Source Reports" in (tmp_path / "phase206-report.md").read_text(encoding="utf-8")


def test_phase206_policy_rejects_missing_required_category() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"] = [case for case in mutated["cases"] if case["category"] != "change_boundary_analysis"]

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("policy.cases missing required categories: change_boundary_analysis" in error for error in errors)


def test_phase206_policy_rejects_incomplete_evidence_tiers() -> None:
    mutated = copy.deepcopy(policy())
    del mutated["cases"][0]["blind_baseline"]["evidence_tier_definitions"]["direct"]

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("evidence_tier_definitions.direct" in error for error in errors)


def test_phase206_policy_rejects_rubric_not_100_points() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["blind_baseline"]["scoring_rubric"][0]["points"] = 1

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("scoring_rubric points must total 100" in error for error in errors)


def test_phase206_policy_rejects_source_catalog_prompt_drift() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["prompt"] = "drifted prompt"

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("prompt must match source catalog case prompt" in error for error in errors)


def test_phase206_policy_rejects_phase205_prompt_family_drift() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][1]["prompt_family"] = "drifted-family"

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("prompt_family must match Phase 205 replay proof" in error for error in errors)


def test_phase206_policy_rejects_unknown_gap_class() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["current_gap_classifications"][0]["gap_class"] = "made_up_gap"

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("gap_class 'made_up_gap' is not policy-approved" in error for error in errors)


def test_phase206_policy_rejects_failed_source_report(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    source_report = tmp_path / "failed-source.json"
    source_report.write_text(
        json.dumps({"phase": "182", "status": "failed", "live": True, "errors": ["bad"]}),
        encoding="utf-8",
    )
    mutated["required_source_reports"][0]["path"] = str(source_report)

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("source_report phase182_evidence_relevance_ranking_live status expected 'passed' got 'failed'" in error for error in errors)
    assert any("source_report phase182_evidence_relevance_ranking_live must not contain errors" in error for error in errors)


def test_phase206_policy_rejects_structured_source_report_errors(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    source_report = tmp_path / "structured-errors-source.json"
    source_report.write_text(
        json.dumps({"phase": "182", "status": "passed", "live": True, "errors": [{"message": "bad"}]}),
        encoding="utf-8",
    )
    mutated["required_source_reports"][0]["path"] = str(source_report)

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("source_report phase182_evidence_relevance_ranking_live must not contain errors" in error for error in errors)


def test_phase206_policy_rejects_replaced_source_dependency_identity() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_source_reports"][1]["id"] = "replacement_route_report"

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("policy.required_source_reports must be exactly" in error for error in errors)


def test_phase206_policy_rejects_missing_line_level_requirement() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["blind_baseline"]["ideal_answer_shape"] = ["Begin with the likely beginning point and confidence."]
    mutated["cases"][0]["blind_baseline"]["must_have_evidence"] = ["The first function tied to the lookup."]

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("must require line-level evidence" in error for error in errors)
