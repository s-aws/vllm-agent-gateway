"""Validate EIG baseline candidates are ready for founder decision only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    artifact_hash_errors,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.baseline_corpus_promotion_rules import REQUIRED_EVIDENCE
from vllm_agent_gateway.acceptance.eig_baseline_candidate_local_comparison import report_path_from_string


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_baseline_candidate_founder_approval_readiness_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-founder-approval-readiness"
REQUIRED_MILESTONES = {"M2", "M9", "M14", "M19", "M25", "M31", "M36"}
ARTIFACT_EVIDENCE = REQUIRED_EVIDENCE - {"founder_approval"}
EXPECTED_REPORTS = {
    "blind_baseline": {
        "kind": "eig_baseline_candidate_blind_baselines_report",
        "phase": 312,
        "evidence": {"blind_baseline"},
    },
    "local_model_comparison": {
        "kind": "eig_baseline_candidate_local_comparison_report",
        "phase": 313,
        "evidence": {"blind_baseline", "local_model_comparison"},
    },
    "route_and_no_mutation_proof": {
        "kind": "eig_baseline_candidate_route_mutation_proof_report",
        "phase": 315,
        "evidence": {"route_proof", "no_mutation_proof"},
    },
    "holdout": {
        "kind": "eig_baseline_candidate_holdout_proof_report",
        "phase": 316,
        "evidence": {"holdout"},
    },
}


class EIGBaselineCandidateFounderApprovalReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidateFounderApprovalReadinessConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    blind_baseline_report_path: Path | None = None
    local_comparison_report_path: Path | None = None
    route_mutation_report_path: Path | None = None
    holdout_report_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-founder-approval-readiness-{utc_timestamp()}.json"


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_baseline_candidate_founder_approval_readiness_policy":
        errors.append("policy.kind must be eig_baseline_candidate_founder_approval_readiness_policy")
    if policy.get("phase") != 317:
        errors.append("policy.phase must be 317")
    if set(string_list(policy.get("required_milestones"))) != REQUIRED_MILESTONES:
        errors.append("policy.required_milestones must match Phase 317 milestones")

    candidate_source = policy.get("candidate_source") if isinstance(policy.get("candidate_source"), dict) else {}
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="candidate_source",
            path_value=candidate_source.get("path"),
            hash_value=candidate_source.get("sha256"),
            required=True,
        )
    )
    if candidate_source.get("expected_candidate_count") != 2:
        errors.append("candidate_source.expected_candidate_count must be 2")
    if candidate_source.get("expected_total_source_case_count") != 7:
        errors.append("candidate_source.expected_total_source_case_count must be 7")

    baseline = policy.get("baseline_corpus") if isinstance(policy.get("baseline_corpus"), dict) else {}
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="baseline_corpus",
            path_value=baseline.get("path"),
            hash_value=baseline.get("sha256"),
            required=True,
        )
    )
    if baseline.get("expected_entry_count") != 5:
        errors.append("baseline_corpus.expected_entry_count must be 5")

    promotion_policy = policy.get("promotion_policy") if isinstance(policy.get("promotion_policy"), dict) else {}
    if set(string_list(promotion_policy.get("required_evidence"))) != REQUIRED_EVIDENCE:
        errors.append("promotion_policy.required_evidence must match baseline corpus promotion evidence")
    if set(string_list(promotion_policy.get("recorded_evidence_before_founder"))) != ARTIFACT_EVIDENCE:
        errors.append("promotion_policy.recorded_evidence_before_founder must contain all artifact evidence")
    if string_list(promotion_policy.get("remaining_missing_evidence")) != ["founder_approval"]:
        errors.append("promotion_policy.remaining_missing_evidence must be founder_approval only")
    for key in (
        "auto_promote_allowed",
        "stable_corpus_mutation_allowed",
        "stable_corpus_promotion_allowed",
        "founder_approval_recording_allowed",
    ):
        if promotion_policy.get(key) is not False:
            errors.append(f"promotion_policy.{key} must be false")
    for key in ("stable_corpus_update_requires_separate_phase", "founder_approval_required_for_promotion"):
        if promotion_policy.get(key) is not True:
            errors.append(f"promotion_policy.{key} must be true")

    report_entries = object_list(policy.get("required_reports"))
    entries_by_name = {str(item.get("name")): item for item in report_entries if isinstance(item.get("name"), str)}
    if set(entries_by_name) != set(EXPECTED_REPORTS):
        errors.append("required_reports must contain the four Phase 312-316 evidence reports")
    for name, expected in EXPECTED_REPORTS.items():
        entry = entries_by_name.get(name, {})
        if entry.get("kind") != expected["kind"]:
            errors.append(f"required_reports[{name}].kind must be {expected['kind']}")
        if entry.get("phase") != expected["phase"]:
            errors.append(f"required_reports[{name}].phase must be {expected['phase']}")
        if entry.get("status") != "passed":
            errors.append(f"required_reports[{name}].status must be passed")
        if set(string_list(entry.get("recorded_evidence"))) != expected["evidence"]:
            errors.append(f"required_reports[{name}].recorded_evidence must match expected evidence")
        if not isinstance(entry.get("path"), str) or not entry["path"].strip():
            errors.append(f"required_reports[{name}].path is required")
    return errors


def configured_report_paths(
    *,
    policy: dict[str, Any],
    config: EIGBaselineCandidateFounderApprovalReadinessConfig,
) -> dict[str, Path | None]:
    overrides = {
        "blind_baseline": config.blind_baseline_report_path,
        "local_model_comparison": config.local_comparison_report_path,
        "route_and_no_mutation_proof": config.route_mutation_report_path,
        "holdout": config.holdout_report_path,
    }
    entries = {
        str(item.get("name")): item
        for item in object_list(policy.get("required_reports"))
        if isinstance(item.get("name"), str)
    }
    paths: dict[str, Path | None] = {}
    for name in EXPECTED_REPORTS:
        if overrides[name] is not None:
            paths[name] = overrides[name]
        else:
            value = entries.get(name, {}).get("path")
            paths[name] = Path(value) if isinstance(value, str) else None
    return paths


def load_report(config_root: Path, name: str, path: Path | None, errors: list[str]) -> tuple[dict[str, Any], Path | None]:
    if path is None:
        errors.append(f"{name} report path is required")
        return {}, None
    report_path = report_path_from_string(config_root, str(path))
    if not report_path.is_file():
        errors.append(f"{name} report is missing: {path}")
        return {}, report_path
    return read_json_object(report_path), report_path


def report_errors(name: str, report: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if report.get("kind") != expected["kind"]:
        errors.append(f"{name}.kind must be {expected['kind']}")
    if report.get("phase") != expected["phase"]:
        errors.append(f"{name}.phase must be {expected['phase']}")
    if report.get("status") != "passed":
        errors.append(f"{name}.status must be passed")
    if summary.get("validation_error_count") not in (0, None):
        errors.append(f"{name}.summary.validation_error_count must be zero")
    recorded = set(string_list(summary.get("recorded_evidence")))
    if not expected["evidence"] <= recorded:
        errors.append(f"{name}.summary.recorded_evidence must include " + ", ".join(sorted(expected["evidence"])))
    if "founder_approval" in recorded:
        errors.append(f"{name}.summary.recorded_evidence must not include founder_approval")
    for key in ("promotion_allowed", "stable_corpus_mutation_allowed", "stable_corpus_promotion_allowed"):
        if summary.get(key) is True:
            errors.append(f"{name}.summary.{key} must not be true")
    if summary.get("stable_corpus_mutated") is True:
        errors.append(f"{name}.summary.stable_corpus_mutated must not be true")
    if summary.get("connector_registry_mutated") is True:
        errors.append(f"{name}.summary.connector_registry_mutated must not be true")
    return errors


def candidate_records(intake_policy: dict[str, Any], *, missing_evidence: list[str]) -> list[dict[str, Any]]:
    records = []
    for candidate in object_list(intake_policy.get("candidates")):
        records.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "proposed_entry_id": candidate.get("proposed_entry_id"),
                "source_pack": candidate.get("source_pack"),
                "source_case_count": len(string_list(candidate.get("source_case_ids"))),
                "decision_status": "blocked_pending_founder_approval",
                "missing_evidence": missing_evidence,
                "promotion_allowed": False,
            }
        )
    return records


def run_eig_baseline_candidate_founder_approval_readiness(
    config: EIGBaselineCandidateFounderApprovalReadinessConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy, config_root=config_root)

    candidate_source = policy.get("candidate_source") if isinstance(policy.get("candidate_source"), dict) else {}
    candidate_path = resolve_path(config_root, str(candidate_source.get("path") or ""))
    intake_policy = read_json_object(candidate_path) if candidate_path.is_file() else {}
    candidates = candidate_records(intake_policy, missing_evidence=["founder_approval"])
    if len(candidates) != 2:
        errors.append("candidate source must contain two EIG baseline candidates")
    if sum(item.get("source_case_count", 0) for item in candidates) != 7:
        errors.append("candidate source must contain seven total source cases")

    report_paths = configured_report_paths(policy=policy, config=config)
    loaded_reports: dict[str, dict[str, Any]] = {}
    report_summaries: dict[str, dict[str, Any]] = {}
    recorded_evidence: set[str] = set()
    for name, expected in EXPECTED_REPORTS.items():
        report, resolved = load_report(config_root, name, report_paths.get(name), errors)
        loaded_reports[name] = report
        errors.extend(report_errors(name, report, expected))
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        recorded_evidence.update(string_list(summary.get("recorded_evidence")))
        report_summaries[name] = {
            "path": str(resolved) if resolved else None,
            "sha256": sha256_file(resolved) if resolved and resolved.is_file() else None,
            "kind": report.get("kind"),
            "phase": report.get("phase"),
            "status": report.get("status"),
            "recorded_evidence": string_list(summary.get("recorded_evidence")),
        }

    baseline = policy.get("baseline_corpus") if isinstance(policy.get("baseline_corpus"), dict) else {}
    baseline_path = resolve_path(config_root, str(baseline.get("path") or ""))
    stable_corpus_mutated = baseline_path.is_file() and sha256_file(baseline_path) != baseline.get("sha256")
    if stable_corpus_mutated:
        errors.append("baseline_corpus.sha256 changed before founder approval")

    missing_evidence = sorted(REQUIRED_EVIDENCE - recorded_evidence)
    if set(missing_evidence) != {"founder_approval"}:
        errors.append("remaining missing evidence must be founder_approval only")
    if not ARTIFACT_EVIDENCE <= recorded_evidence:
        errors.append("artifact evidence is incomplete before founder approval")

    status = (
        EIGBaselineCandidateFounderApprovalReadinessStatus.PASSED.value
        if not errors
        else EIGBaselineCandidateFounderApprovalReadinessStatus.FAILED.value
    )
    ready_for_founder_decision = (
        status == EIGBaselineCandidateFounderApprovalReadinessStatus.PASSED.value
        and missing_evidence == ["founder_approval"]
        and not stable_corpus_mutated
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_founder_approval_readiness_report",
        "phase": 317,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "candidate_count": len(candidates),
            "blocked_candidate_count": len(candidates),
            "approved_candidate_count": 0,
            "promoted_candidate_count": 0,
            "recorded_evidence": sorted(recorded_evidence),
            "missing_evidence": missing_evidence,
            "founder_approval_recorded": False,
            "founder_approval_required_for_promotion": True,
            "ready_for_founder_decision": ready_for_founder_decision,
            "promotion_allowed": False,
            "stable_corpus_mutated": stable_corpus_mutated,
            "stable_corpus_promotion_allowed": False,
            "stable_corpus_update_requires_separate_phase": True,
            "validation_error_count": len(errors),
            "phase318_ready": ready_for_founder_decision,
        },
        "candidates": candidates,
        "evidence_reports": report_summaries,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
