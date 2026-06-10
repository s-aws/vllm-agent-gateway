"""Priority 0 corpus-level gap taxonomy report."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import DEFAULT_CORPUS_PATH
from vllm_agent_gateway.acceptance.failure_taxonomy import (
    FailureCategory,
    category_counts,
    collect_findings,
    highest_severity,
    severity_counts,
)


SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "priority0-gap-taxonomy"


@dataclass(frozen=True)
class Priority0GapTaxonomyConfig:
    config_root: Path
    corpus_path: Path = DEFAULT_CORPUS_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"priority0-gap-taxonomy-{utc_timestamp()}.json"


def markdown_path_for(path: Path) -> Path:
    return path.with_suffix(".md")


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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def gap_class_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "routing": 0,
        "context_gathering": 0,
        "skill_tool_selection": 0,
        "deterministic_formatter": 0,
        "model_capability": 0,
        "safety_boundary": 0,
        "documentation": 0,
        "test_coverage": 0,
    }
    for item in findings:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        gap_class = str(evidence.get("gap_class") or "model_capability")
        counts[gap_class] = counts.get(gap_class, 0) + 1
    return counts


def repair_action_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in findings:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        action = str(evidence.get("bounded_repair_action") or item.get("recommended_next_action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def comparison_input_report(
    *,
    entry: dict[str, Any],
    comparison_path: Path | None,
    comparison_ref: dict[str, Any],
    loaded: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    return {
        "entry_id": entry.get("entry_id"),
        "phase": entry.get("phase"),
        "priority_backlog_id": entry.get("priority_backlog_id"),
        "prompt_family": entry.get("prompt_family"),
        "path": str(comparison_path) if comparison_path is not None else comparison_ref.get("path"),
        "expected_sha256": comparison_ref.get("sha256"),
        "kind": loaded.get("kind") if isinstance(loaded, dict) else None,
        "status": loaded.get("status") if isinstance(loaded, dict) else status,
        "response_count": loaded.get("response_count") if isinstance(loaded, dict) else comparison_ref.get("response_count"),
        "passed_response_count": loaded.get("passed_response_count")
        if isinstance(loaded, dict)
        else comparison_ref.get("passed_response_count"),
        "critical_finding_count": loaded.get("critical_finding_count")
        if isinstance(loaded, dict)
        else comparison_ref.get("critical_finding_count"),
        "high_finding_count": loaded.get("high_finding_count")
        if isinstance(loaded, dict)
        else comparison_ref.get("high_finding_count"),
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Priority 0 Gap Taxonomy Report",
        "",
        f"- Status: {report['status']}",
        f"- Created at: {report['created_at']}",
        f"- Corpus path: {report['corpus_path']}",
        f"- Comparison count: {report['summary']['comparison_count']}",
        f"- Finding count: {report['summary']['finding_count']}",
        f"- Highest severity: {report['summary']['highest_severity']}",
        "",
        "## Gap Class Counts",
        "",
        "| Gap class | Count |",
        "| --- | ---: |",
    ]
    for gap_class, count in report["summary"]["gap_class_counts"].items():
        if count:
            lines.append(f"| {gap_class} | {count} |")
    if not any(report["summary"]["gap_class_counts"].values()):
        lines.append("| none | 0 |")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Severity | Category | Gap class | Source | Message | Repair action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["findings"]:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        lines.append(
            "| {severity} | {category} | {gap_class} | {source} | {message} | {action} |".format(
                severity=item.get("severity"),
                category=item.get("category"),
                gap_class=evidence.get("gap_class", ""),
                source=str(item.get("source", "")).replace("\n", " ")[:240],
                message=str(item.get("message", "")).replace("\n", " ")[:240],
                action=str(evidence.get("bounded_repair_action") or item.get("recommended_next_action") or "").replace(
                    "\n", " "
                )[:300],
            )
        )
    if not report["findings"]:
        lines.append("| none | none | none | all | No Priority 0 comparison misses found. | No action required. |")
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_priority0_gap_taxonomy(config: Priority0GapTaxonomyConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    corpus_path = resolve_path(config_root, config.corpus_path)
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    markdown_path = config.markdown_output_path or markdown_path_for(output_path)
    if not markdown_path.is_absolute():
        markdown_path = config_root / markdown_path

    errors: list[str] = []
    findings: list[dict[str, Any]] = []
    input_reports: list[dict[str, Any]] = []
    try:
        corpus = read_json_object(corpus_path)
        entries = [entry for entry in object_list(corpus.get("entries")) if entry.get("status") == "stable"]
        for entry in entries:
            entry_id = str(entry.get("entry_id") or entry.get("phase") or "unknown")
            comparison_ref = entry.get("comparison") if isinstance(entry.get("comparison"), dict) else {}
            path_value = comparison_ref.get("path")
            expected_hash = comparison_ref.get("sha256")
            if not isinstance(path_value, str) or not path_value.strip():
                errors.append(f"{entry_id}.comparison.path is required")
                input_reports.append(
                    comparison_input_report(
                        entry=entry,
                        comparison_path=None,
                        comparison_ref=comparison_ref,
                        loaded=None,
                        status="missing_path",
                    )
                )
                continue
            comparison_path = resolve_path(config_root, path_value)
            if not comparison_path.is_file():
                if config.require_artifacts:
                    errors.append(f"{entry_id}.comparison artifact is required: {path_value}")
                input_reports.append(
                    comparison_input_report(
                        entry=entry,
                        comparison_path=comparison_path,
                        comparison_ref=comparison_ref,
                        loaded=None,
                        status="missing_artifact",
                    )
                )
                continue
            if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                errors.append(f"{entry_id}.comparison.sha256 must be a 64-character hash")
            else:
                actual_hash = sha256_file(comparison_path)
                if actual_hash != expected_hash:
                    errors.append(f"{entry_id}.comparison.sha256 is stale for {path_value}")
            loaded = read_json_object(comparison_path)
            input_reports.append(
                comparison_input_report(
                    entry=entry,
                    comparison_path=comparison_path,
                    comparison_ref=comparison_ref,
                    loaded=loaded,
                    status=str(loaded.get("status") or "unknown"),
                )
            )
            findings.extend(collect_findings(loaded, report_label=entry_id, report_path=comparison_path))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")

    findings = sorted(
        findings,
        key=lambda item: (
            str(item.get("report_label")),
            str(item.get("source")),
            str(item.get("category")),
            str(item.get("message")),
        ),
    )
    summary = {
        "entry_count": len({str(item.get("entry_id")) for item in input_reports if item.get("entry_id")}),
        "comparison_count": len(input_reports),
        "finding_count": len(findings),
        "category_counts": category_counts(findings),
        "severity_counts": severity_counts(findings),
        "gap_class_counts": gap_class_counts(findings),
        "repair_action_counts": repair_action_counts(findings),
        "highest_severity": highest_severity(findings),
        "error_count": len(errors),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "priority0_gap_taxonomy_report",
        "status": "passed" if not errors and not findings else "failed",
        "created_at": utc_timestamp(),
        "corpus_path": str(corpus_path),
        "require_artifacts": config.require_artifacts,
        "input_reports": input_reports,
        "summary": summary,
        "findings": findings,
        "errors": errors,
        "markdown_report_path": str(markdown_path),
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_markdown(markdown_path, report)
    return report
