"""Phase 157 founder field-test round governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "founder_field_round1_policy"
EXPECTED_REPORT_KIND = "founder_field_round1_report"
EXPECTED_SOURCE_KIND = "founder_field_prompt_evaluation"
EXPECTED_PHASE = 157
EXPECTED_BACKLOG_ID = "P0-BB-021"
DEFAULT_POLICY_PATH = Path("runtime") / "founder_field_round1_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "founder-field-round1" / "phase157"
DEFAULT_FIELD_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase157-founder-field-run.json"
DEFAULT_FIELD_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase157-founder-field-run.md"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase157-founder-field-round1-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase157-founder-field-round1-report.md"
REQUIRED_LIMITATIONS = {
    "not_advanced_broad_refactor_orchestration",
    "not_direct_mutation_of_protected_fixtures",
    "not_unsupported_output_format_parity",
    "not_automatic_model_selection",
}


class FounderFieldRound1Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FounderFieldRound1QualityStatus(str, Enum):
    PASSED = "passed"
    ADVISORY = "advisory"
    FAILED = "failed"


@dataclass(frozen=True)
class FounderFieldRound1Config:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    field_report_path: Path = DEFAULT_FIELD_REPORT_PATH
    output_path: Path = DEFAULT_REPORT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_PATH


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


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 157")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("existing_runner_script") != "scripts/run_founder_field_prompt_eval.py":
        errors.append("policy.existing_runner_script must use the existing founder field runner")
    min_case_count = policy.get("min_case_count")
    max_case_count = policy.get("max_case_count")
    if not isinstance(min_case_count, int) or min_case_count < 20:
        errors.append("policy.min_case_count must be an integer >= 20")
    if not isinstance(max_case_count, int) or max_case_count > 30:
        errors.append("policy.max_case_count must be an integer <= 30")
    case_ids = string_list(policy.get("required_case_ids"))
    if len(case_ids) != len(set(case_ids)):
        errors.append("policy.required_case_ids must be unique")
    if isinstance(min_case_count, int) and len(case_ids) < min_case_count:
        errors.append("policy.required_case_ids must meet min_case_count")
    if isinstance(max_case_count, int) and len(case_ids) > max_case_count:
        errors.append("policy.required_case_ids must not exceed max_case_count")
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append("policy.required_target_roots must include both frozen Coinbase fixtures")
    if not string_list(policy.get("required_workflows")):
        errors.append("policy.required_workflows must be a non-empty list")
    if not string_list(policy.get("required_skill_ids")):
        errors.append("policy.required_skill_ids must be a non-empty list")
    if set(string_list(policy.get("allowed_case_statuses"))) != {"passed", "failed"}:
        errors.append("policy.allowed_case_statuses must be passed and failed")
    if set(string_list(policy.get("allowed_quality_classifications"))) != {"pass", "advisory", "blocker"}:
        errors.append("policy.allowed_quality_classifications must be pass, advisory, and blocker")
    if set(string_list(policy.get("release_limitations"))) != REQUIRED_LIMITATIONS:
        errors.append("policy.release_limitations must preserve governed release limitations")
    return errors


def quality_classification(case: dict[str, Any]) -> str:
    if case.get("status") != FounderFieldRound1Status.PASSED.value:
        return "blocker"
    if isinstance(case.get("prompt_risk"), str) and case["prompt_risk"].strip():
        return "advisory"
    return "pass"


def case_evidence(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "target_root": case.get("target_root"),
        "prompt_sha256": hashlib.sha256(str(case.get("prompt", "")).encode("utf-8")).hexdigest(),
        "expected_workflow": case.get("expected_workflow"),
        "expected_skill_id": case.get("expected_skill_id") or "",
        "expected_artifact_key": case.get("expected_artifact_key") or "",
        "status": case.get("status"),
        "quality_classification": quality_classification(case),
        "output_contract_status": case.get("output_contract_status"),
        "semantic_quality_status": case.get("semantic_quality_status"),
        "run_id": case.get("run_id"),
        "text_sha256": case.get("text_sha256"),
        "initial_difference": case.get("initial_difference"),
        "suggested_prompt_if_missed": case.get("suggested_prompt_if_missed") or "",
        "prompt_risk": case.get("prompt_risk") or "",
    }


def validation_errors_for_source(policy: dict[str, Any], source_report: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    policy_errors = validate_policy(policy)
    errors.extend(
        {
            "id": f"policy.{index}",
            "source": "policy",
            "severity": "high",
            "message": error,
        }
        for index, error in enumerate(policy_errors)
    )
    if source_report.get("kind") != EXPECTED_SOURCE_KIND:
        errors.append(
            {
                "id": "source.kind",
                "source": "field_report",
                "severity": "high",
                "message": f"field report kind must be {EXPECTED_SOURCE_KIND}",
            }
        )
    if source_report.get("anythingllm_preflight", {}).get("status") != FounderFieldRound1Status.PASSED.value:
        errors.append(
            {
                "id": "source.anythingllm_preflight",
                "source": "field_report",
                "severity": "high",
                "message": "AnythingLLM preflight must pass",
            }
        )
    if object_list(source_report.get("errors")) or string_list(source_report.get("errors")):
        errors.append(
            {
                "id": "source.errors",
                "source": "field_report",
                "severity": "high",
                "message": "field report errors must be empty",
            }
        )
    cases = object_list(source_report.get("cases"))
    case_ids = [str(case.get("case_id")) for case in cases if isinstance(case.get("case_id"), str)]
    required_case_ids = string_list(policy.get("required_case_ids"))
    if set(case_ids) != set(required_case_ids):
        errors.append(
            {
                "id": "source.case_ids",
                "source": "field_report",
                "severity": "high",
                "message": "field report case IDs must match the Phase 157 policy",
            }
        )
    if len(case_ids) != len(set(case_ids)):
        errors.append(
            {
                "id": "source.duplicate_case_ids",
                "source": "field_report",
                "severity": "high",
                "message": "field report case IDs must be unique",
            }
        )
    min_case_count = policy.get("min_case_count")
    max_case_count = policy.get("max_case_count")
    if isinstance(min_case_count, int) and len(cases) < min_case_count:
        errors.append(
            {
                "id": "source.too_few_cases",
                "source": "field_report",
                "severity": "high",
                "message": "field report has fewer than the required Phase 157 cases",
            }
        )
    if isinstance(max_case_count, int) and len(cases) > max_case_count:
        errors.append(
            {
                "id": "source.too_many_cases",
                "source": "field_report",
                "severity": "high",
                "message": "field report has more than the allowed Phase 157 cases",
            }
        )
    target_roots = {str(case.get("target_root")) for case in cases if isinstance(case.get("target_root"), str)}
    if target_roots != set(string_list(policy.get("required_target_roots"))):
        errors.append(
            {
                "id": "source.target_roots",
                "source": "field_report",
                "severity": "high",
                "message": "field report must cover both frozen Coinbase fixtures and no other roots",
            }
        )
    workflows = {str(case.get("expected_workflow")) for case in cases if isinstance(case.get("expected_workflow"), str)}
    missing_workflows = sorted(set(string_list(policy.get("required_workflows"))) - workflows)
    if missing_workflows:
        errors.append(
            {
                "id": "source.required_workflows",
                "source": "field_report",
                "severity": "medium",
                "message": "field report missing required workflow coverage: " + ", ".join(missing_workflows),
            }
        )
    skills = {str(case.get("expected_skill_id")) for case in cases if isinstance(case.get("expected_skill_id"), str) and case.get("expected_skill_id")}
    missing_skills = sorted(set(string_list(policy.get("required_skill_ids"))) - skills)
    if missing_skills:
        errors.append(
            {
                "id": "source.required_skills",
                "source": "field_report",
                "severity": "medium",
                "message": "field report missing required skill coverage: " + ", ".join(missing_skills),
            }
        )
    allowed_statuses = set(string_list(policy.get("allowed_case_statuses")))
    for index, case in enumerate(cases):
        prefix = f"source.cases[{index}]"
        if case.get("status") not in allowed_statuses:
            errors.append(
                {
                    "id": f"{prefix}.status",
                    "source": "field_report",
                    "severity": "high",
                    "message": "case status must be passed or failed",
                }
            )
        for key in ("case_id", "target_root", "prompt", "expected_workflow", "run_id", "initial_difference"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                errors.append(
                    {
                        "id": f"{prefix}.{key}",
                        "source": "field_report",
                        "severity": "high",
                        "message": f"case {key} must be a non-empty string",
                    }
                )
        if case.get("run_id") == "unknown":
            errors.append(
                {
                    "id": f"{prefix}.run_id_unknown",
                    "source": "field_report",
                    "severity": "high",
                    "message": "case run_id must be captured from chat output",
                }
            )
        if not isinstance(case.get("text_sha256"), str) or len(str(case.get("text_sha256"))) != 64:
            errors.append(
                {
                    "id": f"{prefix}.text_sha256",
                    "source": "field_report",
                    "severity": "medium",
                    "message": "case text_sha256 must be present",
                }
            )
    before = dict_value(source_report.get("fixture_state_before"))
    after = dict_value(source_report.get("fixture_state_after"))
    if not before or not after:
        errors.append(
            {
                "id": "source.fixture_state_missing",
                "source": "field_report",
                "severity": "high",
                "message": "fixture state before and after must be present",
            }
        )
    elif before != after:
        errors.append(
            {
                "id": "source.fixture_state_changed",
                "source": "field_report",
                "severity": "high",
                "message": "protected fixture state changed during field test",
            }
        )
    return errors


def build_founder_field_round1_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    source_report: dict[str, Any],
    policy_path: Path | None = None,
    field_report_path: Path | None = None,
) -> dict[str, Any]:
    case_records = [case_evidence(case) for case in object_list(source_report.get("cases"))]
    blockers = validation_errors_for_source(policy, source_report)
    pass_count = sum(1 for case in case_records if case["quality_classification"] == "pass")
    advisory_count = sum(1 for case in case_records if case["quality_classification"] == "advisory")
    blocker_count = sum(1 for case in case_records if case["quality_classification"] == "blocker")
    if blocker_count:
        quality_status = FounderFieldRound1QualityStatus.FAILED.value
    elif advisory_count:
        quality_status = FounderFieldRound1QualityStatus.ADVISORY.value
    else:
        quality_status = FounderFieldRound1QualityStatus.PASSED.value
    target_roots = sorted({case["target_root"] for case in case_records if isinstance(case.get("target_root"), str)})
    workflows = sorted({case["expected_workflow"] for case in case_records if isinstance(case.get("expected_workflow"), str)})
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderFieldRound1Status.PASSED.value if not blockers else FounderFieldRound1Status.FAILED.value,
        "quality_status": quality_status,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path),
        "field_report_path": str(field_report_path) if field_report_path else None,
        "field_report_sha256": artifact_hash(field_report_path),
        "release_limitations": string_list(policy.get("release_limitations")),
        "phase158_required": advisory_count > 0 or blocker_count > 0,
        "case_results": case_records,
        "validation_errors": blockers,
        "summary": {
            "case_count": len(case_records),
            "pass_case_count": pass_count,
            "advisory_case_count": advisory_count,
            "blocker_case_count": blocker_count,
            "target_root_count": len(target_roots),
            "target_roots": target_roots,
            "workflow_count": len(workflows),
            "workflows": workflows,
            "phase158_required": advisory_count > 0 or blocker_count > 0,
            "source_status": source_report.get("status"),
            "source_passed": dict_value(source_report.get("summary")).get("passed"),
            "source_failed": dict_value(source_report.get("summary")).get("failed"),
        },
    }
    return report


def stable_view(report: dict[str, Any]) -> dict[str, Any]:
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
            "field_report_path",
            "field_report_sha256",
            "release_limitations",
            "phase158_required",
            "case_results",
            "validation_errors",
            "summary",
        )
    }


def validate_founder_field_round1_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    source_report: dict[str, Any],
    policy_path: Path | None = None,
    field_report_path: Path | None = None,
) -> list[str]:
    expected = build_founder_field_round1_report(
        config_root=config_root,
        policy=policy,
        source_report=source_report,
        policy_path=policy_path,
        field_report_path=field_report_path,
    )
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt founder field round 1 report"]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Founder Field Round 1",
        "",
        f"- Status: {report.get('status')}",
        f"- Quality status: {report.get('quality_status')}",
        f"- Case count: {report.get('summary', {}).get('case_count')}",
        f"- Pass cases: {report.get('summary', {}).get('pass_case_count')}",
        f"- Advisory cases: {report.get('summary', {}).get('advisory_case_count')}",
        f"- Blocker cases: {report.get('summary', {}).get('blocker_case_count')}",
        f"- Phase 158 required: {report.get('phase158_required')}",
        "",
        "## Cases",
        "",
        "| Case | Root | Workflow | Quality | Run ID | Initial Difference |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in object_list(report.get("case_results")):
        difference = str(case.get("initial_difference", "")).replace("\n", " ")[:400]
        lines.append(
            "| {case_id} | {target_root} | {workflow} | {quality} | {run_id} | {difference} |".format(
                case_id=case.get("case_id"),
                target_root=case.get("target_root"),
                workflow=case.get("expected_workflow"),
                quality=case.get("quality_classification"),
                run_id=case.get("run_id"),
                difference=difference,
            )
        )
    lines.extend(["", "## Validation Errors", ""])
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- {item.get('id')}: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    lines.extend(["", "## Release Limitations", ""])
    lines.extend(f"- {item}" for item in string_list(report.get("release_limitations")))
    return "\n".join(lines).rstrip() + "\n"


def run_founder_field_round1(config: FounderFieldRound1Config) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    field_report_path = resolve_path(config_root, config.field_report_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path) if config.markdown_output_path else None
    policy = read_json_object(policy_path)
    source_report = read_json_object(field_report_path)
    report = build_founder_field_round1_report(
        config_root=config_root,
        policy=policy,
        source_report=source_report,
        policy_path=policy_path,
        field_report_path=field_report_path,
    )
    validation_errors = validate_founder_field_round1_report(
        report,
        config_root=config_root,
        policy=policy,
        source_report=source_report,
        policy_path=policy_path,
        field_report_path=field_report_path,
    )
    if validation_errors:
        report["status"] = FounderFieldRound1Status.FAILED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "founder_field_round1",
                    "severity": "high",
                    "message": error,
                }
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
    return report
