"""Phase 197 founder trial execution round validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "founder_trial_execution_round_policy"
EXPECTED_REPORT_KIND = "founder_trial_execution_round_report"
EXPECTED_FIELD_KIND = "founder_field_prompt_evaluation"
EXPECTED_PHASE = 197
EXPECTED_BACKLOG_ID = "P0-BB-061"
DEFAULT_POLICY_PATH = Path("runtime") / "founder_trial_execution_round_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase197" / "phase197-founder-trial-execution-round-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase197" / "phase197-founder-trial-execution-round-report.md"


class FounderTrialExecutionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FounderTrialQualityStatus(str, Enum):
    PASSED = "passed"
    ADVISORY = "advisory"
    FAILED = "failed"


@dataclass(frozen=True)
class FounderTrialExecutionRoundConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def required_case_ids(policy: dict[str, Any]) -> list[str]:
    stage_cases = dict_value(policy.get("required_case_ids_by_stage"))
    return [
        case_id
        for stage_id in ("founder-smoke", "expanded-read-only")
        for case_id in string_list(stage_cases.get(stage_id))
    ]


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 197"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("existing_runner_script") != "scripts/run_founder_field_prompt_eval.py":
        errors.append(validation_error("policy.existing_runner_script", "Phase 197 must use the existing founder field runner"))
    case_ids = required_case_ids(policy)
    if len(case_ids) != 14 or len(case_ids) != len(set(case_ids)):
        errors.append(validation_error("policy.required_case_ids_by_stage", "Phase 197 must declare 14 unique trial case IDs"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "Phase 197 must cover both frozen Coinbase fixtures"))
    if policy.get("required_route_surface") != "anythingllm_via_workflow_router_gateway":
        errors.append(validation_error("policy.required_route_surface", "Phase 197 must run through AnythingLLM via workflow-router gateway"))
    anythingllm = dict_value(policy.get("required_anythingllm"))
    if anythingllm.get("api_base_url") != "http://127.0.0.1:3001" or anythingllm.get("workspace") != "my-workspace":
        errors.append(validation_error("policy.required_anythingllm", "AnythingLLM API base URL and workspace must match the governed local setup"))
    if set(string_list(policy.get("allowed_quality_classifications"))) != {"pass", "advisory", "blocker"}:
        errors.append(validation_error("policy.allowed_quality_classifications", "allowed quality classifications must be pass/advisory/blocker"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    if policy.get("acceptance_marker") != "PHASE197 FOUNDER TRIAL EXECUTION ROUND PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 197"))
    return errors


def validate_required_report(report: dict[str, Any], policy_item: dict[str, Any], source: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if report.get("kind") != policy_item.get("expected_kind"):
        errors.append(validation_error(f"{source}.kind", f"{source} kind must be {policy_item.get('expected_kind')}", source=source))
    if report.get("status") != policy_item.get("expected_status"):
        errors.append(validation_error(f"{source}.status", f"{source} status must be {policy_item.get('expected_status')}", source=source))
    if report.get("phase") != policy_item.get("expected_phase"):
        errors.append(validation_error(f"{source}.phase", f"{source} phase must be {policy_item.get('expected_phase')}", source=source))
    expected_recommendation = policy_item.get("expected_recommendation")
    if isinstance(expected_recommendation, str) and report.get("recommendation") != expected_recommendation:
        errors.append(validation_error(f"{source}.recommendation", f"{source} recommendation must be {expected_recommendation}", source=source))
    if dict_value(report.get("summary")).get("validation_error_count") not in (None, 0):
        errors.append(validation_error(f"{source}.validation_error_count", f"{source} validation_error_count must be 0", source=source))
    return errors


def validate_response_artifact(config_root: Path, case: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    raw_path = case.get("response_artifact_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return [validation_error(f"{prefix}.response_artifact_path", "case must include response_artifact_path", source="field_report")]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        return [validation_error(f"{prefix}.response_artifact_missing", "case response artifact must exist", source="field_report")]
    actual_hash = sha256_file(path)
    if case.get("response_artifact_sha256") != actual_hash:
        errors.append(validation_error(f"{prefix}.response_artifact_hash", "response artifact hash mismatch", source="field_report"))
    if case.get("text_sha256") != actual_hash:
        errors.append(validation_error(f"{prefix}.text_hash", "text_sha256 must match full response artifact hash", source="field_report"))
    if not isinstance(case.get("response_artifact_bytes"), int) or case["response_artifact_bytes"] != path.stat().st_size:
        errors.append(validation_error(f"{prefix}.response_artifact_bytes", "response_artifact_bytes must match file size", source="field_report"))
    return errors


def quality_classification(case: dict[str, Any]) -> str:
    if case.get("status") != "passed" or case.get("output_contract_status") != "passed" or case.get("semantic_quality_status") != "passed":
        return "blocker"
    if str(case.get("prompt_risk") or "").strip() or str(case.get("suggested_prompt_if_missed") or "").strip():
        return "advisory"
    return "pass"


def case_record(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "target_root": case.get("target_root"),
        "prompt": case.get("prompt"),
        "expected_workflow": case.get("expected_workflow"),
        "status": case.get("status"),
        "quality_classification": quality_classification(case),
        "output_contract_status": case.get("output_contract_status"),
        "semantic_quality_status": case.get("semantic_quality_status"),
        "route_surface": case.get("route_surface"),
        "run_id": case.get("run_id"),
        "initial_difference": case.get("initial_difference"),
        "suggested_prompt_if_missed": case.get("suggested_prompt_if_missed") or "",
        "prompt_risk": case.get("prompt_risk") or "",
        "response_artifact_path": case.get("response_artifact_path"),
        "response_artifact_sha256": case.get("response_artifact_sha256"),
    }


def validate_field_report(config_root: Path, policy: dict[str, Any], field_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if field_report.get("kind") != EXPECTED_FIELD_KIND:
        errors.append(validation_error("field.kind", f"field report kind must be {EXPECTED_FIELD_KIND}", source="field_report"))
    if dict_value(field_report.get("anythingllm_preflight")).get("status") != "passed":
        errors.append(validation_error("field.anythingllm_preflight", "AnythingLLM preflight must pass", source="field_report"))
    if object_list(field_report.get("errors")) or string_list(field_report.get("errors")):
        errors.append(validation_error("field.errors", "field report errors must be empty", source="field_report"))
    if field_report.get("fixture_state_before") != field_report.get("fixture_state_after"):
        errors.append(validation_error("field.fixture_state_changed", "field trial changed protected fixture state", "critical", "field_report"))
    cases = object_list(field_report.get("cases"))
    case_ids = [str(case.get("case_id")) for case in cases if isinstance(case.get("case_id"), str)]
    expected_case_ids = required_case_ids(policy)
    if case_ids != expected_case_ids:
        errors.append(validation_error("field.case_ids", "field case IDs must match Phase 195 trial pack order", source="field_report"))
    target_roots = {str(case.get("target_root")) for case in cases if isinstance(case.get("target_root"), str)}
    if target_roots != set(string_list(policy.get("required_target_roots"))):
        errors.append(validation_error("field.target_roots", "field report must cover both frozen Coinbase fixture roots", source="field_report"))
    for index, case in enumerate(cases):
        prefix = f"field.cases[{index}]"
        if case.get("route_surface") != policy.get("required_route_surface"):
            errors.append(validation_error(f"{prefix}.route_surface", "case must run through AnythingLLM via workflow-router gateway", source="field_report"))
        if not isinstance(case.get("run_id"), str) or not str(case["run_id"]).startswith("workflow-router-"):
            errors.append(validation_error(f"{prefix}.run_id", "case must include workflow-router run_id", source="field_report"))
        errors.extend(validate_response_artifact(config_root, case, prefix))
    return errors


def load_sources(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    sources: dict[str, tuple[Path, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    source_specs = {
        "trial_pack": dict_value(policy.get("required_trial_pack_report")),
        "readiness": dict_value(policy.get("required_readiness_report")),
        "field_report": {"path": policy.get("field_report_path")},
    }
    for source_id, spec in source_specs.items():
        raw_path = spec.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(validation_error(f"{source_id}.path", f"{source_id} path is required", source=source_id))
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            errors.append(validation_error(f"{source_id}.missing", f"{source_id} report is missing: {raw_path}", source=source_id))
            sources[source_id] = (path, {})
            continue
        try:
            sources[source_id] = (path, read_json_object(path))
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            errors.append(validation_error(f"{source_id}.malformed", f"{source_id} report is malformed: {type(exc).__name__}: {exc}", source=source_id))
            sources[source_id] = (path, {})
    return sources, errors


def source_ref(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            errors.append(validation_error(f"doc_missing.{raw_path}", f"required doc is missing: {raw_path}", "medium", "documentation"))
    return docs, errors


def build_founder_trial_execution_round_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path, dict[str, Any]]],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    errors.extend(validate_policy(policy))
    errors.extend(source_load_errors)
    trial_path, trial_pack = sources.get("trial_pack", (Path("missing"), {}))
    readiness_path, readiness = sources.get("readiness", (Path("missing"), {}))
    field_path, field_report = sources.get("field_report", (Path("missing"), {}))
    errors.extend(validate_required_report(trial_pack, dict_value(policy.get("required_trial_pack_report")), "trial_pack"))
    errors.extend(validate_required_report(readiness, dict_value(policy.get("required_readiness_report")), "readiness"))
    errors.extend(validate_field_report(config_root, policy, field_report))
    docs, doc_errors = doc_records(config_root, policy)
    errors.extend(doc_errors)
    cases = [case_record(case) for case in object_list(field_report.get("cases"))]
    classification_counts = {
        "pass": sum(1 for item in cases if item.get("quality_classification") == "pass"),
        "advisory": sum(1 for item in cases if item.get("quality_classification") == "advisory"),
        "blocker": sum(1 for item in cases if item.get("quality_classification") == "blocker"),
    }
    if classification_counts["blocker"]:
        quality_status = FounderTrialQualityStatus.FAILED.value
    elif classification_counts["advisory"]:
        quality_status = FounderTrialQualityStatus.ADVISORY.value
    else:
        quality_status = FounderTrialQualityStatus.PASSED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderTrialExecutionStatus.FAILED.value if errors else FounderTrialExecutionStatus.PASSED.value,
        "quality_status": quality_status,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "source_refs": {
            "trial_pack": source_ref(trial_path, trial_pack),
            "readiness": source_ref(readiness_path, readiness),
            "field_report": source_ref(field_path, field_report),
        },
        "case_results": cases,
        "docs": docs,
        "validation_errors": errors,
        "summary": {
            "case_count": len(cases),
            "classification_counts": classification_counts,
            "target_roots": sorted({str(item.get("target_root")) for item in cases if item.get("target_root")}),
            "validation_error_count": len(errors),
            "phase198_required": classification_counts["advisory"] > 0 or classification_counts["blocker"] > 0,
            "next_action": "work Phase 198 feedback intake and repair proposal"
            if classification_counts["advisory"] or classification_counts["blocker"]
            else "work Phase 199 V1 beta release closeout",
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
            "status",
            "quality_status",
            "policy_path",
            "policy_sha256",
            "source_refs",
            "case_results",
            "docs",
            "validation_errors",
            "summary",
        )
    }


def validate_founder_trial_execution_round_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path, dict[str, Any]]],
    source_load_errors: list[dict[str, str]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_founder_trial_execution_round_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt founder trial execution round"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 197 Founder Trial Execution Round",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Quality status: `{report.get('quality_status')}`",
        f"- Cases: `{summary.get('case_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Cases",
        "",
        "| Case | Classification | Status | Workflow | Run ID | Difference |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in object_list(report.get("case_results")):
        difference = str(item.get("initial_difference") or "").replace("\n", " ")[:300]
        lines.append(
            f"| `{item.get('case_id')}` | `{item.get('quality_classification')}` | `{item.get('status')}` | `{item.get('expected_workflow')}` | `{item.get('run_id')}` | {difference} |"
        )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    return "\n".join(lines) + "\n"


def run_founder_trial_execution_round(config: FounderTrialExecutionRoundConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, source_load_errors = load_sources(config_root, policy)
    report = build_founder_trial_execution_round_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_founder_trial_execution_round_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        source_load_errors=source_load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = FounderTrialExecutionStatus.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "founder_trial_execution_round")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
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
