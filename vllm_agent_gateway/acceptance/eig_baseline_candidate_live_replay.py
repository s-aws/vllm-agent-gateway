"""EIG baseline-candidate live replay gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.baseline_corpus import (
    BaselineCorpusConfig,
    read_json_object,
    resolve_path,
    run_baseline_corpus_governance,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.eig3_privacy_runtime_chat import (
    EIG3PrivacyRuntimeChatConfig,
    run_eig3_privacy_runtime_chat,
)
from vllm_agent_gateway.acceptance.eig_baseline_candidate_intake import (
    EIGBaselineCandidateIntakeConfig,
    run_eig_baseline_candidate_intake,
)
from vllm_agent_gateway.acceptance.eig_runtime_breadth_chat import (
    EIGRuntimeBreadthChatConfig,
    run_eig_runtime_breadth_chat_validation,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig_baseline_candidate_live_replay_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "eig-baseline-candidate-live-replay"
REQUIRED_MILESTONES = {"M2", "M4", "M9", "M13", "M14", "M19", "M25", "M31", "M36"}
REQUIRED_SURFACES = {"workflow_router_gateway", "anythingllm"}
REQUIRED_CANDIDATE_IDS = {
    "eig-connector-runtime-chat-phase307",
    "eig-privacy-runtime-chat-phase307",
}


class EIGBaselineCandidateLiveReplayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EIGBaselineCandidateLiveReplayConfig:
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


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"eig-baseline-candidate-live-replay-{utc_timestamp()}.json"


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


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "eig_baseline_candidate_live_replay_policy":
        errors.append("policy.kind must be eig_baseline_candidate_live_replay_policy")
    if policy.get("phase") != 308:
        errors.append("policy.phase must be 308")
    if set(string_list(policy.get("required_milestones"))) != REQUIRED_MILESTONES:
        errors.append("policy.required_milestones must match Phase 308 milestones")
    source = policy.get("candidate_source") if isinstance(policy.get("candidate_source"), dict) else {}
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix="candidate_source",
            path_value=source.get("path"),
            hash_value=source.get("sha256"),
        )
    )
    if source.get("expected_candidate_count") != 2:
        errors.append("candidate_source.expected_candidate_count must be 2")
    if source.get("expected_total_source_case_count") != 7:
        errors.append("candidate_source.expected_total_source_case_count must be 7")
    replay_policy = policy.get("replay_policy") if isinstance(policy.get("replay_policy"), dict) else {}
    if replay_policy.get("live_replay_required") is not True:
        errors.append("replay_policy.live_replay_required must be true")
    if set(string_list(replay_policy.get("required_candidate_ids"))) != REQUIRED_CANDIDATE_IDS:
        errors.append("replay_policy.required_candidate_ids must match Phase 307 candidates")
    if set(string_list(replay_policy.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append("replay_policy.required_surfaces must be workflow_router_gateway and anythingllm")
    if replay_policy.get("stable_corpus_promotion_allowed") is not False:
        errors.append("replay_policy.stable_corpus_promotion_allowed must be false")
    if replay_policy.get("founder_approval_recorded") is not False:
        errors.append("replay_policy.founder_approval_recorded must be false")
    return errors


def compact_child_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": report.get("kind"),
        "status": report.get("status"),
        "mode": report.get("mode"),
        "summary": report.get("summary"),
        "report_path": report.get("report_path"),
    }


def run_child(
    name: str,
    errors: list[str],
    func: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return func()
    except Exception as exc:  # pragma: no cover - exercised through live failures.
        errors.append(f"{name} raised {type(exc).__name__}: {exc}")
        return {"kind": name, "status": EIGBaselineCandidateLiveReplayStatus.FAILED.value, "summary": {}}


def surface_status(child_reports: dict[str, dict[str, Any]]) -> dict[str, bool]:
    connector_gateway = child_reports.get("connector_gateway", {})
    connector_anythingllm = child_reports.get("connector_anythingllm", {})
    privacy = child_reports.get("privacy_runtime", {})
    privacy_summary = privacy.get("summary") if isinstance(privacy.get("summary"), dict) else {}
    privacy_surfaces = set(string_list(privacy_summary.get("surfaces")))
    return {
        "workflow_router_gateway": (
            connector_gateway.get("status") == EIGBaselineCandidateLiveReplayStatus.PASSED.value
            and "workflow_router_gateway" in privacy_surfaces
        ),
        "anythingllm": (
            connector_anythingllm.get("status") == EIGBaselineCandidateLiveReplayStatus.PASSED.value
            and "anythingllm" in privacy_surfaces
        ),
    }


def total_live_result_count(child_reports: dict[str, dict[str, Any]]) -> int:
    connector_gateway = child_reports.get("connector_gateway", {})
    connector_anythingllm = child_reports.get("connector_anythingllm", {})
    privacy = child_reports.get("privacy_runtime", {})
    privacy_summary = privacy.get("summary") if isinstance(privacy.get("summary"), dict) else {}
    total = 0
    for report in (connector_gateway, connector_anythingllm):
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        total += int(summary.get("case_count") or 0)
    total += int(privacy_summary.get("result_count") or 0)
    return total


def run_eig_baseline_candidate_live_replay(config: EIGBaselineCandidateLiveReplayConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    output_path = resolve_path(config_root, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy, config_root=config_root)
    report_dir = output_path.parent

    phase307 = run_child(
        "phase307_candidate_intake",
        errors,
        lambda: run_eig_baseline_candidate_intake(
            EIGBaselineCandidateIntakeConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-phase307-validation.json",
            )
        ),
    )
    baseline = run_child(
        "baseline_corpus",
        errors,
        lambda: run_baseline_corpus_governance(
            BaselineCorpusConfig(
                config_root=config_root,
                output_path=report_dir / f"{output_path.stem}-baseline-corpus-validation.json",
            )
        ),
    )
    if phase307.get("status") != EIGBaselineCandidateLiveReplayStatus.PASSED.value:
        errors.append("phase307_candidate_intake must pass before live replay")
    if baseline.get("status") != EIGBaselineCandidateLiveReplayStatus.PASSED.value:
        errors.append("baseline corpus governance must pass before live replay")

    child_reports: dict[str, dict[str, Any]] = {}
    if config.run_live:
        child_reports["connector_gateway"] = run_child(
            "connector_gateway",
            errors,
            lambda: run_eig_runtime_breadth_chat_validation(
                EIGRuntimeBreadthChatConfig(
                    config_root=config_root,
                    output_path=report_dir / f"{output_path.stem}-connector-gateway.json",
                    controller_output_root=report_dir / "controller-artifacts-connector-gateway",
                    base_url=config.workflow_router_gateway_base_url,
                    timeout_seconds=config.timeout_seconds,
                )
            ),
        )
        child_reports["connector_anythingllm"] = run_child(
            "connector_anythingllm",
            errors,
            lambda: run_eig_runtime_breadth_chat_validation(
                EIGRuntimeBreadthChatConfig(
                    config_root=config_root,
                    output_path=report_dir / f"{output_path.stem}-connector-anythingllm.json",
                    controller_output_root=report_dir / "controller-artifacts-connector-anythingllm",
                    anythingllm_api_base_url=config.anythingllm_api_base_url,
                    anythingllm_workspace=config.anythingllm_workspace,
                    anythingllm_api_key_env=config.anythingllm_api_key_env,
                    controller_base_url=config.controller_base_url,
                    timeout_seconds=config.timeout_seconds,
                )
            ),
        )
        child_reports["privacy_runtime"] = run_child(
            "privacy_runtime",
            errors,
            lambda: run_eig3_privacy_runtime_chat(
                EIG3PrivacyRuntimeChatConfig(
                    config_root=config_root,
                    output_path=report_dir / f"{output_path.stem}-privacy-runtime.json",
                    workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
                    anythingllm_api_base_url=config.anythingllm_api_base_url,
                    workspace=config.anythingllm_workspace,
                    api_key_env=config.anythingllm_api_key_env,
                    timeout_seconds=config.timeout_seconds,
                    run_live=True,
                    include_anythingllm=True,
                )
            ),
        )
        for name, child in child_reports.items():
            if child.get("status") != EIGBaselineCandidateLiveReplayStatus.PASSED.value:
                errors.append(f"{name} report must pass")

    surfaces = surface_status(child_reports) if config.run_live else {surface: False for surface in sorted(REQUIRED_SURFACES)}
    missing_surfaces = sorted(surface for surface, covered in surfaces.items() if covered is not True)
    if config.run_live and missing_surfaces:
        errors.append("missing required live surfaces: " + ", ".join(missing_surfaces))
    status = EIGBaselineCandidateLiveReplayStatus.PASSED.value if not errors else EIGBaselineCandidateLiveReplayStatus.FAILED.value
    phase307_summary = phase307.get("summary") if isinstance(phase307.get("summary"), dict) else {}
    baseline_summary = baseline.get("summary") if isinstance(baseline.get("summary"), dict) else {}
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig_baseline_candidate_live_replay_report",
        "phase": 308,
        "status": status,
        "policy_path": str(policy_path),
        "summary": {
            "status": status,
            "run_live": config.run_live,
            "candidate_count": phase307_summary.get("candidate_count", 0),
            "total_source_case_count": phase307_summary.get("total_source_case_count", 0),
            "live_result_count": total_live_result_count(child_reports),
            "required_surface_count": len(REQUIRED_SURFACES),
            "covered_surface_count": sum(1 for covered in surfaces.values() if covered is True),
            "missing_surface_count": len(missing_surfaces),
            "stable_corpus_entry_count": baseline_summary.get("entry_count", 0),
            "stable_corpus_mutated": False,
            "stable_corpus_promotion_allowed": False,
            "founder_approval_recorded": False,
            "validation_error_count": len(errors),
            "phase309_ready": config.run_live and status == EIGBaselineCandidateLiveReplayStatus.PASSED.value,
        },
        "phase307_candidate_intake": compact_child_report(phase307),
        "baseline_corpus": compact_child_report(baseline),
        "child_reports": {name: compact_child_report(report) for name, report in child_reports.items()},
        "surfaces": surfaces,
        "missing_surfaces": missing_surfaces,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
