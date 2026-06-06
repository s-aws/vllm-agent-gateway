"""Controller run inspection helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class InspectorOutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


DEFAULT_REPORT_DIR = Path("runtime-state") / "run-inspector"


@dataclass(frozen=True)
class RunInspectorConfig:
    config_root: Path
    controller_output_root: Path | None = None
    run_id: str | None = None
    workflow: str | None = None
    output_path: Path | None = None
    output_format: InspectorOutputFormat = InspectorOutputFormat.TEXT


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def mnt_path_to_windows(path_value: str) -> Path | None:
    normalized = path_value.replace("\\", "/")
    parts = normalized.split("/")
    if len(parts) < 4 or parts[0] != "" or parts[1] != "mnt" or len(parts[2]) != 1:
        return None
    drive = parts[2].upper()
    return Path(f"{drive}:\\" + "\\".join(parts[3:]))


def resolved_existing_path(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    candidates = [Path(path_value)]
    converted = mnt_path_to_windows(path_value)
    if converted is not None:
        candidates.append(converted)
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def default_controller_output_roots(config_root: Path) -> list[Path]:
    roots: list[Path] = []
    env_output = os.environ.get("CONTROLLER_OUTPUT_ROOT")
    if env_output:
        roots.append(Path(env_output))
    env_state = os.environ.get("AGENTIC_AGENTS_STATE_ROOT")
    if env_state:
        roots.append(Path(env_state) / "controller-artifacts")
    roots.append(config_root / "runtime-state" / "controller-artifacts")
    roots.append(Path("C:/private_agentic_agents/runtime-state/controller-artifacts"))
    roots.append(Path("/mnt/c/private_agentic_agents/runtime-state/controller-artifacts"))

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def controller_output_root(config: RunInspectorConfig) -> Path:
    if config.controller_output_root is not None:
        return config.controller_output_root
    candidates = [root for root in default_controller_output_roots(config.config_root) if (root / "controller-runs").exists()]
    if not candidates:
        return config.config_root / "runtime-state" / "controller-artifacts"
    return max(candidates, key=lambda root: latest_record_mtime(root) or 0)


def latest_record_mtime(output_root: Path) -> float | None:
    registry = output_root / "controller-runs"
    mtimes = [path.stat().st_mtime for path in registry.glob("*.json") if path.is_file()]
    return max(mtimes) if mtimes else None


def parse_updated_at(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def controller_run_records(output_root: Path, workflow: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    registry = output_root / "controller-runs"
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(registry.glob("*.json")):
        record = read_json_file(path)
        if not record or record.get("kind") != "controller_run_record":
            continue
        if workflow and record.get("workflow") != workflow:
            continue
        records.append((path, record))
    return records


def sort_key_for_record(item: tuple[Path, dict[str, Any]]) -> tuple[float, float]:
    path, record = item
    updated_at = parse_updated_at(record.get("updated_at"))
    return (updated_at or path.stat().st_mtime, path.stat().st_mtime)


def select_run_record(config: RunInspectorConfig, output_root: Path) -> tuple[Path, dict[str, Any]]:
    records = controller_run_records(output_root, workflow=config.workflow)
    if config.run_id:
        for path, record in records if config.workflow else controller_run_records(output_root):
            if record.get("run_id") == config.run_id:
                return path, record
        raise RuntimeError(f"Run {config.run_id!r} was not found under {output_root / 'controller-runs'}")
    if not records:
        workflow_note = f" for workflow {config.workflow!r}" if config.workflow else ""
        raise RuntimeError(f"No controller run records found{workflow_note} under {output_root / 'controller-runs'}")
    return max(records, key=sort_key_for_record)


def route_rules_from_decision(route_decision: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    evidence = route_decision.get("evidence") if isinstance(route_decision.get("evidence"), list) else []
    for item in evidence:
        if isinstance(item, dict) and item.get("source") == "router_rule" and isinstance(item.get("rule"), str):
            rules.append(item["rule"])
    return rules


def semantic_status(record: dict[str, Any]) -> str:
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if isinstance(summary.get("semantic_status"), str):
        return summary["semantic_status"]
    failures = record.get("failures") if isinstance(record.get("failures"), list) else []
    status = record.get("status")
    if status == "completed" and not failures:
        return "completed_no_failures"
    if status == "completed":
        return "completed_with_failures"
    return str(status or "unknown")


def artifact_keys(record: dict[str, Any]) -> list[str]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    return sorted(str(key) for key in artifacts)


def load_artifact(record: dict[str, Any], key: str) -> dict[str, Any] | None:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = resolved_existing_path(artifacts.get(key))
    if path is None:
        return None
    return read_json_file(path)


def mutation_proof(record: dict[str, Any]) -> dict[str, Any]:
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    proof = {
        "source_changed": summary.get("source_changed"),
        "disposable_copy_changed": summary.get("disposable_copy_changed"),
        "source_mutation": summary.get("source_mutation"),
        "target_root": summary.get("target_root"),
    }
    hash_summary = record.get("hash_summary") if isinstance(record.get("hash_summary"), dict) else {}
    if hash_summary:
        proof["changed_files"] = hash_summary.get("changed_files")
    return {key: value for key, value in proof.items() if value is not None}


def inspect_run(config: RunInspectorConfig) -> dict[str, Any]:
    output_root = controller_output_root(config)
    record_path, record = select_run_record(config, output_root)
    route_decision = load_artifact(record, "route_decision") or {}
    downstream = route_decision.get("downstream") if isinstance(route_decision.get("downstream"), dict) else {}
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    selected_skills = route_decision.get("selected_skills")
    if not isinstance(selected_skills, list):
        selected_skills = summary.get("selected_skills") if isinstance(summary.get("selected_skills"), list) else []
    selected_tools = route_decision.get("selected_tools")
    if not isinstance(selected_tools, list):
        selected_tools = []

    report = {
        "schema_version": 1,
        "kind": "controller_run_inspection",
        "created_at": utc_timestamp(),
        "controller_output_root": str(output_root),
        "record_path": str(record_path),
        "run_id": record.get("run_id"),
        "workflow": record.get("workflow"),
        "status": record.get("status"),
        "updated_at": record.get("updated_at"),
        "target_root": summary.get("target_root") or route_decision.get("target_root"),
        "route": {
            "status": summary.get("route_status") or route_decision.get("status"),
            "selected_workflow": summary.get("selected_workflow") or route_decision.get("selected_workflow"),
            "rules": route_rules_from_decision(route_decision),
            "confidence": summary.get("confidence") or route_decision.get("confidence"),
            "next_action": summary.get("next_action") or route_decision.get("next_action"),
        },
        "selected_skills": [str(item) for item in selected_skills],
        "selected_tools": [str(item) for item in selected_tools],
        "downstream": {
            "workflow": summary.get("downstream_workflow") or downstream.get("workflow"),
            "run_id": summary.get("downstream_run_id") or downstream.get("run_id"),
            "status": summary.get("downstream_status") or downstream.get("status"),
            "artifact_keys": sorted(str(key) for key in (downstream.get("artifacts") or {}).keys())
            if isinstance(downstream.get("artifacts"), dict)
            else [],
        },
        "artifact_keys": sorted(str(key) for key in artifacts),
        "artifact_paths": {str(key): str(value) for key, value in artifacts.items() if isinstance(value, str)},
        "semantic_status": semantic_status(record),
        "warning_count": len(record.get("warnings") if isinstance(record.get("warnings"), list) else []),
        "failure_count": len(record.get("failures") if isinstance(record.get("failures"), list) else []),
        "failures": record.get("failures") if isinstance(record.get("failures"), list) else [],
        "mutation_proof": mutation_proof(record),
        "resume_key": record.get("resume_key") if isinstance(record.get("resume_key"), dict) else {},
    }
    if config.output_path:
        write_json(config.output_path, report)
        report["report_path"] = str(config.output_path.resolve())
        write_json(config.output_path, report)
    return report


def format_run_inspection(report: dict[str, Any]) -> str:
    route = report.get("route") if isinstance(report.get("route"), dict) else {}
    downstream = report.get("downstream") if isinstance(report.get("downstream"), dict) else {}
    mutation = report.get("mutation_proof") if isinstance(report.get("mutation_proof"), dict) else {}
    lines = [
        "Latest Run Inspection",
        f"- Run ID: {report.get('run_id')}",
        f"- Workflow: {report.get('workflow')}",
        f"- Status: {report.get('status')}",
        f"- Semantic status: {report.get('semantic_status')}",
        f"- Target root: {report.get('target_root')}",
        f"- Route: {route.get('selected_workflow')} ({route.get('status')})",
    ]
    rules = route.get("rules") if isinstance(route.get("rules"), list) else []
    if rules:
        lines.append(f"- Route rules: {', '.join(str(item) for item in rules)}")
    skills = report.get("selected_skills") if isinstance(report.get("selected_skills"), list) else []
    if skills:
        lines.append(f"- Selected skills: {', '.join(str(item) for item in skills)}")
    tools = report.get("selected_tools") if isinstance(report.get("selected_tools"), list) else []
    if tools:
        lines.append(f"- Selected tools: {', '.join(str(item) for item in tools)}")
    if downstream.get("workflow") or downstream.get("run_id"):
        lines.append(
            f"- Downstream: {downstream.get('workflow')} / {downstream.get('run_id')} / {downstream.get('status')}"
        )
    artifact_keys = report.get("artifact_keys") if isinstance(report.get("artifact_keys"), list) else []
    lines.append(f"- Artifacts: {len(artifact_keys)} key(s): {', '.join(str(item) for item in artifact_keys[:12])}")
    if len(artifact_keys) > 12:
        lines.append(f"- Artifacts omitted: {len(artifact_keys) - 12}")
    lines.append(f"- Warnings: {report.get('warning_count')}")
    lines.append(f"- Failures: {report.get('failure_count')}")
    if mutation:
        mutation_text = ", ".join(f"{key}={value}" for key, value in sorted(mutation.items()))
        lines.append(f"- Mutation proof: {mutation_text}")
    if report.get("report_path"):
        lines.append(f"- Report: {report.get('report_path')}")
    return "\n".join(lines)
