"""Phase 319 context strategy router rebaseline gate."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    dict_value,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.context_strategy_router import (
    ContextStrategyRouterConfig,
    run_context_strategy_router,
)
from vllm_agent_gateway.controllers.large_context.context_strategy import (
    select_context_strategy,
)
from vllm_agent_gateway.controllers.workflow_router.plan import workflow_kind_for_request


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "context_strategy_router_rebaseline_policy"
EXPECTED_REPORT_KIND = "context_strategy_router_rebaseline_report"
EXPECTED_PHASE = 319
EXPECTED_BACKLOG_ID = "P0-M8-319"
EXPECTED_MILESTONE_IDS = {"M8"}
DEFAULT_POLICY_PATH = Path("runtime") / "context_strategy_router_rebaseline_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase319" / "phase319-context-strategy-router-rebaseline-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "phase319" / "phase319-context-strategy-router-rebaseline-report.md"
)
REQUIRED_STRATEGIES = {
    "direct_context",
    "retrieval",
    "chunked_investigation",
    "summarization",
    "artifact_paging",
    "refusal",
}
REQUIRED_INPUT_SIZE_CLASSES = {"small", "medium", "huge"}
REQUIRED_CASE_KINDS = {
    "small_direct",
    "medium_specific_lookup",
    "huge_raw_context_limit",
    "ambiguous_scope",
    "unsupported_capability",
    "missing_index",
    "stale_index",
    "sensitive_or_secret_request",
    "artifact_paging",
    "chunked_synthesis",
    "summarization",
}
REQUIRED_OUT_OF_SCOPE = {
    "second_large_context_router",
    "raw_500k_prompt_support_claim",
    "new_retrieval_engine",
    "vector_search_replacement",
    "protected_fixture_mutation",
    "stable_corpus_promotion",
    "advanced_refactor_reactivation",
}
REQUIRED_EVIDENCE_FIELDS = {
    "case_id",
    "input_size_class",
    "input_token_estimate",
    "available_context_budget",
    "selected_strategy",
    "rejected_strategies",
    "decision_reason",
    "determinism_key",
    "artifact_count",
    "artifact_sizes",
    "source_coverage_percent",
    "chunks_or_pages_selected",
    "chunks_or_pages_omitted",
    "index_status",
    "index_timestamp_or_version",
    "privacy_classification",
    "sensitive_content_actions",
    "clarification_question_present",
    "refusal_reason",
    "user_visible_limitations",
    "expected_route",
    "actual_route",
    "pass_fail",
    "failure_reason",
    "validator_timestamp",
}


@dataclass(frozen=True)
class ContextStrategyRouterRebaselineConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.35))


def evidence_key(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_strategy": decision.get("selected_strategy"),
        "status": decision.get("status"),
        "execution_path": decision.get("execution_path"),
        "reason": decision.get("reason"),
        "prompt_class": decision.get("prompt_class"),
        "source_freshness_status": decision.get("source_freshness_status"),
        "indexed_corpus_match": decision.get("indexed_corpus_match"),
        "rejected_strategies": decision.get("rejected_strategies"),
    }


def stable_json_hash(value: Any) -> str:
    import hashlib

    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 319"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M8"))
    if set(string_list(policy.get("required_strategy_ids"))) != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.required_strategy_ids", "required_strategy_ids must match the existing router strategies"))
    if set(string_list(policy.get("required_input_size_classes"))) != REQUIRED_INPUT_SIZE_CLASSES:
        errors.append(validation_error("policy.required_input_size_classes", "must cover small, medium, and huge inputs"))
    if set(string_list(policy.get("required_case_kinds"))) != REQUIRED_CASE_KINDS:
        errors.append(validation_error("policy.required_case_kinds", "must cover all Phase 319 case kinds"))
    if set(string_list(policy.get("required_evidence_fields"))) != REQUIRED_EVIDENCE_FIELDS:
        errors.append(validation_error("policy.required_evidence_fields", "evidence fields must match the blind-audit checklist"))
    for key in ("phase220_policy_path", "phase318_report_path", "target_root", "context_index_policy_path"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be non-empty"))
    decision_cases = object_list(policy.get("decision_cases"))
    case_kinds = {str(case.get("kind")) for case in decision_cases}
    if not REQUIRED_CASE_KINDS.issubset(case_kinds):
        errors.append(validation_error("policy.decision_cases", "decision_cases must cover every required case kind"))
    if not REQUIRED_INPUT_SIZE_CLASSES.issubset({str(case.get("input_size_class")) for case in decision_cases}):
        errors.append(validation_error("policy.decision_cases", "decision_cases must cover every input size class"))
    for case in decision_cases:
        case_id = str(case.get("case_id") or "<missing>")
        for key in (
            "case_id",
            "kind",
            "input_size_class",
            "target_root_kind",
            "prompt",
            "expected_strategy",
            "expected_status",
            "expected_execution_path",
            "expected_reason",
        ):
            if not isinstance(case.get(key), str) or not str(case.get(key)).strip():
                errors.append(validation_error(f"policy.case.{key}", f"{case_id} missing {key}"))
        if case.get("expected_strategy") not in REQUIRED_STRATEGIES:
            errors.append(validation_error(f"policy.case.{case_id}.expected_strategy", "unknown strategy"))
    missing = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing:
        errors.append(validation_error("policy.out_of_scope", f"missing boundaries: {missing}"))
    if policy.get("acceptance_marker") != "PHASE319 CONTEXT STRATEGY ROUTER REBASELINE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 319"))
    return errors


def load_optional_report(
    config_root: Path,
    raw_path: object,
    *,
    source: str,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error(f"{source}.missing", f"{source} report is required", source=source)]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error(f"{source}.malformed", f"{source} report is malformed: {exc}", source=source)]


def validate_phase318_report(report: dict[str, Any]) -> list[dict[str, str]]:
    if not report:
        return []
    errors: list[dict[str, str]] = []
    summary = dict_value(report.get("summary"))
    if report.get("status") != "passed":
        errors.append(validation_error("phase318.status", "Phase 318 benchmark report must pass", source="phase318"))
    if summary.get("result_count") != 4:
        errors.append(validation_error("phase318.result_count", "Phase 318 must include four context classes", source="phase318"))
    if summary.get("phase319_ready") is not True:
        errors.append(validation_error("phase318.phase319_ready", "Phase 318 must mark phase319_ready", source="phase318"))
    if summary.get("raw_500k_prompt_support_proven") is not False:
        errors.append(
            validation_error(
                "phase318.raw_500k_prompt_support_proven",
                "Phase 319 must not proceed from a raw 500k support claim",
                source="phase318",
            )
        )
    if summary.get("stable_corpus_mutated") is not False:
        errors.append(validation_error("phase318.stable_corpus_mutated", "stable corpus must remain unchanged", source="phase318"))
    return errors


def target_root_for_case(config_root: Path, policy: dict[str, Any], case: dict[str, Any]) -> Path:
    kind = str(case.get("target_root_kind"))
    if kind == "config_root":
        return config_root
    if kind == "large_corpus":
        return resolve_path(config_root, str(policy.get("target_root"))).resolve()
    raise RuntimeError(f"unsupported target_root_kind: {kind}")


def context_for_case(config_root: Path, policy: dict[str, Any], case: dict[str, Any], output_root: Path) -> dict[str, Any]:
    variant = str(case.get("context_variant") or "fresh")
    context_index_policy_path = resolve_path(config_root, str(policy.get("context_index_policy_path")))
    if variant == "fresh":
        return {"context_index_policy_path": str(context_index_policy_path)}
    if variant == "missing_index":
        return {"context_index_policy_path": str(output_root / "missing-index-policy.json")}
    if variant != "stale_index":
        raise RuntimeError(f"unsupported context variant: {variant}")

    original_policy = read_json_object(context_index_policy_path)
    original_index_path = resolve_path(config_root, str(dict_value(original_policy.get("index_artifact")).get("path")))
    mutated_index = copy.deepcopy(read_json_object(original_index_path))
    chunks = object_list(mutated_index.get("chunks"))
    if chunks:
        chunks[0]["source_sha256"] = "0" * 64
        mutated_index["chunks"] = chunks
    stale_dir = output_root / "stale-index"
    stale_index_path = stale_dir / "stale-context-index.json"
    stale_policy_path = stale_dir / "stale-context-index-policy.json"
    write_json(stale_index_path, mutated_index)
    mutated_policy = copy.deepcopy(original_policy)
    mutated_policy["index_artifact"] = {**dict_value(mutated_policy.get("index_artifact")), "path": str(stale_index_path)}
    write_json(stale_policy_path, mutated_policy)
    return {"context_index_policy_path": str(stale_policy_path)}


def prompt_for_case(case: dict[str, Any], target_root: Path) -> str:
    prompt = str(case.get("prompt") or "").strip()
    if str(case.get("target_root_kind")) == "large_corpus" and str(target_root) not in prompt:
        return f"In {target_root}, {prompt}"
    if prompt.lower().startswith("in "):
        return prompt
    return f"In {target_root}, {prompt}"


def route_evidence_for_prompt(prompt: str) -> tuple[str | None, str, list[dict[str, Any]]]:
    workflow_id, status, evidence = workflow_kind_for_request(prompt)
    return workflow_id, status, evidence


def source_coverage_percent(decision: dict[str, Any]) -> int:
    checked = decision.get("checked_source_count")
    stale = decision.get("stale_source_count")
    if not isinstance(checked, int) or checked <= 0:
        return 0
    if not isinstance(stale, int):
        stale = 0
    return max(0, min(100, round(((checked - stale) / checked) * 100)))


def case_sensitive_actions(case: dict[str, Any], decision: dict[str, Any]) -> list[str]:
    if case.get("kind") != "sensitive_or_secret_request":
        return []
    if decision.get("reason") == "unsafe_evidence_request":
        return ["refuse_raw_sensitive_output", "use_safe_limitations_answer", "do_not_index_or_emit_secret_values"]
    return ["unsafe_sensitive_request_not_refused"]


def route_case(config_root: Path, policy: dict[str, Any], output_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    target_root = target_root_for_case(config_root, policy, case)
    prompt = prompt_for_case(case, target_root)
    request_context = context_for_case(config_root, policy, case, output_root / str(case.get("case_id")))
    selected_workflow, route_status, route_evidence = route_evidence_for_prompt(prompt)
    common = {
        "config_root": config_root,
        "target_root": target_root,
        "user_request": prompt,
        "route_evidence": route_evidence,
        "selected_workflow": selected_workflow,
        "request_context": request_context,
    }
    first = select_context_strategy(**common)
    second = select_context_strategy(**common)
    first_key = evidence_key(first)
    second_key = evidence_key(second)
    deterministic = first_key == second_key
    expected_route = {
        "selected_strategy": case.get("expected_strategy"),
        "status": case.get("expected_status"),
        "execution_path": case.get("expected_execution_path"),
        "reason": case.get("expected_reason"),
    }
    actual_route = {
        "selected_strategy": first.get("selected_strategy"),
        "status": first.get("status"),
        "execution_path": first.get("execution_path"),
        "reason": first.get("reason"),
    }
    errors: list[str] = []
    for key, expected in expected_route.items():
        if actual_route.get(key) != expected:
            errors.append(f"{key}_mismatch")
    if not deterministic:
        errors.append("nondeterministic_replay")
    if case.get("input_size_class") == "huge" and first.get("selected_strategy") == "direct_context":
        errors.append("direct_context_for_huge_request")
    if case.get("kind") in {"missing_index", "stale_index"} and first.get("status") != "blocked":
        errors.append("missing_or_stale_index_not_blocked")
    if case.get("kind") == "sensitive_or_secret_request" and first.get("reason") != "unsafe_evidence_request":
        errors.append("sensitive_or_secret_request_not_refused")
    if first.get("raw_1m_prompt_support_proven") is True:
        errors.append("raw_long_context_support_claimed")

    evidence = {
        "case_id": case.get("case_id"),
        "kind": case.get("kind"),
        "input_size_class": case.get("input_size_class"),
        "input_token_estimate": estimate_tokens(prompt),
        "available_context_budget": first.get("target_input_limit"),
        "selected_strategy": first.get("selected_strategy"),
        "rejected_strategies": first.get("rejected_strategies"),
        "decision_reason": first.get("reason"),
        "determinism_key": stable_json_hash(first_key),
        "artifact_count": 0,
        "artifact_sizes": [],
        "source_coverage_percent": source_coverage_percent(first),
        "chunks_or_pages_selected": [],
        "chunks_or_pages_omitted": [],
        "index_status": first.get("source_freshness_status"),
        "index_timestamp_or_version": stable_json_hash(
            {
                "policy_path": request_context.get("context_index_policy_path"),
                "source_freshness_status": first.get("source_freshness_status"),
                "checked_source_count": first.get("checked_source_count"),
            }
        ),
        "privacy_classification": "sensitive_or_secret_request" if case.get("kind") == "sensitive_or_secret_request" else "not_sensitive",
        "sensitive_content_actions": case_sensitive_actions(case, first),
        "clarification_question_present": first.get("reason") == "ambiguous_large_context_request",
        "refusal_reason": first.get("reason") if first.get("selected_strategy") == "refusal" else "",
        "user_visible_limitations": first.get("safe_alternatives"),
        "expected_route": expected_route,
        "actual_route": actual_route,
        "pass_fail": "pass" if not errors else "fail",
        "failure_reason": ";".join(errors),
        "validator_timestamp": utc_timestamp(),
        "route_status": route_status,
        "selected_workflow": selected_workflow,
        "matched_terms": first.get("matched_terms"),
        "prompt_class": first.get("prompt_class"),
        "deterministic_replay": deterministic,
    }
    missing_fields = REQUIRED_EVIDENCE_FIELDS - set(evidence)
    if missing_fields:
        errors.append("missing_route_evidence_fields")
        evidence["failure_reason"] = ";".join(errors)
        evidence["pass_fail"] = "fail"
    evidence["passed"] = not errors
    return evidence


def validate_case_results(policy: dict[str, Any], case_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for result in case_results:
        if result.get("passed") is not True:
            errors.append(
                validation_error(
                    f"case.{result.get('case_id')}",
                    f"case did not pass: {result.get('failure_reason')}",
                    source="case_result",
                )
            )
        missing = REQUIRED_EVIDENCE_FIELDS - set(result)
        if missing:
            errors.append(
                validation_error(
                    f"case.{result.get('case_id')}.evidence_fields",
                    f"missing evidence fields: {sorted(missing)}",
                    source="case_result",
                )
            )
    covered_strategies = {str(item.get("selected_strategy")) for item in case_results}
    if not REQUIRED_STRATEGIES.issubset(covered_strategies):
        errors.append(validation_error("case_results.strategies", "case results must cover every strategy", source="case_result"))
    covered_sizes = {str(item.get("input_size_class")) for item in case_results}
    if not REQUIRED_INPUT_SIZE_CLASSES.issubset(covered_sizes):
        errors.append(validation_error("case_results.input_sizes", "case results must cover small, medium, and huge", source="case_result"))
    covered_kinds = {str(item.get("kind")) for item in case_results}
    if not set(string_list(policy.get("required_case_kinds"))).issubset(covered_kinds):
        errors.append(validation_error("case_results.kinds", "case results must cover every required kind", source="case_result"))
    return errors


def build_report(config: ContextStrategyRouterRebaselineConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)

    phase318_path, phase318_report, phase318_load_errors = load_optional_report(
        config_root,
        policy.get("phase318_report_path"),
        source="phase318",
        require_artifacts=config.require_artifacts,
    )
    phase318_errors = validate_phase318_report(phase318_report)

    phase220_output_path = output_path.parent / "phase220-rebaseline" / "context-strategy-router-report.json"
    phase220_markdown_path = output_path.parent / "phase220-rebaseline" / "context-strategy-router-report.md"
    phase220_report = run_context_strategy_router(
        ContextStrategyRouterConfig(
            config_root=config_root,
            policy_path=Path(str(policy.get("phase220_policy_path"))),
            output_path=phase220_output_path,
            markdown_output_path=phase220_markdown_path,
            require_artifacts=False,
        )
    )
    phase220_errors = []
    if phase220_report.get("status") != "passed":
        phase220_errors.append(validation_error("phase220.status", "Phase 220 router gate must still pass", source="phase220"))

    output_root = output_path.parent / "case-artifacts"
    case_results = [route_case(config_root, policy, output_root, case) for case in object_list(policy.get("decision_cases"))]
    case_errors = validate_case_results(policy, case_results)
    validation_errors = policy_errors + phase318_load_errors + phase318_errors + phase220_errors + case_errors
    strategy_counts: dict[str, int] = {}
    for item in case_results:
        strategy = str(item.get("selected_strategy"))
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
    status = "passed" if not validation_errors else "failed"
    phase318_summary = dict_value(phase318_report.get("summary"))
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
        "phase318_report_path": str(phase318_path) if phase318_path is not None else None,
        "phase318_report_sha256": sha256_file(phase318_path) if phase318_path is not None and phase318_path.is_file() else None,
        "phase220_rebaseline_report_path": str(phase220_output_path),
        "case_results": case_results,
        "strategy_counts": strategy_counts,
        "validation_errors": validation_errors,
        "summary": {
            "case_count": len(case_results),
            "passed_case_count": len([item for item in case_results if item.get("passed") is True]),
            "failed_case_count": len([item for item in case_results if item.get("passed") is not True]),
            "covered_strategy_count": len(strategy_counts),
            "all_strategies_covered": REQUIRED_STRATEGIES.issubset(set(strategy_counts)),
            "input_size_classes": sorted({str(item.get("input_size_class")) for item in case_results}),
            "phase220_status": phase220_report.get("status"),
            "phase318_status": phase318_report.get("status"),
            "phase318_max_prompt_tokens": phase318_summary.get("max_prompt_tokens"),
            "raw_500k_prompt_support_proven": phase318_summary.get("raw_500k_prompt_support_proven") is True,
            "raw_prompt_stuffing_allowed": False,
            "sensitive_or_secret_request_refused": any(
                item.get("kind") == "sensitive_or_secret_request"
                and item.get("selected_strategy") == "refusal"
                and item.get("decision_reason") == "unsafe_evidence_request"
                for item in case_results
            ),
            "deterministic_replay_passed": all(item.get("deterministic_replay") is True for item in case_results),
            "phase320_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Context Strategy Router Rebaseline",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Cases: `{summary.get('passed_case_count')}/{summary.get('case_count')}`",
        f"- All strategies covered: `{summary.get('all_strategies_covered')}`",
        f"- Input size classes: `{', '.join(string_list(summary.get('input_size_classes')))}`",
        f"- Phase 220 status: `{summary.get('phase220_status')}`",
        f"- Phase 318 status: `{summary.get('phase318_status')}`",
        f"- Raw 500k prompt support proven: `{summary.get('raw_500k_prompt_support_proven')}`",
        f"- Sensitive or secret request refused: `{summary.get('sensitive_or_secret_request_refused')}`",
        f"- Deterministic replay passed: `{summary.get('deterministic_replay_passed')}`",
        f"- Phase 320 ready: `{summary.get('phase320_ready')}`",
        "",
        "## Cases",
    ]
    for item in object_list(report.get("case_results")):
        lines.append(
            f"- `{item.get('case_id')}` `{item.get('kind')}` -> `{item.get('selected_strategy')}` "
            f"status `{dict_value(item.get('actual_route')).get('status')}` reason `{item.get('decision_reason')}` "
            f"passed `{item.get('passed')}`"
        )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_context_strategy_router_rebaseline(config: ContextStrategyRouterRebaselineConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
