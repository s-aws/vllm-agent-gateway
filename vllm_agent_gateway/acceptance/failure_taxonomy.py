"""Failure taxonomy extraction for validation artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.run_artifact_diff import existing_artifact_path, load_json, report_kind


DEFAULT_REPORT_DIR = Path("runtime-state") / "failure-taxonomy"
MAX_MESSAGE_CHARS = 1200


class FailureCategory(str, Enum):
    ROUTING_MISS = "routing_miss"
    SEMANTIC_MISS = "semantic_miss"
    OUTPUT_CONTRACT_MISS = "output_contract_miss"
    EVIDENCE_MISS = "evidence_miss"
    PROMPT_AMBIGUITY = "prompt_ambiguity"
    FIXTURE_MUTATION = "fixture_mutation"
    ANYTHINGLLM_CONFIG_ERROR = "anythingllm_config_error"
    MODEL_TIMEOUT = "model_timeout"
    APPROVAL_BOUNDARY_MISS = "approval_boundary_miss"
    MODEL_QUALITY = "model_quality"
    HARNESS_ERROR = "harness_error"
    UNKNOWN = "unknown"


SEVERITY_BY_CATEGORY: dict[FailureCategory, str] = {
    FailureCategory.FIXTURE_MUTATION: "critical",
    FailureCategory.APPROVAL_BOUNDARY_MISS: "critical",
    FailureCategory.ANYTHINGLLM_CONFIG_ERROR: "high",
    FailureCategory.MODEL_TIMEOUT: "high",
    FailureCategory.ROUTING_MISS: "high",
    FailureCategory.OUTPUT_CONTRACT_MISS: "medium",
    FailureCategory.SEMANTIC_MISS: "medium",
    FailureCategory.EVIDENCE_MISS: "medium",
    FailureCategory.MODEL_QUALITY: "medium",
    FailureCategory.HARNESS_ERROR: "medium",
    FailureCategory.PROMPT_AMBIGUITY: "low",
    FailureCategory.UNKNOWN: "medium",
}


NEXT_ACTION_BY_CATEGORY: dict[FailureCategory, str] = {
    FailureCategory.ROUTING_MISS: "Inspect route-decision artifacts and prompt-matrix expectations before changing prompts.",
    FailureCategory.SEMANTIC_MISS: "Inspect required semantic markers and artifact rendering; fix deterministic evidence extraction when the prompt is clear.",
    FailureCategory.OUTPUT_CONTRACT_MISS: "Inspect FormatA/JSON chat contract rendering and required marker extraction.",
    FailureCategory.EVIDENCE_MISS: "Inspect source refs, related tests, verification commands, and artifact evidence collection.",
    FailureCategory.PROMPT_AMBIGUITY: "Record the refined prompt and retest before changing router behavior.",
    FailureCategory.FIXTURE_MUTATION: "Stop validation, inspect protected fixture diffs, and restore the fixture before more live tests.",
    FailureCategory.ANYTHINGLLM_CONFIG_ERROR: "Check AnythingLLM API key, workspace, target URL, and backend health.",
    FailureCategory.MODEL_TIMEOUT: "Rerun from Bash, inspect latency/body-byte timeouts, and reduce scope before judging model quality.",
    FailureCategory.APPROVAL_BOUNDARY_MISS: "Inspect approval state, continuation run ID, and mutation policy; fail closed before apply work.",
    FailureCategory.MODEL_QUALITY: "Keep harness behavior unchanged until the failed model output and context budget are inspected.",
    FailureCategory.HARNESS_ERROR: "Inspect runtime setup, suite stdout/stderr, and report loading before changing skill or prompt behavior.",
    FailureCategory.UNKNOWN: "Open the referenced artifact and add a narrower taxonomy rule if the pattern repeats.",
}


TERM_RULES: tuple[tuple[FailureCategory, tuple[str, ...]], ...] = (
    (
        FailureCategory.FIXTURE_MUTATION,
        (
            "changed protected fixture state",
            "fixture state",
            "mutated watched",
            "mutated selected frozen",
            "source_changed: true",
            "disposable_copy_changed: true",
            "changed git status",
        ),
    ),
    (
        FailureCategory.APPROVAL_BOUNDARY_MISS,
        (
            "approval",
            "apply-boundary",
            "approval boundary",
            "missing approval",
            "wrong-run continuation",
            "duplicate approval",
            "unsafe mutation policy",
        ),
    ),
    (
        FailureCategory.ANYTHINGLLM_CONFIG_ERROR,
        (
            "anythingllm_api_key",
            "anythingllm preflight failed",
            "workspace",
            "api key",
            "anythingllm returned http",
            "anythingllm",
        ),
    ),
    (
        FailureCategory.MODEL_TIMEOUT,
        (
            "timed out",
            "timeout",
            "body bytes",
            "winerror 10055",
            "read timed out",
        ),
    ),
    (
        FailureCategory.ROUTING_MISS,
        (
            "wrong workflow",
            "selected wrong workflow",
            "expected_workflow",
            "expected workflow",
            "selected_workflow",
            "route miss",
            "routing miss",
            "expected_rule",
            "route rule",
        ),
    ),
    (
        FailureCategory.OUTPUT_CONTRACT_MISS,
        (
            "missing marker",
            "missing_markers",
            "output_contract",
            "format_a",
            "chat-visible",
            "missing format",
        ),
    ),
    (
        FailureCategory.SEMANTIC_MISS,
        (
            "semantic_quality",
            "semantic quality",
            "missing_semantic_markers",
            "forbidden_markers",
            "forbidden answer",
            "semantic miss",
        ),
    ),
    (
        FailureCategory.EVIDENCE_MISS,
        (
            "evidence miss",
            "source refs",
            "related tests",
            "verification command",
            "missing evidence",
        ),
    ),
    (
        FailureCategory.PROMPT_AMBIGUITY,
        (
            "prompt_risk",
            "refined_prompt",
            "suggested_prompt_if_missed",
            "miss_suggestion",
            "ambiguous",
            "prompt ambiguity",
        ),
    ),
    (
        FailureCategory.MODEL_QUALITY,
        (
            "invalid_model_route",
            "model route output",
            "model_router_status",
            "malformed",
            "jsondecodeerror",
            "not valid json",
            "schema",
            "model_quality",
        ),
    ),
    (
        FailureCategory.HARNESS_ERROR,
        (
            "health check failed",
            "connection refused",
            "missing_report_path",
            "failed_to_load",
            "not readable",
            "acceptance suite command failed",
            "http ",
        ),
    ),
)


@dataclass(frozen=True)
class FailureTaxonomyConfig:
    config_root: Path
    report_paths: tuple[Path, ...]
    labels: tuple[str, ...] = ()
    output_path: Path | None = None
    markdown_output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"failure-taxonomy-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bounded_text(value: object, *, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 32] + "...[truncated]"


def classify_text(text: str) -> tuple[FailureCategory, list[str]]:
    lowered = text.lower()
    for category, terms in TERM_RULES:
        matches = [term for term in terms if term in lowered]
        if matches:
            return category, matches
    return FailureCategory.UNKNOWN, []


def finding(
    *,
    report_label: str,
    report_path: Path,
    source: str,
    category: FailureCategory,
    message: object,
    severity: str | None = None,
    evidence: dict[str, Any] | None = None,
    matched_terms: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "report_label": report_label,
        "report_path": str(report_path),
        "source": source,
        "category": category.value,
        "severity": severity or SEVERITY_BY_CATEGORY[category],
        "message": bounded_text(message),
        "matched_terms": matched_terms or [],
        "evidence": evidence or {},
        "recommended_next_action": NEXT_ACTION_BY_CATEGORY[category],
    }


def classify_message_finding(report_label: str, report_path: Path, source: str, message: object) -> dict[str, Any]:
    category, terms = classify_text(str(message))
    return finding(
        report_label=report_label,
        report_path=report_path,
        source=source,
        category=category,
        message=message,
        matched_terms=terms,
    )


def collect_founder_field_findings(report: dict[str, Any], *, report_label: str, report_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    for index, error in enumerate(errors):
        findings.append(classify_message_finding(report_label, report_path, f"errors[{index}]", error))
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or f"case_{index}")
        missing_markers = item.get("missing_markers") if isinstance(item.get("missing_markers"), list) else []
        missing_semantic = (
            item.get("missing_semantic_markers")
            if isinstance(item.get("missing_semantic_markers"), list)
            else []
        )
        forbidden = item.get("forbidden_markers_found") if isinstance(item.get("forbidden_markers_found"), list) else []
        if item.get("output_contract_status") not in (None, "", "passed") or missing_markers:
            markers_text = " ".join(str(marker) for marker in missing_markers)
            category = (
                FailureCategory.ROUTING_MISS
                if "selected_workflow:" in markers_text or "selected_workflow" in markers_text
                else FailureCategory.OUTPUT_CONTRACT_MISS
            )
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"cases[{case_id}].output_contract",
                    category=category,
                    message=item.get("initial_difference") or f"{case_id} output contract failed",
                    evidence={"missing_markers": missing_markers, "expected_workflow": item.get("expected_workflow")},
                )
            )
        if item.get("semantic_quality_status") not in (None, "", "passed") or missing_semantic or forbidden:
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"cases[{case_id}].semantic_quality",
                    category=FailureCategory.SEMANTIC_MISS,
                    message=item.get("initial_difference") or f"{case_id} semantic quality failed",
                    evidence={
                        "missing_semantic_markers": missing_semantic,
                        "forbidden_markers_found": forbidden,
                    },
                )
            )
        if item.get("status") not in (None, "", "passed") and item.get("prompt_risk"):
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"cases[{case_id}].prompt_risk",
                    category=FailureCategory.PROMPT_AMBIGUITY,
                    message=item.get("prompt_risk"),
                    evidence={"refined_prompt": item.get("refined_prompt"), "suggested_prompt": item.get("suggested_prompt_if_missed")},
                )
            )
    before = report.get("fixture_state_before")
    after = report.get("fixture_state_after")
    if isinstance(before, dict) and isinstance(after, dict) and before != after:
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="fixture_state",
                category=FailureCategory.FIXTURE_MUTATION,
                message="Fixture state changed between before and after snapshots.",
            )
        )
    return findings


def collect_v1_findings(report: dict[str, Any], *, report_label: str, report_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    for index, error in enumerate(errors):
        findings.append(classify_message_finding(report_label, report_path, f"errors[{index}]", error))
    for index, item in enumerate(report.get("health") if isinstance(report.get("health"), list) else []):
        if isinstance(item, dict) and (item.get("status") != "passed" or item.get("http_status") not in (None, 200)):
            message = item.get("error") or f"Health check failed for {item.get('name')}"
            category, terms = classify_text(str(message))
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"health[{item.get('name') or index}]",
                    category=category if category != FailureCategory.UNKNOWN else FailureCategory.HARNESS_ERROR,
                    message=message,
                    matched_terms=terms,
                    evidence=item,
                )
            )
    preflight = report.get("anythingllm_preflight")
    if isinstance(preflight, dict) and preflight and preflight.get("status") != "passed":
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="anythingllm_preflight",
                category=FailureCategory.ANYTHINGLLM_CONFIG_ERROR,
                message="AnythingLLM preflight failed.",
                evidence=preflight,
            )
        )
    suite_runs = report.get("suite_runs") if isinstance(report.get("suite_runs"), list) else []
    for index, item in enumerate(suite_runs):
        if not isinstance(item, dict) or item.get("status") == "passed":
            continue
        suite_id = str(item.get("id") or f"suite_{index}")
        text = "\n".join(str(item.get(key) or "") for key in ("description", "stdout_tail", "stderr_tail", "returncode"))
        findings.append(classify_message_finding(report_label, report_path, f"suite_runs[{suite_id}]", text))
    founder_summary = report.get("founder_field_summary")
    if isinstance(founder_summary, dict):
        for index, error in enumerate(founder_summary.get("errors") if isinstance(founder_summary.get("errors"), list) else []):
            findings.append(classify_message_finding(report_label, report_path, f"founder_field_summary.errors[{index}]", error))
        summary = founder_summary.get("summary") if isinstance(founder_summary.get("summary"), dict) else {}
        if isinstance(summary.get("failed"), int) and summary["failed"] > 0:
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source="founder_field_summary.failed",
                    category=FailureCategory.SEMANTIC_MISS,
                    message=f"Founder field suite reported {summary['failed']} failed prompt(s).",
                    evidence=summary,
                )
            )
        nested_path = existing_artifact_path(founder_summary.get("report_path"), base_path=report_path)
        if nested_path is not None:
            findings.extend(
                collect_founder_field_findings(
                    load_json(nested_path),
                    report_label=f"{report_label}:founder-field",
                    report_path=nested_path,
                )
            )
    skill_health = report.get("skill_library_health")
    if isinstance(skill_health, dict):
        for index, error in enumerate(skill_health.get("errors") if isinstance(skill_health.get("errors"), list) else []):
            findings.append(classify_message_finding(report_label, report_path, f"skill_library_health.errors[{index}]", error))
        live_suite_statuses = skill_health.get("live_suite_statuses")
        if isinstance(live_suite_statuses, dict):
            for suite_id, status in live_suite_statuses.items():
                if status != "passed":
                    findings.append(
                        finding(
                            report_label=report_label,
                            report_path=report_path,
                            source=f"skill_library_health.live_suite_statuses[{suite_id}]",
                            category=FailureCategory.HARNESS_ERROR,
                            message=f"Skill release live suite {suite_id} returned {status}.",
                        )
                    )
    return dedupe_findings(findings)


def collect_model_portability_findings(report: dict[str, Any], *, report_label: str, report_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, error in enumerate(report.get("errors") if isinstance(report.get("errors"), list) else []):
        findings.append(classify_message_finding(report_label, report_path, f"errors[{index}]", error))
    category_map = {
        "harness": FailureCategory.HARNESS_ERROR,
        "classifier": FailureCategory.ROUTING_MISS,
        "prompt": FailureCategory.PROMPT_AMBIGUITY,
        "model_quality": FailureCategory.MODEL_QUALITY,
        "unknown": FailureCategory.UNKNOWN,
    }
    for index, item in enumerate(report.get("classified_failures") if isinstance(report.get("classified_failures"), list) else []):
        if not isinstance(item, dict):
            continue
        category = category_map.get(str(item.get("classification")), FailureCategory.UNKNOWN)
        message = item.get("message") or item
        text_category, terms = classify_text(str(message))
        if text_category != FailureCategory.UNKNOWN and category in (FailureCategory.HARNESS_ERROR, FailureCategory.MODEL_QUALITY):
            category = text_category
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source=f"classified_failures[{index}]",
                category=category,
                message=message,
                matched_terms=terms or list(item.get("matched_terms") or []),
                evidence={"source": item.get("source"), "classification": item.get("classification")},
            )
        )
    nested_path = existing_artifact_path(report.get("acceptance_report_path"), base_path=report_path)
    if nested_path is not None:
        findings.extend(
            collect_v1_findings(load_json(nested_path), report_label=f"{report_label}:v1", report_path=nested_path)
        )
    return dedupe_findings(findings)


def collect_run_diff_findings(report: dict[str, Any], *, report_label: str, report_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, error in enumerate(report.get("errors") if isinstance(report.get("errors"), list) else []):
        findings.append(classify_message_finding(report_label, report_path, f"errors[{index}]", error))
    diff = report.get("diff") if isinstance(report.get("diff"), dict) else {}
    if diff.get("fixture_state_changes"):
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="diff.fixture_state_changes",
                category=FailureCategory.FIXTURE_MUTATION,
                message="Run diff detected fixture state changes.",
                evidence={"fixture_state_changes": diff.get("fixture_state_changes")},
            )
        )
    if diff.get("semantic_miss_changes", {}).get("added") if isinstance(diff.get("semantic_miss_changes"), dict) else False:
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="diff.semantic_miss_changes",
                category=FailureCategory.SEMANTIC_MISS,
                message="Run diff detected newly added semantic misses.",
                evidence=diff.get("semantic_miss_changes"),
            )
        )
    if diff.get("output_miss_changes", {}).get("added") if isinstance(diff.get("output_miss_changes"), dict) else False:
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="diff.output_miss_changes",
                category=FailureCategory.OUTPUT_CONTRACT_MISS,
                message="Run diff detected newly added output-contract misses.",
                evidence=diff.get("output_miss_changes"),
            )
        )
    for key in ("route_rule_changes", "workflow_changes"):
        value = diff.get(key)
        if isinstance(value, dict) and value.get("changed_count"):
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"diff.{key}",
                    category=FailureCategory.ROUTING_MISS,
                    message=f"Run diff detected {key.replace('_', ' ')}.",
                    evidence=value,
                )
            )
    classification_delta = diff.get("classification_summary_delta")
    if isinstance(classification_delta, dict):
        for classification, value in classification_delta.items():
            if not isinstance(value, dict) or value.get("delta") in (None, 0):
                continue
            category = {
                "harness": FailureCategory.HARNESS_ERROR,
                "classifier": FailureCategory.ROUTING_MISS,
                "prompt": FailureCategory.PROMPT_AMBIGUITY,
                "model_quality": FailureCategory.MODEL_QUALITY,
                "unknown": FailureCategory.UNKNOWN,
            }.get(str(classification), FailureCategory.UNKNOWN)
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"diff.classification_summary_delta[{classification}]",
                    category=category,
                    message=f"Model portability classification count changed for {classification}.",
                    evidence=value,
                )
            )
    return findings


COMPARISON_CATEGORY_MAP: dict[str, tuple[FailureCategory, str]] = {
    "routing": (FailureCategory.ROUTING_MISS, "routing"),
    "route": (FailureCategory.ROUTING_MISS, "routing"),
    "evidence": (FailureCategory.EVIDENCE_MISS, "context_gathering"),
    "missing_data": (FailureCategory.EVIDENCE_MISS, "context_gathering"),
    "observability": (FailureCategory.EVIDENCE_MISS, "context_gathering"),
    "unknowns": (FailureCategory.EVIDENCE_MISS, "context_gathering"),
    "answer_contract": (FailureCategory.OUTPUT_CONTRACT_MISS, "deterministic_formatter"),
    "output_contract": (FailureCategory.OUTPUT_CONTRACT_MISS, "deterministic_formatter"),
    "baseline_topic_gap": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "root_cause": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "recommendation": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "tradeoffs": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "risk": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "validation": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "confidence": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "technical_debt": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "engineering_method": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "deployment_readiness": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "mentorship_quality": (FailureCategory.SEMANTIC_MISS, "model_capability"),
    "unsupported_preference": (FailureCategory.MODEL_QUALITY, "model_capability"),
    "test_level": (FailureCategory.SEMANTIC_MISS, "test_coverage"),
    "reproduction": (FailureCategory.SEMANTIC_MISS, "test_coverage"),
    "safety_boundary": (FailureCategory.APPROVAL_BOUNDARY_MISS, "safety_boundary"),
    "read_only_boundary": (FailureCategory.APPROVAL_BOUNDARY_MISS, "safety_boundary"),
    "documentation": (FailureCategory.HARNESS_ERROR, "documentation"),
    "docs": (FailureCategory.HARNESS_ERROR, "documentation"),
    "tool_availability": (FailureCategory.EVIDENCE_MISS, "skill_tool_selection"),
    "tool_selection": (FailureCategory.EVIDENCE_MISS, "skill_tool_selection"),
    "skill_selection": (FailureCategory.SEMANTIC_MISS, "skill_tool_selection"),
}


COMPARISON_REPAIR_ACTION_BY_GAP_CLASS: dict[str, str] = {
    "routing": "Repair the narrowest workflow-router rule or prompt-family expectation, then rerun target and holdout cases.",
    "context_gathering": "Repair deterministic source, test, log, or evidence extraction before changing prompt wording.",
    "skill_tool_selection": "Repair the selected skill, rejected skill, tool catalog, or allowlist evidence before changing answer text.",
    "deterministic_formatter": "Repair the chat renderer or FormatA/JSON contract so required fields are visible in chat.",
    "model_capability": "Inspect local-model output and model capability profile before changing routing or skills.",
    "safety_boundary": "Fail closed and repair approval, read-only, or no-mutation boundary rendering before any apply work.",
    "documentation": "Repair setup, tester, or workflow documentation and rerun the affected chat-quality proof.",
    "test_coverage": "Repair the test-selection, reproduction, or verification strategy output and rerun the affected prompt family.",
}
COMPARISON_MINIMUM_SCORE = 85


def is_priority0_comparison_kind(kind: str) -> bool:
    return kind.endswith("_blind_baseline_comparison")


def comparison_category_details(category: object, message: object) -> tuple[FailureCategory, str, list[str]]:
    category_text = str(category or "").strip().lower()
    if category_text in COMPARISON_CATEGORY_MAP:
        failure_category, gap_class = COMPARISON_CATEGORY_MAP[category_text]
        return failure_category, gap_class, [category_text]
    text_category, terms = classify_text(f"{category_text} {message}")
    if text_category != FailureCategory.UNKNOWN:
        gap_class = {
            FailureCategory.ROUTING_MISS: "routing",
            FailureCategory.OUTPUT_CONTRACT_MISS: "deterministic_formatter",
            FailureCategory.EVIDENCE_MISS: "context_gathering",
            FailureCategory.APPROVAL_BOUNDARY_MISS: "safety_boundary",
            FailureCategory.MODEL_QUALITY: "model_capability",
            FailureCategory.HARNESS_ERROR: "documentation",
            FailureCategory.ANYTHINGLLM_CONFIG_ERROR: "documentation",
        }.get(text_category, "model_capability")
        return text_category, gap_class, terms
    return FailureCategory.SEMANTIC_MISS, "model_capability", []


def collect_priority0_comparison_findings(
    report: dict[str, Any],
    *,
    report_label: str,
    report_path: Path,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, error in enumerate(report.get("errors") if isinstance(report.get("errors"), list) else []):
        findings.append(classify_message_finding(report_label, report_path, f"errors[{index}]", error))
    priority_backlog_id = report.get("priority_backlog_id")
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    route_count = 0
    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id") or f"case_{case_index}")
        case_type = case.get("case_type")
        target_root = case.get("target_root")
        holdout = case.get("holdout") is True
        routes = case.get("routes") if isinstance(case.get("routes"), list) else []
        for route_index, route in enumerate(routes):
            if not isinstance(route, dict):
                continue
            route_count += 1
            route_name = str(route.get("route") or f"route_{route_index}")
            unresolved = route.get("unresolved_findings") if isinstance(route.get("unresolved_findings"), list) else []
            route_issues = list(unresolved)
            if not unresolved and route.get("pass") is not True:
                route_issues.append(
                    {
                        "severity": "high",
                        "category": "routing" if not route.get("selected_workflow") else "baseline_topic_gap",
                        "message": "comparison route failed without a specific unresolved finding",
                    }
                )
            score = route.get("score")
            if isinstance(score, int) and score < COMPARISON_MINIMUM_SCORE:
                route_issues.append(
                    {
                        "severity": "high",
                        "category": "baseline_topic_gap",
                        "message": f"comparison route score {score} is below {COMPARISON_MINIMUM_SCORE}",
                    }
                )
            for finding_index, unresolved_item in enumerate(route_issues):
                if not isinstance(unresolved_item, dict):
                    continue
                message = unresolved_item.get("message") or unresolved_item
                source_category = unresolved_item.get("category")
                category, gap_class, matched_terms = comparison_category_details(source_category, message)
                evidence = {
                    "comparison_kind": report.get("kind"),
                    "priority_backlog_id": priority_backlog_id,
                    "case_id": case_id,
                    "case_type": case_type,
                    "holdout": holdout,
                    "target_root": target_root,
                    "route": route_name,
                    "selected_workflow": route.get("selected_workflow"),
                    "score": route.get("score"),
                    "pass": route.get("pass"),
                    "comparison_category": source_category,
                    "gap_class": gap_class,
                    "bounded_repair_action": COMPARISON_REPAIR_ACTION_BY_GAP_CLASS[gap_class],
                }
                findings.append(
                    finding(
                        report_label=report_label,
                        report_path=report_path,
                        source=f"cases[{case_id}].routes[{route_name}].unresolved_findings[{finding_index}]",
                        category=category,
                        severity=str(unresolved_item.get("severity") or SEVERITY_BY_CATEGORY[category]),
                        message=message,
                        matched_terms=matched_terms,
                        evidence=evidence,
                    )
                )
    summary_gap_categories = report.get("gap_categories") if isinstance(report.get("gap_categories"), dict) else {}
    for gap_category, count in sorted(summary_gap_categories.items()):
        if not isinstance(count, int) or count <= 0:
            continue
        category, gap_class, matched_terms = comparison_category_details(
            gap_category,
            f"comparison summary reported {count} {gap_category} gap(s)",
        )
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source=f"comparison.gap_categories[{gap_category}]",
                category=category,
                severity="high",
                message=f"Comparison summary reported {count} {gap_category} gap(s).",
                matched_terms=matched_terms,
                evidence={
                    "comparison_kind": report.get("kind"),
                    "priority_backlog_id": priority_backlog_id,
                    "comparison_category": gap_category,
                    "gap_count": count,
                    "gap_class": gap_class,
                    "bounded_repair_action": COMPARISON_REPAIR_ACTION_BY_GAP_CLASS[gap_class],
                },
            )
        )
    for field, severity in (("critical_finding_count", "critical"), ("high_finding_count", "high")):
        count = report.get(field)
        if isinstance(count, int) and count > 0 and not summary_gap_categories:
            gap_class = "documentation"
            findings.append(
                finding(
                    report_label=report_label,
                    report_path=report_path,
                    source=f"comparison.{field}",
                    category=FailureCategory.HARNESS_ERROR,
                    severity=severity,
                    message=f"Comparison summary reported {field}={count} without route-level gap categories.",
                    evidence={
                        "comparison_kind": report.get("kind"),
                        "priority_backlog_id": priority_backlog_id,
                        "summary_field": field,
                        "summary_count": count,
                        "gap_class": gap_class,
                        "bounded_repair_action": COMPARISON_REPAIR_ACTION_BY_GAP_CLASS[gap_class],
                    },
                )
            )
    response_count = report.get("response_count")
    passed_response_count = report.get("passed_response_count")
    if (
        isinstance(response_count, int)
        and isinstance(passed_response_count, int)
        and response_count > passed_response_count
        and not findings
    ):
        gap_class = "documentation"
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="comparison.passed_response_count",
                category=FailureCategory.HARNESS_ERROR,
                severity="high",
                message="Comparison summary has fewer passed responses than responses without route-level findings.",
                evidence={
                    "comparison_kind": report.get("kind"),
                    "priority_backlog_id": priority_backlog_id,
                    "response_count": response_count,
                    "passed_response_count": passed_response_count,
                    "gap_class": gap_class,
                    "bounded_repair_action": COMPARISON_REPAIR_ACTION_BY_GAP_CLASS[gap_class],
                },
            )
        )
    repairs = report.get("recommended_next_repairs") if isinstance(report.get("recommended_next_repairs"), list) else []
    for index, repair in enumerate(repairs):
        repair_category = repair.get("category") if isinstance(repair, dict) else None
        repair_message = repair.get("recommendation") if isinstance(repair, dict) else repair
        category, gap_class, matched_terms = comparison_category_details(repair_category, repair_message)
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source=f"comparison.recommended_next_repairs[{index}]",
                category=category,
                severity="medium",
                message=repair_message,
                matched_terms=matched_terms,
                evidence={
                    "comparison_kind": report.get("kind"),
                    "priority_backlog_id": priority_backlog_id,
                    "comparison_category": repair_category,
                    "gap_class": gap_class,
                    "bounded_repair_action": COMPARISON_REPAIR_ACTION_BY_GAP_CLASS[gap_class],
                },
            )
        )
    if str(report.get("status") or "") != "passed" and not findings:
        findings.append(
            finding(
                report_label=report_label,
                report_path=report_path,
                source="comparison.status",
                category=FailureCategory.HARNESS_ERROR if route_count == 0 else FailureCategory.SEMANTIC_MISS,
                severity="high",
                message=f"Priority 0 comparison status is {report.get('status')} without route-level findings.",
                evidence={
                    "comparison_kind": report.get("kind"),
                    "priority_backlog_id": priority_backlog_id,
                    "gap_class": "documentation" if route_count == 0 else "model_capability",
                },
            )
        )
    return dedupe_findings(findings)


def collect_findings(report: dict[str, Any], *, report_label: str, report_path: Path) -> list[dict[str, Any]]:
    kind = str(report.get("kind") or report_kind(report).value)
    if is_priority0_comparison_kind(kind):
        return collect_priority0_comparison_findings(report, report_label=report_label, report_path=report_path)
    if kind == "founder_field_prompt_evaluation":
        return collect_founder_field_findings(report, report_label=report_label, report_path=report_path)
    if kind == "v1_acceptance_report":
        return collect_v1_findings(report, report_label=report_label, report_path=report_path)
    if kind == "model_portability_report":
        return collect_model_portability_findings(report, report_label=report_label, report_path=report_path)
    if kind == "run_artifact_diff":
        return collect_run_diff_findings(report, report_label=report_label, report_path=report_path)
    return [classify_message_finding(report_label, report_path, "unknown_report", report)]


def dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in findings:
        key = (
            str(item.get("report_path")),
            str(item.get("source")),
            str(item.get("category")),
            re.sub(r"\s+", " ", str(item.get("message"))).strip()[:240],
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def category_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {category.value: 0 for category in FailureCategory}
    for item in findings:
        category = str(item.get("category") or FailureCategory.UNKNOWN.value)
        counts[category] = counts.get(category, 0) + 1
    return counts


def severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in findings:
        severity = str(item.get("severity") or "medium")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def highest_severity(findings: list[dict[str, Any]]) -> str:
    counts = severity_counts(findings)
    for severity in ("critical", "high", "medium", "low"):
        if counts.get(severity):
            return severity
    return "none"


def markdown_path_for(path: Path) -> Path:
    return path.with_suffix(".md")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Failure Taxonomy Report",
        "",
        f"- Status: {report['status']}",
        f"- Created at: {report['created_at']}",
        f"- Report count: {len(report['input_reports'])}",
        f"- Finding count: {len(report['findings'])}",
        f"- Highest severity: {report['summary']['highest_severity']}",
        "",
        "## Category Counts",
        "",
        "| Category | Count |",
        "| --- | ---: |",
    ]
    for category, count in report["summary"]["category_counts"].items():
        if count:
            lines.append(f"| {category} | {count} |")
    if not any(report["summary"]["category_counts"].values()):
        lines.append("| none | 0 |")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Severity | Category | Report | Source | Message | Next action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["findings"]:
        lines.append(
            "| {severity} | {category} | {report} | {source} | {message} | {next_action} |".format(
                severity=item["severity"],
                category=item["category"],
                report=item["report_label"],
                source=item["source"],
                message=str(item["message"]).replace("\n", " ")[:300],
                next_action=str(item["recommended_next_action"]).replace("\n", " ")[:300],
            )
        )
    if not report["findings"]:
        lines.append("| none | none | all | none | No classified failures found. | No action required. |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_failure_taxonomy(config: FailureTaxonomyConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    markdown_path = config.markdown_output_path or markdown_path_for(output_path)
    labels = list(config.labels)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "failure_taxonomy_report",
        "status": "failed",
        "created_at": utc_timestamp(),
        "input_reports": [],
        "summary": {},
        "findings": [],
        "markdown_report_path": str(markdown_path),
        "errors": [],
    }
    try:
        if not config.report_paths:
            raise RuntimeError("at least one report path is required")
        findings: list[dict[str, Any]] = []
        for index, path in enumerate(config.report_paths):
            resolved = path.resolve()
            label = labels[index] if index < len(labels) and labels[index] else resolved.stem
            loaded = load_json(resolved)
            kind = str(loaded.get("kind") or report_kind(loaded).value)
            report["input_reports"].append(
                {
                    "label": label,
                    "path": str(resolved),
                    "kind": kind,
                    "status": loaded.get("status"),
                }
            )
            findings.extend(collect_findings(loaded, report_label=label, report_path=resolved))
        findings = dedupe_findings(findings)
        report["findings"] = findings
        report["summary"] = {
            "finding_count": len(findings),
            "category_counts": category_counts(findings),
            "severity_counts": severity_counts(findings),
            "highest_severity": highest_severity(findings),
        }
        report["status"] = "passed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_markdown(markdown_path, report)
    return report
