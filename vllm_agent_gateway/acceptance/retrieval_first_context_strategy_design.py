"""Phase 215 retrieval-first context strategy design gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "retrieval_first_context_strategy_design_policy"
EXPECTED_REPORT_KIND = "retrieval_first_context_strategy_design_report"
EXPECTED_PHASE = 215
EXPECTED_BACKLOG_ID = "P0-M6-215"
EXPECTED_MILESTONE_IDS = {"M6", "M8"}
MINIMUM_LARGE_CONTEXT_OBJECTIVE_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "retrieval_first_context_strategy_design_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase215" / "phase215-retrieval-first-context-strategy-design-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "phase215" / "phase215-retrieval-first-context-strategy-design-report.md"
)


class ContextStrategy(str, Enum):
    DIRECT_CONTEXT = "direct_context"
    RETRIEVAL = "retrieval"
    CHUNKED_INVESTIGATION = "chunked_investigation"
    SUMMARIZATION = "summarization"
    ARTIFACT_PAGING = "artifact_paging"
    REFUSAL = "refusal"


REQUIRED_STRATEGIES = {item.value for item in ContextStrategy}
EVIDENCE_STRATEGIES = REQUIRED_STRATEGIES - {ContextStrategy.REFUSAL.value}
REQUIRED_ROUTING_INPUTS = {
    "prompt_intent",
    "target_root",
    "estimated_corpus_tokens",
    "file_count",
    "requested_specificity",
    "output_format",
    "mutation_intent",
    "allowed_root_status",
    "ignore_policy_status",
    "index_safety_status",
    "source_freshness_status",
    "context_budget",
    "ambiguity_level",
}
REQUIRED_FAILURES = {
    "raw_1m_prompt_stuffing_request",
    "missing_target_root",
    "unapproved_target_root",
    "ignored_or_private_path_requested",
    "secret_like_content_requested",
    "stale_index_or_source_hash",
    "no_relevant_evidence_found",
    "ambiguous_large_context_request",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "no_raw_prompt_stuffing_claim",
    "no_retrieval_backed_chat_before_phase218",
    "no_durable_index_before_phase216",
    "no_ignored_private_or_secret_like_content",
    "no_unapproved_root_access",
    "no_artifact_only_chat_answer",
    "no_mutation_of_protected_fixtures",
}
REQUIRED_OUT_OF_SCOPE = {
    "retrieval_index_implementation",
    "retrieval_backed_chat_integration",
    "artifact_paging_implementation",
    "raw_1m_context_benchmark",
    "protected_fixture_mutation",
    "advanced_refactor_reactivation",
}
REQUIRED_EVIDENCE_REQUIREMENTS = {
    "source_refs",
    "source_hashes",
    "confidence",
    "limitations",
    "safe_alternative",
    "output_format_parity",
}


@dataclass(frozen=True)
class RetrievalFirstContextStrategyDesignConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def require_string_list(
    errors: list[dict[str, str]],
    value: object,
    *,
    error_id: str,
    message: str,
    minimum: int = 1,
) -> list[str]:
    values = string_list(value)
    if len(values) < minimum:
        errors.append(validation_error(error_id, message))
    return values


def validate_strategy_definitions(policy: dict[str, Any], errors: list[dict[str, str]]) -> None:
    strategies = object_list(policy.get("strategy_definitions"))
    strategy_ids = [str(item.get("strategy_id")) for item in strategies]
    if set(strategy_ids) != REQUIRED_STRATEGIES:
        errors.append(
            validation_error(
                "policy.strategy_definitions",
                f"strategy_definitions must define exactly {sorted(REQUIRED_STRATEGIES)}",
            )
        )
    if len(strategy_ids) != len(set(strategy_ids)):
        errors.append(validation_error("policy.strategy_definitions.duplicates", "strategy IDs must be unique"))

    by_id = {str(item.get("strategy_id")): item for item in strategies}
    for strategy_id in REQUIRED_STRATEGIES:
        item = by_id.get(strategy_id, {})
        prefix = f"policy.strategy_definitions.{strategy_id}"
        for key in ("purpose", "budget_rule"):
            if not isinstance(item.get(key), str) or not str(item.get(key)).strip():
                errors.append(validation_error(f"{prefix}.{key}", f"{key} must be a non-empty string"))
        for key in ("use_when", "forbidden_when", "evidence_requirements", "output_contract"):
            require_string_list(errors, item.get(key), error_id=f"{prefix}.{key}", message=f"{key} must not be empty")
        if strategy_id in EVIDENCE_STRATEGIES:
            evidence = set(string_list(item.get("evidence_requirements")))
            for required in ("source_refs", "source_hashes", "confidence", "limitations"):
                if required not in evidence:
                    errors.append(validation_error(f"{prefix}.evidence_requirements", f"missing {required}"))
        if strategy_id == ContextStrategy.RETRIEVAL.value:
            forbidden = " ".join(string_list(item.get("forbidden_when"))).lower()
            if "safety governance" not in forbidden:
                errors.append(validation_error(f"{prefix}.forbidden_when", "retrieval must be forbidden before safety governance"))
            if "stale" not in forbidden:
                errors.append(validation_error(f"{prefix}.forbidden_when", "retrieval must reject stale source/index state"))
        if strategy_id == ContextStrategy.DIRECT_CONTEXT.value:
            forbidden = " ".join(string_list(item.get("forbidden_when"))).lower()
            if "full corpus" not in forbidden and "whole corpus" not in forbidden:
                errors.append(validation_error(f"{prefix}.forbidden_when", "direct context must reject full-corpus prompt stuffing"))
            if "target input limit" not in str(item.get("budget_rule", "")).lower():
                errors.append(validation_error(f"{prefix}.budget_rule", "direct context budget rule must reference target input limit"))
        if strategy_id == ContextStrategy.REFUSAL.value:
            evidence = set(string_list(item.get("evidence_requirements")))
            for required in ("refusal_reason", "safe_alternative", "required_next_step"):
                if required not in evidence:
                    errors.append(validation_error(f"{prefix}.evidence_requirements", f"missing {required}"))


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 215"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6 and M8"))

    phase214 = dict_value(policy.get("phase214_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(phase214.get(key), str) or not str(phase214.get(key)).strip():
            errors.append(validation_error(f"policy.phase214_precondition.{key}", f"{key} must be a non-empty string"))
    if phase214.get("required_phase215_ready") is not True:
        errors.append(
            validation_error("policy.phase214_precondition.required_phase215_ready", "required_phase215_ready must be true")
        )
    minimum_tokens = phase214.get("minimum_estimated_token_count")
    if not isinstance(minimum_tokens, int) or minimum_tokens < MINIMUM_LARGE_CONTEXT_OBJECTIVE_TOKENS:
        errors.append(
            validation_error(
                "policy.phase214_precondition.minimum_estimated_token_count",
                f"minimum_estimated_token_count must be at least {MINIMUM_LARGE_CONTEXT_OBJECTIVE_TOKENS}",
            )
        )
    if phase214.get("raw_1m_prompt_support_proven_must_be") is not False:
        errors.append(
            validation_error(
                "policy.phase214_precondition.raw_1m_prompt_support_proven_must_be",
                "raw_1m_prompt_support_proven_must_be must be false",
            )
        )

    if set(string_list(policy.get("required_strategy_ids"))) != REQUIRED_STRATEGIES:
        errors.append(
            validation_error("policy.required_strategy_ids", f"required strategies must be {sorted(REQUIRED_STRATEGIES)}")
        )
    validate_strategy_definitions(policy, errors)

    routing_input_ids = {str(item.get("input_id")) for item in object_list(policy.get("routing_inputs"))}
    missing_inputs = sorted(REQUIRED_ROUTING_INPUTS - routing_input_ids)
    if missing_inputs:
        errors.append(validation_error("policy.routing_inputs", f"missing routing inputs: {missing_inputs}"))
    for item in object_list(policy.get("routing_inputs")):
        if item.get("input_id") in REQUIRED_ROUTING_INPUTS and item.get("required") is not True:
            errors.append(validation_error(f"policy.routing_inputs.{item.get('input_id')}", "required routing input must be true"))

    decision_cases = object_list(policy.get("decision_cases"))
    case_strategies = {str(item.get("expected_strategy")) for item in decision_cases}
    if case_strategies != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.decision_cases", "decision cases must cover every strategy exactly enough to prove selection"))
    if len(decision_cases) < 8:
        errors.append(validation_error("policy.decision_cases.count", "decision_cases must include target and negative control cases"))
    for index, item in enumerate(decision_cases):
        prefix = f"policy.decision_cases[{index}]"
        for key in ("case_id", "prompt_class", "estimated_token_relation", "requested_specificity", "index_safety_status", "expected_strategy"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(validation_error(f"{prefix}.{key}", f"{key} must be a non-empty string"))
        if item.get("expected_strategy") not in REQUIRED_STRATEGIES:
            errors.append(validation_error(f"{prefix}.expected_strategy", "expected_strategy must be a known strategy"))
        require_string_list(
            errors,
            item.get("required_rationale"),
            error_id=f"{prefix}.required_rationale",
            message="required_rationale must not be empty",
            minimum=2,
        )

    evidence_ids = {str(item.get("requirement_id")) for item in object_list(policy.get("evidence_requirements"))}
    missing_evidence = sorted(REQUIRED_EVIDENCE_REQUIREMENTS - evidence_ids)
    if missing_evidence:
        errors.append(validation_error("policy.evidence_requirements", f"missing evidence requirements: {missing_evidence}"))

    failure_ids = {str(item.get("failure_id")) for item in object_list(policy.get("failure_behaviors"))}
    missing_failures = sorted(REQUIRED_FAILURES - failure_ids)
    if missing_failures:
        errors.append(validation_error("policy.failure_behaviors", f"missing failure behaviors: {missing_failures}"))
    for item in object_list(policy.get("failure_behaviors")):
        if item.get("expected_strategy") != ContextStrategy.REFUSAL.value:
            errors.append(validation_error(f"policy.failure_behaviors.{item.get('failure_id')}", "failure behavior must refuse"))
        if not isinstance(item.get("required_user_visible_recovery"), str) or not item["required_user_visible_recovery"].strip():
            errors.append(
                validation_error(
                    f"policy.failure_behaviors.{item.get('failure_id')}.required_user_visible_recovery",
                    "failure behavior must include user-visible recovery",
                )
            )

    missing_negative_controls = sorted(REQUIRED_NEGATIVE_CONTROLS - set(string_list(policy.get("negative_controls"))))
    if missing_negative_controls:
        errors.append(validation_error("policy.negative_controls", f"missing negative controls: {missing_negative_controls}"))
    missing_out_of_scope = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing_out_of_scope:
        errors.append(validation_error("policy.out_of_scope", f"missing out-of-scope boundaries: {missing_out_of_scope}"))

    sequence = {int(item.get("phase")): item for item in object_list(policy.get("implementation_sequence")) if isinstance(item.get("phase"), int)}
    if 216 not in sequence:
        errors.append(validation_error("policy.implementation_sequence.216", "Phase 216 must be sequenced before indexing/retrieval"))
    else:
        missing_precedence = sorted({217, 218, 220, 221} - set(int(value) for value in sequence[216].get("must_precede", []) if isinstance(value, int)))
        if missing_precedence:
            errors.append(validation_error("policy.implementation_sequence.216", f"Phase 216 must precede {missing_precedence}"))
    if 217 in sequence and 218 not in sequence[217].get("must_precede", []):
        errors.append(validation_error("policy.implementation_sequence.217", "Phase 217 must precede Phase 218"))
    if policy.get("acceptance_marker") != "PHASE215 RETRIEVAL FIRST CONTEXT STRATEGY DESIGN PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 215"))
    return errors


def load_phase214_report(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    precondition = dict_value(policy.get("phase214_precondition"))
    raw_path = precondition.get("report_path")
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error("phase214_report.missing", "Phase 214 report is required", source="phase214")]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [
            validation_error(
                "phase214_report.malformed",
                f"Phase 214 report is malformed: {type(exc).__name__}: {exc}",
                source="phase214",
            )
        ]


def validate_phase214_precondition(policy: dict[str, Any], phase214_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not phase214_report:
        return errors
    precondition = dict_value(policy.get("phase214_precondition"))
    summary = dict_value(phase214_report.get("summary"))
    if phase214_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase214_report.status", "Phase 214 report status must be passed", source="phase214"))
    if summary.get("phase215_ready") is not precondition.get("required_phase215_ready"):
        errors.append(validation_error("phase214_report.phase215_ready", "Phase 214 report must mark phase215_ready", source="phase214"))
    minimum_tokens = precondition.get("minimum_estimated_token_count")
    if not isinstance(summary.get("estimated_token_count"), int) or summary["estimated_token_count"] < minimum_tokens:
        errors.append(
            validation_error(
                "phase214_report.estimated_token_count",
                f"Phase 214 estimated_token_count must be at least {minimum_tokens}",
                source="phase214",
            )
        )
    if summary.get("raw_1m_prompt_support_proven") is not precondition.get("raw_1m_prompt_support_proven_must_be"):
        errors.append(
            validation_error(
                "phase214_report.raw_1m_prompt_support_proven",
                "Phase 214 must not prove or claim raw 1M prompt support",
                source="phase214",
            )
        )
    return errors


def report_summary(policy: dict[str, Any], phase214_report: dict[str, Any], validation_errors: list[dict[str, str]]) -> dict[str, Any]:
    strategies = object_list(policy.get("strategy_definitions"))
    decisions = object_list(policy.get("decision_cases"))
    phase214_summary = dict_value(phase214_report.get("summary"))
    return {
        "strategy_count": len(strategies),
        "decision_case_count": len(decisions),
        "routing_input_count": len(object_list(policy.get("routing_inputs"))),
        "failure_behavior_count": len(object_list(policy.get("failure_behaviors"))),
        "negative_control_count": len(string_list(policy.get("negative_controls"))),
        "out_of_scope_count": len(string_list(policy.get("out_of_scope"))),
        "phase214_estimated_token_count": phase214_summary.get("estimated_token_count"),
        "phase214_model_limit": phase214_summary.get("model_limit"),
        "phase214_target_input_limit": phase214_summary.get("target_input_limit"),
        "raw_1m_prompt_support_proven": False,
        "retrieval_index_implementation_in_scope": "retrieval_index_implementation" not in string_list(policy.get("out_of_scope")),
        "retrieval_backed_chat_integration_in_scope": "retrieval_backed_chat_integration" not in string_list(policy.get("out_of_scope")),
        "phase216_ready": not validation_errors,
        "validation_error_count": len(validation_errors),
    }


def build_report(config: RetrievalFirstContextStrategyDesignConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    phase214_path, phase214_report, phase214_errors = load_phase214_report(
        config_root,
        policy,
        require_artifacts=config.require_artifacts,
    )
    precondition_errors = validate_phase214_precondition(policy, phase214_report)
    validation_errors = policy_errors + phase214_errors + precondition_errors
    status = "passed" if not validation_errors else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "output_path": str(output_path),
        "phase214_report_path": str(phase214_path) if phase214_path is not None else None,
        "phase214_report_sha256": sha256_file(phase214_path) if phase214_path is not None and phase214_path.is_file() else None,
        "strategies": object_list(policy.get("strategy_definitions")),
        "routing_inputs": object_list(policy.get("routing_inputs")),
        "decision_cases": object_list(policy.get("decision_cases")),
        "evidence_requirements": object_list(policy.get("evidence_requirements")),
        "failure_behaviors": object_list(policy.get("failure_behaviors")),
        "negative_controls": string_list(policy.get("negative_controls")),
        "implementation_sequence": object_list(policy.get("implementation_sequence")),
        "out_of_scope": string_list(policy.get("out_of_scope")),
        "validation_errors": validation_errors,
        "summary": report_summary(policy, phase214_report, validation_errors),
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Retrieval-First Context Strategy Design",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Strategy count: `{summary.get('strategy_count')}`",
        f"- Decision cases: `{summary.get('decision_case_count')}`",
        f"- Routing inputs: `{summary.get('routing_input_count')}`",
        f"- Phase 214 estimated tokens: `{summary.get('phase214_estimated_token_count')}`",
        f"- Phase 214 model limit: `{summary.get('phase214_model_limit')}`",
        f"- Phase 214 target input limit: `{summary.get('phase214_target_input_limit')}`",
        f"- Raw 1M prompt support proven: `{summary.get('raw_1m_prompt_support_proven')}`",
        f"- Retrieval index implementation in scope: `{summary.get('retrieval_index_implementation_in_scope')}`",
        f"- Retrieval-backed chat integration in scope: `{summary.get('retrieval_backed_chat_integration_in_scope')}`",
        f"- Phase 216 ready: `{summary.get('phase216_ready')}`",
        "",
        "## Strategy Labels",
    ]
    for strategy in object_list(report.get("strategies")):
        lines.append(f"- `{strategy.get('strategy_id')}`: {strategy.get('purpose')}")
    lines.extend(["", "## Decision Cases"])
    for case in object_list(report.get("decision_cases")):
        lines.append(f"- `{case.get('case_id')}` -> `{case.get('expected_strategy')}`: {case.get('prompt_class')}")
    lines.extend(
        [
            "",
            "## Phase Boundary",
            "",
            "- This phase defines strategy selection rules only.",
            "- It does not build an index, retrieve chunks, connect retrieval to chat, implement artifact paging, or claim raw 1M-token prompt support.",
            "- Phase 216 safety governance and Phase 217 index prototype gates must pass before retrieval-backed chat work proceeds.",
        ]
    )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_retrieval_first_context_strategy_design(config: RetrievalFirstContextStrategyDesignConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
