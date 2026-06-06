"""Compare acceptance and field-test run artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


DEFAULT_REPORT_DIR = Path("runtime-state") / "run-artifact-diffs"


class RunReportKind(str, Enum):
    V1_ACCEPTANCE = "v1_acceptance_report"
    FOUNDER_FIELD = "founder_field_prompt_evaluation"
    MODEL_PORTABILITY = "model_portability_report"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RunArtifactDiffConfig:
    left_report_path: Path
    right_report_path: Path
    config_root: Path
    left_label: str = "left"
    right_label: str = "right"
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"run-artifact-diff-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"report root must be an object: {path}")
    return value


def report_kind(report: dict[str, Any]) -> RunReportKind:
    raw = str(report.get("kind") or "")
    try:
        return RunReportKind(raw)
    except ValueError:
        return RunReportKind.UNKNOWN


def existing_artifact_path(raw_path: object, *, base_path: Path | None = None) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidates: list[Path] = []
    raw = raw_path.strip()
    path = Path(raw)
    candidates.append(path)
    if not path.is_absolute() and base_path is not None:
        candidates.append(base_path.parent / path)
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/mnt/c/"):
        candidates.append(Path("C:/" + normalized[len("/mnt/c/") :]))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def stable_digest(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def numeric_delta(left: object, right: object) -> int | None:
    if isinstance(left, int) and isinstance(right, int):
        return right - left
    return None


def set_diff(left: set[str], right: set[str]) -> dict[str, list[str]]:
    return {
        "added": sorted(right - left),
        "removed": sorted(left - right),
        "unchanged_count": len(left & right),
    }


def status_map(items: object, key: str = "id") -> dict[str, str]:
    if not isinstance(items, list):
        return {}
    result: dict[str, str] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get(key)
        if not isinstance(item_id, str) or not item_id:
            item_id = f"item_{index}"
        result[item_id] = str(item.get("status") or "")
    return result


def health_status_map(items: object) -> dict[str, str]:
    if not isinstance(items, list):
        return {}
    result: dict[str, str] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            name = f"health_{index}"
        status = str(item.get("status") or "")
        http_status = item.get("http_status")
        result[name] = f"{status}:{http_status}" if http_status is not None else status
    return result


def fixture_signatures(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = report.get("fixture_state")
    if not isinstance(raw, dict):
        before = report.get("fixture_state_before")
        after = report.get("fixture_state_after")
        if isinstance(before, dict) or isinstance(after, dict):
            raw = {"before": before or {}, "after": after or {}}
        else:
            return {}
    signatures: dict[str, dict[str, Any]] = {}
    for target_root, value in raw.items():
        if isinstance(value, dict):
            signatures[str(target_root)] = {
                "sha256": stable_digest(value),
                "hash_count": len(value.get("hashes") or {}) if isinstance(value.get("hashes"), dict) else None,
                "git_clean": value.get("git_status", {}).get("clean")
                if isinstance(value.get("git_status"), dict)
                else None,
            }
        else:
            signatures[str(target_root)] = {"sha256": stable_digest(value), "hash_count": None, "git_clean": None}
    return signatures


def extract_founder_summary(report: dict[str, Any]) -> dict[str, Any]:
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    case_statuses: dict[str, str] = {}
    case_route_rules: dict[str, str] = {}
    case_workflows: dict[str, str] = {}
    semantic_miss_cases: set[str] = set()
    output_miss_cases: set[str] = set()
    selected_skills: set[str] = set()
    expected_artifacts: set[str] = set()
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or f"case_{index}")
        case_statuses[case_id] = str(item.get("status") or "")
        expected_rule = item.get("expected_rule")
        if isinstance(expected_rule, str) and expected_rule:
            case_route_rules[case_id] = expected_rule
        expected_workflow = item.get("expected_workflow")
        if isinstance(expected_workflow, str) and expected_workflow:
            case_workflows[case_id] = expected_workflow
        if item.get("semantic_quality_status") not in (None, "", "passed"):
            semantic_miss_cases.add(case_id)
        if item.get("output_contract_status") not in (None, "", "passed"):
            output_miss_cases.add(case_id)
        expected_skill = item.get("expected_skill_id")
        if isinstance(expected_skill, str) and expected_skill:
            selected_skills.add(expected_skill)
        expected_artifact = item.get("expected_artifact_key")
        if isinstance(expected_artifact, str) and expected_artifact:
            expected_artifacts.add(expected_artifact)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "kind": RunReportKind.FOUNDER_FIELD.value,
        "status": report.get("status"),
        "created_at": report.get("created_at"),
        "case_count": len(cases),
        "passed_count": summary.get("passed"),
        "failed_count": summary.get("failed"),
        "case_statuses": case_statuses,
        "case_route_rules": case_route_rules,
        "case_workflows": case_workflows,
        "semantic_miss_cases": sorted(semantic_miss_cases),
        "output_miss_cases": sorted(output_miss_cases),
        "selected_skills": sorted(selected_skills),
        "expected_artifacts": sorted(expected_artifacts),
        "fixture_signatures": fixture_signatures(report),
        "artifact_count": len(cases),
    }


def extract_v1_summary(report: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    suite_runs = report.get("suite_runs") if isinstance(report.get("suite_runs"), list) else []
    founder_summary = report.get("founder_field_summary") if isinstance(report.get("founder_field_summary"), dict) else {}
    founder_report_summary: dict[str, Any] = {}
    founder_report_path = existing_artifact_path(founder_summary.get("report_path"), base_path=source_path)
    if founder_report_path is not None:
        founder_report_summary = extract_founder_summary(load_json(founder_report_path))
        founder_report_summary["report_path"] = str(founder_report_path)
    skill_health = report.get("skill_library_health") if isinstance(report.get("skill_library_health"), dict) else {}
    catalog_summary = skill_health.get("catalog_summary") if isinstance(skill_health.get("catalog_summary"), dict) else {}
    prompt_catalog_summary = (
        skill_health.get("prompt_catalog_summary")
        if isinstance(skill_health.get("prompt_catalog_summary"), dict)
        else {}
    )
    generated_reports = (
        skill_health.get("generated_reports")
        if isinstance(skill_health.get("generated_reports"), dict)
        else {}
    )
    return {
        "kind": RunReportKind.V1_ACCEPTANCE.value,
        "status": report.get("status"),
        "profile": report.get("profile"),
        "created_at": report.get("created_at"),
        "target_roots": report.get("target_roots") if isinstance(report.get("target_roots"), list) else [],
        "suite_statuses": status_map(suite_runs),
        "health_statuses": health_status_map(report.get("health")),
        "json_output_count": len(report.get("json_output") or []),
        "feedback_count": len(report.get("feedback") or []),
        "error_count": len(report.get("errors") or []),
        "founder_field_summary": founder_summary,
        "founder_field_report": founder_report_summary,
        "skill_library_status": skill_health.get("status"),
        "skill_count": catalog_summary.get("skill_count"),
        "eval_case_count": catalog_summary.get("eval_case_count"),
        "route_key_count": catalog_summary.get("route_key_count"),
        "prompt_matrix_failed": prompt_catalog_summary.get("prompt_matrix_failed"),
        "generated_report_count": len(generated_reports),
        "fixture_signatures": fixture_signatures(report),
        "artifact_count": len(suite_runs)
        + len(report.get("json_output") or [])
        + len(report.get("feedback") or [])
        + len(report.get("health") or [])
        + len(generated_reports),
    }


def extract_model_portability_summary(report: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    acceptance_summary: dict[str, Any] = {}
    acceptance_path = existing_artifact_path(report.get("acceptance_report_path"), base_path=source_path)
    if acceptance_path is not None:
        acceptance_summary = extract_v1_summary(load_json(acceptance_path), source_path=acceptance_path)
        acceptance_summary["report_path"] = str(acceptance_path)
    candidate = report.get("candidate") if isinstance(report.get("candidate"), dict) else {}
    return {
        "kind": RunReportKind.MODEL_PORTABILITY.value,
        "status": report.get("status"),
        "created_at": report.get("created_at"),
        "candidate_id": candidate.get("candidate_id"),
        "candidate_model_base_url": candidate.get("candidate_model_base_url"),
        "candidate_model_ids": report.get("candidate_model_probe", {}).get("model_ids")
        if isinstance(report.get("candidate_model_probe"), dict)
        else [],
        "classification_summary": report.get("classification_summary")
        if isinstance(report.get("classification_summary"), dict)
        else {},
        "classified_failure_count": len(report.get("classified_failures") or []),
        "acceptance_report": report.get("acceptance_report") if isinstance(report.get("acceptance_report"), dict) else {},
        "nested_acceptance": acceptance_summary,
        "artifact_count": len(report.get("classified_failures") or []) + (acceptance_summary.get("artifact_count") or 0),
    }


def extract_summary(report: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    kind = report_kind(report)
    if kind == RunReportKind.FOUNDER_FIELD:
        return extract_founder_summary(report)
    if kind == RunReportKind.V1_ACCEPTANCE:
        return extract_v1_summary(report, source_path=source_path)
    if kind == RunReportKind.MODEL_PORTABILITY:
        return extract_model_portability_summary(report, source_path=source_path)
    return {
        "kind": RunReportKind.UNKNOWN.value,
        "status": report.get("status"),
        "created_at": report.get("created_at"),
        "artifact_count": len(report),
        "sha256": stable_digest(report),
    }


def nested_founder(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("kind") == RunReportKind.FOUNDER_FIELD.value:
        return summary
    nested = summary.get("founder_field_report")
    if isinstance(nested, dict):
        return nested
    nested_acceptance = summary.get("nested_acceptance")
    if isinstance(nested_acceptance, dict):
        nested_founder_report = nested_acceptance.get("founder_field_report")
        if isinstance(nested_founder_report, dict):
            return nested_founder_report
    return {}


def nested_v1(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("kind") == RunReportKind.V1_ACCEPTANCE.value:
        return summary
    nested = summary.get("nested_acceptance")
    return nested if isinstance(nested, dict) else {}


def map_changes(left: dict[str, str], right: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    changes: list[dict[str, str]] = []
    for key in sorted(set(left) | set(right)):
        left_value = left.get(key, "")
        right_value = right.get(key, "")
        if left_value != right_value:
            changes.append({"id": key, "left": left_value, "right": right_value})
    return {"changed": changes, "changed_count": len(changes)}


def fixture_state_changes(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for target in sorted(set(left) | set(right)):
        left_value = left.get(target)
        right_value = right.get(target)
        if left_value != right_value:
            changes.append({"target_root": target, "left": left_value, "right": right_value})
    return changes


def classification_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, dict[str, int | None]]:
    keys = sorted(set(left) | set(right))
    return {
        key: {"left": left.get(key), "right": right.get(key), "delta": numeric_delta(left.get(key), right.get(key))}
        for key in keys
        if left.get(key) != right.get(key)
    }


def build_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_founder = nested_founder(left)
    right_founder = nested_founder(right)
    left_v1 = nested_v1(left)
    right_v1 = nested_v1(right)
    semantic_left = set(left_founder.get("semantic_miss_cases") or [])
    semantic_right = set(right_founder.get("semantic_miss_cases") or [])
    output_left = set(left_founder.get("output_miss_cases") or [])
    output_right = set(right_founder.get("output_miss_cases") or [])
    selected_skills_left = set(left_founder.get("selected_skills") or [])
    selected_skills_right = set(right_founder.get("selected_skills") or [])
    fixture_left = left.get("fixture_signatures") or left_v1.get("fixture_signatures") or left_founder.get("fixture_signatures") or {}
    fixture_right = right.get("fixture_signatures") or right_v1.get("fixture_signatures") or right_founder.get("fixture_signatures") or {}
    return {
        "status_changed": left.get("status") != right.get("status"),
        "left_status": left.get("status"),
        "right_status": right.get("status"),
        "artifact_count": {
            "left": left.get("artifact_count"),
            "right": right.get("artifact_count"),
            "delta": numeric_delta(left.get("artifact_count"), right.get("artifact_count")),
        },
        "suite_status_changes": map_changes(left_v1.get("suite_statuses") or {}, right_v1.get("suite_statuses") or {}),
        "health_status_changes": map_changes(left_v1.get("health_statuses") or {}, right_v1.get("health_statuses") or {}),
        "case_status_changes": map_changes(left_founder.get("case_statuses") or {}, right_founder.get("case_statuses") or {}),
        "route_rule_changes": map_changes(left_founder.get("case_route_rules") or {}, right_founder.get("case_route_rules") or {}),
        "workflow_changes": map_changes(left_founder.get("case_workflows") or {}, right_founder.get("case_workflows") or {}),
        "semantic_miss_changes": set_diff(semantic_left, semantic_right),
        "output_miss_changes": set_diff(output_left, output_right),
        "selected_skill_changes": set_diff(selected_skills_left, selected_skills_right),
        "fixture_state_changes": fixture_state_changes(fixture_left, fixture_right),
        "classification_summary_delta": classification_delta(
            left.get("classification_summary") if isinstance(left.get("classification_summary"), dict) else {},
            right.get("classification_summary") if isinstance(right.get("classification_summary"), dict) else {},
        ),
        "candidate_changed": {
            "left": left.get("candidate_id"),
            "right": right.get("candidate_id"),
            "changed": left.get("candidate_id") != right.get("candidate_id"),
        }
        if left.get("candidate_id") or right.get("candidate_id")
        else {},
    }


def recommendations(diff: dict[str, Any]) -> list[str]:
    result: list[str] = []
    if diff.get("status_changed"):
        result.append("Status changed between reports; inspect failed suites before treating the newer run as stable.")
    if diff.get("fixture_state_changes"):
        result.append("Fixture state changed; verify the change is expected before running additional acceptance gates.")
    if diff.get("semantic_miss_changes", {}).get("added"):
        result.append("New semantic misses appeared; inspect the founder-field report case details and prompt refinements.")
    if diff.get("output_miss_changes", {}).get("added"):
        result.append("New output-contract misses appeared; inspect chat-visible FormatA rendering and artifact extraction.")
    if diff.get("route_rule_changes", {}).get("changed_count"):
        result.append("Route rule expectations changed; run the prompt matrix before live AnythingLLM validation.")
    if diff.get("suite_status_changes", {}).get("changed_count"):
        result.append("Suite status changed; compare stdout_tail/stderr_tail for the affected suite IDs.")
    if diff.get("classification_summary_delta"):
        result.append("Model portability failure classes changed; inspect classified_failures before changing model policy.")
    if not result:
        result.append("No material route, semantic, suite, classification, or fixture diff was detected.")
    return result


def run_artifact_diff(config: RunArtifactDiffConfig) -> dict[str, Any]:
    left_path = config.left_report_path.resolve()
    right_path = config.right_report_path.resolve()
    output_path = config.output_path or default_report_path(config.config_root.resolve())
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "run_artifact_diff",
        "status": "failed",
        "created_at": utc_timestamp(),
        "left": {"label": config.left_label, "report_path": str(left_path)},
        "right": {"label": config.right_label, "report_path": str(right_path)},
        "diff": {},
        "recommendations": [],
        "errors": [],
    }
    try:
        left_summary = extract_summary(load_json(left_path), source_path=left_path)
        right_summary = extract_summary(load_json(right_path), source_path=right_path)
        report["left"]["summary"] = left_summary
        report["right"]["summary"] = right_summary
        diff = build_diff(left_summary, right_summary)
        report["diff"] = diff
        report["recommendations"] = recommendations(diff)
        report["status"] = "passed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
