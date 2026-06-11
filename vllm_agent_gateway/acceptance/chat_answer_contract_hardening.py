"""Phase 180 chat answer contract hardening gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import (
    ControllerOutputFormat,
    assistant_content_for_controller_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chat_answer_contract_hardening_policy"
EXPECTED_REPORT_KIND = "chat_answer_contract_hardening_report"
EXPECTED_PHASE = 180
EXPECTED_BACKLOG_ID = "P0-BB-044"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_answer_contract_hardening_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase180" / "phase180-chat-answer-contract-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase180" / "phase180-chat-answer-contract-report.md"
DEFAULT_FIXTURE_ROOT = Path("runtime-state") / "phase180" / "chat-answer-contract-fixtures"
REQUIRED_WORKFLOW_FAMILIES = {
    "read_only_investigation",
    "schema_evidence",
    "request_flow",
    "change_boundary",
    "generic_chat",
    "format_selected_output",
}


class ChatAnswerContractStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ChatAnswerContractHardeningConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    fixture_root: Path = DEFAULT_FIXTURE_ROOT


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def contains(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append({"id": "policy.schema_version", "severity": "high", "message": "policy.schema_version must be 1"})
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append({"id": "policy.kind", "severity": "high", "message": f"policy.kind must be {EXPECTED_POLICY_KIND}"})
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append({"id": "policy.phase", "severity": "high", "message": "policy.phase must be 180"})
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append({"id": "policy.priority_backlog_id", "severity": "high", "message": f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"})
    if policy.get("acceptance_marker") != "PHASE180 CHAT ANSWER CONTRACT PASS":
        errors.append({"id": "policy.acceptance_marker", "severity": "high", "message": "policy.acceptance_marker must be PHASE180 CHAT ANSWER CONTRACT PASS"})

    cases = object_list(policy.get("cases"))
    if not cases:
        errors.append({"id": "policy.cases", "severity": "high", "message": "policy.cases must be non-empty"})
        return errors
    case_ids: set[str] = set()
    families: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"policy.cases[{index}]"
        case_id = case.get("case_id")
        family = case.get("workflow_family")
        if not isinstance(case_id, str) or not case_id:
            errors.append({"id": f"{prefix}.case_id", "severity": "high", "message": "case_id is required"})
        elif case_id in case_ids:
            errors.append({"id": f"{prefix}.case_id", "severity": "high", "message": f"duplicate case_id {case_id}"})
        else:
            case_ids.add(case_id)
        if not isinstance(family, str) or not family:
            errors.append({"id": f"{prefix}.workflow_family", "severity": "high", "message": "workflow_family is required"})
        else:
            families.add(family)
        if case.get("expected_output_formats") != ["format_a", "json"]:
            errors.append({"id": f"{prefix}.expected_output_formats", "severity": "high", "message": "expected_output_formats must be ['format_a', 'json']"})
        for field in ("required_format_a_markers", "required_json_markers"):
            if not string_list(case.get(field)):
                errors.append({"id": f"{prefix}.{field}", "severity": "high", "message": f"{field} must be a non-empty string list"})
        if case.get("contract_kind") not in {"inline", "primary"}:
            errors.append({"id": f"{prefix}.contract_kind", "severity": "high", "message": "contract_kind must be inline or primary"})
    missing_families = sorted(REQUIRED_WORKFLOW_FAMILIES - families)
    if missing_families:
        errors.append({"id": "policy.workflow_families", "severity": "high", "message": "missing workflow families: " + ", ".join(missing_families)})
    if not any(case.get("negative_artifact_only_guard") is True for case in cases):
        errors.append({"id": "policy.negative_artifact_only_guard", "severity": "high", "message": "at least one case must guard against artifact-only output"})
    return errors


def route_decision(selected_workflow: str, *, rule: str = "phase180_contract_fixture") -> dict[str, Any]:
    return {
        "kind": "workflow_route_decision",
        "selected_workflow": selected_workflow,
        "selected_skills": ["phase180-contract-skill"],
        "selected_tools": ["structure_index", "git_grep", "read_file"],
        "next_action": "execute_read_only",
        "evidence": [{"source": "router_rule", "rule": rule}],
    }


def base_response(case: dict[str, Any], fixture_dir: Path, artifacts: dict[str, str]) -> dict[str, Any]:
    route_path = fixture_dir / "route-decision.json"
    route_rule = str(case.get("route_rule") or "phase180_contract_fixture")
    write_json(
        route_path,
        route_decision(str(case.get("expected_selected_workflow") or "code_investigation.plan"), rule=route_rule),
    )
    return {
        "run_id": f"phase180-{case['case_id']}",
        "workflow": "workflow_router.plan",
        "status": "completed",
        "summary": {
            "selected_workflow": case.get("expected_selected_workflow"),
            "downstream_status": "completed",
            "next_action": "none",
            "verification_command_count": 1,
        },
        "artifacts": {"route_decision": str(route_path), **artifacts},
        "warning_count": 0,
        "warnings": [],
        "failure_count": 0,
        "failures": [],
        "run_lookup": f"/v1/controller/runs/phase180-{case['case_id']}",
    }


def synthetic_response_for_case(case: dict[str, Any], fixture_root: Path) -> dict[str, Any]:
    case_id = str(case["case_id"])
    family = str(case["workflow_family"])
    fixture_dir = fixture_root / case_id
    fixture_dir.mkdir(parents=True, exist_ok=True)

    if family == "read_only_investigation":
        artifact = {
            "kind": "code_investigation_plan",
            "status": "ready",
            "likely_beginning_point": {"path": "core/stealth_order_manager.py", "line": 4169},
            "related_tests": [{"path": "tests/unit/test_order_id_and_followup_rules.py", "line": 8}],
            "verification_plan": {
                "verification_commands": [
                    {"command": ["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"]}
                ]
            },
            "mutation_policy": "read_only_no_source_mutation",
        }
        artifact_path = fixture_dir / "investigation-plan.json"
        write_json(artifact_path, artifact)
        return base_response(case, fixture_dir, {"downstream_investigation_plan": str(artifact_path)})

    if family == "schema_evidence":
        artifact = {
            "kind": "data_model_lookup",
            "status": "ready",
            "target": "stealth_orders",
            "fields": [
                {
                    "name": "placed_order_id",
                    "definition": "persisted lookup field for stealth order correlation",
                    "path": "core/models.py",
                    "line": 42,
                    "source": "sql_schema_block",
                }
            ],
            "model_files": ["core/models.py"],
            "reason": "Bounded evidence ties the field to persisted schema, not runtime-only dictionaries.",
            "source_refs": [{"path": "core/models.py", "line": 42}],
            "mutation_policy": "read_only_no_source_mutation",
            "gaps": [],
        }
        artifact_path = fixture_dir / "data-model-lookup.json"
        write_json(artifact_path, artifact)
        return base_response(case, fixture_dir, {"downstream_data_model_lookup": str(artifact_path)})

    if family == "request_flow":
        artifact = {
            "kind": "request_flow_map",
            "status": "ready",
            "target_flow": "placed_order_id order lookup",
            "handler_files": [{"path": "api/orders.py", "line": 77, "role": "handler"}],
            "flow_steps": [
                {"path": "api/orders.py", "line": 77, "role": "request handler"},
                {"path": "core/stealth_order_manager.py", "line": 4169, "role": "lookup"},
            ],
            "related_tests": [{"path": "tests/unit/test_order_id_and_followup_rules.py", "line": 8}],
            "source_refs": [{"path": "api/orders.py", "line": 77}],
            "risks": [{"risk": "missed branch", "level": "medium", "reason": "only bounded handler evidence was inspected"}],
            "verification_commands": [["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"]],
            "mutation_policy": "read_only_no_source_mutation",
        }
        artifact_path = fixture_dir / "request-flow-map.json"
        write_json(artifact_path, artifact)
        return base_response(case, fixture_dir, {"downstream_request_flow_map": str(artifact_path)})

    if family == "change_boundary":
        artifact = {
            "kind": "change_surface_summary",
            "status": "ready",
            "target": "placed_order_id stealth lookup",
            "change_surface_files": [{"path": "core/stealth_order_manager.py", "category": "primary"}],
            "files_to_touch": [{"path": "core/stealth_order_manager.py", "role": "primary", "reason": "owns lookup"}],
            "files_not_to_touch": [{"path": "main.py", "role": "out_of_scope", "reason": "CLI entrypoint is not lookup logic"}],
            "related_tests": [{"path": "tests/unit/test_order_id_and_followup_rules.py", "line": 8}],
            "risk_level": "medium",
            "implementation_status": "not_ready_without_approval",
            "risks": [{"risk": "schema mismatch", "level": "medium", "reason": "persisted and runtime fields must remain separate"}],
            "unknowns": [{"unknown": "full integration path", "reason": "bounded evidence only"}],
            "verification_commands": [["python", "-m", "pytest", "tests/unit/test_order_id_and_followup_rules.py"]],
            "source_refs": [{"path": "core/stealth_order_manager.py", "line": 4169}],
            "mutation_policy": "read_only_no_source_mutation",
            "gaps": [],
        }
        artifact_path = fixture_dir / "change-surface-summary.json"
        write_json(artifact_path, artifact)
        return base_response(case, fixture_dir, {"downstream_change_surface_summary": str(artifact_path)})

    if family == "generic_chat":
        return {
            "run_id": f"phase180-{case_id}",
            "workflow": "workflow_router.plan",
            "status": "completed",
            "summary": {
                "route_status": "general_chat_no_target",
                "selected_workflow": "none",
                "answer": "Hi. Include an allowed target_root path and a concrete coding task. No repository source was changed.",
                "next_action": "Send a prompt with the repository path, symbol, file, error, or behavior to inspect.",
                "source_changed": False,
                "source_tree_changed": False,
            },
            "artifacts": {},
            "warning_count": 0,
            "warnings": [],
            "failure_count": 0,
            "failures": [],
            "run_lookup": f"/v1/controller/runs/phase180-{case_id}",
        }

    if family == "format_selected_output":
        artifact = {
            "kind": "code_explanation",
            "status": "ready",
            "target": {
                "path": "core/stealth_order_manager.py",
                "symbol": "find_stealth_order_by_placed_order_id",
            },
            "summary": "Looks up a stealth order by placed order id using bounded source evidence.",
            "key_inputs": [{"name": "placed_order_id", "role": "lookup key"}],
            "outputs": [{"description": "matching stealth order or None"}],
            "side_effects": [{"kind": "read", "target": "_placed_order_index"}],
            "related_tests": [{"path": "tests/unit/test_order_id_and_followup_rules.py", "line": 8}],
            "source_refs": [{"path": "core/stealth_order_manager.py", "line": 4169}],
        }
        artifact_path = fixture_dir / "code-explanation.json"
        write_json(artifact_path, artifact)
        return base_response(case, fixture_dir, {"downstream_code_explanation": str(artifact_path)})

    if family == "mixed_route_guard":
        response = synthetic_response_for_case({**case, "workflow_family": "read_only_investigation"}, fixture_root)
        cli_path = fixture_root / case_id / "cli-entrypoint-lookup.json"
        write_json(
            cli_path,
            {
                "kind": "cli_entrypoint_lookup",
                "status": "ready",
                "target": "placed_order_id",
                "entrypoints": [{"path": "main.py", "line": 65, "kind": "python_main_guard"}],
                "mutation_policy": "read_only_no_source_mutation",
            },
        )
        response["artifacts"]["downstream_cli_entrypoint_lookup"] = str(cli_path)
        return response

    raise RuntimeError(f"unsupported workflow_family {family!r}")


def parse_json_response(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("assistant JSON response was not an object")
    return parsed


def validate_rendered_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    case_id = str(case["case_id"])
    format_a_text = assistant_content_for_controller_response(response, ControllerOutputFormat.FORMAT_A)
    json_text = assistant_content_for_controller_response(response, ControllerOutputFormat.JSON)
    parsed = parse_json_response(json_text)
    expected_heading = str(case.get("expected_heading") or "")

    for marker in string_list(case.get("required_format_a_markers")):
        if not contains(format_a_text, marker):
            errors.append({"id": f"{case_id}.format_a.{marker}", "severity": "high", "message": f"FormatA missing marker: {marker}"})
    if expected_heading and expected_heading in format_a_text and "Artifacts:" in format_a_text:
        if format_a_text.index(expected_heading) > format_a_text.index("Artifacts:"):
            errors.append({"id": f"{case_id}.format_a.artifact_first", "severity": "critical", "message": "answer heading appears after artifacts"})
    if format_a_text.strip().startswith("Artifacts:"):
        errors.append({"id": f"{case_id}.format_a.artifact_only", "severity": "critical", "message": "FormatA output starts with artifacts"})

    chat_contract = dict_value(parsed.get("chat_contract"))
    if parsed.get("output_format") != "json":
        errors.append({"id": f"{case_id}.json.output_format", "severity": "high", "message": "JSON output_format must be json"})
    if chat_contract.get("selected_workflow") != case.get("expected_selected_workflow"):
        errors.append({"id": f"{case_id}.json.selected_workflow", "severity": "high", "message": "JSON selected workflow did not match policy"})

    contract_kind = case.get("contract_kind")
    contract_text = ""
    if contract_kind == "primary":
        contract = dict_value(parsed.get("primary_answer_contract"))
        if not contract:
            errors.append({"id": f"{case_id}.json.primary_answer_contract", "severity": "high", "message": "JSON missing primary_answer_contract"})
        if contract.get("heading") != expected_heading:
            errors.append({"id": f"{case_id}.json.primary_heading", "severity": "high", "message": "primary answer heading did not match policy"})
        contract_text = str(contract.get("text") or "")
    else:
        contract = dict_value(parsed.get("inline_answer_contract"))
        if not contract:
            errors.append({"id": f"{case_id}.json.inline_answer_contract", "severity": "high", "message": "JSON missing inline_answer_contract"})
        if contract.get("artifact_kind") != case.get("expected_artifact_kind"):
            errors.append({"id": f"{case_id}.json.artifact_kind", "severity": "high", "message": "inline artifact kind did not match policy"})
        if contract.get("heading") != expected_heading:
            errors.append({"id": f"{case_id}.json.inline_heading", "severity": "high", "message": "inline answer heading did not match policy"})
        contract_text = str(contract.get("text") or "")

    for marker in string_list(case.get("required_json_markers")):
        if not contains(contract_text, marker):
            errors.append({"id": f"{case_id}.json.{marker}", "severity": "high", "message": f"JSON answer contract missing marker: {marker}"})

    return {
        "case_id": case_id,
        "workflow_family": case.get("workflow_family"),
        "status": ChatAnswerContractStatus.FAILED.value if errors else ChatAnswerContractStatus.PASSED.value,
        "expected_selected_workflow": case.get("expected_selected_workflow"),
        "expected_heading": expected_heading,
        "format_a_sha256": sha256_text(format_a_text),
        "json_sha256": sha256_text(json_text),
        "format_a_preview": format_a_text[:1200],
        "json_contract_kind": contract_kind,
        "validation_errors": errors,
    }


def build_chat_answer_contract_hardening_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    fixture_root: Path,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    case_reports: list[dict[str, Any]] = []
    if not errors:
        for case in object_list(policy.get("cases")):
            response = synthetic_response_for_case(case, fixture_root)
            case_report = validate_rendered_case(case, response)
            case_reports.append(case_report)
            errors.extend(error for error in case_report["validation_errors"])
    blocking_errors = [error for error in errors if error.get("severity") in {"critical", "high"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ChatAnswerContractStatus.FAILED.value if blocking_errors else ChatAnswerContractStatus.PASSED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "fixture_root": str(fixture_root.resolve()),
        "cases": case_reports,
        "summary": {
            "case_count": len(case_reports),
            "passed_case_count": sum(1 for case in case_reports if case.get("status") == "passed"),
            "failed_case_count": sum(1 for case in case_reports if case.get("status") == "failed"),
            "workflow_family_count": len({case.get("workflow_family") for case in case_reports}),
            "blocking_error_count": len(blocking_errors),
            "next_action": "work Phase 181 next" if not blocking_errors else "repair chat answer contract before Phase 181",
        },
        "validation_errors": errors,
    }


def validate_chat_answer_contract_hardening_report(report: dict[str, Any], *, policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append({"id": "report.kind", "severity": "high", "message": f"report.kind must be {EXPECTED_REPORT_KIND}"})
    if report.get("status") != "passed":
        errors.append({"id": "report.status", "severity": "high", "message": "report must pass"})
    if report.get("phase") != EXPECTED_PHASE:
        errors.append({"id": "report.phase", "severity": "high", "message": "report.phase must be 180"})
    cases = object_list(report.get("cases"))
    policy_cases = object_list(policy.get("cases"))
    if len(cases) != len(policy_cases):
        errors.append({"id": "report.cases", "severity": "high", "message": "report case count must match policy"})
    for case in cases:
        if case.get("status") != "passed":
            errors.append({"id": f"report.{case.get('case_id')}", "severity": "high", "message": "case did not pass"})
    summary = dict_value(report.get("summary"))
    if summary.get("blocking_error_count") != 0:
        errors.append({"id": "report.summary.blocking_error_count", "severity": "high", "message": "blocking_error_count must be zero"})
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Chat Answer Contract Hardening",
        "",
        f"- Status: {report.get('status')}",
        f"- Phase: {report.get('phase')}",
        f"- Backlog: {report.get('priority_backlog_id')}",
        f"- Generated: {report.get('generated_at')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in dict_value(report.get("summary")).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Cases", ""])
    for case in object_list(report.get("cases")):
        lines.append(
            f"- {case.get('case_id')}: {case.get('status')} "
            f"({case.get('workflow_family')}, heading={case.get('expected_heading')})"
        )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        for error in errors:
            lines.append(f"- {error.get('severity')}: {error.get('id')} - {error.get('message')}")
    return "\n".join(lines) + "\n"


def run_chat_answer_contract_hardening(config: ChatAnswerContractHardeningConfig) -> dict[str, Any]:
    policy_path = resolve_path(config.config_root, config.policy_path)
    output_path = resolve_path(config.config_root, config.output_path)
    fixture_root = resolve_path(config.config_root, config.fixture_root)
    policy = read_json_object(policy_path)
    report = build_chat_answer_contract_hardening_report(
        config_root=config.config_root,
        policy=policy,
        fixture_root=fixture_root,
        policy_path=policy_path,
    )
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        markdown_path = resolve_path(config.config_root, config.markdown_output_path)
        write_text(markdown_path, render_markdown(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
