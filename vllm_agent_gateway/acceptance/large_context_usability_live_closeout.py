"""Phase 221 large-context usability live closeout gate."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    dict_value,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    run_id_from_text,
    text_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_usability_live_closeout_policy"
EXPECTED_REPORT_KIND = "large_context_usability_live_closeout_report"
EXPECTED_PHASE = 221
EXPECTED_BACKLOG_ID = "P0-M6-221"
EXPECTED_MILESTONE_IDS = {"M6", "M8"}
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_usability_live_closeout_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase221" / "phase221-large-context-usability-live-closeout-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase221" / "phase221-large-context-usability-live-closeout-report.md"
DEFAULT_PREFLIGHT_OUTPUT_PATH = (
    Path("runtime-state") / "phase221" / "phase221-large-context-usability-live-closeout-preflight-report.json"
)
DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "phase221" / "phase221-large-context-usability-live-closeout-preflight-report.md"
)
REQUIRED_BASELINE_CATEGORIES = {
    "large_corpus_evidence_lookup",
    "large_corpus_navigation",
    "large_corpus_summarization",
    "large_corpus_limitations",
}
REQUIRED_SURFACES = {"gateway", "anythingllm"}


class LargeContextLiveCloseoutStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PREFLIGHT_PASSED = "preflight_passed"


@dataclass(frozen=True)
class LargeContextUsabilityLiveCloseoutConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
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
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def default_output_path(*, live: bool) -> Path:
    return DEFAULT_OUTPUT_PATH if live else DEFAULT_PREFLIGHT_OUTPUT_PATH


def default_markdown_output_path(*, live: bool) -> Path:
    return DEFAULT_MARKDOWN_OUTPUT_PATH if live else DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def bool_value(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def validation_error(error_id: str, message: str, *, source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "source": source, "message": message}


def selected_cases(policy: dict[str, Any], config: LargeContextUsabilityLiveCloseoutConfig) -> list[dict[str, Any]]:
    cases = object_list(policy.get("baseline_cases")) + object_list(policy.get("holdout_cases"))
    if not config.case_ids:
        return cases
    wanted = set(config.case_ids)
    return [case for case in cases if case.get("case_id") in wanted]


def selected_surfaces(config: LargeContextUsabilityLiveCloseoutConfig) -> list[str]:
    values: list[str] = []
    if config.include_gateway:
        values.append("gateway")
    if config.include_anythingllm:
        values.append("anythingllm")
    return values


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 221"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M6 and M8"))
    if set(string_list(policy.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must be gateway and anythingllm"))
    for key in ("target_root", "context_index_policy_path"):
        if not isinstance(policy.get(key), str) or not str(policy[key]).strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be non-empty"))
    precondition = dict_value(policy.get("phase220_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition[key]).strip():
            errors.append(validation_error(f"policy.phase220_precondition.{key}", f"{key} must be non-empty"))
    if precondition.get("required_phase221_ready") is not True:
        errors.append(validation_error("policy.phase220_precondition.required_phase221_ready", "required_phase221_ready must be true"))
    baseline_cases = object_list(policy.get("baseline_cases"))
    holdout_cases = object_list(policy.get("holdout_cases"))
    minimums = dict_value(policy.get("minimums"))
    if len(baseline_cases) < int_value(minimums.get("baseline_case_count"), 4):
        errors.append(validation_error("policy.baseline_cases", "not enough baseline cases"))
    if len(holdout_cases) < int_value(minimums.get("holdout_case_count"), 4):
        errors.append(validation_error("policy.holdout_cases", "not enough holdout cases"))
    categories = {str(case.get("category")) for case in baseline_cases}
    if not REQUIRED_BASELINE_CATEGORIES.issubset(categories):
        errors.append(validation_error("policy.baseline_cases.categories", "baseline cases must cover all four Phase 221 categories"))
    seen: set[str] = set()
    for case in baseline_cases + holdout_cases:
        case_id = str(case.get("case_id") or "")
        if not case_id:
            errors.append(validation_error("policy.case.case_id", "case_id must be non-empty"))
            continue
        if case_id in seen:
            errors.append(validation_error(f"policy.case.{case_id}", "duplicate case_id"))
        seen.add(case_id)
        for key in ("category", "prompt", "expected_strategy", "expected_execution_path"):
            if not isinstance(case.get(key), str) or not str(case[key]).strip():
                errors.append(validation_error(f"policy.case.{case_id}.{key}", f"{key} must be non-empty"))
        if not string_list(case.get("required_terms")):
            errors.append(validation_error(f"policy.case.{case_id}.required_terms", "required_terms must be non-empty"))
        if int_value(case.get("minimum_score"), 0) < int_value(minimums.get("minimum_response_score"), 85):
            errors.append(validation_error(f"policy.case.{case_id}.minimum_score", "minimum_score must meet policy minimum"))
    contract = dict_value(policy.get("answer_contract"))
    expected_contract = {
        "answer_first_required": True,
        "artifact_only_allowed": False,
        "raw_prompt_stuffing_allowed": False,
        "chat_visible_strategy_required": True,
        "source_hash_revalidation_required": True,
        "index_freshness_required": True,
    }
    for key, expected in expected_contract.items():
        if contract.get(key) is not expected:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be {expected}"))
    required_blind_keys = {
        "ideal_answer_shape",
        "must_have_facts",
        "evidence_expectations",
        "safety_boundaries",
        "scoring",
    }
    for case in baseline_cases:
        blind = dict_value(case.get("blind_baseline"))
        missing = sorted(key for key in required_blind_keys if not string_list(blind.get(key)))
        if missing:
            errors.append(validation_error(f"policy.case.{case.get('case_id')}.blind_baseline", f"missing blind baseline keys: {missing}"))
    if policy.get("acceptance_marker") != "PHASE221 LARGE CONTEXT USABILITY LIVE CLOSEOUT PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 221"))
    return errors


def load_report(
    config_root: Path,
    raw_path: object,
    *,
    source: str,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error(f"{source}.missing", f"{source} report is required", source=source)]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error(f"{source}.malformed", f"{source} report is malformed: {exc}", source=source)]


def validate_phase220_precondition(policy: dict[str, Any], phase220_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase220_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase220_precondition"))
    summary = dict_value(phase220_report.get("summary"))
    if phase220_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase220_report.status", "Phase 220 report status must be passed", source="phase220"))
    if summary.get("phase221_ready") is not precondition.get("required_phase221_ready"):
        errors.append(validation_error("phase220_report.phase221_ready", "Phase 220 must mark phase221_ready", source="phase220"))
    return errors


def case_prompt(case: dict[str, Any], target_root: Path) -> str:
    return str(case.get("prompt") or "").replace("{target_root}", str(target_root))


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str) or not path:
        return {}
    try:
        return read_json_object(Path(path))
    except (OSError, RuntimeError, json.JSONDecodeError):
        return {}


def source_hash_revalidation(target_root: Path, evidence_refs: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    checked = 0
    for ref in evidence_refs:
        relative_path = str(ref.get("source_path") or "")
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            errors.append(f"invalid source ref path {relative_path!r}")
            continue
        source_path = target_root / relative_path
        if not source_path.is_file():
            errors.append(f"source ref missing at {relative_path}")
            continue
        expected_sha = ref.get("source_sha256")
        if not isinstance(expected_sha, str) or not expected_sha:
            errors.append(f"source hash missing for {relative_path}")
            continue
        checked += 1
        if sha256_file(source_path) != expected_sha:
            errors.append(f"source hash mismatch for {relative_path}")
        if ref.get("freshness_status") != "fresh":
            errors.append(f"source ref not fresh for {relative_path}")
        for key in ("line_start", "line_end", "chunk_sha256"):
            if ref.get(key) in (None, ""):
                errors.append(f"source ref missing {key} for {relative_path}")
    return {"checked_count": checked, "errors": errors}


def artifact_contract_errors(artifact: dict[str, Any], case: dict[str, Any], target_root: Path) -> list[str]:
    errors: list[str] = []
    if artifact.get("status") != "answered":
        errors.append("retrieval artifact status must be answered")
    if dict_value(artifact.get("prompt_budget")).get("raw_prompt_stuffing") is not False:
        errors.append("retrieval artifact prompt_budget.raw_prompt_stuffing must be false")
    if artifact.get("source_text_retention") != "metadata_only":
        errors.append("retrieval artifact source_text_retention must be metadata_only")
    if artifact.get("store_source_text") is not False:
        errors.append("retrieval artifact store_source_text must be false")
    serialized = json.dumps(artifact, sort_keys=True)
    for forbidden in ('"source_text":', '"chunk_text":', '"snippet":', '"content":', "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE"):
        if forbidden in serialized:
            errors.append(f"retrieval artifact leaked forbidden field or marker {forbidden}")
    evidence_refs = object_list(artifact.get("evidence_refs"))
    if len(evidence_refs) < int_value(case.get("minimum_evidence_refs"), 0):
        errors.append("retrieval artifact evidence ref count below case minimum")
    hash_result = source_hash_revalidation(target_root, evidence_refs)
    errors.extend(string_list(hash_result.get("errors")))
    pages = dict_value(artifact.get("artifact_pages"))
    if int_value(case.get("minimum_page_count"), 0):
        if int_value(pages.get("page_count"), 0) < int_value(case.get("minimum_page_count"), 0):
            errors.append("artifact page count below case minimum")
        if int_value(pages.get("artifact_source_ref_count"), 0) < int_value(case.get("minimum_artifact_refs"), 0):
            errors.append("artifact source ref count below case minimum")
        if pages.get("chat_refs_trace_to_pages") is not True:
            errors.append("artifact pages must trace chat refs to pages")
        if pages.get("store_source_text") is not False:
            errors.append("artifact pages must not store source text")
    return errors


def response_score(case: dict[str, Any], text: str, record: dict[str, Any], artifact: dict[str, Any], target_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    score = 100
    summary = dict_value(record.get("summary"))
    if record.get("status") != "completed":
        errors.append("controller run status must be completed")
        score -= 25
    if not text.startswith("Answer:"):
        errors.append("chat response must start with Answer:")
        score -= 20
    for marker in ("run_id:", "selected_context_strategy", "context_strategy_rationale"):
        if marker not in text:
            errors.append(f"chat response missing marker {marker!r}")
            score -= 8
    if summary.get("selected_context_strategy") != case.get("expected_strategy"):
        errors.append(
            f"summary.selected_context_strategy expected {case.get('expected_strategy')!r} got {summary.get('selected_context_strategy')!r}"
        )
        score -= 20
    if summary.get("context_strategy_execution_path") != case.get("expected_execution_path"):
        errors.append("summary.context_strategy_execution_path mismatch")
        score -= 15
    if summary.get("downstream_workflow") != "large_context.retrieval_answer":
        errors.append("downstream_workflow must be large_context.retrieval_answer")
        score -= 15
    if summary.get("downstream_status") != "completed":
        errors.append("downstream_status must be completed")
        score -= 15
    if summary.get("raw_prompt_stuffing") is not False:
        errors.append("summary.raw_prompt_stuffing must be false")
        score -= 25
    if summary.get("source_changed") is not False:
        errors.append("summary.source_changed must be false")
        score -= 20
    for term in string_list(case.get("required_terms")):
        if term.lower() not in text.lower():
            errors.append(f"chat response missing required term {term!r}")
            score -= 6
    for term in string_list(case.get("forbidden_terms")):
        if term.lower() in text.lower():
            errors.append(f"chat response contains forbidden term {term!r}")
            score -= 15
    artifact_errors = artifact_contract_errors(artifact, case, target_root)
    if artifact_errors:
        errors.extend(artifact_errors)
        score -= min(30, len(artifact_errors) * 6)
    evidence_refs = object_list(artifact.get("evidence_refs"))
    visible_refs = [
        str(ref.get("source_path"))
        for ref in evidence_refs
        if isinstance(ref.get("source_path"), str) and str(ref.get("source_path")) in text
    ]
    if len(visible_refs) < int_value(case.get("minimum_visible_refs"), 0):
        errors.append("chat response did not expose enough retrieved source refs")
        score -= 12
    baseline_dimensions = string_list(dict_value(case.get("blind_baseline")).get("scoring"))
    if case.get("baseline_case_id") and not baseline_dimensions:
        warnings.append("holdout case inherits baseline dimensions")
    score = max(0, score)
    return {
        "status": "passed" if not errors and score >= int_value(case.get("minimum_score"), 85) else "failed",
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "visible_source_refs": sorted(set(visible_refs)),
        "artifact_evidence_ref_count": len(evidence_refs),
        "artifact_page_count": int_value(dict_value(artifact.get("artifact_pages")).get("page_count"), 0),
        "raw_prompt_stuffing": summary.get("raw_prompt_stuffing"),
        "selected_context_strategy": summary.get("selected_context_strategy"),
        "context_strategy_reason": summary.get("context_strategy_reason"),
        "context_strategy_execution_path": summary.get("context_strategy_execution_path"),
    }


def gateway_live_response(
    config: LargeContextUsabilityLiveCloseoutConfig,
    *,
    prompt: str,
) -> tuple[str, dict[str, Any], str]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt}],
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
        raise RuntimeError("gateway response did not include a workflow-router run_id")
    return text, controller_run_record(config, run_id), run_id


def anythingllm_live_response(
    config: LargeContextUsabilityLiveCloseoutConfig,
    *,
    prompt: str,
    case_id: str,
    api_key: str,
) -> tuple[str, dict[str, Any], str]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": prompt,
            "mode": "chat",
            "sessionId": f"phase221-large-context-{case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("AnythingLLM response did not include a workflow-router run_id")
    return text, controller_run_record(config, run_id), run_id


def run_live_case(
    config: LargeContextUsabilityLiveCloseoutConfig,
    *,
    case: dict[str, Any],
    surface: str,
    target_root: Path,
    api_key: str | None,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    try:
        if surface == "gateway":
            text, record, run_id = gateway_live_response(config, prompt=prompt)
        elif surface == "anythingllm":
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM live validation")
            text, record, run_id = anythingllm_live_response(config, prompt=prompt, case_id=str(case.get("case_id")), api_key=api_key)
        else:
            raise RuntimeError(f"unsupported surface {surface}")
        artifact = artifact_json(record, "downstream_retrieval_backed_chat_answer")
        scored = response_score(case, text, record, artifact, target_root)
    except Exception as exc:  # noqa: BLE001 - closeout reports classify all live failures
        text = ""
        record = {}
        run_id = "unknown"
        scored = {
            "status": "failed",
            "score": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "warnings": [],
            "visible_source_refs": [],
            "artifact_evidence_ref_count": 0,
            "artifact_page_count": 0,
            "raw_prompt_stuffing": None,
            "selected_context_strategy": None,
            "context_strategy_reason": None,
            "context_strategy_execution_path": None,
        }
    return {
        "surface": surface,
        "case_id": case.get("case_id"),
        "case_type": "holdout" if case.get("baseline_case_id") else "baseline",
        "category": case.get("category"),
        "run_id": run_id,
        "prompt_sha256": sha256_text(prompt),
        "status": scored["status"],
        "score": scored["score"],
        "errors": scored["errors"],
        "warnings": scored["warnings"],
        "selected_context_strategy": scored["selected_context_strategy"],
        "context_strategy_execution_path": scored["context_strategy_execution_path"],
        "context_strategy_reason": scored["context_strategy_reason"],
        "raw_prompt_stuffing": scored["raw_prompt_stuffing"],
        "visible_source_refs": scored["visible_source_refs"],
        "artifact_evidence_ref_count": scored["artifact_evidence_ref_count"],
        "artifact_page_count": scored["artifact_page_count"],
        "chat_excerpt": text[:1200],
    }


def sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def small_repo_prompt(root: str) -> str:
    return f"In {root}, find where retrieval starts in this repo. Read only. Include source refs."


def run_small_repo_non_regression(
    config: LargeContextUsabilityLiveCloseoutConfig,
    *,
    surface: str,
    root: str,
    api_key: str | None,
) -> dict[str, Any]:
    before = fixture_state(root)
    prompt = small_repo_prompt(root)
    try:
        if surface == "gateway":
            text, record, run_id = gateway_live_response(config, prompt=prompt)
        elif surface == "anythingllm":
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM live validation")
            text, record, run_id = anythingllm_live_response(
                config,
                prompt=prompt,
                case_id=f"small-{Path(root).name}",
                api_key=api_key,
            )
        else:
            raise RuntimeError(f"unsupported surface {surface}")
        assert_fixture_state_unchanged(before, root, f"phase221 {surface} small-repo non-regression")
        summary = dict_value(record.get("summary"))
        errors: list[str] = []
        if summary.get("selected_context_strategy") != "direct_context":
            errors.append("small-repo prompt must remain direct_context")
        if summary.get("downstream_workflow") == "large_context.retrieval_answer" or summary.get("retrieval_status"):
            errors.append("small-repo prompt must not invoke large-context retrieval")
        if summary.get("source_changed") is not False:
            errors.append("small-repo source_changed must be false")
        status = "passed" if not errors else "failed"
    except Exception as exc:  # noqa: BLE001
        text = ""
        run_id = "unknown"
        summary = {}
        errors = [f"{type(exc).__name__}: {exc}"]
        status = "failed"
    return {
        "surface": surface,
        "target_root": root,
        "status": status,
        "run_id": run_id,
        "errors": errors,
        "selected_context_strategy": summary.get("selected_context_strategy"),
        "downstream_workflow": summary.get("downstream_workflow"),
        "chat_excerpt": text[:600],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 221 Large-Context Usability Live Closeout",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Live: `{report.get('live')}`",
        f"- Response count: `{summary.get('response_count')}`",
        f"- Failed response count: `{summary.get('failed_response_count')}`",
        f"- Small-repo regression count: `{summary.get('small_repo_regression_count')}`",
        f"- M6 ready: `{summary.get('m6_ready')}`",
        f"- M8 ready: `{summary.get('m8_ready')}`",
        "",
        "## Large-Context Responses",
    ]
    for item in object_list(report.get("responses")):
        lines.append(
            f"- `{item.get('status')}` `{item.get('surface')}` `{item.get('case_id')}` "
            f"strategy=`{item.get('selected_context_strategy')}` score=`{item.get('score')}` run=`{item.get('run_id')}`"
        )
        for error in string_list(item.get("errors")):
            lines.append(f"  - error: {error}")
    lines.extend(["", "## Small-Repo Non-Regression"])
    for item in object_list(report.get("small_repo_regression_results")):
        lines.append(
            f"- `{item.get('status')}` `{item.get('surface')}` `{item.get('target_root')}` "
            f"strategy=`{item.get('selected_context_strategy')}` run=`{item.get('run_id')}`"
        )
        for error in string_list(item.get("errors")):
            lines.append(f"  - error: {error}")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for error in errors:
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    return "\n".join(lines).rstrip() + "\n"


def validate_large_context_usability_live_closeout(config: LargeContextUsabilityLiveCloseoutConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path or default_output_path(live=config.live))
    markdown_output_path = resolve_path(
        config_root,
        config.markdown_output_path or default_markdown_output_path(live=config.live),
    )
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)
    phase220_path, phase220_report, phase220_errors = load_report(
        config_root,
        dict_value(policy.get("phase220_precondition")).get("report_path"),
        source="phase220_report",
        require_artifacts=config.require_artifacts,
    )
    validation_errors.extend(phase220_errors)
    validation_errors.extend(validate_phase220_precondition(policy, phase220_report))
    target_root = resolve_path(config_root, str(policy.get("target_root"))).resolve()
    cases = selected_cases(policy, config)
    surfaces = selected_surfaces(config)
    responses: list[dict[str, Any]] = []
    small_repo_results: list[dict[str, Any]] = []

    if not config.allow_partial:
        if set(surfaces) != set(string_list(policy.get("required_surfaces"))):
            validation_errors.append(validation_error("live.surfaces", "closeout must include gateway and AnythingLLM"))
        if len(cases) < int_value(dict_value(policy.get("minimums")).get("total_case_count"), 8):
            validation_errors.append(validation_error("live.case_count", "closeout must include all baseline and holdout cases"))

    if config.live and not validation_errors:
        api_key = os.environ.get(config.api_key_env)
        for surface in surfaces:
            for case in cases:
                responses.append(run_live_case(config, case=case, surface=surface, target_root=target_root, api_key=api_key))
        for surface in surfaces:
            for root in string_list(policy.get("small_repo_regression_roots")):
                small_repo_results.append(run_small_repo_non_regression(config, surface=surface, root=root, api_key=api_key))

    failed_responses = [item for item in responses if item.get("status") != "passed"]
    failed_small_repo = [item for item in small_repo_results if item.get("status") != "passed"]
    status = LargeContextLiveCloseoutStatus.FAILED.value
    if not validation_errors and not config.live:
        status = LargeContextLiveCloseoutStatus.PREFLIGHT_PASSED.value
    elif not validation_errors and not failed_responses and not failed_small_repo:
        status = LargeContextLiveCloseoutStatus.PASSED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "live": config.live,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "phase220_report_path": str(phase220_path) if phase220_path is not None else None,
        "phase220_report_sha256": sha256_file(phase220_path) if phase220_path is not None and phase220_path.is_file() else None,
        "target_root": str(target_root),
        "responses": responses,
        "small_repo_regression_results": small_repo_results,
        "validation_errors": validation_errors,
        "summary": {
            "case_count": len(cases),
            "surface_count": len(surfaces),
            "response_count": len(responses),
            "failed_response_count": len(failed_responses),
            "small_repo_regression_count": len(small_repo_results),
            "failed_small_repo_regression_count": len(failed_small_repo),
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
            "raw_prompt_stuffing_allowed": dict_value(policy.get("answer_contract")).get("raw_prompt_stuffing_allowed"),
            "minimum_response_score": dict_value(policy.get("minimums")).get("minimum_response_score"),
            "m6_ready": status == LargeContextLiveCloseoutStatus.PASSED.value,
            "m8_ready": status == LargeContextLiveCloseoutStatus.PASSED.value,
            "phase222_ready": status == LargeContextLiveCloseoutStatus.PASSED.value,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
