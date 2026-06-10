"""Governed closure for stable chat-quality release blockers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "stable_release_blocker_closure_policy"
EXPECTED_REPORT_KIND = "stable_release_blocker_closure_report"
EXPECTED_PHASE = 131
EXPECTED_BACKLOG_ID = "P0-BB-016"
DEFAULT_POLICY_PATH = Path("runtime") / "stable_release_blocker_closure_policy.json"
DEFAULT_PROMPT_TIGHTENING_REPORT_PATH = (
    Path("runtime-state")
    / "prompt-tightening-recommendations"
    / "phase128"
    / "phase128-prompt-tightening-recommendations-report.json"
)
DEFAULT_FOUNDER_FEEDBACK_REPORT_PATH = (
    Path("runtime-state") / "founder-feedback-loop" / "phase125-founder-feedback-loop-live.json"
)
DEFAULT_FOUNDER_FEEDBACK_CASES_PATH = Path("runtime") / "founder_feedback_loop_cases.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "stable-release-blocker-closure" / "phase131"


class StableReleaseBlockerClosureStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class PromptTighteningClosureStatus(str, Enum):
    REJECTED = "rejected"
    ACCEPTED_WITH_RERUN_PROOF = "accepted_with_rerun_proof"


class FounderFeedbackClosureStatus(str, Enum):
    CLOSED_AS_SYNTHETIC_FIXTURE = "closed_as_synthetic_fixture"
    CLOSED_BY_REQUIRED_GATE = "closed_by_required_gate"


@dataclass(frozen=True)
class StableReleaseBlockerClosureConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    prompt_tightening_report_path: Path = DEFAULT_PROMPT_TIGHTENING_REPORT_PATH
    founder_feedback_report_path: Path = DEFAULT_FOUNDER_FEEDBACK_REPORT_PATH
    founder_feedback_cases_path: Path = DEFAULT_FOUNDER_FEEDBACK_CASES_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"stable-release-blocker-closure-{utc_timestamp()}.json"


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


def rationale_is_sufficient(value: object) -> bool:
    return isinstance(value, str) and len(value.split()) >= 12


def pending_prompt_tightening_candidates(prompt_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(candidate.get("candidate_id")): candidate
        for candidate in object_list(prompt_report.get("candidates"))
        if dict_value(candidate.get("decision")).get("status") == "pending_review"
        and isinstance(candidate.get("candidate_id"), str)
    }


def accepted_pending_founder_feedback(founder_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for case in object_list(founder_report.get("cases")):
        decision = dict_value(case.get("decision"))
        validation = dict_value(decision.get("validation_result"))
        case_id = case.get("case_id")
        if (
            decision.get("decision_status") == "accepted"
            and validation.get("status") != StableReleaseBlockerClosureStatus.PASSED.value
            and isinstance(case_id, str)
        ):
            records[case_id] = case
    return records


def founder_case_catalog_by_id(cases_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if cases_catalog.get("kind") != "founder_feedback_loop_cases":
        return {}
    return {
        str(item.get("case_id")): item
        for item in object_list(cases_catalog.get("cases"))
        if isinstance(item.get("case_id"), str)
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 131")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if set(string_list(policy.get("allowed_prompt_tightening_closure_statuses"))) != {
        item.value for item in PromptTighteningClosureStatus
    }:
        errors.append("policy.allowed_prompt_tightening_closure_statuses must match governed values")
    if set(string_list(policy.get("allowed_founder_feedback_closure_statuses"))) != {
        item.value for item in FounderFeedbackClosureStatus
    }:
        errors.append("policy.allowed_founder_feedback_closure_statuses must match governed values")
    return errors


def prompt_closure_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("candidate_id")): item
        for item in object_list(policy.get("prompt_tightening_closures"))
        if isinstance(item.get("candidate_id"), str)
    }


def founder_closure_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("case_id")): item
        for item in object_list(policy.get("founder_feedback_closures"))
        if isinstance(item.get("case_id"), str)
    }


def build_prompt_closure_records(
    *,
    policy: dict[str, Any],
    prompt_report: dict[str, Any],
) -> list[dict[str, Any]]:
    pending = pending_prompt_tightening_candidates(prompt_report)
    closures = prompt_closure_by_id(policy)
    records: list[dict[str, Any]] = []
    for candidate_id, candidate in sorted(pending.items()):
        closure = closures.get(candidate_id, {})
        closure_status = closure.get("closure_status")
        blockers: list[str] = []
        if not closure:
            blockers.append("missing prompt-tightening closure")
        elif closure_status not in {item.value for item in PromptTighteningClosureStatus}:
            blockers.append("unsupported prompt-tightening closure status")
        if not rationale_is_sufficient(closure.get("rationale")):
            blockers.append("closure rationale must explain the decision")
        if closure.get("prompt_catalog_changed") is not False:
            blockers.append("prompt catalog must not change during blocker closure")
        if closure_status == PromptTighteningClosureStatus.ACCEPTED_WITH_RERUN_PROOF.value:
            rerun = dict_value(closure.get("rerun_proof"))
            if rerun.get("target_case_status") != "passed" or rerun.get("holdout_status") != "passed":
                blockers.append("accepted prompt-tightening closure requires target and holdout rerun proof")
        if closure_status == PromptTighteningClosureStatus.REJECTED.value:
            if candidate.get("trigger_reasons") != ["low_confidence_pass"]:
                blockers.append("prompt-tightening rejection requires only low_confidence_pass trigger")
            if candidate.get("minimum_route_score") != 85:
                blockers.append("prompt-tightening rejection requires score exactly at the governed floor")
            if candidate.get("unresolved_findings") not in ([], None):
                blockers.append("cannot reject prompt-tightening candidate while unresolved findings remain")
            if dict_value(candidate.get("fresh_drift_context")).get("drift_severity") not in ("none", None):
                blockers.append("cannot reject prompt-tightening candidate with active fresh drift")
        records.append(
            {
                "candidate_id": candidate_id,
                "closure_status": closure_status,
                "release_blocker_resolved": not blockers,
                "source_trigger_reasons": candidate.get("trigger_reasons"),
                "source_minimum_route_score": candidate.get("minimum_route_score"),
                "rationale": closure.get("rationale"),
                "blockers": blockers,
            }
        )
    return records


def build_founder_feedback_closure_records(
    *,
    policy: dict[str, Any],
    founder_report: dict[str, Any],
    founder_cases: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    pending = accepted_pending_founder_feedback(founder_report)
    closures = founder_closure_by_id(policy)
    records: list[dict[str, Any]] = []
    for case_id, case in sorted(pending.items()):
        decision = dict_value(case.get("decision"))
        validation = dict_value(decision.get("validation_result"))
        closure = closures.get(case_id, {})
        closure_status = closure.get("closure_status")
        fixture_case = founder_cases.get(case_id, {})
        blockers: list[str] = []
        if not closure:
            blockers.append("missing founder-feedback closure")
        elif closure_status not in {item.value for item in FounderFeedbackClosureStatus}:
            blockers.append("unsupported founder-feedback closure status")
        if closure.get("required_gate") != validation.get("required_gate"):
            blockers.append("closure required_gate must match source validation_result")
        if not fixture_case:
            blockers.append("synthetic closure must reference a governed Phase 125 fixture case")
        elif closure_status == FounderFeedbackClosureStatus.CLOSED_AS_SYNTHETIC_FIXTURE.value:
            if decision.get("kind") != fixture_case.get("expected_decision_kind"):
                blockers.append("synthetic closure decision kind must match fixture catalog")
            if decision.get("gap_class") != fixture_case.get("expected_gap_class"):
                blockers.append("synthetic closure gap class must match fixture catalog")
            if case.get("target_root") != fixture_case.get("target_root"):
                blockers.append("synthetic closure target_root must match fixture catalog")
            if decision.get("mutation_policy") != "controller_artifacts_only":
                blockers.append("synthetic closure mutation_policy must be controller_artifacts_only")
            feedback_record = dict_value(case.get("feedback_record"))
            if decision.get("target_run_id") != feedback_record.get("target_run_id"):
                blockers.append("synthetic closure target_run_id must match feedback record")
            if decision.get("feedback_run_id") != feedback_record.get("run_id"):
                blockers.append("synthetic closure feedback_run_id must match feedback record")
        if not rationale_is_sufficient(closure.get("rationale")):
            blockers.append("closure rationale must explain the decision")
        if closure_status == FounderFeedbackClosureStatus.CLOSED_AS_SYNTHETIC_FIXTURE.value:
            if "synthetic" not in str(closure.get("rationale", "")).lower():
                blockers.append("synthetic fixture closure must explicitly say synthetic")
            if "not production founder feedback" not in str(closure.get("rationale", "")).lower():
                blockers.append("synthetic fixture closure must explicitly state it is not production founder feedback")
        if closure_status == FounderFeedbackClosureStatus.CLOSED_BY_REQUIRED_GATE.value:
            gate_proof = dict_value(closure.get("gate_proof"))
            if gate_proof.get("status") != "passed":
                blockers.append("required-gate closure requires passed gate_proof")
        records.append(
            {
                "case_id": case_id,
                "decision_kind": decision.get("kind"),
                "required_gate": validation.get("required_gate"),
                "closure_status": closure_status,
                "release_blocker_resolved": not blockers,
                "rationale": closure.get("rationale"),
                "blockers": blockers,
            }
        )
    return records


def build_stable_release_blocker_closure_report(
    *,
    policy: dict[str, Any],
    prompt_report: dict[str, Any],
    founder_report: dict[str, Any],
    founder_cases_catalog: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    prompt_report_path: Path | None = None,
    founder_report_path: Path | None = None,
    founder_cases_path: Path | None = None,
) -> dict[str, Any]:
    founder_cases = founder_case_catalog_by_id(founder_cases_catalog or {})
    prompt_records = build_prompt_closure_records(policy=policy, prompt_report=prompt_report)
    founder_records = build_founder_feedback_closure_records(
        policy=policy,
        founder_report=founder_report,
        founder_cases=founder_cases,
    )
    blockers = [
        f"prompt_tightening_closures[{record['candidate_id']}]: {blocker}"
        for record in prompt_records
        for blocker in string_list(record.get("blockers"))
    ]
    blockers.extend(
        f"founder_feedback_closures[{record['case_id']}]: {blocker}"
        for record in founder_records
        for blocker in string_list(record.get("blockers"))
    )
    pending_prompt_ids = set(pending_prompt_tightening_candidates(prompt_report))
    pending_founder_ids = set(accepted_pending_founder_feedback(founder_report))
    extra_prompt_ids = sorted(set(prompt_closure_by_id(policy)) - pending_prompt_ids)
    extra_founder_ids = sorted(set(founder_closure_by_id(policy)) - pending_founder_ids)
    blockers.extend(f"prompt_tightening_closures[{candidate_id}]: extra closure ID is not a current blocker" for candidate_id in extra_prompt_ids)
    blockers.extend(f"founder_feedback_closures[{case_id}]: extra closure ID is not a current blocker" for case_id in extra_founder_ids)
    prompt_summary = dict_value(prompt_report.get("summary"))
    if prompt_summary.get("applied_prompt_catalog_change_count") != 0:
        blockers.append("prompt_tightening_report.summary.applied_prompt_catalog_change_count must be 0")
    if founder_report.get("priority_backlog_id") != "P0-BB-010":
        blockers.append("founder_feedback_report.priority_backlog_id must be P0-BB-010 for synthetic closure")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": StableReleaseBlockerClosureStatus.PASSED.value if not blockers else StableReleaseBlockerClosureStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "prompt_tightening_report_path": str(prompt_report_path or DEFAULT_PROMPT_TIGHTENING_REPORT_PATH),
        "prompt_tightening_report_sha256": artifact_hash(prompt_report_path) if prompt_report_path else None,
        "founder_feedback_report_path": str(founder_report_path or DEFAULT_FOUNDER_FEEDBACK_REPORT_PATH),
        "founder_feedback_report_sha256": artifact_hash(founder_report_path) if founder_report_path else None,
        "founder_feedback_cases_path": str(founder_cases_path or DEFAULT_FOUNDER_FEEDBACK_CASES_PATH),
        "founder_feedback_cases_sha256": artifact_hash(founder_cases_path) if founder_cases_path else None,
        "prompt_tightening_closures": prompt_records,
        "founder_feedback_closures": founder_records,
        "extra_prompt_tightening_closure_ids": extra_prompt_ids,
        "extra_founder_feedback_closure_ids": extra_founder_ids,
        "summary": {
            "prompt_tightening_blocker_count": len(prompt_records),
            "prompt_tightening_closed_count": sum(
                1 for record in prompt_records if record.get("release_blocker_resolved") is True
            ),
            "founder_feedback_blocker_count": len(founder_records),
            "founder_feedback_closed_count": sum(
                1 for record in founder_records if record.get("release_blocker_resolved") is True
            ),
            "unresolved_blocker_count": len(blockers),
        },
        "errors": blockers,
    }


def validate_stable_release_blocker_closure_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    prompt_report: dict[str, Any],
    founder_report: dict[str, Any],
    founder_cases_catalog: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    prompt_report_path: Path | None = None,
    founder_report_path: Path | None = None,
    founder_cases_path: Path | None = None,
) -> list[str]:
    errors = validate_policy(policy)
    expected = build_stable_release_blocker_closure_report(
        policy=policy,
        prompt_report=prompt_report,
        founder_report=founder_report,
        founder_cases_catalog=founder_cases_catalog,
        policy_path=policy_path,
        prompt_report_path=prompt_report_path,
        founder_report_path=founder_report_path,
        founder_cases_path=founder_cases_path,
    )
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "policy_path",
        "policy_sha256",
        "prompt_tightening_report_path",
        "prompt_tightening_report_sha256",
        "founder_feedback_report_path",
        "founder_feedback_report_sha256",
        "founder_feedback_cases_path",
        "founder_feedback_cases_sha256",
        "prompt_tightening_closures",
        "founder_feedback_closures",
        "extra_prompt_tightening_closure_ids",
        "extra_founder_feedback_closure_ids",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt blocker closure evidence")
    if expected["summary"]["unresolved_blocker_count"] != 0:
        errors.append("report.summary.unresolved_blocker_count must be 0 for release closure")
    return errors


def run_stable_release_blocker_closure_gate(config: StableReleaseBlockerClosureConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    prompt_path = resolve_path(config_root, config.prompt_tightening_report_path)
    founder_path = resolve_path(config_root, config.founder_feedback_report_path)
    founder_cases_path = resolve_path(config_root, config.founder_feedback_cases_path)
    missing = [
        str(path)
        for path in (policy_path, prompt_path, founder_path, founder_cases_path)
        if config.require_artifacts and not path.is_file()
    ]
    policy = read_json_object(policy_path)
    prompt_report = read_json_object(prompt_path) if prompt_path.is_file() else {}
    founder_report = read_json_object(founder_path) if founder_path.is_file() else {}
    founder_cases = read_json_object(founder_cases_path) if founder_cases_path.is_file() else {}
    report = build_stable_release_blocker_closure_report(
        policy=policy,
        prompt_report=prompt_report,
        founder_report=founder_report,
        founder_cases_catalog=founder_cases,
        policy_path=policy_path,
        prompt_report_path=prompt_path,
        founder_report_path=founder_path,
        founder_cases_path=founder_cases_path,
    )
    errors = [f"required artifact is missing: {path}" for path in missing]
    errors.extend(
        validate_stable_release_blocker_closure_report(
            report,
            policy=policy,
            prompt_report=prompt_report,
            founder_report=founder_report,
            founder_cases_catalog=founder_cases,
            policy_path=policy_path,
            prompt_report_path=prompt_path,
            founder_report_path=founder_path,
            founder_cases_path=founder_cases_path,
        )
    )
    if errors:
        report["status"] = StableReleaseBlockerClosureStatus.FAILED.value
        report["errors"] = errors
        report["summary"]["unresolved_blocker_count"] = len(errors)
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
