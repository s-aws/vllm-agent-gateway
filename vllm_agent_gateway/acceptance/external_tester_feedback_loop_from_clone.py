"""Phase 243 external-tester feedback loop proof from a release-candidate clone."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_feedback_loop import (
    FounderFeedbackLoopCase,
    load_founder_feedback_loop_cases,
    validate_case_catalog,
    validate_founder_feedback_loop_report,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "external_tester_feedback_loop_from_clone_policy"
EXPECTED_REPORT_KIND = "external_tester_feedback_loop_from_clone_report"
EXPECTED_PHASE = 243
EXPECTED_BACKLOG_ID = "P0-M14-243"
EXPECTED_MILESTONE_IDS = {"M9", "M14"}
DEFAULT_POLICY_PATH = Path("runtime") / "external_tester_feedback_loop_from_clone_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "external-tester-feedback-loop-from-clone"
    / "phase243"
    / "phase243-external-tester-feedback-loop-from-clone-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "external-tester-feedback-loop-from-clone"
    / "phase243"
    / "phase243-external-tester-feedback-loop-from-clone-report.md"
)
REQUIRED_OUTCOMES = {"positive_feedback_no_repair", "targeted_defect_repair_followup"}
REQUIRED_TRACE_TRUE = {
    "artifact_hash_required",
    "target_run_record_required",
    "route_decision_required",
    "request_artifact_required",
    "prompt_hash_required",
    "feedback_run_id_required",
}
REQUIRED_RERUN_TRUE = {
    "blind_baseline_first_required",
    "target_prompt_rerun_required",
    "holdout_prompt_rerun_required",
    "gateway_surface_required",
    "anythingllm_surface_required",
    "fixture_mutation_check_required",
    "rejected_explanations_required",
    "gap_class_comparison_required",
    "artifact_trace_required",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "missing_positive_feedback_record",
    "missing_defect_feedback_record",
    "missing_target_run_id",
    "missing_feedback_run_id",
    "missing_route_decision",
    "missing_prompt_hash",
    "missing_output_artifacts",
    "accepted_repair_without_rerun_contract",
    "rejected_feedback_without_explanation",
    "target_fixture_mutation",
}


@dataclass(frozen=True)
class ExternalTesterFeedbackLoopFromCloneConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_live_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validation_error(error_id: str, message: str, *, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "severity": severity}


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def resolve_artifact_path(raw_path: object) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path)
    if path.exists():
        return path
    if raw_path.startswith("/mnt/") and len(raw_path) > 7 and raw_path[6] == "/":
        drive = raw_path[5].upper()
        translated = Path(f"{drive}:/" + raw_path[7:])
        if translated.exists():
            return translated
    return path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def try_read_json_object(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "path is missing"
    if not path.is_file():
        return {}, f"artifact is missing: {path}"
    try:
        return read_json_object(path), None
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return {}, f"artifact could not be read: {path}: {exc}"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 243"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M9 and M14"))
    if not isinstance(policy.get("cases_path"), str) or not str(policy["cases_path"]).strip():
        errors.append(validation_error("policy.cases_path", "cases_path is required"))
    if not isinstance(policy.get("live_feedback_report_path"), str) or not str(policy["live_feedback_report_path"]).strip():
        errors.append(validation_error("policy.live_feedback_report_path", "live_feedback_report_path is required"))

    source = dict_value(policy.get("release_candidate_source"))
    if source.get("required_source_mode") != "remote_branch_clone":
        errors.append(validation_error("policy.release_candidate_source.required_source_mode", "must be remote_branch_clone"))
    if source.get("disallow_active_workspace") is not True:
        errors.append(validation_error("policy.release_candidate_source.disallow_active_workspace", "must be true"))
    if not string_list(source.get("source_path_markers")):
        errors.append(validation_error("policy.release_candidate_source.source_path_markers", "must be non-empty"))
    if not isinstance(source.get("expected_branch"), str) or not source["expected_branch"]:
        errors.append(validation_error("policy.release_candidate_source.expected_branch", "expected_branch is required"))
    if not isinstance(source.get("expected_remote_url"), str) or not source["expected_remote_url"]:
        errors.append(validation_error("policy.release_candidate_source.expected_remote_url", "expected_remote_url is required"))
    for key in ("require_commit", "require_remote", "require_clean_source"):
        if source.get(key) is not True:
            errors.append(validation_error(f"policy.release_candidate_source.{key}", f"{key} must be true"))

    trace = dict_value(policy.get("trace_contract"))
    for key in sorted(REQUIRED_TRACE_TRUE):
        if trace.get(key) is not True:
            errors.append(validation_error(f"policy.trace_contract.{key}", f"{key} must be true"))
    if trace.get("target_run_id_prefix") != "workflow-router-":
        errors.append(validation_error("policy.trace_contract.target_run_id_prefix", "target_run_id_prefix must be workflow-router-"))
    if trace.get("minimum_output_artifacts") != 1:
        errors.append(validation_error("policy.trace_contract.minimum_output_artifacts", "minimum_output_artifacts must be 1"))

    hygiene = dict_value(policy.get("runtime_state_hygiene"))
    for key in ("local_artifacts_only", "git_ls_files_runtime_state_must_be_empty", "git_check_ignore_required"):
        if hygiene.get(key) is not True:
            errors.append(validation_error(f"policy.runtime_state_hygiene.{key}", f"{key} must be true"))

    rerun = dict_value(policy.get("rerun_gate_contract"))
    for key in sorted(REQUIRED_RERUN_TRUE):
        if rerun.get(key) is not True:
            errors.append(validation_error(f"policy.rerun_gate_contract.{key}", f"{key} must be true"))
    if rerun.get("manual_success_without_rerun_allowed") is not False:
        errors.append(
            validation_error(
                "policy.rerun_gate_contract.manual_success_without_rerun_allowed",
                "manual success without rerun must be false",
            )
        )

    outcomes = object_list(policy.get("required_feedback_outcomes"))
    if {str(item.get("outcome")) for item in outcomes} != REQUIRED_OUTCOMES:
        errors.append(validation_error("policy.required_feedback_outcomes", "positive and targeted defect outcomes are required"))
    for item in outcomes:
        case_id = str(item.get("case_id") or "unknown")
        if item.get("expected_decision_kind") not in {"rejected_finding", "repair_followup"}:
            errors.append(validation_error(f"policy.required_feedback_outcomes.{case_id}.expected_decision_kind", "unexpected decision kind"))
        if not string_list(item.get("expected_classifications")):
            errors.append(validation_error(f"policy.required_feedback_outcomes.{case_id}.expected_classifications", "classifications are required"))

    repair_cases = object_list(policy.get("accepted_finding_rerun_cases"))
    if not repair_cases:
        errors.append(validation_error("policy.accepted_finding_rerun_cases", "at least one accepted repair case is required"))
    for case in repair_cases:
        case_id = str(case.get("source_case_id") or "unknown")
        if case.get("expected_decision_kind") != "repair_followup":
            errors.append(validation_error(f"policy.accepted_finding_rerun_cases.{case_id}.expected_decision_kind", "must be repair_followup"))
        if case.get("closure_status_before_rerun") != "open_pending_repair":
            errors.append(
                validation_error(
                    f"policy.accepted_finding_rerun_cases.{case_id}.closure_status_before_rerun",
                    "must be open_pending_repair",
                )
            )
        if case.get("minimum_rerun_records") != 2:
            errors.append(validation_error(f"policy.accepted_finding_rerun_cases.{case_id}.minimum_rerun_records", "must be 2"))
        if set(string_list(case.get("required_surfaces"))) != {"gateway", "anythingllm"}:
            errors.append(validation_error(f"policy.accepted_finding_rerun_cases.{case_id}.required_surfaces", "gateway and anythingllm are required"))
        if set(string_list(case.get("required_fixture_roots"))) != {
            "/mnt/c/coinbase_testing_repo_frozen_tmp",
            "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        }:
            errors.append(validation_error(f"policy.accepted_finding_rerun_cases.{case_id}.required_fixture_roots", "both frozen fixtures are required"))
        if not isinstance(case.get("target_prompt"), str) or not str(case["target_prompt"]).strip():
            errors.append(validation_error(f"policy.accepted_finding_rerun_cases.{case_id}.target_prompt", "target_prompt is required"))
        if not isinstance(case.get("holdout_prompt"), str) or not str(case["holdout_prompt"]).strip():
            errors.append(validation_error(f"policy.accepted_finding_rerun_cases.{case_id}.holdout_prompt", "holdout_prompt is required"))

    missing_controls = sorted(REQUIRED_NEGATIVE_CONTROLS - set(string_list(policy.get("negative_controls"))))
    if missing_controls:
        errors.append(validation_error("policy.negative_controls", f"missing controls: {missing_controls}"))
    if policy.get("acceptance_marker") != "PHASE243 EXTERNAL TESTER FEEDBACK LOOP FROM CLONE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 243"))
    return errors


def required_decisions(policy: dict[str, Any]) -> set[str]:
    return {
        str(item.get("expected_decision_kind"))
        for item in object_list(policy.get("required_feedback_outcomes"))
        if isinstance(item.get("expected_decision_kind"), str)
    }


def validate_phase243_cases(cases: list[FounderFeedbackLoopCase], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors = [
        validation_error("cases.catalog", message)
        for message in validate_case_catalog(cases, required_decisions=required_decisions(policy))
    ]
    expected_by_id = {
        str(item.get("case_id")): item
        for item in object_list(policy.get("required_feedback_outcomes"))
        if isinstance(item.get("case_id"), str)
    }
    actual_by_id = {case.case_id: case for case in cases}
    for case_id, outcome in expected_by_id.items():
        case = actual_by_id.get(case_id)
        if case is None:
            errors.append(validation_error(f"cases.{case_id}.missing", "required outcome case is missing"))
            continue
        if list(case.expected_classifications) != string_list(outcome.get("expected_classifications")):
            errors.append(validation_error(f"cases.{case_id}.classifications", "classifications do not match policy"))
        if case.expected_decision_kind != outcome.get("expected_decision_kind"):
            errors.append(validation_error(f"cases.{case_id}.decision_kind", "decision kind does not match policy"))
        if case.expected_gap_class != outcome.get("expected_gap_class"):
            errors.append(validation_error(f"cases.{case_id}.gap_class", "gap class does not match policy"))
    if len(cases) < 2:
        errors.append(validation_error("cases.count", "Phase 243 requires at least two cases"))
    return errors


def git_branch_for_path(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else None


def git_text(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def source_summary(policy: dict[str, Any], live_report: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    source = dict_value(policy.get("release_candidate_source"))
    raw_config_root = live_report.get("config_root")
    config_root = Path(str(raw_config_root)) if isinstance(raw_config_root, str) and raw_config_root else None
    config_text = str(raw_config_root) if isinstance(raw_config_root, str) else ""
    active_workspace = str(source.get("active_workspace_path") or "")
    markers = string_list(source.get("source_path_markers"))
    marker_matched = [marker for marker in markers if marker in config_text]
    if not config_root:
        errors.append(validation_error("live_report.config_root", "live report must include config_root"))
    elif source.get("disallow_active_workspace") is True and config_text.rstrip("/\\") == active_workspace.rstrip("/\\"):
        errors.append(validation_error("live_report.config_root", "live report must come from clone path, not active workspace"))
    if not marker_matched:
        errors.append(validation_error("live_report.config_root_marker", "live report config_root must include an approved clone path marker"))

    source_git = dict_value(live_report.get("source_git"))
    branch = source_git.get("branch") if isinstance(source_git.get("branch"), str) else None
    if branch is None and config_root is not None:
        branch = git_branch_for_path(config_root)
    if branch != source.get("expected_branch"):
        errors.append(validation_error("live_report.source_git.branch", f"branch must be {source.get('expected_branch')}"))
    commit = source_git.get("commit") if isinstance(source_git.get("commit"), str) else None
    if commit is None and config_root is not None:
        commit = git_text(config_root, "rev-parse", "HEAD")
    if source.get("require_commit") is True and not commit:
        errors.append(validation_error("live_report.source_git.commit", "commit is required"))
    remote = source_git.get("remote_origin_url") if isinstance(source_git.get("remote_origin_url"), str) else None
    if remote is None and config_root is not None:
        remote = git_text(config_root, "config", "--get", "remote.origin.url")
    if remote != source.get("expected_remote_url"):
        errors.append(validation_error("live_report.source_git.remote_origin_url", f"remote must be {source.get('expected_remote_url')}"))
    status_short = source_git.get("status_short") if isinstance(source_git.get("status_short"), str) else None
    if status_short is None and config_root is not None:
        status_short = git_text(config_root, "status", "--short") or ""
    if source.get("require_clean_source") is True and status_short:
        errors.append(validation_error("live_report.source_git.status_short", "release-candidate clone source must be clean"))
    return {
        "config_root": config_text or None,
        "source_mode": source.get("required_source_mode"),
        "branch": branch,
        "commit": commit,
        "remote_origin_url": remote,
        "source_clean": status_short == "",
        "matched_source_path_markers": marker_matched,
        "active_workspace_disallowed": source.get("disallow_active_workspace") is True,
    }, errors


def cases_by_id(live_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in object_list(live_report.get("cases")):
        case_id = item.get("case_id")
        if isinstance(case_id, str):
            rows[case_id] = item
    return rows


def output_artifact_keys(artifacts: dict[str, Any]) -> list[str]:
    metadata = {
        "request",
        "registry_snapshot",
        "route_decision",
        "approval_state",
        "context_source_audit",
        "run_state",
    }
    return sorted(key for key in artifacts if isinstance(key, str) and key not in metadata)


def artifact_hashes(artifacts: dict[str, Any], keys: list[str]) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for key in keys:
        path = resolve_artifact_path(artifacts.get(key))
        if path is None or not path.is_file():
            missing.append(key)
            continue
        hashes[key] = sha256_file(path)
    return hashes, missing


def validate_case_trace(
    policy: dict[str, Any],
    case_report: dict[str, Any],
    outcome: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    case_id = str(outcome.get("case_id") or case_report.get("case_id") or "unknown")
    trace = dict_value(policy.get("trace_contract"))
    feedback_record = dict_value(case_report.get("feedback_record"))
    decision = dict_value(case_report.get("decision"))
    feedback_context = dict_value(feedback_record.get("feedback_context"))

    target_run_id = case_report.get("target_run_id")
    feedback_run_id = case_report.get("feedback_run_id")
    if not isinstance(target_run_id, str) or not target_run_id.startswith(str(trace.get("target_run_id_prefix"))):
        errors.append(validation_error(f"cases.{case_id}.target_run_id", "target workflow-router run_id is required"))
    if not isinstance(feedback_run_id, str) or not feedback_run_id.startswith("workflow-feedback-"):
        errors.append(validation_error(f"cases.{case_id}.feedback_run_id", "feedback run_id is required"))
    if feedback_record.get("target_run_id") != target_run_id:
        errors.append(validation_error(f"cases.{case_id}.feedback_record_target", "feedback record must link the target run_id"))
    if decision.get("target_run_id") != target_run_id:
        errors.append(validation_error(f"cases.{case_id}.decision_target", "decision must link the target run_id"))
    if decision.get("feedback_run_id") != feedback_run_id:
        errors.append(validation_error(f"cases.{case_id}.decision_feedback", "decision must link the feedback run_id"))
    if feedback_context.get("target_run_found") is not True:
        errors.append(validation_error(f"cases.{case_id}.target_run_found", "linked target run record must be found"))

    route_path = resolve_artifact_path(feedback_context.get("route_decision"))
    route_decision, route_error = try_read_json_object(route_path)
    if route_error:
        errors.append(validation_error(f"cases.{case_id}.route_decision", route_error))
    elif route_decision.get("run_id") != target_run_id:
        errors.append(validation_error(f"cases.{case_id}.route_decision.run_id", "route decision run_id must match target run_id"))

    run_dir = route_path.parent if route_path is not None else None
    request, request_error = try_read_json_object(run_dir / "request.json" if run_dir else None)
    run_state, run_state_error = try_read_json_object(run_dir / "run-state.json" if run_dir else None)
    if request_error:
        errors.append(validation_error(f"cases.{case_id}.request", request_error))
    if run_state_error:
        errors.append(validation_error(f"cases.{case_id}.run_state", run_state_error))
    prompt = request.get("user_request")
    prompt_hash = sha256_text(prompt) if isinstance(prompt, str) else None
    if prompt_hash is None:
        errors.append(validation_error(f"cases.{case_id}.prompt_hash", "target request must include user_request for hashing"))

    artifacts = dict_value(run_state.get("artifacts"))
    artifact_keys = output_artifact_keys(artifacts)
    if len(artifact_keys) < int(trace.get("minimum_output_artifacts") or 1):
        errors.append(validation_error(f"cases.{case_id}.output_artifacts", "target run must include output artifacts"))
    route_sha256 = sha256_file(route_path) if route_path is not None and route_path.is_file() else None
    output_hashes, missing_hashes = artifact_hashes(artifacts, artifact_keys)
    if trace.get("artifact_hash_required") is True and (route_sha256 is None or missing_hashes or len(output_hashes) != len(artifact_keys)):
        errors.append(validation_error(f"cases.{case_id}.artifact_hashes", f"artifact hashes are required; missing={missing_hashes}"))

    classifications = feedback_record.get("classifications")
    if classifications != string_list(outcome.get("expected_classifications")):
        errors.append(validation_error(f"cases.{case_id}.classifications", "feedback classifications do not match expected outcome"))
    if decision.get("kind") != outcome.get("expected_decision_kind"):
        errors.append(validation_error(f"cases.{case_id}.decision_kind", "decision kind does not match expected outcome"))
    if decision.get("decision_status") != outcome.get("decision_status"):
        errors.append(validation_error(f"cases.{case_id}.decision_status", "decision status does not match expected outcome"))
    if decision.get("gap_class") != outcome.get("expected_gap_class"):
        errors.append(validation_error(f"cases.{case_id}.gap_class", "gap class does not match expected outcome"))

    validation_result = dict_value(decision.get("validation_result"))
    if decision.get("decision_status") in {"rejected", "deferred"} and not isinstance(validation_result.get("reason"), str):
        errors.append(validation_error(f"cases.{case_id}.nonaccepted_explanation", "rejected/deferred feedback requires an explanation"))
    if decision.get("decision_status") == "accepted":
        repair_cases = {
            str(item.get("source_case_id")): item
            for item in object_list(policy.get("accepted_finding_rerun_cases"))
            if isinstance(item.get("source_case_id"), str)
        }
        repair_case = dict_value(repair_cases.get(case_id))
        if not repair_case:
            errors.append(validation_error(f"cases.{case_id}.rerun_contract", "accepted repair feedback must have a rerun contract"))
        elif repair_case.get("closure_status_before_rerun") != "open_pending_repair":
            errors.append(validation_error(f"cases.{case_id}.closure_status", "accepted repair must remain open before rerun proof"))
        if validation_result.get("required_gate") not in {"eval_repair_loop", "answer_usefulness", "safety_boundary_review", "drift_gate"}:
            errors.append(validation_error(f"cases.{case_id}.required_gate", "accepted repair feedback must name a repair gate"))

    return {
        "case_id": case_id,
        "target_run_id": target_run_id,
        "feedback_run_id": feedback_run_id,
        "route_decision_path": str(route_path) if route_path else None,
        "route_decision_sha256": route_sha256,
        "prompt_hash": prompt_hash,
        "selected_workflow": route_decision.get("selected_workflow"),
        "route_status": route_decision.get("status"),
        "output_artifact_keys": artifact_keys,
        "output_artifact_sha256": output_hashes,
        "decision_kind": decision.get("kind"),
        "decision_status": decision.get("decision_status"),
        "gap_class": decision.get("gap_class"),
    }, errors


def runtime_state_hygiene(config_root: Path, policy: dict[str, Any], output_path: Path, markdown_output_path: Path, live_report_path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    hygiene = dict_value(policy.get("runtime_state_hygiene"))
    errors: list[dict[str, str]] = []
    tracked = git_text(config_root, "ls-files", "runtime-state") or ""
    tracked_lines = [line for line in tracked.splitlines() if line.strip()]
    if hygiene.get("git_ls_files_runtime_state_must_be_empty") is True and tracked_lines:
        errors.append(validation_error("runtime_state_hygiene.tracked_runtime_state", "runtime-state files must not be tracked"))
    check_paths = [output_path, markdown_output_path, live_report_path]
    ignored: dict[str, bool] = {}
    ignore_details: dict[str, str | None] = {}
    for path in check_paths:
        try:
            rel = path.resolve().relative_to(config_root.resolve())
        except (OSError, ValueError):
            rel = path
        result = subprocess.run(
            ["git", "-C", str(config_root), "check-ignore", "-v", str(rel)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        ignored[str(rel)] = result.returncode == 0
        ignore_details[str(rel)] = result.stdout.strip() or None
    if hygiene.get("git_check_ignore_required") is True:
        not_ignored = sorted(path for path, value in ignored.items() if not value)
        if not_ignored:
            errors.append(validation_error("runtime_state_hygiene.check_ignore", f"runtime artifacts must be ignored: {not_ignored}"))
    return {
        "tracked_runtime_state_count": len(tracked_lines),
        "tracked_runtime_state_sample": tracked_lines[:10],
        "checked_paths": ignored,
        "check_ignore_details": ignore_details,
    }, errors


def validate_live_report(policy: dict[str, Any], cases: list[FounderFeedbackLoopCase], live_report: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors = [
        validation_error("live_report.contract", message)
        for message in validate_founder_feedback_loop_report(
            live_report,
            cases,
            required_decisions=required_decisions(policy),
        )
    ]
    source, source_errors = source_summary(policy, live_report)
    errors.extend(source_errors)
    live_cases = cases_by_id(live_report)
    traces: list[dict[str, Any]] = []
    for outcome in object_list(policy.get("required_feedback_outcomes")):
        case_id = str(outcome.get("case_id") or "unknown")
        case_report = live_cases.get(case_id)
        if not case_report:
            errors.append(validation_error(f"cases.{case_id}.missing_live_report", "required live case report is missing"))
            continue
        trace, trace_errors = validate_case_trace(policy, case_report, outcome)
        traces.append(trace)
        errors.extend(trace_errors)
    return {
        "status": live_report.get("status"),
        "case_count": len(object_list(live_report.get("cases"))),
        "source": source,
        "traces": traces,
    }, errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# External Tester Feedback Loop From Clone",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Phase 244 ready: `{summary.get('phase244_ready')}`",
        f"- Case count: `{summary.get('case_count')}`",
        f"- Trace count: `{summary.get('trace_count')}`",
        "",
        "## Validation Errors",
    ]
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_external_tester_feedback_loop_from_clone(
    config: ExternalTesterFeedbackLoopFromCloneConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)

    cases_path = resolve_path(config_root, Path(str(policy.get("cases_path", ""))))
    cases = load_founder_feedback_loop_cases(cases_path)
    validation_errors.extend(validate_phase243_cases(cases, policy))

    live_report_path = resolve_path(config_root, Path(str(policy.get("live_feedback_report_path", ""))))
    live_summary: dict[str, Any] = {}
    if live_report_path.is_file():
        live_report = read_json_object(live_report_path)
        live_summary, live_errors = validate_live_report(policy, cases, live_report)
        validation_errors.extend(live_errors)
    elif config.require_live_artifacts:
        validation_errors.append(validation_error("live_report.missing", f"required live report missing: {live_report_path}"))

    hygiene_summary, hygiene_errors = runtime_state_hygiene(
        config_root,
        policy,
        output_path,
        markdown_output_path,
        live_report_path,
    )
    validation_errors.extend(hygiene_errors)

    trace_count = len(object_list(live_summary.get("traces")))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": "passed" if not validation_errors else "failed",
        "policy_path": str(policy_path),
        "cases_path": str(cases_path),
        "live_feedback_report_path": str(live_report_path),
        "validation_errors": validation_errors,
        "live_report": live_summary,
        "runtime_state_hygiene": hygiene_summary,
        "summary": {
            "case_count": len(cases),
            "required_outcome_count": len(object_list(policy.get("required_feedback_outcomes"))),
            "trace_count": trace_count,
            "repair_rerun_case_count": len(object_list(policy.get("accepted_finding_rerun_cases"))),
            "phase244_ready": not validation_errors and bool(live_summary),
        },
    }
    write_json(output_path, report)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(render_markdown(report), encoding="utf-8")
    return report
