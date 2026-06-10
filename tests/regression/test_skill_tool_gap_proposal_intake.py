from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_tool_gap_proposal_intake import (
    SkillToolGapProposalIntakeConfig,
    build_intake_report,
    read_json_object,
    run_skill_tool_gap_proposal_intake,
    validate_intake_policy,
    validate_intake_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "skill_tool_gap_proposal_intake_policy.json"
SOURCE_POLICY_PATH = REPO_ROOT / "runtime" / "skill_tool_coverage_gap_policy.json"
PROMPT_COVERAGE_PATH = REPO_ROOT / "runtime" / "prompt_skill_coverage.json"
CAPABILITY_BACKLOG_PATH = REPO_ROOT / "runtime" / "natural_language_capability_gap_backlog.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def source_candidate(candidate_id: str = "STG-001") -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "source": "priority0_gap_taxonomy",
        "source_finding": {
            "category": "evidence_miss",
            "severity": "high",
            "message": "selected deterministic tool was missing",
        },
        "gap_class": "skill_tool_selection",
        "repair_action": "Add a deterministic lookup tool only if prompt or formatter repair is insufficient.",
        "capability_type": "tool",
        "capability_id": "deterministic.endpoint_lookup",
        "proposal_summary": "Add a deterministic endpoint lookup tool with bounded file search and route evidence.",
        "eval_gate": "endpoint_lookup_tool_eval",
        "validation_tier": "gateway_anythingllm",
        "approval_boundary": "roadmap_approval_required",
        "capability_backlog_ref": "P93-004",
        "status": "proposed",
    }


def source_report_with_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "skill_tool_coverage_gap_report",
        "status": "passed",
        "gap_candidates": candidates,
        "non_skill_tool_records": [],
        "summary": {
            "skill_tool_finding_count": len(candidates),
            "gap_candidate_count": len(candidates),
            "prompt_tightening_candidate_count": 0,
            "implemented_coverage_entry_count": 38,
            "new_capability_required": bool(candidates),
            "next_action": "review proposed skill/tool gaps before adding skills or tools" if candidates else "none",
        },
        "errors": [],
    }


def policy_with_source_report(tmp_path: Path, source_report: dict[str, Any]) -> dict[str, Any]:
    value = policy()
    source_path = write_json(tmp_path / "source-skill-tool-gap-report.json", source_report)
    value["source_skill_tool_gap_report"] = {
        "path": str(source_path),
        "sha256": sha256_file(source_path),
        "expected_status": "passed",
        "expected_new_capability_required": bool(source_report.get("gap_candidates")),
    }
    return value


def proposal_from_source(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": "STGP-001",
        "source": "skill_tool_coverage_gap_report",
        "source_candidate_id": candidate["candidate_id"],
        "capability_type": candidate["capability_type"],
        "capability_id": candidate["capability_id"],
        "scope": "Add one deterministic endpoint lookup capability with bounded search, route evidence, and no source mutation.",
        "eval_gate": candidate["eval_gate"],
        "validation_tier": candidate["validation_tier"],
        "approval_boundary": candidate["approval_boundary"],
        "status": "pending_approval",
        "implementation_status": "not_started",
        "auto_register": False,
        "source_mutation_required": False,
        "prompt_or_formatter_repair_insufficient": True,
    }


def test_project_skill_tool_gap_proposal_intake_passes_current_no_gap_policy() -> None:
    report = run_skill_tool_gap_proposal_intake(
        SkillToolGapProposalIntakeConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "skill-tool-gap-proposal-intake" / "unit-project.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["source_gap_candidate_count"] == 0
    assert report["summary"]["proposal_count"] == 0
    assert report["summary"]["error_count"] == 0


def test_skill_tool_gap_proposal_intake_requires_proposal_for_source_gap(tmp_path: Path) -> None:
    candidate = source_candidate()
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate]))

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("proposals missing source gap candidate" in error for error in errors)


def test_skill_tool_gap_proposal_intake_accepts_pending_approval_proposal(tmp_path: Path) -> None:
    candidate = source_candidate()
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate]))
    value["proposals"] = [proposal_from_source(candidate)]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert errors == []


def test_skill_tool_gap_proposal_intake_rejects_stale_source_hash(tmp_path: Path) -> None:
    value = policy_with_source_report(tmp_path, source_report_with_candidates([]))
    value["source_skill_tool_gap_report"]["sha256"] = "0" * 64

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("source_skill_tool_gap_report.sha256 is stale" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_unknown_source_candidate(tmp_path: Path) -> None:
    value = policy_with_source_report(tmp_path, source_report_with_candidates([]))
    candidate = source_candidate()
    value["proposals"] = [proposal_from_source(candidate)]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("unknown source gap candidate" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_started_implementation(tmp_path: Path) -> None:
    candidate = source_candidate()
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate]))
    proposal = proposal_from_source(candidate)
    proposal["implementation_status"] = "scaffolded"
    value["proposals"] = [proposal]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("implementation_status must be not_started" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_auto_register_or_source_mutation(tmp_path: Path) -> None:
    candidate = source_candidate()
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate]))
    proposal = proposal_from_source(candidate)
    proposal["auto_register"] = True
    proposal["source_mutation_required"] = True
    value["proposals"] = [proposal]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("auto_register must be false" in error for error in errors)
    assert any("source_mutation_required must be false" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_prompt_or_formatter_not_ruled_out(tmp_path: Path) -> None:
    candidate = source_candidate()
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate]))
    proposal = proposal_from_source(candidate)
    proposal["prompt_or_formatter_repair_insufficient"] = False
    value["proposals"] = [proposal]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("prompt_or_formatter_repair_insufficient must be true" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_mismatched_candidate_fields(tmp_path: Path) -> None:
    candidate = source_candidate()
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate]))
    proposal = proposal_from_source(candidate)
    proposal["capability_id"] = "wrong.capability"
    value["proposals"] = [proposal]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("capability_id must match source gap candidate" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_duplicate_proposal_ids(tmp_path: Path) -> None:
    candidate_a = source_candidate("STG-001")
    candidate_b = source_candidate("STG-002")
    candidate_b["capability_id"] = "deterministic.config_lookup"
    value = policy_with_source_report(tmp_path, source_report_with_candidates([candidate_a, candidate_b]))
    proposal_a = proposal_from_source(candidate_a)
    proposal_b = proposal_from_source(candidate_b)
    proposal_b["proposal_id"] = proposal_a["proposal_id"]
    value["proposals"] = [proposal_a, proposal_b]

    errors = validate_intake_policy(value, config_root=REPO_ROOT, require_artifacts=True)

    assert any("duplicate proposal_id" in error for error in errors)


def test_skill_tool_gap_proposal_intake_rejects_hidden_summary_change() -> None:
    value = policy()
    report = build_intake_report(policy=value, config_root=REPO_ROOT, policy_path=POLICY_PATH, require_artifacts=True)
    tampered = copy.deepcopy(report)
    tampered["summary"]["proposal_count"] = 99

    errors = validate_intake_report(
        tampered,
        policy=value,
        config_root=REPO_ROOT,
        policy_path=POLICY_PATH,
        require_artifacts=True,
    )

    assert any("report.summary must match rebuilt skill/tool gap proposal intake report" in error for error in errors)
