"""Phase 230 small skill admission pilot validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import dict_value, object_list, read_json_object, string_list, write_json


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "small_skill_admission_pilot_policy"
EXPECTED_REPORT_KIND = "small_skill_admission_pilot_report"
EXPECTED_PHASE = 230
EXPECTED_BACKLOG_ID = "P0-M12-230"
EXPECTED_MILESTONE_IDS = {"M12"}
DEFAULT_POLICY_PATH = Path("runtime") / "small_skill_admission_pilot_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "skill-library-scaling" / "phase230" / "phase230-small-skill-admission-pilot-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "skill-library-scaling" / "phase230" / "phase230-small-skill-admission-pilot-report.md"
PROMPT_COVERAGE_PATH = Path("runtime") / "prompt_skill_coverage.json"
SKILL_EVALS_PATH = Path("runtime") / "skill_evals.json"


@dataclass(frozen=True)
class SmallSkillAdmissionPilotConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True
    live_report_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def validation_error(error_id: str, message: str) -> dict[str, str]:
    return {"id": error_id, "message": message}


def load_optional(
    config_root: Path,
    raw_path: object,
    *,
    required: bool,
    error_id: str,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, {}, [validation_error(f"{error_id}.path", "path is required")]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        if required:
            return path, {}, [validation_error(f"{error_id}.missing", f"required artifact missing: {path}")]
        return path, {}, []
    return path, read_json_object(path), []


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 230"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M12"))
    precondition = dict_value(policy.get("phase229_precondition"))
    for key in ("report_path", "required_status", "required_candidate_id"):
        if not isinstance(precondition.get(key), str) or not str(precondition[key]).strip():
            errors.append(validation_error(f"policy.phase229_precondition.{key}", f"{key} is required"))
    if precondition.get("required_phase230_ready") is not True:
        errors.append(validation_error("policy.phase229_precondition.required_phase230_ready", "must be true"))
    candidate = dict_value(policy.get("candidate"))
    expected_candidate = {
        "id": "FX-001",
        "required_status": "implemented",
        "expected_level": "fixture",
        "expected_selected_workflow": "code_investigation.plan",
        "expected_route_rule": "l1_endpoint_route_lookup_terms",
        "no_new_runtime_skill_required": True,
        "manual_skill_injection_allowed": False,
        "mutation_policy": "read_only_no_source_mutation",
    }
    for key, expected in expected_candidate.items():
        if candidate.get(key) != expected:
            errors.append(validation_error(f"policy.candidate.{key}", f"{key} must be {expected!r}"))
    required_lists = {
        "expected_additional_route_rules": ["l1_data_model_lookup_terms"],
        "expected_skill_ids": ["endpoint-route-locator", "data-model-schema-locator"],
        "expected_tool_ids": ["git_grep", "read_file", "structure_index"],
        "expected_eval_case_ids": [
            "phase230_python_service_endpoint_route_lookup",
            "phase230_python_service_data_model_lookup",
        ],
        "expected_validation_suites": ["multi_repo_fixture_suite", "small_skill_admission_pilot_suite"],
        "expected_live_case_ids": ["python-service-endpoint-route-lookup", "python-service-schema-lookup"],
    }
    for key, expected in required_lists.items():
        if string_list(candidate.get(key)) != expected:
            errors.append(validation_error(f"policy.candidate.{key}", f"{key} must be {expected!r}"))
    blind = dict_value(policy.get("blind_baseline"))
    if not isinstance(blind.get("path"), str) or not blind["path"].strip():
        errors.append(validation_error("policy.blind_baseline.path", "blind baseline path is required"))
    if blind.get("required_status") != "accepted":
        errors.append(validation_error("policy.blind_baseline.required_status", "required_status must be accepted"))
    if set(string_list(blind.get("required_prompts"))) != {"python-service-endpoint-route-lookup", "python-service-schema-lookup"}:
        errors.append(validation_error("policy.blind_baseline.required_prompts", "blind baseline must cover both Phase 230 prompts"))
    live = dict_value(policy.get("live_proof"))
    if not isinstance(live.get("report_path"), str) or not live["report_path"].strip():
        errors.append(validation_error("policy.live_proof.report_path", "live report path is required"))
    if live.get("required_status") != "passed":
        errors.append(validation_error("policy.live_proof.required_status", "required_status must be passed"))
    if set(string_list(live.get("required_clients"))) != {"gateway", "anythingllm"}:
        errors.append(validation_error("policy.live_proof.required_clients", "live proof must require gateway and AnythingLLM"))
    if policy.get("acceptance_marker") != "PHASE230 SMALL SKILL ADMISSION PILOT PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 230"))
    return errors


def validate_phase229_precondition(policy: dict[str, Any], phase229_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase229_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase229_precondition"))
    summary = dict_value(phase229_report.get("summary"))
    if phase229_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase229.status", "Phase 229 report status must be passed"))
    if summary.get("phase230_ready") is not precondition.get("required_phase230_ready"):
        errors.append(validation_error("phase229.phase230_ready", "Phase 229 report must mark phase230_ready"))
    if summary.get("phase230_recommended_candidate_id") != precondition.get("required_candidate_id"):
        errors.append(validation_error("phase229.candidate", "Phase 229 report must recommend FX-001"))
    return errors


def entry_by_id(registry: dict[str, Any], entry_id: str) -> dict[str, Any]:
    for entry in object_list(registry.get("entries")):
        if entry.get("id") == entry_id:
            return entry
    return {}


def validate_candidate_entry(policy: dict[str, Any], coverage: dict[str, Any], evals: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    candidate = dict_value(policy.get("candidate"))
    entry = entry_by_id(coverage, str(candidate.get("id") or ""))
    if not entry:
        return [validation_error("coverage.candidate", "FX-001 prompt coverage entry is required")]
    field_pairs = {
        "status": candidate.get("required_status"),
        "level": candidate.get("expected_level"),
        "selected_workflow": candidate.get("expected_selected_workflow"),
        "route_rule": candidate.get("expected_route_rule"),
    }
    for field, expected in field_pairs.items():
        if entry.get(field) != expected:
            errors.append(validation_error(f"coverage.{field}", f"FX-001 {field} must be {expected!r}"))
    list_pairs = {
        "additional_route_rules": string_list(candidate.get("expected_additional_route_rules")),
        "skill_ids": string_list(candidate.get("expected_skill_ids")),
        "tool_ids": string_list(candidate.get("expected_tool_ids")),
        "eval_case_ids": string_list(candidate.get("expected_eval_case_ids")),
        "validation_suites": string_list(candidate.get("expected_validation_suites")),
    }
    for field, expected in list_pairs.items():
        actual = string_list(entry.get(field))
        if actual != expected:
            errors.append(validation_error(f"coverage.{field}", f"FX-001 {field} must be {expected!r}; actual={actual!r}"))
    fixture_targets = object_list(entry.get("fixture_targets"))
    if not fixture_targets:
        errors.append(validation_error("coverage.fixture_targets", "FX-001 must include fixture target metadata"))
    else:
        fixture = fixture_targets[0]
        if fixture.get("fixture_id") != candidate.get("expected_fixture_id"):
            errors.append(validation_error("coverage.fixture_targets.fixture_id", "FX-001 fixture target must be python-service-generalization"))
        if fixture.get("admission_phase") != EXPECTED_PHASE:
            errors.append(validation_error("coverage.fixture_targets.admission_phase", "FX-001 fixture target must record admission phase 230"))
        if fixture.get("read_only") is not True:
            errors.append(validation_error("coverage.fixture_targets.read_only", "FX-001 fixture target must be read-only"))
        if string_list(fixture.get("live_case_ids")) != string_list(candidate.get("expected_live_case_ids")):
            errors.append(validation_error("coverage.fixture_targets.live_case_ids", "FX-001 fixture target must list the Phase 230 live cases"))
    eval_entries = {str(item.get("id")): item for item in object_list(evals.get("cases"))}
    for eval_case_id in string_list(candidate.get("expected_eval_case_ids")):
        eval_case = eval_entries.get(eval_case_id)
        if not eval_case:
            errors.append(validation_error(f"evals.{eval_case_id}", "expected Phase 230 eval case is missing"))
            continue
        if eval_case.get("expected_workflow") != candidate.get("expected_selected_workflow"):
            errors.append(validation_error(f"evals.{eval_case_id}.expected_workflow", "eval case workflow must match FX-001 workflow"))
        if eval_case.get("mutation_policy") != "no_repository_mutation":
            errors.append(validation_error(f"evals.{eval_case_id}.mutation_policy", "eval case must be no_repository_mutation"))
        if eval_case.get("live_suite") != "multi_repo_fixture_suite":
            errors.append(validation_error(f"evals.{eval_case_id}.live_suite", "eval case must use the multi-repo fixture suite"))
    return errors


def validate_blind_baseline(policy: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, str]]:
    if not baseline:
        return []
    errors: list[dict[str, str]] = []
    required = set(string_list(dict_value(policy.get("blind_baseline")).get("required_prompts")))
    prompts = {str(item.get("case_id")): item for item in object_list(baseline.get("prompts"))}
    if baseline.get("status") != dict_value(policy.get("blind_baseline")).get("required_status"):
        errors.append(validation_error("blind_baseline.status", "blind baseline must be accepted"))
    missing = sorted(required - set(prompts))
    if missing:
        errors.append(validation_error("blind_baseline.prompts", f"blind baseline missing prompt(s): {missing}"))
    for case_id in sorted(required & set(prompts)):
        prompt = prompts[case_id]
        if not string_list(prompt.get("must_have_facts")):
            errors.append(validation_error(f"blind_baseline.{case_id}.must_have_facts", "must-have facts are required"))
        if not string_list(prompt.get("evidence_expectations")):
            errors.append(validation_error(f"blind_baseline.{case_id}.evidence_expectations", "evidence expectations are required"))
        if not string_list(prompt.get("pass_criteria")):
            errors.append(validation_error(f"blind_baseline.{case_id}.pass_criteria", "pass criteria are required"))
    return errors


def validate_live_proof(policy: dict[str, Any], live_report: dict[str, Any]) -> list[dict[str, str]]:
    if not live_report:
        return []
    errors: list[dict[str, str]] = []
    live = dict_value(policy.get("live_proof"))
    required_clients = set(string_list(live.get("required_clients")))
    required_case_ids = set(string_list(live.get("required_case_ids")))
    expected_artifacts = dict_value(live.get("expected_artifacts"))
    expected_route_hints = dict_value(live.get("expected_route_hints"))
    expected_markers = {case_id: string_list(markers) for case_id, markers in dict_value(live.get("expected_artifact_markers")).items()}
    cases = object_list(live_report.get("cases"))
    if live_report.get("status") != live.get("required_status"):
        errors.append(validation_error("live_report.status", "live report must be passed"))
    by_case_client = {(str(case.get("case_id")), str(case.get("client"))): case for case in cases}
    for case_id in sorted(required_case_ids):
        for client in sorted(required_clients):
            item = by_case_client.get((case_id, client))
            if not item:
                errors.append(validation_error(f"live_report.{case_id}.{client}", "required live case/client proof is missing"))
                continue
            if item.get("status") != "passed":
                errors.append(validation_error(f"live_report.{case_id}.{client}.status", "live case status must be passed"))
            if item.get("expected_artifact") != expected_artifacts.get(case_id):
                errors.append(validation_error(f"live_report.{case_id}.{client}.artifact", "live case expected artifact mismatch"))
            if item.get("expected_route_hint") != expected_route_hints.get(case_id):
                errors.append(validation_error(f"live_report.{case_id}.{client}.route_hint", "live case route hint mismatch"))
            if item.get("source_unchanged") is not True:
                errors.append(validation_error(f"live_report.{case_id}.{client}.source_unchanged", "live case must keep source unchanged"))
            marker_status = dict_value(item.get("artifact_marker_status"))
            if expected_markers.get(case_id):
                actual_markers = string_list(marker_status.get("required"))
                missing_expected_markers = [marker for marker in expected_markers[case_id] if marker not in actual_markers]
                if missing_expected_markers:
                    errors.append(
                        validation_error(
                            f"live_report.{case_id}.{client}.artifact_markers",
                            f"artifact marker proof missing expected marker(s): {missing_expected_markers}",
                        )
                    )
                if string_list(marker_status.get("missing")):
                    errors.append(validation_error(f"live_report.{case_id}.{client}.artifact_markers_missing", "artifact markers must not be missing"))
            skills = string_list(item.get("selected_skills"))
            if case_id == "python-service-endpoint-route-lookup" and "endpoint-route-locator" not in skills:
                errors.append(validation_error(f"live_report.{case_id}.{client}.selected_skills", "endpoint route case must select endpoint-route-locator"))
            if case_id == "python-service-schema-lookup" and "data-model-schema-locator" not in skills:
                errors.append(validation_error(f"live_report.{case_id}.{client}.selected_skills", "schema case must select data-model-schema-locator"))
    clients_seen = {str(case.get("client")) for case in cases if isinstance(case.get("client"), str)}
    missing_clients = sorted(required_clients - clients_seen)
    if missing_clients:
        errors.append(validation_error("live_report.clients", f"live report missing client(s): {missing_clients}"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Small Skill Admission Pilot",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Candidate: `{summary.get('candidate_id')}`",
        f"- Live case count: `{summary.get('live_case_count')}`",
        f"- Client case count: `{summary.get('client_case_count')}`",
        f"- Phase 231 ready: `{summary.get('phase231_ready')}`",
    ]
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def validate_small_skill_admission_pilot(config: SmallSkillAdmissionPilotConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)
    phase229_path, phase229_report, phase229_errors = load_optional(
        config_root,
        dict_value(policy.get("phase229_precondition")).get("report_path"),
        required=config.require_artifacts,
        error_id="phase229_report",
    )
    validation_errors.extend(phase229_errors)
    validation_errors.extend(validate_phase229_precondition(policy, phase229_report))
    coverage_path = config_root / PROMPT_COVERAGE_PATH
    evals_path = config_root / SKILL_EVALS_PATH
    coverage = read_json_object(coverage_path)
    evals = read_json_object(evals_path)
    validation_errors.extend(validate_candidate_entry(policy, coverage, evals))
    baseline_path, baseline, baseline_errors = load_optional(
        config_root,
        dict_value(policy.get("blind_baseline")).get("path"),
        required=True,
        error_id="blind_baseline",
    )
    validation_errors.extend(baseline_errors)
    validation_errors.extend(validate_blind_baseline(policy, baseline))
    live_path, live_report, live_errors = load_optional(
        config_root,
        str(config.live_report_path)
        if config.live_report_path
        else dict_value(policy.get("live_proof")).get("report_path"),
        required=config.require_artifacts,
        error_id="live_report",
    )
    validation_errors.extend(live_errors)
    validation_errors.extend(validate_live_proof(policy, live_report))
    live_cases = object_list(live_report.get("cases"))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not validation_errors else "failed",
        "policy_path": str(policy_path),
        "phase229_report_path": str(phase229_path) if phase229_path else None,
        "prompt_coverage_path": str(coverage_path),
        "skill_evals_path": str(evals_path),
        "blind_baseline_path": str(baseline_path) if baseline_path else None,
        "live_report_path": str(live_path) if live_path else None,
        "validation_errors": validation_errors,
        "summary": {
            "candidate_id": dict_value(policy.get("candidate")).get("id"),
            "candidate_status": entry_by_id(coverage, "FX-001").get("status"),
            "client_case_count": len(live_cases),
            "live_case_count": len({str(item.get("case_id")) for item in live_cases}),
            "clients": sorted({str(item.get("client")) for item in live_cases if isinstance(item.get("client"), str)}),
            "phase231_ready": not validation_errors,
        },
    }
    write_json(output_path, report)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(render_markdown(report), encoding="utf-8")
    return report
