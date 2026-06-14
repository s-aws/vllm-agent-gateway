"""Phase 202 chat-visible output-format and usefulness refresh."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.output_format_parity import validate_output_format_parity_report


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chat_visible_output_usefulness_refresh_policy"
EXPECTED_REPORT_KIND = "chat_visible_output_usefulness_refresh_report"
EXPECTED_PHASE = 202
EXPECTED_BACKLOG_ID = "P0-BB-066"
EXPECTED_MILESTONE_ID = "M2"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_visible_output_usefulness_refresh_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase202" / "phase202-chat-visible-output-usefulness-refresh-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase202" / "phase202-chat-visible-output-usefulness-refresh-report.md"


class OutputUsefulnessRefreshStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ChatVisibleOutputUsefulnessRefreshConfig:
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
        errors.append(validation_error("policy.phase", "policy.phase must be 202"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "policy.milestone_id must be M2"))
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must be gateway and anythingllm"))
    if set(string_list(policy.get("required_output_formats"))) != {"format_a", "json"}:
        errors.append(validation_error("policy.required_output_formats", "required_output_formats must be format_a and json"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "required target roots must include both frozen Coinbase fixtures"))
    probes = object_list(policy.get("required_port_health_probes"))
    if len(probes) < 11:
        errors.append(validation_error("policy.required_port_health_probes", "required_port_health_probes must include the full featured probe set"))
    seen_probe_labels: set[str] = set()
    for index, probe in enumerate(probes):
        label = probe.get("label")
        url = probe.get("url")
        if not isinstance(label, str) or not label.strip():
            errors.append(validation_error(f"policy.required_port_health_probes[{index}].label", "probe label is required"))
        elif label in seen_probe_labels:
            errors.append(validation_error(f"policy.required_port_health_probes[{index}].label", "probe labels must be unique"))
        else:
            seen_probe_labels.add(label)
        if not isinstance(url, str) or not url.strip():
            errors.append(validation_error(f"policy.required_port_health_probes[{index}].url", "probe URL is required"))
    minimum_live_case_count = policy.get("minimum_live_case_count")
    if not isinstance(minimum_live_case_count, int) or minimum_live_case_count < 8:
        errors.append(validation_error("policy.minimum_live_case_count", "minimum_live_case_count must be at least 8"))
    minimum_checked = policy.get("minimum_usefulness_checked_case_count")
    if not isinstance(minimum_checked, int) or minimum_checked < 40:
        errors.append(validation_error("policy.minimum_usefulness_checked_case_count", "minimum_usefulness_checked_case_count must be at least 40"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required_docs must be non-empty"))
    if policy.get("acceptance_marker") != "PHASE202 CHAT VISIBLE OUTPUT USEFULNESS REFRESH PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 202"))
    if not dict_value(policy.get("required_phase201_report")).get("path"):
        errors.append(validation_error("policy.required_phase201_report.path", "Phase 201 report path is required"))
    live_reports = dict_value(policy.get("required_live_reports"))
    for report_id in ("output_format_parity", "answer_usefulness"):
        if not dict_value(live_reports.get(report_id)).get("path"):
            errors.append(validation_error(f"policy.required_live_reports.{report_id}.path", f"{report_id} report path is required"))
    return errors


def load_required_report(config_root: Path, spec: dict[str, Any], source: str) -> tuple[Path, dict[str, Any], list[dict[str, str]]]:
    raw_path = spec.get("path")
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else config_root / "<missing>"
    if not isinstance(raw_path, str) or not raw_path.strip():
        return path, {}, [validation_error(f"{source}.path", "report path is required", source=source)]
    if not path.is_file():
        return path, {}, [validation_error(f"{source}.missing", f"report is missing: {raw_path}", source=source)]
    try:
        report = read_json_object(path)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error(f"{source}.malformed", f"report is malformed: {type(exc).__name__}: {exc}", source=source)]
    errors: list[dict[str, str]] = []
    expected_kind = spec.get("expected_kind")
    if isinstance(expected_kind, str) and report.get("kind") != expected_kind:
        errors.append(validation_error(f"{source}.kind", f"report kind must be {expected_kind}", source=source))
    expected_status = spec.get("expected_status")
    if isinstance(expected_status, str) and report.get("status") != expected_status:
        errors.append(validation_error(f"{source}.status", f"report status must be {expected_status}", source=source))
    expected_phase = spec.get("expected_phase")
    if isinstance(expected_phase, int) and report.get("phase") != expected_phase:
        errors.append(validation_error(f"{source}.phase", f"report phase must be {expected_phase}", source=source))
    return path, report, errors


def source_ref(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
    }


def validate_phase201_report(report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    summary = dict_value(report.get("summary"))
    if summary.get("phase202_ready") is not True:
        errors.append(validation_error("phase201.phase202_ready", "Phase 201 must report phase202_ready=true", source="phase201"))
    if summary.get("validation_error_count") != 0:
        errors.append(validation_error("phase201.validation_error_count", "Phase 201 validation_error_count must be 0", source="phase201"))
    return errors


def validate_parity_report(report: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors = [
        validation_error("output_format_parity.report", error, "critical", "output_format_parity")
        for error in validate_output_format_parity_report(report)
    ]
    cases = object_list(report.get("cases"))
    if len(cases) < int(policy.get("minimum_live_case_count", 0)):
        errors.append(validation_error("output_format_parity.case_count", "live parity case count is below policy minimum", source="output_format_parity"))
    target_roots = {str(case.get("target_root")) for case in cases if isinstance(case.get("target_root"), str)}
    missing_roots = sorted(set(string_list(policy.get("required_target_roots"))) - target_roots)
    if missing_roots:
        errors.append(validation_error("output_format_parity.target_roots", "missing target roots: " + ", ".join(missing_roots), source="output_format_parity"))
    port_health = object_list(report.get("port_health"))
    if not port_health:
        errors.append(validation_error("output_format_parity.port_health", "port_health proof is required", "critical", "output_format_parity"))
    expected_probes = {
        (str(probe.get("label")), str(probe.get("url")))
        for probe in object_list(policy.get("required_port_health_probes"))
        if isinstance(probe.get("label"), str) and isinstance(probe.get("url"), str)
    }
    actual_probes = {
        (str(probe.get("label")), str(probe.get("url")))
        for probe in port_health
        if isinstance(probe.get("label"), str) and isinstance(probe.get("url"), str)
    }
    missing_probes = sorted(expected_probes - actual_probes)
    extra_probes = sorted(actual_probes - expected_probes)
    if missing_probes:
        errors.append(
            validation_error(
                "output_format_parity.port_health.missing_probes",
                "missing port-health probes: " + ", ".join(f"{label}={url}" for label, url in missing_probes),
                "critical",
                "output_format_parity",
            )
        )
    if extra_probes:
        errors.append(
            validation_error(
                "output_format_parity.port_health.extra_probes",
                "unexpected port-health probes: " + ", ".join(f"{label}={url}" for label, url in extra_probes),
                source="output_format_parity",
            )
        )
    for index, probe in enumerate(port_health):
        if probe.get("status") != "passed":
            errors.append(validation_error(f"output_format_parity.port_health[{index}].status", "port health probe must pass", "critical", "output_format_parity"))
        if not isinstance(probe.get("label"), str) or not probe["label"].strip():
            errors.append(validation_error(f"output_format_parity.port_health[{index}].label", "port health label is required", source="output_format_parity"))
        if not isinstance(probe.get("url"), str) or not probe["url"].strip():
            errors.append(validation_error(f"output_format_parity.port_health[{index}].url", "port health URL is required", source="output_format_parity"))
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    for case in cases:
        case_id = str(case.get("case_id") or "<missing>")
        responses = dict_value(case.get("responses"))
        for surface in required_surfaces:
            surface_report = dict_value(responses.get(surface))
            if surface_report.get("status") != "passed":
                errors.append(validation_error(f"output_format_parity.{case_id}.{surface}.status", f"{surface} must pass", source="output_format_parity"))
                continue
            format_a = dict_value(surface_report.get("format_a"))
            json_report = dict_value(surface_report.get("json"))
            if not isinstance(format_a.get("text"), str) or not format_a["text"].strip():
                errors.append(validation_error(f"output_format_parity.{case_id}.{surface}.format_a", "FormatA text is required", source="output_format_parity"))
            parsed = dict_value(json_report.get("parsed"))
            if parsed.get("output_format") != "json":
                errors.append(validation_error(f"output_format_parity.{case_id}.{surface}.json.output_format", "JSON parsed output_format must be json", source="output_format_parity"))
            if not isinstance(json_report.get("text"), str) or not json_report["text"].strip():
                errors.append(validation_error(f"output_format_parity.{case_id}.{surface}.json.text", "JSON text is required", source="output_format_parity"))
    return errors


def validate_usefulness_report(report: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if report.get("require_artifacts") is not True:
        errors.append(validation_error("answer_usefulness.require_artifacts", "answer usefulness report must be generated with require_artifacts=true", "critical", "answer_usefulness"))
    if object_list(report.get("errors")) or report.get("errors"):
        errors.append(validation_error("answer_usefulness.errors", "answer usefulness report must have no errors", "critical", "answer_usefulness"))
    summary = dict_value(report.get("summary"))
    if summary.get("error_count") != 0:
        errors.append(validation_error("answer_usefulness.error_count", "answer usefulness error_count must be 0", "critical", "answer_usefulness"))
    if int(summary.get("checked_case_count") or 0) < int(policy.get("minimum_usefulness_checked_case_count", 0)):
        errors.append(validation_error("answer_usefulness.checked_case_count", "checked_case_count is below policy minimum", source="answer_usefulness"))
    entries = object_list(report.get("entries"))
    if not entries:
        errors.append(validation_error("answer_usefulness.entries", "answer usefulness entries are required", "critical", "answer_usefulness"))
    checked_total = 0
    for entry in entries:
        entry_id = str(entry.get("entry_id") or "<missing>")
        if int(entry.get("error_count") or 0) != 0:
            errors.append(validation_error(f"answer_usefulness.entries.{entry_id}.error_count", "entry error_count must be 0", "critical", "answer_usefulness"))
        checked_cases = int(entry.get("checked_cases") or 0)
        expected_cases = int(entry.get("expected_case_count") or 0)
        checked_total += checked_cases
        if checked_cases <= 0:
            errors.append(validation_error(f"answer_usefulness.entries.{entry_id}.checked_cases", "entry checked_cases must be positive", source="answer_usefulness"))
        if expected_cases <= 0:
            errors.append(validation_error(f"answer_usefulness.entries.{entry_id}.expected_case_count", "entry expected_case_count must be positive", source="answer_usefulness"))
        if checked_cases != expected_cases:
            errors.append(validation_error(f"answer_usefulness.entries.{entry_id}.case_count", "checked_cases must equal expected_case_count", source="answer_usefulness"))
        if not isinstance(entry.get("local_eval_path"), str) or not entry["local_eval_path"].strip():
            errors.append(validation_error(f"answer_usefulness.entries.{entry_id}.local_eval_path", "local_eval_path is required", source="answer_usefulness"))
    if checked_total != summary.get("checked_case_count"):
        errors.append(validation_error("answer_usefulness.checked_case_total", "entry checked_cases must sum to summary.checked_case_count", source="answer_usefulness"))
    return errors


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            errors.append(validation_error(f"docs.{raw_path}.missing", f"required doc is missing: {raw_path}", "medium", "documentation"))
    return docs, errors


def build_chat_visible_output_usefulness_refresh_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None,
    loaded_reports: dict[str, tuple[Path, dict[str, Any]]],
    load_errors: list[dict[str, str]],
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(load_errors)
    phase201 = loaded_reports.get("phase201", (Path(), {}))[1]
    parity = loaded_reports.get("output_format_parity", (Path(), {}))[1]
    usefulness = loaded_reports.get("answer_usefulness", (Path(), {}))[1]
    errors.extend(validate_phase201_report(phase201))
    errors.extend(validate_parity_report(parity, policy))
    errors.extend(validate_usefulness_report(usefulness, policy))
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    parity_cases = object_list(parity.get("cases"))
    surface_counts = {
        surface: sum(1 for case in parity_cases if dict_value(dict_value(case.get("responses")).get(surface)).get("status") == "passed")
        for surface in string_list(policy.get("required_surfaces"))
    }
    source_refs = {
        report_id: source_ref(path, payload)
        for report_id, (path, payload) in loaded_reports.items()
    }
    usefulness_summary = dict_value(usefulness.get("summary"))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": OutputUsefulnessRefreshStatus.FAILED.value if errors else OutputUsefulnessRefreshStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": source_refs,
        "docs": docs,
        "validation_errors": errors,
        "summary": {
            "phase201_ready": dict_value(phase201.get("summary")).get("phase202_ready") is True,
            "live_case_count": len(parity_cases),
            "target_roots": sorted({case.get("target_root") for case in parity_cases if isinstance(case.get("target_root"), str)}),
            "prompt_family_count": len({case.get("prompt_family") for case in parity_cases if isinstance(case.get("prompt_family"), str)}),
            "surface_pass_counts": surface_counts,
            "answer_usefulness_checked_case_count": usefulness_summary.get("checked_case_count"),
            "answer_usefulness_error_count": usefulness_summary.get("error_count"),
            "validation_error_count": len(errors),
            "m2_ready": not errors,
            "phase203_ready": not errors,
            "next_action": "work Phase 203 Workflow/Skill/Tool Selection Matrix Refresh"
            if not errors
            else "repair Phase 202 live output/usefulness refresh gaps before M3 work",
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
            "policy_path",
            "policy_sha256",
            "source_refs",
            "docs",
            "validation_errors",
            "summary",
        )
    }


def validate_chat_visible_output_usefulness_refresh_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None,
    loaded_reports: dict[str, tuple[Path, dict[str, Any]]],
    load_errors: list[dict[str, str]],
) -> list[str]:
    expected = build_chat_visible_output_usefulness_refresh_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        loaded_reports=loaded_reports,
        load_errors=load_errors,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt chat-visible output usefulness refresh"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 202 Chat-Visible Output Usefulness Refresh",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Live cases: `{summary.get('live_case_count')}`",
        f"- Target roots: `{', '.join(string_list(summary.get('target_roots')))}`",
        f"- Surface pass counts: `{json.dumps(summary.get('surface_pass_counts'), sort_keys=True)}`",
        f"- Answer-usefulness checked cases: `{summary.get('answer_usefulness_checked_case_count')}`",
        f"- M2 ready: `{summary.get('m2_ready')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
    ]
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def load_required_reports(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    loaded: dict[str, tuple[Path, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    phase201_path, phase201_report, phase201_errors = load_required_report(
        config_root,
        dict_value(policy.get("required_phase201_report")),
        "phase201",
    )
    loaded["phase201"] = (phase201_path, phase201_report)
    errors.extend(phase201_errors)
    for report_id, spec in dict_value(policy.get("required_live_reports")).items():
        path, report, report_errors = load_required_report(config_root, dict_value(spec), report_id)
        loaded[report_id] = (path, report)
        errors.extend(report_errors)
    return loaded, errors


def run_chat_visible_output_usefulness_refresh(config: ChatVisibleOutputUsefulnessRefreshConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    loaded_reports, load_errors = load_required_reports(config_root, policy)
    report = build_chat_visible_output_usefulness_refresh_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        loaded_reports=loaded_reports,
        load_errors=load_errors,
    )
    validation_errors = validate_chat_visible_output_usefulness_refresh_report(
        report,
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        loaded_reports=loaded_reports,
        load_errors=load_errors,
    )
    if validation_errors:
        report["status"] = OutputUsefulnessRefreshStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "chat_visible_output_usefulness_refresh")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["m2_ready"] = False
        report["summary"]["phase203_ready"] = False
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
