"""Deterministic chat transcript quality classifier for Priority 0 founder testing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "priority0_chat_transcript_quality_policy"
EXPECTED_REPORT_KIND = "chat_transcript_quality_report"
EXPECTED_SOURCE_REPORT_KIND = "founder_field_prompt_evaluation"
EXPECTED_PHASE = 138
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_transcript_quality_policy.json"
DEFAULT_TRANSCRIPT_REPORT_PATH = Path("runtime-state") / "founder-field-tests" / "phase134-founder-smoke.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "chat-transcript-quality" / "phase138"


class ChatTranscriptGateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ChatTranscriptQualityStatus(str, Enum):
    PASS = "pass"
    ADVISORY = "advisory"
    BLOCKER = "blocker"


class TranscriptFindingSeverity(str, Enum):
    ADVISORY = "advisory"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class ChatTranscriptQualityConfig:
    config_root: Path
    transcript_report_path: Path = DEFAULT_TRANSCRIPT_REPORT_PATH
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"chat-transcript-quality-{utc_timestamp()}.json"


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


def contains_marker(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def marker_index(text: str, marker: str) -> int:
    return text.lower().find(marker.lower())


def non_empty_line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def transcript_text(case: dict[str, Any]) -> str:
    for key in ("text", "assistant_text", "response_text", "text_sample"):
        value = case.get(key)
        if isinstance(value, str) and value.strip():
            return value
    body = case.get("body")
    if isinstance(body, dict):
        for key in ("textResponse", "response", "message", "text"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def finding(severity: TranscriptFindingSeverity, code: str, message: str) -> dict[str, str]:
    return {"severity": severity.value, "code": code, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 138")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    minimum_transcript_chars = policy.get("minimum_transcript_chars")
    if not isinstance(minimum_transcript_chars, int) or minimum_transcript_chars < 200:
        errors.append("policy.minimum_transcript_chars must be at least 200")
    minimum_non_empty_lines = policy.get("minimum_non_empty_lines")
    if not isinstance(minimum_non_empty_lines, int) or minimum_non_empty_lines < 5:
        errors.append("policy.minimum_non_empty_lines must be at least 5")
    minimum_pre_artifact = policy.get("minimum_pre_artifact_non_empty_lines")
    if not isinstance(minimum_pre_artifact, int) or minimum_pre_artifact < 3:
        errors.append("policy.minimum_pre_artifact_non_empty_lines must be at least 3")
    if not string_list(policy.get("required_markers")):
        errors.append("policy.required_markers is required")
    if not string_list(policy.get("workflow_marker_templates")):
        errors.append("policy.workflow_marker_templates is required")
    evidence_groups = object_list(policy.get("evidence_marker_groups"))
    if not evidence_groups:
        errors.append("policy.evidence_marker_groups is required")
    for group in evidence_groups:
        name = group.get("group")
        if not isinstance(name, str) or not name.strip():
            errors.append("policy.evidence_marker_groups[].group is required")
        if not string_list(group.get("markers")):
            errors.append(f"policy.evidence_marker_groups[{name or '<missing>'}].markers is required")
    if not isinstance(policy.get("artifact_section_marker"), str) or not policy["artifact_section_marker"].strip():
        errors.append("policy.artifact_section_marker is required")
    if not string_list(policy.get("unsafe_mutation_markers")):
        errors.append("policy.unsafe_mutation_markers is required")
    return errors


def workflow_marker_present(text: str, expected_workflow: str, policy: dict[str, Any]) -> bool:
    for template in string_list(policy.get("workflow_marker_templates")):
        marker = template.replace("{expected_workflow}", expected_workflow)
        if contains_marker(text, marker):
            return True
    return False


def classify_case(case: dict[str, Any], *, policy: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "<missing>")
    expected_workflow = str(case.get("expected_workflow") or "")
    run_id = str(case.get("run_id") or "")
    text = transcript_text(case)
    findings: list[dict[str, str]] = []

    http_status = case.get("http_status")
    if http_status != 200:
        findings.append(
            finding(
                TranscriptFindingSeverity.BLOCKER,
                "http_status_not_ok",
                f"AnythingLLM transcript HTTP status must be 200; got {http_status}.",
            )
        )
    if case.get("status") not in (None, "passed"):
        findings.append(
            finding(
                TranscriptFindingSeverity.BLOCKER,
                "source_case_failed",
                "Source founder prompt case is already failed and cannot pass transcript quality.",
            )
        )
    if not text:
        findings.append(
            finding(TranscriptFindingSeverity.BLOCKER, "missing_transcript_text", "Assistant transcript text is required.")
        )
    else:
        minimum_chars = int(policy.get("minimum_transcript_chars", 0))
        if len(text) < minimum_chars:
            findings.append(
                finding(
                    TranscriptFindingSeverity.BLOCKER,
                    "transcript_too_short",
                    f"Transcript has {len(text)} characters; expected at least {minimum_chars}.",
                )
            )
        minimum_lines = int(policy.get("minimum_non_empty_lines", 0))
        line_count = non_empty_line_count(text)
        if line_count < minimum_lines:
            findings.append(
                finding(
                    TranscriptFindingSeverity.BLOCKER,
                    "transcript_too_few_lines",
                    f"Transcript has {line_count} non-empty lines; expected at least {minimum_lines}.",
                )
            )
        if not run_id or run_id == "unknown":
            findings.append(
                finding(TranscriptFindingSeverity.BLOCKER, "missing_run_id", "Transcript case must include a known run ID.")
            )
        elif run_id not in text:
            findings.append(
                finding(
                    TranscriptFindingSeverity.BLOCKER,
                    "run_id_not_visible",
                    "Run ID must be visible in the chat transcript for traceability.",
                )
            )
        for marker in string_list(policy.get("required_markers")):
            if not contains_marker(text, marker):
                findings.append(
                    finding(
                        TranscriptFindingSeverity.BLOCKER,
                        "missing_required_section",
                        f"Transcript is missing required section marker {marker}.",
                    )
                )
        for group in object_list(policy.get("evidence_marker_groups")):
            markers = string_list(group.get("markers"))
            if markers and not any(contains_marker(text, marker) for marker in markers):
                findings.append(
                    finding(
                        TranscriptFindingSeverity.BLOCKER,
                        "missing_evidence_section",
                        f"Transcript is missing evidence marker group {group.get('group')}.",
                    )
                )
        if expected_workflow and not workflow_marker_present(text, expected_workflow, policy):
            findings.append(
                finding(
                    TranscriptFindingSeverity.BLOCKER,
                    "route_workflow_mismatch",
                    f"Transcript does not show the expected workflow {expected_workflow}.",
                )
            )
        artifact_marker = str(policy.get("artifact_section_marker", "Artifacts:"))
        artifact_index = marker_index(text, artifact_marker)
        if artifact_index >= 0:
            answer_indexes = [
                index
                for marker in ["Result:", "Answer:", "Summary:", "Skill Selection:"]
                for index in [marker_index(text, marker)]
                if index >= 0
            ]
            if not answer_indexes or artifact_index < min(answer_indexes):
                findings.append(
                    finding(
                        TranscriptFindingSeverity.BLOCKER,
                        "artifact_only_or_artifact_first",
                        "Artifact links appear before any chat-visible answer section.",
                    )
                )
            elif non_empty_line_count(text[:artifact_index]) < int(policy.get("minimum_pre_artifact_non_empty_lines", 0)):
                findings.append(
                    finding(
                        TranscriptFindingSeverity.BLOCKER,
                        "insufficient_answer_before_artifacts",
                        "Transcript has too little answer content before artifact links.",
                    )
                )
        unsafe = [marker for marker in string_list(policy.get("unsafe_mutation_markers")) if contains_marker(text, marker)]
        if unsafe:
            findings.append(
                finding(
                    TranscriptFindingSeverity.BLOCKER,
                    "unsafe_mutation_claim",
                    "Read-only transcript includes unsafe mutation claim(s): " + ", ".join(sorted(unsafe)),
                )
            )
    blocker_count = sum(1 for item in findings if item["severity"] == TranscriptFindingSeverity.BLOCKER.value)
    advisory_count = sum(1 for item in findings if item["severity"] == TranscriptFindingSeverity.ADVISORY.value)
    if blocker_count:
        quality_status = ChatTranscriptQualityStatus.BLOCKER.value
    elif advisory_count:
        quality_status = ChatTranscriptQualityStatus.ADVISORY.value
    else:
        quality_status = ChatTranscriptQualityStatus.PASS.value
    return {
        "case_id": case_id,
        "quality_status": quality_status,
        "expected_workflow": expected_workflow,
        "run_id": run_id,
        "http_status": http_status,
        "source_case_status": case.get("status"),
        "text_sha256": case.get("text_sha256") or hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
        "text_chars_checked": len(text),
        "non_empty_lines_checked": non_empty_line_count(text),
        "finding_count": len(findings),
        "blocker_count": blocker_count,
        "advisory_count": advisory_count,
        "findings": findings,
    }


def build_chat_transcript_quality_report(
    *,
    transcript_report: dict[str, Any],
    policy: dict[str, Any],
    transcript_report_path: Path | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    if transcript_report.get("kind") != EXPECTED_SOURCE_REPORT_KIND:
        errors.append(f"transcript_report.kind must be {EXPECTED_SOURCE_REPORT_KIND}")
    cases = object_list(transcript_report.get("cases"))
    classified_cases = [classify_case(case, policy=policy) for case in cases] if not validate_policy(policy) else []
    blocker_count = sum(int(case["blocker_count"]) for case in classified_cases)
    advisory_count = sum(int(case["advisory_count"]) for case in classified_cases)
    case_blocker_count = sum(1 for case in classified_cases if case["quality_status"] == ChatTranscriptQualityStatus.BLOCKER.value)
    case_advisory_count = sum(1 for case in classified_cases if case["quality_status"] == ChatTranscriptQualityStatus.ADVISORY.value)
    if errors:
        quality_status = ChatTranscriptQualityStatus.BLOCKER.value
    elif blocker_count:
        quality_status = ChatTranscriptQualityStatus.BLOCKER.value
    elif advisory_count:
        quality_status = ChatTranscriptQualityStatus.ADVISORY.value
    else:
        quality_status = ChatTranscriptQualityStatus.PASS.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ChatTranscriptGateStatus.PASSED.value
        if quality_status != ChatTranscriptQualityStatus.BLOCKER.value and not errors
        else ChatTranscriptGateStatus.FAILED.value,
        "quality_status": quality_status,
        "generated_at": utc_timestamp(),
        "transcript_report_path": str(transcript_report_path or DEFAULT_TRANSCRIPT_REPORT_PATH),
        "transcript_report_sha256": artifact_hash(transcript_report_path) if transcript_report_path else None,
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "source_report_status": transcript_report.get("status"),
        "source_report_summary": transcript_report.get("summary"),
        "cases": classified_cases,
        "summary": {
            "case_count": len(classified_cases),
            "pass_case_count": sum(1 for case in classified_cases if case["quality_status"] == "pass"),
            "advisory_case_count": case_advisory_count,
            "blocker_case_count": case_blocker_count,
            "finding_count": sum(int(case["finding_count"]) for case in classified_cases),
            "advisory_finding_count": advisory_count,
            "blocker_finding_count": blocker_count,
        },
        "errors": errors,
    }


def validate_chat_transcript_quality_report(
    report: dict[str, Any],
    *,
    transcript_report: dict[str, Any],
    policy: dict[str, Any],
    transcript_report_path: Path | None = None,
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_chat_transcript_quality_report(
        transcript_report=transcript_report,
        policy=policy,
        transcript_report_path=transcript_report_path,
        policy_path=policy_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "quality_status",
        "transcript_report_path",
        "transcript_report_sha256",
        "policy_path",
        "policy_sha256",
        "source_report_status",
        "source_report_summary",
        "cases",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt chat transcript quality report")
    return errors


def run_chat_transcript_quality_gate(config: ChatTranscriptQualityConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    transcript_path = resolve_path(config_root, config.transcript_report_path)
    policy_path = resolve_path(config_root, config.policy_path)
    missing_errors = []
    for label, path in (("transcript report", transcript_path), ("policy", policy_path)):
        if config.require_artifacts and not path.is_file():
            missing_errors.append(f"required {label} artifact is missing: {path}")
    transcript_report = read_json_object(transcript_path) if transcript_path.is_file() else {}
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    report = build_chat_transcript_quality_report(
        transcript_report=transcript_report,
        policy=policy,
        transcript_report_path=transcript_path,
        policy_path=policy_path,
    )
    validation_errors = validate_chat_transcript_quality_report(
        report,
        transcript_report=transcript_report,
        policy=policy,
        transcript_report_path=transcript_path,
        policy_path=policy_path,
    )
    if missing_errors or validation_errors:
        report["status"] = ChatTranscriptGateStatus.FAILED.value
        report["quality_status"] = ChatTranscriptQualityStatus.BLOCKER.value
        report["errors"] = missing_errors + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
