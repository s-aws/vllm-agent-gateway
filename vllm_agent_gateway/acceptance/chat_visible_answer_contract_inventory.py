"""Phase 200 chat-visible answer contract inventory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import is_prompt_family_baseline_entry


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chat_visible_answer_contract_inventory_policy"
EXPECTED_REPORT_KIND = "chat_visible_answer_contract_inventory_report"
EXPECTED_PHASE = 200
EXPECTED_BACKLOG_ID = "P0-BB-064"
EXPECTED_MILESTONE_ID = "M2"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_visible_answer_contract_inventory_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase200" / "phase200-chat-visible-answer-contract-inventory-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase200" / "phase200-chat-visible-answer-contract-inventory-report.md"


class ContractInventoryStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ContractGapClass(str, Enum):
    MISSING_CONTRACT = "missing_contract"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MISSING_OUTPUT_FORMAT = "missing_output_format"
    MISSING_SAFETY_BOUNDARY = "missing_safety_boundary"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    DOC_REFERENCE_MISSING = "doc_reference_missing"


@dataclass(frozen=True)
class ChatVisibleAnswerContractInventoryConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH


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


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


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


def validation_error(error_id: str, message: str, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 200"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "policy.milestone_id must be M2"))
    if set(string_list(policy.get("required_workflows"))) != {
        "code_context.lookup",
        "code_investigation.plan",
        "execution_planning.plan",
        "task.decompose",
    }:
        errors.append(validation_error("policy.required_workflows", "required workflows must match the current supported workflow set"))
    for field in (
        "required_contract_fields",
        "required_output_formats",
        "required_safety_boundaries",
        "required_docs",
    ):
        if not string_list(policy.get(field)):
            errors.append(validation_error(f"policy.{field}", f"{field} must be a non-empty list"))
    sources = dict_value(policy.get("required_sources"))
    for source_id in ("prompt_skill_coverage", "baseline_corpus", "founder_field_catalog"):
        source = dict_value(sources.get(source_id))
        if not isinstance(source.get("path"), str) or not source["path"].strip():
            errors.append(validation_error(f"policy.required_sources.{source_id}.path", f"{source_id} source path is required"))
    if policy.get("acceptance_marker") != "PHASE200 CHAT VISIBLE ANSWER CONTRACT INVENTORY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 200"))
    return errors


def load_sources(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[dict[str, str]]]:
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    for source_id, spec in dict_value(policy.get("required_sources")).items():
        source = dict_value(spec)
        raw_path = source.get("path")
        if not isinstance(raw_path, str):
            sources[source_id] = (None, {})
            errors.append(validation_error(f"{source_id}.path", "source path must be a string", source=source_id))
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            sources[source_id] = (path, {})
            errors.append(validation_error(f"{source_id}.missing", f"source is missing: {raw_path}", source=source_id))
            continue
        try:
            payload = read_json_object(path)
            sources[source_id] = (path, payload)
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            sources[source_id] = (path, {})
            errors.append(validation_error(f"{source_id}.malformed", f"source is malformed: {type(exc).__name__}: {exc}", source=source_id))
            continue
        expected_kind = source.get("expected_kind")
        if isinstance(expected_kind, str) and payload.get("kind") != expected_kind:
            errors.append(validation_error(f"{source_id}.kind", f"source kind must be {expected_kind}", source=source_id))
    return sources, errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path is not None else None,
        "exists": path.is_file() if path is not None else False,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "entry_count": len(object_list(payload.get("entries"))),
        "case_count": len(object_list(payload.get("cases"))),
    }


def implemented_entries(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in object_list(coverage.get("entries"))
        if item.get("status") == "implemented" and isinstance(item.get("id"), str)
    ]


def contract_kind(entry: dict[str, Any]) -> str:
    workflow = entry.get("selected_workflow")
    if workflow == "execution_planning.plan":
        return "draft_proposal"
    if workflow == "task.decompose":
        return "task_decomposition"
    if workflow == "code_context.lookup":
        return "code_context"
    return "read_only_answer"


def required_sections_for_entry(entry: dict[str, Any]) -> list[str]:
    workflow = entry.get("selected_workflow")
    artifacts = set(string_list(entry.get("expected_artifacts")))
    sections = ["Answer", "Evidence", "Safety boundary", "Run traceability"]
    if workflow == "execution_planning.plan":
        sections = ["Draft proposal", "Target files", "Safety checks", "Verification commands", "Run traceability"]
    elif workflow == "task.decompose":
        sections = ["Task Decomposition", "Work packages", "Acceptance criteria", "Dependencies", "Risks", "Run traceability"]
    elif workflow == "code_context.lookup":
        sections = ["Answer", "Callers/usages", "Evidence", "Confidence", "Run traceability"]
    elif "related_tests" in artifacts:
        sections.extend(["Related tests", "Recommended commands"])
    elif "verification_plan" in artifacts or "test_selection_plan" in artifacts:
        sections.extend(["Recommended commands", "Residual risk"])
    elif "configuration_lookup" in artifacts or "data_model_lookup" in artifacts:
        sections.extend(["Definitions", "Source references"])
    elif "module_summary" in artifacts:
        sections.extend(["Responsibilities", "Key files"])
    return list(dict.fromkeys(sections))


def evidence_expectations_for_entry(entry: dict[str, Any]) -> list[str]:
    workflow = entry.get("selected_workflow")
    if workflow == "execution_planning.plan":
        return ["exact target path", "operation source evidence", "verification command", "mutation boundary"]
    if workflow == "task.decompose":
        return ["requirement source", "scope boundary", "acceptance criteria", "dependency evidence"]
    if workflow == "code_context.lookup":
        return ["symbol or usage references", "source file paths", "confidence label"]
    return ["source file paths", "line or symbol references when available", "related tests when requested", "confidence label"]


def safety_boundaries_for_entry(entry: dict[str, Any]) -> list[str]:
    workflow = entry.get("selected_workflow")
    boundaries = ["no_unsupported_mutation_claims", "source_mutation_status", "unsupported_scope_recovery"]
    if workflow == "execution_planning.plan":
        boundaries.extend(["draft_only_until_approved", "protected_fixture_no_source_mutation"])
    if workflow in {"code_context.lookup", "code_investigation.plan"}:
        boundaries.append("read_only_no_source_mutation")
    return list(dict.fromkeys(boundaries))


def output_format_behavior() -> dict[str, str]:
    return {
        "format_a": "Answer-first natural-language response with evidence, safety boundary, and run traceability.",
        "json": "Structured response preserving the same answer body, evidence markers, safety boundary, and run traceability.",
    }


def contract_record(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": entry.get("id"),
        "prompt_family": entry.get("prompt_family"),
        "level": entry.get("level"),
        "selected_workflow": entry.get("selected_workflow"),
        "route_rule": entry.get("route_rule"),
        "skill_ids": string_list(entry.get("skill_ids")),
        "tool_ids": string_list(entry.get("tool_ids")),
        "expected_artifacts": string_list(entry.get("expected_artifacts")),
        "validation_suites": string_list(entry.get("validation_suites")),
        "docs_examples": string_list(entry.get("docs_examples")),
        "contract_kind": contract_kind(entry),
        "answer_heading": "Draft proposal" if entry.get("selected_workflow") == "execution_planning.plan" else "Answer",
        "required_sections": required_sections_for_entry(entry),
        "evidence_expectations": evidence_expectations_for_entry(entry),
        "safety_boundaries": safety_boundaries_for_entry(entry),
        "run_traceability": ["workflow-router run_id", "selected_workflow", "artifact references when generated"],
        "output_format_behavior": output_format_behavior(),
        "inventory_status": "defined",
    }


def validate_contract_records(
    config_root: Path,
    policy: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required_fields = set(string_list(policy.get("required_contract_fields")))
    required_formats = set(string_list(policy.get("required_output_formats")))
    required_safety = set(string_list(policy.get("required_safety_boundaries")))
    if not records:
        errors.append(validation_error("contracts.empty", "at least one supported prompt-family contract is required", source="contracts"))
        return errors
    entry_ids = [str(item.get("entry_id")) for item in records if isinstance(item.get("entry_id"), str)]
    if len(entry_ids) != len(set(entry_ids)):
        errors.append(validation_error("contracts.duplicate_entry_id", "contract entry IDs must be unique", source="contracts"))
    for index, record in enumerate(records):
        prefix = f"contracts[{index}]"
        for field in required_fields:
            value = record.get(field)
            if isinstance(value, list) and not string_list(value):
                errors.append(validation_error(f"{prefix}.{field}", f"{field} must be non-empty", source="contracts"))
            elif isinstance(value, dict) and not value:
                errors.append(validation_error(f"{prefix}.{field}", f"{field} must be non-empty", source="contracts"))
            elif not isinstance(value, (list, dict)) and not isinstance(value, str):
                errors.append(validation_error(f"{prefix}.{field}", f"{field} is required", source="contracts"))
            elif isinstance(value, str) and not value.strip():
                errors.append(validation_error(f"{prefix}.{field}", f"{field} must be non-empty", source="contracts"))
        formats = set(dict_value(record.get("output_format_behavior")).keys())
        if formats != required_formats:
            errors.append(validation_error(f"{prefix}.output_format_behavior", "output format behavior must cover required formats", source="contracts"))
        safety = set(string_list(record.get("safety_boundaries")))
        if not required_safety.issubset(safety):
            errors.append(validation_error(f"{prefix}.safety_boundaries", "contract is missing required safety boundaries", source="contracts"))
        for doc_path in string_list(record.get("docs_examples")):
            if not resolve_path(config_root, doc_path).exists():
                errors.append(validation_error(f"{prefix}.docs_examples", f"doc reference is missing: {doc_path}", "medium", "contracts"))
    return errors


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            errors.append(validation_error(f"docs.{raw_path}.missing", f"required doc is missing: {raw_path}", "medium", "documentation"))
    return docs, errors


def baseline_records(baseline_corpus: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "entry_id": item.get("entry_id"),
            "prompt_family": item.get("prompt_family"),
            "phase": item.get("phase"),
            "status": item.get("status"),
            "minimum_route_score": dict_value(item.get("comparison")).get("minimum_route_score"),
            "critical_finding_count": dict_value(item.get("comparison")).get("critical_finding_count"),
            "high_finding_count": dict_value(item.get("comparison")).get("high_finding_count"),
        }
        for item in object_list(baseline_corpus.get("entries"))
        if is_prompt_family_baseline_entry(item)
    ]


def founder_catalog_summary(catalog: dict[str, Any]) -> dict[str, Any]:
    cases = object_list(catalog.get("cases"))
    workflows = sorted({str(case.get("expected_workflow")) for case in cases if isinstance(case.get("expected_workflow"), str)})
    return {
        "case_count": len(cases),
        "workflows": workflows,
        "read_only_case_count": sum(1 for case in cases if "read-only" in string_list(case.get("tags"))),
        "case_ids": [case.get("case_id") for case in cases if isinstance(case.get("case_id"), str)],
    }


def build_chat_visible_answer_contract_inventory_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(source_load_errors)
    coverage = sources.get("prompt_skill_coverage", (None, {}))[1]
    baseline_corpus = sources.get("baseline_corpus", (None, {}))[1]
    founder_catalog = sources.get("founder_field_catalog", (None, {}))[1]
    records = [contract_record(entry) for entry in implemented_entries(coverage)]
    errors.extend(validate_contract_records(config_root, policy, records))
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    workflow_counts = {
        workflow: sum(1 for item in records if item.get("selected_workflow") == workflow)
        for workflow in string_list(policy.get("required_workflows"))
    }
    for workflow, count in workflow_counts.items():
        if count == 0:
            errors.append(validation_error(f"contracts.workflow.{workflow}", f"workflow has no contract records: {workflow}", source="contracts"))
    source_refs = {source_id: source_ref(path, payload) for source_id, (path, payload) in sources.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": ContractInventoryStatus.FAILED.value if errors else ContractInventoryStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": source_refs,
        "contract_records": records,
        "baseline_records": baseline_records(baseline_corpus),
        "founder_catalog_summary": founder_catalog_summary(founder_catalog),
        "docs": docs,
        "gap_matrix": [
            {
                "gap_class": ContractGapClass.MISSING_CONTRACT.value,
                "count": 0 if records else 1,
                "phase201_action": "enforce all defined contracts",
            },
            {
                "gap_class": ContractGapClass.DOC_REFERENCE_MISSING.value,
                "count": sum(1 for error in errors if error["id"].endswith(".docs_examples")),
                "phase201_action": "repair missing documentation references before enforcement",
            },
        ],
        "validation_errors": errors,
        "summary": {
            "contract_count": len(records),
            "implemented_coverage_entry_count": len(implemented_entries(coverage)),
            "stable_baseline_count": len(baseline_records(baseline_corpus)),
            "founder_catalog_case_count": len(object_list(founder_catalog.get("cases"))),
            "workflow_counts": workflow_counts,
            "validation_error_count": len(errors),
            "phase201_ready": not errors,
            "next_action": "work Phase 201 Chat-Visible Answer Contract Enforcement Gate"
            if not errors
            else "repair Phase 200 contract inventory gaps before enforcement",
        },
    }


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "milestone_id",
            "status",
            "policy_path",
            "policy_sha256",
            "source_refs",
            "contract_records",
            "baseline_records",
            "founder_catalog_summary",
            "docs",
            "gap_matrix",
            "validation_errors",
            "summary",
        )
    }


def validate_chat_visible_answer_contract_inventory_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_chat_visible_answer_contract_inventory_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt chat-visible answer contract inventory"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 200 Chat-Visible Answer Contract Inventory",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Contracts: `{summary.get('contract_count')}`",
        f"- Stable baselines: `{summary.get('stable_baseline_count')}`",
        f"- Founder catalog cases: `{summary.get('founder_catalog_case_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Workflow Counts",
        "",
    ]
    for workflow, count in sorted(dict_value(summary.get("workflow_counts")).items()):
        lines.append(f"- `{workflow}`: `{count}`")
    lines.extend(["", "## Contract Records", "", "| Entry | Workflow | Kind | Sections |", "| --- | --- | --- | --- |"])
    for item in object_list(report.get("contract_records")):
        sections = ", ".join(string_list(item.get("required_sections")))
        lines.append(f"| `{item.get('entry_id')}` | `{item.get('selected_workflow')}` | `{item.get('contract_kind')}` | {sections} |")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def run_chat_visible_answer_contract_inventory(config: ChatVisibleAnswerContractInventoryConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, source_load_errors = load_sources(config_root, policy)
    report = build_chat_visible_answer_contract_inventory_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_chat_visible_answer_contract_inventory_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = ContractInventoryStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "chat_visible_answer_contract_inventory")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase201_ready"] = False
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if config.markdown_output_path is not None:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_text(markdown_path, render_markdown(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        write_text(resolve_path(config_root, config.markdown_output_path), render_markdown(report))
    return report
