"""Promotion rules for stable Priority 0 baseline corpus entries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    MINIMUM_SCORE,
    REQUIRED_COINBASE_TARGETS,
    REQUIRED_ROUTES,
    artifact_hash_errors,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    validate_baseline_corpus,
    write_json,
)
from vllm_agent_gateway.acceptance.founder_test_prompt_pack import validate_pack as validate_founder_prompt_pack


SCHEMA_VERSION = 1
EXPECTED_RULES_KIND = "baseline_corpus_promotion_rules"
EXPECTED_REPORT_KIND = "baseline_corpus_promotion_rules_report"
EXPECTED_PHASE = 142
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_RULES_PATH = Path("runtime") / "baseline_corpus_promotion_rules.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "baseline-corpus-promotion-rules" / "phase142"
REQUIRED_EVIDENCE = {
    "blind_baseline",
    "local_model_comparison",
    "holdout",
    "route_proof",
    "no_mutation_proof",
    "founder_approval",
}
ARTIFACT_EVIDENCE = REQUIRED_EVIDENCE - {"founder_approval"}
ALLOWED_DECISION_STATUSES = {
    "approved_for_promotion",
    "blocked_pending_evidence",
    "promoted",
    "rejected",
}


class BaselineCorpusPromotionRulesStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class BaselineCorpusPromotionRulesConfig:
    config_root: Path
    rules_path: Path = DEFAULT_RULES_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"baseline-corpus-promotion-rules-{utc_timestamp()}.json"


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def selected_prompt_pack_case_ids(pack: dict[str, Any]) -> list[str]:
    case_ids: list[str] = []
    for tier in object_list(pack.get("tiers")):
        case_ids.extend(string_list(tier.get("case_ids")))
    return case_ids


def existing_corpus_entry_ids(corpus: dict[str, Any]) -> set[str]:
    return {str(entry.get("entry_id")) for entry in object_list(corpus.get("entries")) if isinstance(entry.get("entry_id"), str)}


def evidence_by_type(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("evidence_type")): item
        for item in object_list(candidate.get("evidence_refs"))
        if isinstance(item.get("evidence_type"), str)
    }


def validate_source_artifacts(
    rules: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    del require_artifacts
    errors: list[str] = []
    source_corpus = rules.get("source_corpus") if isinstance(rules.get("source_corpus"), dict) else {}
    source_pack = rules.get("source_prompt_pack") if isinstance(rules.get("source_prompt_pack"), dict) else {}
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="source_corpus",
            path_value=source_corpus.get("path"),
            hash_value=source_corpus.get("sha256"),
            required=True,
        )
    )
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="source_prompt_pack",
            path_value=source_pack.get("path"),
            hash_value=source_pack.get("sha256"),
            required=True,
        )
    )
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="source_prompt_pack.catalog",
            path_value=source_pack.get("catalog_path"),
            hash_value=source_pack.get("catalog_sha256"),
            required=True,
        )
    )
    corpus: dict[str, Any] = {}
    prompt_pack: dict[str, Any] = {}
    if not errors:
        corpus = read_json_object(resolve_path(config_root, str(source_corpus["path"])))
        prompt_pack = read_json_object(resolve_path(config_root, str(source_pack["path"])))
        corpus_errors = validate_baseline_corpus(corpus, config_root=config_root, require_artifacts=True)
        errors.extend(f"source_corpus.{error}" for error in corpus_errors)
        if source_corpus.get("expected_entry_count") != len(object_list(corpus.get("entries"))):
            errors.append("source_corpus.expected_entry_count must match source corpus entries")
        if prompt_pack.get("kind") != "founder_test_prompt_pack":
            errors.append("source_prompt_pack.path must reference a founder_test_prompt_pack")
        catalog = read_json_object(resolve_path(config_root, str(source_pack["catalog_path"])))
        prompt_pack_errors = validate_founder_prompt_pack(prompt_pack, catalog=catalog, config_root=config_root)
        errors.extend(f"source_prompt_pack.{error}" for error in prompt_pack_errors)
        expected_case_ids = string_list(source_pack.get("expected_case_ids"))
        actual_case_ids = selected_prompt_pack_case_ids(prompt_pack)
        if expected_case_ids != actual_case_ids:
            errors.append("source_prompt_pack.expected_case_ids must match selected founder prompt-pack case order")
    return errors, corpus, prompt_pack


def validate_policy(rules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if rules.get("schema_version") != SCHEMA_VERSION:
        errors.append("rules.schema_version must be 1")
    if rules.get("kind") != EXPECTED_RULES_KIND:
        errors.append(f"rules.kind must be {EXPECTED_RULES_KIND}")
    if rules.get("phase") != EXPECTED_PHASE:
        errors.append("rules.phase must be 142")
    if rules.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"rules.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    policy = rules.get("promotion_policy") if isinstance(rules.get("promotion_policy"), dict) else {}
    if set(string_list(policy.get("required_evidence"))) != REQUIRED_EVIDENCE:
        errors.append("promotion_policy.required_evidence must contain all required promotion evidence")
    if set(string_list(policy.get("required_routes"))) != REQUIRED_ROUTES:
        errors.append("promotion_policy.required_routes must be gateway and anythingllm")
    if set(string_list(policy.get("required_target_roots"))) != REQUIRED_COINBASE_TARGETS:
        errors.append("promotion_policy.required_target_roots must be both frozen Coinbase fixtures")
    if policy.get("minimum_score") != MINIMUM_SCORE:
        errors.append(f"promotion_policy.minimum_score must be {MINIMUM_SCORE}")
    if policy.get("critical_findings_allowed") != 0 or policy.get("high_findings_allowed") != 0:
        errors.append("promotion_policy critical/high findings allowed must be 0")
    for key in (
        "source_mutation_allowed",
        "stale_source_hashes_allowed",
        "auto_promote_allowed",
    ):
        if policy.get(key) is not False:
            errors.append(f"promotion_policy.{key} must be false")
    if policy.get("stable_corpus_update_requires_separate_phase") is not True:
        errors.append("promotion_policy.stable_corpus_update_requires_separate_phase must be true")
    return errors


def validate_evidence_artifact(
    evidence_type: str,
    evidence: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool,
    prefix: str,
) -> list[str]:
    errors = artifact_hash_errors(
        config_root=config_root,
        prefix=prefix,
        path_value=evidence.get("path"),
        hash_value=evidence.get("sha256"),
        required=require_artifacts,
    )
    path_value = evidence.get("path")
    path = resolve_path(config_root, path_value) if isinstance(path_value, str) else Path()
    artifact = read_json_object(path) if path.is_file() else {}
    case_ids = set(string_list(evidence.get("case_ids")))
    if evidence_type == "local_model_comparison":
        if evidence.get("status") != "passed":
            errors.append(f"{prefix}.status must be passed")
        if not isinstance(evidence.get("minimum_score"), int) or evidence["minimum_score"] < MINIMUM_SCORE:
            errors.append(f"{prefix}.minimum_score must be >= {MINIMUM_SCORE}")
        if evidence.get("critical_finding_count") != 0 or evidence.get("high_finding_count") != 0:
            errors.append(f"{prefix} critical/high finding counts must be 0")
        if artifact:
            if artifact.get("status") != "passed":
                errors.append(f"{prefix} artifact status must be passed")
            artifact_case_ids = {
                str(case.get("case_id"))
                for case in object_list(artifact.get("cases"))
                if isinstance(case.get("case_id"), str)
            }
            if artifact_case_ids != case_ids:
                errors.append(f"{prefix} artifact case IDs must match evidence case_ids")
            for case in object_list(artifact.get("cases")):
                for route in object_list(case.get("routes")):
                    if route.get("pass") is not True:
                        errors.append(f"{prefix} artifact route must pass for {case.get('case_id')}")
                    score = route.get("score")
                    if not isinstance(score, int) or score < MINIMUM_SCORE:
                        errors.append(f"{prefix} artifact route score must be >= {MINIMUM_SCORE} for {case.get('case_id')}")
                    for finding in object_list(route.get("unresolved_findings")):
                        if finding.get("severity") in {"critical", "high"}:
                            errors.append(f"{prefix} artifact must not contain unresolved critical/high findings")
    if evidence_type == "route_proof":
        if set(string_list(evidence.get("routes"))) != REQUIRED_ROUTES:
            errors.append(f"{prefix}.routes must be gateway and anythingllm")
        if set(string_list(evidence.get("target_roots"))) < REQUIRED_COINBASE_TARGETS:
            errors.append(f"{prefix}.target_roots must include both frozen Coinbase fixtures")
        if artifact:
            artifact_case_ids = {
                str(case.get("case_id"))
                for case in object_list(artifact.get("cases"))
                if isinstance(case.get("case_id"), str)
            }
            if artifact_case_ids and artifact_case_ids != case_ids:
                errors.append(f"{prefix} artifact case IDs must match evidence case_ids")
            artifact_roots = {
                str(case.get("target_root"))
                for case in object_list(artifact.get("cases"))
                if isinstance(case.get("target_root"), str)
            }
            if artifact_roots and artifact_roots < REQUIRED_COINBASE_TARGETS:
                errors.append(f"{prefix} artifact target roots must include both frozen Coinbase fixtures")
    if evidence_type == "holdout":
        if evidence.get("status") != "passed":
            errors.append(f"{prefix}.status must be passed")
        if not isinstance(evidence.get("holdout_case_count"), int) or evidence["holdout_case_count"] < 1:
            errors.append(f"{prefix}.holdout_case_count must be at least 1")
        if artifact:
            holdout_ids = set(string_list(evidence.get("holdout_case_ids")))
            if not holdout_ids:
                errors.append(f"{prefix}.holdout_case_ids is required")
            artifact_holdouts: set[str] = set()
            for entry in object_list(artifact.get("entries")):
                artifact_holdouts.update(string_list(entry.get("holdout_case_ids")))
            for case in object_list(artifact.get("cases")):
                if case.get("holdout") is True and isinstance(case.get("case_id"), str):
                    artifact_holdouts.add(str(case.get("case_id")))
            if holdout_ids and not holdout_ids <= artifact_holdouts:
                errors.append(f"{prefix} artifact must contain holdout_case_ids")
    if evidence_type == "no_mutation_proof":
        if evidence.get("runtime_changed_files") != []:
            errors.append(f"{prefix}.runtime_changed_files must be []")
        if evidence.get("target_changed_files") != {}:
            errors.append(f"{prefix}.target_changed_files must be {{}}")
        if evidence.get("target_git_changed") not in ({}, None):
            errors.append(f"{prefix}.target_git_changed must be empty when present")
        if artifact:
            if artifact.get("runtime_changed_files") not in ([], None):
                errors.append(f"{prefix} artifact runtime_changed_files must be []")
            if artifact.get("target_changed_files") not in ({}, None):
                errors.append(f"{prefix} artifact target_changed_files must be {{}}")
            if artifact.get("target_git_changed") not in ({}, None):
                errors.append(f"{prefix} artifact target_git_changed must be empty when present")
            before = artifact.get("fixture_state_before")
            after = artifact.get("fixture_state_after")
            if before is not None or after is not None:
                if before != after:
                    errors.append(f"{prefix} artifact fixture state must be unchanged")
    if evidence_type == "blind_baseline" and artifact:
        if "blind_baselines" not in str(artifact.get("kind") or ""):
            errors.append(f"{prefix} artifact kind must be a blind baselines artifact")
        policy = artifact.get("baseline_policy") if isinstance(artifact.get("baseline_policy"), dict) else {}
        if policy.get("blind_agent_context") != "contextless":
            errors.append(f"{prefix} artifact baseline_policy.blind_agent_context must be contextless")
        if policy.get("local_model_output_seen") is not False:
            errors.append(f"{prefix} artifact must record local_model_output_seen=false")
        artifact_case_ids = {
            str(item.get("case_id"))
            for item in object_list(artifact.get("baselines"))
            if isinstance(item.get("case_id"), str)
        }
        if artifact_case_ids != case_ids:
            errors.append(f"{prefix} artifact case IDs must match evidence case_ids")
    return errors


def validate_candidate(
    candidate: dict[str, Any],
    *,
    config_root: Path,
    corpus: dict[str, Any],
    prompt_pack: dict[str, Any],
    require_artifacts: bool,
) -> list[str]:
    candidate_id = str(candidate.get("candidate_id") or "<missing>")
    prefix = f"candidates[{candidate_id}]"
    errors: list[str] = []
    if not isinstance(candidate.get("candidate_id"), str) or not candidate["candidate_id"].strip():
        errors.append(f"{prefix}.candidate_id is required")
    proposed_entry_id = candidate.get("proposed_entry_id")
    if not isinstance(proposed_entry_id, str) or not proposed_entry_id.strip():
        errors.append(f"{prefix}.proposed_entry_id is required")
    decision_status = candidate.get("decision_status")
    if decision_status not in ALLOWED_DECISION_STATUSES:
        errors.append(f"{prefix}.decision_status must be supported")
    if candidate.get("source") != "founder_test_prompt_pack":
        errors.append(f"{prefix}.source must be founder_test_prompt_pack")
    source_case_ids = string_list(candidate.get("source_case_ids"))
    if source_case_ids != selected_prompt_pack_case_ids(prompt_pack):
        errors.append(f"{prefix}.source_case_ids must match the selected founder prompt-pack cases")
    existing_entries = existing_corpus_entry_ids(corpus)
    if decision_status in {"approved_for_promotion", "blocked_pending_evidence", "rejected"} and proposed_entry_id in existing_entries:
        errors.append(f"{prefix}.proposed_entry_id already exists in stable corpus")
    if decision_status == "promoted" and proposed_entry_id not in existing_entries:
        errors.append(f"{prefix}.promoted candidate must exist in stable corpus")
    policy_requires_separate_phase = True

    missing_evidence = string_list(candidate.get("missing_evidence"))
    unknown_missing = sorted(set(missing_evidence) - REQUIRED_EVIDENCE)
    if unknown_missing:
        errors.append(f"{prefix}.missing_evidence contains unknown evidence: " + ", ".join(unknown_missing))
    approval = candidate.get("founder_approval") if isinstance(candidate.get("founder_approval"), dict) else {}
    evidence = evidence_by_type(candidate)
    duplicate_evidence = duplicate_values(
        [
            str(item.get("evidence_type"))
            for item in object_list(candidate.get("evidence_refs"))
            if isinstance(item.get("evidence_type"), str)
        ]
    )
    if duplicate_evidence:
        errors.append(f"{prefix}.evidence_refs contains duplicate evidence_type values: " + ", ".join(duplicate_evidence))
    unknown_evidence = sorted(set(evidence) - REQUIRED_EVIDENCE)
    if unknown_evidence:
        errors.append(f"{prefix}.evidence_refs contains unknown evidence: " + ", ".join(unknown_evidence))

    if decision_status in {"approved_for_promotion", "promoted"}:
        if decision_status == "promoted" and policy_requires_separate_phase:
            errors.append(f"{prefix}.decision_status cannot be promoted while stable corpus update requires a separate phase")
        if missing_evidence:
            errors.append(f"{prefix}.missing_evidence must be empty for approved/promoted candidates")
        if approval.get("status") != "approved":
            errors.append(f"{prefix}.founder_approval.status must be approved")
        if not isinstance(approval.get("approved_by"), str) or not approval["approved_by"].strip():
            errors.append(f"{prefix}.founder_approval.approved_by is required")
        if not isinstance(approval.get("approved_at"), str) or not approval["approved_at"].strip():
            errors.append(f"{prefix}.founder_approval.approved_at is required")
        missing_artifacts = sorted(ARTIFACT_EVIDENCE - set(evidence))
        if missing_artifacts:
            errors.append(f"{prefix}.evidence_refs missing artifact evidence: " + ", ".join(missing_artifacts))
        for evidence_type in sorted(ARTIFACT_EVIDENCE & set(evidence)):
            if string_list(evidence[evidence_type].get("case_ids")) != source_case_ids:
                errors.append(f"{prefix}.evidence_refs[{evidence_type}].case_ids must match candidate source_case_ids")
            errors.extend(
                validate_evidence_artifact(
                    evidence_type,
                    evidence[evidence_type],
                    config_root=config_root,
                    require_artifacts=True,
                    prefix=f"{prefix}.evidence_refs[{evidence_type}]",
                )
            )
    elif decision_status == "blocked_pending_evidence":
        if not missing_evidence:
            errors.append(f"{prefix}.missing_evidence must explain why promotion is blocked")
        if approval.get("status") == "approved":
            errors.append(f"{prefix}.founder_approval cannot be approved while candidate is blocked")
        if not isinstance(candidate.get("promotion_blocker"), str) or len(candidate["promotion_blocker"].strip()) < 40:
            errors.append(f"{prefix}.promotion_blocker must explain the blocker")
        for evidence_type, value in sorted(evidence.items()):
            errors.extend(
                validate_evidence_artifact(
                    evidence_type,
                    value,
                    config_root=config_root,
                    require_artifacts=require_artifacts,
                    prefix=f"{prefix}.evidence_refs[{evidence_type}]",
                )
            )
    elif decision_status == "rejected":
        if not isinstance(candidate.get("rejection_reason"), str) or len(candidate["rejection_reason"].strip()) < 20:
            errors.append(f"{prefix}.rejection_reason is required")
    return errors


def validate_promotion_rules(
    rules: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool = False,
) -> list[str]:
    errors = validate_policy(rules)
    source_errors, corpus, prompt_pack = validate_source_artifacts(
        rules,
        config_root=config_root,
        require_artifacts=require_artifacts,
    )
    errors.extend(source_errors)
    candidates = object_list(rules.get("candidates"))
    if not candidates:
        errors.append("candidates must contain at least one governed promotion candidate")
        return errors
    candidate_ids = [str(item.get("candidate_id")) for item in candidates if isinstance(item.get("candidate_id"), str)]
    if duplicate_values(candidate_ids):
        errors.append("candidates contain duplicate candidate_id values")
    proposed_ids = [str(item.get("proposed_entry_id")) for item in candidates if isinstance(item.get("proposed_entry_id"), str)]
    if duplicate_values(proposed_ids):
        errors.append("candidates contain duplicate proposed_entry_id values")
    if not source_errors:
        for candidate in candidates:
            errors.extend(
                validate_candidate(
                    candidate,
                    config_root=config_root,
                    corpus=corpus,
                    prompt_pack=prompt_pack,
                    require_artifacts=require_artifacts,
                )
            )
    return errors


def build_promotion_rules_report(
    *,
    rules: dict[str, Any],
    config_root: Path,
    rules_path: Path | None = None,
    require_artifacts: bool = False,
) -> dict[str, Any]:
    errors = validate_promotion_rules(rules, config_root=config_root, require_artifacts=require_artifacts)
    candidates = object_list(rules.get("candidates"))
    status_counts: dict[str, int] = {status: 0 for status in sorted(ALLOWED_DECISION_STATUSES)}
    for candidate in candidates:
        status = str(candidate.get("decision_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    source_corpus = rules.get("source_corpus") if isinstance(rules.get("source_corpus"), dict) else {}
    source_pack = rules.get("source_prompt_pack") if isinstance(rules.get("source_prompt_pack"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": BaselineCorpusPromotionRulesStatus.PASSED.value if not errors else BaselineCorpusPromotionRulesStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "rules_path": str(rules_path or DEFAULT_RULES_PATH),
        "rules_sha256": artifact_hash(rules_path) if rules_path else None,
        "source_corpus_path": source_corpus.get("path"),
        "source_corpus_sha256": source_corpus.get("sha256"),
        "source_prompt_pack_path": source_pack.get("path"),
        "source_prompt_pack_sha256": source_pack.get("sha256"),
        "required_evidence": sorted(REQUIRED_EVIDENCE),
        "candidates": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "proposed_entry_id": candidate.get("proposed_entry_id"),
                "decision_status": candidate.get("decision_status"),
                "missing_evidence": string_list(candidate.get("missing_evidence")),
                "source_case_count": len(string_list(candidate.get("source_case_ids"))),
            }
            for candidate in candidates
        ],
        "summary": {
            "candidate_count": len(candidates),
            "approved_candidate_count": status_counts.get("approved_for_promotion", 0),
            "blocked_candidate_count": status_counts.get("blocked_pending_evidence", 0),
            "promoted_candidate_count": status_counts.get("promoted", 0),
            "rejected_candidate_count": status_counts.get("rejected", 0),
            "error_count": len(errors),
        },
        "errors": errors,
    }


def validate_promotion_rules_report(
    report: dict[str, Any],
    *,
    rules: dict[str, Any],
    config_root: Path,
    rules_path: Path | None = None,
    require_artifacts: bool = False,
) -> list[str]:
    expected = build_promotion_rules_report(
        rules=rules,
        config_root=config_root,
        rules_path=rules_path,
        require_artifacts=require_artifacts,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "rules_path",
        "rules_sha256",
        "source_corpus_path",
        "source_corpus_sha256",
        "source_prompt_pack_path",
        "source_prompt_pack_sha256",
        "required_evidence",
        "candidates",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt baseline corpus promotion rules report")
    return errors


def run_promotion_rules_gate(config: BaselineCorpusPromotionRulesConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    rules_path = resolve_path(config_root, config.rules_path)
    rules = read_json_object(rules_path) if rules_path.is_file() else {}
    missing_errors = []
    if config.require_artifacts and not rules_path.is_file():
        missing_errors.append(f"required rules artifact is missing: {rules_path}")
    report = build_promotion_rules_report(
        rules=rules,
        config_root=config_root,
        rules_path=rules_path,
        require_artifacts=config.require_artifacts,
    )
    validation_errors = validate_promotion_rules_report(
        report,
        rules=rules,
        config_root=config_root,
        rules_path=rules_path,
        require_artifacts=config.require_artifacts,
    )
    if missing_errors or validation_errors:
        report["status"] = BaselineCorpusPromotionRulesStatus.FAILED.value
        report["errors"] = missing_errors + validation_errors
        report["summary"]["error_count"] = len(report["errors"])
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
