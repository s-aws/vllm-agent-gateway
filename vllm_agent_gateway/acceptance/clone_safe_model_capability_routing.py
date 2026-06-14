"""Phase 235 clone-safe model capability routing gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "clone_safe_model_capability_routing_policy"
EXPECTED_REPORT_KIND = "clone_safe_model_capability_routing_report"
EXPECTED_PHASE = 235
EXPECTED_BACKLOG_ID = "P0-M14-235"
EXPECTED_MILESTONE_ID = "M14"
DEFAULT_POLICY_PATH = Path("runtime") / "clone_safe_model_capability_routing_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase235" / "phase235-clone-safe-model-capability-routing-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase235" / "phase235-clone-safe-model-capability-routing-report.md"


class CloneSafeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class CloneSafeDecision(str, Enum):
    READY = "clone_safe_routing_ready"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CloneSafeModelCapabilityRoutingConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_clean_handoff_report: bool = True


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


def read_optional_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return read_json_object(path), None
    except FileNotFoundError:
        return None, f"missing JSON object: {path}"
    except Exception as exc:  # noqa: BLE001
        return None, f"invalid JSON object at {path}: {type(exc).__name__}: {exc}"


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


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "severity": severity, "source": source}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 235"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "milestone_id must be M14"))
    if policy.get("required_routing_policy_path") != "runtime/model_capability_routing.json":
        errors.append(validation_error("policy.required_routing_policy_path", "routing policy path must be runtime/model_capability_routing.json"))
    if policy.get("profile_path_prefix") != "runtime/model_capability_profiles/":
        errors.append(validation_error("policy.profile_path_prefix", "profile path prefix must be runtime/model_capability_profiles/"))
    if not isinstance(policy.get("required_task_policies"), dict):
        errors.append(validation_error("policy.required_task_policies", "required_task_policies must be an object"))
    return errors


def validate_routing_and_profile(policy: dict[str, Any], routing: dict[str, Any], profile: dict[str, Any] | None, profile_path: Path | None) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if routing.get("kind") != "model_capability_routing_policy":
        errors.append(validation_error("routing.kind", "routing policy kind must be model_capability_routing_policy", source="routing"))
    if routing.get("enforcement_mode") != "fail_closed":
        errors.append(validation_error("routing.enforcement_mode", "routing must remain fail_closed", source="routing"))
    default_profile_id = policy.get("required_default_profile_id")
    if routing.get("default_profile_id") != default_profile_id:
        errors.append(validation_error("routing.default_profile_id", f"default profile id must be {default_profile_id}", source="routing"))
    profiles = routing.get("profiles") if isinstance(routing.get("profiles"), list) else []
    active = next((item for item in profiles if isinstance(item, dict) and item.get("profile_id") == default_profile_id), None)
    if not isinstance(active, dict):
        errors.append(validation_error("routing.profile_entry", "routing policy must include the required default profile entry", source="routing"))
        return errors
    raw_path = active.get("profile_path")
    if not isinstance(raw_path, str):
        errors.append(validation_error("routing.profile_path", "profile_path must be a string", source="routing"))
        return errors
    for fragment in policy.get("forbidden_profile_path_fragments", []):
        if isinstance(fragment, str) and fragment in raw_path:
            errors.append(validation_error("routing.profile_path.runtime_state", "profile_path must not reference runtime-state", source="routing"))
    if not raw_path.startswith(str(policy.get("profile_path_prefix"))):
        errors.append(validation_error("routing.profile_path.prefix", "profile_path must use the clone-safe runtime profile directory", source="routing"))
    if profile_path is None or not profile_path.is_file():
        errors.append(validation_error("profile.exists", "clone-safe profile file must exist", source="profile"))
        return errors
    if profile is None:
        errors.append(validation_error("profile.load", "clone-safe profile must be valid JSON", source="profile"))
        return errors
    if profile.get("kind") != "model_capability_profile":
        errors.append(validation_error("profile.kind", "profile kind must be model_capability_profile", source="profile"))
    if profile.get("clone_safe") is not True:
        errors.append(validation_error("profile.clone_safe", "profile must declare clone_safe=true", source="profile"))
    if profile.get("status") == "failed":
        errors.append(validation_error("profile.status", "profile status must not be failed", source="profile"))
    required_task_policies = dict_value(policy.get("required_task_policies"))
    task_policy = dict_value(profile.get("task_policy"))
    for key, expected in required_task_policies.items():
        actual = dict_value(task_policy.get(key)).get("status")
        if actual != expected:
            errors.append(validation_error(f"profile.task_policy.{key}", f"task policy {key} must be {expected}, got {actual}", source="profile"))
    return errors


def validate_clean_handoff(clean_report: dict[str, Any] | None, clean_report_error: str | None, *, require: bool) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if clean_report is None:
        if require:
            errors.append(validation_error("clean_handoff.load", clean_report_error or "clean handoff report is missing", source="clean_handoff"))
        return errors
    if clean_report.get("kind") != "clean_clone_release_handoff_report" or clean_report.get("status") != "passed":
        errors.append(validation_error("clean_handoff.status", "clean handoff report must pass", source="clean_handoff"))
    summary = dict_value(clean_report.get("summary"))
    if summary.get("runtime_seed_count") != 0 or summary.get("failed_runtime_seed_count") != 0:
        errors.append(validation_error("clean_handoff.runtime_seed_count", "clean handoff must pass without runtime-state profile seeding", source="clean_handoff"))
    if summary.get("managed_stack_from_snapshot") is not True:
        errors.append(validation_error("clean_handoff.managed_stack", "managed stack must run from clean snapshot", source="clean_handoff"))
    if summary.get("live_minimal_ran") is not True:
        errors.append(validation_error("clean_handoff.live_minimal", "clean handoff must run live onboarding proof", source="clean_handoff"))
    return errors


def build_clone_safe_model_capability_routing_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None,
    require_clean_handoff_report: bool,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    routing_path = resolve_path(config_root, str(policy.get("required_routing_policy_path") or ""))
    routing, routing_error = read_optional_json_object(routing_path)
    if routing is None:
        routing = {}
        errors.append(validation_error("routing.load", routing_error or "routing policy is missing", source="routing"))
    raw_profile_path = None
    for item in routing.get("profiles", []) if isinstance(routing.get("profiles"), list) else []:
        if isinstance(item, dict) and item.get("profile_id") == policy.get("required_default_profile_id"):
            raw_profile_path = item.get("profile_path")
            break
    profile_path = resolve_path(config_root, raw_profile_path) if isinstance(raw_profile_path, str) else None
    profile, profile_error = read_optional_json_object(profile_path) if profile_path else (None, "profile path missing")
    errors.extend(validate_routing_and_profile(policy, routing, profile, profile_path))
    clean_report_path = resolve_path(config_root, str(policy.get("clean_handoff_report_path") or ""))
    clean_report, clean_error = read_optional_json_object(clean_report_path)
    errors.extend(validate_clean_handoff(clean_report, clean_error, require=require_clean_handoff_report))
    status = CloneSafeStatus.FAILED.value if errors else CloneSafeStatus.PASSED.value
    decision = CloneSafeDecision.READY.value if status == CloneSafeStatus.PASSED.value else CloneSafeDecision.BLOCKED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "routing_policy_path": str(routing_path),
        "profile_path": str(profile_path) if profile_path else None,
        "profile_sha256": sha256_file(profile_path) if profile_path and profile_path.is_file() else None,
        "clean_handoff_report_path": str(clean_report_path),
        "validation_errors": errors,
        "summary": {
            "decision": decision,
            "profile_path": str(profile_path) if profile_path else None,
            "profile_clone_safe": dict_value(profile).get("clone_safe") is True if profile else False,
            "profile_path_uses_runtime_state": "runtime-state" in str(profile_path) if profile_path else True,
            "clean_handoff_required": require_clean_handoff_report,
            "clean_handoff_loaded": clean_report is not None,
            "clean_handoff_runtime_seed_count": dict_value(clean_report.get("summary")).get("runtime_seed_count") if clean_report else None,
            "validation_error_count": len(errors),
            "phase236_ready": not errors,
            "next_action": "work next approved milestone-aligned phase" if not errors else "repair clone-safe routing proof",
        },
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    return stable


def validate_clone_safe_model_capability_routing_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None,
    require_clean_handoff_report: bool,
) -> list[str]:
    expected = build_clone_safe_model_capability_routing_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        require_clean_handoff_report=require_clean_handoff_report,
    )
    return [] if stable_report(report) == stable_report(expected) else ["report must match rebuilt clone-safe routing report"]


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 235 Clone-Safe Model Capability Routing",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Profile path: `{summary.get('profile_path')}`",
        f"- Profile clone-safe: `{summary.get('profile_clone_safe')}`",
        f"- Clean handoff runtime seed count: `{summary.get('clean_handoff_runtime_seed_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        "",
    ]
    if report.get("validation_errors"):
        lines.extend(["## Validation Errors", ""])
        for item in report["validation_errors"]:
            lines.append(f"- `{item.get('id')}`: {item.get('message')}")
        lines.append("")
    return "\n".join(lines)


def run_clone_safe_model_capability_routing(config: CloneSafeModelCapabilityRoutingConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    report = build_clone_safe_model_capability_routing_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        require_clean_handoff_report=config.require_clean_handoff_report,
    )
    report_path = resolve_path(config_root, config.output_path)
    report["report_path"] = str(report_path)
    write_json(report_path, report)
    if config.markdown_output_path:
        write_text(resolve_path(config_root, config.markdown_output_path), markdown_report(report))
    return report
