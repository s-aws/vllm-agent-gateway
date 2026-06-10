"""Small live smoke probe for detecting localhost model swaps."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.current_model_compatibility_matrix import (
    CurrentModelCompatibilityMatrixConfig,
    run_current_model_compatibility_matrix,
)
from vllm_agent_gateway.acceptance.model_portability import bounded_text, openai_base_url, probe_model_base_url
from vllm_agent_gateway.acceptance.v1 import DEFAULT_MODEL_BASE_URL, HEALTH_TARGETS, health_check


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "model_swap_smoke_probe_policy"
EXPECTED_REPORT_KIND = "model_swap_smoke_probe_report"
EXPECTED_PHASE = 154
DEFAULT_POLICY_PATH = Path("runtime") / "model_swap_smoke_probe_policy.json"
DEFAULT_CURRENT_MODEL_POLICY_PATH = Path("runtime") / "current_model_compatibility_matrix_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "model-swap-smoke-probe" / "phase154"
REQUIRED_LIVE_PROBES = {"model_metadata", "model_generation", "harness_health"}
REQUIRED_ARTIFACT_GATES = {"current_model_compatibility_matrix"}
REQUIRED_HEALTH_TARGETS = {"model", "llm_gateway", "workflow_router_gateway", "controller"}
DECISION_VALUES = {
    "current_model_ready",
    "model_swap_requires_drift",
    "fix_model_backend",
    "fix_harness",
    "fix_model_generation",
    "refresh_current_model_evidence",
}


class ModelSwapSmokeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


ModelProbeReader = Callable[[str, int], dict[str, Any]]
GenerationProbeRunner = Callable[[str, str, int, int], dict[str, Any]]
HealthReader = Callable[[int], list[dict[str, Any]]]
CompatibilityRunner = Callable[[CurrentModelCompatibilityMatrixConfig], dict[str, Any]]


@dataclass(frozen=True)
class ModelSwapSmokeProbeConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    current_model_policy_path: Path = DEFAULT_CURRENT_MODEL_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    candidate_model_base_url: str = DEFAULT_MODEL_BASE_URL
    timeout_seconds: int = 120
    compatibility_output_path: Path | None = None
    compatibility_markdown_output_path: Path | None = None
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"model-swap-smoke-probe-{utc_timestamp()}.json"


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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 154")
    if policy.get("current_model_policy_path") != DEFAULT_CURRENT_MODEL_POLICY_PATH.as_posix():
        errors.append("policy.current_model_policy_path must point at the current-model compatibility policy")
    if policy.get("candidate_model_base_url") != DEFAULT_MODEL_BASE_URL:
        errors.append("policy.candidate_model_base_url must be http://127.0.0.1:8000/v1")
    if policy.get("exact_model_id_match_required_for_no_drift") is not True:
        errors.append("policy.exact_model_id_match_required_for_no_drift must be true")
    if set(string_list(policy.get("required_live_probes"))) != REQUIRED_LIVE_PROBES:
        errors.append("policy.required_live_probes must be model_metadata, model_generation, and harness_health")
    if set(string_list(policy.get("required_existing_artifact_gates"))) != REQUIRED_ARTIFACT_GATES:
        errors.append("policy.required_existing_artifact_gates must be current_model_compatibility_matrix")
    if set(string_list(policy.get("required_health_targets"))) != REQUIRED_HEALTH_TARGETS:
        errors.append("policy.required_health_targets must be model, llm_gateway, workflow_router_gateway, and controller")
    generation = dict_value(policy.get("generation_probe"))
    if not isinstance(generation.get("prompt"), str) or "SMOKE_OK" not in generation.get("prompt", ""):
        errors.append("policy.generation_probe.prompt must ask for SMOKE_OK")
    if generation.get("required_non_empty_content") is not True:
        errors.append("policy.generation_probe.required_non_empty_content must be true")
    if not isinstance(generation.get("max_tokens"), int) or int(generation.get("max_tokens", 0)) <= 0:
        errors.append("policy.generation_probe.max_tokens must be a positive integer")
    next_gate = dict_value(policy.get("next_gate_by_decision"))
    if set(next_gate) != {
        "current_model_ready",
        "model_swap_requires_drift",
        "fix_model_backend",
        "fix_harness",
        "fix_model_generation",
        "refresh_current_model_evidence",
    }:
        errors.append("policy.next_gate_by_decision must define the governed decision mappings")
    forbidden = " ".join(string_list(policy.get("must_not"))).lower()
    for phrase in ("mutate model capability profile", "change runtime routing", "automatic model selection"):
        if phrase not in forbidden:
            errors.append(f"policy.must_not must include {phrase}")
    return errors


def expected_model_ids(current_model_policy: dict[str, Any]) -> list[str]:
    return string_list(dict_value(current_model_policy.get("current_model")).get("expected_model_ids"))


def direct_generation_probe(
    base_url: str,
    model_id: str,
    timeout_seconds: int,
    max_tokens: int,
) -> dict[str, Any]:
    url = f"{openai_base_url(base_url)}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a health checker. Reply briefly."},
            {"role": "user", "content": "Reply with SMOKE_OK."},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            body = json.loads(body_text)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        return {
            "status": ModelSwapSmokeStatus.FAILED.value,
            "url": url,
            "model_id": model_id,
            "http_status": exc.code,
            "error": bounded_text(body_text),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": ModelSwapSmokeStatus.FAILED.value,
            "url": url,
            "model_id": model_id,
            "error": f"{type(exc).__name__}: {bounded_text(exc)}",
        }
    content = ""
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            content = message["content"].strip()
    return {
        "status": ModelSwapSmokeStatus.PASSED.value if content else ModelSwapSmokeStatus.FAILED.value,
        "url": url,
        "model_id": model_id,
        "http_status": response.status,
        "content_sample": bounded_text(content, limit=240),
        "content_length": len(content),
        "raw_kind": body.get("object") if isinstance(body, dict) else "",
    }


def compatibility_report_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}-current-model-compatibility.json")


def compatibility_markdown_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}-current-model-compatibility.md")


def required_health_results(health_results: list[dict[str, Any]], required_targets: set[str]) -> list[dict[str, Any]]:
    return [item for item in health_results if str(item.get("name")) in required_targets]


def health_ready(health_results: list[dict[str, Any]], required_targets: set[str]) -> bool:
    by_name = {str(item.get("name")): item for item in health_results}
    return all(by_name.get(name, {}).get("status") == ModelSwapSmokeStatus.PASSED.value for name in required_targets)


def model_swap_detected(expected_ids: list[str], actual_ids: list[str]) -> bool:
    return set(expected_ids) != set(actual_ids)


def build_decision(
    *,
    expected_ids: list[str],
    model_probe: dict[str, Any],
    generation_probe: dict[str, Any],
    health_results: list[dict[str, Any]],
    compatibility_report: dict[str, Any],
) -> dict[str, Any]:
    actual_ids = string_list(model_probe.get("model_ids"))
    probe_passed = model_probe.get("status") == ModelSwapSmokeStatus.PASSED.value and bool(actual_ids)
    generation_passed = generation_probe.get("status") == ModelSwapSmokeStatus.PASSED.value
    required_health = required_health_results(health_results, REQUIRED_HEALTH_TARGETS)
    harness_passed = health_ready(health_results, REQUIRED_HEALTH_TARGETS)
    compatibility_passed = compatibility_report.get("status") == ModelSwapSmokeStatus.PASSED.value
    swap_detected = model_swap_detected(expected_ids, actual_ids)
    if not probe_passed:
        decision = "fix_model_backend"
        status = ModelSwapSmokeStatus.FAILED.value
        delta = "Model metadata is unavailable; fix localhost:8000 before judging chat quality."
    elif not harness_passed:
        decision = "fix_harness"
        status = ModelSwapSmokeStatus.FAILED.value
        delta = "Harness health failed; fix gateway/controller/proxy readiness before blaming model quality."
    elif not generation_passed:
        decision = "fix_model_generation"
        status = ModelSwapSmokeStatus.FAILED.value
        delta = "Model metadata is reachable but direct generation failed; fix backend generation before chat-quality testing."
    elif not compatibility_passed:
        decision = "refresh_current_model_evidence"
        status = ModelSwapSmokeStatus.FAILED.value
        delta = "Current compatibility artifacts are not passing; refresh evidence before release decisions."
    elif swap_detected:
        decision = "model_swap_requires_drift"
        status = ModelSwapSmokeStatus.PASSED.value
        delta = "Actual localhost model ids differ from the approved baseline; chat-quality delta is unknown until full drift and portability gates pass."
    else:
        decision = "current_model_ready"
        status = ModelSwapSmokeStatus.PASSED.value
        delta = "No model-id swap detected; no model-swap-specific chat-quality delta is expected."
    return {
        "status": status,
        "decision": decision,
        "expected_model_ids": expected_ids,
        "actual_model_ids": actual_ids,
        "model_swap_detected": swap_detected,
        "harness_health_passed": harness_passed,
        "required_health_results": required_health,
        "generation_probe_passed": generation_passed,
        "compatibility_artifacts_passed": compatibility_passed,
        "full_drift_gate_required": decision == "model_swap_requires_drift",
        "model_portability_gate_required": decision == "model_swap_requires_drift",
        "expected_chat_quality_delta": delta,
        "next_gate": {
            "current_model_ready": "none",
            "model_swap_requires_drift": "scripts/validate_fresh_local_model_drift.py and scripts/validate_model_portability.py",
            "fix_model_backend": "fix localhost:8000 before judging chat quality",
            "fix_harness": "restart gateway/controller/proxies before judging model quality",
            "fix_model_generation": "fix localhost:8000 generation before judging chat quality",
            "refresh_current_model_evidence": "refresh current-model compatibility artifacts before release decision",
        }[decision],
    }


def markdown_report(report: dict[str, Any]) -> str:
    decision = dict_value(report.get("decision"))
    lines = [
        "# Model Swap Smoke Probe",
        "",
        f"- Status: {report.get('status')}",
        f"- Decision: {decision.get('decision')}",
        f"- Expected model ids: {', '.join(string_list(decision.get('expected_model_ids'))) or 'none'}",
        f"- Actual model ids: {', '.join(string_list(decision.get('actual_model_ids'))) or 'none'}",
        f"- Full drift gate required: {decision.get('full_drift_gate_required')}",
        f"- Next gate: {decision.get('next_gate')}",
        "",
        "## Expected Chat-Quality Delta",
        "",
        str(decision.get("expected_chat_quality_delta") or ""),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def run_model_swap_smoke_probe(
    config: ModelSwapSmokeProbeConfig,
    *,
    model_probe_reader: ModelProbeReader = probe_model_base_url,
    generation_probe_runner: GenerationProbeRunner = direct_generation_probe,
    health_reader: HealthReader = health_check,
    compatibility_runner: CompatibilityRunner = run_current_model_compatibility_matrix,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    policy_path = resolve_path(config_root, config.policy_path)
    current_model_policy_path = resolve_path(config_root, config.current_model_policy_path)
    policy = read_json_object(policy_path)
    current_policy = read_json_object(current_model_policy_path)
    policy_errors = validate_policy(policy)
    expected_ids = expected_model_ids(current_policy)
    model_probe = model_probe_reader(config.candidate_model_base_url, min(30, config.timeout_seconds))
    actual_ids = string_list(model_probe.get("model_ids"))
    max_tokens = int(dict_value(policy.get("generation_probe")).get("max_tokens") or 16)
    generation = (
        generation_probe_runner(config.candidate_model_base_url, actual_ids[0], min(60, config.timeout_seconds), max_tokens)
        if actual_ids
        else {
            "status": ModelSwapSmokeStatus.FAILED.value,
            "error": "generation probe skipped because model metadata returned no model ids",
            "model_id": None,
        }
    )
    health_results = health_reader(min(30, config.timeout_seconds))
    compatibility_output = config.compatibility_output_path or compatibility_report_path(output_path)
    compatibility_markdown = config.compatibility_markdown_output_path or compatibility_markdown_path(output_path)
    compatibility_report = compatibility_runner(
        CurrentModelCompatibilityMatrixConfig(
            config_root=config_root,
            output_path=compatibility_output,
            markdown_output_path=compatibility_markdown,
            require_artifacts=config.require_artifacts,
        )
    )
    decision = build_decision(
        expected_ids=expected_ids,
        model_probe=model_probe,
        generation_probe=generation,
        health_results=health_results,
        compatibility_report=compatibility_report,
    )
    errors = list(policy_errors)
    if not expected_ids:
        errors.append("current_model_policy expected_model_ids must be non-empty")
    if decision["status"] == ModelSwapSmokeStatus.FAILED.value:
        errors.append(decision["expected_chat_quality_delta"])
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "status": ModelSwapSmokeStatus.PASSED.value
        if not errors
        else ModelSwapSmokeStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path),
        "current_model_policy_path": str(current_model_policy_path),
        "candidate_model_base_url": config.candidate_model_base_url,
        "policy_errors": policy_errors,
        "model_probe": model_probe,
        "generation_probe": generation,
        "health_results": health_results,
        "compatibility_report": {
            "status": compatibility_report.get("status"),
            "report_path": compatibility_report.get("report_path"),
            "markdown_report_path": compatibility_report.get("markdown_report_path"),
            "summary": compatibility_report.get("summary", {}),
            "blocker_count": len(object_list(compatibility_report.get("blockers"))),
            "error_count": len(string_list(compatibility_report.get("errors"))),
        },
        "decision": decision,
        "errors": errors,
        "summary": {
            "decision": decision["decision"],
            "model_swap_detected": decision["model_swap_detected"],
            "full_drift_gate_required": decision["full_drift_gate_required"],
            "model_portability_gate_required": decision["model_portability_gate_required"],
            "harness_health_passed": decision["harness_health_passed"],
            "generation_probe_passed": decision["generation_probe_passed"],
            "compatibility_artifacts_passed": decision["compatibility_artifacts_passed"],
            "error_count": len(errors),
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if config.markdown_output_path:
        write_text(config.markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(config.markdown_output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        write_text(config.markdown_output_path, markdown_report(report))
    return report
