"""Phase 241 release-candidate large-context strategy replay gate."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chunked_investigation_executor_implementation import (
    ChunkedInvestigationExecutorImplementationConfig,
    validate_chunked_investigation_executor_implementation,
)
from vllm_agent_gateway.acceptance.context_index_prototype import (
    ContextIndexPrototypeConfig,
    dict_value,
    object_list,
    read_json_object,
    resolve_path,
    run_context_index_prototype,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.large_context_usability_live_closeout import (
    LargeContextUsabilityLiveCloseoutConfig,
    validate_large_context_usability_live_closeout,
)
from vllm_agent_gateway.acceptance.large_corpus_context_budget_inventory import (
    LargeCorpusContextBudgetInventoryConfig,
    run_large_corpus_context_budget_inventory,
)
from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)
from vllm_agent_gateway.acceptance.remote_clone_priority0_chat_quality_replay import anythingllm_target_settings


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "release_candidate_large_context_strategy_replay_policy"
EXPECTED_REPORT_KIND = "release_candidate_large_context_strategy_replay_report"
EXPECTED_PHASE = 241
EXPECTED_BACKLOG_ID = "P0-M14-241"
EXPECTED_MILESTONE_IDS = {"M6", "M8", "M16", "M14"}
DEFAULT_POLICY_PATH = Path("runtime") / "release_candidate_large_context_strategy_replay_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "release-candidate-large-context-strategy-replay" / "phase241"


class ReleaseCandidateLargeContextReplayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ReleaseCandidateLargeContextReplayDecision(str, Enum):
    READY = "release_candidate_large_context_strategy_ready"
    BLOCKED = "release_candidate_large_context_strategy_blocked"


@dataclass(frozen=True)
class ReleaseCandidateLargeContextStrategyReplayConfig:
    config_root: Path
    output_path: Path | None = None
    policy_path: Path = DEFAULT_POLICY_PATH
    include_gateway: bool = True
    include_anythingllm: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 1200


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"release-candidate-large-context-strategy-replay-{utc_timestamp()}.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    return read_json(resolve_path(config_root, policy_path))


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def bool_value(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 241")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append("policy.milestone_ids must be M6, M8, M16, and M14")
    if policy.get("required_decision") != ReleaseCandidateLargeContextReplayDecision.READY.value:
        errors.append("policy.required_decision must be release_candidate_large_context_strategy_ready")
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append("policy.required_surfaces must include gateway and anythingllm")
    required_strategy_ids = set(string_list(policy.get("required_strategy_ids")))
    for strategy_id in ("retrieval", "artifact_paging", "summarization", "refusal", "chunked_investigation"):
        if strategy_id not in required_strategy_ids:
            errors.append(f"policy.required_strategy_ids missing {strategy_id}")
    for report_name in ("large_corpus_context_budget_inventory", "context_index_prototype"):
        if report_name not in string_list(policy.get("required_bootstrap_reports")):
            errors.append(f"policy.required_bootstrap_reports missing {report_name}")
    for report_name in ("large_context_usability_live_closeout", "chunked_investigation_executor_implementation"):
        if report_name not in string_list(policy.get("required_live_reports")):
            errors.append(f"policy.required_live_reports missing {report_name}")
    safety = dict_value(policy.get("safety_requirements"))
    expected_safety: dict[str, object] = {
        "raw_1m_prompt_support_proven": False,
        "raw_prompt_stuffing_allowed": False,
        "source_text_retention": "metadata_only",
        "store_source_text": False,
        "store_rejected_content": False,
        "generated_corpus_unchanged_after_live_replay": True,
        "artifact_only_answers_allowed": False,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) != expected:
            errors.append(f"policy.safety_requirements.{key} must be {expected!r}")
    minimums = dict_value(policy.get("minimums"))
    for key in (
        "phase221_response_count",
        "phase223_response_count",
        "anythingllm_response_count",
        "small_repo_regression_count",
        "large_corpus_estimated_tokens",
    ):
        if int_value(minimums.get(key)) <= 0:
            errors.append(f"policy.minimums.{key} must be a positive integer")
    baseline = dict_value(policy.get("blind_baseline_summary"))
    for key in ("ideal_answer_shape", "must_have_facts", "hard_failures"):
        if not string_list(baseline.get(key)):
            errors.append(f"policy.blind_baseline_summary.{key} must be a non-empty string list")
    if policy.get("acceptance_marker") != "RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY PASS":
        errors.append("policy.acceptance_marker must be RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY PASS")
    return errors


def selected_surfaces(config: ReleaseCandidateLargeContextStrategyReplayConfig) -> list[str]:
    values: list[str] = []
    if config.include_gateway:
        values.append("gateway")
    if config.include_anythingllm:
        values.append("anythingllm")
    return values


def tree_snapshot(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {"path": str(root), "exists": False, "files": {}}
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        files[relative] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    return {"path": str(root), "exists": True, "file_count": len(files), "files": files}


def target_root_from_phase214_report(config_root: Path, report: dict[str, Any]) -> Path:
    fixture = dict_value(report.get("generated_fixture"))
    root = fixture.get("root") or report.get("target_root") or "runtime-state/phase214/generated-large-corpus"
    return resolve_path(config_root, str(root)).resolve()


def output_dir_for(config: ReleaseCandidateLargeContextStrategyReplayConfig) -> Path:
    output_path = config.output_path or default_report_path(config.config_root.resolve())
    if not output_path.is_absolute():
        output_path = config.config_root.resolve() / output_path
    return output_path.parent


def run_bootstrap_reports(config: ReleaseCandidateLargeContextStrategyReplayConfig, output_dir: Path) -> dict[str, Any]:
    phase214 = run_large_corpus_context_budget_inventory(
        LargeCorpusContextBudgetInventoryConfig(
            config_root=config.config_root,
        )
    )
    phase217 = run_context_index_prototype(
        ContextIndexPrototypeConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase241-phase217-context-index-prototype-report.json",
            markdown_output_path=output_dir / "phase241-phase217-context-index-prototype-report.md",
            require_artifacts=False,
        )
    )
    return {"phase214": phase214, "phase217": phase217}


def run_live_reports(
    config: ReleaseCandidateLargeContextStrategyReplayConfig,
    output_dir: Path,
) -> dict[str, Any]:
    phase221 = validate_large_context_usability_live_closeout(
        LargeContextUsabilityLiveCloseoutConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase241-phase221-large-context-usability-live-closeout-report.json",
            markdown_output_path=output_dir / "phase241-phase221-large-context-usability-live-closeout-report.md",
            include_gateway=config.include_gateway,
            include_anythingllm=config.include_anythingllm,
            live=True,
            model_base_url=config.model_base_url,
            workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
            controller_base_url=config.controller_base_url,
            anythingllm_api_base_url=config.anythingllm_api_base_url,
            workspace=config.workspace,
            api_key_env=config.api_key_env,
            timeout_seconds=config.timeout_seconds,
            require_artifacts=False,
        )
    )
    phase223 = validate_chunked_investigation_executor_implementation(
        ChunkedInvestigationExecutorImplementationConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase241-phase223-chunked-investigation-executor-implementation-report.json",
            markdown_output_path=output_dir / "phase241-phase223-chunked-investigation-executor-implementation-report.md",
            include_gateway=config.include_gateway,
            include_anythingllm=config.include_anythingllm,
            live=True,
            model_base_url=config.model_base_url,
            workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
            controller_base_url=config.controller_base_url,
            anythingllm_api_base_url=config.anythingllm_api_base_url,
            workspace=config.workspace,
            api_key_env=config.api_key_env,
            timeout_seconds=config.timeout_seconds,
            require_artifacts=False,
        )
    )
    return {"phase221": phase221, "phase223": phase223}


def response_count_for_surface(report: dict[str, Any], surface: str) -> int:
    return sum(1 for item in object_list(report.get("responses")) if item.get("surface") == surface)


def small_repo_count(report: dict[str, Any]) -> int:
    return len(object_list(report.get("small_repo_regression_results")))


def failed_small_repo_count(report: dict[str, Any]) -> int:
    return sum(1 for item in object_list(report.get("small_repo_regression_results")) if item.get("status") != "passed")


def strategy_ids_from_reports(phase221: dict[str, Any], phase223: dict[str, Any]) -> list[str]:
    values = {
        str(item.get("selected_context_strategy"))
        for item in object_list(phase221.get("responses")) + object_list(phase223.get("responses"))
        if isinstance(item.get("selected_context_strategy"), str)
    }
    return sorted(values)


def run_ids_from_reports(phase221: dict[str, Any], phase223: dict[str, Any]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for report_name, report in (("phase221", phase221), ("phase223", phase223)):
        values[report_name] = [
            str(item.get("run_id"))
            for item in object_list(report.get("responses")) + object_list(report.get("small_repo_regression_results"))
            if isinstance(item.get("run_id"), str) and item.get("run_id") not in ("", "unknown")
        ]
    return values


def build_report(
    *,
    policy: dict[str, Any],
    target_settings: dict[str, Any],
    bootstrap_reports: dict[str, Any],
    live_reports: dict[str, Any],
    corpus_before: dict[str, Any],
    corpus_after: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    phase214 = dict_value(bootstrap_reports.get("phase214"))
    phase217 = dict_value(bootstrap_reports.get("phase217"))
    phase221 = dict_value(live_reports.get("phase221"))
    phase223 = dict_value(live_reports.get("phase223"))
    minimums = dict_value(policy.get("minimums"))
    safety = dict_value(policy.get("safety_requirements"))
    strategies = strategy_ids_from_reports(phase221, phase223)
    required_strategies = set(string_list(policy.get("required_strategy_ids")))
    corpus_unchanged = corpus_before == corpus_after
    anythingllm_response_count = response_count_for_surface(phase221, "anythingllm") + response_count_for_surface(phase223, "anythingllm")
    gateway_response_count = response_count_for_surface(phase221, "gateway") + response_count_for_surface(phase223, "gateway")
    small_regression_count = small_repo_count(phase221) + small_repo_count(phase223)
    failed_small_regression_count = failed_small_repo_count(phase221) + failed_small_repo_count(phase223)
    phase214_summary = dict_value(phase214.get("summary"))
    phase217_summary = dict_value(phase217.get("summary"))
    phase221_summary = dict_value(phase221.get("summary"))
    phase223_summary = dict_value(phase223.get("summary"))
    computed_errors = list(errors)
    if target_settings.get("status") != ReleaseCandidateLargeContextReplayStatus.PASSED.value:
        computed_errors.append("AnythingLLM target settings must pass")
    if phase214.get("status") != "passed":
        computed_errors.append("Phase 214 bootstrap report must pass")
    if int_value(phase214_summary.get("estimated_token_count")) < int_value(minimums.get("large_corpus_estimated_tokens")):
        computed_errors.append("Phase 214 estimated token count below policy minimum")
    if phase214_summary.get("raw_1m_prompt_support_proven") is not safety.get("raw_1m_prompt_support_proven"):
        computed_errors.append("Phase 214 raw 1M prompt support boundary drifted")
    if phase217.get("status") != "passed":
        computed_errors.append("Phase 217 bootstrap report must pass")
    if phase217_summary.get("source_text_retention") != safety.get("source_text_retention"):
        computed_errors.append("Phase 217 source_text_retention drifted")
    if phase217_summary.get("store_source_text") is not safety.get("store_source_text"):
        computed_errors.append("Phase 217 store_source_text drifted")
    if phase217_summary.get("store_rejected_content") is not safety.get("store_rejected_content"):
        computed_errors.append("Phase 217 store_rejected_content drifted")
    if phase221.get("status") != "passed":
        computed_errors.append("Phase 221 live report must pass")
    if int_value(phase221_summary.get("response_count")) < int_value(minimums.get("phase221_response_count")):
        computed_errors.append("Phase 221 response count below policy minimum")
    if int_value(phase221_summary.get("failed_response_count")):
        computed_errors.append("Phase 221 failed responses must be zero")
    if phase221_summary.get("raw_prompt_stuffing_allowed") is not safety.get("raw_prompt_stuffing_allowed"):
        computed_errors.append("Phase 221 raw_prompt_stuffing_allowed drifted")
    if phase223.get("status") != "passed":
        computed_errors.append("Phase 223 live report must pass")
    if int_value(phase223_summary.get("response_count")) < int_value(minimums.get("phase223_response_count")):
        computed_errors.append("Phase 223 response count below policy minimum")
    if int_value(phase223_summary.get("failed_response_count")):
        computed_errors.append("Phase 223 failed responses must be zero")
    if phase223_summary.get("raw_prompt_stuffing_allowed") is not safety.get("raw_prompt_stuffing_allowed"):
        computed_errors.append("Phase 223 raw_prompt_stuffing_allowed drifted")
    missing_strategies = sorted(required_strategies - set(strategies))
    if missing_strategies:
        computed_errors.append("Missing required strategies: " + ", ".join(missing_strategies))
    if anythingllm_response_count < int_value(minimums.get("anythingllm_response_count")):
        computed_errors.append("AnythingLLM response count below policy minimum")
    if small_regression_count < int_value(minimums.get("small_repo_regression_count")):
        computed_errors.append("small-repo regression count below policy minimum")
    if failed_small_regression_count:
        computed_errors.append("small-repo regression failures must be zero")
    if corpus_unchanged is not safety.get("generated_corpus_unchanged_after_live_replay"):
        computed_errors.append("generated corpus changed during live replay")
    ready = not computed_errors
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "status": ReleaseCandidateLargeContextReplayStatus.PASSED.value
        if ready
        else ReleaseCandidateLargeContextReplayStatus.FAILED.value,
        "decision": ReleaseCandidateLargeContextReplayDecision.READY.value
        if ready
        else ReleaseCandidateLargeContextReplayDecision.BLOCKED.value,
        "generated_at": utc_timestamp(),
        "target_settings": target_settings,
        "bootstrap_reports": {
            "phase214": {
                "status": phase214.get("status"),
                "report_path": phase214.get("report_path"),
                "summary": phase214_summary,
            },
            "phase217": {
                "status": phase217.get("status"),
                "report_path": phase217.get("report_path"),
                "summary": phase217_summary,
            },
        },
        "live_reports": {
            "phase221": {
                "status": phase221.get("status"),
                "report_path": phase221.get("report_path"),
                "summary": phase221_summary,
            },
            "phase223": {
                "status": phase223.get("status"),
                "report_path": phase223.get("report_path"),
                "summary": phase223_summary,
            },
        },
        "run_ids": run_ids_from_reports(phase221, phase223),
        "corpus_before": {
            "path": corpus_before.get("path"),
            "exists": corpus_before.get("exists"),
            "file_count": corpus_before.get("file_count"),
        },
        "corpus_after": {
            "path": corpus_after.get("path"),
            "exists": corpus_after.get("exists"),
            "file_count": corpus_after.get("file_count"),
        },
        "corpus_unchanged": corpus_unchanged,
        "summary": {
            "phase214_status": phase214.get("status"),
            "phase217_status": phase217.get("status"),
            "phase221_status": phase221.get("status"),
            "phase223_status": phase223.get("status"),
            "phase221_response_count": phase221_summary.get("response_count"),
            "phase223_response_count": phase223_summary.get("response_count"),
            "gateway_response_count": gateway_response_count,
            "anythingllm_response_count": anythingllm_response_count,
            "small_repo_regression_count": small_regression_count,
            "failed_small_repo_regression_count": failed_small_regression_count,
            "strategy_ids": strategies,
            "required_strategy_ids": sorted(required_strategies),
            "raw_1m_prompt_support_proven": phase214_summary.get("raw_1m_prompt_support_proven"),
            "raw_prompt_stuffing_allowed": phase221_summary.get("raw_prompt_stuffing_allowed"),
            "source_text_retention": phase217_summary.get("source_text_retention"),
            "store_source_text": phase217_summary.get("store_source_text"),
            "store_rejected_content": phase217_summary.get("store_rejected_content"),
            "target_settings_status": target_settings.get("status"),
            "corpus_unchanged": corpus_unchanged,
        },
        "errors": computed_errors,
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 241")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if set(string_list(report.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append("report.milestone_ids must be M6, M8, M16, and M14")
    if report.get("decision") != policy.get("required_decision"):
        errors.append("report.decision must match policy.required_decision")
    summary = dict_value(report.get("summary"))
    if summary.get("target_settings_status") != ReleaseCandidateLargeContextReplayStatus.PASSED.value:
        errors.append("report.summary.target_settings_status must pass")
    if summary.get("raw_1m_prompt_support_proven") is not False:
        errors.append("report.summary.raw_1m_prompt_support_proven must be false")
    if summary.get("raw_prompt_stuffing_allowed") is not False:
        errors.append("report.summary.raw_prompt_stuffing_allowed must be false")
    if summary.get("source_text_retention") != "metadata_only":
        errors.append("report.summary.source_text_retention must be metadata_only")
    if summary.get("store_source_text") is not False:
        errors.append("report.summary.store_source_text must be false")
    if summary.get("store_rejected_content") is not False:
        errors.append("report.summary.store_rejected_content must be false")
    if summary.get("corpus_unchanged") is not True or report.get("corpus_unchanged") is not True:
        errors.append("report.corpus_unchanged must be true")
    missing = sorted(set(string_list(policy.get("required_strategy_ids"))) - set(string_list(summary.get("strategy_ids"))))
    if missing:
        errors.append("report.summary.strategy_ids missing " + ", ".join(missing))
    minimums = dict_value(policy.get("minimums"))
    if int_value(summary.get("phase221_response_count")) < int_value(minimums.get("phase221_response_count")):
        errors.append("report.summary.phase221_response_count below minimum")
    if int_value(summary.get("phase223_response_count")) < int_value(minimums.get("phase223_response_count")):
        errors.append("report.summary.phase223_response_count below minimum")
    if int_value(summary.get("anythingllm_response_count")) < int_value(minimums.get("anythingllm_response_count")):
        errors.append("report.summary.anythingllm_response_count below minimum")
    if int_value(summary.get("small_repo_regression_count")) < int_value(minimums.get("small_repo_regression_count")):
        errors.append("report.summary.small_repo_regression_count below minimum")
    if int_value(summary.get("failed_small_repo_regression_count")):
        errors.append("report.summary.failed_small_repo_regression_count must be zero")
    if report.get("errors"):
        errors.append("report.errors must be empty")
    return errors


def run_release_candidate_large_context_strategy_replay(
    config: ReleaseCandidateLargeContextStrategyReplayConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    errors = validate_policy(policy)
    surfaces = selected_surfaces(config)
    if set(surfaces) != set(string_list(policy.get("required_surfaces"))):
        errors.append("selected surfaces must match policy.required_surfaces")
    api_key = os.environ.get(config.api_key_env)
    if config.include_anythingllm and not api_key:
        errors.append(f"{config.api_key_env} is required for live AnythingLLM replay")
        api_key = None
    target_settings = (
        anythingllm_target_settings(config, api_key=api_key, policy=policy)
        if api_key
        else {"status": ReleaseCandidateLargeContextReplayStatus.FAILED.value, "errors": [f"{config.api_key_env} missing"]}
    )
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    output_dir = output_path.parent
    bootstrap_reports: dict[str, Any] = {}
    live_reports: dict[str, Any] = {}
    corpus_before: dict[str, Any] = {}
    corpus_after: dict[str, Any] = {}
    if not errors:
        bootstrap_reports = run_bootstrap_reports(config, output_dir)
        corpus_root = target_root_from_phase214_report(config_root, dict_value(bootstrap_reports.get("phase214")))
        corpus_before = tree_snapshot(corpus_root)
        live_reports = run_live_reports(config, output_dir)
        corpus_after = tree_snapshot(corpus_root)
    report = build_report(
        policy=policy,
        target_settings=target_settings,
        bootstrap_reports=bootstrap_reports,
        live_reports=live_reports,
        corpus_before=corpus_before,
        corpus_after=corpus_after,
        errors=errors,
    )
    validation_errors = validate_report(report, policy)
    if validation_errors:
        report["status"] = ReleaseCandidateLargeContextReplayStatus.FAILED.value
        report["decision"] = ReleaseCandidateLargeContextReplayDecision.BLOCKED.value
        report["errors"] = report["errors"] + validation_errors
    write_json(output_path, report)
    return report
