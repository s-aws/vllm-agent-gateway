"""Phase 199 V1 founder beta release closeout gate."""

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
EXPECTED_POLICY_KIND = "v1_beta_release_closeout_policy"
EXPECTED_REPORT_KIND = "v1_beta_release_closeout_report"
EXPECTED_PHASE = 199
EXPECTED_BACKLOG_ID = "P0-BB-063"
EXPECTED_MILESTONE_ID = "M1"
DEFAULT_POLICY_PATH = Path("runtime") / "v1_beta_release_closeout_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase199" / "phase199-v1-beta-release-closeout-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase199" / "phase199-v1-beta-release-closeout-report.md"

REQUIRED_RELEASE_SCOPE = {
    "local_founder_beta",
    "anythingllm_workflow_router_path",
    "current_localhost_model",
    "two_frozen_coinbase_fixtures",
    "format_a_and_json_output",
    "read_only_l1_l2_chat_quality",
    "draft_only_skill_authoring_packets",
    "structured_founder_feedback_capture",
}
REQUIRED_RELEASE_LIMITATIONS = {
    "not_production_deployment",
    "not_advanced_broad_refactor_orchestration",
    "not_mutation_capable_founder_prompt_pack",
    "not_every_repository_language_or_coding_task",
    "not_direct_mutation_of_protected_fixtures",
    "not_automatic_model_selection",
    "not_unbounded_skill_library_scale",
    "raw_1m_context_not_yet_supported",
}


class V1BetaCloseoutStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class V1BetaCloseoutDecision(str, Enum):
    RELEASE = "release_for_founder_beta"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class V1BetaReleaseCloseoutConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


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


def directory_fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    ignored_dirs = {".git", "__pycache__", ".pytest_cache"}
    for item in sorted(child for child in path.rglob("*") if child.is_file() and not any(part in ignored_dirs for part in child.parts)):
        relative = item.relative_to(path).as_posix()
        data = item.read_bytes()
        digest.update(relative.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\0")
        file_count += 1
        total_bytes += len(data)
    return {"file_count": file_count, "total_bytes": total_bytes, "sha256": digest.hexdigest()}


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


def validation_error(error_id: str, message: str, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 199"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "policy.milestone_id must be M1"))
    if set(string_list(policy.get("allowed_decisions"))) != {item.value for item in V1BetaCloseoutDecision}:
        errors.append(validation_error("policy.allowed_decisions", "allowed decisions must be release_for_founder_beta and blocked"))
    reports = object_list(policy.get("required_reports"))
    report_ids = [str(item.get("id")) for item in reports if isinstance(item.get("id"), str)]
    if set(report_ids) != {
        "release_candidate_founder_trial_pack",
        "v1_product_readiness_reassessment",
        "v1_product_readiness_live_proof",
        "founder_trial_execution_round",
        "founder_feedback_intake_repair",
    }:
        errors.append(validation_error("policy.required_reports", "policy.required_reports must match the Phase 195-198 proof chain"))
    if len(report_ids) != len(set(report_ids)):
        errors.append(validation_error("policy.required_reports.duplicates", "required report IDs must be unique"))
    for index, item in enumerate(reports):
        prefix = f"policy.required_reports[{index}]"
        for key in ("id", "path", "expected_kind", "expected_status"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(validation_error(f"{prefix}.{key}", f"{key} must be a non-empty string"))
        if not isinstance(item.get("expected_phase"), int):
            errors.append(validation_error(f"{prefix}.expected_phase", "expected_phase must be an integer"))
    if set(string_list(policy.get("release_scope"))) != REQUIRED_RELEASE_SCOPE:
        errors.append(validation_error("policy.release_scope", "release scope must match M1 V1 founder beta scope"))
    if set(string_list(policy.get("release_limitations"))) != REQUIRED_RELEASE_LIMITATIONS:
        errors.append(validation_error("policy.release_limitations", "release limitations must match M1 V1 founder beta limitations"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if not isinstance(policy.get("required_doc_markers"), dict):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers must be an object"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "both frozen Coinbase fixtures are required"))
    anythingllm = dict_value(policy.get("required_anythingllm"))
    if anythingllm.get("workflow_router_base_url") != "http://127.0.0.1:8500/v1":
        errors.append(validation_error("policy.required_anythingllm.workflow_router_base_url", "AnythingLLM must target the workflow-router gateway"))
    if anythingllm.get("api_base_url") != "http://127.0.0.1:3001":
        errors.append(validation_error("policy.required_anythingllm.api_base_url", "AnythingLLM API URL must match the governed local setup"))
    if policy.get("acceptance_marker") != "PHASE199 V1 BETA RELEASE CLOSEOUT PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 199"))
    return errors


def load_sources(config_root: Path, policy: dict[str, Any], *, require_artifacts: bool) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[dict[str, str]]]:
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    for item in object_list(policy.get("required_reports")):
        report_id = str(item.get("id"))
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            sources[report_id] = (None, {})
            errors.append(validation_error(f"{report_id}.path", "required report path is invalid", source=report_id))
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            sources[report_id] = (path, {})
            if require_artifacts:
                errors.append(validation_error(f"{report_id}.missing", f"required report is missing: {raw_path}", source=report_id))
            continue
        try:
            sources[report_id] = (path, read_json_object(path))
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            sources[report_id] = (path, {})
            errors.append(validation_error(f"{report_id}.malformed", f"required report is malformed: {type(exc).__name__}: {exc}", source=report_id))
    return sources, errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path is not None else None,
        "exists": path.is_file() if path is not None else False,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "recommendation": payload.get("recommendation"),
        "quality_status": payload.get("quality_status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def report_policy_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in object_list(policy.get("required_reports"))
        if isinstance(item.get("id"), str)
    }


def validate_required_reports(policy: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for report_id, spec in report_policy_by_id(policy).items():
        path, payload = sources.get(report_id, (None, {}))
        prefix = f"reports.{report_id}"
        if path is None or not path.is_file():
            errors.append(validation_error(f"{prefix}.missing", "required report is missing", source=report_id))
            continue
        if payload.get("kind") != spec.get("expected_kind"):
            errors.append(validation_error(f"{prefix}.kind", f"kind must be {spec.get('expected_kind')}", source=report_id))
        if payload.get("status") != spec.get("expected_status"):
            errors.append(validation_error(f"{prefix}.status", f"status must be {spec.get('expected_status')}", source=report_id))
        if payload.get("phase") != spec.get("expected_phase"):
            errors.append(validation_error(f"{prefix}.phase", f"phase must be {spec.get('expected_phase')}", source=report_id))
        expected_recommendation = spec.get("expected_recommendation")
        if isinstance(expected_recommendation, str) and payload.get("recommendation") != expected_recommendation:
            errors.append(validation_error(f"{prefix}.recommendation", f"recommendation must be {expected_recommendation}", source=report_id))
        if object_list(payload.get("validation_errors")):
            errors.append(validation_error(f"{prefix}.validation_errors", "validation_errors must be empty", source=report_id))
        summary = dict_value(payload.get("summary"))
        if summary.get("validation_error_count") not in (None, 0):
            errors.append(validation_error(f"{prefix}.validation_error_count", "validation_error_count must be 0", source=report_id))
    return errors


def validate_closeout_semantics(sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    _, phase197 = sources.get("founder_trial_execution_round", (None, {}))
    phase197_summary = dict_value(phase197.get("summary"))
    phase197_counts = dict_value(phase197_summary.get("classification_counts"))
    if phase197_counts.get("blocker") not in (None, 0):
        errors.append(validation_error("phase197.blockers", "Phase 197 must have zero blocker classifications", "critical", "phase197"))
    if phase197.get("quality_status") not in {"passed", "advisory"}:
        errors.append(validation_error("phase197.quality_status", "Phase 197 quality status must be passed or advisory", source="phase197"))
    _, phase198 = sources.get("founder_feedback_intake_repair", (None, {}))
    phase198_summary = dict_value(phase198.get("summary"))
    if phase198_summary.get("phase199_blocked") is True:
        errors.append(validation_error("phase198.phase199_blocked", "Phase 198 blocks Phase 199 closeout", "critical", "phase198"))
    if phase198_summary.get("phase199_ready_after_intake") is not True:
        errors.append(validation_error("phase198.phase199_ready_after_intake", "Phase 198 must report phase199_ready_after_intake=true", source="phase198"))
    if phase198_summary.get("release_blocker_count") not in (None, 0):
        errors.append(validation_error("phase198.release_blocker_count", "Phase 198 release blocker count must be 0", "critical", "phase198"))
    if phase198_summary.get("open_required_repair_count") not in (None, 0):
        errors.append(validation_error("phase198.open_required_repair_count", "Phase 198 open required repair count must be 0", "critical", "phase198"))
    _, live = sources.get("v1_product_readiness_live_proof", (None, {}))
    live_summary = dict_value(live.get("summary"))
    if live_summary.get("error_count") not in (None, 0):
        errors.append(validation_error("live_proof.error_count", "live proof error_count must be 0", source="live_proof"))
    if live_summary.get("fixture_integrity") not in (None, "passed"):
        errors.append(validation_error("live_proof.fixture_integrity", "live proof fixture_integrity must pass", source="live_proof"))
    return errors


def validate_docs(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    marker_policy = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        markers = string_list(marker_policy.get(raw_path))
        missing_markers: list[str] = []
        if exists:
            text = path.read_text(encoding="utf-8", errors="replace")
            missing_markers = [marker for marker in markers if marker not in text]
        elif markers:
            missing_markers = markers
        docs.append(
            {
                "path": raw_path,
                "exists": exists,
                "sha256": artifact_hash(path),
                "required_markers": markers,
                "missing_markers": missing_markers,
            }
        )
        if not exists:
            errors.append(validation_error(f"docs.{raw_path}.missing", f"required doc is missing: {raw_path}", "medium", "documentation"))
        if missing_markers:
            errors.append(validation_error(f"docs.{raw_path}.markers", f"required doc markers missing: {', '.join(missing_markers)}", "high", "documentation"))
    return docs, errors


def git_status(path: Path) -> tuple[str | None, str | None]:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--short"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip()
    return result.stdout.strip(), None


def fixture_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_root in string_list(policy.get("required_target_roots")):
        root = Path(raw_root)
        exists = root.exists()
        record: dict[str, Any] = {"root": raw_root, "exists": exists}
        if not exists:
            errors.append(validation_error(f"fixtures.{raw_root}.missing", f"fixture root is missing: {raw_root}", "critical", "fixtures"))
            records.append(record)
            continue
        if (root / ".git").is_dir():
            status, status_error = git_status(root)
            record["git_status"] = status
            record["git_status_error"] = status_error
            record["clean"] = status == "" and status_error is None
            if record["clean"] is not True:
                errors.append(validation_error(f"fixtures.{raw_root}.dirty", "git fixture must be clean", "critical", "fixtures"))
        else:
            record["fingerprint"] = directory_fingerprint(root)
            record["clean"] = True
        records.append(record)
    return records, errors


def build_v1_beta_release_closeout_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(source_load_errors)
    errors.extend(validate_required_reports(policy, sources))
    errors.extend(validate_closeout_semantics(sources))
    docs, doc_errors = validate_docs(config_root, policy)
    errors.extend(doc_errors)
    fixtures, fixture_errors = fixture_records(policy)
    errors.extend(fixture_errors)
    source_refs = {source_id: source_ref(path, payload) for source_id, (path, payload) in sources.items()}
    decision = V1BetaCloseoutDecision.BLOCKED.value if errors else V1BetaCloseoutDecision.RELEASE.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": V1BetaCloseoutStatus.FAILED.value if errors else V1BetaCloseoutStatus.PASSED.value,
        "decision": decision,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": source_refs,
        "docs": docs,
        "fixtures": fixtures,
        "release_scope": string_list(policy.get("release_scope")),
        "release_limitations": string_list(policy.get("release_limitations")),
        "next_milestone_phase_candidates": string_list(policy.get("next_milestone_phase_candidates")),
        "validation_errors": errors,
        "summary": {
            "required_report_count": len(source_refs),
            "doc_count": len(docs),
            "fixture_count": len(fixtures),
            "phase199_blocked": bool(errors),
            "validation_error_count": len(errors),
            "decision": decision,
            "next_action": "work Phase 200 Chat-Visible Answer Contract Inventory"
            if not errors
            else "repair closeout blockers before Phase 200",
        },
    }


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "milestone_id",
            "status",
            "decision",
            "policy_path",
            "policy_sha256",
            "source_refs",
            "docs",
            "fixtures",
            "release_scope",
            "release_limitations",
            "next_milestone_phase_candidates",
            "validation_errors",
            "summary",
        )
    }


def validate_v1_beta_release_closeout_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_v1_beta_release_closeout_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt V1 beta release closeout report"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 199 V1 Beta Release Closeout",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Milestone: `{report.get('milestone_id')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Required Reports",
        "",
        "| Source | Phase | Status | Kind |",
        "| --- | --- | --- | --- |",
    ]
    for source_id, ref in sorted(dict_value(report.get("source_refs")).items()):
        lines.append(f"| `{source_id}` | `{ref.get('phase')}` | `{ref.get('status')}` | `{ref.get('kind')}` |")
    lines.extend(["", "## Fixtures", "", "| Root | Exists | Clean |", "| --- | --- | --- |"])
    for item in object_list(report.get("fixtures")):
        lines.append(f"| `{item.get('root')}` | `{item.get('exists')}` | `{item.get('clean')}` |")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def run_v1_beta_release_closeout(config: V1BetaReleaseCloseoutConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, source_load_errors = load_sources(config_root, policy, require_artifacts=config.require_artifacts)
    report = build_v1_beta_release_closeout_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_v1_beta_release_closeout_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = V1BetaCloseoutStatus.FAILED.value
        report["decision"] = V1BetaCloseoutDecision.BLOCKED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "v1_beta_release_closeout")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["phase199_blocked"] = True
        report["summary"]["decision"] = V1BetaCloseoutDecision.BLOCKED.value
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if config.markdown_output_path is not None:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_text(markdown_path, render_markdown(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        write_text(resolve_path(config_root, config.markdown_output_path), render_markdown(report))
    return report
