"""Semi-well-defined prompt generalization validation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.recursive_blind_testing import DEFAULT_POLICY_PATH
from vllm_agent_gateway.controllers.workflow_router.plan import workflow_kind_for_request
from vllm_agent_gateway.fixtures.manager import (
    DEFAULT_MANIFEST_PATH,
    FixtureEntry,
    fixture_entries,
    load_fixture_manifest,
    watched_hashes as fixture_watched_hashes,
)
from vllm_agent_gateway.prompt_catalogs import (
    DEFAULT_FOUNDER_FIELD_CATALOG,
    PromptCatalogCase,
    load_prompt_catalog,
    prompt_cases_from_catalog,
    validate_prompt_catalog,
)


SCHEMA_VERSION = 1
DEFAULT_CATALOG_PATH = Path("runtime") / "prompt_catalogs" / "semi_well_defined_v1.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "semi-well-defined-prompts"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TIMEOUT_SECONDS = 900
REQUIRED_COINBASE_FIXTURES = {"coinbase-frozen", "coinbase-frozen-git"}
INTERNAL_PROMPT_TERMS = (
    "selected_workflow:",
    "workflow_router.plan",
    "code_investigation.plan",
    "code_context.lookup",
    "execution_planning.plan",
    "task.decompose",
    "downstream_",
    "route_decision",
    "manual skill injection",
)
REQUIRED_VARIANT_TYPES = {
    "omitted_read_only_equivalent",
    "reordered_outputs",
    "partial_target_description",
    "natural_no_internal_terms",
}
VALID_SAFETY_EXPECTATIONS = {
    "read_only_explicit",
    "read_only_inferred_from_no_change",
    "draft_only_no_source_mutation",
    "blocked_approval_bypass",
    "blocked_raw_context",
}


class LiveClient(str, Enum):
    GATEWAY = "gateway"
    ANYTHINGLLM = "anythingllm"


@dataclass(frozen=True)
class SemiWellDefinedConfig:
    config_root: Path
    catalog_path: Path = DEFAULT_CATALOG_PATH
    manifest_path: Path = DEFAULT_MANIFEST_PATH
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    case_ids: tuple[str, ...] = ()
    clients: tuple[LiveClient, ...] = (LiveClient.GATEWAY, LiveClient.ANYTHINGLLM)
    live: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"semi-well-defined-prompts-{utc_timestamp()}.json"


def markdown_path_for(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def canonical_mnt_path(value: str | Path) -> str:
    normalized = str(value).replace("\\", "/").rstrip("/")
    lower = normalized.lower()
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        drive = normalized[0].lower()
        return f"/mnt/{drive}/{normalized[3:]}".lower()
    if lower.startswith("/mnt/"):
        return lower
    return lower


def fixture_id_for_case(case: PromptCatalogCase, entries: tuple[FixtureEntry, ...]) -> str:
    target = canonical_mnt_path(case.target_root)
    for entry in entries:
        if canonical_mnt_path(entry.source_path) == target:
            return entry.fixture_id
    raise RuntimeError(f"{case.case_id} target_root is not in runtime/fixtures.json: {case.target_root}")


def raw_cases_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = catalog.get("cases") if isinstance(catalog.get("cases"), list) else []
    return {str(item.get("case_id")): item for item in cases if isinstance(item, dict)}


def raw_boundary_cases(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    value = catalog.get("boundary_cases")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def fixture_by_id(entries: tuple[FixtureEntry, ...]) -> dict[str, FixtureEntry]:
    return {entry.fixture_id: entry for entry in entries}


def git_status_hash(root: Path) -> dict[str, Any] | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return {
        "clean": result.stdout == "",
        "line_count": len(result.stdout.splitlines()),
        "sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
    }


def fixture_state(entries: tuple[FixtureEntry, ...], fixture_ids: set[str]) -> dict[str, dict[str, Any]]:
    by_id = fixture_by_id(entries)
    state: dict[str, dict[str, Any]] = {}
    for fixture_id in sorted(fixture_ids):
        entry = by_id[fixture_id]
        state[fixture_id] = {
            "source_path": entry.source_path.as_posix(),
            "category": entry.category,
            "watched_hashes": fixture_watched_hashes(entry.source_path, entry.watched_paths),
            "git_status": git_status_hash(entry.source_path),
        }
    return state


def selected_cases(cases: tuple[PromptCatalogCase, ...], case_ids: tuple[str, ...]) -> tuple[PromptCatalogCase, ...]:
    if not case_ids:
        return cases
    by_id = {case.case_id: case for case in cases}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise RuntimeError("unknown semi-well-defined case id(s): " + ", ".join(missing))
    return tuple(by_id[case_id] for case_id in case_ids)


def router_rules(evidence: list[Any]) -> list[str]:
    return [
        str(item["rule"])
        for item in evidence
        if isinstance(item, dict) and item.get("source") == "router_rule" and isinstance(item.get("rule"), str)
    ]


def evaluate_route(case: PromptCatalogCase) -> dict[str, Any]:
    actual_workflow, status_reason, evidence = workflow_kind_for_request(case.prompt)
    rules = router_rules(evidence)
    actual_rule = rules[0] if rules else ""
    problems: list[str] = []
    if status_reason != "ready":
        problems.append(f"status_reason={status_reason}")
    if actual_workflow != case.expected_workflow:
        problems.append(f"workflow expected {case.expected_workflow} got {actual_workflow}")
    if actual_rule != case.expected_rule:
        problems.append(f"primary rule expected {case.expected_rule} got {actual_rule or 'none'}")
    return {
        "case_id": case.case_id,
        "status": "passed" if not problems else "failed",
        "expected_workflow": case.expected_workflow,
        "actual_workflow": actual_workflow,
        "expected_rule": case.expected_rule,
        "actual_rule": actual_rule,
        "all_rules": rules,
        "status_reason": status_reason,
        "problems": problems,
    }


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    for key in ("textResponse", "response", "message", "text"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    raise RuntimeError("response did not include assistant text")


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def semantic_result(case: PromptCatalogCase, text: str) -> dict[str, Any]:
    missing = sorted({marker for marker in case.semantic_markers if marker not in text})
    forbidden = sorted({marker for marker in case.forbidden_markers if marker in text})
    return {
        "status": "passed" if not missing and not forbidden else "failed",
        "missing_semantic_markers": missing,
        "forbidden_markers_found": forbidden,
        "required_semantic_markers": list(case.semantic_markers),
    }


def output_contract(case: PromptCatalogCase, text: str, common_markers: tuple[str, ...]) -> dict[str, Any]:
    markers = list(common_markers)
    markers.append(f"selected_workflow: {case.expected_workflow}")
    markers.append(case.expected_rule)
    markers.extend(case.expected_markers)
    if case.expected_skill_id:
        markers.append(case.expected_skill_id)
    if case.expected_artifact_key:
        markers.append(case.expected_artifact_key)
    missing = sorted({marker for marker in markers if marker not in text})
    return {
        "status": "passed" if not missing else "failed",
        "missing_markers": missing,
        "required_markers": markers,
    }


def dimension_scores(
    *,
    case: PromptCatalogCase,
    text: str,
    route_result: dict[str, Any],
    contract: dict[str, Any],
    semantic: dict[str, Any],
) -> dict[str, int]:
    semantic_required = list(case.semantic_markers)
    semantic_present = len(semantic_required) - len(semantic["missing_semantic_markers"])
    semantic_score = 100 if not semantic_required else int((semantic_present / len(semantic_required)) * 100)
    if semantic["forbidden_markers_found"]:
        semantic_score = 0
    route_score = 100 if route_result["status"] == "passed" and case.expected_rule in text else 0
    evidence_score = 100 if "Artifacts:" in text and (not case.expected_artifact_key or case.expected_artifact_key in text) else 0
    output_score = 100 if contract["status"] == "passed" else max(0, 100 - (20 * len(contract["missing_markers"])))
    verification_score = 100 if "- Verification:" in text and ("Recommended commands:" in text or "python -m pytest" in text) else 70
    safety_score = 100 if not semantic["forbidden_markers_found"] else 0
    diagnosability_score = 100 if run_id_from_text(text) != "unknown" and "Initial difference" not in text else 90
    return {
        "route_workflow_skill_tool_correctness": route_score,
        "evidence_grounding_and_artifact_quality": evidence_score,
        "semantic_correctness": semantic_score,
        "output_contract_and_chat_visible_markers": output_score,
        "verification_command_relevance": verification_score,
        "safety_approval_and_mutation_boundary": safety_score,
        "diagnosability": diagnosability_score,
    }


def weighted_score(category_scores: dict[str, int], policy: dict[str, Any]) -> int:
    dimensions = policy.get("score_rubric", {}).get("dimensions") if isinstance(policy.get("score_rubric"), dict) else []
    points_by_id = {
        str(item.get("id")): int(item.get("points"))
        for item in dimensions
        if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("points"), int)
    }
    total = sum(points_by_id.values()) or 100
    weighted = sum((category_scores.get(dimension_id, 0) * points) for dimension_id, points in points_by_id.items())
    return round(weighted / total)


def evaluate_text(
    *,
    case: PromptCatalogCase,
    text: str,
    route_result: dict[str, Any],
    common_markers: tuple[str, ...],
    policy: dict[str, Any],
) -> dict[str, Any]:
    contract = output_contract(case, text, common_markers)
    semantic = semantic_result(case, text)
    category_scores = dimension_scores(
        case=case,
        text=text,
        route_result=route_result,
        contract=contract,
        semantic=semantic,
    )
    score = weighted_score(category_scores, policy)
    difference_parts: list[str] = []
    if route_result["status"] != "passed":
        difference_parts.append("Route decision missed expected workflow or rule: " + "; ".join(route_result["problems"]))
    if contract["missing_markers"]:
        difference_parts.append("Response missed chat-visible markers: " + ", ".join(contract["missing_markers"]))
    if semantic["missing_semantic_markers"]:
        difference_parts.append("Response missed semantic concepts: " + ", ".join(semantic["missing_semantic_markers"]))
    if semantic["forbidden_markers_found"]:
        difference_parts.append("Response included forbidden concepts: " + ", ".join(semantic["forbidden_markers_found"]))
    case_minimum = int(policy.get("score_rubric", {}).get("stable_acceptance_case_minimum", 85))
    passed = route_result["status"] == "passed" and contract["status"] == "passed" and semantic["status"] == "passed" and score >= case_minimum
    return {
        "status": "passed" if passed else "failed",
        "score": score,
        "category_scores": category_scores,
        "case_minimum": case_minimum,
        "output_contract_status": contract["status"],
        "semantic_quality_status": semantic["status"],
        "missing_markers": contract["missing_markers"],
        "missing_semantic_markers": semantic["missing_semantic_markers"],
        "forbidden_markers_found": semantic["forbidden_markers_found"],
        "required_semantic_markers": semantic["required_semantic_markers"],
        "run_id": run_id_from_text(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
        "text_sample": text[:1600],
        "initial_difference": "No deterministic difference from the baseline target." if not difference_parts else " ".join(difference_parts),
        "suggested_prompt_if_missed": "" if passed else (case.refined_prompt or case.miss_suggestion),
        "refined_prompt": case.refined_prompt,
        "prompt_risk": case.prompt_risk,
    }


def run_gateway_case(config: SemiWellDefinedConfig, case: PromptCatalogCase) -> tuple[int, dict[str, Any]]:
    return json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": case.prompt}],
        },
        timeout_seconds=config.timeout_seconds,
    )


def run_anythingllm_case(config: SemiWellDefinedConfig, case: PromptCatalogCase, api_key: str) -> tuple[int, dict[str, Any]]:
    return json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": case.prompt,
            "mode": "chat",
            "sessionId": f"semi-well-defined-{case.case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )


def evaluate_boundary_cases(catalog: dict[str, Any], entries: tuple[FixtureEntry, ...]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    by_id = fixture_by_id(entries)
    for index, item in enumerate(raw_boundary_cases(catalog)):
        case_id = str(item.get("case_id") or f"B{index + 1:02d}")
        prompt_template = item.get("prompt")
        expected_status_reason = item.get("expected_status_reason")
        expected_rule = item.get("expected_rule")
        fixture_id = item.get("fixture_id")
        problems: list[str] = []
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            problems.append("prompt must be a non-empty string")
            prompt_template = ""
        if not isinstance(expected_status_reason, str) or not expected_status_reason.strip():
            problems.append("expected_status_reason must be a non-empty string")
            expected_status_reason = ""
        if not isinstance(expected_rule, str) or not expected_rule.strip():
            problems.append("expected_rule must be a non-empty string")
            expected_rule = ""
        if not isinstance(fixture_id, str) or fixture_id not in by_id:
            problems.append("fixture_id must reference runtime/fixtures.json")
            target_root = ""
        else:
            target_root = by_id[fixture_id].source_path.as_posix()
        prompt = prompt_template.format(target_root=target_root) if prompt_template else ""
        workflow, status_reason, evidence = workflow_kind_for_request(prompt)
        rules = router_rules(evidence)
        actual_rule = rules[0] if rules else ""
        if status_reason != expected_status_reason:
            problems.append(f"status_reason expected {expected_status_reason} got {status_reason}")
        if actual_rule != expected_rule:
            problems.append(f"rule expected {expected_rule} got {actual_rule or 'none'}")
        if workflow is not None:
            problems.append(f"boundary case must not select a workflow, got {workflow}")
        results.append(
            {
                "case_id": case_id,
                "status": "passed" if not problems else "failed",
                "prompt": prompt,
                "fixture_id": fixture_id,
                "expected_status_reason": expected_status_reason,
                "actual_status_reason": status_reason,
                "expected_rule": expected_rule,
                "actual_rule": actual_rule,
                "selected_workflow": workflow,
                "problems": problems,
            }
        )
    return results


def live_case(
    *,
    config: SemiWellDefinedConfig,
    case: PromptCatalogCase,
    client: LiveClient,
    api_key: str,
    route_result: dict[str, Any],
    common_markers: tuple[str, ...],
    policy: dict[str, Any],
) -> dict[str, Any]:
    status, body = (
        run_gateway_case(config, case)
        if client == LiveClient.GATEWAY
        else run_anythingllm_case(config, case, api_key)
    )
    base = {
        "client": client.value,
        "case_id": case.case_id,
        "target_root": case.target_root,
        "prompt": case.prompt,
        "baseline_target": case.baseline_target,
        "expected_workflow": case.expected_workflow,
        "expected_rule": case.expected_rule,
        "expected_skill_id": case.expected_skill_id,
        "expected_artifact_key": case.expected_artifact_key,
        "http_status": status,
        "route_decision": route_result,
    }
    if status != 200:
        return {
            **base,
            "status": "failed",
            "score": 0,
            "initial_difference": f"{client.value} returned HTTP {status}.",
            "suggested_prompt_if_missed": case.refined_prompt or case.miss_suggestion,
            "body": body,
        }
    text = text_response(body)
    return {
        **base,
        **evaluate_text(case=case, text=text, route_result=route_result, common_markers=common_markers, policy=policy),
    }


def validate_catalog_contract(
    *,
    config_root: Path,
    catalog: dict[str, Any],
    cases: tuple[PromptCatalogCase, ...],
    entries: tuple[FixtureEntry, ...],
) -> list[str]:
    errors = validate_prompt_catalog(catalog)
    if catalog.get("catalog_id") != "semi_well_defined_v1":
        errors.append("catalog_id must be semi_well_defined_v1")
    if not 20 <= len(cases) <= 30:
        errors.append("semi-well-defined suite must contain 20 to 30 cases")
    fixture_ids = {fixture_id_for_case(case, entries) for case in cases}
    missing_coinbase = sorted(REQUIRED_COINBASE_FIXTURES - fixture_ids)
    if missing_coinbase:
        errors.append("suite must include both frozen Coinbase fixtures; missing " + ", ".join(missing_coinbase))
    by_id = fixture_by_id(entries)
    non_coinbase = [fixture_id for fixture_id in fixture_ids if by_id[fixture_id].category.startswith("synthetic-")]
    if not non_coinbase:
        errors.append("suite must include at least one representative non-Coinbase fixture")
    raw_by_id = raw_cases_by_id(catalog)
    variant_types: set[str] = set()
    required_count = 0
    holdout_count = 0
    founder_prompts: set[str] = set()
    try:
        founder_catalog = load_prompt_catalog(config_root, DEFAULT_FOUNDER_FIELD_CATALOG)
        founder_prompts = {
            str(item.get("prompt", "")).strip()
            for item in founder_catalog.get("cases", [])
            if isinstance(item, dict)
        }
    except Exception:  # noqa: BLE001
        founder_prompts = set()
    for case in cases:
        raw_case = raw_by_id.get(case.case_id, {})
        variant_type = raw_case.get("variant_type")
        if not isinstance(variant_type, str) or variant_type not in REQUIRED_VARIANT_TYPES:
            errors.append(f"{case.case_id} variant_type must be one of {sorted(REQUIRED_VARIANT_TYPES)}")
        else:
            variant_types.add(variant_type)
        fixture_id = raw_case.get("fixture_id")
        if not isinstance(fixture_id, str) or fixture_id != fixture_id_for_case(case, entries):
            errors.append(f"{case.case_id} fixture_id must match target_root fixture")
        if not isinstance(raw_case.get("supported_capability"), str) or not raw_case["supported_capability"].strip():
            errors.append(f"{case.case_id} supported_capability must be a non-empty string")
        if raw_case.get("required") is True:
            required_count += 1
        if raw_case.get("holdout") is True:
            holdout_count += 1
        safety = raw_case.get("safety_expectation")
        if safety not in VALID_SAFETY_EXPECTATIONS:
            errors.append(f"{case.case_id} safety_expectation must be one of {sorted(VALID_SAFETY_EXPECTATIONS)}")
        if not isinstance(raw_case.get("evaluator_rubric"), dict) or not raw_case["evaluator_rubric"]:
            errors.append(f"{case.case_id} evaluator_rubric must be a non-empty object")
        if case.prompt.strip() in founder_prompts:
            errors.append(f"{case.case_id} prompt must not be an exact copy of a founder-field prompt")
        prompt_lower = case.prompt.lower()
        found_internal_terms = [term for term in INTERNAL_PROMPT_TERMS if term.lower() in prompt_lower]
        if found_internal_terms:
            errors.append(f"{case.case_id} prompt contains internal workflow/tool terms: {found_internal_terms}")
        if case.expected_rule not in case.expected_markers and case.expected_rule not in case.semantic_markers:
            errors.append(f"{case.case_id} must require the expected route rule as a visible marker")
        if not case.expected_artifact_key:
            errors.append(f"{case.case_id} must declare expected_artifact_key for artifact proof")
    missing_variants = sorted(REQUIRED_VARIANT_TYPES - variant_types)
    if missing_variants:
        errors.append("suite missing required variant types: " + ", ".join(missing_variants))
    if required_count < 12:
        errors.append("suite must mark at least 12 cases as required")
    if holdout_count < 4:
        errors.append("suite must mark at least 4 cases as holdout")
    boundary_results = evaluate_boundary_cases(catalog, entries)
    if len(boundary_results) < 2:
        errors.append("suite must include at least two boundary_cases")
    for item in boundary_results:
        if item["status"] != "passed":
            errors.append(f"boundary case {item['case_id']} failed: {item['problems']}")
    return errors


def build_offline_report(
    *,
    config_root: Path,
    catalog_path: Path,
    manifest_path: Path,
    policy_path: Path,
    case_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    catalog = load_prompt_catalog(config_root, catalog_path)
    all_cases = prompt_cases_from_catalog(catalog)
    cases = selected_cases(all_cases, case_ids)
    manifest = load_fixture_manifest(config_root, manifest_path)
    entries = fixture_entries(config_root, manifest)
    policy = read_json_object(resolve_path(config_root, policy_path))
    catalog_errors = validate_catalog_contract(config_root=config_root, catalog=catalog, cases=all_cases, entries=entries)
    route_results = [evaluate_route(case) for case in cases]
    route_failures = [item for item in route_results if item["status"] != "passed"]
    boundary_results = evaluate_boundary_cases(catalog, entries)
    boundary_failures = [item for item in boundary_results if item["status"] != "passed"]
    status = "passed" if not catalog_errors and not route_failures and not boundary_failures else "failed"
    fixture_ids = {fixture_id_for_case(case, entries) for case in cases}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "semi_well_defined_prompt_generalization_report",
        "status": status,
        "mode": "offline",
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "catalog_path": str(resolve_path(config_root, catalog_path)),
        "policy_path": str(resolve_path(config_root, policy_path)),
        "thresholds": {
            "stable_mean_minimum": policy.get("score_rubric", {}).get("stable_acceptance_mean_minimum"),
            "stable_case_minimum": policy.get("score_rubric", {}).get("stable_acceptance_case_minimum"),
        },
        "summary": {
            "case_count": len(cases),
            "catalog_case_count": len(all_cases),
            "route_passed": len(route_results) - len(route_failures),
            "route_failed": len(route_failures),
            "boundary_passed": len(boundary_results) - len(boundary_failures),
            "boundary_failed": len(boundary_failures),
            "catalog_error_count": len(catalog_errors),
            "fixture_ids": sorted(fixture_ids),
        },
        "catalog_errors": catalog_errors,
        "route_results": route_results,
        "boundary_results": boundary_results,
        "cases": [
            {
                "case_id": case.case_id,
                "prompt": case.prompt,
                "target_root": case.target_root,
                "baseline_target": case.baseline_target,
                "expected_workflow": case.expected_workflow,
                "expected_rule": case.expected_rule,
                "expected_artifact_key": case.expected_artifact_key,
                "tags": list(case.tags),
            }
            for case in cases
        ],
        "errors": catalog_errors
        + [problem for item in route_failures for problem in item["problems"]]
        + [problem for item in boundary_failures for problem in item["problems"]],
    }


def validate_semi_well_defined_prompts(config: SemiWellDefinedConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    catalog_path = resolve_path(config_root, config.catalog_path)
    manifest_path = resolve_path(config_root, config.manifest_path)
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root)
    markdown_path = config.markdown_output_path or markdown_path_for(output_path)
    if not config.live:
        report = build_offline_report(
            config_root=config_root,
            catalog_path=catalog_path,
            manifest_path=manifest_path,
            policy_path=policy_path,
            case_ids=config.case_ids,
        )
        write_json(output_path, report)
        write_markdown(markdown_path, report)
        return report

    report = build_offline_report(
        config_root=config_root,
        catalog_path=catalog_path,
        manifest_path=manifest_path,
        policy_path=policy_path,
        case_ids=config.case_ids,
    )
    report["mode"] = "live"
    report["anythingllm_api_base_url"] = config.anythingllm_api_base_url
    report["workflow_router_gateway_base_url"] = config.workflow_router_gateway_base_url
    report["workspace"] = config.workspace
    report["clients"] = [client.value for client in config.clients]
    report["live_results"] = []
    report["fixture_state_before"] = {}
    report["fixture_state_after"] = {}
    if report["status"] != "passed":
        write_json(output_path, report)
        write_markdown(markdown_path, report)
        return report
    try:
        catalog = load_prompt_catalog(config_root, catalog_path)
        common_markers = tuple(catalog["common_format_a_markers"])
        policy = read_json_object(policy_path)
        all_cases = prompt_cases_from_catalog(catalog)
        cases = selected_cases(all_cases, config.case_ids)
        manifest = load_fixture_manifest(config_root, manifest_path)
        entries = fixture_entries(config_root, manifest)
        fixture_ids = {fixture_id_for_case(case, entries) for case in cases}
        report["fixture_state_before"] = fixture_state(entries, fixture_ids)
        api_key = ""
        if LiveClient.ANYTHINGLLM in config.clients:
            api_key = os.environ.get(config.api_key_env) or ""
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM live validation")
        route_by_case = {item["case_id"]: item for item in report["route_results"]}
        for case in cases:
            for client in config.clients:
                item = live_case(
                    config=config,
                    case=case,
                    client=client,
                    api_key=api_key,
                    route_result=route_by_case[case.case_id],
                    common_markers=common_markers,
                    policy=policy,
                )
                report["live_results"].append(item)
                print(
                    "SEMI WELL DEFINED {client} {case_id} {status} score={score} run_id={run_id}".format(
                        client=client.value,
                        case_id=case.case_id,
                        status=item.get("status", "failed").upper(),
                        score=item.get("score", 0),
                        run_id=item.get("run_id", "unknown"),
                    )
                )
        report["fixture_state_after"] = fixture_state(entries, fixture_ids)
        if report["fixture_state_after"] != report["fixture_state_before"]:
            raise RuntimeError("semi-well-defined prompt suite changed protected fixture state")
        results = [item for item in report["live_results"] if isinstance(item, dict)]
        scores = [int(item.get("score", 0)) for item in results]
        failed = [item for item in results if item.get("status") != "passed"]
        mean_score = round(sum(scores) / len(scores), 2) if scores else 0
        policy_rubric = policy.get("score_rubric") if isinstance(policy.get("score_rubric"), dict) else {}
        mean_minimum = int(policy_rubric.get("stable_acceptance_mean_minimum", 90))
        case_minimum = int(policy_rubric.get("stable_acceptance_case_minimum", 85))
        report["summary"].update(
            {
                "client_case_count": len(results),
                "live_passed": len(results) - len(failed),
                "live_failed": len(failed),
                "mean_score": mean_score,
                "minimum_score": min(scores) if scores else 0,
                "stable_mean_minimum": mean_minimum,
                "stable_case_minimum": case_minimum,
                "fixture_unchanged": True,
            }
        )
        if mean_score < mean_minimum:
            report["errors"].append(f"mean_score {mean_score} below stable threshold {mean_minimum}")
        below_case_minimum = [item["case_id"] + ":" + item["client"] for item in results if int(item.get("score", 0)) < case_minimum]
        if below_case_minimum:
            report["errors"].append("case scores below stable threshold: " + ", ".join(below_case_minimum))
        if failed:
            report["errors"].append("live failed cases: " + ", ".join(item["case_id"] + ":" + item["client"] for item in failed))
        report["status"] = "passed" if not report["errors"] else "failed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["status"] = "failed"
    write_json(output_path, report)
    write_markdown(markdown_path, report)
    return report


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Semi-Well-Defined Prompt Generalization",
        "",
        f"- Status: {report.get('status')}",
        f"- Mode: {report.get('mode')}",
        f"- Created at: {report.get('created_at')}",
        f"- Catalog: `{report.get('catalog_path')}`",
        f"- Case count: {summary.get('case_count')}",
        f"- Client case count: {summary.get('client_case_count', 0)}",
        f"- Mean score: {summary.get('mean_score', 'not_run')}",
        f"- Minimum score: {summary.get('minimum_score', 'not_run')}",
        f"- Fixture unchanged: {summary.get('fixture_unchanged', 'not_run')}",
        "",
        "## Live Results",
        "",
        "| Client | Case | Status | Score | Expected workflow | Expected rule | Run ID | Initial difference | Suggestion |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("live_results") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {client} | {case_id} | {status} | {score} | {workflow} | {rule} | {run_id} | {difference} | {suggestion} |".format(
                client=item.get("client", ""),
                case_id=item.get("case_id", ""),
                status=item.get("status", ""),
                score=item.get("score", ""),
                workflow=item.get("expected_workflow", ""),
                rule=item.get("expected_rule", ""),
                run_id=item.get("run_id", ""),
                difference=str(item.get("initial_difference", "")).replace("\n", " ")[:500],
                suggestion=str(item.get("suggested_prompt_if_missed", "")).replace("\n", " ")[:300],
            )
        )
    lines.extend(["", "## Route Matrix", ""])
    lines.append("| Case | Status | Expected workflow | Actual workflow | Expected rule | Actual rule | Problems |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in report.get("route_results") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {case_id} | {status} | {expected_workflow} | {actual_workflow} | {expected_rule} | {actual_rule} | {problems} |".format(
                case_id=item.get("case_id", ""),
                status=item.get("status", ""),
                expected_workflow=item.get("expected_workflow", ""),
                actual_workflow=item.get("actual_workflow", ""),
                expected_rule=item.get("expected_rule", ""),
                actual_rule=item.get("actual_rule", ""),
                problems="; ".join(item.get("problems") or []),
            )
        )
    lines.extend(["", "## Boundary Cases", ""])
    lines.append("| Case | Status | Expected reason | Actual reason | Expected rule | Actual rule | Problems |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in report.get("boundary_results") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| {case_id} | {status} | {expected_reason} | {actual_reason} | {expected_rule} | {actual_rule} | {problems} |".format(
                case_id=item.get("case_id", ""),
                status=item.get("status", ""),
                expected_reason=item.get("expected_status_reason", ""),
                actual_reason=item.get("actual_status_reason", ""),
                expected_rule=item.get("expected_rule", ""),
                actual_rule=item.get("actual_rule", ""),
                problems="; ".join(item.get("problems") or []),
            )
        )
    lines.extend(["", "## Cases", ""])
    for item in report.get("cases") or []:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"### {item.get('case_id')}",
                "",
                f"Prompt: {item.get('prompt')}",
                "",
                f"Baseline target: {item.get('baseline_target')}",
                "",
                f"Expected workflow: `{item.get('expected_workflow')}`",
                "",
                f"Expected rule: `{item.get('expected_rule')}`",
                "",
                f"Expected artifact: `{item.get('expected_artifact_key')}`",
                "",
            ]
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- {error}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
