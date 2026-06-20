"""Validate EIG candidate route and no-mutation proof."""

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
from vllm_agent_gateway.acceptance.eig_baseline_candidate_local_comparison import report_path_from_string


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_baseline_candidate_route_mutation_proof_policy.json"
DEFAULT_LIVE_REPLAY_REPORT_PATH = (
    Path("runtime-state")
    / "eig-baseline-candidate-live-replay"
    / "phase314-after-pii-repair-live.json"
)
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-route-mutation-proof"
REQUIRED_SURFACES = {"workflow_router_gateway", "anythingllm"}


class EIGBaselineCandidateRouteMutationProofStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidateRouteMutationProofConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    live_replay_report_path: Path = DEFAULT_LIVE_REPLAY_REPORT_PATH
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-route-mutation-proof-{utc_timestamp()}.json"


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_baseline_candidate_route_mutation_proof_policy":
        errors.append("policy.kind must be eig_baseline_candidate_route_mutation_proof_policy")
    if policy.get("phase") != 315:
        errors.append("policy.phase must be 315")
    replay = policy.get("required_live_replay") if isinstance(policy.get("required_live_replay"), dict) else {}
    if replay.get("candidate_count") != 2:
        errors.append("required_live_replay.candidate_count must be 2")
    if replay.get("live_result_count") != 14:
        errors.append("required_live_replay.live_result_count must be 14")
    if set(string_list(replay.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append("required_live_replay.required_surfaces must be workflow_router_gateway and anythingllm")
    if set(string_list(policy.get("recorded_evidence"))) != {"route_proof", "no_mutation_proof"}:
        errors.append("policy.recorded_evidence must include route_proof and no_mutation_proof")
    for key in ("stable_corpus_mutation_allowed", "stable_corpus_promotion_allowed"):
        if policy.get(key) is not False:
            errors.append(f"policy.{key} must be false")
    return errors


def load_child_report(config_root: Path, compact: dict[str, Any]) -> dict[str, Any]:
    path = compact.get("report_path")
    if not isinstance(path, str):
        return {}
    report_path = report_path_from_string(config_root, path)
    if not report_path.is_file():
        return {}
    return read_json_object(report_path)


def connector_route_errors(report: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if report.get("status") != "passed":
        errors.append(f"{label}.status must be passed")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("source_connector_registry_changed") is not False:
        errors.append(f"{label}.source_connector_registry_changed must be false")
    if summary.get("case_count") != 3 or summary.get("passed_case_count") != 3:
        errors.append(f"{label} must contain three passing connector cases")
    for result in object_list(report.get("case_results")):
        case_id = str(result.get("case_id") or "unknown")
        if result.get("status") != "passed":
            errors.append(f"{label}.{case_id}.status must be passed")
        if result.get("workflow") != "connector.invoke":
            errors.append(f"{label}.{case_id}.workflow must be connector.invoke")
        if result.get("errors"):
            errors.append(f"{label}.{case_id}.errors must be empty")
        if not isinstance(result.get("run_id"), str) or not str(result.get("run_id")).strip():
            errors.append(f"{label}.{case_id}.run_id is required")
    return errors


def privacy_route_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("status") != "passed":
        errors.append("privacy_runtime.status must be passed")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("result_count") != 8:
        errors.append("privacy_runtime.result_count must be 8")
    if summary.get("surface_count") != 2:
        errors.append("privacy_runtime.surface_count must be 2")
    if set(string_list(summary.get("surfaces"))) != REQUIRED_SURFACES:
        errors.append("privacy_runtime.surfaces must include both required surfaces")
    if summary.get("raw_source_content_retained_in_report") is not False:
        errors.append("privacy_runtime.raw_source_content_retained_in_report must be false")
    for result in object_list(report.get("case_results")):
        case_id = str(result.get("case_id") or "unknown")
        surface = str(result.get("surface") or "unknown")
        prefix = f"privacy_runtime.{surface}.{case_id}"
        if result.get("status") != "passed":
            errors.append(f"{prefix}.status must be passed")
        if result.get("selected_workflow") != "none":
            errors.append(f"{prefix}.selected_workflow must be none")
        if result.get("route_status") != "eig3_privacy_policy_no_target":
            errors.append(f"{prefix}.route_status must be eig3_privacy_policy_no_target")
        if result.get("finding_count") not in {0, None}:
            errors.append(f"{prefix}.finding_count must be zero")
        if result.get("findings"):
            errors.append(f"{prefix}.findings must be empty")
    return errors


def run_eig_baseline_candidate_route_mutation_proof(
    config: EIGBaselineCandidateRouteMutationProofConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    live_path = resolve_path(config_root, config.live_replay_report_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    if not live_path.is_file():
        errors.append(f"live replay report is missing: {config.live_replay_report_path}")
        live_report: dict[str, Any] = {}
    else:
        live_report = read_json_object(live_path)
    summary = live_report.get("summary") if isinstance(live_report.get("summary"), dict) else {}
    if live_report.get("status") != "passed":
        errors.append("live replay report must pass")
    if summary.get("candidate_count") != 2:
        errors.append("live replay candidate_count must be 2")
    if summary.get("live_result_count") != 14:
        errors.append("live replay live_result_count must be 14")
    if summary.get("covered_surface_count") != 2 or summary.get("missing_surface_count") != 0:
        errors.append("live replay must cover both required surfaces")
    if summary.get("stable_corpus_mutated") is not False:
        errors.append("live replay stable_corpus_mutated must be false")
    if summary.get("stable_corpus_promotion_allowed") is not False:
        errors.append("live replay stable_corpus_promotion_allowed must be false")
    if live_report.get("baseline_corpus", {}).get("status") != "passed":
        errors.append("baseline corpus governance must pass")

    children = live_report.get("child_reports") if isinstance(live_report.get("child_reports"), dict) else {}
    connector_gateway = load_child_report(config_root, children.get("connector_gateway") if isinstance(children.get("connector_gateway"), dict) else {})
    connector_anythingllm = load_child_report(config_root, children.get("connector_anythingllm") if isinstance(children.get("connector_anythingllm"), dict) else {})
    privacy = load_child_report(config_root, children.get("privacy_runtime") if isinstance(children.get("privacy_runtime"), dict) else {})
    errors.extend(connector_route_errors(connector_gateway, "connector_gateway"))
    errors.extend(connector_route_errors(connector_anythingllm, "connector_anythingllm"))
    errors.extend(privacy_route_errors(privacy))

    status = (
        EIGBaselineCandidateRouteMutationProofStatus.PASSED.value
        if not errors
        else EIGBaselineCandidateRouteMutationProofStatus.FAILED.value
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_route_mutation_proof_report",
        "phase": 315,
        "status": status,
        "policy_path": str(policy_path),
        "live_replay_report_path": str(live_path),
        "live_replay_report_sha256": sha256_file(live_path) if live_path.is_file() else None,
        "summary": {
            "status": status,
            "route_proof_recorded": status == EIGBaselineCandidateRouteMutationProofStatus.PASSED.value,
            "no_mutation_proof_recorded": status == EIGBaselineCandidateRouteMutationProofStatus.PASSED.value,
            "recorded_evidence": ["route_proof", "no_mutation_proof"] if not errors else [],
            "remaining_missing_evidence": ["founder_approval", "holdout"],
            "connector_result_count": len(object_list(connector_gateway.get("case_results")))
            + len(object_list(connector_anythingllm.get("case_results"))),
            "privacy_result_count": len(object_list(privacy.get("case_results"))),
            "stable_corpus_mutated": summary.get("stable_corpus_mutated"),
            "stable_corpus_promotion_allowed": summary.get("stable_corpus_promotion_allowed"),
            "validation_error_count": len(errors),
            "phase316_ready": status == EIGBaselineCandidateRouteMutationProofStatus.PASSED.value,
        },
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
