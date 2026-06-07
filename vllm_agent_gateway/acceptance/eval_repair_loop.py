"""Eval-driven repair recommendations from failed validation artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.failure_taxonomy import FailureCategory
from vllm_agent_gateway.acceptance.recursive_blind_testing import (
    REQUIRED_SCORE_DIMENSIONS,
    object_list,
    string_list,
    unresolved_high_findings,
)


SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("runtime-state") / "eval-repair-loop"
MAX_REPAIR_CYCLES_PER_ISSUE = 2
RECURSIVE_ACCEPTANCE_MINIMUM = 85
RECURSIVE_CATEGORY_FLOOR = 70
UNKNOWN_TARGET_PROMPT = "unknown_prompt_case"
HOLDOUT_REQUIRED_AFTER_ACCEPTANCE = "holdout_required_after_current_phase_repair"


class EvalRepairLoopStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class EvalRepairCategory(str, Enum):
    ROUTE_RULE = "route_rule"
    SKILL_METADATA = "skill_metadata"
    TOOL_AVAILABILITY = "tool_availability"
    PROMPT_AMBIGUITY = "prompt_ambiguity"
    MODEL_QUALITY = "model_quality"
    DOCS_SETUP_ISSUE = "docs_setup_issue"
    UNSUPPORTED_SCOPE = "unsupported_scope"


class RepairTargetSurface(str, Enum):
    WORKFLOW_ROUTER = "workflow_router"
    SKILL_REGISTRY = "skill_registry"
    TOOL_CATALOG = "tool_catalog"
    CHAT_CONTRACT = "chat_contract"
    PROMPT_CATALOG = "prompt_catalog"
    MODEL_PROFILE = "model_profile"
    DOCS_SETUP = "docs_setup"
    ROADMAP_BACKLOG = "roadmap_backlog"


class RepairResultStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    REGRESSED = "regressed"
    NOT_RUN_ADVISORY = "not_run_advisory"
    NOT_RUN_REQUIRED = "not_run_required"


@dataclass(frozen=True)
class EvalRepairLoopConfig:
    config_root: Path
    failure_taxonomy_report_paths: tuple[Path, ...] = ()
    recursive_report_paths: tuple[Path, ...] = ()
    target_prompt_case_id: str = ""
    holdout_prompt_case_id: str = ""
    output_path: Path | None = None
    markdown_output_path: Path | None = None


REPAIR_CATEGORY_BY_FAILURE_CATEGORY: dict[str, EvalRepairCategory] = {
    FailureCategory.ROUTING_MISS.value: EvalRepairCategory.ROUTE_RULE,
    FailureCategory.SEMANTIC_MISS.value: EvalRepairCategory.SKILL_METADATA,
    FailureCategory.OUTPUT_CONTRACT_MISS.value: EvalRepairCategory.SKILL_METADATA,
    FailureCategory.EVIDENCE_MISS.value: EvalRepairCategory.SKILL_METADATA,
    FailureCategory.PROMPT_AMBIGUITY.value: EvalRepairCategory.PROMPT_AMBIGUITY,
    FailureCategory.ANYTHINGLLM_CONFIG_ERROR.value: EvalRepairCategory.DOCS_SETUP_ISSUE,
    FailureCategory.MODEL_TIMEOUT.value: EvalRepairCategory.MODEL_QUALITY,
    FailureCategory.MODEL_QUALITY.value: EvalRepairCategory.MODEL_QUALITY,
    FailureCategory.HARNESS_ERROR.value: EvalRepairCategory.DOCS_SETUP_ISSUE,
    FailureCategory.APPROVAL_BOUNDARY_MISS.value: EvalRepairCategory.UNSUPPORTED_SCOPE,
    FailureCategory.UNKNOWN.value: EvalRepairCategory.UNSUPPORTED_SCOPE,
}

REPAIR_CATEGORY_BY_RECURSIVE_CATEGORY: dict[str, EvalRepairCategory] = {
    "routing_miss": EvalRepairCategory.ROUTE_RULE,
    "answer_quality_miss": EvalRepairCategory.SKILL_METADATA,
    "setup_issue": EvalRepairCategory.DOCS_SETUP_ISSUE,
    "unsafe_behavior": EvalRepairCategory.UNSUPPORTED_SCOPE,
    "missing_capability": EvalRepairCategory.UNSUPPORTED_SCOPE,
    "roadmap_drift": EvalRepairCategory.UNSUPPORTED_SCOPE,
    "docs_usability": EvalRepairCategory.DOCS_SETUP_ISSUE,
    "output_contract_miss": EvalRepairCategory.SKILL_METADATA,
    "prompt_ambiguity": EvalRepairCategory.PROMPT_AMBIGUITY,
    "overfitting_risk": EvalRepairCategory.PROMPT_AMBIGUITY,
    "rejected_non_product_request": EvalRepairCategory.UNSUPPORTED_SCOPE,
    "unknown": EvalRepairCategory.UNSUPPORTED_SCOPE,
}

TARGET_SURFACE_BY_REPAIR_CATEGORY: dict[EvalRepairCategory, RepairTargetSurface] = {
    EvalRepairCategory.ROUTE_RULE: RepairTargetSurface.WORKFLOW_ROUTER,
    EvalRepairCategory.SKILL_METADATA: RepairTargetSurface.SKILL_REGISTRY,
    EvalRepairCategory.TOOL_AVAILABILITY: RepairTargetSurface.TOOL_CATALOG,
    EvalRepairCategory.PROMPT_AMBIGUITY: RepairTargetSurface.PROMPT_CATALOG,
    EvalRepairCategory.MODEL_QUALITY: RepairTargetSurface.MODEL_PROFILE,
    EvalRepairCategory.DOCS_SETUP_ISSUE: RepairTargetSurface.DOCS_SETUP,
    EvalRepairCategory.UNSUPPORTED_SCOPE: RepairTargetSurface.ROADMAP_BACKLOG,
}

TARGET_ARTIFACTS_BY_REPAIR_CATEGORY: dict[EvalRepairCategory, list[str]] = {
    EvalRepairCategory.ROUTE_RULE: [
        "vllm_agent_gateway/controllers/workflow_router/plan.py",
        "runtime/prompt_catalogs/",
        "route-decision.json",
    ],
    EvalRepairCategory.SKILL_METADATA: [
        "runtime/skills.json",
        "runtime/skill_evals.json",
        "vllm_agent_gateway/skills/registry.py",
    ],
    EvalRepairCategory.TOOL_AVAILABILITY: [
        "runtime/tools.json",
        "runtime/workflows.json",
        "runtime/roles.json",
    ],
    EvalRepairCategory.PROMPT_AMBIGUITY: [
        "runtime/prompt_catalogs/",
        "README.getting-started.md",
        "docs/examples/",
    ],
    EvalRepairCategory.MODEL_QUALITY: [
        "runtime/model_capability_routing.json",
        "runtime-state/model-capability-profiles/",
        "runtime-state/model-portability/",
    ],
    EvalRepairCategory.DOCS_SETUP_ISSUE: [
        "README.getting-started.md",
        "README.productized-setup.md",
        "scripts/run_productized_setup.py",
    ],
    EvalRepairCategory.UNSUPPORTED_SCOPE: [
        "docs/ACTIONABLE_WORKFLOW_ROADMAP.md",
        "runtime/prompt_skill_coverage.json",
        "docs/NATURAL_LANGUAGE_CAPABILITY_GAP_BACKLOG.md",
    ],
}

VALIDATION_COMMAND_BY_REPAIR_CATEGORY: dict[EvalRepairCategory, str] = {
    EvalRepairCategory.ROUTE_RULE: "python scripts/validate_founder_field_prompt_matrix.py",
    EvalRepairCategory.SKILL_METADATA: "python scripts/validate_skill_evals.py --live-target metadata",
    EvalRepairCategory.TOOL_AVAILABILITY: (
        "python -m pytest tests/regression/test_tool_catalog.py tests/regression/test_tool_mediator.py -q"
    ),
    EvalRepairCategory.PROMPT_AMBIGUITY: "python scripts/validate_founder_field_prompt_matrix.py",
    EvalRepairCategory.MODEL_QUALITY: (
        "python scripts/generate_model_capability_profile.py "
        "--portability-report-path runtime-state/model-portability/phase100-current-skip-live.json"
    ),
    EvalRepairCategory.DOCS_SETUP_ISSUE: "python scripts/run_productized_setup.py validate",
    EvalRepairCategory.UNSUPPORTED_SCOPE: "python scripts/validate_capability_gap_backlog.py",
}

RECOMMENDATION_BY_REPAIR_CATEGORY: dict[EvalRepairCategory, str] = {
    EvalRepairCategory.ROUTE_RULE: (
        "Inspect the route-decision evidence and adjust the narrowest workflow-router rule or prompt catalog "
        "expectation that explains the mismatch."
    ),
    EvalRepairCategory.SKILL_METADATA: (
        "Inspect the selected/rejected skill evidence and repair the smallest registry, eval, artifact, or "
        "chat-rendering metadata mismatch."
    ),
    EvalRepairCategory.TOOL_AVAILABILITY: (
        "Inspect tool candidate rejection and repair the catalog, role, or workflow tool allowlist before changing "
        "prompt wording."
    ),
    EvalRepairCategory.PROMPT_AMBIGUITY: (
        "Record the ambiguity, refine the governed prompt case, and retest the refined prompt before changing "
        "router behavior."
    ),
    EvalRepairCategory.MODEL_QUALITY: (
        "Keep routing unchanged until the model output, schema status, latency, and capability profile evidence are "
        "inspected."
    ),
    EvalRepairCategory.DOCS_SETUP_ISSUE: (
        "Fix setup, AnythingLLM, workspace, port, root, or tester documentation before changing workflow behavior."
    ),
    EvalRepairCategory.UNSUPPORTED_SCOPE: (
        "Keep the request blocked or deferred and update the governed capability backlog or roadmap rather than "
        "adding unapproved runtime behavior."
    ),
}

TOOL_TERMS = (
    "allowed_tools",
    "tool candidate",
    "tool catalog",
    "required tool",
    "missing tool",
    "blocked tool",
    "tool availability",
    "tool allowlist",
)
SKILL_TERMS = ("skill", "route key", "registry", "eval case", "skill_evals", "skill metadata")
MODEL_TERMS = (
    "model output",
    "model route output",
    "invalid_model_route",
    "not valid json",
    "schema",
    "timeout",
    "latency",
    "malformed",
    "capability profile",
)
DOCS_SETUP_TERMS = ("setup", "doctor", "anythingllm", "workspace", "api key", "port", "localhost", "docs")
UNSUPPORTED_TERMS = ("unsupported", "defer", "deferred", "roadmap", "missing capability", "out of scope")
FIXTURE_MUTATION_TERMS = (
    "fixture mutation",
    "protected fixture",
    "source_changed: true",
    '"source_changed": true',
    "source_changed': true",
    "source_tree_changed: true",
    '"source_tree_changed": true',
    "source_tree_changed': true",
    "changed protected fixture",
    "fixture state changed",
)
STRUCTURED_FIXTURE_MUTATION_KEYS = {
    "fixture_mutation",
    "protected_fixture_changed",
    "source_changed",
    "source_tree_changed",
}
HOLDOUT_REGRESSION_TERMS = ("holdout regressed", "holdout regression", "holdout case regresses")
STRUCTURED_HOLDOUT_REGRESSION_KEYS = {
    "holdout_regressed",
    "holdout_regression",
}
STRUCTURED_HOLDOUT_STATUS_KEYS = {
    "holdout_result_status",
    "holdout_status",
}
OUTPUT_CONTRACT_TARGET_ARTIFACTS = [
    "vllm_agent_gateway/controller_service/server.py",
    "tests/regression/test_chat_response_contract.py",
    "scripts/run_founder_field_prompt_eval.py",
]
OUTPUT_CONTRACT_VALIDATION_COMMAND = (
    "python -m pytest tests/regression/test_chat_response_contract.py "
    "tests/regression/test_controller_service.py -q"
)
OUTPUT_CONTRACT_RECOMMENDATION = (
    "Inspect FormatA/JSON chat contract rendering, required marker extraction, and the selected workflow artifact "
    "renderer before changing skill metadata."
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eval-repair-loop-{utc_timestamp()}.json"


def markdown_path_for(path: Path) -> Path:
    return path.with_suffix(".md")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def bounded_text(value: object, *, limit: int = 1200) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 32] + "...[truncated]"


def combined_text(*values: object) -> str:
    return "\n".join(bounded_text(value) for value in values if value not in (None, "", [], {}))


def has_any_term(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def has_structured_fixture_mutation_signal(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in STRUCTURED_FIXTURE_MUTATION_KEYS and item is True:
                return True
            if has_structured_fixture_mutation_signal(item):
                return True
    if isinstance(value, list):
        return any(has_structured_fixture_mutation_signal(item) for item in value)
    return False


def has_fixture_mutation_signal(*values: object) -> bool:
    return has_any_term(combined_text(*values), FIXTURE_MUTATION_TERMS) or any(
        has_structured_fixture_mutation_signal(value) for value in values
    )


def has_structured_holdout_regression_signal(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in STRUCTURED_HOLDOUT_REGRESSION_KEYS and item is True:
                return True
            if key_text in STRUCTURED_HOLDOUT_STATUS_KEYS and str(item).lower() in {
                RepairResultStatus.FAILED.value,
                RepairResultStatus.REGRESSED.value,
                "regression",
            }:
                return True
            if has_structured_holdout_regression_signal(item):
                return True
    if isinstance(value, list):
        return any(has_structured_holdout_regression_signal(item) for item in value)
    return False


def has_holdout_regression_signal(*values: object) -> bool:
    return has_any_term(combined_text(*values), HOLDOUT_REGRESSION_TERMS) or any(
        has_structured_holdout_regression_signal(value) for value in values
    )


def extract_case_id(source: object, evidence: object, fallback: str) -> str:
    source_text = str(source or "")
    match = re.search(r"cases\[([^\]]+)\]", source_text)
    if match:
        return match.group(1)
    if isinstance(evidence, dict):
        for key in ("case_id", "target_prompt_case_id", "prompt_case_id"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback or UNKNOWN_TARGET_PROMPT


def target_rerun_command(case_id: str) -> str:
    if case_id == UNKNOWN_TARGET_PROMPT:
        return "python scripts/run_founder_field_prompt_eval.py --case-id <target_prompt_case_id>"
    return f"python scripts/run_founder_field_prompt_eval.py --case-id {case_id}"


def holdout_rerun_command(case_id: str) -> str:
    if case_id == HOLDOUT_REQUIRED_AFTER_ACCEPTANCE:
        return "python scripts/run_founder_field_prompt_eval.py --case-id <holdout_prompt_case_id>"
    return f"python scripts/run_founder_field_prompt_eval.py --case-id {case_id}"


def classify_repair_category(source_category: str, text: str) -> EvalRepairCategory:
    if has_any_term(text, TOOL_TERMS):
        return EvalRepairCategory.TOOL_AVAILABILITY
    if source_category == FailureCategory.ROUTING_MISS.value:
        return EvalRepairCategory.ROUTE_RULE
    if source_category in REPAIR_CATEGORY_BY_FAILURE_CATEGORY:
        category = REPAIR_CATEGORY_BY_FAILURE_CATEGORY[source_category]
    else:
        category = REPAIR_CATEGORY_BY_RECURSIVE_CATEGORY.get(source_category, EvalRepairCategory.UNSUPPORTED_SCOPE)
    if category == EvalRepairCategory.UNSUPPORTED_SCOPE:
        if has_any_term(text, UNSUPPORTED_TERMS):
            return EvalRepairCategory.UNSUPPORTED_SCOPE
        if has_any_term(text, SKILL_TERMS):
            return EvalRepairCategory.SKILL_METADATA
        if has_any_term(text, MODEL_TERMS):
            return EvalRepairCategory.MODEL_QUALITY
        if has_any_term(text, DOCS_SETUP_TERMS):
            return EvalRepairCategory.DOCS_SETUP_ISSUE
        if "prompt" in text.lower() or "ambiguous" in text.lower():
            return EvalRepairCategory.PROMPT_AMBIGUITY
    if source_category in {"answer_quality_miss", FailureCategory.SEMANTIC_MISS.value}:
        if has_any_term(text, MODEL_TERMS):
            return EvalRepairCategory.MODEL_QUALITY
        if has_any_term(text, SKILL_TERMS):
            return EvalRepairCategory.SKILL_METADATA
    if source_category in {"setup_issue", FailureCategory.HARNESS_ERROR.value} and has_any_term(text, MODEL_TERMS):
        return EvalRepairCategory.MODEL_QUALITY
    if has_any_term(text, UNSUPPORTED_TERMS):
        return EvalRepairCategory.UNSUPPORTED_SCOPE
    return category


def recommendation_id(source_kind: str, source_label: str, source_id: str, index: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{source_kind}-{source_label}-{source_id or index}").strip("-")
    return safe[:140] or f"repair-{index}"


def evidence_refs_for(
    *,
    report_path: Path,
    source: object,
    finding: dict[str, Any],
) -> list[str]:
    refs = string_list(finding.get("evidence_refs"))
    if source:
        refs.append(f"{report_path}:{source}")
    else:
        refs.append(str(report_path))
    evidence = finding.get("evidence")
    if isinstance(evidence, dict):
        for key in ("route_decision_path", "artifact_path", "report_path", "markdown_report_path"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                refs.append(value.strip())
    return sorted(set(refs))


def target_surface_for(category: EvalRepairCategory, source_category: str) -> RepairTargetSurface:
    if source_category == FailureCategory.OUTPUT_CONTRACT_MISS.value:
        return RepairTargetSurface.CHAT_CONTRACT
    return TARGET_SURFACE_BY_REPAIR_CATEGORY[category]


def target_artifacts_for(category: EvalRepairCategory, source_category: str, evidence: dict[str, Any] | None) -> list[str]:
    if source_category != FailureCategory.OUTPUT_CONTRACT_MISS.value:
        return TARGET_ARTIFACTS_BY_REPAIR_CATEGORY[category]
    artifacts = list(OUTPUT_CONTRACT_TARGET_ARTIFACTS)
    expected_workflow = str((evidence or {}).get("expected_workflow") or "")
    if expected_workflow == "code_investigation.plan":
        artifacts.append("vllm_agent_gateway/controllers/code_investigation/plan.py")
    elif expected_workflow == "execution_planning.plan":
        artifacts.append("vllm_agent_gateway/controllers/execution_planning/workflow.py")
    elif expected_workflow == "workflow_router.plan":
        artifacts.append("vllm_agent_gateway/controllers/workflow_router/plan.py")
    return artifacts


def recommendation_for(category: EvalRepairCategory, source_category: str) -> str:
    if source_category == FailureCategory.OUTPUT_CONTRACT_MISS.value:
        return OUTPUT_CONTRACT_RECOMMENDATION
    return RECOMMENDATION_BY_REPAIR_CATEGORY[category]


def validation_command_for(category: EvalRepairCategory, source_category: str) -> str:
    if source_category == FailureCategory.OUTPUT_CONTRACT_MISS.value:
        return OUTPUT_CONTRACT_VALIDATION_COMMAND
    return VALIDATION_COMMAND_BY_REPAIR_CATEGORY[category]


def build_recommendation(
    *,
    source_kind: str,
    source_label: str,
    report_path: Path,
    source_id: str,
    source: str,
    source_category: str,
    severity: str,
    message: object,
    evidence: dict[str, Any] | None,
    index: int,
    target_prompt_case_id: str,
    holdout_prompt_case_id: str,
    repair_cycle_count: int = 0,
    advisory_only: bool = True,
    current_phase_tightening: bool = False,
    accepted_repair_status: str = "proposed_advisory",
    target_result_status: str = RepairResultStatus.NOT_RUN_ADVISORY.value,
    holdout_result_status: str = RepairResultStatus.NOT_RUN_ADVISORY.value,
) -> dict[str, Any]:
    text = combined_text(source_category, message, evidence or {})
    category = classify_repair_category(source_category, text)
    target_case = extract_case_id(source, evidence or {}, target_prompt_case_id)
    holdout_case = holdout_prompt_case_id or HOLDOUT_REQUIRED_AFTER_ACCEPTANCE
    target_surface = target_surface_for(category, source_category)
    evidence_refs = []
    if isinstance(evidence, dict):
        evidence_refs.extend(string_list(evidence.get("evidence_refs")))
        evidence_refs.extend(string_list(evidence.get("validation_refs")))
    return {
        "id": recommendation_id(source_kind, source_label, source_id, index),
        "source_kind": source_kind,
        "source_label": source_label,
        "source_report_path": str(report_path),
        "source_id": source_id,
        "source": source,
        "source_category": source_category,
        "failure_category": category.value,
        "severity": severity or "medium",
        "message": bounded_text(message),
        "evidence_refs": evidence_refs_for(
            report_path=report_path,
            source=source,
            finding={"evidence_refs": evidence_refs, "evidence": evidence or {}},
        ),
        "target_surface": target_surface.value,
        "target_file_or_artifact": target_artifacts_for(category, source_category, evidence),
        "minimal_repair_recommendation": recommendation_for(category, source_category),
        "validation_command": validation_command_for(category, source_category),
        "target_prompt_case_id": target_case,
        "target_rerun_command": target_rerun_command(target_case),
        "holdout_prompt_case_id": holdout_case,
        "holdout_rerun_command": holdout_rerun_command(holdout_case),
        "repair_cycle_count": repair_cycle_count,
        "advisory_only": advisory_only,
        "current_phase_tightening": current_phase_tightening,
        "fixture_mutation_guard": True,
        "accepted_repair_status": accepted_repair_status,
        "target_result_status": target_result_status,
        "holdout_result_status": holdout_result_status,
    }


def taxonomy_recommendations(
    report: dict[str, Any],
    *,
    report_path: Path,
    target_prompt_case_id: str,
    holdout_prompt_case_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if report.get("kind") != "failure_taxonomy_report":
        return [], [f"{report_path} kind must be failure_taxonomy_report"]
    recommendations: list[dict[str, Any]] = []
    blocking_errors: list[str] = []
    findings = object_list(report.get("findings"))
    for index, finding in enumerate(findings):
        category = str(finding.get("category") or FailureCategory.UNKNOWN.value)
        source = str(finding.get("source") or "")
        message = finding.get("message") or finding
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        if category == FailureCategory.FIXTURE_MUTATION.value or has_fixture_mutation_signal(message, evidence):
            blocking_errors.append(f"{report_path}:{source or index} detected protected fixture mutation")
            continue
        recommendations.append(
            build_recommendation(
                source_kind="failure_taxonomy",
                source_label=str(finding.get("report_label") or report_path.stem),
                report_path=report_path,
                source_id=str(finding.get("source") or index),
                source=source,
                source_category=category,
                severity=str(finding.get("severity") or "medium"),
                message=message,
                evidence=evidence,
                index=index,
                target_prompt_case_id=target_prompt_case_id,
                holdout_prompt_case_id=holdout_prompt_case_id,
            )
        )
    if report.get("status") != "passed":
        blocking_errors.append(f"{report_path} failure taxonomy report status is {report.get('status')}")
    return recommendations, blocking_errors


def recursive_finding_text(finding: dict[str, Any]) -> str:
    return combined_text(
        finding.get("summary"),
        finding.get("message"),
        finding.get("action"),
        finding.get("rejection_reason"),
        finding.get("evidence"),
        finding.get("evidence_refs"),
        finding.get("validation_refs"),
    )


def accepted_repair_status(finding: dict[str, Any], *, current_phase_tightening: bool) -> str:
    explicit = finding.get("accepted_repair_status")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    action = str(finding.get("action") or "").lower()
    if current_phase_tightening:
        return "accepted_current_phase"
    if "future" in action or "phase " in action or "phase-" in action or "defer" in action:
        return "accepted_future_scope"
    return "accepted_advisory"


def recursive_recommendations(
    report: dict[str, Any],
    *,
    report_path: Path,
    target_prompt_case_id: str,
    holdout_prompt_case_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if report.get("kind") != "recursive_blind_testing_report":
        return [], [f"{report_path} kind must be recursive_blind_testing_report"]
    recommendations: list[dict[str, Any]] = []
    blocking_errors: list[str] = []
    rounds = object_list(report.get("rounds"))
    accepted_by_id: dict[str, list[dict[str, Any]]] = {}
    rejected_ids: set[str] = set()
    blind_findings: list[tuple[int, dict[str, Any]]] = []
    for round_index, round_item in enumerate(rounds):
        for finding in object_list(round_item.get("blind_findings")):
            source_id = str(finding.get("id") or f"round-{round_index}-blind-{len(blind_findings)}")
            blind_findings.append((round_index, {**finding, "id": source_id}))
        for finding in object_list(round_item.get("accepted_findings")):
            source_id = str(finding.get("id") or f"round-{round_index}-accepted")
            accepted_by_id.setdefault(source_id, []).append({**finding, "id": source_id})
        for finding in object_list(round_item.get("rejected_findings")):
            source_id = str(finding.get("id") or "")
            if source_id:
                rejected_ids.add(source_id)
    for source_id, findings in accepted_by_id.items():
        if len(findings) > MAX_REPAIR_CYCLES_PER_ISSUE:
            blocking_errors.append(
                f"{report_path}:{source_id} exceeds max repair cycles {MAX_REPAIR_CYCLES_PER_ISSUE}"
            )
    for source_id in unresolved_high_findings(report):
        blocking_errors.append(f"{report_path}:{source_id} has unresolved critical/high blind finding")
    convergence = report.get("convergence") if isinstance(report.get("convergence"), dict) else {}
    if convergence.get("status") == "round_limit_exhausted":
        blocking_errors.append(f"{report_path} ended with round_limit_exhausted")
    score_summary = report.get("score_summary") if isinstance(report.get("score_summary"), dict) else {}
    total_score = score_summary.get("total_score")
    if isinstance(total_score, int) and total_score < RECURSIVE_ACCEPTANCE_MINIMUM:
        blocking_errors.append(f"{report_path} score_summary.total_score is below {RECURSIVE_ACCEPTANCE_MINIMUM}")
    category_scores = score_summary.get("category_scores") if isinstance(score_summary.get("category_scores"), dict) else {}
    for score_id in REQUIRED_SCORE_DIMENSIONS:
        value = category_scores.get(score_id)
        if isinstance(value, int) and value < RECURSIVE_CATEGORY_FLOOR:
            blocking_errors.append(f"{report_path} score_summary.category_scores[{score_id}] is below {RECURSIVE_CATEGORY_FLOOR}")
    for source_id, findings in accepted_by_id.items():
        finding = findings[-1]
        if has_fixture_mutation_signal(recursive_finding_text(finding), finding.get("evidence")):
            blocking_errors.append(f"{report_path}:{source_id} accepted protected fixture mutation finding")
        if has_holdout_regression_signal(recursive_finding_text(finding), finding.get("evidence")):
            blocking_errors.append(f"{report_path}:{source_id} accepted holdout regression finding")
        current_phase_tightening = bool(finding.get("current_phase_tightening"))
        target_status = str(finding.get("target_result_status") or RepairResultStatus.NOT_RUN_ADVISORY.value)
        holdout_status = str(finding.get("holdout_result_status") or RepairResultStatus.NOT_RUN_ADVISORY.value)
        recommendations.append(
            build_recommendation(
                source_kind="recursive_blind_testing",
                source_label=str(report.get("scenario_id") or report_path.stem),
                report_path=report_path,
                source_id=source_id,
                source=f"accepted_findings[{source_id}]",
                source_category=str(finding.get("category") or "unknown"),
                severity=str(finding.get("severity") or "medium"),
                message=recursive_finding_text(finding),
                evidence={"evidence_refs": string_list(finding.get("evidence_refs")), "validation_refs": string_list(finding.get("validation_refs"))},
                index=len(recommendations),
                target_prompt_case_id=str(finding.get("target_prompt_case_id") or target_prompt_case_id),
                holdout_prompt_case_id=str(finding.get("holdout_prompt_case_id") or holdout_prompt_case_id),
                repair_cycle_count=int(finding.get("repair_cycle_count") or len(findings)),
                advisory_only=not current_phase_tightening,
                current_phase_tightening=current_phase_tightening,
                accepted_repair_status=accepted_repair_status(finding, current_phase_tightening=current_phase_tightening),
                target_result_status=target_status,
                holdout_result_status=holdout_status,
            )
        )
    for round_index, finding in blind_findings:
        source_id = str(finding.get("id") or f"round-{round_index}-blind")
        if source_id in accepted_by_id or source_id in rejected_ids:
            continue
        if has_fixture_mutation_signal(recursive_finding_text(finding), finding.get("evidence")):
            blocking_errors.append(f"{report_path}:{source_id} unresolved protected fixture mutation finding")
        if has_holdout_regression_signal(recursive_finding_text(finding), finding.get("evidence")):
            blocking_errors.append(f"{report_path}:{source_id} unresolved holdout regression finding")
        recommendations.append(
            build_recommendation(
                source_kind="recursive_blind_testing",
                source_label=str(report.get("scenario_id") or report_path.stem),
                report_path=report_path,
                source_id=source_id,
                source=f"rounds[{round_index}].blind_findings[{source_id}]",
                source_category=str(finding.get("category") or "unknown"),
                severity=str(finding.get("severity") or "medium"),
                message=recursive_finding_text(finding),
                evidence={"evidence_refs": string_list(finding.get("evidence_refs"))},
                index=len(recommendations),
                target_prompt_case_id=str(finding.get("target_prompt_case_id") or target_prompt_case_id),
                holdout_prompt_case_id=str(finding.get("holdout_prompt_case_id") or holdout_prompt_case_id),
            )
        )
    return recommendations, blocking_errors


def repair_category_counts(recommendations: list[dict[str, Any]]) -> dict[str, int]:
    counts = {category.value: 0 for category in EvalRepairCategory}
    for item in recommendations:
        category = str(item.get("failure_category") or "")
        counts[category] = counts.get(category, 0) + 1
    return counts


def validate_eval_repair_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if report.get("kind") != "eval_repair_loop_report":
        errors.append("kind must be eval_repair_loop_report")
    recommendations = object_list(report.get("recommendations"))
    source_finding_count = report.get("summary", {}).get("source_finding_count") if isinstance(report.get("summary"), dict) else 0
    if isinstance(source_finding_count, int) and source_finding_count > 0 and not recommendations:
        errors.append("failed eval inputs must produce at least one repair recommendation")
    for index, item in enumerate(recommendations):
        prefix = f"recommendations[{item.get('id') or index}]"
        if item.get("failure_category") not in {category.value for category in EvalRepairCategory}:
            errors.append(f"{prefix}.failure_category must be a Phase 104 repair category")
        if not string_list(item.get("evidence_refs")):
            errors.append(f"{prefix}.evidence_refs must be non-empty")
        if not string_list(item.get("target_file_or_artifact")):
            errors.append(f"{prefix}.target_file_or_artifact must be non-empty")
        if not isinstance(item.get("minimal_repair_recommendation"), str) or not str(
            item.get("minimal_repair_recommendation")
        ).strip():
            errors.append(f"{prefix}.minimal_repair_recommendation must be non-empty")
        if not isinstance(item.get("validation_command"), str) or not str(item.get("validation_command")).strip():
            errors.append(f"{prefix}.validation_command must be non-empty")
        repair_cycle_count = item.get("repair_cycle_count")
        if not isinstance(repair_cycle_count, int) or repair_cycle_count < 0:
            errors.append(f"{prefix}.repair_cycle_count must be a non-negative integer")
        elif repair_cycle_count > MAX_REPAIR_CYCLES_PER_ISSUE:
            errors.append(f"{prefix}.repair_cycle_count exceeds {MAX_REPAIR_CYCLES_PER_ISSUE}")
        current_phase = item.get("current_phase_tightening") is True
        if current_phase:
            if item.get("target_prompt_case_id") in (None, "", UNKNOWN_TARGET_PROMPT):
                errors.append(f"{prefix}.target_prompt_case_id is required for current-phase repairs")
            if item.get("holdout_prompt_case_id") in (None, "", HOLDOUT_REQUIRED_AFTER_ACCEPTANCE):
                errors.append(f"{prefix}.holdout_prompt_case_id is required for current-phase repairs")
            if not isinstance(item.get("target_rerun_command"), str) or "<target_prompt_case_id>" in str(
                item.get("target_rerun_command")
            ):
                errors.append(f"{prefix}.target_rerun_command must be concrete for current-phase repairs")
            if not isinstance(item.get("holdout_rerun_command"), str) or "<holdout_prompt_case_id>" in str(
                item.get("holdout_rerun_command")
            ):
                errors.append(f"{prefix}.holdout_rerun_command must be concrete for current-phase repairs")
            if str(item.get("target_result_status") or "").lower() != RepairResultStatus.PASSED.value:
                errors.append(f"{prefix}.target_result_status must be passed for current-phase repairs")
            if str(item.get("holdout_result_status") or "").lower() != RepairResultStatus.PASSED.value:
                errors.append(f"{prefix}.holdout_result_status must be passed for current-phase repairs")
        elif item.get("advisory_only") is not True:
            errors.append(f"{prefix}.advisory_only must be true unless current_phase_tightening is true")
        if item.get("fixture_mutation_guard") is not True:
            errors.append(f"{prefix}.fixture_mutation_guard must be true")
    for error in string_list(report.get("blocking_errors")):
        errors.append(error)
    return errors


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Eval Repair Loop Report",
        "",
        f"- Status: {report['status']}",
        f"- Created at: {report['created_at']}",
        f"- Source report count: {len(report['input_reports'])}",
        f"- Source finding count: {report['summary']['source_finding_count']}",
        f"- Recommendation count: {report['summary']['recommendation_count']}",
        f"- Blocking errors: {len(report['blocking_errors'])}",
        "",
        "## Category Counts",
        "",
        "| Repair category | Count |",
        "| --- | ---: |",
    ]
    counts = report["summary"]["repair_category_counts"]
    for category, count in counts.items():
        if count:
            lines.append(f"| {category} | {count} |")
    if not any(counts.values()):
        lines.append("| none | 0 |")
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "| Category | Severity | Source | Target | Recommendation | Validation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["recommendations"]:
        lines.append(
            "| {category} | {severity} | {source} | {target} | {recommendation} | {validation} |".format(
                category=item["failure_category"],
                severity=item["severity"],
                source=str(item["source"])[:160].replace("\n", " "),
                target=", ".join(item["target_file_or_artifact"])[:220],
                recommendation=str(item["minimal_repair_recommendation"])[:260].replace("\n", " "),
                validation=str(item["validation_command"])[:180].replace("\n", " "),
            )
        )
    if not report["recommendations"]:
        lines.append("| none | none | none | none | No repair recommendations were generated. | none |")
    if report["blocking_errors"]:
        lines.extend(["", "## Blocking Errors", ""])
        for error in report["blocking_errors"]:
            lines.append(f"- {error}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval_repair_loop(config: EvalRepairLoopConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    markdown_path = config.markdown_output_path or markdown_path_for(output_path)
    recommendations: list[dict[str, Any]] = []
    blocking_errors: list[str] = []
    input_reports: list[dict[str, Any]] = []
    source_finding_count = 0
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eval_repair_loop_report",
        "status": EvalRepairLoopStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "input_reports": input_reports,
        "summary": {},
        "recommendations": recommendations,
        "blocking_errors": blocking_errors,
        "validation_errors": [],
        "markdown_report_path": str(markdown_path),
    }
    try:
        if not config.failure_taxonomy_report_paths and not config.recursive_report_paths:
            raise RuntimeError("at least one failure taxonomy or recursive blind-testing report is required")
        for path in config.failure_taxonomy_report_paths:
            resolved = path.resolve()
            loaded = read_json_object(resolved)
            findings = object_list(loaded.get("findings"))
            source_finding_count += len(findings)
            input_reports.append(
                {
                    "kind": loaded.get("kind"),
                    "path": str(resolved),
                    "status": loaded.get("status"),
                    "finding_count": len(findings),
                }
            )
            items, errors = taxonomy_recommendations(
                loaded,
                report_path=resolved,
                target_prompt_case_id=config.target_prompt_case_id,
                holdout_prompt_case_id=config.holdout_prompt_case_id,
            )
            recommendations.extend(items)
            blocking_errors.extend(errors)
        for path in config.recursive_report_paths:
            resolved = path.resolve()
            loaded = read_json_object(resolved)
            rounds = object_list(loaded.get("rounds"))
            finding_count = sum(len(object_list(item.get("blind_findings"))) for item in rounds)
            source_finding_count += finding_count
            input_reports.append(
                {
                    "kind": loaded.get("kind"),
                    "path": str(resolved),
                    "status": loaded.get("status"),
                    "finding_count": finding_count,
                    "scenario_id": loaded.get("scenario_id"),
                }
            )
            items, errors = recursive_recommendations(
                loaded,
                report_path=resolved,
                target_prompt_case_id=config.target_prompt_case_id,
                holdout_prompt_case_id=config.holdout_prompt_case_id,
            )
            recommendations.extend(items)
            blocking_errors.extend(errors)
    except Exception as exc:  # noqa: BLE001
        blocking_errors.append(f"{type(exc).__name__}: {exc}")
    report["summary"] = {
        "source_finding_count": source_finding_count,
        "recommendation_count": len(recommendations),
        "repair_category_counts": repair_category_counts(recommendations),
        "advisory_recommendation_count": sum(1 for item in recommendations if item.get("advisory_only") is True),
        "current_phase_tightening_count": sum(1 for item in recommendations if item.get("current_phase_tightening") is True),
        "max_repair_cycles_per_issue": MAX_REPAIR_CYCLES_PER_ISSUE,
        "holdout_required_for_current_phase_repairs": True,
        "fixture_mutation_guard": True,
    }
    validation_errors = validate_eval_repair_report(report)
    report["validation_errors"] = validation_errors
    report["status"] = EvalRepairLoopStatus.PASSED.value if not validation_errors else EvalRepairLoopStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_markdown(markdown_path, report)
    return report
