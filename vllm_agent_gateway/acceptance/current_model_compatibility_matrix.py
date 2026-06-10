"""Current localhost model compatibility matrix for Priority 0."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "current_model_compatibility_matrix_policy"
EXPECTED_REPORT_KIND = "current_model_compatibility_matrix_report"
EXPECTED_PHASE = 150
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "current_model_compatibility_matrix_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "current-model-compatibility-matrix" / "phase150"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_STATUS_VALUES = {
    "supported",
    "conditional",
    "monitored",
    "not_governed",
    "not_approved",
    "blocked",
}
REQUIRED_OUTPUT_FORMATS = {"format_a", "json"}


class MatrixStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class CurrentModelCompatibilityMatrixConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"current-model-compatibility-matrix-{utc_timestamp()}.json"


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
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 150")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    version = policy.get("policy_version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append("policy.policy_version must use semantic version x.y.z")
    purpose = str(policy.get("purpose") or "").lower()
    if "without expanding" not in purpose:
        errors.append("policy.purpose must state that the matrix does not expand supported product scope")
    current_model = dict_value(policy.get("current_model"))
    if current_model.get("candidate_model_base_url") != "http://127.0.0.1:8000/v1":
        errors.append("current_model.candidate_model_base_url must be http://127.0.0.1:8000/v1")
    if not string_list(current_model.get("expected_model_ids")):
        errors.append("current_model.expected_model_ids must be a non-empty list")
    if set(string_list(policy.get("status_values"))) != REQUIRED_STATUS_VALUES:
        errors.append("policy.status_values must match the required matrix status values")
    if set(string_list(policy.get("governed_output_formats"))) != REQUIRED_OUTPUT_FORMATS:
        errors.append("policy.governed_output_formats must be format_a and json")
    not_governed = set(string_list(policy.get("not_governed_output_formats")))
    if not_governed & REQUIRED_OUTPUT_FORMATS:
        errors.append("not_governed_output_formats must not include governed formats")
    task_policies = dict_value(policy.get("required_task_policies"))
    for key, expected in {
        "read_only_l1": "approved",
        "draft_only_l1": "approved",
        "approval_gated_l1": "conditional",
        "l2_read_only": "approved",
        "apply_prep": "conditional",
        "real_apply": "not_approved",
        "automatic_model_selection": "not_approved",
    }.items():
        if task_policies.get(key) != expected:
            errors.append(f"required_task_policies.{key} must be {expected}")
    sources = object_list(policy.get("source_artifacts"))
    if not sources:
        errors.append("policy.source_artifacts must contain required artifacts")
    ids = [str(item.get("id")) for item in sources if isinstance(item.get("id"), str)]
    if len(ids) != len(set(ids)):
        errors.append("policy.source_artifacts ids must be unique")
    for index, source in enumerate(sources):
        prefix = f"policy.source_artifacts[{index}]"
        for key in ("id", "type", "path"):
            if not isinstance(source.get(key), str) or not source[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        if source.get("required") is not True:
            errors.append(f"{prefix}.required must be true")
        if "expected_kind" in source and (not isinstance(source.get("expected_kind"), str) or not source["expected_kind"].strip()):
            errors.append(f"{prefix}.expected_kind must be a non-empty string when present")
        if "allowed_statuses" in source and not isinstance(source.get("allowed_statuses"), list):
            errors.append(f"{prefix}.allowed_statuses must be a list when present")
        expected_phase = source.get("expected_phase")
        if expected_phase is not None and not isinstance(expected_phase, int):
            errors.append(f"{prefix}.expected_phase must be an integer when present")
    return errors


def source_ref(path: Path | None, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "priority_backlog_id": payload.get("priority_backlog_id"),
        "created_at": payload.get("created_at"),
        "generated_at": payload.get("generated_at"),
    }


def blocker(code: str, source_id: str, message: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "source_id": source_id,
        "severity": "high",
        "message": message,
        "evidence_refs": evidence_refs or [],
    }


def load_sources(
    *,
    config_root: Path,
    policy: dict[str, Any],
    require_artifacts: bool,
) -> tuple[dict[str, tuple[Path | None, dict[str, Any] | None]], list[str]]:
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]] = {}
    errors: list[str] = []
    for source in object_list(policy.get("source_artifacts")):
        source_id = str(source.get("id"))
        path_value = source.get("path")
        if not isinstance(path_value, str):
            sources[source_id] = (None, None)
            errors.append(f"source {source_id} path is invalid")
            continue
        path = resolve_path(config_root, path_value)
        if not path.is_file():
            sources[source_id] = (None, None)
            if require_artifacts or source.get("required") is True:
                errors.append(f"required source is missing: {path_value}")
            continue
        try:
            sources[source_id] = (path, read_json_object(path))
        except Exception as exc:  # noqa: BLE001
            sources[source_id] = (path, None)
            errors.append(f"source {source_id} is malformed: {type(exc).__name__}: {exc}")
    return sources, errors


def validate_source_contracts(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for source in object_list(policy.get("source_artifacts")):
        source_id = str(source.get("id"))
        path, payload = sources.get(source_id, (None, None))
        evidence = [str(path)] if path is not None else []
        if path is None or payload is None:
            blockers.append(blocker("missing_required_artifact", source_id, "required compatibility source is missing"))
            continue
        expected_kind = source.get("expected_kind")
        if isinstance(expected_kind, str) and payload.get("kind") != expected_kind:
            blockers.append(
                blocker(
                    "source_kind_mismatch",
                    source_id,
                    f"expected kind {expected_kind} but found {payload.get('kind')}",
                    evidence,
                )
            )
        allowed_statuses = source.get("allowed_statuses")
        if isinstance(allowed_statuses, list) and payload.get("status") not in allowed_statuses:
            blockers.append(
                blocker(
                    "source_status_not_allowed",
                    source_id,
                    f"status {payload.get('status')} is not in allowed_statuses",
                    evidence,
                )
            )
        expected_phase = source.get("expected_phase")
        if expected_phase is not None and payload.get("phase") != expected_phase:
            blockers.append(
                blocker(
                    "source_phase_mismatch",
                    source_id,
                    f"expected phase {expected_phase} but found {payload.get('phase')}",
                    evidence,
                )
            )
    return blockers


def payload(sources: dict[str, tuple[Path | None, dict[str, Any] | None]], source_id: str) -> dict[str, Any]:
    return sources.get(source_id, (None, None))[1] or {}


def prompt_task_class(entry: dict[str, Any]) -> str:
    level = entry.get("level")
    workflow = entry.get("selected_workflow")
    if level == "L2":
        return "l2_read_only"
    if workflow == "execution_planning.plan":
        return "draft_only_l1"
    return "read_only_l1"


def prompt_status_for_task(task_class: str, task_policy: dict[str, Any]) -> str:
    status = dict_value(task_policy.get(task_class)).get("status")
    if status == "approved":
        return "supported"
    if status == "conditional":
        return "conditional"
    return "blocked"


def build_prompt_family_matrix(
    coverage: dict[str, Any],
    model_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    task_policy = dict_value(model_profile.get("task_policy"))
    rows: list[dict[str, Any]] = []
    for entry in object_list(coverage.get("entries")):
        level = entry.get("level")
        if level not in {"L1", "L2"}:
            continue
        task_class = prompt_task_class(entry)
        entry_status = entry.get("status")
        compatibility_status = (
            prompt_status_for_task(task_class, task_policy) if entry_status == "implemented" else "not_approved"
        )
        rows.append(
            {
                "id": entry.get("id"),
                "level": level,
                "prompt_family": entry.get("prompt_family"),
                "implementation_status": entry_status,
                "compatibility_status": compatibility_status,
                "selected_workflow": entry.get("selected_workflow"),
                "route_rule": entry.get("route_rule"),
                "task_class": task_class,
                "skill_ids": string_list(entry.get("skill_ids")),
                "tool_ids": string_list(entry.get("tool_ids")),
                "validation_suites": string_list(entry.get("validation_suites")),
            }
        )
    return rows


def build_output_format_matrix(
    *,
    policy: dict[str, Any],
    output_parity: dict[str, Any],
    natural_preference: dict[str, Any],
) -> list[dict[str, Any]]:
    parity_passed = output_parity.get("status") == "passed"
    natural_passed = natural_preference.get("status") == "passed"
    rows: list[dict[str, Any]] = []
    for output_format in string_list(policy.get("governed_output_formats")):
        rows.append(
            {
                "format": output_format,
                "compatibility_status": "supported" if parity_passed and natural_passed else "blocked",
                "evidence": [
                    "runtime-state/output-format-parity/phase124-output-format-parity-live.json",
                    "runtime-state/natural-output-format-preference/phase144/phase144-natural-output-format-preference-live.json",
                ],
                "surfaces": ["gateway", "anythingllm"],
            }
        )
    for output_format in string_list(policy.get("not_governed_output_formats")):
        rows.append(
            {
                "format": output_format,
                "compatibility_status": "not_governed",
                "evidence": ["runtime/release_notes_policy.json"],
                "surfaces": [],
            }
        )
    return rows


def build_skill_tool_matrix(prompt_rows: list[dict[str, Any]]) -> dict[str, Any]:
    skill_counter: Counter[str] = Counter()
    tool_counter: Counter[str] = Counter()
    for row in prompt_rows:
        if row.get("compatibility_status") not in {"supported", "conditional"}:
            continue
        skill_counter.update(string_list(row.get("skill_ids")))
        tool_counter.update(string_list(row.get("tool_ids")))
    return {
        "skill_count": len(skill_counter),
        "tool_count": len(tool_counter),
        "skills": [
            {"skill_id": skill_id, "prompt_family_count": count, "compatibility_status": "supported"}
            for skill_id, count in sorted(skill_counter.items())
        ],
        "tools": [
            {"tool_id": tool_id, "prompt_family_count": count, "compatibility_status": "supported"}
            for tool_id, count in sorted(tool_counter.items())
        ],
    }


def build_anythingllm_matrix(
    *,
    fresh_drift: dict[str, Any],
    output_parity: dict[str, Any],
    natural_preference: dict[str, Any],
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    fresh_summary = dict_value(fresh_drift.get("summary"))
    supported = (
        fresh_drift.get("status") == "passed"
        and "anythingllm" in string_list(fresh_summary.get("required_routes"))
        and output_parity.get("anythingllm_applicable") is True
        and natural_preference.get("anythingllm_applicable") is True
        and scorecard.get("status") == "passed"
    )
    return {
        "compatibility_status": "supported" if supported else "blocked",
        "workspace": "my-workspace",
        "required_routes": string_list(fresh_summary.get("required_routes")),
        "evidence": [
            "runtime-state/fresh-local-model-drift/phase127/phase127-fresh-local-model-drift-report.json",
            "runtime-state/output-format-parity/phase124-output-format-parity-live.json",
            "runtime-state/natural-output-format-preference/phase144/phase144-natural-output-format-preference-live.json",
            "runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json",
        ],
    }


def build_known_failure_modes(watchlist: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in object_list(watchlist.get("items")):
        rows.append(
            {
                "watch_id": item.get("watch_id"),
                "case_ids": string_list(item.get("case_ids")),
                "prompt_family": item.get("prompt_family"),
                "severity": item.get("severity"),
                "risk_class": item.get("risk_class"),
                "repair_owner": item.get("repair_owner"),
                "compatibility_status": "monitored",
                "risk_statement": item.get("risk_statement"),
                "repair_path": item.get("repair_path"),
            }
        )
    return rows


def model_boundaries(model_profile: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    capabilities = dict_value(model_profile.get("capabilities"))
    latency = dict_value(capabilities.get("latency"))
    if latency.get("status") == "unknown":
        boundaries.append(
            {
                "boundary": "latency",
                "compatibility_status": "monitored",
                "reason": "Latency remains unknown in the active model profile.",
            }
        )
    task_policy = dict_value(model_profile.get("task_policy"))
    for key in ("real_apply", "automatic_model_selection"):
        status = dict_value(task_policy.get(key)).get("status")
        boundaries.append(
            {
                "boundary": key,
                "compatibility_status": "not_approved" if status == "not_approved" else "blocked",
                "reason": dict_value(task_policy.get(key)).get("required_evidence")
                or "This capability is outside the governed current-model surface.",
            }
        )
    for output_format in string_list(policy.get("not_governed_output_formats")):
        boundaries.append(
            {
                "boundary": f"output_format:{output_format}",
                "compatibility_status": "not_governed",
                "reason": "Only format_a and json are governed for current chat-quality compatibility.",
            }
        )
    return boundaries


def task_policy_blockers(model_profile: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    required = dict_value(policy.get("required_task_policies"))
    task_policy = dict_value(model_profile.get("task_policy"))
    for key, expected_status in required.items():
        actual_status = dict_value(task_policy.get(key)).get("status")
        if actual_status != expected_status:
            blockers.append(
                blocker(
                    "task_policy_mismatch",
                    "model_capability_profile",
                    f"task policy {key} must be {expected_status} but found {actual_status}",
                )
            )
    return blockers


def model_identity_blockers(model_profile: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    current_model = dict_value(policy.get("current_model"))
    candidate = dict_value(model_profile.get("candidate"))
    if candidate.get("candidate_model_base_url") != current_model.get("candidate_model_base_url"):
        blockers.append(
            blocker(
                "model_base_url_mismatch",
                "model_capability_profile",
                "model capability profile does not describe localhost:8000",
            )
        )
    probe = dict_value(model_profile.get("candidate_model_probe"))
    expected_ids = set(string_list(current_model.get("expected_model_ids")))
    actual_ids = set(string_list(probe.get("model_ids")))
    if probe.get("status") != "passed" or expected_ids - actual_ids:
        blockers.append(
            blocker(
                "model_probe_mismatch",
                "model_capability_profile",
                "model probe does not prove the expected current localhost model id",
            )
        )
    return blockers


def build_current_model_compatibility_matrix_report(
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
    policy_path: Path | None = None,
    input_errors: list[str] | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(input_errors or [])
    source_blockers = validate_source_contracts(policy, sources)
    model_profile = payload(sources, "model_capability_profile")
    coverage = payload(sources, "prompt_skill_coverage")
    fresh_drift = payload(sources, "fresh_local_model_drift")
    output_parity = payload(sources, "output_format_parity")
    natural_preference = payload(sources, "natural_output_format_preference")
    watchlist = payload(sources, "local_model_regression_watchlist")
    watchlist_report = payload(sources, "local_model_regression_watchlist_report")
    scorecard = payload(sources, "contextless_audit_scorecard")
    prompt_rows = build_prompt_family_matrix(coverage, model_profile)
    output_rows = build_output_format_matrix(
        policy=policy,
        output_parity=output_parity,
        natural_preference=natural_preference,
    )
    blockers = source_blockers + task_policy_blockers(model_profile, policy) + model_identity_blockers(model_profile, policy)
    if not any(row.get("level") == "L1" and row.get("compatibility_status") == "supported" for row in prompt_rows):
        blockers.append(blocker("missing_supported_l1", "prompt_skill_coverage", "matrix has no supported L1 prompt families"))
    if not any(row.get("level") == "L2" and row.get("compatibility_status") == "supported" for row in prompt_rows):
        blockers.append(blocker("missing_supported_l2", "prompt_skill_coverage", "matrix has no supported L2 prompt families"))
    if not all(row.get("compatibility_status") == "supported" for row in output_rows if row.get("format") in REQUIRED_OUTPUT_FORMATS):
        blockers.append(blocker("output_format_not_supported", "output_formats", "governed output formats are not fully supported"))
    anythingllm = build_anythingllm_matrix(
        fresh_drift=fresh_drift,
        output_parity=output_parity,
        natural_preference=natural_preference,
        scorecard=scorecard,
    )
    if anythingllm.get("compatibility_status") != "supported":
        blockers.append(blocker("anythingllm_not_supported", "anythingllm", "AnythingLLM compatibility evidence is incomplete"))
    known_modes = build_known_failure_modes(watchlist)
    level_counts = Counter(str(row.get("level")) for row in prompt_rows)
    compatibility_counts = Counter(str(row.get("compatibility_status")) for row in prompt_rows)
    matrix = {
        "model": {
            "candidate_id": dict_value(model_profile.get("candidate")).get("candidate_id"),
            "candidate_model_base_url": dict_value(model_profile.get("candidate")).get("candidate_model_base_url"),
            "model_ids": string_list(dict_value(model_profile.get("candidate_model_probe")).get("model_ids")),
            "profile_status": model_profile.get("status"),
            "capabilities": model_profile.get("capabilities"),
        },
        "prompt_families": prompt_rows,
        "output_formats": output_rows,
        "skill_tool_support": build_skill_tool_matrix(prompt_rows),
        "anythingllm": anythingllm,
        "known_failure_modes": known_modes,
        "known_boundaries": model_boundaries(model_profile, policy),
        "watchlist_summary": {
            "catalog_item_count": len(known_modes),
            "report_summary": watchlist_report.get("summary"),
            "severity_counts": watchlist_report.get("severity_counts"),
            "repair_owner_counts": watchlist_report.get("repair_owner_counts"),
        },
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": MatrixStatus.PASSED.value if not blockers and not errors else MatrixStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_ref": source_ref(policy_path, policy),
        "source_refs": {
            source_id: source_ref(path, source_payload)
            for source_id, (path, source_payload) in sources.items()
        },
        "matrix": matrix,
        "blockers": blockers,
        "summary": {
            "prompt_family_count": len(prompt_rows),
            "l1_prompt_family_count": level_counts.get("L1", 0),
            "l2_prompt_family_count": level_counts.get("L2", 0),
            "supported_prompt_family_count": compatibility_counts.get("supported", 0),
            "conditional_prompt_family_count": compatibility_counts.get("conditional", 0),
            "known_failure_mode_count": len(known_modes),
            "governed_output_format_count": len(REQUIRED_OUTPUT_FORMATS),
            "anythingllm_compatibility_status": anythingllm.get("compatibility_status"),
            "model_profile_status": model_profile.get("status"),
            "blocker_count": len(blockers),
            "error_count": len(errors),
        },
        "errors": errors,
    }
    return report


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"generated_at", "report_path", "markdown_report_path"}
    }


def validate_current_model_compatibility_matrix_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]],
    policy_path: Path | None = None,
    input_errors: list[str] | None = None,
) -> list[str]:
    expected = build_current_model_compatibility_matrix_report(
        policy=policy,
        sources=sources,
        policy_path=policy_path,
        input_errors=input_errors,
    )
    errors: list[str] = []
    for key, value in stable_report_view(expected).items():
        if stable_report_view(report).get(key) != value:
            errors.append(f"report.{key} must match rebuilt current-model compatibility matrix")
    return errors


def markdown_from_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    matrix = dict_value(report.get("matrix"))
    model = dict_value(matrix.get("model"))
    lines = [
        "# Current-Model Compatibility Matrix",
        "",
        f"- Status: {report.get('status')}",
        f"- Model: {', '.join(string_list(model.get('model_ids')))}",
        f"- Profile status: {summary.get('model_profile_status')}",
        f"- Prompt families: {summary.get('prompt_family_count')}",
        f"- Supported prompt families: {summary.get('supported_prompt_family_count')}",
        f"- Conditional prompt families: {summary.get('conditional_prompt_family_count')}",
        f"- AnythingLLM: {summary.get('anythingllm_compatibility_status')}",
        f"- Known monitored failure modes: {summary.get('known_failure_mode_count')}",
        f"- Blockers: {summary.get('blocker_count')}",
        "",
        "## Output Formats",
        "",
    ]
    for row in object_list(matrix.get("output_formats")):
        lines.append(f"- {row.get('format')}: {row.get('compatibility_status')}")
    lines.extend(["", "## Known Boundaries", ""])
    for row in object_list(matrix.get("known_boundaries")):
        lines.append(f"- {row.get('boundary')}: {row.get('compatibility_status')} - {row.get('reason')}")
    lines.extend(["", "## Blockers", ""])
    blockers = object_list(report.get("blockers"))
    if not blockers:
        lines.append("- None")
    else:
        for item in blockers:
            lines.append(f"- {item.get('code')} ({item.get('source_id')}): {item.get('message')}")
    lines.append("")
    return "\n".join(lines)


def run_current_model_compatibility_matrix(config: CurrentModelCompatibilityMatrixConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    try:
        policy = read_json_object(policy_path)
    except Exception as exc:  # noqa: BLE001
        policy = {}
        load_errors = [f"policy could not be loaded: {type(exc).__name__}: {exc}"]
    else:
        load_errors = []
    sources, source_errors = load_sources(
        config_root=config_root,
        policy=policy,
        require_artifacts=config.require_artifacts,
    )
    load_errors.extend(source_errors)
    report = build_current_model_compatibility_matrix_report(
        policy=policy,
        sources=sources,
        policy_path=policy_path if policy_path.is_file() else None,
        input_errors=load_errors,
    )
    validation_errors = validate_current_model_compatibility_matrix_report(
        report,
        policy=policy,
        sources=sources,
        policy_path=policy_path if policy_path.is_file() else None,
        input_errors=load_errors,
    )
    if validation_errors:
        report["status"] = MatrixStatus.FAILED.value
        report["errors"] = list(report.get("errors", [])) + validation_errors
        report["summary"]["error_count"] = len(report["errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        markdown_path = config.markdown_output_path
        if not markdown_path.is_absolute():
            markdown_path = config_root / markdown_path
        write_text(markdown_path, markdown_from_report(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
