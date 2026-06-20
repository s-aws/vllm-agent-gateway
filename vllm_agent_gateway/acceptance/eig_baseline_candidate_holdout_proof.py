"""Run EIG baseline-candidate holdout proof."""

from __future__ import annotations

import os
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
from vllm_agent_gateway.acceptance.eig3_privacy_evalops import fixture_lookup, memory_lookup
from vllm_agent_gateway.acceptance.eig3_privacy_runtime_chat import (
    EIG3PrivacyRuntimeChatConfig,
    anythingllm_case,
    classify_case_response,
    gateway_case,
)
from vllm_agent_gateway.acceptance.eig_runtime_breadth_chat import (
    EIGRuntimeBreadthChatConfig,
    anythingllm_chat_response,
    case_errors,
    direct_chat_response,
    file_sha256,
    live_chat_response,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_baseline_candidate_holdout_proof_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-holdout-proof"
REQUIRED_SURFACES = {"workflow_router_gateway", "anythingllm"}


class EIGBaselineCandidateHoldoutProofStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidateHoldoutProofConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    workflow_router_gateway_base_url: str = "http://127.0.0.1:8500/v1"
    anythingllm_api_base_url: str = "http://127.0.0.1:3001"
    anythingllm_workspace: str = "my-workspace"
    anythingllm_api_key_env: str = "ANYTHINGLLM_API_KEY"
    controller_base_url: str = "http://127.0.0.1:8400"
    timeout_seconds: int = 180
    run_live: bool = True
    include_anythingllm: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-holdout-proof-{utc_timestamp()}.json"


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_baseline_candidate_holdout_proof_policy":
        errors.append("policy.kind must be eig_baseline_candidate_holdout_proof_policy")
    if policy.get("phase") != 316:
        errors.append("policy.phase must be 316")
    if policy.get("recorded_evidence") != "holdout":
        errors.append("policy.recorded_evidence must be holdout")
    if set(string_list(policy.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append("policy.required_surfaces must be workflow_router_gateway and anythingllm")
    cases = policy.get("holdout_cases") if isinstance(policy.get("holdout_cases"), dict) else {}
    path = cases.get("path")
    if not isinstance(path, str) or not path.strip():
        errors.append("holdout_cases.path is required")
    elif not resolve_path(config_root, path).is_file():
        errors.append(f"holdout_cases.path does not exist: {path}")
    if cases.get("expected_case_count") != 7:
        errors.append("holdout_cases.expected_case_count must be 7")
    for key in ("stable_corpus_mutation_allowed", "stable_corpus_promotion_allowed"):
        if policy.get(key) is not False:
            errors.append(f"policy.{key} must be false")
    return errors


def validate_cases_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"cases.schema_version must be {SCHEMA_VERSION}")
    if pack.get("kind") != "eig_baseline_candidate_holdout_cases":
        errors.append("cases.kind must be eig_baseline_candidate_holdout_cases")
    if pack.get("phase") != 316:
        errors.append("cases.phase must be 316")
    if pack.get("synthetic_only") is not True:
        errors.append("cases.synthetic_only must be true")
    baseline = pack.get("contextless_baseline") if isinstance(pack.get("contextless_baseline"), dict) else {}
    if baseline.get("collected_before_local_output") is not True:
        errors.append("contextless_baseline.collected_before_local_output must be true")
    if baseline.get("local_model_output_seen") is not False:
        errors.append("contextless_baseline.local_model_output_seen must be false")
    cases = object_list(pack.get("holdout_cases"))
    if len(cases) != 7:
        errors.append("holdout_cases must contain exactly 7 cases")
    categories = [case.get("category") for case in cases]
    if categories.count("connector") != 3:
        errors.append("holdout_cases must contain 3 connector cases")
    if categories.count("privacy") != 4:
        errors.append("holdout_cases must contain 4 privacy cases")
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append("holdout case id is required")
            continue
        if case_id in seen:
            errors.append(f"duplicate holdout case id: {case_id}")
        seen.add(case_id)
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            errors.append(f"{case_id}.prompt is required")
        if case.get("category") == "connector":
            for key in ("expected_workflow", "expected_connector_id", "expected_operation_id", "expected_result_fragments"):
                if key not in case:
                    errors.append(f"{case_id}.{key} is required")
        elif case.get("category") == "privacy":
            for key in ("expected_route_status", "fixture_ids", "required_markers", "forbidden_markers", "output_format"):
                if key not in case:
                    errors.append(f"{case_id}.{key} is required")
        else:
            errors.append(f"{case_id}.category must be connector or privacy")
    return errors


def connector_response(config: EIGBaselineCandidateHoldoutProofConfig, case: dict[str, Any], surface: str) -> dict[str, Any]:
    connector_config = EIGRuntimeBreadthChatConfig(
        config_root=config.config_root,
        base_url=config.workflow_router_gateway_base_url if surface == "workflow_router_gateway" else None,
        anythingllm_api_base_url=config.anythingllm_api_base_url if surface == "anythingllm" else None,
        anythingllm_workspace=config.anythingllm_workspace,
        anythingllm_api_key_env=config.anythingllm_api_key_env,
        controller_base_url=config.controller_base_url,
        timeout_seconds=config.timeout_seconds,
    )
    prompt = str(case["prompt"])
    if surface == "anythingllm":
        return anythingllm_chat_response(connector_config, prompt)
    if config.run_live:
        return live_chat_response(connector_config, prompt)
    return direct_chat_response(connector_config, prompt)


def connector_result(
    config: EIGBaselineCandidateHoldoutProofConfig,
    case: dict[str, Any],
    *,
    surface: str,
    source_connectors_hash: str,
) -> dict[str, Any]:
    response = connector_response(config, case, surface)
    errors = case_errors(
        case,
        response,
        source_connectors_hash=source_connectors_hash,
        connectors_path=config.config_root / "runtime" / "connectors.json",
    )
    compact = response.get("agentic_controller_response") if isinstance(response.get("agentic_controller_response"), dict) else {}
    return {
        "case_id": case.get("id"),
        "category": "connector",
        "surface": surface,
        "status": "failed" if errors else "passed",
        "workflow": compact.get("workflow"),
        "run_id": compact.get("run_id"),
        "errors": errors,
    }


def privacy_result(
    config: EIGBaselineCandidateHoldoutProofConfig,
    case: dict[str, Any],
    *,
    surface: str,
    fixtures: dict[str, dict[str, Any]],
    memory_records: dict[str, dict[str, Any]],
    api_key: str | None,
) -> dict[str, Any]:
    privacy_config = EIG3PrivacyRuntimeChatConfig(
        config_root=config.config_root,
        workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
        anythingllm_api_base_url=config.anythingllm_api_base_url,
        workspace=config.anythingllm_workspace,
        api_key_env=config.anythingllm_api_key_env,
        timeout_seconds=config.timeout_seconds,
        run_live=config.run_live,
        include_anythingllm=config.include_anythingllm,
    )
    if surface == "anythingllm":
        if not api_key:
            raise RuntimeError(f"{config.anythingllm_api_key_env} is required for AnythingLLM holdout proof")
        result = anythingllm_case(privacy_config, case, fixtures, memory_records, api_key)
    else:
        result = gateway_case(privacy_config, case, fixtures, memory_records)
    return {
        "case_id": result.get("case_id"),
        "category": "privacy",
        "surface": surface,
        "status": result.get("status"),
        "route_status": result.get("route_status"),
        "selected_workflow": result.get("selected_workflow"),
        "errors": result.get("findings") if isinstance(result.get("findings"), list) else [],
    }


def run_eig_baseline_candidate_holdout_proof(config: EIGBaselineCandidateHoldoutProofConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy, config_root=config_root)
    cases_info = policy.get("holdout_cases") if isinstance(policy.get("holdout_cases"), dict) else {}
    cases_path = resolve_path(config_root, str(cases_info.get("path") or ""))
    cases_pack = read_json_object(cases_path) if cases_path.is_file() else {}
    errors.extend(validate_cases_pack(cases_pack))
    holdouts = object_list(cases_pack.get("holdout_cases"))
    baseline_hash_before = sha256_file(config_root / "runtime" / "baseline_corpus.json")
    connectors_hash_before = file_sha256(config_root / "runtime" / "connectors.json")
    fixtures = fixture_lookup(read_json_object(config_root / "runtime" / "eig3_sensitive_data_fixtures.json"))
    memory_records = memory_lookup(read_json_object(config_root / "runtime" / "eig3_memory_lifecycle_fixtures.json"))
    api_key = os.environ.get(config.anythingllm_api_key_env)
    surfaces = ["workflow_router_gateway"]
    if config.include_anythingllm:
        surfaces.append("anythingllm")
        if not api_key and config.run_live:
            errors.append(f"{config.anythingllm_api_key_env} is required for AnythingLLM holdout proof")
    results: list[dict[str, Any]] = []
    if config.run_live and not errors:
        for case in holdouts:
            for surface in surfaces:
                try:
                    if case.get("category") == "connector":
                        results.append(
                            connector_result(
                                config,
                                case,
                                surface=surface,
                                source_connectors_hash=connectors_hash_before,
                            )
                        )
                    elif case.get("category") == "privacy":
                        results.append(
                            privacy_result(
                                config,
                                case,
                                surface=surface,
                                fixtures=fixtures,
                                memory_records=memory_records,
                                api_key=api_key,
                            )
                        )
                except Exception as exc:  # noqa: BLE001 - report proof failures instead of hiding them
                    results.append(
                        {
                            "case_id": case.get("id"),
                            "category": case.get("category"),
                            "surface": surface,
                            "status": "failed",
                            "errors": [{"code": "exception", "message": f"{type(exc).__name__}: {exc}"}],
                        }
                    )
    failed = [item for item in results if item.get("status") != "passed"]
    for item in failed:
        errors.append(f"{item.get('surface')}.{item.get('case_id')} failed")
    baseline_hash_after = sha256_file(config_root / "runtime" / "baseline_corpus.json")
    connectors_hash_after = file_sha256(config_root / "runtime" / "connectors.json")
    stable_corpus_mutated = baseline_hash_before != baseline_hash_after
    connector_registry_mutated = connectors_hash_before != connectors_hash_after
    if stable_corpus_mutated:
        errors.append("runtime/baseline_corpus.json changed during holdout proof")
    if connector_registry_mutated:
        errors.append("runtime/connectors.json changed during holdout proof")
    status = EIGBaselineCandidateHoldoutProofStatus.PASSED.value if not errors else EIGBaselineCandidateHoldoutProofStatus.FAILED.value
    expected_result_count = len(holdouts) * len(surfaces)
    proof_recorded = (
        status == EIGBaselineCandidateHoldoutProofStatus.PASSED.value
        and config.run_live
        and len(results) == expected_result_count
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_holdout_proof_report",
        "phase": 316,
        "status": status,
        "policy_path": str(policy_path),
        "cases_path": str(cases_path),
        "cases_sha256": sha256_file(cases_path) if cases_path.is_file() else None,
        "summary": {
            "status": status,
            "holdout_case_count": len(holdouts),
            "result_count": len(results),
            "passed_result_count": len(results) - len(failed),
            "failed_result_count": len(failed),
            "surface_count": len({str(item.get("surface")) for item in results}),
            "surfaces": sorted({str(item.get("surface")) for item in results}),
            "stable_corpus_mutated": stable_corpus_mutated,
            "connector_registry_mutated": connector_registry_mutated,
            "stable_corpus_promotion_allowed": False,
            "recorded_evidence": ["holdout"] if proof_recorded else [],
            "remaining_missing_evidence": ["founder_approval"] if proof_recorded else ["founder_approval", "holdout"],
            "validation_error_count": len(errors),
            "phase317_ready": proof_recorded,
        },
        "case_results": results,
        "failed_results": failed,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
