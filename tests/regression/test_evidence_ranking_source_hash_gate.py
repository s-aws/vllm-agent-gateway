from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.evidence_ranking_source_hash_gate import (
    DEFAULT_POLICY_PATH,
    EvidenceRankingSourceHashGateConfig,
    case_report,
    is_sha256,
    negative_control_report,
    read_json_object,
    source_proofs_for_refs,
    validate_evidence_ranking_source_hash_gate,
    validate_policy,
    validate_source_reports,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def policy() -> dict:
    return read_json_object(REPO_ROOT / DEFAULT_POLICY_PATH)


def test_phase207_policy_passes() -> None:
    assert validate_policy(policy(), config_root=REPO_ROOT) == []


def test_phase207_validator_writes_report(tmp_path: Path) -> None:
    report = validate_evidence_ranking_source_hash_gate(
        EvidenceRankingSourceHashGateConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase207-report.json",
            markdown_output_path=tmp_path / "phase207-report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 4
    assert report["summary"]["negative_control_count"] == 3
    assert report["summary"]["failed_negative_control_count"] == 0
    assert report["summary"]["phase208_ready"] is True
    assert report["summary"]["source_hash_count"] >= 4
    assert (tmp_path / "phase207-report.md").read_text(encoding="utf-8").startswith("# Evidence Ranking Source Hash Gate")


def test_phase207_case_report_contains_sha256_source_proof() -> None:
    active_policy = policy()
    report = case_report(active_policy, active_policy["cases"][0])

    assert report["status"] == "passed"
    assert report["source_proofs"]
    assert all(is_sha256(item.get("sha256")) for item in report["source_proofs"])
    assert all(is_sha256(item.get("line_sha256")) for item in report["source_proofs"])
    assert all(item.get("line_contains_query") is True for item in report["source_proofs"])


def test_phase207_source_proof_rejects_stale_line_query() -> None:
    active_policy = policy()

    _, errors = source_proofs_for_refs(
        Path(active_policy["target_root"]),
        [{"path": "core/stealth_order_manager.py", "line": 4169, "query": "not_present_on_this_line"}],
    )

    assert any("does not contain query" in error for error in errors)


def test_phase207_negative_controls_pass_and_keep_direct_evidence_first() -> None:
    active_policy = policy()
    reports = [negative_control_report(active_policy, control) for control in active_policy["negative_controls"]]

    assert reports
    assert all(report["status"] == "passed" for report in reports)
    hinted_control = next(report for report in reports if report["control_id"] == "P207-NC-002")
    assert hinted_control["top_path"] == "core/stealth_order_manager.py"
    repeated_hinted_control = next(report for report in reports if report["control_id"] == "P207-NC-003")
    assert repeated_hinted_control["top_path"] == "core/stealth_order_manager.py"
    assert repeated_hinted_control["evidence_records"][1]["path"] == "core/order_engine.py"
    assert repeated_hinted_control["evidence_records"][1]["relevance"]["tier"] == "strong"


def test_phase207_policy_rejects_missing_audit_case() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["audit_case_id"] = "missing-case"

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("audit_case_id must exist in Phase 206 report" in error for error in errors)


def test_phase207_policy_rejects_phase206_category_drift() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["category"] = "related_test_discovery"

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("category must match Phase 206 audit case category" in error for error in errors)


def test_phase207_policy_rejects_phase206_semantic_term_drift() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["phase206_required_terms"] = ["term-not-in-baseline-or-evidence"]

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("missing from Phase 206 baseline" in error for error in errors)
    assert any("missing from Phase 207 evidence" in error for error in errors)


def test_phase207_policy_rejects_missing_source_file() -> None:
    mutated = copy.deepcopy(policy())
    mutated["cases"][0]["direct_paths"] = ["missing.py"]

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert any("direct_paths missing source file missing.py" in error for error in errors)


def test_phase207_policy_rejects_missing_negative_controls() -> None:
    mutated = copy.deepcopy(policy())
    mutated["negative_controls"] = []

    errors = validate_policy(mutated, config_root=REPO_ROOT)

    assert "policy.negative_controls below policy.minimum_negative_control_count" in errors


def test_phase207_case_report_rejects_weak_top_evidence() -> None:
    active_policy = copy.deepcopy(policy())
    active_policy["cases"][0]["matches"] = [
        {"path": "core/order_engine.py", "line": 1, "query": "find_stealth_order_by_placed_order_id", "source": "phase207_synthetic"},
        {"path": "core/stealth_order_manager.py", "line": 1, "query": "id", "source": "phase207_synthetic"},
    ]

    report = case_report(active_policy, active_policy["cases"][0])

    assert report["status"] == "failed"
    assert any("top evidence path" in error for error in report["errors"])


def test_phase207_rejects_failed_phase206_source_report(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    source_report = tmp_path / "phase206-failed.json"
    source_report.write_text(
        json.dumps({"phase": 206, "status": "failed", "summary": {"phase207_ready": False}, "errors": ["bad"]}),
        encoding="utf-8",
    )
    mutated["phase206_audit_pack_report_path"] = str(source_report)

    errors = validate_source_reports(REPO_ROOT, mutated)

    assert "phase206 source report status must be passed" in errors
    assert "phase206 source report must have summary.phase207_ready=true" in errors
    assert "phase206 source report must not contain errors" in errors


def test_phase207_rejects_non_live_phase182_source_report(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    source_report = tmp_path / "phase182-offline.json"
    source_report.write_text(
        json.dumps({"phase": "182", "status": "passed", "live": False, "errors": []}),
        encoding="utf-8",
    )
    mutated["phase182_evidence_ranking_report_path"] = str(source_report)

    errors = validate_source_reports(REPO_ROOT, mutated)

    assert "phase182 source report must be live" in errors


def test_phase207_rejects_incomplete_phase182_live_report(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    source_report = tmp_path / "phase182-incomplete.json"
    source_report.write_text(
        json.dumps(
            {
                "phase": "182",
                "status": "passed",
                "live": True,
                "live_case_count": 4,
                "live_passed_case_count": 3,
                "live_cases": [
                    {
                        "status": "passed",
                        "errors": [],
                        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
                    }
                ],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    mutated["phase182_evidence_ranking_report_path"] = str(source_report)

    errors = validate_source_reports(REPO_ROOT, mutated)

    assert "phase182 source report live_case_count must equal live_passed_case_count" in errors
    assert "phase182 source report live_cases length must equal live_case_count" in errors
    assert "phase182 source report missing live target_root /mnt/c/coinbase_testing_repo_frozen_tmp.github" in errors
