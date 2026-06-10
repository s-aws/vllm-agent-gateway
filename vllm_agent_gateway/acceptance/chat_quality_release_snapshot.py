"""Chat-quality release-candidate snapshot manifest."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chat_quality_release_snapshot_policy"
EXPECTED_REPORT_KIND = "chat_quality_release_snapshot"
EXPECTED_PHASE = 136
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_quality_release_snapshot_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "chat-quality-release-snapshot" / "phase136"


class ChatQualityReleaseSnapshotStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ChatQualityReleaseSnapshotConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"chat-quality-release-snapshot-{utc_timestamp()}.json"


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


def git_status_short(config_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(config_root), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 136")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    artifact_ids = [item.get("id") for item in object_list(policy.get("required_artifacts"))]
    for expected_id in (
        "stable_chat_quality_release",
        "stable_release_blocker_closure",
        "anythingllm_founder_smoke",
        "founder_smoke_feedback",
    ):
        if expected_id not in artifact_ids:
            errors.append(f"policy.required_artifacts missing {expected_id}")
    if not string_list(policy.get("required_docs")):
        errors.append("policy.required_docs must be a non-empty string array")
    return errors


def artifact_record(config_root: Path, item: dict[str, Any]) -> dict[str, Any]:
    path_value = item.get("path")
    path = resolve_path(config_root, str(path_value)) if isinstance(path_value, str) else Path()
    payload = read_json_object(path) if path.is_file() else {}
    return {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "path": str(path),
        "exists": path.is_file(),
        "sha256": artifact_hash(path),
        "status": payload.get("status"),
        "readiness": payload.get("readiness"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def doc_record(config_root: Path, path_value: str) -> dict[str, Any]:
    path = resolve_path(config_root, path_value)
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": artifact_hash(path),
    }


def build_snapshot_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    artifacts = [artifact_record(config_root, item) for item in object_list(policy.get("required_artifacts"))]
    docs = [doc_record(config_root, path) for path in string_list(policy.get("required_docs"))]
    artifact_by_id = {str(item.get("id")): item for item in artifacts}
    errors = validate_policy(policy)
    for item in artifacts:
        if item.get("exists") is not True:
            errors.append(f"required artifact missing: {item.get('id')}")
        if item.get("kind") and item.get("status") != "passed":
            errors.append(f"required artifact not passed: {item.get('id')}")
    stable = artifact_by_id.get("stable_chat_quality_release", {})
    if stable.get("readiness") != "ready_for_founder_testing":
        errors.append("stable_chat_quality_release.readiness must be ready_for_founder_testing")
    smoke = artifact_by_id.get("anythingllm_founder_smoke", {})
    smoke_summary = dict_value(smoke.get("summary"))
    if smoke_summary.get("failed") != 0:
        errors.append("anythingllm_founder_smoke.summary.failed must be 0")
    feedback = artifact_by_id.get("founder_smoke_feedback", {})
    feedback_summary = dict_value(feedback.get("summary"))
    if feedback_summary.get("actionable_feedback_count") != 0:
        errors.append("founder_smoke_feedback.summary.actionable_feedback_count must be 0")
    for item in docs:
        if item.get("exists") is not True:
            errors.append(f"required doc missing: {item.get('path')}")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ChatQualityReleaseSnapshotStatus.PASSED.value if not errors else ChatQualityReleaseSnapshotStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "artifacts": artifacts,
        "docs": docs,
        "git_status_short": git_status_short(config_root),
        "summary": {
            "artifact_count": len(artifacts),
            "doc_count": len(docs),
            "missing_artifact_count": sum(1 for item in artifacts if item.get("exists") is not True),
            "missing_doc_count": sum(1 for item in docs if item.get("exists") is not True),
            "release_readiness": stable.get("readiness"),
            "founder_smoke_failed": smoke_summary.get("failed"),
            "actionable_feedback_count": feedback_summary.get("actionable_feedback_count"),
        },
        "errors": errors,
    }


def validate_snapshot_report(report: dict[str, Any], *, config_root: Path, policy: dict[str, Any], policy_path: Path | None = None) -> list[str]:
    expected = build_snapshot_report(config_root=config_root, policy=policy, policy_path=policy_path)
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "policy_path",
        "policy_sha256",
        "artifacts",
        "docs",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt release snapshot")
    return errors


def run_snapshot_gate(config: ChatQualityReleaseSnapshotConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    report = build_snapshot_report(config_root=config_root, policy=policy, policy_path=policy_path)
    errors = []
    if config.require_artifacts and not policy_path.is_file():
        errors.append(f"required artifact is missing: {policy_path}")
    errors.extend(validate_snapshot_report(report, config_root=config_root, policy=policy, policy_path=policy_path))
    if errors:
        report["status"] = ChatQualityReleaseSnapshotStatus.FAILED.value
        report["errors"] = report["errors"] + errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
