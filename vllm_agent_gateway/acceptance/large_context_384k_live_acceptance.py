"""Phase 261 live acceptance gate for the 384k large-context target."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.chunked_investigation_executor_implementation import (
    ChunkedInvestigationExecutorImplementationConfig,
    validate_chunked_investigation_executor_implementation,
)
from vllm_agent_gateway.acceptance.large_context_384k_fixture_index_readiness import (
    LargeContext384kFixtureIndexReadinessConfig,
    validate_large_context_384k_fixture_index_readiness,
)
from vllm_agent_gateway.acceptance.large_context_384k_stale_index_rejection import (
    LargeContext384kStaleIndexRejectionConfig,
    validate_large_context_384k_stale_index_rejection,
)
from vllm_agent_gateway.acceptance.large_context_384k_usability_acceptance_contract import (
    LargeContext384kUsabilityAcceptanceContractConfig,
    validate_large_context_384k_usability_acceptance_contract,
)
from vllm_agent_gateway.acceptance.large_context_usability_live_closeout import (
    LargeContextUsabilityLiveCloseoutConfig,
    source_hash_revalidation,
    validate_large_context_usability_live_closeout,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    run_id_from_text,
    text_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_384k_live_acceptance_policy"
EXPECTED_REPORT_KIND = "large_context_384k_live_acceptance_report"
EXPECTED_PHASE = 261
EXPECTED_BACKLOG_ID = "P0-M6-261"
EXPECTED_MILESTONE_IDS = {"M2", "M4", "M6", "M8", "M13", "M14", "M16"}
TARGET_ESTIMATED_PROJECT_TOKENS = 384_000
REQUIRED_STRATEGIES = {"retrieval", "artifact_paging", "summarization", "refusal", "chunked_investigation"}
REQUIRED_SURFACES = {"gateway", "anythingllm"}
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_384k_live_acceptance_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase261"
    / "phase261-large-context-384k-live-acceptance-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase261"
    / "phase261-large-context-384k-live-acceptance-report.md"
)


class LargeContext384kLiveAcceptanceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PREFLIGHT_PASSED = "preflight_passed"


class LargeContext384kLiveAcceptanceDecision(str, Enum):
    READY = "phase261_current_384k_live_acceptance_proof"
    BLOCKED = "phase261_live_acceptance_blocked"
    PREFLIGHT_READY = "phase261_live_acceptance_preflight_ready"


@dataclass(frozen=True)
class LargeContext384kLiveAcceptanceConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    include_gateway: bool = True
    include_anythingllm: bool = True
    live: bool = False
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_workflow_router_base_url: str | None = None
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 1200
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    text = str(value)
    if os.name == "nt" and len(text) > 7 and text.startswith("/mnt/") and text[5].isalpha() and text[6] == "/":
        return Path(f"{text[5].upper()}:/{text[7:]}")
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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "source": source, "severity": severity}


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                body = {"text": body_text}
            return response.status, body if isinstance(body, dict) else {"value": body}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body if isinstance(body, dict) else {"value": body}
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": {"message": str(exc), "code": "request_error"}}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 261"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M2, M4, M6, M8, M13, M14, and M16"))
    if policy.get("target_estimated_project_tokens") != TARGET_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.target_estimated_project_tokens", "target must be 384000"))
    if set(string_list(policy.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must be gateway and anythingllm"))
    if set(string_list(policy.get("required_strategy_ids"))) != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.required_strategy_ids", "all required strategy ids must be present"))
    if len(dict_value(policy.get("required_preconditions"))) != 3:
        errors.append(validation_error("policy.required_preconditions", "Phase 258, 259, and 260 preconditions are required"))
    live_reports = dict_value(policy.get("required_live_reports"))
    for report_id in ("phase221", "phase223"):
        if not dict_value(live_reports.get(report_id)):
            errors.append(validation_error(f"policy.required_live_reports.{report_id}", f"{report_id} live report is required"))
    parity = dict_value(policy.get("json_default_parity"))
    if parity.get("required") is not True:
        errors.append(validation_error("policy.json_default_parity.required", "JSON/default parity must be required"))
    if parity.get("surface") != "gateway":
        errors.append(validation_error("policy.json_default_parity.surface", "Phase 261 parity must run on gateway"))
    if parity.get("expected_strategy") not in REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.json_default_parity.expected_strategy", "expected strategy must be governed"))
    if set(string_list(parity.get("expected_output_formats"))) != {"format_a", "json"}:
        errors.append(validation_error("policy.json_default_parity.expected_output_formats", "format_a and json are required"))
    blind = dict_value(policy.get("blind_baseline_comparison"))
    if blind.get("required") is not True or blind.get("critical_or_high_finding_count") != 0:
        errors.append(validation_error("policy.blind_baseline_comparison", "blind baseline comparison must be fail-closed"))
    safety = dict_value(policy.get("safety_requirements"))
    for key in (
        "raw_prompt_stuffing_allowed",
        "raw_384k_prompt_support_claim_allowed",
        "raw_1m_prompt_support_claim_allowed",
        "store_source_text",
        "store_rejected_content",
        "artifact_only_answers_allowed",
        "protected_fixture_mutation_allowed",
        "generated_corpus_mutation_allowed",
        "post_384k_expansion_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(validation_error(f"policy.safety_requirements.{key}", f"{key} must be false"))
    if safety.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.safety_requirements.source_text_retention", "source_text_retention must be metadata_only"))
    if len(string_list(policy.get("protected_fixture_roots"))) < 2:
        errors.append(validation_error("policy.protected_fixture_roots", "both protected Coinbase fixture roots are required"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE261 LARGE CONTEXT 384K LIVE ACCEPTANCE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 261"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        missing = [marker for marker in string_list(required_markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        results.append(result)
    return results, errors


def tree_fingerprint(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {"root": str(root), "exists": False, "file_count": 0, "total_size": 0, "sha256": None}
    digest = hashlib.sha256()
    file_count = 0
    total_size = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative.startswith(".git/") or "/.git/" in relative:
            continue
        data = path.read_bytes()
        file_count += 1
        total_size += len(data)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return {"root": str(root), "exists": True, "file_count": file_count, "total_size": total_size, "sha256": digest.hexdigest()}


def fixture_fingerprints(config_root: Path, policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roots = [str(policy.get("target_root") or "")]
    roots.extend(string_list(policy.get("protected_fixture_roots")))
    return {raw_path: tree_fingerprint(resolve_path(config_root, raw_path)) for raw_path in roots if raw_path}


def mutation_errors(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for root, before_value in before.items():
        after_value = after.get(root, {})
        if before_value.get("exists") is not True:
            errors.append(validation_error(f"fixtures.{root}.missing", "fixture or target root is missing", source="fixtures", severity="critical"))
            continue
        if before_value != after_value:
            errors.append(validation_error(f"fixtures.{root}.changed", "fixture or target root fingerprint changed", source="fixtures", severity="critical"))
    return errors


def target_settings_result(config: LargeContext384kLiveAcceptanceConfig, policy: dict[str, Any], api_key: str | None) -> dict[str, Any]:
    if not config.include_anythingllm:
        return {"status": LargeContext384kLiveAcceptanceStatus.FAILED.value, "errors": ["AnythingLLM surface is required"]}
    if not api_key:
        return {"status": LargeContext384kLiveAcceptanceStatus.FAILED.value, "errors": [f"{config.api_key_env} is required"]}
    required_policy = dict_value(policy.get("required_anythingllm"))
    expected_workflow_router = config.anythingllm_workflow_router_base_url or str(
        required_policy.get("internal_workflow_router_base_url") or ""
    )
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/system",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(config.timeout_seconds, 30),
    )
    settings = dict_value(body.get("settings"))
    actual = {
        "api_base_url": config.anythingllm_api_base_url,
        "workspace": config.workspace,
        "provider": settings.get("LLMProvider"),
        "model": settings.get("LLMModel"),
        "generic_openai_base_path": settings.get("GenericOpenAiBasePath"),
    }
    required = {
        "api_base_url": required_policy.get("api_base_url"),
        "workspace": required_policy.get("workspace"),
        "provider": required_policy.get("provider"),
        "model": required_policy.get("model"),
        "internal_workflow_router_base_url": required_policy.get("internal_workflow_router_base_url"),
        "effective_workflow_router_base_url": expected_workflow_router,
    }
    checks = {
        "http_status": status == 200,
        "api_base_url": actual["api_base_url"] == required["api_base_url"],
        "workspace": actual["workspace"] == required["workspace"],
        "provider": actual["provider"] == required["provider"],
        "model": actual["model"] == required["model"],
        "generic_openai_base_path": actual["generic_openai_base_path"] == expected_workflow_router,
    }
    return {
        "status": LargeContext384kLiveAcceptanceStatus.PASSED.value if all(checks.values()) else LargeContext384kLiveAcceptanceStatus.FAILED.value,
        "http_status": status,
        "actual": actual,
        "required": required,
        "checks": checks,
        "split_url_mode": expected_workflow_router != required_policy.get("internal_workflow_router_base_url"),
        "errors": [] if all(checks.values()) else ["AnythingLLM target settings did not match required workflow-router target"],
    }


def run_precondition_reports(config: LargeContext384kLiveAcceptanceConfig) -> dict[str, dict[str, Any]]:
    config_root = config.config_root.resolve()
    phase258 = validate_large_context_384k_usability_acceptance_contract(
        LargeContext384kUsabilityAcceptanceContractConfig(config_root=config_root)
    )
    phase259 = validate_large_context_384k_fixture_index_readiness(
        LargeContext384kFixtureIndexReadinessConfig(config_root=config_root)
    )
    phase260 = validate_large_context_384k_stale_index_rejection(
        LargeContext384kStaleIndexRejectionConfig(config_root=config_root)
    )
    return {"phase258": phase258, "phase259": phase259, "phase260": phase260}


def run_live_reports(
    config: LargeContext384kLiveAcceptanceConfig,
    output_dir: Path,
) -> dict[str, dict[str, Any]]:
    phase221 = validate_large_context_usability_live_closeout(
        LargeContextUsabilityLiveCloseoutConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase261-phase221-large-context-usability-live-closeout-report.json",
            markdown_output_path=output_dir / "phase261-phase221-large-context-usability-live-closeout-report.md",
            include_gateway=config.include_gateway,
            include_anythingllm=config.include_anythingllm,
            live=True,
            allow_partial=False,
            model_base_url=config.model_base_url,
            workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
            controller_base_url=config.controller_base_url,
            anythingllm_api_base_url=config.anythingllm_api_base_url,
            workspace=config.workspace,
            api_key_env=config.api_key_env,
            timeout_seconds=config.timeout_seconds,
            require_artifacts=config.require_artifacts,
        )
    )
    phase223 = validate_chunked_investigation_executor_implementation(
        ChunkedInvestigationExecutorImplementationConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase261-phase223-chunked-investigation-executor-implementation-report.json",
            markdown_output_path=output_dir / "phase261-phase223-chunked-investigation-executor-implementation-report.md",
            include_gateway=config.include_gateway,
            include_anythingllm=config.include_anythingllm,
            live=True,
            allow_partial=False,
            model_base_url=config.model_base_url,
            workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
            controller_base_url=config.controller_base_url,
            anythingllm_api_base_url=config.anythingllm_api_base_url,
            workspace=config.workspace,
            api_key_env=config.api_key_env,
            timeout_seconds=config.timeout_seconds,
            require_artifacts=config.require_artifacts,
        )
    )
    return {"phase221": phase221, "phase223": phase223}


def selected_strategies(phase221: dict[str, Any], phase223: dict[str, Any]) -> list[str]:
    values = {
        str(item.get("selected_context_strategy"))
        for item in object_list(phase221.get("responses")) + object_list(phase223.get("responses"))
        if isinstance(item.get("selected_context_strategy"), str)
    }
    return sorted(values)


def response_count_for_surface(report: dict[str, Any], surface: str) -> int:
    return sum(1 for item in object_list(report.get("responses")) if item.get("surface") == surface)


def failed_small_repo_count(report: dict[str, Any]) -> int:
    return sum(1 for item in object_list(report.get("small_repo_regression_results")) if item.get("status") != "passed")


def run_ids_from_report(report: dict[str, Any]) -> list[str]:
    return [
        str(item.get("run_id"))
        for item in object_list(report.get("responses")) + object_list(report.get("small_repo_regression_results"))
        if isinstance(item.get("run_id"), str) and item.get("run_id") not in ("", "unknown")
    ]


def baseline_artifacts(config_root: Path, output_dir: Path) -> dict[str, Any]:
    phase221_policy = read_json_object(config_root / "runtime" / "large_context_usability_live_closeout_policy.json")
    phase223_policy = read_json_object(config_root / "runtime" / "chunked_investigation_executor_implementation_policy.json")
    generated_at = utc_timestamp()
    artifacts: list[dict[str, Any]] = []
    for case in object_list(phase221_policy.get("baseline_cases")) + object_list(phase221_policy.get("holdout_cases")):
        baseline_payload = {
            "case_id": case.get("case_id"),
            "baseline_case_id": case.get("baseline_case_id"),
            "category": case.get("category"),
            "prompt_sha256": sha256_text(str(case.get("prompt") or "")),
            "blind_baseline": dict_value(case.get("blind_baseline")),
        }
        artifacts.append(
            {
                "case_id": case.get("case_id"),
                "source": "phase221_policy",
                "generated_before_local_output": True,
                "generated_at": generated_at,
                "sha256": sha256_text(json.dumps(baseline_payload, ensure_ascii=True, sort_keys=True)),
                "baseline_key_count": len(dict_value(case.get("blind_baseline"))),
            }
        )
    chunked_payload = {
        "case_id": "P223-CHUNKED-001",
        "prompt_sha256": sha256_text(str(phase223_policy.get("chunked_prompt") or "")),
        "contract_refs": phase223_policy.get("answer_contract"),
        "minimums": phase223_policy.get("minimums"),
    }
    artifacts.append(
        {
            "case_id": "P223-CHUNKED-001",
            "source": "phase223_policy",
            "generated_before_local_output": True,
            "generated_at": generated_at,
            "sha256": sha256_text(json.dumps(chunked_payload, ensure_ascii=True, sort_keys=True)),
            "baseline_key_count": 3,
        }
    )
    path = output_dir / "phase261-blind-baseline-artifacts.json"
    payload = {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "baselines": artifacts}
    write_json(path, payload)
    return {"path": str(path.resolve()), "sha256": sha256_file(path), "baseline_count": len(artifacts), "baselines": artifacts}


def blind_baseline_comparisons(
    phase221: dict[str, Any],
    phase223: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for item in object_list(phase221.get("responses")):
        severity = "none" if item.get("status") == "passed" else ("critical" if item.get("run_id") == "unknown" else "high")
        comparisons.append(
            {
                "case_id": item.get("case_id"),
                "surface": item.get("surface"),
                "source": "phase221",
                "status": "passed" if severity == "none" else "failed",
                "severity": severity,
                "score": item.get("score"),
                "errors": item.get("errors") if isinstance(item.get("errors"), list) else [],
            }
        )
    for item in object_list(phase223.get("responses")):
        severity = "none" if item.get("status") == "passed" else ("critical" if item.get("run_id") == "unknown" else "high")
        comparisons.append(
            {
                "case_id": "P223-CHUNKED-001",
                "surface": item.get("surface"),
                "source": "phase223",
                "status": "passed" if severity == "none" else "failed",
                "severity": severity,
                "errors": item.get("errors") if isinstance(item.get("errors"), list) else [],
            }
        )
    critical_or_high = sum(1 for item in comparisons if item.get("severity") in {"critical", "high"})
    path = output_dir / "phase261-blind-baseline-comparisons.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "comparison_count": len(comparisons),
        "critical_or_high_finding_count": critical_or_high,
        "comparisons": comparisons,
    }
    write_json(path, payload)
    return {"path": str(path.resolve()), "sha256": sha256_file(path), **payload}


def artifact_from_compact(compact: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = dict_value(compact.get("artifacts"))
    path = artifacts.get(key)
    if not isinstance(path, str) or not path:
        return {}
    try:
        return read_json_object(Path(path))
    except (OSError, RuntimeError, json.JSONDecodeError):
        return {}


def gateway_chat(config: LargeContext384kLiveAcceptanceConfig, *, prompt: str, response_format: dict[str, str] | None = None) -> tuple[int, dict[str, Any], str]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": prompt}],
        "role_base_url": config.model_base_url,
        "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
    }
    if response_format is not None:
        payload["response_format"] = response_format
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=config.timeout_seconds,
    )
    return status, body, text_response(body) if status == 200 else ""


def run_json_default_parity(
    config: LargeContext384kLiveAcceptanceConfig,
    policy: dict[str, Any],
    target_root: Path,
) -> dict[str, Any]:
    parity = dict_value(policy.get("json_default_parity"))
    prompt = str(parity.get("prompt") or "").replace("{target_root}", str(target_root))
    default_status, default_body, default_text = gateway_chat(config, prompt=prompt)
    json_status, json_body, json_text = gateway_chat(config, prompt=prompt, response_format={"type": "json_object"})
    errors: list[str] = []
    parsed_json: dict[str, Any] = {}
    try:
        parsed_value = json.loads(json_text)
        if isinstance(parsed_value, dict):
            parsed_json = parsed_value
        else:
            errors.append("JSON response was not an object")
    except json.JSONDecodeError as exc:
        errors.append(f"JSON response was not parseable: {exc}")

    default_compact = dict_value(default_body.get("agentic_controller_response"))
    default_summary = dict_value(default_compact.get("summary"))
    json_summary = dict_value(parsed_json.get("summary"))
    default_artifact = artifact_from_compact(default_compact, "downstream_retrieval_backed_chat_answer")
    json_artifact = artifact_from_compact(parsed_json, "downstream_retrieval_backed_chat_answer")
    if not json_artifact:
        json_artifact = artifact_from_compact(dict_value(json_body.get("agentic_controller_response")), "downstream_retrieval_backed_chat_answer")
    expected_strategy = parity.get("expected_strategy")
    if default_status != 200:
        errors.append(f"default gateway HTTP status was {default_status}")
    if json_status != 200:
        errors.append(f"json gateway HTTP status was {json_status}")
    if not default_text.startswith("Answer:"):
        errors.append("default response did not start with Answer:")
    if parsed_json.get("output_format") != "json":
        errors.append(f"JSON output_format was {parsed_json.get('output_format')!r}")
    primary = dict_value(parsed_json.get("primary_answer_contract"))
    primary_text = str(primary.get("text") or "")
    if not primary_text:
        errors.append("JSON primary_answer_contract.text was empty")
    if default_compact.get("output_format") != "format_a":
        errors.append(f"default compact output_format was {default_compact.get('output_format')!r}")
    if default_summary.get("selected_context_strategy") != expected_strategy:
        errors.append("default selected_context_strategy did not match expected strategy")
    if json_summary.get("selected_context_strategy") != expected_strategy:
        errors.append("JSON selected_context_strategy did not match expected strategy")
    if default_summary.get("raw_prompt_stuffing") is not False:
        errors.append("default raw_prompt_stuffing was not false")
    if json_summary.get("raw_prompt_stuffing") is not False:
        errors.append("JSON raw_prompt_stuffing was not false")
    for term in string_list(parity.get("required_terms")):
        if term.lower() not in default_text.lower():
            errors.append(f"default response missing required term {term!r}")
        if term.lower() not in primary_text.lower() and term.lower() not in json_text.lower():
            errors.append(f"JSON response missing required term {term!r}")
    default_refs = object_list(default_artifact.get("evidence_refs"))
    json_refs = object_list(json_artifact.get("evidence_refs"))
    if len(default_refs) < int_value(parity.get("minimum_evidence_refs")):
        errors.append("default evidence ref count below minimum")
    if len(json_refs) < int_value(parity.get("minimum_evidence_refs")):
        errors.append("JSON evidence ref count below minimum")
    default_hash = source_hash_revalidation(target_root, default_refs)
    json_hash = source_hash_revalidation(target_root, json_refs)
    errors.extend(f"default {item}" for item in string_list(default_hash.get("errors")))
    errors.extend(f"json {item}" for item in string_list(json_hash.get("errors")))
    status = "passed" if not errors else "failed"
    return {
        "case_id": parity.get("case_id"),
        "status": status,
        "prompt_sha256": sha256_text(prompt),
        "surface": "gateway",
        "default": {
            "http_status": default_status,
            "run_id": default_compact.get("run_id") or run_id_from_text(default_text),
            "output_format": default_compact.get("output_format"),
            "selected_context_strategy": default_summary.get("selected_context_strategy"),
            "raw_prompt_stuffing": default_summary.get("raw_prompt_stuffing"),
            "evidence_ref_count": len(default_refs),
            "source_hash_checked_count": default_hash.get("checked_count"),
        },
        "json": {
            "http_status": json_status,
            "run_id": parsed_json.get("run_id") or run_id_from_text(json_text),
            "output_format": parsed_json.get("output_format"),
            "selected_context_strategy": json_summary.get("selected_context_strategy"),
            "raw_prompt_stuffing": json_summary.get("raw_prompt_stuffing"),
            "evidence_ref_count": len(json_refs),
            "source_hash_checked_count": json_hash.get("checked_count"),
            "has_primary_answer": bool(primary_text),
        },
        "errors": errors,
    }


def precondition_errors(policy: dict[str, Any], reports: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("required_preconditions"))
    for phase_id, report in reports.items():
        precondition = dict_value(required.get(phase_id))
        if report.get("status") != precondition.get("required_status"):
            errors.append(validation_error(f"{phase_id}.status", f"{phase_id} precondition did not pass", source=phase_id, severity="critical"))
        flag = precondition.get("required_summary_flag")
        if isinstance(flag, str) and dict_value(report.get("summary")).get(flag) is not True:
            errors.append(validation_error(f"{phase_id}.{flag}", f"{phase_id} summary flag {flag} must be true", source=phase_id))
        minimum_indexed = precondition.get("minimum_estimated_indexed_token_count")
        if isinstance(minimum_indexed, int) and int_value(dict_value(report.get("summary")).get("estimated_indexed_token_count")) < minimum_indexed:
            errors.append(validation_error(f"{phase_id}.estimated_indexed_token_count", "indexed token count below 384k", source=phase_id))
    return errors


def live_report_errors(policy: dict[str, Any], reports: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("required_live_reports"))
    for report_id in ("phase221", "phase223"):
        report = dict_value(reports.get(report_id))
        req = dict_value(required.get(report_id))
        summary = dict_value(report.get("summary"))
        if report.get("status") != req.get("required_status"):
            errors.append(validation_error(f"{report_id}.status", f"{report_id} live report did not pass", source=report_id, severity="critical"))
        if int_value(summary.get("response_count")) < int_value(req.get("minimum_response_count")):
            errors.append(validation_error(f"{report_id}.response_count", f"{report_id} response count below minimum", source=report_id))
        if int_value(summary.get("failed_response_count")):
            errors.append(validation_error(f"{report_id}.failed_response_count", f"{report_id} failed responses must be zero", source=report_id))
        if int_value(summary.get("small_repo_regression_count")) < int_value(req.get("minimum_small_repo_regression_count")):
            errors.append(validation_error(f"{report_id}.small_repo_regression_count", f"{report_id} small repo count below minimum", source=report_id))
        if int_value(summary.get("failed_small_repo_regression_count")):
            errors.append(validation_error(f"{report_id}.failed_small_repo_regression_count", f"{report_id} small repo failures must be zero", source=report_id))
        if summary.get("raw_prompt_stuffing_allowed") is not False:
            errors.append(validation_error(f"{report_id}.raw_prompt_stuffing_allowed", f"{report_id} raw prompt stuffing must be false", source=report_id))
    strategies = set(selected_strategies(dict_value(reports.get("phase221")), dict_value(reports.get("phase223"))))
    missing = sorted(REQUIRED_STRATEGIES - strategies)
    if missing:
        errors.append(validation_error("live_reports.strategy_ids", "missing required strategies: " + ", ".join(missing), source="live_reports", severity="critical"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 384k Live Acceptance",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Strategy ids: `{', '.join(string_list(summary.get('strategy_ids')))}`",
        f"- Response count: `{summary.get('response_count')}`",
        f"- AnythingLLM target settings: `{summary.get('target_settings_status')}`",
        f"- JSON/default parity: `{summary.get('json_default_parity_status')}`",
        f"- Critical/high blind-baseline findings: `{summary.get('critical_or_high_finding_count')}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('severity')}` `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_384k_live_acceptance(config: LargeContext384kLiveAcceptanceConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    output_dir = output_path.parent
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    docs, doc_errors = docs_checks(config_root, policy)
    errors.extend(doc_errors)
    api_key = os.environ.get(config.api_key_env)
    target_settings = target_settings_result(config, policy, api_key) if config.live else {"status": "not_run", "errors": []}
    preconditions: dict[str, dict[str, Any]] = {}
    live_reports: dict[str, dict[str, Any]] = {}
    before_fixtures: dict[str, dict[str, Any]] = {}
    baseline_bundle = baseline_artifacts(config_root, output_dir)
    comparison_bundle: dict[str, Any] = {
        "path": None,
        "comparison_count": 0,
        "critical_or_high_finding_count": 0,
        "comparisons": [],
    }
    parity_results: list[dict[str, Any]] = []
    if not errors:
        preconditions = run_precondition_reports(config)
        errors.extend(precondition_errors(policy, preconditions))
        before_fixtures = fixture_fingerprints(config_root, policy)
    if config.live and not errors:
        if target_settings.get("status") != LargeContext384kLiveAcceptanceStatus.PASSED.value:
            errors.append(validation_error("anythingllm.target_settings", "AnythingLLM target settings must pass", source="anythingllm", severity="critical"))
    if config.live and not errors:
        live_reports = run_live_reports(config, output_dir)
        errors.extend(live_report_errors(policy, live_reports))
        comparison_bundle = blind_baseline_comparisons(
            dict_value(live_reports.get("phase221")),
            dict_value(live_reports.get("phase223")),
            output_dir,
        )
        if int_value(comparison_bundle.get("critical_or_high_finding_count")):
            errors.append(validation_error("blind_baseline.critical_or_high", "blind baseline comparison has critical/high findings", source="blind_baseline", severity="critical"))
        target_root = resolve_path(config_root, str(policy.get("target_root"))).resolve()
        parity_results.append(run_json_default_parity(config, policy, target_root))
        if any(item.get("status") != "passed" for item in parity_results):
            errors.append(validation_error("json_default_parity.status", "JSON/default parity failed", source="json_default_parity", severity="critical"))
    elif not config.live and not errors:
        errors.append(validation_error("live.required", "Phase 261 acceptance requires --live", source="live", severity="critical"))
    after_fixtures = fixture_fingerprints(config_root, policy)
    errors.extend(mutation_errors(before_fixtures, after_fixtures))

    phase221 = dict_value(live_reports.get("phase221"))
    phase223 = dict_value(live_reports.get("phase223"))
    phase221_summary = dict_value(phase221.get("summary"))
    phase223_summary = dict_value(phase223.get("summary"))
    strategies = selected_strategies(phase221, phase223)
    response_count = int_value(phase221_summary.get("response_count")) + int_value(phase223_summary.get("response_count"))
    gateway_response_count = response_count_for_surface(phase221, "gateway") + response_count_for_surface(phase223, "gateway")
    anythingllm_response_count = response_count_for_surface(phase221, "anythingllm") + response_count_for_surface(phase223, "anythingllm")
    small_repo_count = int_value(phase221_summary.get("small_repo_regression_count")) + int_value(phase223_summary.get("small_repo_regression_count"))
    failed_small_count = failed_small_repo_count(phase221) + failed_small_repo_count(phase223)
    parity_passed = sum(1 for item in parity_results if item.get("status") == "passed")
    status = LargeContext384kLiveAcceptanceStatus.PASSED.value if not errors else LargeContext384kLiveAcceptanceStatus.FAILED.value
    decision = (
        LargeContext384kLiveAcceptanceDecision.READY.value
        if status == LargeContext384kLiveAcceptanceStatus.PASSED.value
        else LargeContext384kLiveAcceptanceDecision.BLOCKED.value
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "live": config.live,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "docs": docs,
        "target_settings": target_settings,
        "preconditions": {
            key: {"status": value.get("status"), "summary": dict_value(value.get("summary")), "report_path": value.get("report_path")}
            for key, value in preconditions.items()
        },
        "live_reports": {
            "phase221": {"status": phase221.get("status"), "summary": phase221_summary, "report_path": phase221.get("report_path")},
            "phase223": {"status": phase223.get("status"), "summary": phase223_summary, "report_path": phase223.get("report_path")},
        },
        "run_ids": {"phase221": run_ids_from_report(phase221), "phase223": run_ids_from_report(phase223)},
        "json_default_parity_results": parity_results,
        "blind_baseline_artifacts": {
            "path": baseline_bundle.get("path"),
            "sha256": baseline_bundle.get("sha256"),
            "baseline_count": baseline_bundle.get("baseline_count"),
        },
        "blind_baseline_comparison": {
            "path": comparison_bundle.get("path"),
            "sha256": comparison_bundle.get("sha256"),
            "comparison_count": comparison_bundle.get("comparison_count"),
            "critical_or_high_finding_count": comparison_bundle.get("critical_or_high_finding_count"),
        },
        "fixture_fingerprints_before": before_fixtures,
        "fixture_fingerprints_after": after_fixtures,
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "target_estimated_project_tokens": policy.get("target_estimated_project_tokens"),
            "strategy_ids": strategies,
            "required_strategy_ids": sorted(REQUIRED_STRATEGIES),
            "response_count": response_count,
            "gateway_response_count": gateway_response_count,
            "anythingllm_response_count": anythingllm_response_count,
            "small_repo_regression_count": small_repo_count,
            "failed_small_repo_regression_count": failed_small_count,
            "target_settings_status": target_settings.get("status"),
            "json_default_parity_status": "passed" if parity_results and parity_passed == len(parity_results) else "failed",
            "json_default_parity_case_count": len(parity_results),
            "json_default_parity_passed_count": parity_passed,
            "critical_or_high_finding_count": comparison_bundle.get("critical_or_high_finding_count"),
            "raw_prompt_stuffing_allowed": False,
            "phase262_ready": not errors,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
