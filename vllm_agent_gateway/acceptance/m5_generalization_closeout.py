"""Phase 213 M5 multi-repo generalization closeout gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "m5_generalization_closeout_policy"
EXPECTED_REPORT_KIND = "m5_generalization_closeout_report"
EXPECTED_PHASE = 213
EXPECTED_BACKLOG_ID = "P0-M5-213"
EXPECTED_MILESTONE_ID = "M5"
DEFAULT_POLICY_PATH = Path("runtime") / "m5_generalization_closeout_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase213" / "phase213-m5-generalization-closeout-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase213" / "phase213-m5-generalization-closeout-report.md"


@dataclass(frozen=True)
class M5GeneralizationCloseoutConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
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


def error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(error("policy.phase", "policy.phase must be 213"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(error("policy.milestone_id", "policy.milestone_id must be M5"))
    if set(string_list(policy.get("allowed_decisions"))) != {"close_m5_move_to_m6", "repeat_m5_repair_cycle", "blocked"}:
        errors.append(error("policy.allowed_decisions", "allowed decisions must match the M5 closeout decision set"))
    report_ids = [str(item.get("id")) for item in object_list(policy.get("required_reports"))]
    if set(report_ids) != {
        "phase209_fixture_baseline_pack",
        "phase211_repair_live_proof",
        "phase212_live_generalization_rerun",
    }:
        errors.append(error("policy.required_reports", "required reports must cover Phase 209, Phase 211 repair proof, and Phase 212 live rerun"))
    if len(report_ids) != len(set(report_ids)):
        errors.append(error("policy.required_reports.duplicates", "required report IDs must be unique"))
    if not string_list(policy.get("known_limits")):
        errors.append(error("policy.known_limits", "known_limits must not be empty"))
    if not string_list(policy.get("required_docs")):
        errors.append(error("policy.required_docs", "required_docs must not be empty"))
    if not isinstance(policy.get("required_doc_markers"), dict):
        errors.append(error("policy.required_doc_markers", "required_doc_markers must be an object"))
    if policy.get("acceptance_marker") != "PHASE213 M5 GENERALIZATION CLOSEOUT PASS":
        errors.append(error("policy.acceptance_marker", "acceptance marker must match Phase 213"))
    return errors


def load_required_reports(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[dict[str, str]]]:
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    for spec in object_list(policy.get("required_reports")):
        report_id = str(spec.get("id"))
        raw_path = spec.get("path")
        path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
        if path is None or not path.is_file():
            sources[report_id] = (path, {})
            if require_artifacts:
                errors.append(error(f"reports.{report_id}.missing", f"required report is missing: {raw_path}", source=report_id))
            continue
        try:
            sources[report_id] = (path, read_json_object(path))
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            sources[report_id] = (path, {})
            errors.append(error(f"reports.{report_id}.malformed", f"required report is malformed: {type(exc).__name__}: {exc}", source=report_id))
    return sources, errors


def validate_required_reports(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    specs = {str(item.get("id")): item for item in object_list(policy.get("required_reports"))}
    for report_id, spec in specs.items():
        path, payload = sources.get(report_id, (None, {}))
        prefix = f"reports.{report_id}"
        if path is None or not path.is_file():
            errors.append(error(f"{prefix}.missing", "required report is missing", source=report_id))
            continue
        if payload.get("kind") != spec.get("expected_kind"):
            errors.append(error(f"{prefix}.kind", f"kind must be {spec.get('expected_kind')}", source=report_id))
        if payload.get("phase") != spec.get("expected_phase"):
            errors.append(error(f"{prefix}.phase", f"phase must be {spec.get('expected_phase')}", source=report_id))
        if payload.get("status") != spec.get("expected_status"):
            errors.append(error(f"{prefix}.status", f"status must be {spec.get('expected_status')}", source=report_id))
        summary = dict_value(payload.get("summary"))
        for key, expected in dict_value(spec.get("expected_summary")).items():
            actual = summary.get(key)
            if isinstance(expected, int):
                if expected == 0:
                    if actual != 0:
                        errors.append(error(f"{prefix}.summary.{key}", f"summary.{key} must be 0", source=report_id))
                elif not isinstance(actual, int) or actual < expected:
                    errors.append(error(f"{prefix}.summary.{key}", f"summary.{key} must be at least {expected}", source=report_id))
            elif actual != expected:
                errors.append(error(f"{prefix}.summary.{key}", f"summary.{key} must be {expected!r}", source=report_id))
    return errors


def validate_docs(config_root: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            errors.append(error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        missing = [marker for marker in string_list(markers.get(raw_path)) if marker not in text]
        if missing:
            errors.append(error(f"docs.{raw_path}.markers", f"missing required markers: {missing}", source="docs"))
    return errors


def source_refs(sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for report_id, (path, payload) in sorted(sources.items()):
        refs.append(
            {
                "id": report_id,
                "path": str(path) if path is not None else None,
                "exists": path.is_file() if path is not None else False,
                "sha256": sha256_file(path) if path is not None and path.is_file() else None,
                "kind": payload.get("kind"),
                "phase": payload.get("phase"),
                "status": payload.get("status"),
                "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
            }
        )
    return refs


def build_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path,
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    validation_errors: list[dict[str, str]],
) -> dict[str, Any]:
    status = "passed" if not validation_errors else "failed"
    decision = "close_m5_move_to_m6" if status == "passed" else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "source_reports": source_refs(sources),
        "accepted_findings": object_list(policy.get("accepted_findings")),
        "known_limits": string_list(policy.get("known_limits")),
        "next_recommendation": policy.get("next_recommendation"),
        "validation_errors": validation_errors,
        "summary": {
            "required_report_count": len(object_list(policy.get("required_reports"))),
            "validation_error_count": len(validation_errors),
            "accepted_finding_count": len(object_list(policy.get("accepted_findings"))),
            "known_limit_count": len(string_list(policy.get("known_limits"))),
            "m5_closed": decision == "close_m5_move_to_m6",
            "phase214_approved": decision == "close_m5_move_to_m6",
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# M5 Generalization Closeout",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- M5 closed: `{summary.get('m5_closed')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next recommendation: {report.get('next_recommendation')}",
        "",
        "## Source Reports",
    ]
    for item in object_list(report.get("source_reports")):
        lines.append(f"- `{item.get('id')}` status=`{item.get('status')}` phase=`{item.get('phase')}` path=`{item.get('path')}`")
    lines.extend(["", "## Known Limits"])
    for item in string_list(report.get("known_limits")):
        lines.append(f"- {item}")
    if object_list(report.get("validation_errors")):
        lines.extend(["", "## Validation Errors"])
        for item in object_list(report.get("validation_errors")):
            lines.append(f"- `{item.get('id')}` {item.get('message')}")
    return "\n".join(lines).rstrip() + "\n"


def run_m5_generalization_closeout(config: M5GeneralizationCloseoutConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    sources, source_errors = load_required_reports(config_root, policy, require_artifacts=config.require_artifacts)
    validation_errors = policy_errors + source_errors + validate_required_reports(policy, sources) + validate_docs(config_root, policy)
    report = build_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        sources=sources,
        validation_errors=validation_errors,
    )
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_path, render_markdown_report(report))
    return report
