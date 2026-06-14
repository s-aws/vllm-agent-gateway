"""Phase 212 live multi-repo generalization rerun validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    MultiRepoComparisonStatus,
    dict_value,
    object_list,
    read_json_object,
    run_live_case,
    string_list,
    validate_policy as validate_phase210_policy_shape,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "multi_repo_live_generalization_rerun_policy"
EXPECTED_REPORT_KIND = "multi_repo_live_generalization_rerun_report"
EXPECTED_PHASE = 212
EXPECTED_BACKLOG_ID = "P0-M5-212"
EXPECTED_MILESTONE_ID = "M5"
DEFAULT_POLICY_PATH = Path("runtime") / "multi_repo_live_generalization_rerun_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase212" / "phase212-multi-repo-live-generalization-rerun-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase212" / "phase212-multi-repo-live-generalization-rerun-report.md"
DEFAULT_PREFLIGHT_OUTPUT_PATH = Path("runtime-state") / "phase212" / "phase212-multi-repo-live-generalization-rerun-preflight-report.json"
DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase212" / "phase212-multi-repo-live-generalization-rerun-preflight-report.md"


@dataclass(frozen=True)
class MultiRepoLiveGeneralizationRerunConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    include_gateway: bool = True
    include_anythingllm: bool = True
    live: bool = False
    allow_partial: bool = False
    case_ids: tuple[str, ...] = ()
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


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


def surfaces(config: MultiRepoLiveGeneralizationRerunConfig) -> list[str]:
    values: list[str] = []
    if config.include_gateway:
        values.append("gateway")
    if config.include_anythingllm:
        values.append("anythingllm")
    return values


def validate_case(case: dict[str, Any], *, prefix: str, required_roots: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(case.get("case_id"), str) or not case.get("case_id"):
        errors.append(f"{prefix}.case_id must be a non-empty string")
    if not isinstance(case.get("prompt"), str) or not case.get("prompt"):
        errors.append(f"{prefix}.prompt must be a non-empty string")
    if case.get("expected_workflow") != "code_investigation.plan":
        errors.append(f"{prefix}.expected_workflow must be code_investigation.plan")
    target_root = case.get("target_root")
    if target_root not in required_roots:
        errors.append(f"{prefix}.target_root must be one of required_target_roots")
    if not string_list(case.get("source_hints")):
        errors.append(f"{prefix}.source_hints must not be empty")
    if not string_list(case.get("test_hints")):
        errors.append(f"{prefix}.test_hints must not be empty")
    return errors


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 212")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append("policy.required_surfaces must include gateway and anythingllm")
    required_roots = set(string_list(policy.get("required_target_roots")))
    for required in (
        "/mnt/c/staterail_testing_repo_frozen_tmp.github",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
    ):
        if required not in required_roots:
            errors.append(f"policy.required_target_roots must include {required}")
    if int(policy.get("minimum_target_case_count", 0)) < 5:
        errors.append("policy.minimum_target_case_count must be at least 5")
    if int(policy.get("minimum_holdout_case_count", 0)) < 4:
        errors.append("policy.minimum_holdout_case_count must be at least 4")
    if int(policy.get("minimum_repository_count", 0)) < 3:
        errors.append("policy.minimum_repository_count must be at least 3")
    if int(policy.get("minimum_response_count", 0)) < 18:
        errors.append("policy.minimum_response_count must be at least 18")
    for marker in ("Answer:", "Source mutation: false"):
        if marker not in string_list(policy.get("required_chat_markers")):
            errors.append(f"policy.required_chat_markers must include {marker!r}")
    if set(string_list(policy.get("required_gap_classes_for_closeout"))) != {"none"}:
        errors.append("policy.required_gap_classes_for_closeout must be ['none']")

    phase209_policy_path = resolve_path(config_root, str(policy.get("phase209_policy_path") or ""))
    phase211_report_path = resolve_path(config_root, str(policy.get("phase211_report_path") or ""))
    phase209_policy: dict[str, Any] = {}
    phase211_report: dict[str, Any] = {}
    if not phase209_policy_path.is_file():
        errors.append(f"phase209 policy missing at {phase209_policy_path}")
    else:
        phase209_policy = read_json_object(phase209_policy_path)
        phase209_cases = object_list(phase209_policy.get("cases"))
        if len(phase209_cases) < int(policy.get("minimum_target_case_count", 5)):
            errors.append("phase209 policy does not contain enough target cases")
        for index, case in enumerate(phase209_cases):
            errors.extend(validate_case(case, prefix=f"phase209.cases[{index}]", required_roots=required_roots))
    if not phase211_report_path.is_file():
        errors.append(f"phase211 report missing at {phase211_report_path}")
    else:
        phase211_report = read_json_object(phase211_report_path)
        summary = dict_value(phase211_report.get("summary"))
        if phase211_report.get("status") != "passed":
            errors.append("phase211 report status must be passed")
        if summary.get("gap_response_count") != 0:
            errors.append("phase211 report summary.gap_response_count must be 0")
        if summary.get("phase211_ready") is not True:
            errors.append("phase211 report summary.phase211_ready must be true")

    holdouts = object_list(policy.get("holdout_cases"))
    if len(holdouts) < int(policy.get("minimum_holdout_case_count", 4)):
        errors.append("policy.holdout_cases below minimum_holdout_case_count")
    for index, case in enumerate(holdouts):
        errors.extend(validate_case(case, prefix=f"policy.holdout_cases[{index}]", required_roots=required_roots))
    target_roots = {str(case.get("target_root")) for case in object_list(phase209_policy.get("cases")) + holdouts}
    if len(target_roots & required_roots) < int(policy.get("minimum_repository_count", 3)):
        errors.append("combined cases must cover minimum_repository_count required roots")
    return errors, phase209_policy, phase211_report


def selected_cases(
    phase209_policy: dict[str, Any],
    policy: dict[str, Any],
    config: MultiRepoLiveGeneralizationRerunConfig,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case in object_list(phase209_policy.get("cases")):
        item = dict(case)
        item["case_type"] = "target"
        cases.append(item)
    for case in object_list(policy.get("holdout_cases")):
        item = dict(case)
        item["case_type"] = "holdout"
        cases.append(item)
    if not config.case_ids:
        return cases
    wanted = set(config.case_ids)
    return [case for case in cases if case.get("case_id") in wanted]


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Multi-Repo Live Generalization Rerun",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Live: `{report.get('live')}`",
        f"- Case count: `{summary.get('case_count')}`",
        f"- Holdout count: `{summary.get('holdout_case_count')}`",
        f"- Response count: `{summary.get('response_count')}`",
        f"- Gap response count: `{summary.get('gap_response_count')}`",
        f"- Phase 213 ready: `{summary.get('phase213_ready')}`",
        "",
        "## Responses",
    ]
    for response in object_list(report.get("responses")):
        lines.append(
            f"- `{response.get('surface')}` `{response.get('case_id')}` "
            f"score=`{response.get('score')}` gaps=`{','.join(string_list(response.get('gap_classes')))}` "
            f"run=`{response.get('run_id')}`"
        )
        for error in string_list(response.get("errors")):
            lines.append(f"  - {error}")
    if string_list(report.get("errors")):
        lines.extend(["", "## Errors"])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"


def validate_multi_repo_live_generalization_rerun(config: MultiRepoLiveGeneralizationRerunConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_value = (
        DEFAULT_PREFLIGHT_OUTPUT_PATH
        if not config.live and config.output_path == DEFAULT_OUTPUT_PATH
        else config.output_path
    )
    markdown_value = (
        DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH
        if not config.live and config.markdown_output_path == DEFAULT_MARKDOWN_OUTPUT_PATH
        else config.markdown_output_path
    )
    output_path = resolve_path(config_root, output_value)
    markdown_path = resolve_path(config_root, markdown_value)
    policy = read_json_object(policy_path)
    errors, phase209_policy, phase211_report = validate_policy(policy, config_root=config_root)
    phase210_shape_errors, _, _ = validate_phase210_policy_shape(
        {
            "schema_version": 1,
            "kind": "multi_repo_baseline_comparison_policy",
            "phase": 210,
            "priority_backlog_id": "P0-M5-210",
            "milestone_id": "M5",
            "required_surfaces": policy.get("required_surfaces"),
            "minimum_case_count": policy.get("minimum_target_case_count"),
            "minimum_response_count": 10,
            "required_chat_markers": policy.get("required_chat_markers"),
            "required_no_repair_boundary": [
                "do not change router/controller/workflow/skill/formatter behavior",
                "do not commit or push to s-aws/staterail",
                "classify misses before repairs",
            ],
            "allowed_gap_classes": [
                "none",
                "route_gap",
                "evidence_gap",
                "formatter_gap",
                "missing_skill_tool",
                "repo_shape_gap",
            ],
            "phase209_policy_path": policy.get("phase209_policy_path"),
            "phase209_report_path": "runtime-state/phase209/phase209-multi-repo-fixture-baseline-pack-report.json",
        },
        config_root=config_root,
    )
    errors.extend(f"phase210_shape.{error}" for error in phase210_shape_errors)
    cases = selected_cases(phase209_policy, policy, config)
    selected_surfaces = surfaces(config)
    if not config.allow_partial and len(cases) < int(policy.get("minimum_target_case_count", 5)) + int(policy.get("minimum_holdout_case_count", 4)):
        errors.append("live closeout must include target cases plus holdouts")
    if not config.allow_partial and set(selected_surfaces) != set(string_list(policy.get("required_surfaces"))):
        errors.append("live closeout must include gateway and AnythingLLM")
    responses: list[dict[str, Any]] = []
    if config.live and not errors:
        api_key = os.environ.get(config.api_key_env)
        for surface in selected_surfaces:
            for case in cases:
                responses.append(run_live_case(config, policy=policy, case=case, surface=surface, api_key=api_key))
        if not config.allow_partial and len(responses) < int(policy.get("minimum_response_count", 18)):
            errors.append("live response count below policy.minimum_response_count")
    gap_responses = [item for item in responses if string_list(item.get("gap_classes")) != ["none"]]
    low_score_responses = [
        item
        for item in responses
        if isinstance(item.get("score"), int) and item.get("score") < int(policy.get("minimum_score_for_pass", 80))
    ]
    if config.live and not config.allow_partial:
        if gap_responses:
            errors.append("live closeout found gap responses")
        if low_score_responses:
            errors.append("live closeout found responses below minimum_score_for_pass")
    status = MultiRepoComparisonStatus.FAILED.value
    if not errors and not config.live:
        status = MultiRepoComparisonStatus.PREFLIGHT_PASSED.value
    elif not errors:
        status = MultiRepoComparisonStatus.PASSED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "live": config.live,
        "policy_path": str(policy_path),
        "phase211_report_status": phase211_report.get("status"),
        "errors": errors,
        "responses": responses,
        "summary": {
            "case_count": len(cases),
            "target_case_count": len([case for case in cases if case.get("case_type") == "target"]),
            "holdout_case_count": len([case for case in cases if case.get("case_type") == "holdout"]),
            "surface_count": len(selected_surfaces),
            "repository_count": len({case.get("target_root") for case in cases}),
            "response_count": len(responses),
            "gap_response_count": len(gap_responses),
            "gap_classes": sorted({gap for response in responses for gap in string_list(response.get("gap_classes")) if gap != "none"}),
            "low_score_response_count": len(low_score_responses),
            "phase213_ready": status == MultiRepoComparisonStatus.PASSED.value,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_path, render_markdown_report(report))
    return report
