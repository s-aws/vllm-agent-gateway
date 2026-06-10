from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import sha256_file
from vllm_agent_gateway.acceptance.baseline_corpus_promotion_rules import (
    REQUIRED_EVIDENCE,
    BaselineCorpusPromotionRulesConfig,
    build_promotion_rules_report,
    run_promotion_rules_gate,
    validate_promotion_rules,
    validate_promotion_rules_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / "runtime" / "baseline_corpus_promotion_rules.json"


def load_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def project_report(rules: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_promotion_rules_report(
        rules=rules or load_rules(),
        config_root=REPO_ROOT,
        rules_path=RULES_PATH,
        require_artifacts=True,
    )


def candidate_case_ids(rules: dict[str, Any]) -> list[str]:
    return list(rules["candidates"][0]["source_case_ids"])


def evidence_ref(evidence_type: str, path: str, *, case_ids: list[str], **fields: Any) -> dict[str, Any]:
    artifact_path = REPO_ROOT / path
    return {
        "evidence_type": evidence_type,
        "path": path,
        "sha256": sha256_file(artifact_path),
        "case_ids": case_ids,
        **fields,
    }


def write_artifact(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def full_evidence_paths(tmp_path: Path, case_ids: list[str]) -> dict[str, str]:
    comparison_cases = [
        {
            "case_id": case_id,
            "routes": [
                {"route": "anythingllm", "pass": True, "score": 90, "unresolved_findings": []},
                {"route": "gateway", "pass": True, "score": 90, "unresolved_findings": []},
            ],
        }
        for case_id in case_ids
    ]
    route_cases = [
        {
            "case_id": case_id,
            "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
            if index % 2
            else "/mnt/c/coinbase_testing_repo_frozen_tmp",
        }
        for index, case_id in enumerate(case_ids)
    ]
    return {
        "blind_baseline": write_artifact(
            tmp_path / "candidate-blind-baselines.json",
            {
                "kind": "phase142_candidate_blind_baselines",
                "baseline_policy": {
                    "blind_agent_context": "contextless",
                    "local_model_output_seen": False,
                    "source_mutation_allowed": False,
                },
                "baselines": [{"case_id": case_id} for case_id in case_ids],
            },
        ),
        "local_model_comparison": write_artifact(
            tmp_path / "candidate-comparison.json",
            {
                "kind": "phase142_candidate_comparison",
                "status": "passed",
                "cases": comparison_cases,
            },
        ),
        "holdout": write_artifact(
            tmp_path / "candidate-holdouts.json",
            {
                "kind": "priority0_holdout_prompt_bank",
                "entries": [{"entry_id": "phase142_candidate", "holdout_case_ids": ["H142-001", "H142-002"]}],
            },
        ),
        "route_proof": write_artifact(
            tmp_path / "candidate-route-proof.json",
            {
                "kind": "phase142_candidate_route_proof",
                "cases": route_cases,
            },
        ),
        "no_mutation_proof": write_artifact(
            tmp_path / "candidate-no-mutation.json",
            {
                "kind": "phase142_candidate_no_mutation_proof",
                "runtime_changed_files": [],
                "target_changed_files": {},
                "target_git_changed": {},
            },
        ),
    }


def approve_candidate(rules: dict[str, Any], tmp_path: Path) -> None:
    case_ids = candidate_case_ids(rules)
    paths = full_evidence_paths(tmp_path, case_ids)
    candidate = rules["candidates"][0]
    candidate["decision_status"] = "approved_for_promotion"
    candidate["missing_evidence"] = []
    candidate["founder_approval"] = {
        "status": "approved",
        "approved_by": "founder",
        "approved_at": "2026-06-09T00:00:00Z",
    }
    candidate["evidence_refs"] = [
        evidence_ref(
            "blind_baseline",
            paths["blind_baseline"],
            case_ids=case_ids,
        ),
        evidence_ref(
            "local_model_comparison",
            paths["local_model_comparison"],
            case_ids=case_ids,
            status="passed",
            minimum_score=90,
            critical_finding_count=0,
            high_finding_count=0,
        ),
        evidence_ref(
            "holdout",
            paths["holdout"],
            case_ids=case_ids,
            status="passed",
            holdout_case_count=2,
            holdout_case_ids=["H142-001", "H142-002"],
        ),
        evidence_ref(
            "route_proof",
            paths["route_proof"],
            case_ids=case_ids,
            routes=["anythingllm", "gateway"],
            target_roots=[
                "/mnt/c/coinbase_testing_repo_frozen_tmp",
                "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
            ],
        ),
        evidence_ref(
            "no_mutation_proof",
            paths["no_mutation_proof"],
            case_ids=case_ids,
            runtime_changed_files=[],
            target_changed_files={},
            target_git_changed={},
        ),
    ]


def test_project_baseline_corpus_promotion_rules_pass_with_blocked_candidate() -> None:
    report = run_promotion_rules_gate(
        BaselineCorpusPromotionRulesConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT / "runtime-state" / "baseline-corpus-promotion-rules" / "unit-project.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["blocked_candidate_count"] == 1
    assert report["summary"]["approved_candidate_count"] == 0
    assert report["summary"]["error_count"] == 0


def test_baseline_corpus_promotion_rules_allow_approved_candidate_with_full_proof(tmp_path: Path) -> None:
    rules = load_rules()
    approve_candidate(rules, tmp_path)

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT, require_artifacts=True)

    assert errors == []


def test_baseline_corpus_promotion_rules_reject_missing_required_evidence_policy() -> None:
    rules = load_rules()
    rules["promotion_policy"]["required_evidence"] = ["blind_baseline"]

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT)

    assert any("required_evidence" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_stale_source_hash() -> None:
    rules = load_rules()
    rules["source_corpus"]["sha256"] = "0" * 64

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT)

    assert any("source_corpus.sha256 is stale" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_approval_without_artifact_evidence() -> None:
    rules = load_rules()
    candidate = rules["candidates"][0]
    candidate["decision_status"] = "approved_for_promotion"
    candidate["missing_evidence"] = []
    candidate["founder_approval"] = {
        "status": "approved",
        "approved_by": "founder",
        "approved_at": "2026-06-09T00:00:00Z",
    }

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT)

    assert any("evidence_refs missing artifact evidence" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_missing_founder_approval(tmp_path: Path) -> None:
    rules = load_rules()
    approve_candidate(rules, tmp_path)
    rules["candidates"][0]["founder_approval"] = {"status": "not_requested"}

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT, require_artifacts=True)

    assert any("founder_approval.status must be approved" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_low_comparison_score(tmp_path: Path) -> None:
    rules = load_rules()
    approve_candidate(rules, tmp_path)
    comparison = next(item for item in rules["candidates"][0]["evidence_refs"] if item["evidence_type"] == "local_model_comparison")
    comparison["minimum_score"] = 84

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT, require_artifacts=True)

    assert any("minimum_score must be >= 85" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_evidence_case_id_mismatch(tmp_path: Path) -> None:
    rules = load_rules()
    approve_candidate(rules, tmp_path)
    rules["candidates"][0]["evidence_refs"][0]["case_ids"] = ["P01"]

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT, require_artifacts=True)

    assert any("case_ids must match candidate source_case_ids" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_blocked_candidate_with_approval() -> None:
    rules = load_rules()
    rules["candidates"][0]["founder_approval"] = {
        "status": "approved",
        "approved_by": "founder",
        "approved_at": "2026-06-09T00:00:00Z",
    }

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT)

    assert any("cannot be approved while candidate is blocked" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_promoted_status_in_separate_phase_boundary(tmp_path: Path) -> None:
    rules = load_rules()
    approve_candidate(rules, tmp_path)
    candidate = rules["candidates"][0]
    candidate["decision_status"] = "promoted"
    candidate["proposed_entry_id"] = "phase116_code_quality"

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT, require_artifacts=True)

    assert any("cannot be promoted while stable corpus update requires a separate phase" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_prompt_pack_case_drift() -> None:
    rules = load_rules()
    rules["candidates"][0]["source_case_ids"] = ["P01"]

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT)

    assert any("source_case_ids must match" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_duplicate_proposed_entry_id() -> None:
    rules = load_rules()
    duplicate = copy.deepcopy(rules["candidates"][0])
    duplicate["candidate_id"] = "duplicate-candidate"
    rules["candidates"].append(duplicate)

    errors = validate_promotion_rules(rules, config_root=REPO_ROOT)

    assert any("duplicate proposed_entry_id" in error for error in errors)


def test_baseline_corpus_promotion_rules_reject_hidden_summary_change() -> None:
    rules = load_rules()
    report = project_report(rules)
    tampered = copy.deepcopy(report)
    tampered["summary"]["candidate_count"] = 99

    errors = validate_promotion_rules_report(
        tampered,
        rules=rules,
        config_root=REPO_ROOT,
        rules_path=RULES_PATH,
        require_artifacts=True,
    )

    assert any("report.summary must match rebuilt baseline corpus promotion rules report" in error for error in errors)


def test_baseline_corpus_promotion_rules_required_evidence_constant_matches_policy() -> None:
    rules = load_rules()

    assert set(rules["promotion_policy"]["required_evidence"]) == REQUIRED_EVIDENCE
