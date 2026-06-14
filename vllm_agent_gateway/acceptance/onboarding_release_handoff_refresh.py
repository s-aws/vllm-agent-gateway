"""Phase 232 onboarding and release handoff refresh gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "onboarding_release_handoff_refresh_policy"
EXPECTED_REPORT_KIND = "onboarding_release_handoff_refresh_report"
EXPECTED_PHASE = 232
EXPECTED_BACKLOG_ID = "P0-M14-232"
EXPECTED_MILESTONE_ID = "M14"
DEFAULT_POLICY_PATH = Path("runtime") / "onboarding_release_handoff_refresh_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase232" / "phase232-onboarding-release-handoff-refresh-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase232" / "phase232-onboarding-release-handoff-refresh-report.md"


class OnboardingReleaseHandoffStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class OnboardingReleaseHandoffDecision(str, Enum):
    HANDOFF_READY = "handoff_ready"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class OnboardingReleaseHandoffConfig:
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


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 232"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "milestone_id must be M14"))
    if policy.get("required_decision") != OnboardingReleaseHandoffDecision.HANDOFF_READY.value:
        errors.append(validation_error("policy.required_decision", "required_decision must be handoff_ready"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required_docs must be a non-empty list"))
    if not isinstance(policy.get("required_doc_markers"), dict):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers must be an object"))
    if not isinstance(policy.get("forbidden_doc_markers"), dict):
        errors.append(validation_error("policy.forbidden_doc_markers", "forbidden_doc_markers must be an object"))
    if not string_list(policy.get("required_commands")):
        errors.append(validation_error("policy.required_commands", "required_commands must be a non-empty list"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "both frozen Coinbase fixtures are required"))
    anythingllm = dict_value(policy.get("required_anythingllm"))
    if anythingllm.get("workflow_router_base_url") != "http://127.0.0.1:8500/v1":
        errors.append(validation_error("policy.required_anythingllm.workflow_router_base_url", "AnythingLLM must target 8500/v1"))
    if anythingllm.get("api_base_url") != "http://127.0.0.1:3001":
        errors.append(validation_error("policy.required_anythingllm.api_base_url", "AnythingLLM API base URL must be 3001"))
    if anythingllm.get("workspace") != "my-workspace":
        errors.append(validation_error("policy.required_anythingllm.workspace", "workspace must be my-workspace"))
    if policy.get("acceptance_marker") != "PHASE232 ONBOARDING RELEASE HANDOFF REFRESH PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 232"))
    return errors


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    forbidden_markers = dict_value(policy.get("forbidden_doc_markers"))
    for doc in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, doc)
        record: dict[str, Any] = {
            "path": doc,
            "exists": path.is_file(),
            "sha256": artifact_hash(path),
            "missing_required_markers": [],
            "present_forbidden_markers": [],
        }
        if not path.is_file():
            errors.append(validation_error(f"docs.{doc}.missing", f"required doc is missing: {doc}", source=doc))
            records.append(record)
            continue
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in string_list(required_markers.get(doc)) if marker not in text]
        forbidden = [marker for marker in string_list(forbidden_markers.get(doc)) if marker in text]
        record["missing_required_markers"] = missing
        record["present_forbidden_markers"] = forbidden
        if missing:
            errors.append(
                validation_error(
                    f"docs.{doc}.required_markers",
                    "missing marker(s): " + ", ".join(missing),
                    source=doc,
                )
            )
        if forbidden:
            errors.append(
                validation_error(
                    f"docs.{doc}.forbidden_markers",
                    "forbidden stale marker(s): " + ", ".join(forbidden),
                    source=doc,
                )
            )
        records.append(record)
    return records, errors


def command_records(config_root: Path, policy: dict[str, Any], docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    combined_text_parts: list[str] = []
    for record in docs:
        path_value = record.get("path")
        if isinstance(path_value, str):
            path = resolve_path(config_root, path_value)
            if path.is_file():
                combined_text_parts.append(path.read_text(encoding="utf-8"))
    combined_text = "\n".join(combined_text_parts)
    records: list[dict[str, Any]] = []
    for command in string_list(policy.get("required_commands")):
        present = command in combined_text
        records.append({"command": command, "documented": present})
        if not present:
            errors.append(validation_error(f"commands.{command}.missing", f"required command is not documented: {command}", source="commands"))
    return records, errors


def build_onboarding_release_handoff_refresh_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    commands, command_errors = command_records(config_root, policy, docs)
    errors.extend(command_errors)
    status = OnboardingReleaseHandoffStatus.FAILED.value if errors else OnboardingReleaseHandoffStatus.PASSED.value
    decision = (
        OnboardingReleaseHandoffDecision.HANDOFF_READY.value
        if status == OnboardingReleaseHandoffStatus.PASSED.value
        else OnboardingReleaseHandoffDecision.BLOCKED.value
    )
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
        "policy_sha256": artifact_hash(policy_path),
        "docs": docs,
        "commands": commands,
        "required_anythingllm": dict_value(policy.get("required_anythingllm")),
        "required_target_roots": string_list(policy.get("required_target_roots")),
        "validation_errors": errors,
        "summary": {
            "decision": decision,
            "doc_count": len(docs),
            "missing_doc_count": sum(1 for item in docs if item.get("exists") is not True),
            "docs_with_missing_marker_count": sum(1 for item in docs if item.get("missing_required_markers")),
            "docs_with_forbidden_marker_count": sum(1 for item in docs if item.get("present_forbidden_markers")),
            "required_command_count": len(commands),
            "missing_command_count": sum(1 for item in commands if item.get("documented") is not True),
            "validation_error_count": len(errors),
            "phase233_ready": not errors,
            "next_action": "work next approved milestone-aligned phase" if not errors else "repair onboarding and release handoff docs",
        },
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    return stable


def validate_onboarding_release_handoff_refresh_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_onboarding_release_handoff_refresh_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
    )
    if stable_report(report) != stable_report(expected):
        return ["report must match rebuilt onboarding release handoff refresh report"]
    return []


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 232 Onboarding Release Handoff Refresh",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Document count: `{summary.get('doc_count')}`",
        f"- Missing docs: `{summary.get('missing_doc_count')}`",
        f"- Docs with missing markers: `{summary.get('docs_with_missing_marker_count')}`",
        f"- Docs with forbidden markers: `{summary.get('docs_with_forbidden_marker_count')}`",
        f"- Missing commands: `{summary.get('missing_command_count')}`",
        "",
        "## Documents",
    ]
    for item in report.get("docs", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('path')}` exists=`{item.get('exists')}` "
            f"missing_markers=`{len(string_list(item.get('missing_required_markers')))}`"
        )
    if report.get("validation_errors"):
        lines.extend(["", "## Validation Errors"])
        for error in report["validation_errors"]:
            lines.append(f"- `{error.get('id')}` {error.get('message')}")
    return "\n".join(lines) + "\n"


def run_onboarding_release_handoff_refresh(config: OnboardingReleaseHandoffConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path) if config.markdown_output_path else None
    policy = read_json_object(policy_path)
    report = build_onboarding_release_handoff_refresh_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
    )
    validation_errors = validate_onboarding_release_handoff_refresh_report(
        report,
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = OnboardingReleaseHandoffStatus.FAILED.value
        report["decision"] = OnboardingReleaseHandoffDecision.BLOCKED.value
        report["validation_errors"].extend(validation_error("report.rebuild", item) for item in validation_errors)
        report["summary"]["decision"] = report["decision"]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase233_ready"] = False
        report["summary"]["next_action"] = "repair onboarding and release handoff docs"
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if markdown_output_path:
        write_text(markdown_output_path, render_markdown_report(report))
    return report
