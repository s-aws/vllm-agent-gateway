"""Multi-repo baseline comparison dry-run validation for Phase 210."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.multi_repo_fixture_baseline_pack import (
    read_json_object,
    validate_policy as validate_phase209_policy,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    controller_run_record,
    json_request,
    run_id_from_text,
    text_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "multi_repo_baseline_comparison_policy"
EXPECTED_REPORT_KIND = "multi_repo_baseline_comparison_report"
EXPECTED_PHASE = 210
EXPECTED_BACKLOG_ID = "P0-M5-210"
EXPECTED_MILESTONE_ID = "M5"
DEFAULT_POLICY_PATH = Path("runtime") / "multi_repo_baseline_comparison_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase210" / "phase210-multi-repo-baseline-comparison-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase210" / "phase210-multi-repo-baseline-comparison-report.md"


class MultiRepoComparisonStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PREFLIGHT_PASSED = "preflight_passed"


@dataclass(frozen=True)
class MultiRepoBaselineComparisonConfig:
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


def git_status(target_root: str) -> str:
    if not (Path(target_root) / ".git").exists():
        raise RuntimeError(f"{target_root} is not a git repository")
    result = subprocess.run(
        ["git", "-C", target_root, "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_watch_paths(case: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for path in string_list(case.get("source_hints")) + string_list(case.get("test_hints")):
        if path not in values:
            values.append(path)
    return values


def fixture_state(case: dict[str, Any]) -> dict[str, Any]:
    target_root = str(case.get("target_root") or "")
    root = Path(target_root)
    if (root / ".git").exists():
        return {"mode": "git", "git_status": git_status(target_root)}

    hashes: dict[str, str] = {}
    for relative_path in fixture_watch_paths(case):
        path = root / relative_path
        if path.is_file():
            hashes[relative_path] = sha256_file(path)
    if not hashes:
        raise RuntimeError(f"{target_root} is not git-backed and has no existing source_hints or test_hints to hash")
    return {"mode": "path_hashes", "hashes": hashes}


def selected_cases(phase209_policy: dict[str, Any], config: MultiRepoBaselineComparisonConfig) -> list[dict[str, Any]]:
    cases = object_list(phase209_policy.get("cases"))
    if not config.case_ids:
        return cases
    wanted = set(config.case_ids)
    return [case for case in cases if case.get("case_id") in wanted]


def surfaces(config: MultiRepoBaselineComparisonConfig) -> list[str]:
    values: list[str] = []
    if config.include_gateway:
        values.append("gateway")
    if config.include_anythingllm:
        values.append("anythingllm")
    return values


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 210")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append("policy.required_surfaces must include gateway and anythingllm")
    if int(policy.get("minimum_case_count", 0)) < 5:
        errors.append("policy.minimum_case_count must be at least 5")
    if int(policy.get("minimum_response_count", 0)) < 10:
        errors.append("policy.minimum_response_count must be at least 10")
    for marker in ("Answer:", "Source mutation: false"):
        if marker not in string_list(policy.get("required_chat_markers")):
            errors.append(f"policy.required_chat_markers must include {marker!r}")
    boundary_text = " ".join(string_list(policy.get("required_no_repair_boundary"))).lower()
    for phrase in ("do not change", "do not commit or push", "classify misses"):
        if phrase not in boundary_text:
            errors.append(f"policy.required_no_repair_boundary must mention {phrase!r}")
    allowed_gap_classes = set(string_list(policy.get("allowed_gap_classes")))
    for required in ("none", "route_gap", "evidence_gap", "formatter_gap", "missing_skill_tool", "repo_shape_gap"):
        if required not in allowed_gap_classes:
            errors.append(f"policy.allowed_gap_classes must include {required}")
    phase209_policy_path = resolve_path(config_root, str(policy.get("phase209_policy_path") or ""))
    phase209_report_path = resolve_path(config_root, str(policy.get("phase209_report_path") or ""))
    phase209_policy: dict[str, Any] = {}
    phase209_report: dict[str, Any] = {}
    if not phase209_policy_path.is_file():
        errors.append(f"phase209 policy missing at {phase209_policy_path}")
    else:
        phase209_policy = read_json_object(phase209_policy_path)
        phase209_errors, _ = validate_phase209_policy(phase209_policy)
        if phase209_errors:
            errors.append("phase209 policy must pass before Phase 210: " + "; ".join(phase209_errors[:5]))
    if not phase209_report_path.is_file():
        errors.append(f"phase209 report missing at {phase209_report_path}")
    else:
        phase209_report = read_json_object(phase209_report_path)
        if phase209_report.get("status") != "passed":
            errors.append("phase209 report status must be passed")
        if dict_value(phase209_report.get("summary")).get("phase210_ready") is not True:
            errors.append("phase209 report summary.phase210_ready must be true")
    return errors, phase209_policy, phase209_report


def gateway_response(config: MultiRepoBaselineComparisonConfig, case: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": str(case.get("prompt") or "")}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    run_id = str(compact.get("run_id") or run_id_from_text(text))
    if run_id == "unknown":
        raise RuntimeError(
            "gateway response did not include a workflow-router run_id; "
            f"text_excerpt={text[:500]!r}; body_keys={sorted(body.keys())}"
        )
    return text, controller_run_record(config, run_id), run_id


def anythingllm_response(
    config: MultiRepoBaselineComparisonConfig,
    case: dict[str, Any],
    *,
    api_key: str,
) -> tuple[str, dict[str, Any], str]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": str(case.get("prompt") or ""),
            "mode": "chat",
            "sessionId": f"phase210-{case.get('case_id', 'case').lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError(
            "AnythingLLM response did not include a workflow-router run_id; "
            f"text_excerpt={text[:500]!r}; body_keys={sorted(body.keys())}"
        )
    return text, controller_run_record(config, run_id), run_id


def classify_gap(*, case: dict[str, Any], text: str, run_record: dict[str, Any], required_markers: list[str]) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    gap_classes: list[str] = []
    score = 100
    summary = dict_value(run_record.get("summary"))
    route_workflow = summary.get("selected_workflow")
    if run_record.get("status") != "completed" or summary.get("downstream_status") != "completed":
        errors.append("controller run did not complete")
        gap_classes.append("runtime_surface_gap")
        score -= 25
    if route_workflow != case.get("expected_workflow"):
        errors.append(f"selected_workflow expected {case.get('expected_workflow')!r} got {route_workflow!r}")
        gap_classes.append("route_gap")
        score -= 25
    for marker in required_markers:
        if marker not in text:
            errors.append(f"chat text missing marker {marker!r}")
            gap_classes.append("formatter_gap")
            score -= 10
    expected_paths = string_list(case.get("source_hints")) + string_list(case.get("test_hints"))
    visible_hits = [path for path in expected_paths if path in text]
    if not visible_hits:
        errors.append("chat text did not include any Phase 209 source_hints or test_hints")
        gap_classes.append("evidence_gap")
        score -= 20
    if summary.get("source_changed") is not False:
        errors.append("summary.source_changed must be false")
        gap_classes.append("runtime_surface_gap")
        score -= 20
    if "commit" in text.lower() and "s-aws/staterail" in text.lower() and "do not" not in text.lower():
        errors.append("chat text may imply committing to s-aws/staterail")
        gap_classes.append("formatter_gap")
        score -= 10
    if not gap_classes:
        gap_classes.append("none")
    return max(0, score), sorted(set(gap_classes)), errors


def run_live_case(
    config: MultiRepoBaselineComparisonConfig,
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    surface: str,
    api_key: str | None,
) -> dict[str, Any]:
    target_root = str(case.get("target_root") or "")
    before_state = fixture_state(case)
    try:
        if surface == "gateway":
            text, run_record, run_id = gateway_response(config, case)
        elif surface == "anythingllm":
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM Phase 210 validation")
            text, run_record, run_id = anythingllm_response(config, case, api_key=api_key)
        else:
            raise RuntimeError(f"unsupported surface {surface}")
        after_state = fixture_state(case)
        if after_state != before_state:
            raise RuntimeError(f"protected fixture state changed during live response for {target_root}")
        score, gap_classes, errors = classify_gap(
            case=case,
            text=text,
            run_record=run_record,
            required_markers=string_list(policy.get("required_chat_markers")),
        )
        status = "completed"
    except Exception as exc:  # noqa: BLE001 - report runtime comparison gaps instead of hiding them.
        text = ""
        run_record = {}
        run_id = "unknown"
        score = 0
        gap_classes = ["runtime_surface_gap"]
        errors = [str(exc)]
        status = "failed"
    return {
        "surface": surface,
        "case_id": case.get("case_id"),
        "category": case.get("category"),
        "prompt_family": case.get("prompt_family"),
        "target_root": target_root,
        "status": status if not errors else "gap_recorded",
        "score": score,
        "gap_classes": gap_classes,
        "errors": errors,
        "run_id": run_id,
        "selected_workflow": dict_value(run_record.get("summary")).get("selected_workflow") if run_record else None,
        "source_changed": dict_value(run_record.get("summary")).get("source_changed") if run_record else None,
        "chat_excerpt": text[:1200],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Multi-Repo Baseline Comparison",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Live: `{report.get('live')}`",
        f"- Response count: `{summary.get('response_count')}`",
        f"- Gap response count: `{summary.get('gap_response_count')}`",
        f"- Phase 211 ready: `{summary.get('phase211_ready')}`",
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


def validate_multi_repo_baseline_comparison(config: MultiRepoBaselineComparisonConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)
    errors, phase209_policy, _ = validate_policy(policy, config_root=config_root)
    cases = selected_cases(phase209_policy, config)
    selected_surfaces = surfaces(config)
    if not config.allow_partial and len(cases) < int(policy.get("minimum_case_count", 5)):
        errors.append("live closeout must include all Phase 209 cases")
    if not config.allow_partial and set(selected_surfaces) != set(string_list(policy.get("required_surfaces"))):
        errors.append("live closeout must include gateway and AnythingLLM")
    responses: list[dict[str, Any]] = []
    if config.live and not errors:
        api_key = os.environ.get(config.api_key_env)
        for surface in selected_surfaces:
            for case in cases:
                responses.append(run_live_case(config, policy=policy, case=case, surface=surface, api_key=api_key))
        if not config.allow_partial and len(responses) < int(policy.get("minimum_response_count", 10)):
            errors.append("live response count below policy.minimum_response_count")
    gap_responses = [item for item in responses if string_list(item.get("gap_classes")) != ["none"]]
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
        "errors": errors,
        "responses": responses,
        "summary": {
            "case_count": len(cases),
            "surface_count": len(selected_surfaces),
            "response_count": len(responses),
            "gap_response_count": len(gap_responses),
            "gap_classes": sorted({gap for response in responses for gap in string_list(response.get("gap_classes")) if gap != "none"}),
            "phase211_ready": status == MultiRepoComparisonStatus.PASSED.value,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_path, render_markdown_report(report))
    return report
