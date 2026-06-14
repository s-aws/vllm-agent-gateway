"""Phase 203 workflow/skill/tool selection matrix refresh."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "workflow_skill_tool_selection_matrix_policy"
EXPECTED_REPORT_KIND = "workflow_skill_tool_selection_matrix_report"
EXPECTED_PHASE = 203
EXPECTED_BACKLOG_ID = "P0-BB-067"
EXPECTED_MILESTONE_ID = "M3"
DEFAULT_POLICY_PATH = Path("runtime") / "workflow_skill_tool_selection_matrix_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase203" / "phase203-workflow-skill-tool-selection-matrix-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase203" / "phase203-workflow-skill-tool-selection-matrix-report.md"


class SelectionMatrixStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkflowSkillToolSelectionMatrixConfig:
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
        errors.append(validation_error("policy.phase", "policy.phase must be 203"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "policy.milestone_id must be M3"))
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must be gateway and anythingllm"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "required_target_roots must include both frozen Coinbase roots"))
    if "/mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture" not in set(string_list(policy.get("required_non_coinbase_roots"))):
        errors.append(validation_error("policy.required_non_coinbase_roots", "python_service_fixture non-Coinbase root is required"))
    if int(policy.get("minimum_matrix_record_count") or 0) < 38:
        errors.append(validation_error("policy.minimum_matrix_record_count", "minimum_matrix_record_count must be at least 38"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required_docs must be non-empty"))
    for source_id, spec in dict_value(policy.get("required_sources")).items():
        if not dict_value(spec).get("path"):
            errors.append(validation_error(f"policy.required_sources.{source_id}.path", f"{source_id} path is required"))
    if policy.get("acceptance_marker") != "PHASE203 WORKFLOW SKILL TOOL SELECTION MATRIX PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 203"))
    return errors


def load_sources(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    loaded: dict[str, tuple[Path, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    for source_id, raw_spec in dict_value(policy.get("required_sources")).items():
        spec = dict_value(raw_spec)
        raw_path = spec.get("path")
        path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else config_root / "<missing>"
        if not isinstance(raw_path, str) or not raw_path.strip():
            loaded[source_id] = (path, {})
            errors.append(validation_error(f"{source_id}.path", "source path is required", source=source_id))
            continue
        if not path.is_file():
            loaded[source_id] = (path, {})
            errors.append(validation_error(f"{source_id}.missing", f"source is missing: {raw_path}", source=source_id))
            continue
        try:
            payload = read_json_object(path)
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            loaded[source_id] = (path, {})
            errors.append(validation_error(f"{source_id}.malformed", f"source is malformed: {type(exc).__name__}: {exc}", source=source_id))
            continue
        loaded[source_id] = (path, payload)
        expected_kind = spec.get("expected_kind")
        if isinstance(expected_kind, str) and payload.get("kind") != expected_kind:
            errors.append(validation_error(f"{source_id}.kind", f"source kind must be {expected_kind}", source=source_id))
        expected_status = spec.get("expected_status")
        if isinstance(expected_status, str) and payload.get("status") != expected_status:
            errors.append(validation_error(f"{source_id}.status", f"source status must be {expected_status}", source=source_id))
        expected_phase = spec.get("expected_phase")
        if isinstance(expected_phase, int) and payload.get("phase") != expected_phase:
            errors.append(validation_error(f"{source_id}.phase", f"source phase must be {expected_phase}", source=source_id))
    return loaded, errors


def implemented_entries(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in object_list(coverage.get("entries"))
        if entry.get("status") == "implemented" and isinstance(entry.get("id"), str)
    ]


def registry_ids(payload: dict[str, Any], key: str) -> set[str]:
    return {str(item.get("id")) for item in object_list(payload.get(key)) if isinstance(item.get("id"), str)}


def normalize_family(value: str) -> str:
    lowered = value.lower()
    for prefix in ("l1-", "l2-", "d1-"):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :]
    replacements = {
        "code-explanation": "code_explanation",
        "configuration-lookup": "configuration_lookup",
        "data-model-lookup": "schema_lookup",
        "request-flow-map": "request_flow",
        "change-surface-summary": "change_surface",
        "table-read-write-lookup": "table_read_write",
        "related-tests": "related_tests",
        "callers-usages": "callers_usages",
        "runtime-error-diagnosis": "runtime_error_diagnosis",
    }
    return replacements.get(lowered, lowered.replace("-", "_"))


def phase151_proof_by_family(selection_report: dict[str, Any], selection_cases: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for result in object_list(selection_report.get("results")):
        case = selection_cases.get(str(result.get("case_id")))
        family = normalize_family(str(case.get("prompt_family") or "")) if case else ""
        if result.get("status") == "passed" and family:
            by_family.setdefault(family, []).append(
                {
                    "case_id": result.get("case_id"),
                    "surface": result.get("surface"),
                    "target_root": result.get("target_root"),
                    "rejected_candidate_counts": result.get("rejected_candidate_counts"),
                    "route_rules": result.get("route_rules"),
                }
            )
    return by_family


def phase187_proof_by_family(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for case in object_list(report.get("cases")):
        if case.get("status") != "passed":
            continue
        family = normalize_family(str(case.get("prompt_family") or ""))
        if not family:
            continue
        by_family.setdefault(family, []).append(
            {
                "case_id": case.get("case_id"),
                "client": case.get("client"),
                "target_root": case.get("target_root"),
                "selected_workflow": case.get("selected_workflow"),
                "selected_skills": string_list(case.get("selected_skills")),
                "selected_tools": string_list(case.get("selected_tools")),
            }
        )
    return by_family


def holdout_by_family(holdout_bank: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for entry in object_list(holdout_bank.get("entries")):
        family = normalize_family(str(entry.get("prompt_family") or ""))
        if family:
            by_family.setdefault(family, []).append(
                {
                    "entry_id": entry.get("entry_id"),
                    "holdout_case_ids": string_list(entry.get("holdout_case_ids")),
                    "holdout_target_roots": string_list(entry.get("holdout_target_roots")),
                }
            )
    return by_family


def matrix_records(policy: dict[str, Any], sources: dict[str, tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    coverage = sources["prompt_skill_coverage"][1]
    workflows = registry_ids(sources["workflows"][1], "workflows")
    skills = registry_ids(sources["skills"][1], "skills")
    tools = registry_ids(sources["tools"][1], "tools")
    selection_cases = {
        str(item.get("case_id")): item
        for item in object_list(sources["selection_cases"][1].get("cases"))
        if isinstance(item.get("case_id"), str)
    }
    phase151 = phase151_proof_by_family(sources["selection_explainability"][1], selection_cases)
    phase187 = phase187_proof_by_family(sources["multi_fixture_parity"][1])
    holdouts = holdout_by_family(sources["holdout_prompt_bank"][1])
    required_roots = string_list(policy.get("required_target_roots"))
    records: list[dict[str, Any]] = []
    for entry in implemented_entries(coverage):
        family_key = normalize_family(str(entry.get("prompt_family") or ""))
        skill_ids = string_list(entry.get("skill_ids"))
        tool_ids = string_list(entry.get("tool_ids"))
        phase151_proofs = phase151.get(family_key, [])
        phase187_proofs = phase187.get(family_key, [])
        non_coinbase_proofs = [
            proof for proof in phase187_proofs if isinstance(proof.get("target_root"), str) and "coinbase_testing_repo" not in proof["target_root"]
        ]
        holdout_proofs = holdouts.get(family_key, [])
        records.append(
            {
                "entry_id": entry.get("id"),
                "prompt_family": entry.get("prompt_family"),
                "family_key": family_key,
                "level": entry.get("level"),
                "expected_workflow": entry.get("selected_workflow"),
                "route_rule": entry.get("route_rule"),
                "selected_skill_ids": skill_ids,
                "selected_tool_ids": tool_ids,
                "registered_workflow": entry.get("selected_workflow") in workflows,
                "registered_skills": sorted(set(skill_ids) & skills),
                "missing_skills": sorted(set(skill_ids) - skills),
                "registered_tools": sorted(set(tool_ids) & tools),
                "missing_tools": sorted(set(tool_ids) - tools),
                "route_surfaces": string_list(policy.get("required_surfaces")),
                "fixture_targets": required_roots,
                "phase151_explainability_proof_count": len(phase151_proofs),
                "phase151_explainability_status": "covered" if phase151_proofs else "needs_phase204_live_explainability",
                "phase187_multi_fixture_proof_count": len(phase187_proofs),
                "non_coinbase_proof_count": len(non_coinbase_proofs),
                "holdout_proof_count": len(holdout_proofs),
                "rejected_candidate_expectation": "required_in_phase204",
                "docs_examples": string_list(entry.get("docs_examples")),
                "validation_suites": string_list(entry.get("validation_suites")),
            }
        )
    return records


def validate_matrix_records(policy: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if len(records) < int(policy.get("minimum_matrix_record_count") or 0):
        errors.append(validation_error("matrix.record_count", "matrix record count is below policy minimum", "critical", "matrix"))
    for index, record in enumerate(records):
        prefix = f"matrix[{index}]"
        if not record.get("registered_workflow"):
            errors.append(validation_error(f"{prefix}.registered_workflow", "expected workflow is not registered", "critical", "matrix"))
        if record.get("missing_skills"):
            errors.append(validation_error(f"{prefix}.missing_skills", f"missing skills: {record.get('missing_skills')}", "critical", "matrix"))
        if record.get("missing_tools"):
            errors.append(validation_error(f"{prefix}.missing_tools", f"missing tools: {record.get('missing_tools')}", "critical", "matrix"))
        if set(string_list(record.get("route_surfaces"))) != set(string_list(policy.get("required_surfaces"))):
            errors.append(validation_error(f"{prefix}.route_surfaces", "route surfaces must match policy", source="matrix"))
    if not any(int(record.get("non_coinbase_proof_count") or 0) > 0 for record in records):
        errors.append(validation_error("matrix.non_coinbase_proof", "at least one matrix row must include non-Coinbase proof", "critical", "matrix"))
    if not any(record.get("phase151_explainability_status") == "covered" for record in records):
        errors.append(validation_error("matrix.explainability_proof", "at least one matrix row must include Phase 151 explainability proof", "critical", "matrix"))
    return errors


def source_ref(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
    }


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


def build_workflow_skill_tool_selection_matrix_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path, dict[str, Any]]],
    source_errors: list[dict[str, str]],
    policy_path: Path | None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(source_errors)
    records = matrix_records(policy, sources) if not source_errors else []
    errors.extend(validate_matrix_records(policy, records))
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    source_refs = {source_id: source_ref(path, payload) for source_id, (path, payload) in sources.items()}
    workflow_counts = {
        workflow: sum(1 for record in records if record.get("expected_workflow") == workflow)
        for workflow in sorted({str(record.get("expected_workflow")) for record in records})
    }
    gaps: list[dict[str, Any]] = []
    for record in records:
        if record.get("phase151_explainability_status") != "covered":
            gaps.append(
                {
                    "entry_id": record.get("entry_id"),
                    "prompt_family": record.get("prompt_family"),
                    "gap_class": "missing_selection_explainability_proof",
                    "phase204_action": "run live natural prompt explainability proof",
                }
            )
        if int(record.get("holdout_proof_count") or 0) == 0:
            gaps.append(
                {
                    "entry_id": record.get("entry_id"),
                    "prompt_family": record.get("prompt_family"),
                    "gap_class": "missing_holdout_proof",
                    "phase205_action": "include in route-stability holdout replay or document why no holdout is applicable",
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": SelectionMatrixStatus.FAILED.value if errors else SelectionMatrixStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": source_refs,
        "matrix_records": records,
        "gap_records": gaps,
        "docs": docs,
        "validation_errors": errors,
        "summary": {
            "matrix_record_count": len(records),
            "workflow_counts": workflow_counts,
            "registered_gap_count": sum(1 for record in records if record.get("missing_skills") or record.get("missing_tools") or not record.get("registered_workflow")),
            "phase151_explainability_covered_count": sum(1 for record in records if record.get("phase151_explainability_status") == "covered"),
            "phase204_explainability_needed_count": sum(1 for gap in gaps if gap.get("gap_class") == "missing_selection_explainability_proof"),
            "holdout_proof_covered_count": sum(1 for record in records if int(record.get("holdout_proof_count") or 0) > 0),
            "holdout_proof_needed_count": sum(1 for gap in gaps if gap.get("gap_class") == "missing_holdout_proof"),
            "gap_count": len(gaps),
            "non_coinbase_proof_row_count": sum(1 for record in records if int(record.get("non_coinbase_proof_count") or 0) > 0),
            "validation_error_count": len(errors),
            "phase204_ready": not errors,
            "next_action": "work Phase 204 No Manual Skill Injection And Selection Explainability Gate"
            if not errors
            else "repair Phase 203 selection matrix gaps before Phase 204",
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
            "matrix_records",
            "gap_records",
            "docs",
            "validation_errors",
            "summary",
        )
    }


def validate_workflow_skill_tool_selection_matrix_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path, dict[str, Any]]],
    source_errors: list[dict[str, str]],
    policy_path: Path | None,
) -> list[str]:
    expected = build_workflow_skill_tool_selection_matrix_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_errors=source_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt workflow/skill/tool selection matrix"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 203 Workflow/Skill/Tool Selection Matrix",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Matrix records: `{summary.get('matrix_record_count')}`",
        f"- Registry gaps: `{summary.get('registered_gap_count')}`",
        f"- Phase 151 explainability covered: `{summary.get('phase151_explainability_covered_count')}`",
        f"- Phase 204 explainability needed: `{summary.get('phase204_explainability_needed_count')}`",
        f"- Holdout proof covered: `{summary.get('holdout_proof_covered_count')}`",
        f"- Holdout proof needed: `{summary.get('holdout_proof_needed_count')}`",
        f"- Non-Coinbase proof rows: `{summary.get('non_coinbase_proof_row_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Matrix",
        "",
        "| Entry | Family | Workflow | Skills | Tools | Phase 204 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in object_list(report.get("matrix_records")):
        lines.append(
            "| `{entry}` | `{family}` | `{workflow}` | {skills} | {tools} | `{status}` |".format(
                entry=record.get("entry_id"),
                family=record.get("prompt_family"),
                workflow=record.get("expected_workflow"),
                skills=", ".join(string_list(record.get("selected_skill_ids"))) or "none",
                tools=", ".join(string_list(record.get("selected_tool_ids"))) or "none",
                status=record.get("phase151_explainability_status"),
            )
        )
    return "\n".join(lines) + "\n"


def run_workflow_skill_tool_selection_matrix(config: WorkflowSkillToolSelectionMatrixConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, source_errors = load_sources(config_root, policy)
    report = build_workflow_skill_tool_selection_matrix_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_errors=source_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_workflow_skill_tool_selection_matrix_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_errors=source_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = SelectionMatrixStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "workflow_skill_tool_selection_matrix")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase204_ready"] = False
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
