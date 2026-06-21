"""EIG baseline-candidate intake gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_baseline_candidate_intake_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-intake"
REQUIRED_MILESTONES = {"M2", "M9", "M14", "M19", "M25", "M31", "M36"}
REQUIRED_MISSING_EVIDENCE = {
    "blind_baseline",
    "local_model_comparison",
    "holdout",
    "route_proof",
    "no_mutation_proof",
    "founder_approval",
}
ALLOWED_DECISION_STATUSES = {"candidate_pending_live_replay"}


class EIGBaselineCandidateIntakeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidateIntakeConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-intake-{utc_timestamp()}.json"


def artifact_hash_errors(
    *,
    config_root: Path,
    prefix: str,
    path_value: object,
    hash_value: object,
) -> list[str]:
    if not isinstance(path_value, str) or not path_value.strip():
        return [f"{prefix}.path is required"]
    if not isinstance(hash_value, str) or len(hash_value) != 64:
        return [f"{prefix}.sha256 must be a 64-character hash"]
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        return [f"{prefix}.path does not exist: {path_value}"]
    actual = sha256_file(path)
    if actual != hash_value:
        return [f"{prefix}.sha256 is stale for {path_value}"]
    return []


def case_id_list(pack: dict[str, Any]) -> list[str]:
    return [str(item.get("id")) for item in object_list(pack.get("cases")) if isinstance(item.get("id"), str)]


def existing_entry_ids(corpus: dict[str, Any]) -> set[str]:
    return {str(item.get("entry_id")) for item in object_list(corpus.get("entries")) if isinstance(item.get("entry_id"), str)}


def validate_source_corpus(policy: dict[str, Any], *, config_root: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    source = policy.get("source_corpus") if isinstance(policy.get("source_corpus"), dict) else {}
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="source_corpus",
            path_value=source.get("path"),
            hash_value=source.get("sha256"),
        )
    )
    corpus: dict[str, Any] = {}
    if not errors:
        corpus = read_json_object(resolve_path(config_root, str(source["path"])))
        if source.get("expected_entry_count") != len(object_list(corpus.get("entries"))):
            errors.append("source_corpus.expected_entry_count must match source corpus entries")
    return errors, corpus


def validate_source_packs(policy: dict[str, Any], *, config_root: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    pack_records: dict[str, dict[str, Any]] = {}
    source_packs = policy.get("source_packs") if isinstance(policy.get("source_packs"), dict) else {}
    if set(source_packs) != {"eig_runtime_breadth_chat_cases", "eig3_privacy_runtime_chat_cases"}:
        errors.append("source_packs must contain eig_runtime_breadth_chat_cases and eig3_privacy_runtime_chat_cases")
        return errors, pack_records
    for pack_id, source in sorted(source_packs.items()):
        if not isinstance(source, dict):
            errors.append(f"source_packs.{pack_id} must be an object")
            continue
        prefix = f"source_packs.{pack_id}"
        errors.extend(
            artifact_hash_errors(
                config_root=config_root,
                prefix=prefix,
                path_value=source.get("path"),
                hash_value=source.get("sha256"),
            )
        )
        path_value = source.get("path")
        pack = read_json_object(resolve_path(config_root, str(path_value))) if isinstance(path_value, str) else {}
        if pack:
            if pack.get("kind") != source.get("kind"):
                errors.append(f"{prefix}.kind must match source pack kind")
            ids = case_id_list(pack)
            if source.get("expected_case_count") != len(ids):
                errors.append(f"{prefix}.expected_case_count must match source pack case count")
            if source.get("synthetic_only_required") is True and pack.get("synthetic_only") is not True:
                errors.append(f"{prefix}.synthetic_only must be true")
            boundary = pack.get("scope_boundary") if isinstance(pack.get("scope_boundary"), dict) else {}
            if pack_id == "eig_runtime_breadth_chat_cases":
                for key in (
                    "direct_model_tool_access_allowed",
                    "raw_mcp_allowed",
                    "external_network_allowed",
                    "runtime_registry_mutation_allowed",
                    "target_repository_mutation_allowed",
                ):
                    if boundary.get(key) is not False:
                        errors.append(f"{prefix}.scope_boundary.{key} must be false")
            pack_records[pack_id] = {
                "path": path_value,
                "sha256": source.get("sha256"),
                "case_ids": ids,
                "case_count": len(ids),
            }
    return errors, pack_records


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_baseline_candidate_intake_policy":
        errors.append("policy.kind must be eig_baseline_candidate_intake_policy")
    if policy.get("phase") != 307:
        errors.append("policy.phase must be 307")
    if set(string_list(policy.get("required_milestones"))) != REQUIRED_MILESTONES:
        errors.append("policy.required_milestones must match Phase 307 milestones")
    candidate_policy = policy.get("candidate_policy") if isinstance(policy.get("candidate_policy"), dict) else {}
    if set(string_list(candidate_policy.get("missing_evidence_required"))) != REQUIRED_MISSING_EVIDENCE:
        errors.append("candidate_policy.missing_evidence_required must contain all required evidence")
    if candidate_policy.get("stable_corpus_mutation_allowed") is not False:
        errors.append("candidate_policy.stable_corpus_mutation_allowed must be false")
    if candidate_policy.get("auto_promote_allowed") is not False:
        errors.append("candidate_policy.auto_promote_allowed must be false")
    if candidate_policy.get("stable_corpus_update_requires_separate_phase") is not True:
        errors.append("candidate_policy.stable_corpus_update_requires_separate_phase must be true")

    corpus_errors, corpus = validate_source_corpus(policy, config_root=config_root)
    errors.extend(corpus_errors)
    pack_errors, pack_records = validate_source_packs(policy, config_root=config_root)
    errors.extend(pack_errors)

    corpus_entry_ids = existing_entry_ids(corpus)
    candidate_records: list[dict[str, Any]] = []
    for index, candidate in enumerate(object_list(policy.get("candidates"))):
        prefix = f"candidates[{index}]"
        candidate_id = candidate.get("candidate_id")
        proposed_entry_id = candidate.get("proposed_entry_id")
        source_pack = candidate.get("source_pack")
        source_case_ids = string_list(candidate.get("source_case_ids"))
        missing_evidence = set(string_list(candidate.get("missing_evidence")))
        if not isinstance(candidate_id, str) or not candidate_id:
            errors.append(f"{prefix}.candidate_id is required")
        if not isinstance(proposed_entry_id, str) or not proposed_entry_id:
            errors.append(f"{prefix}.proposed_entry_id is required")
        elif proposed_entry_id in corpus_entry_ids:
            errors.append(f"{prefix}.proposed_entry_id must not already exist in stable corpus")
        if candidate.get("decision_status") not in ALLOWED_DECISION_STATUSES:
            errors.append(f"{prefix}.decision_status must be candidate_pending_live_replay")
        if candidate.get("evidence_refs") != []:
            errors.append(f"{prefix}.evidence_refs must be empty before Phase 308 live replay")
        if missing_evidence != REQUIRED_MISSING_EVIDENCE:
            errors.append(f"{prefix}.missing_evidence must contain all required missing evidence")
        if not isinstance(candidate.get("promotion_blocker"), str) or not candidate["promotion_blocker"]:
            errors.append(f"{prefix}.promotion_blocker is required")
        pack_record = pack_records.get(str(source_pack))
        if pack_record is None:
            errors.append(f"{prefix}.source_pack must reference a known EIG runtime pack")
        elif source_case_ids != pack_record["case_ids"]:
            errors.append(f"{prefix}.source_case_ids must match source pack case order")
        candidate_records.append(
            {
                "candidate_id": candidate_id,
                "proposed_entry_id": proposed_entry_id,
                "source_pack": source_pack,
                "source_case_ids": source_case_ids,
                "source_case_count": len(source_case_ids),
                "decision_status": candidate.get("decision_status"),
            }
        )
    if len(candidate_records) != 2:
        errors.append("candidates must contain exactly two EIG baseline candidates")
    if len({item["candidate_id"] for item in candidate_records}) != len(candidate_records):
        errors.append("candidate_id values must be unique")
    if len({item["proposed_entry_id"] for item in candidate_records}) != len(candidate_records):
        errors.append("proposed_entry_id values must be unique")

    evidence = {
        "source_corpus": {
            "path": (policy.get("source_corpus") or {}).get("path")
            if isinstance(policy.get("source_corpus"), dict)
            else None,
            "stable_entry_count": len(corpus_entry_ids),
        },
        "source_packs": pack_records,
        "candidates": candidate_records,
    }
    return errors, evidence


def run_eig_baseline_candidate_intake(config: EIGBaselineCandidateIntakeConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors, evidence = validate_policy(policy, config_root=config_root)
    status = EIGBaselineCandidateIntakeStatus.PASSED.value if not errors else EIGBaselineCandidateIntakeStatus.FAILED.value
    candidates = evidence.get("candidates", [])
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_intake_report",
        "phase": 307,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "candidate_count": len(candidates),
            "total_source_case_count": sum(
                item.get("source_case_count", 0) for item in candidates if isinstance(item, dict)
            ),
            "stable_corpus_entry_count": evidence.get("source_corpus", {}).get("stable_entry_count", 0),
            "stable_corpus_mutated": False,
            "candidate_pending_live_replay_count": sum(
                1
                for item in candidates
                if isinstance(item, dict) and item.get("decision_status") == "candidate_pending_live_replay"
            ),
            "validation_error_count": len(errors),
            "phase308_ready": status == EIGBaselineCandidateIntakeStatus.PASSED.value,
        },
        "evidence": evidence,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
