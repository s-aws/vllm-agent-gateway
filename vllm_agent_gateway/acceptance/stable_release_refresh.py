"""Phase 160 stable release refresh gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "stable_release_refresh_policy"
EXPECTED_REPORT_KIND = "stable_release_refresh_report"
EXPECTED_PHASE = 160
EXPECTED_BACKLOG_ID = "P0-BB-024"
SUPPORTED_POLICY_BACKLOG_IDS = {
    160: "P0-BB-024",
    170: "P0-BB-034",
}
SUPPORTED_NEXT_PHASES = {
    160: 161,
    170: None,
}
DEFAULT_POLICY_PATH = Path("runtime") / "stable_release_refresh_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "stable-release-refresh" / "phase160"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase160-stable-release-refresh-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase160-stable-release-refresh-report.md"
REQUIRED_RELEASE_LIMITATIONS = {
    "not_production_deployment",
    "not_advanced_broad_refactor_orchestration",
    "not_every_repository_language_or_coding_task",
    "not_direct_mutation_of_protected_fixtures",
    "not_unsupported_output_format_parity",
    "not_automatic_model_selection",
}
REQUIRED_REFRESH_COMMANDS = {
    "stable_chat_quality_release",
    "stable_release_reset_rehearsal",
    "model_swap_smoke_probe",
    "v1_product_readiness_review",
    "v1_stable_release_decision",
}
PHASE160_REQUIRED_REPORT_IDS = {
    "stable_chat_quality_release",
    "stable_release_reset_rehearsal",
    "model_swap_smoke_probe",
    "v1_product_readiness_review",
    "v1_stable_release_decision",
    "founder_field_round1",
    "transcript_quality_feedback_intake",
    "priority0_repair_loop",
}
PHASE170_ADDITIONAL_REPORT_IDS = {
    "post_restart_runtime_readiness_phase163",
    "founder_field_round2",
    "prompt_advisory_closure",
    "generic_chat_vague_prompt_contract",
    "anythingllm_ui_replay_phase167",
    "answer_first_ui_replay_phase168",
    "post_restart_runtime_readiness_phase168",
    "failure_to_roadmap_phase169",
    "release_notes_phase169",
}
REFRESH_OUTPUTS = {
    "stable_chat_quality_release": [
        Path("runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json"),
    ],
    "stable_release_reset_rehearsal": [
        Path("runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json"),
    ],
    "model_swap_smoke_probe": [
        Path("runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json"),
        Path(
            "runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report-current-model-compatibility.json"
        ),
    ],
    "v1_product_readiness_review": [
        Path("runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json"),
    ],
    "v1_stable_release_decision": [
        Path("runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json"),
    ],
}


class StableReleaseRefreshStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class StableReleaseRefreshConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_REPORT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_PATH
    run_refresh: bool = False
    timeout_seconds: int = 1800
    execute_reset_start: bool = False
    execute_recovery: bool = False


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


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def policy_phase(policy: dict[str, Any]) -> int:
    return policy.get("phase") if isinstance(policy.get("phase"), int) else EXPECTED_PHASE


def policy_backlog_id(policy: dict[str, Any]) -> str:
    value = policy.get("priority_backlog_id")
    return value if isinstance(value, str) and value else EXPECTED_BACKLOG_ID


def required_report_ids_for_phase(phase: int) -> set[str]:
    if phase == 170:
        return PHASE160_REQUIRED_REPORT_IDS | PHASE170_ADDITIONAL_REPORT_IDS
    return set(PHASE160_REQUIRED_REPORT_IDS)


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    phase = policy.get("phase")
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if phase not in SUPPORTED_POLICY_BACKLOG_IDS:
        errors.append("policy.phase must be one of " + ", ".join(str(item) for item in sorted(SUPPORTED_POLICY_BACKLOG_IDS)))
    expected_backlog_id = SUPPORTED_POLICY_BACKLOG_IDS.get(phase)
    if expected_backlog_id is not None and policy.get("priority_backlog_id") != expected_backlog_id:
        errors.append(f"policy.priority_backlog_id must be {expected_backlog_id}")
    if set(string_list(policy.get("required_refresh_commands"))) != REQUIRED_REFRESH_COMMANDS:
        errors.append("policy.required_refresh_commands must match the Phase 160 refresh command set")
    reports = object_list(policy.get("required_reports"))
    ids = [str(item.get("id")) for item in reports if isinstance(item.get("id"), str)]
    if len(ids) != len(set(ids)):
        errors.append("policy.required_reports ids must be unique")
    required_ids = required_report_ids_for_phase(phase if isinstance(phase, int) else EXPECTED_PHASE)
    if set(ids) != required_ids:
        errors.append("policy.required_reports must include the governed stable refresh report IDs")
    for index, item in enumerate(reports):
        prefix = f"policy.required_reports[{index}]"
        for key in ("id", "path", "expected_kind", "expected_status"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        if "expected_phase" in item and not isinstance(item.get("expected_phase"), int):
            errors.append(f"{prefix}.expected_phase must be an integer")
        if phase == 160 and not isinstance(item.get("expected_phase"), int):
            errors.append(f"{prefix}.expected_phase must be an integer for Phase 160 policy")
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append("policy.required_target_roots must include both frozen Coinbase fixtures")
    if set(string_list(policy.get("expected_model_ids"))) != {"Qwen3-Coder-30B-A3B-Instruct"}:
        errors.append("policy.expected_model_ids must contain Qwen3-Coder-30B-A3B-Instruct")
    if set(string_list(policy.get("allowed_phase159_repair_modes"))) != {"no_repair_required", "repairs_closed"}:
        errors.append("policy.allowed_phase159_repair_modes must be no_repair_required and repairs_closed")
    if set(string_list(policy.get("required_release_limitations"))) != REQUIRED_RELEASE_LIMITATIONS:
        errors.append("policy.required_release_limitations must match governed release limitations")
    if phase in SUPPORTED_NEXT_PHASES and policy.get("next_phase") != SUPPORTED_NEXT_PHASES[phase]:
        errors.append(f"policy.next_phase must be {SUPPORTED_NEXT_PHASES[phase]}")
    return errors


def report_policy_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in object_list(policy.get("required_reports"))
        if isinstance(item.get("id"), str)
    }


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "readiness": payload.get("readiness"),
        "recommendation": payload.get("recommendation"),
        "decision": dict_value(decision).get("decision") if isinstance(decision, dict) else decision,
        "repair_mode": payload.get("repair_mode"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def load_sources(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[str]]:
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[str] = []
    for item in object_list(policy.get("required_reports")):
        report_id = str(item.get("id"))
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            sources[report_id] = (None, {})
            errors.append(f"required report {report_id} path is invalid")
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            sources[report_id] = (path, {})
            errors.append(f"required report is missing: {raw_path}")
            continue
        try:
            sources[report_id] = (path, read_json_object(path))
        except Exception as exc:  # noqa: BLE001
            sources[report_id] = (path, {})
            errors.append(f"required report {report_id} is malformed: {type(exc).__name__}: {exc}")
    return sources, errors


def expected_report_contract_errors(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
) -> list[dict[str, Any]]:
    errors = [
        {"id": f"load_error.{index}", "source": "input_loading", "severity": "high", "message": error}
        for index, error in enumerate(load_errors)
    ]
    for report_id, item in report_policy_by_id(policy).items():
        path, payload = sources.get(report_id, (None, {}))
        messages: list[str] = []
        if path is None or not path.is_file():
            messages.append("required report is missing")
        if payload.get("kind") != item.get("expected_kind"):
            messages.append(f"kind must be {item.get('expected_kind')}")
        if payload.get("status") != item.get("expected_status"):
            messages.append(f"status must be {item.get('expected_status')}")
        if isinstance(item.get("expected_phase"), int) and payload.get("phase") != item.get("expected_phase"):
            messages.append(f"phase must be {item.get('expected_phase')}")
        expected_readiness = item.get("expected_readiness")
        if isinstance(expected_readiness, str) and payload.get("readiness") != expected_readiness:
            messages.append(f"readiness must be {expected_readiness}")
        expected_recommendation = item.get("expected_recommendation")
        if isinstance(expected_recommendation, str) and payload.get("recommendation") != expected_recommendation:
            messages.append(f"recommendation must be {expected_recommendation}")
        expected_decision = item.get("expected_decision")
        if isinstance(expected_decision, str):
            decision = payload.get("decision")
            actual_decision = dict_value(decision).get("decision") if isinstance(decision, dict) else decision
            if actual_decision != expected_decision:
                messages.append(f"decision must be {expected_decision}")
        source_errors = payload.get("errors")
        if isinstance(source_errors, list) and source_errors:
            messages.append("errors must be empty")
        validation_errors = payload.get("validation_errors")
        if isinstance(validation_errors, list) and validation_errors:
            messages.append("validation_errors must be empty")
        for message in messages:
            errors.append(
                {
                    "id": f"{report_id}.{message.replace(' ', '_')}",
                    "source": report_id,
                    "severity": "high",
                    "message": message,
                    "path": str(path) if path else None,
                }
            )
    return errors


def refresh_command_errors(policy: dict[str, Any], refresh_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    required_ids = set(string_list(policy.get("required_refresh_commands")))
    seen_ids = [str(item.get("id")) for item in refresh_results if isinstance(item.get("id"), str)]
    if set(seen_ids) != required_ids:
        errors.append(
            {
                "id": "refresh_commands.ids",
                "source": "refresh_commands",
                "severity": "high",
                "message": "refresh command IDs must match the Phase 160 required command set",
            }
        )
    for duplicate in sorted({item for item in seen_ids if seen_ids.count(item) > 1}):
        errors.append(
            {
                "id": f"refresh_commands.{duplicate}.duplicate",
                "source": "refresh_commands",
                "severity": "high",
                "message": "refresh command IDs must be unique",
            }
        )
    for item in refresh_results:
        command_id = item.get("id")
        if command_id not in required_ids:
            continue
        if item.get("returncode") != 0:
            errors.append(
                {
                    "id": f"refresh_commands.{command_id}.returncode",
                    "source": "refresh_commands",
                    "severity": "high",
                    "message": "refresh command must exit 0",
                }
            )
        if not isinstance(item.get("command"), list) or not item["command"]:
            errors.append(
                {
                    "id": f"refresh_commands.{command_id}.command",
                    "source": "refresh_commands",
                    "severity": "high",
                    "message": "refresh command must record argv",
                }
            )
        outputs = object_list(item.get("outputs"))
        expected_outputs = [str(path) for path in REFRESH_OUTPUTS.get(str(command_id), [])]
        output_paths = [str(output.get("path")) for output in outputs if isinstance(output.get("path"), str)]
        if output_paths != expected_outputs:
            errors.append(
                {
                    "id": f"refresh_commands.{command_id}.outputs",
                    "source": "refresh_commands",
                    "severity": "high",
                    "message": "refresh command outputs must match the governed output path list",
                }
            )
        for output in outputs:
            if output.get("exists") is not True:
                errors.append(
                    {
                        "id": f"refresh_commands.{command_id}.{output.get('path')}.missing_output",
                        "source": "refresh_commands",
                        "severity": "high",
                        "message": "refresh command output file must exist after command execution",
                    }
                )
            if not isinstance(output.get("sha256"), str) or len(str(output.get("sha256"))) != 64:
                errors.append(
                    {
                        "id": f"refresh_commands.{command_id}.{output.get('path')}.sha256",
                        "source": "refresh_commands",
                        "severity": "high",
                        "message": "refresh command output file must have a sha256 hash",
                    }
                )
    return errors


def cross_report_errors(policy: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    founder = sources.get("founder_field_round1", (None, {}))[1]
    founder_summary = dict_value(founder.get("summary"))
    if set(string_list(founder_summary.get("target_roots"))) != set(string_list(policy.get("required_target_roots"))):
        errors.append(
            {
                "id": "founder_field_round1.target_roots",
                "source": "founder_field_round1",
                "severity": "high",
                "message": "Phase 157 field round must cover both frozen Coinbase fixtures",
            }
        )
    if founder_summary.get("blocker_case_count") != 0:
        errors.append(
            {
                "id": "founder_field_round1.blockers",
                "source": "founder_field_round1",
                "severity": "high",
                "message": "Phase 157 field round must have zero blocker cases before stable refresh",
            }
        )
    intake = sources.get("transcript_quality_feedback_intake", (None, {}))[1]
    repair = sources.get("priority0_repair_loop", (None, {}))[1]
    intake_summary = dict_value(intake.get("summary"))
    repair_summary = dict_value(repair.get("summary"))
    if intake_summary.get("phase159_eligible_count") != repair_summary.get("phase159_eligible_count"):
        errors.append(
            {
                "id": "phase158_phase159.eligible_count_mismatch",
                "source": "priority0_repair_loop",
                "severity": "high",
                "message": "Phase 158 and Phase 159 eligible finding counts must match",
            }
        )
    if repair.get("repair_mode") not in set(string_list(policy.get("allowed_phase159_repair_modes"))):
        errors.append(
            {
                "id": "priority0_repair_loop.repair_mode",
                "source": "priority0_repair_loop",
                "severity": "high",
                "message": "Phase 159 repair_mode must be no_repair_required or repairs_closed",
            }
        )
    model_swap = sources.get("model_swap_smoke_probe", (None, {}))[1]
    model_decision = dict_value(model_swap.get("decision"))
    if set(string_list(model_decision.get("actual_model_ids"))) != set(string_list(policy.get("expected_model_ids"))):
        errors.append(
            {
                "id": "model_swap_smoke_probe.actual_model_ids",
                "source": "model_swap_smoke_probe",
                "severity": "high",
                "message": "current localhost model identity must match the governed expected model",
            }
        )
    if model_decision.get("full_drift_gate_required") is not False:
        errors.append(
            {
                "id": "model_swap_smoke_probe.full_drift_gate_required",
                "source": "model_swap_smoke_probe",
                "severity": "high",
                "message": "model swap smoke must explicitly prove full_drift_gate_required=false for stable refresh",
            }
        )
    stable_decision = sources.get("v1_stable_release_decision", (None, {}))[1]
    if set(string_list(stable_decision.get("release_limitations"))) != set(
        string_list(policy.get("required_release_limitations"))
    ):
        errors.append(
            {
                "id": "v1_stable_release_decision.release_limitations",
                "source": "v1_stable_release_decision",
                "severity": "high",
                "message": "release limitations must remain unchanged",
            }
        )
    if founder_summary.get("case_count") != 30:
        errors.append(
            {
                "id": "founder_field_round1.case_count",
                "source": "founder_field_round1",
                "severity": "high",
                "message": "Phase 157 field round must include the governed 30-case round",
            }
        )
    if founder_summary.get("advisory_case_count") != 14:
        errors.append(
            {
                "id": "founder_field_round1.advisory_case_count",
                "source": "founder_field_round1",
                "severity": "high",
                "message": "Phase 157 advisory count must remain 14 for this refresh proof",
            }
        )
    if intake_summary.get("source_case_count") != founder_summary.get("case_count"):
        errors.append(
            {
                "id": "phase157_phase158.case_count_mismatch",
                "source": "transcript_quality_feedback_intake",
                "severity": "high",
                "message": "Phase 158 source_case_count must match Phase 157 case_count",
            }
        )
    if intake_summary.get("accepted_finding_count") != founder_summary.get("advisory_case_count"):
        errors.append(
            {
                "id": "phase157_phase158.advisory_count_mismatch",
                "source": "transcript_quality_feedback_intake",
                "severity": "high",
                "message": "Phase 158 accepted findings must match Phase 157 advisory findings for this refresh proof",
            }
        )
    if repair_summary.get("monitoring_only_count") != intake_summary.get("accepted_finding_count"):
        errors.append(
            {
                "id": "phase158_phase159.monitoring_count_mismatch",
                "source": "priority0_repair_loop",
                "severity": "high",
                "message": "Phase 159 monitoring-only count must match Phase 158 accepted findings",
            }
        )
    if repair_summary.get("open_repair_count") != 0:
        errors.append(
            {
                "id": "priority0_repair_loop.open_repair_count",
                "source": "priority0_repair_loop",
                "severity": "high",
                "message": "Phase 159 must have zero open repairs before stable refresh",
            }
        )
    if policy_phase(policy) != 170:
        return errors

    phase163 = sources.get("post_restart_runtime_readiness_phase163", (None, {}))[1]
    phase163_summary = dict_value(phase163.get("summary"))
    if phase163.get("decision") != "ready_after_restart" or phase163_summary.get("missing_required_surface_count") != 0:
        errors.append(
            {
                "id": "phase163_post_restart_runtime_readiness.ready",
                "source": "post_restart_runtime_readiness_phase163",
                "severity": "high",
                "message": "Phase 163 post-restart readiness must prove ready_after_restart with zero missing surfaces",
            }
        )
    if phase163_summary.get("covered_surface_count") != phase163_summary.get("required_surface_count"):
        errors.append(
            {
                "id": "phase163_post_restart_runtime_readiness.coverage",
                "source": "post_restart_runtime_readiness_phase163",
                "severity": "high",
                "message": "Phase 163 covered surfaces must match required surfaces",
            }
        )

    round2 = sources.get("founder_field_round2", (None, {}))[1]
    round2_summary = dict_value(round2.get("summary"))
    round2_counts = dict_value(round2_summary.get("classification_counts"))
    if round2_summary.get("case_count") != 16 or round2_counts.get("blocker") != 0:
        errors.append(
            {
                "id": "phase164_founder_field_round2.case_quality",
                "source": "founder_field_round2",
                "severity": "high",
                "message": "Phase 164 founder field round 2 must include 16 cases and zero blockers",
            }
        )
    if round2_summary.get("min_score", 0) < 85:
        errors.append(
            {
                "id": "phase164_founder_field_round2.min_score",
                "source": "founder_field_round2",
                "severity": "high",
                "message": "Phase 164 minimum score must remain at least 85",
            }
        )
    if set(string_list(round2_summary.get("target_roots"))) != set(string_list(policy.get("required_target_roots"))):
        errors.append(
            {
                "id": "phase164_founder_field_round2.target_roots",
                "source": "founder_field_round2",
                "severity": "high",
                "message": "Phase 164 must cover both frozen Coinbase fixtures",
            }
        )

    closure = sources.get("prompt_advisory_closure", (None, {}))[1]
    closure_summary = dict_value(closure.get("summary"))
    if closure_summary.get("product_gap_escalation_count") != 6 or closure_summary.get("validation_error_count") != 0:
        errors.append(
            {
                "id": "phase165_prompt_advisory_closure.product_gaps",
                "source": "prompt_advisory_closure",
                "severity": "high",
                "message": "Phase 165 must close with six product-gap escalations and zero validation errors",
            }
        )

    generic = sources.get("generic_chat_vague_prompt_contract", (None, {}))[1]
    generic_summary = dict_value(generic.get("summary"))
    if (
        generic_summary.get("failed_case_count") != 0
        or generic_summary.get("fixture_state_changed") is not False
        or generic_summary.get("target_root_count") != 2
    ):
        errors.append(
            {
                "id": "phase166_generic_chat_vague_prompt_contract.summary",
                "source": "generic_chat_vague_prompt_contract",
                "severity": "high",
                "message": "Phase 166 generic/vague contract must have zero failures, unchanged fixtures, and both target roots",
            }
        )

    for report_id in ("anythingllm_ui_replay_phase167", "answer_first_ui_replay_phase168"):
        ui_report = sources.get(report_id, (None, {}))[1]
        ui = dict_value(ui_report.get("ui"))
        cases = object_list(ui.get("cases"))
        if ui_report.get("fixture_unchanged") is not True or ui.get("status") != "passed" or len(cases) < 11:
            errors.append(
                {
                    "id": f"{report_id}.ui_replay",
                    "source": report_id,
                    "severity": "high",
                    "message": "AnythingLLM UI replay must pass, keep fixtures unchanged, and include the governed 11-case mixed set",
                }
            )
        if any(case.get("status") != "passed" for case in cases):
            errors.append(
                {
                    "id": f"{report_id}.case_status",
                    "source": report_id,
                    "severity": "high",
                    "message": "All UI replay cases must pass",
                }
            )

    phase168 = sources.get("post_restart_runtime_readiness_phase168", (None, {}))[1]
    phase168_summary = dict_value(phase168.get("summary"))
    if phase168.get("decision") != "ready_after_restart" or phase168_summary.get("missing_required_surface_count") != 0:
        errors.append(
            {
                "id": "phase168_post_restart_runtime_readiness.ready",
                "source": "post_restart_runtime_readiness_phase168",
                "severity": "high",
                "message": "Phase 168 post-restart readiness must prove ready_after_restart with zero missing surfaces",
            }
        )

    failure_to_roadmap = sources.get("failure_to_roadmap_phase169", (None, {}))[1]
    ftr_summary = dict_value(failure_to_roadmap.get("summary"))
    if (
        ftr_summary.get("proposal_count") != 6
        or ftr_summary.get("unapproved_proposal_count") != 6
        or ftr_summary.get("release_blocker_count") != 0
        or ftr_summary.get("roadmap_mutation_allowed") is not False
        or ftr_summary.get("source_mutation_allowed") is not False
    ):
        errors.append(
            {
                "id": "phase169_failure_to_roadmap.proposals",
                "source": "failure_to_roadmap_phase169",
                "severity": "high",
                "message": "Phase 169 must produce six unapproved proposals with zero release blockers and no mutation authority",
            }
        )

    release_notes = sources.get("release_notes_phase169", (None, {}))[1]
    release_summary = dict_value(release_notes.get("summary"))
    if release_summary.get("error_count") != 0 or release_summary.get("stable_blocker_count") != 0:
        errors.append(
            {
                "id": "phase169_release_notes.summary",
                "source": "release_notes_phase169",
                "severity": "high",
                "message": "Phase 169 release notes validation must have zero errors and zero stable blockers",
            }
        )
    return errors


def refresh_commands(config_root: Path, *, execute_reset_start: bool, execute_recovery: bool) -> list[tuple[str, list[str]]]:
    py = sys.executable
    reset_command = [
        py,
        "scripts/validate_stable_release_reset_rehearsal.py",
        "--output-path",
        "runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json",
    ]
    if execute_reset_start:
        reset_command.append("--execute-reset-start")
    if execute_recovery:
        reset_command.append("--execute-recovery")
    return [
        (
            "stable_chat_quality_release",
            [
                py,
                "scripts/validate_stable_chat_quality_release.py",
                "--require-artifacts",
                "--output-path",
                "runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json",
            ],
        ),
        ("stable_release_reset_rehearsal", reset_command),
        (
            "model_swap_smoke_probe",
            [
                py,
                "scripts/validate_model_swap_smoke_probe.py",
                "--output-path",
                "runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json",
                "--markdown-output-path",
                "runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.md",
                "--compatibility-output-path",
                "runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report-current-model-compatibility.json",
                "--compatibility-markdown-output-path",
                "runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report-current-model-compatibility.md",
            ],
        ),
        (
            "v1_product_readiness_review",
            [
                py,
                "scripts/validate_v1_product_readiness_review.py",
                "--output-path",
                "runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json",
                "--markdown-output-path",
                "runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.md",
            ],
        ),
        (
            "v1_stable_release_decision",
            [
                py,
                "scripts/validate_v1_stable_release_decision.py",
                "--output-path",
                "runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json",
                "--markdown-output-path",
                "runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.md",
            ],
        ),
    ]


def output_records(config_root: Path, command_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative_path in REFRESH_OUTPUTS.get(command_id, []):
        path = config_root / relative_path
        records.append(
            {
                "path": str(relative_path),
                "exists": path.is_file(),
                "sha256": artifact_hash(path),
            }
        )
    return records


def run_refresh_commands(
    config_root: Path,
    *,
    timeout_seconds: int,
    execute_reset_start: bool,
    execute_recovery: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command_id, command in refresh_commands(
        config_root,
        execute_reset_start=execute_reset_start,
        execute_recovery=execute_recovery,
    ):
        try:
            completed = subprocess.run(
                command,
                cwd=config_root,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            result = {
                "id": command_id,
                "command": command,
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:],
                "outputs": output_records(config_root, command_id),
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "id": command_id,
                "command": command,
                "returncode": "timeout",
                "stdout_tail": str(exc.stdout or "")[-4000:],
                "stderr_tail": str(exc.stderr or "")[-4000:],
                "outputs": output_records(config_root, command_id),
                "exception": "TimeoutExpired",
            }
        except Exception as exc:  # noqa: BLE001
            result = {
                "id": command_id,
                "command": command,
                "returncode": "exception",
                "stdout_tail": "",
                "stderr_tail": f"{type(exc).__name__}: {exc}",
                "outputs": output_records(config_root, command_id),
                "exception": type(exc).__name__,
            }
        results.append(
            result
        )
    return results


def build_stable_release_refresh_report(
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
    refresh_results: list[dict[str, Any]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    phase = policy_phase(policy)
    backlog_id = policy_backlog_id(policy)
    validation_errors = [
        {
            "id": f"policy.{index}",
            "source": "policy",
            "severity": "high",
            "message": error,
        }
        for index, error in enumerate(validate_policy(policy))
    ]
    validation_errors.extend(expected_report_contract_errors(policy, sources, load_errors))
    validation_errors.extend(refresh_command_errors(policy, refresh_results))
    validation_errors.extend(cross_report_errors(policy, sources))
    source_refs = {
        report_id: source_ref(path, payload)
        for report_id, (path, payload) in sorted(sources.items())
    }
    phase169_summary = dict_value(sources.get("failure_to_roadmap_phase169", (None, {}))[1].get("summary"))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": phase,
        "priority_backlog_id": backlog_id,
        "status": StableReleaseRefreshStatus.PASSED.value
        if not validation_errors
        else StableReleaseRefreshStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_ref": source_ref(policy_path, policy),
        "source_refs": source_refs,
        "refresh_results": refresh_results,
        "validation_errors": validation_errors,
        "readiness": "ready_for_founder_testing" if not validation_errors else "blocked",
        "decision": "release_for_founder_testing" if not validation_errors else "blocked",
        "next_phase": policy.get("next_phase"),
        "summary": {
            "refresh_command_count": len(refresh_results),
            "source_report_count": len(source_refs),
            "validation_error_count": len(validation_errors),
            "readiness": "ready_for_founder_testing" if not validation_errors else "blocked",
            "decision": "release_for_founder_testing" if not validation_errors else "blocked",
            "phase159_repair_mode": source_refs.get("priority0_repair_loop", {}).get("repair_mode"),
            "model_ids": dict_value(sources.get("model_swap_smoke_probe", (None, {}))[1].get("decision")).get(
                "actual_model_ids"
            ),
            "phase169_proposal_count": phase169_summary.get("proposal_count"),
            "phase169_release_blocker_count": phase169_summary.get("release_blocker_count"),
        },
    }
    return report


def stable_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "status",
            "policy_ref",
            "source_refs",
            "refresh_results",
            "validation_errors",
            "readiness",
            "decision",
            "next_phase",
            "summary",
        )
    }


def validate_stable_release_refresh_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
    refresh_results: list[dict[str, Any]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_stable_release_refresh_report(
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        refresh_results=refresh_results,
        policy_path=policy_path,
    )
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt stable release refresh report"]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Stable Release Refresh",
        "",
        f"- Status: {report.get('status')}",
        f"- Readiness: {report.get('readiness')}",
        f"- Decision: {report.get('decision')}",
        f"- Refresh commands: {summary.get('refresh_command_count')}",
        f"- Source reports: {summary.get('source_report_count')}",
        f"- Validation errors: {summary.get('validation_error_count')}",
        "",
        "## Refresh Commands",
        "",
        "| ID | Return Code |",
        "| --- | --- |",
    ]
    for item in object_list(report.get("refresh_results")):
        lines.append(f"| {item.get('id')} | {item.get('returncode')} |")
    lines.extend(["", "## Source Reports", ""])
    for report_id, ref in dict_value(report.get("source_refs")).items():
        lines.append(
            f"- {report_id}: {dict_value(ref).get('kind')} status={dict_value(ref).get('status')} sha256={dict_value(ref).get('sha256')}"
        )
    lines.extend(["", "## Validation Errors", ""])
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- {error.get('id')}: {error.get('message')}" for error in errors)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def run_stable_release_refresh(config: StableReleaseRefreshConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path) if config.markdown_output_path else None
    policy = read_json_object(policy_path)
    refresh_results = (
        run_refresh_commands(
            config_root,
            timeout_seconds=config.timeout_seconds,
            execute_reset_start=config.execute_reset_start,
            execute_recovery=config.execute_recovery,
        )
        if config.run_refresh
        else []
    )
    sources, load_errors = load_sources(config_root, policy)
    report = build_stable_release_refresh_report(
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        refresh_results=refresh_results,
        policy_path=policy_path,
    )
    validation_errors = validate_stable_release_refresh_report(
        report,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        refresh_results=refresh_results,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = StableReleaseRefreshStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "stable_release_refresh",
                    "severity": "high",
                    "message": error,
                }
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
    return report
