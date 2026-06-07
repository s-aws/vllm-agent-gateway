"""Executable skill eval catalog validation."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.skills.registry import (
    MUTATION_POLICIES,
    SCHEMA_VERSION,
    WORKFLOW_MUTATION_POLICY_ALLOWLIST,
    SkillRegistryError,
    load_skill_registry,
    read_json_object,
    registry_ids,
    validate_eval_case_item,
)


SKILL_EVALS_PATH = Path("runtime") / "skill_evals.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-evals"
ALLOWED_LIVE_SUITES = {
    "skill_registry_contract",
    "workflow_router_l1_suite",
    "workflow_router_l2_suite",
    "workflow_router_natural_clients",
}
METADATA_ONLY_LIVE_SUITES = {"skill_registry_contract"}
MANUAL_ARTIFACT_IDS = {
    "route_decision",
}
LIVE_SUITE_CASE_MAP = {
    "workflow_router_l1_suite": {
        "l1_read_only_context": "L1-001",
        "l1_explain_code": "L1-002",
        "l1_related_tests": "L1-003",
        "l1_configuration_lookup": "L1-004",
        "l1_test_failure_summary": "L1-005",
        "l1_behavior_exists": "L1-006",
        "l1_callers_usages": "L1-007",
        "l1_callers_usages_summary": "L1-007",
        "l1_safe_test_command": "L1-008",
        "l1_draft_packet_design": "L1-010",
        "l1_endpoint_route_lookup": "L1-012",
        "l1_message_source_lookup": "L1-013",
        "l1_module_summary": "L1-014",
        "l1_data_model_lookup": "L1-015",
        "l1_dependency_lookup": "L1-016",
        "l1_coverage_gap_summary": "L1-017",
        "l1_documentation_lookup": "L1-018",
        "l1_cli_entrypoint_lookup": "L1-019",
        "l1_configuration_effect_summary": "L1-020",
        "l1_local_change_summary": "L1-021",
        "d1_config_default_test": "D1-004",
        "d1_message_assertion_test": "D1-005",
        "d1_test_assertion_update": "D1-006",
    },
    "workflow_router_l2_suite": {
        "l2_failing_test_diagnosis": "L2-001",
        "l2_multi_file_behavior": "L2-002",
        "l2_dependency_impact": "L2-003",
        "l2_dependency_impact_summary": "L2-003",
        "l2_test_selection": "L2-005",
        "l2_test_selection_rationale": "L2-005",
        "l2_runtime_error_diagnosis": "L2-006",
        "l2_request_flow_map": "L2-007",
        "l2_code_path_comparison": "L2-008",
        "l2_change_surface_summary": "L2-009",
        "l2_ci_log_triage": "L2-010",
        "l2_table_read_write_lookup": "L2-011",
        "l2_runtime_reproduction_checklist": "L2-012",
        "l2_user_facing_message_test_target": "L2-013",
    },
}
LIVE_SUITE_SCRIPT_MAP = {
    "workflow_router_l1_suite": Path("scripts") / "validate_workflow_router_l1_suite.py",
    "workflow_router_l2_suite": Path("scripts") / "validate_workflow_router_l2_suite.py",
}
LIVE_TARGETS = {"metadata", "gateway", "gateway_and_anythingllm"}
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"skill-evals-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def workflow_result_artifacts(workflows_manifest: dict[str, Any]) -> set[str]:
    artifacts: set[str] = set()
    workflows = workflows_manifest.get("workflows")
    if not isinstance(workflows, list):
        raise SkillRegistryError("runtime/workflows.json must contain a workflows list.")
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        for action in workflow.get("controller_actions") or []:
            if not isinstance(action, dict):
                continue
            result_artifacts = action.get("result_artifacts")
            if isinstance(result_artifacts, list):
                artifacts.update(item for item in result_artifacts if isinstance(item, str))
    return artifacts


def skill_output_artifacts(skill_registry: dict[str, dict[str, Any]]) -> set[str]:
    artifacts: set[str] = set()
    for skill in skill_registry.values():
        contract = skill.get("capability_contract")
        if not isinstance(contract, dict):
            continue
        output_artifacts = contract.get("output_artifacts")
        if isinstance(output_artifacts, list):
            artifacts.update(item for item in output_artifacts if isinstance(item, str))
    return artifacts


def live_mapping_for_case(case: dict[str, Any]) -> dict[str, Any]:
    live_suite = case["live_suite"]
    if live_suite in METADATA_ONLY_LIVE_SUITES:
        return {
            "status": "metadata_only",
            "live_suite": live_suite,
            "reason": "case is validated by catalog and registry contract checks",
        }
    case_map = LIVE_SUITE_CASE_MAP.get(live_suite)
    if not case_map:
        return {
            "status": "not_mapped",
            "live_suite": live_suite,
            "reason": "live suite does not expose per-case L1/L2 mapping in the eval runner",
        }
    live_case_id = case_map.get(case["id"])
    if not live_case_id:
        return {
            "status": "not_mapped",
            "live_suite": live_suite,
            "reason": f"eval case {case['id']} is not mapped to {live_suite}",
        }
    return {
        "status": "mapped",
        "live_suite": live_suite,
        "script": str(LIVE_SUITE_SCRIPT_MAP[live_suite]).replace("\\", "/"),
        "case_id": live_case_id,
    }


def validate_fixture_items(fixtures: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(fixtures, list):
        return [], ["runtime/skill_evals.json must contain a fixtures list."]
    fixture_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict) or not isinstance(fixture.get("id"), str) or not fixture["id"].strip():
            errors.append(f"fixtures[{index}] must include a non-empty id.")
            continue
        fixture_id = fixture["id"]
        if fixture_id in fixture_ids:
            errors.append(f"Duplicate skill eval fixture id: {fixture_id}")
            continue
        fixture_ids.add(fixture_id)
        for field in ("description", "expected_behavior"):
            if not isinstance(fixture.get(field), str) or not fixture[field].strip():
                errors.append(f"fixture {fixture_id}.{field} must be a non-empty string.")
        validated.append(dict(fixture))
    return validated, errors


def validate_case_against_catalog(
    raw_case: Any,
    *,
    workflow_ids: set[str],
    known_artifacts: set[str],
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        case = validate_eval_case_item(raw_case, workflow_ids=workflow_ids)
    except SkillRegistryError as exc:
        case_id = raw_case.get("id") if isinstance(raw_case, dict) else "<unknown>"
        return {
            "case_id": str(case_id),
            "status": "failed",
            "errors": [str(exc)],
            "live_mapping": {"status": "not_checked"},
        }

    live_suite = case["live_suite"]
    if live_suite not in ALLOWED_LIVE_SUITES:
        errors.append(
            f"Skill eval case {case['id']} has unsupported live_suite {live_suite!r}; "
            f"allowed values: {', '.join(sorted(ALLOWED_LIVE_SUITES))}"
        )
    unknown_artifacts = sorted(set(case["expected_artifacts"]) - known_artifacts)
    if unknown_artifacts:
        errors.append(
            f"Skill eval case {case['id']} references unknown expected_artifacts: "
            f"{', '.join(unknown_artifacts)}"
        )
    allowed_mutation_policies = WORKFLOW_MUTATION_POLICY_ALLOWLIST.get(case["expected_workflow"], MUTATION_POLICIES)
    if case["mutation_policy"] not in allowed_mutation_policies:
        errors.append(
            f"Skill eval case {case['id']} mutation_policy {case['mutation_policy']!r} is not allowed "
            f"for workflow {case['expected_workflow']!r}."
        )

    return {
        "case_id": case["id"],
        "prompt_family": case["prompt_family"],
        "expected_workflow": case["expected_workflow"],
        "expected_artifacts": case["expected_artifacts"],
        "mutation_policy": case["mutation_policy"],
        "live_suite": live_suite,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "live_mapping": live_mapping_for_case(case) if not errors else {"status": "not_checked"},
    }


def build_skill_eval_report(
    config_root: Path,
    *,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    requested_case_ids = set(case_ids or [])
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_eval_runner_report",
        "mode": "metadata",
        "status": "failed",
        "config_root": str(config_root),
        "catalog_path": str((config_root / SKILL_EVALS_PATH).resolve()),
        "summary": {
            "fixture_count": 0,
            "case_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "requested_case_ids": sorted(requested_case_ids),
        },
        "checks": [],
        "errors": [],
    }
    try:
        workflow_ids = registry_ids(config_root / "runtime" / "workflows.json", "workflows")
        workflows_manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
        skill_registry = load_skill_registry(config_root)
        known_artifacts = workflow_result_artifacts(workflows_manifest) | skill_output_artifacts(skill_registry) | MANUAL_ARTIFACT_IDS
        manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            report["errors"].append("runtime/skill_evals.json schema_version must be 1.")
        if manifest.get("kind") != "skill_eval_fixture_registry":
            report["errors"].append("runtime/skill_evals.json kind must be skill_eval_fixture_registry.")

        fixtures, fixture_errors = validate_fixture_items(manifest.get("fixtures"))
        report["summary"]["fixture_count"] = len(fixtures)
        report["errors"].extend(fixture_errors)
        raw_cases = manifest.get("cases")
        if not isinstance(raw_cases, list):
            report["errors"].append("runtime/skill_evals.json cases must be a list.")
            raw_cases = []

        seen_case_ids: set[str] = set()
        selected_raw_cases: list[Any] = []
        for raw_case in raw_cases:
            raw_case_id = raw_case.get("id") if isinstance(raw_case, dict) else None
            if isinstance(raw_case_id, str):
                if raw_case_id in seen_case_ids:
                    report["errors"].append(f"Duplicate skill eval case id: {raw_case_id}")
                seen_case_ids.add(raw_case_id)
            if requested_case_ids and raw_case_id not in requested_case_ids:
                continue
            selected_raw_cases.append(raw_case)

        missing_requested = sorted(requested_case_ids - seen_case_ids)
        if missing_requested:
            report["errors"].append(f"Requested skill eval case id(s) not found: {', '.join(missing_requested)}")

        checks = [
            validate_case_against_catalog(raw_case, workflow_ids=workflow_ids, known_artifacts=known_artifacts)
            for raw_case in selected_raw_cases
        ]
        report["checks"] = checks
        report["summary"]["case_count"] = len(checks)
        report["summary"]["passed_count"] = sum(1 for check in checks if check["status"] == "passed")
        report["summary"]["failed_count"] = sum(1 for check in checks if check["status"] == "failed")
        live_suite_counts: dict[str, int] = {}
        for check in checks:
            live_suite = check.get("live_suite")
            if isinstance(live_suite, str):
                live_suite_counts[live_suite] = live_suite_counts.get(live_suite, 0) + 1
        report["summary"]["live_suite_counts"] = live_suite_counts
    except SkillRegistryError as exc:
        report["errors"].append(str(exc))
    except OSError as exc:
        report["errors"].append(f"Could not read skill eval catalog inputs: {exc}")

    has_case_failures = any(check.get("status") == "failed" for check in report["checks"])
    report["status"] = "failed" if report["errors"] or has_case_failures else "passed"
    return report


def live_suite_commands(
    config_root: Path,
    checks: list[dict[str, Any]],
    *,
    live_target: str,
    target_roots: list[str],
    workflow_router_gateway_base_url: str,
    anythingllm_api_base_url: str,
    workspace: str,
    api_key_env: str,
    timeout_seconds: int,
    python_executable: str | None = None,
) -> list[dict[str, Any]]:
    if live_target not in LIVE_TARGETS:
        raise SkillRegistryError(f"Unsupported live target: {live_target}")
    if live_target == "metadata":
        return []
    python = python_executable or sys.executable
    grouped: dict[str, set[str]] = {}
    for check in checks:
        mapping = check.get("live_mapping")
        if not isinstance(mapping, dict) or mapping.get("status") != "mapped":
            continue
        suite = str(mapping["live_suite"])
        case_id = str(mapping["case_id"])
        grouped.setdefault(suite, set()).add(case_id)

    commands: list[dict[str, Any]] = []
    for suite, case_ids in sorted(grouped.items()):
        script = config_root / LIVE_SUITE_SCRIPT_MAP[suite]
        command = [
            python,
            str(script),
            "--workflow-router-gateway-base-url",
            workflow_router_gateway_base_url,
            "--anythingllm-api-base-url",
            anythingllm_api_base_url,
            "--workspace",
            workspace,
            "--api-key-env",
            api_key_env,
            "--timeout-seconds",
            str(timeout_seconds),
        ]
        for target_root in target_roots:
            command.extend(["--target-root", target_root])
        for case_id in sorted(case_ids):
            command.extend(["--case-id", case_id])
        if live_target == "gateway":
            command.append("--skip-anythingllm")
        commands.append(
            {
                "suite": suite,
                "case_ids": sorted(case_ids),
                "command": command,
                "status": "planned",
            }
        )
    return commands


def execute_live_suite_commands(commands: list[dict[str, Any]], *, timeout_seconds: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in commands:
        command = item["command"]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        results.append(
            {
                **item,
                "status": "passed" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        )
    return results


def run_skill_eval_catalog(
    config_root: Path,
    *,
    output_path: Path | None = None,
    case_ids: list[str] | None = None,
    live_target: str = "metadata",
    execute_live: bool = False,
    target_roots: list[str] | None = None,
    workflow_router_gateway_base_url: str = "http://127.0.0.1:8500/v1",
    anythingllm_api_base_url: str = "http://127.0.0.1:3001",
    workspace: str = "my-workspace",
    api_key_env: str = "ANYTHINGLLM_API_KEY",
    timeout_seconds: int = 900,
    python_executable: str | None = None,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    report = build_skill_eval_report(config_root, case_ids=case_ids)
    if live_target != "metadata":
        report["mode"] = "live"
        if report["status"] == "passed":
            commands = live_suite_commands(
                config_root,
                list(report["checks"]),
                live_target=live_target,
                target_roots=target_roots or DEFAULT_TARGET_ROOTS,
                workflow_router_gateway_base_url=workflow_router_gateway_base_url,
                anythingllm_api_base_url=anythingllm_api_base_url,
                workspace=workspace,
                api_key_env=api_key_env,
                timeout_seconds=timeout_seconds,
                python_executable=python_executable,
            )
            report["live_suite_runs"] = (
                execute_live_suite_commands(commands, timeout_seconds=timeout_seconds) if execute_live else commands
            )
            if execute_live and any(item.get("status") == "failed" for item in report["live_suite_runs"]):
                report["status"] = "failed"
        else:
            report["live_suite_runs"] = []
    path = output_path or default_report_path(config_root)
    write_json(path, report)
    report["report_path"] = str(path.resolve())
    write_json(path, report)
    return report
