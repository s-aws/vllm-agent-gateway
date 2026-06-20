"""EIG baseline-candidate blind-baseline evidence validation."""

from __future__ import annotations

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
from vllm_agent_gateway.acceptance.baseline_corpus_promotion_rules import REQUIRED_EVIDENCE


SCHEMA_VERSION = 1
DEFAULT_BASELINE_PATH = Path("runtime") / "eig_baseline_candidate_blind_baselines.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-blind-baselines"
REQUIRED_CASE_IDS = [
    "EIG-RUNTIME-WORK-LOOKUP",
    "EIG-RUNTIME-RECORD-LOOKUP",
    "EIG-RUNTIME-KNOWLEDGE-SEARCH",
    "EIG3-RUNTIME-SEC-REFUSE",
    "EIG3-RUNTIME-PII-AUTH",
    "EIG3-RUNTIME-BIZ-JSON",
    "EIG3-RUNTIME-MEMORY",
]
RECORDED_EVIDENCE = {"blind_baseline"}


class EIGBaselineCandidateBlindBaselineStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidateBlindBaselineConfig:
    config_root: Path
    baseline_path: Path = DEFAULT_BASELINE_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-blind-baselines-{utc_timestamp()}.json"


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


def source_case_ids(config_root: Path, path_value: str) -> list[str]:
    pack = read_json_object(resolve_path(config_root, path_value))
    return [str(item.get("id")) for item in object_list(pack.get("cases")) if isinstance(item.get("id"), str)]


def validate_baselines(baselines: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if baselines.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"baselines.schema_version must be {SCHEMA_VERSION}")
    if baselines.get("kind") != "eig_baseline_candidate_blind_baselines":
        errors.append("baselines.kind must be eig_baseline_candidate_blind_baselines")
    if baselines.get("phase") != 312:
        errors.append("baselines.phase must be 312")
    policy = baselines.get("baseline_policy") if isinstance(baselines.get("baseline_policy"), dict) else {}
    if policy.get("source") != "contextless_blind_agent":
        errors.append("baseline_policy.source must be contextless_blind_agent")
    if policy.get("blind_agent_context") != "contextless":
        errors.append("baseline_policy.blind_agent_context must be contextless")
    if policy.get("collection_order") != "blind_baseline_before_local_model_output":
        errors.append("baseline_policy.collection_order must be blind_baseline_before_local_model_output")
    if policy.get("local_model_output_seen") is not False:
        errors.append("baseline_policy.local_model_output_seen must be false")
    if policy.get("promotion_evidence_type") != "blind_baseline":
        errors.append("baseline_policy.promotion_evidence_type must be blind_baseline")

    source_packs = baselines.get("source_packs") if isinstance(baselines.get("source_packs"), dict) else {}
    collected_source_ids: list[str] = []
    for key in ("eig_runtime_breadth_chat_cases", "eig3_privacy_runtime_chat_cases"):
        source = source_packs.get(key) if isinstance(source_packs.get(key), dict) else {}
        prefix = f"source_packs.{key}"
        errors.extend(
            artifact_hash_errors(
                config_root=config_root,
                prefix=prefix,
                path_value=source.get("path"),
                hash_value=source.get("sha256"),
            )
        )
        if isinstance(source.get("path"), str):
            collected_source_ids.extend(source_case_ids(config_root, source["path"]))
    if collected_source_ids != REQUIRED_CASE_IDS:
        errors.append("source_packs case IDs must match the Phase 312 EIG case order")

    baseline_items = object_list(baselines.get("baselines"))
    case_ids = [str(item.get("case_id")) for item in baseline_items if isinstance(item.get("case_id"), str)]
    if case_ids != REQUIRED_CASE_IDS:
        errors.append("baselines case IDs must match the Phase 312 EIG case order")
    if len(set(case_ids)) != len(case_ids):
        errors.append("baselines case IDs must be unique")
    for index, item in enumerate(baseline_items):
        prefix = f"baselines[{index}]"
        if not isinstance(item.get("ideal_answer_shape"), str) or not item["ideal_answer_shape"].strip():
            errors.append(f"{prefix}.ideal_answer_shape is required")
        for field in ("must_include", "must_not_include", "hard_failures"):
            if not string_list(item.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string array")
        if not isinstance(item.get("evidence_expectations"), str) or not item["evidence_expectations"].strip():
            errors.append(f"{prefix}.evidence_expectations is required")
        if not isinstance(item.get("scoring_notes"), str) or not item["scoring_notes"].strip():
            errors.append(f"{prefix}.scoring_notes is required")

    group = baselines.get("group_promotion_readiness_notes") if isinstance(baselines.get("group_promotion_readiness_notes"), dict) else {}
    for field in ("baseline_strengths", "promotion_requirements", "hard_group_failures"):
        if not string_list(group.get(field)):
            errors.append(f"group_promotion_readiness_notes.{field} must be a non-empty string array")
    if not isinstance(group.get("scoring_guidance"), str) or not group["scoring_guidance"].strip():
        errors.append("group_promotion_readiness_notes.scoring_guidance is required")
    return errors


def run_eig_baseline_candidate_blind_baselines(
    config: EIGBaselineCandidateBlindBaselineConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path = resolve_path(config_root, config.baseline_path)
    baselines = read_json_object(baseline_path)
    errors = validate_baselines(baselines, config_root=config_root)
    status = EIGBaselineCandidateBlindBaselineStatus.PASSED.value if not errors else EIGBaselineCandidateBlindBaselineStatus.FAILED.value
    remaining_missing = sorted(REQUIRED_EVIDENCE - RECORDED_EVIDENCE)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_blind_baselines_report",
        "phase": 312,
        "status": status,
        "baseline_path": str(baseline_path),
        "baseline_sha256": sha256_file(baseline_path) if baseline_path.is_file() else None,
        "summary": {
            "status": status,
            "case_count": len(object_list(baselines.get("baselines"))),
            "expected_case_count": len(REQUIRED_CASE_IDS),
            "contextless_agent_first": (baselines.get("baseline_policy") or {}).get("blind_agent_context") == "contextless",
            "local_model_output_seen": (baselines.get("baseline_policy") or {}).get("local_model_output_seen"),
            "recorded_evidence": sorted(RECORDED_EVIDENCE),
            "remaining_missing_evidence": remaining_missing,
            "promotion_allowed": False,
            "stable_corpus_mutation_allowed": False,
            "validation_error_count": len(errors),
            "phase313_ready": status == EIGBaselineCandidateBlindBaselineStatus.PASSED.value,
        },
        "case_ids": [
            str(item.get("case_id"))
            for item in object_list(baselines.get("baselines"))
            if isinstance(item.get("case_id"), str)
        ],
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
