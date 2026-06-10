"""Stable chat-quality release gate for founder testing readiness."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import validate_baseline_corpus


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "stable_chat_quality_release_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "stable-chat-quality-release" / "phase130"
EXPECTED_POLICY_KIND = "stable_chat_quality_release_policy"
EXPECTED_REPORT_KIND = "stable_chat_quality_release_report"
EXPECTED_PHASE = 130
EXPECTED_BACKLOG_ID = "P0-BB-015"
REQUIRED_ROUTES = {"gateway", "anythingllm"}
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}


class StableChatQualityReleaseStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ChatQualityReadiness(str, Enum):
    READY_FOR_FOUNDER_TESTING = "ready_for_founder_testing"
    BLOCKED = "blocked"


class ReleaseGateId(str, Enum):
    BASELINE_CORPUS = "baseline_corpus"
    ANYTHINGLLM_ANSWER_USEFULNESS = "anythingllm_answer_usefulness"
    HOLDOUT_PROMPT_BANK = "holdout_prompt_bank"
    PRIORITY0_GAP_TAXONOMY = "priority0_gap_taxonomy"
    OUTPUT_FORMAT_PARITY = "output_format_parity"
    FOUNDER_FEEDBACK_LOOP = "founder_feedback_loop"
    ANYTHINGLLM_UI_E2E = "anythingllm_ui_e2e"
    FRESH_LOCAL_MODEL_DRIFT = "fresh_local_model_drift"
    PROMPT_TIGHTENING_RECOMMENDATIONS = "prompt_tightening_recommendations"
    SKILL_TOOL_COVERAGE_GAP = "skill_tool_coverage_gap"
    STABLE_RELEASE_BLOCKER_CLOSURE = "stable_release_blocker_closure"


EXPECTED_GATE_ORDER = [item.value for item in ReleaseGateId]
EXPECTED_GATE_KINDS = {
    ReleaseGateId.BASELINE_CORPUS.value: "priority0_baseline_corpus",
    ReleaseGateId.ANYTHINGLLM_ANSWER_USEFULNESS.value: "anythingllm_answer_usefulness_report",
    ReleaseGateId.HOLDOUT_PROMPT_BANK.value: "holdout_prompt_bank_report",
    ReleaseGateId.PRIORITY0_GAP_TAXONOMY.value: "priority0_gap_taxonomy_report",
    ReleaseGateId.OUTPUT_FORMAT_PARITY.value: "output_format_parity_live_report",
    ReleaseGateId.FOUNDER_FEEDBACK_LOOP.value: "founder_feedback_loop_live_report",
    ReleaseGateId.ANYTHINGLLM_UI_E2E.value: "anythingllm_ui_e2e_report",
    ReleaseGateId.FRESH_LOCAL_MODEL_DRIFT.value: "fresh_local_model_drift_report",
    ReleaseGateId.PROMPT_TIGHTENING_RECOMMENDATIONS.value: "prompt_tightening_recommendation_report",
    ReleaseGateId.SKILL_TOOL_COVERAGE_GAP.value: "skill_tool_coverage_gap_report",
    ReleaseGateId.STABLE_RELEASE_BLOCKER_CLOSURE.value: "stable_release_blocker_closure_report",
}
DEFAULT_GATE_PATHS = {
    ReleaseGateId.BASELINE_CORPUS.value: Path("runtime") / "baseline_corpus.json",
    ReleaseGateId.ANYTHINGLLM_ANSWER_USEFULNESS.value: (
        Path("runtime-state") / "anythingllm-answer-usefulness" / "phase121-answer-usefulness-report.json"
    ),
    ReleaseGateId.HOLDOUT_PROMPT_BANK.value: (
        Path("runtime-state") / "holdout-prompt-bank" / "phase122-holdout-prompt-bank-report.json"
    ),
    ReleaseGateId.PRIORITY0_GAP_TAXONOMY.value: (
        Path("runtime-state") / "priority0-gap-taxonomy" / "phase129-priority0-gap-taxonomy-report.json"
    ),
    ReleaseGateId.OUTPUT_FORMAT_PARITY.value: (
        Path("runtime-state") / "output-format-parity" / "phase124-output-format-parity-live.json"
    ),
    ReleaseGateId.FOUNDER_FEEDBACK_LOOP.value: (
        Path("runtime-state") / "founder-feedback-loop" / "phase125-founder-feedback-loop-live.json"
    ),
    ReleaseGateId.ANYTHINGLLM_UI_E2E.value: (
        Path("runtime-state") / "anythingllm-ui" / "phase126-corpus-ui-usefulness.json"
    ),
    ReleaseGateId.FRESH_LOCAL_MODEL_DRIFT.value: (
        Path("runtime-state")
        / "fresh-local-model-drift"
        / "phase127"
        / "phase127-fresh-local-model-drift-report.json"
    ),
    ReleaseGateId.PROMPT_TIGHTENING_RECOMMENDATIONS.value: (
        Path("runtime-state")
        / "prompt-tightening-recommendations"
        / "phase128"
        / "phase128-prompt-tightening-recommendations-report.json"
    ),
    ReleaseGateId.SKILL_TOOL_COVERAGE_GAP.value: (
        Path("runtime-state")
        / "skill-tool-coverage-gap"
        / "phase129"
        / "phase129-skill-tool-coverage-gap-report.json"
    ),
    ReleaseGateId.STABLE_RELEASE_BLOCKER_CLOSURE.value: (
        Path("runtime-state")
        / "stable-release-blocker-closure"
        / "phase131"
        / "phase131-stable-release-blocker-closure-report.json"
    ),
}


@dataclass(frozen=True)
class StableChatQualityReleaseConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"stable-chat-quality-release-{utc_timestamp()}.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def closure_prompt_ids(closure_report: dict[str, Any]) -> set[str]:
    if closure_report.get("status") != "passed":
        return set()
    return {
        str(record.get("candidate_id"))
        for record in object_list(closure_report.get("prompt_tightening_closures"))
        if record.get("release_blocker_resolved") is True and isinstance(record.get("candidate_id"), str)
    }


def closure_founder_case_ids(closure_report: dict[str, Any]) -> set[str]:
    if closure_report.get("status") != "passed":
        return set()
    return {
        str(record.get("case_id"))
        for record in object_list(closure_report.get("founder_feedback_closures"))
        if record.get("release_blocker_resolved") is True and isinstance(record.get("case_id"), str)
    }


def gate_policy_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(gate.get("id")): gate
        for gate in object_list(policy.get("required_gates"))
        if isinstance(gate.get("id"), str)
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 130")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if set(string_list(policy.get("allowed_readiness_statuses"))) != {item.value for item in ChatQualityReadiness}:
        errors.append("policy.allowed_readiness_statuses must match governed readiness values")
    if set(string_list(policy.get("required_routes"))) != REQUIRED_ROUTES:
        errors.append("policy.required_routes must be gateway and anythingllm")
    if set(string_list(policy.get("required_target_roots"))) != REQUIRED_TARGET_ROOTS:
        errors.append("policy.required_target_roots must be both frozen Coinbase fixtures")
    for key in (
        "minimum_answer_usefulness_case_count",
        "minimum_holdout_response_count",
        "minimum_output_format_case_count",
        "minimum_founder_feedback_case_count",
        "minimum_fresh_drift_response_count",
        "minimum_skill_coverage_entry_count",
    ):
        if not isinstance(policy.get(key), int) or policy[key] < 1:
            errors.append(f"policy.{key} must be a positive integer")
    if policy.get("prompt_tightening_pending_review_blocks_release") is not True:
        errors.append("policy.prompt_tightening_pending_review_blocks_release must be true")
    if policy.get("accepted_prompt_tightening_blocks_release") is not True:
        errors.append("policy.accepted_prompt_tightening_blocks_release must be true")
    if policy.get("accepted_founder_feedback_pending_eval_blocks_release") is not True:
        errors.append("policy.accepted_founder_feedback_pending_eval_blocks_release must be true")
    gates = object_list(policy.get("required_gates"))
    gate_ids = [str(gate.get("id")) for gate in gates if isinstance(gate.get("id"), str)]
    if gate_ids != EXPECTED_GATE_ORDER:
        errors.append("policy.required_gates must contain the governed gates in order")
    gate_map = gate_policy_by_id(policy)
    for gate_id in EXPECTED_GATE_ORDER:
        gate = gate_map.get(gate_id, {})
        if gate.get("kind") != EXPECTED_GATE_KINDS[gate_id]:
            errors.append(f"policy.required_gates[{gate_id}].kind must be {EXPECTED_GATE_KINDS[gate_id]}")
        if not isinstance(gate.get("path"), str) or not gate["path"].strip():
            errors.append(f"policy.required_gates[{gate_id}].path must be a non-empty string")
    return errors


def clean_mutation_proof(mutation_proof: dict[str, Any]) -> bool:
    if not mutation_proof:
        return True
    if mutation_proof.get("runtime_changed_files") not in ([], None):
        return False
    target_changed = mutation_proof.get("target_changed_files")
    if isinstance(target_changed, dict):
        if any(value not in ([], None) for value in target_changed.values()):
            return False
    elif target_changed is not None:
        return False
    if mutation_proof.get("target_git_changed") not in ({}, None):
        return False
    if mutation_proof.get("protected_fixture_changed") not in (False, None):
        return False
    return True


def require_passed_status(payload: dict[str, Any], blockers: list[str], *, gate_id: str) -> None:
    if payload.get("status") != StableChatQualityReleaseStatus.PASSED.value:
        blockers.append(f"{gate_id}.status must be passed")
    report_errors = payload.get("errors")
    if isinstance(report_errors, list) and report_errors:
        blockers.append(f"{gate_id}.errors must be empty")
    summary = dict_value(payload.get("summary"))
    if summary and summary.get("error_count") not in (0, None):
        blockers.append(f"{gate_id}.summary.error_count must be 0")


def require_target_roots(payload: dict[str, Any], blockers: list[str], *, gate_id: str) -> None:
    roots = set(string_list(payload.get("target_roots")))
    if not roots:
        summary = dict_value(payload.get("summary"))
        roots = set(string_list(summary.get("target_roots")))
    missing = sorted(REQUIRED_TARGET_ROOTS - roots)
    if missing:
        blockers.append(f"{gate_id}.target_roots missing required target(s): " + ", ".join(missing))


def require_routes(payload: dict[str, Any], blockers: list[str], *, gate_id: str) -> None:
    routes = set(string_list(payload.get("required_routes")))
    if not routes:
        summary = dict_value(payload.get("summary"))
        routes = set(string_list(summary.get("required_routes")))
    missing = sorted(REQUIRED_ROUTES - routes)
    if missing:
        blockers.append(f"{gate_id}.required_routes missing required route(s): " + ", ".join(missing))


def build_baseline_corpus_result(
    *,
    config_root: Path,
    path: Path,
    payload: dict[str, Any],
    missing: bool,
    require_artifacts: bool,
) -> dict[str, Any]:
    gate_id = ReleaseGateId.BASELINE_CORPUS.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    validation_errors = validate_baseline_corpus(payload, config_root=config_root, require_artifacts=require_artifacts) if payload else []
    blockers.extend(f"{gate_id}.{error}" for error in validation_errors)
    entries = object_list(payload.get("entries"))
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "entry_count": len(entries),
            "stable_entry_count": sum(1 for entry in entries if entry.get("status") == "stable"),
            "validation_error_count": len(validation_errors),
        },
    )


def build_answer_usefulness_result(*, path: Path, payload: dict[str, Any], missing: bool, policy: dict[str, Any]) -> dict[str, Any]:
    gate_id = ReleaseGateId.ANYTHINGLLM_ANSWER_USEFULNESS.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    checked = int_value(summary.get("checked_case_count"))
    if checked < int(policy["minimum_answer_usefulness_case_count"]):
        blockers.append(f"{gate_id}.summary.checked_case_count below release minimum")
    return gate_result(gate_id=gate_id, path=path, blockers=blockers, advisories=[], summary={"checked_case_count": checked})


def build_holdout_result(*, path: Path, payload: dict[str, Any], missing: bool, policy: dict[str, Any]) -> dict[str, Any]:
    gate_id = ReleaseGateId.HOLDOUT_PROMPT_BANK.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    responses = int_value(summary.get("holdout_response_count"))
    if responses < int(policy["minimum_holdout_response_count"]):
        blockers.append(f"{gate_id}.summary.holdout_response_count below release minimum")
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "holdout_case_count": int_value(summary.get("holdout_case_count")),
            "holdout_response_count": responses,
        },
    )


def build_priority0_gap_taxonomy_result(*, path: Path, payload: dict[str, Any], missing: bool) -> dict[str, Any]:
    gate_id = ReleaseGateId.PRIORITY0_GAP_TAXONOMY.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    if int_value(summary.get("finding_count")) != 0:
        blockers.append(f"{gate_id}.summary.finding_count must be 0")
    if summary.get("highest_severity") not in ("none", None):
        blockers.append(f"{gate_id}.summary.highest_severity must be none")
    severity_counts = dict_value(summary.get("severity_counts"))
    if int_value(severity_counts.get("critical")) != 0 or int_value(severity_counts.get("high")) != 0:
        blockers.append(f"{gate_id}.summary.severity_counts critical/high must be 0")
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "finding_count": int_value(summary.get("finding_count")),
            "highest_severity": summary.get("highest_severity"),
        },
    )


def build_output_format_result(*, path: Path, payload: dict[str, Any], missing: bool, policy: dict[str, Any]) -> dict[str, Any]:
    gate_id = ReleaseGateId.OUTPUT_FORMAT_PARITY.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    case_count = int_value(payload.get("case_count"))
    if case_count < int(policy["minimum_output_format_case_count"]):
        blockers.append(f"{gate_id}.case_count below release minimum")
    require_target_roots(payload, blockers, gate_id=gate_id)
    if not clean_mutation_proof(dict_value(payload.get("mutation_proof"))):
        blockers.append(f"{gate_id}.mutation_proof must show no protected fixture changes")
    target_roots_seen: set[str] = set()
    for case in object_list(payload.get("cases")):
        case_id = case.get("case_id")
        if isinstance(case.get("target_root"), str):
            target_roots_seen.add(str(case["target_root"]))
        if case.get("errors") not in ([], None):
            blockers.append(f"{gate_id}.cases[{case_id}].errors must be empty")
        responses = dict_value(case.get("responses"))
        missing_routes = sorted(REQUIRED_ROUTES - set(responses))
        if missing_routes:
            blockers.append(f"{gate_id}.cases[{case_id}].responses missing route(s): " + ", ".join(missing_routes))
        for route in REQUIRED_ROUTES:
            response = dict_value(responses.get(route))
            if not response:
                continue
            if response.get("status") != "passed":
                blockers.append(f"{gate_id}.cases[{case_id}].responses[{route}].status must be passed")
            if response.get("errors") not in ([], None):
                blockers.append(f"{gate_id}.cases[{case_id}].responses[{route}].errors must be empty")
            format_a = dict_value(response.get("format_a"))
            json_response = dict_value(response.get("json"))
            if int_value(format_a.get("http_status")) != 200:
                blockers.append(f"{gate_id}.cases[{case_id}].responses[{route}].format_a.http_status must be 200")
            if int_value(json_response.get("http_status")) != 200:
                blockers.append(f"{gate_id}.cases[{case_id}].responses[{route}].json.http_status must be 200")
            if not isinstance(json_response.get("run_id"), str) or not json_response["run_id"].strip():
                blockers.append(f"{gate_id}.cases[{case_id}].responses[{route}].json.run_id is required")
    missing_case_targets = sorted(REQUIRED_TARGET_ROOTS - target_roots_seen)
    if missing_case_targets:
        blockers.append(f"{gate_id}.cases missing target root(s): " + ", ".join(missing_case_targets))
    return gate_result(gate_id=gate_id, path=path, blockers=blockers, advisories=[], summary={"case_count": case_count})


def build_founder_feedback_result(
    *,
    path: Path,
    payload: dict[str, Any],
    missing: bool,
    policy: dict[str, Any],
    closure_report: dict[str, Any],
) -> dict[str, Any]:
    gate_id = ReleaseGateId.FOUNDER_FEEDBACK_LOOP.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    case_count = int_value(payload.get("case_count"))
    if case_count < int(policy["minimum_founder_feedback_case_count"]):
        blockers.append(f"{gate_id}.case_count below release minimum")
    require_target_roots(payload, blockers, gate_id=gate_id)
    if not clean_mutation_proof(dict_value(payload.get("mutation_proof"))):
        blockers.append(f"{gate_id}.mutation_proof must show no protected fixture changes")
    accepted_pending_eval: list[str] = []
    closed_case_ids = closure_founder_case_ids(closure_report)
    for case in object_list(payload.get("cases")):
        case_id = str(case.get("case_id"))
        if case.get("status") != "passed":
            blockers.append(f"{gate_id}.cases[{case_id}].status must be passed")
        if case.get("errors") not in ([], None):
            blockers.append(f"{gate_id}.cases[{case_id}].errors must be empty")
        decision = dict_value(case.get("decision"))
        validation = dict_value(decision.get("validation_result"))
        if (
            decision.get("decision_status") == "accepted"
            and validation.get("status") != "passed"
            and case_id not in closed_case_ids
        ):
            accepted_pending_eval.append(case_id)
    if accepted_pending_eval and policy.get("accepted_founder_feedback_pending_eval_blocks_release") is True:
        blockers.append(
            f"{gate_id}.accepted feedback still pending required eval: " + ", ".join(sorted(accepted_pending_eval))
        )
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={"case_count": case_count, "accepted_pending_eval_count": len(accepted_pending_eval)},
    )


def build_ui_e2e_result(*, path: Path, payload: dict[str, Any], missing: bool) -> dict[str, Any]:
    gate_id = ReleaseGateId.ANYTHINGLLM_UI_E2E.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    if payload.get("fixture_unchanged") is not True:
        blockers.append(f"{gate_id}.fixture_unchanged must be true")
    ui = dict_value(payload.get("ui"))
    if ui.get("status") != "passed":
        blockers.append(f"{gate_id}.ui.status must be passed")
    if ui.get("page_errors") not in ([], None):
        blockers.append(f"{gate_id}.ui.page_errors must be empty")
    if ui.get("non_ignored_request_failures") not in ([], None):
        blockers.append(f"{gate_id}.ui.non_ignored_request_failures must be empty")
    ui_cases = object_list(ui.get("cases"))
    submitted_case_count = int_value(ui.get("submitted_case_count"), int_value(ui.get("case_count"), len(ui_cases)))
    for case in ui_cases:
        case_id = case.get("case_id")
        if case.get("status") != "passed":
            blockers.append(f"{gate_id}.ui.cases[{case_id}].status must be passed")
        if case.get("missing_required_markers") not in ([], None):
            blockers.append(f"{gate_id}.ui.cases[{case_id}].missing_required_markers must be empty")
        if case.get("rejected_markers_present") not in ([], None):
            blockers.append(f"{gate_id}.ui.cases[{case_id}].rejected_markers_present must be empty")
        if not isinstance(case.get("parsed_run_id"), str) or not case["parsed_run_id"].strip():
            blockers.append(f"{gate_id}.ui.cases[{case_id}].parsed_run_id is required")
        if dict_value(case.get("screenshots")).get("status") != "passed":
            blockers.append(f"{gate_id}.ui.cases[{case_id}].screenshots.status must be passed")
        usefulness = dict_value(case.get("answer_usefulness"))
        if usefulness.get("usefulness_status") != "passed" or usefulness.get("errors") not in ([], None):
            blockers.append(f"{gate_id}.ui.cases[{case_id}].answer_usefulness must pass")
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "fixture_unchanged": payload.get("fixture_unchanged"),
            "submitted_case_count": submitted_case_count,
        },
    )


def build_fresh_drift_result(*, path: Path, payload: dict[str, Any], missing: bool, policy: dict[str, Any]) -> dict[str, Any]:
    gate_id = ReleaseGateId.FRESH_LOCAL_MODEL_DRIFT.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    if summary.get("drift_status") != "no_drift_detected":
        blockers.append(f"{gate_id}.summary.drift_status must be no_drift_detected")
    if int_value(summary.get("failed_family_count")) != 0:
        blockers.append(f"{gate_id}.summary.failed_family_count must be 0")
    if int_value(summary.get("critical_finding_count")) != 0 or int_value(summary.get("high_finding_count")) != 0:
        blockers.append(f"{gate_id}.summary critical/high finding counts must be 0")
    responses = int_value(summary.get("response_count"))
    if responses < int(policy["minimum_fresh_drift_response_count"]):
        blockers.append(f"{gate_id}.summary.response_count below release minimum")
    if int_value(summary.get("passed_response_count")) != responses:
        blockers.append(f"{gate_id}.summary.passed_response_count must equal response_count")
    require_routes({"required_routes": summary.get("required_routes")}, blockers, gate_id=gate_id)
    require_target_roots({"target_roots": summary.get("target_roots")}, blockers, gate_id=gate_id)
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "drift_status": summary.get("drift_status"),
            "response_count": responses,
            "selected_case_count": int_value(summary.get("selected_case_count")),
        },
    )


def build_prompt_tightening_result(*, path: Path, payload: dict[str, Any], missing: bool, policy: dict[str, Any]) -> dict[str, Any]:
    gate_id = ReleaseGateId.PROMPT_TIGHTENING_RECOMMENDATIONS.value
    blockers: list[str] = []
    advisories: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    applied = int_value(summary.get("applied_prompt_catalog_change_count"))
    if applied != 0:
        blockers.append(f"{gate_id}.summary.applied_prompt_catalog_change_count must be 0")
    decisions = dict_value(summary.get("decision_status_counts"))
    accepted = int_value(decisions.get("accepted"))
    pending_candidate_ids = [
        str(candidate.get("candidate_id"))
        for candidate in object_list(payload.get("candidates"))
        if dict_value(candidate.get("decision")).get("status") == "pending_review"
        and isinstance(candidate.get("candidate_id"), str)
    ]
    closed_prompt_ids = closure_prompt_ids(dict_value(policy.get("_closure_report")))
    unresolved_pending_ids = sorted(set(pending_candidate_ids) - closed_prompt_ids)
    pending = len(unresolved_pending_ids)
    if accepted and policy.get("accepted_prompt_tightening_blocks_release") is True:
        blockers.append(f"{gate_id}.summary.decision_status_counts.accepted must be 0 for release")
    if pending:
        message = f"{gate_id} has {pending} pending prompt-tightening candidate(s)"
        if policy.get("prompt_tightening_pending_review_blocks_release") is True:
            blockers.append(message)
        else:
            advisories.append(message)
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=advisories,
        summary={
            "candidate_count": int_value(summary.get("candidate_count")),
            "pending_review_count": len(pending_candidate_ids),
            "pending_review_unresolved_count": pending,
            "accepted_count": accepted,
            "applied_prompt_catalog_change_count": applied,
        },
    )


def build_skill_tool_gap_result(*, path: Path, payload: dict[str, Any], missing: bool, policy: dict[str, Any]) -> dict[str, Any]:
    gate_id = ReleaseGateId.SKILL_TOOL_COVERAGE_GAP.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    if summary.get("new_capability_required") is not False:
        blockers.append(f"{gate_id}.summary.new_capability_required must be false")
    if int_value(summary.get("gap_candidate_count")) != 0:
        blockers.append(f"{gate_id}.summary.gap_candidate_count must be 0")
    if int_value(summary.get("skill_tool_finding_count")) != 0:
        blockers.append(f"{gate_id}.summary.skill_tool_finding_count must be 0")
    coverage_count = int_value(summary.get("implemented_coverage_entry_count"))
    if coverage_count < int(policy["minimum_skill_coverage_entry_count"]):
        blockers.append(f"{gate_id}.summary.implemented_coverage_entry_count below release minimum")
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "gap_candidate_count": int_value(summary.get("gap_candidate_count")),
            "new_capability_required": summary.get("new_capability_required"),
            "implemented_coverage_entry_count": coverage_count,
        },
    )


def build_blocker_closure_result(
    *,
    path: Path,
    payload: dict[str, Any],
    missing: bool,
    prompt_tightening_path: Path,
    founder_feedback_path: Path,
) -> dict[str, Any]:
    gate_id = ReleaseGateId.STABLE_RELEASE_BLOCKER_CLOSURE.value
    blockers: list[str] = []
    if missing:
        blockers.append(f"{gate_id}.artifact is missing")
    require_passed_status(payload, blockers, gate_id=gate_id)
    summary = dict_value(payload.get("summary"))
    if int_value(summary.get("unresolved_blocker_count")) != 0:
        blockers.append(f"{gate_id}.summary.unresolved_blocker_count must be 0")
    if payload.get("prompt_tightening_report_sha256") != artifact_hash(prompt_tightening_path):
        blockers.append(f"{gate_id}.prompt_tightening_report_sha256 must match current prompt-tightening artifact")
    if payload.get("founder_feedback_report_sha256") != artifact_hash(founder_feedback_path):
        blockers.append(f"{gate_id}.founder_feedback_report_sha256 must match current founder-feedback artifact")
    return gate_result(
        gate_id=gate_id,
        path=path,
        blockers=blockers,
        advisories=[],
        summary={
            "prompt_tightening_closed_count": int_value(summary.get("prompt_tightening_closed_count")),
            "founder_feedback_closed_count": int_value(summary.get("founder_feedback_closed_count")),
            "unresolved_blocker_count": int_value(summary.get("unresolved_blocker_count")),
        },
    )


def gate_result(
    *,
    gate_id: str,
    path: Path,
    blockers: list[str],
    advisories: list[str],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "artifact_path": str(path),
        "artifact_sha256": artifact_hash(path),
        "status": "blocked" if blockers else "passed",
        "blockers": blockers,
        "advisories": advisories,
        "summary": summary,
    }


def build_gate_result(
    *,
    config_root: Path,
    policy: dict[str, Any],
    gate_id: str,
    path: Path,
    payload: dict[str, Any],
    missing: bool,
    require_artifacts: bool,
    closure_report: dict[str, Any] | None = None,
    gate_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    expected_kind = EXPECTED_GATE_KINDS[gate_id]
    kind_blocker = [] if payload.get("kind") == expected_kind else [f"{gate_id}.kind must be {expected_kind}"]
    if gate_id == ReleaseGateId.BASELINE_CORPUS.value:
        result = build_baseline_corpus_result(
            config_root=config_root,
            path=path,
            payload=payload,
            missing=missing,
            require_artifacts=require_artifacts,
        )
    elif gate_id == ReleaseGateId.ANYTHINGLLM_ANSWER_USEFULNESS.value:
        result = build_answer_usefulness_result(path=path, payload=payload, missing=missing, policy=policy)
    elif gate_id == ReleaseGateId.HOLDOUT_PROMPT_BANK.value:
        result = build_holdout_result(path=path, payload=payload, missing=missing, policy=policy)
    elif gate_id == ReleaseGateId.PRIORITY0_GAP_TAXONOMY.value:
        result = build_priority0_gap_taxonomy_result(path=path, payload=payload, missing=missing)
    elif gate_id == ReleaseGateId.OUTPUT_FORMAT_PARITY.value:
        result = build_output_format_result(path=path, payload=payload, missing=missing, policy=policy)
    elif gate_id == ReleaseGateId.FOUNDER_FEEDBACK_LOOP.value:
        result = build_founder_feedback_result(
            path=path,
            payload=payload,
            missing=missing,
            policy=policy,
            closure_report=closure_report or {},
        )
    elif gate_id == ReleaseGateId.ANYTHINGLLM_UI_E2E.value:
        result = build_ui_e2e_result(path=path, payload=payload, missing=missing)
    elif gate_id == ReleaseGateId.FRESH_LOCAL_MODEL_DRIFT.value:
        result = build_fresh_drift_result(path=path, payload=payload, missing=missing, policy=policy)
    elif gate_id == ReleaseGateId.PROMPT_TIGHTENING_RECOMMENDATIONS.value:
        prompt_policy = dict(policy)
        prompt_policy["_closure_report"] = closure_report or {}
        result = build_prompt_tightening_result(path=path, payload=payload, missing=missing, policy=prompt_policy)
    elif gate_id == ReleaseGateId.SKILL_TOOL_COVERAGE_GAP.value:
        result = build_skill_tool_gap_result(path=path, payload=payload, missing=missing, policy=policy)
    elif gate_id == ReleaseGateId.STABLE_RELEASE_BLOCKER_CLOSURE.value:
        paths = gate_paths or {}
        result = build_blocker_closure_result(
            path=path,
            payload=payload,
            missing=missing,
            prompt_tightening_path=paths.get(ReleaseGateId.PROMPT_TIGHTENING_RECOMMENDATIONS.value, Path()),
            founder_feedback_path=paths.get(ReleaseGateId.FOUNDER_FEEDBACK_LOOP.value, Path()),
        )
    else:
        result = gate_result(
            gate_id=gate_id,
            path=path,
            blockers=[f"{gate_id} is not a governed release gate"],
            advisories=[],
            summary={},
        )
    if kind_blocker:
        result["blockers"] = kind_blocker + string_list(result.get("blockers"))
        result["status"] = "blocked"
    return result


def build_release_summary(gate_results: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [blocker for result in gate_results for blocker in string_list(result.get("blockers"))]
    advisories = [advisory for result in gate_results for advisory in string_list(result.get("advisories"))]
    readiness = (
        ChatQualityReadiness.READY_FOR_FOUNDER_TESTING.value
        if not blockers
        else ChatQualityReadiness.BLOCKED.value
    )
    return {
        "readiness": readiness,
        "gate_count": len(gate_results),
        "passed_gate_count": sum(1 for result in gate_results if result.get("status") == "passed"),
        "blocked_gate_count": sum(1 for result in gate_results if result.get("status") == "blocked"),
        "blocker_count": len(blockers),
        "advisory_count": len(advisories),
        "next_action": "continue founder testing" if not blockers else "resolve release blockers before founder testing",
    }


def build_stable_chat_quality_release_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    gate_payloads: dict[str, dict[str, Any]],
    gate_paths: dict[str, Path],
    missing_gates: set[str] | None = None,
    policy_path: Path | None = None,
    require_artifacts: bool = False,
) -> dict[str, Any]:
    missing = missing_gates or set()
    closure_report = gate_payloads.get(ReleaseGateId.STABLE_RELEASE_BLOCKER_CLOSURE.value, {})
    gate_results = [
        build_gate_result(
            config_root=config_root,
            policy=policy,
            gate_id=gate_id,
            path=gate_paths.get(gate_id, config_root / DEFAULT_GATE_PATHS[gate_id]),
            payload=gate_payloads.get(gate_id, {}),
            missing=gate_id in missing,
            require_artifacts=require_artifacts,
            closure_report=closure_report,
            gate_paths=gate_paths,
        )
        for gate_id in EXPECTED_GATE_ORDER
    ]
    summary = build_release_summary(gate_results)
    blockers = [blocker for result in gate_results for blocker in string_list(result.get("blockers"))]
    status = (
        StableChatQualityReleaseStatus.PASSED.value
        if summary["readiness"] == ChatQualityReadiness.READY_FOR_FOUNDER_TESTING.value
        else StableChatQualityReleaseStatus.FAILED.value
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "readiness": summary["readiness"],
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "require_artifacts": require_artifacts,
        "gate_results": gate_results,
        "summary": summary,
        "errors": blockers,
    }


def validate_stable_chat_quality_release_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    gate_payloads: dict[str, dict[str, Any]],
    gate_paths: dict[str, Path],
    config_root: Path,
    missing_gates: set[str] | None = None,
    policy_path: Path | None = None,
    require_artifacts: bool = False,
) -> list[str]:
    errors = validate_policy(policy)
    expected = build_stable_chat_quality_release_report(
        config_root=config_root,
        policy=policy,
        gate_payloads=gate_payloads,
        gate_paths=gate_paths,
        missing_gates=missing_gates,
        policy_path=policy_path,
        require_artifacts=require_artifacts,
    )
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "readiness",
        "policy_path",
        "policy_sha256",
        "require_artifacts",
        "gate_results",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt release evidence")
    expected_status = StableChatQualityReleaseStatus.PASSED.value if not expected["errors"] else StableChatQualityReleaseStatus.FAILED.value
    if report.get("status") != expected_status:
        errors.append(f"report.status must be {expected_status}")
    return errors


def run_stable_chat_quality_release_gate(config: StableChatQualityReleaseConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    gate_map = gate_policy_by_id(policy)
    gate_paths = {
        gate_id: resolve_path(config_root, gate_map.get(gate_id, {}).get("path", DEFAULT_GATE_PATHS[gate_id]))
        for gate_id in EXPECTED_GATE_ORDER
    }
    missing_gates = {gate_id for gate_id, path in gate_paths.items() if config.require_artifacts and not path.is_file()}
    gate_payloads = {
        gate_id: read_json_object(path) if path.is_file() else {}
        for gate_id, path in gate_paths.items()
    }
    report = build_stable_chat_quality_release_report(
        config_root=config_root,
        policy=policy,
        gate_payloads=gate_payloads,
        gate_paths=gate_paths,
        missing_gates=missing_gates,
        policy_path=policy_path,
        require_artifacts=config.require_artifacts,
    )
    validation_errors = validate_stable_chat_quality_release_report(
        report,
        policy=policy,
        gate_payloads=gate_payloads,
        gate_paths=gate_paths,
        config_root=config_root,
        missing_gates=missing_gates,
        policy_path=policy_path,
        require_artifacts=config.require_artifacts,
    )
    if validation_errors:
        report["status"] = StableChatQualityReleaseStatus.FAILED.value
        report["readiness"] = ChatQualityReadiness.BLOCKED.value
        report["errors"] = report["errors"] + validation_errors
        report["summary"] = build_release_summary(object_list(report.get("gate_results")))
        report["summary"]["readiness"] = ChatQualityReadiness.BLOCKED.value
        report["summary"]["blocker_count"] = len(report["errors"])
        report["summary"]["next_action"] = "resolve release blockers before founder testing"
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
