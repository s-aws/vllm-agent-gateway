"""Model portability acceptance helpers.

Phase 72 does not change router behavior. It reruns or classifies the existing
V1 acceptance report for a named model candidate and records whether failures
look like model quality, classifier, prompt, harness, or unknown issues.
"""

from __future__ import annotations

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

from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    V1AcceptanceConfig,
    run_v1_acceptance,
)


DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_REPORT_DIR = Path("runtime-state") / "model-portability"
MAX_MESSAGE_CHARS = 1200


class ModelPortabilityIssue(str, Enum):
    MODEL_QUALITY = "model_quality"
    CLASSIFIER = "classifier"
    PROMPT = "prompt"
    HARNESS = "harness"
    UNKNOWN = "unknown"


CLASSIFICATION_TERMS: dict[ModelPortabilityIssue, tuple[str, ...]] = {
    ModelPortabilityIssue.HARNESS: (
        "anythingllm_api_key",
        "anythingllm preflight failed",
        "health check failed",
        "timed out",
        "timeout",
        "body bytes",
        "winerror 10055",
        "connection refused",
        "http ",
        "missing_report_path",
        "failed_to_load",
        "changed protected fixture state",
        "fixture state",
        "not readable",
        "workspace",
    ),
    ModelPortabilityIssue.CLASSIFIER: (
        "wrong workflow",
        "selected wrong workflow",
        "expected workflow",
        "expected_workflow",
        "expected rule",
        "expected_rule",
        "route miss",
        "routing miss",
        "classifier",
        "selected_workflow",
        "route rule",
    ),
    ModelPortabilityIssue.PROMPT: (
        "prompt ambiguity",
        "prompt_risk",
        "refined_prompt",
        "suggested_prompt_if_missed",
        "miss_suggestion",
        "ambiguous",
        "permits more than one",
    ),
    ModelPortabilityIssue.MODEL_QUALITY: (
        "semantic_quality",
        "semantic quality",
        "missing_semantic_markers",
        "missing semantic",
        "forbidden_markers",
        "forbidden answer",
        "model route output",
        "invalid_model_route",
        "jsondecodeerror",
        "not valid json",
        "malformed",
        "schema",
        "model_router_status",
    ),
}


NEXT_ACTION_BY_ISSUE: dict[ModelPortabilityIssue, str] = {
    ModelPortabilityIssue.MODEL_QUALITY: (
        "Keep the harness unchanged and inspect the failed prompt output; prefer smaller context, clearer "
        "artifact rendering, or a stronger model profile before changing deterministic router rules."
    ),
    ModelPortabilityIssue.CLASSIFIER: (
        "Inspect route-decision artifacts and prompt-matrix coverage; fix deterministic route rules or "
        "classifier guidance only if the prompt target is unambiguous."
    ),
    ModelPortabilityIssue.PROMPT: (
        "Record the miss as prompt ambiguity and test the refined prompt before changing router behavior."
    ),
    ModelPortabilityIssue.HARNESS: (
        "Fix runtime setup, ports, AnythingLLM configuration, fixture state, or report loading before "
        "judging model quality."
    ),
    ModelPortabilityIssue.UNKNOWN: (
        "Open the referenced acceptance report or suite output and add a narrower classification rule if "
        "the evidence repeats."
    ),
}


@dataclass(frozen=True)
class ModelPortabilityConfig:
    config_root: Path
    candidate_id: str
    candidate_description: str = ""
    candidate_model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    timeout_seconds: int = 900
    command_timeout_seconds: int = 1800
    output_path: Path | None = None
    acceptance_output_path: Path | None = None
    acceptance_report_path: Path | None = None
    python_executable: str | None = None
    skip_live_acceptance: bool = False
    skip_model_probe: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"model-portability-{utc_timestamp()}.json"


def default_acceptance_report_path(report_path: Path) -> Path:
    return report_path.parent / f"{report_path.stem}-v1-acceptance.json"


def openai_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/v1") else f"{value}/v1"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bounded_text(value: object, *, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 32] + "...[truncated]"


def probe_model_base_url(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    url = f"{openai_base_url(base_url)}/models"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            body = json.loads(body_text)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "url": url,
            "http_status": exc.code,
            "error": bounded_text(body_text),
            "model_ids": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "url": url,
            "error": f"{type(exc).__name__}: {bounded_text(exc)}",
            "model_ids": [],
        }
    data = body.get("data") if isinstance(body, dict) else None
    model_ids = [
        item["id"]
        for item in data or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    return {
        "status": "passed",
        "url": url,
        "http_status": response.status,
        "model_ids": model_ids,
        "raw_kind": body.get("object") if isinstance(body, dict) else "",
    }


def load_json_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"report root must be an object: {path}")
    return value


def matched_terms(text: str, issue: ModelPortabilityIssue) -> list[str]:
    lowered = text.lower()
    return [term for term in CLASSIFICATION_TERMS[issue] if term in lowered]


def classify_message(message: str) -> tuple[ModelPortabilityIssue, list[str]]:
    for issue in (
        ModelPortabilityIssue.HARNESS,
        ModelPortabilityIssue.CLASSIFIER,
        ModelPortabilityIssue.PROMPT,
        ModelPortabilityIssue.MODEL_QUALITY,
    ):
        matches = matched_terms(message, issue)
        if matches:
            return issue, matches
    return ModelPortabilityIssue.UNKNOWN, []


def failure_record(source: str, message: str) -> dict[str, Any]:
    issue, terms = classify_message(message)
    return {
        "source": source,
        "classification": issue.value,
        "matched_terms": terms,
        "message": bounded_text(message),
        "recommended_next_action": NEXT_ACTION_BY_ISSUE[issue],
    }


def suite_failure_records(suite_runs: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, item in enumerate(suite_runs):
        if not isinstance(item, dict) or item.get("status") == "passed":
            continue
        suite_id = str(item.get("id") or f"suite_{index}")
        text = "\n".join(
            str(item.get(key) or "")
            for key in ("description", "stdout_tail", "stderr_tail", "returncode")
        ).strip()
        records.append(failure_record(f"suite_runs[{suite_id}]", text or "suite failed without captured output"))
    return records


def founder_field_failure_records(founder_summary: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    errors = founder_summary.get("errors") if isinstance(founder_summary.get("errors"), list) else []
    for index, error in enumerate(errors):
        records.append(failure_record(f"founder_field_summary.errors[{index}]", str(error)))
    summary = founder_summary.get("summary") if isinstance(founder_summary.get("summary"), dict) else {}
    failed = summary.get("failed")
    if isinstance(failed, int) and failed > 0:
        records.append(
            failure_record(
                "founder_field_summary.summary.failed",
                f"Founder field prompt suite reported {failed} failed prompt(s). Inspect semantic_quality_status, "
                "missing_semantic_markers, prompt_risk, and suggested_prompt_if_missed in the founder field report.",
            )
        )
    return records


def acceptance_failure_records(acceptance_report: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    errors = acceptance_report.get("errors") if isinstance(acceptance_report.get("errors"), list) else []
    for index, error in enumerate(errors):
        records.append(failure_record(f"acceptance.errors[{index}]", str(error)))
    suite_runs = acceptance_report.get("suite_runs") if isinstance(acceptance_report.get("suite_runs"), list) else []
    records.extend(suite_failure_records(suite_runs))
    founder_summary = acceptance_report.get("founder_field_summary")
    if isinstance(founder_summary, dict):
        records.extend(founder_field_failure_records(founder_summary))
    return dedupe_failure_records(records)


def dedupe_failure_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        key = (
            str(record.get("source")),
            str(record.get("classification")),
            re.sub(r"\s+", " ", str(record.get("message"))).strip()[:240],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def classification_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    summary = {issue.value: 0 for issue in ModelPortabilityIssue}
    for record in records:
        classification = str(record.get("classification") or ModelPortabilityIssue.UNKNOWN.value)
        summary[classification] = summary.get(classification, 0) + 1
    return summary


def candidate_environment(config: ModelPortabilityConfig) -> dict[str, Any]:
    return {
        "candidate_id": config.candidate_id,
        "candidate_description": config.candidate_description,
        "candidate_model_base_url": openai_base_url(config.candidate_model_base_url),
        "workflow_router_gateway_base_url": config.workflow_router_gateway_base_url,
        "controller_base_url": config.controller_base_url,
        "anythingllm_api_base_url": config.anythingllm_api_base_url,
        "workspace": config.workspace,
        "api_key_env": config.api_key_env,
        "api_key_available": bool(os.environ.get(config.api_key_env)),
        "target_roots": list(config.target_roots),
    }


def run_or_load_acceptance(config: ModelPortabilityConfig, report_path: Path) -> dict[str, Any]:
    if config.skip_live_acceptance:
        if not config.acceptance_report_path:
            raise RuntimeError("--acceptance-report-path is required when --skip-live-acceptance is used")
        report = load_json_report(config.acceptance_report_path)
        report.setdefault("report_path", str(config.acceptance_report_path.resolve()))
        return report
    acceptance_path = config.acceptance_output_path or default_acceptance_report_path(report_path)
    return run_v1_acceptance(
        V1AcceptanceConfig(
            config_root=config.config_root,
            workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
            controller_base_url=config.controller_base_url,
            anythingllm_api_base_url=config.anythingllm_api_base_url,
            workspace=config.workspace,
            api_key_env=config.api_key_env,
            target_roots=config.target_roots,
            timeout_seconds=config.timeout_seconds,
            command_timeout_seconds=config.command_timeout_seconds,
            output_path=acceptance_path,
            python_executable=config.python_executable,
            profile=ReleaseGateProfile.RELEASE_CANDIDATE,
        )
    )


def run_model_portability(config: ModelPortabilityConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    report_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "model_portability_report",
        "status": "failed",
        "created_at": utc_timestamp(),
        "candidate": candidate_environment(config),
        "candidate_model_probe": {"status": "skipped"} if config.skip_model_probe else {},
        "acceptance_report": {},
        "acceptance_report_path": "",
        "classification_summary": {},
        "classified_failures": [],
        "errors": [],
    }
    try:
        if not config.candidate_id.strip():
            raise RuntimeError("candidate_id is required")
        if not config.skip_model_probe:
            report["candidate_model_probe"] = probe_model_base_url(
                config.candidate_model_base_url,
                min(30, config.timeout_seconds),
            )
        acceptance_report = run_or_load_acceptance(config, report_path)
        report["acceptance_report"] = {
            "kind": acceptance_report.get("kind"),
            "status": acceptance_report.get("status"),
            "profile": acceptance_report.get("profile"),
            "report_path": acceptance_report.get("report_path"),
            "target_roots": acceptance_report.get("target_roots"),
            "suite_count": len(acceptance_report.get("suite_runs") or []),
            "error_count": len(acceptance_report.get("errors") or []),
            "founder_field_summary": acceptance_report.get("founder_field_summary")
            if isinstance(acceptance_report.get("founder_field_summary"), dict)
            else {},
            "skill_library_health": acceptance_report.get("skill_library_health")
            if isinstance(acceptance_report.get("skill_library_health"), dict)
            else {},
        }
        report["acceptance_report_path"] = str(
            acceptance_report.get("report_path")
            or (config.acceptance_report_path.resolve() if config.acceptance_report_path else "")
        )
        probe_failures: list[dict[str, Any]] = []
        if not config.skip_model_probe and report.get("candidate_model_probe", {}).get("status") != "passed":
            probe_failures.append(
                failure_record(
                    "candidate_model_probe",
                    "Candidate model probe failed: "
                    + json.dumps(report.get("candidate_model_probe", {}), ensure_ascii=True, sort_keys=True),
                )
            )
        failures = dedupe_failure_records([*probe_failures, *acceptance_failure_records(acceptance_report)])
        report["classified_failures"] = failures
        report["classification_summary"] = classification_summary(failures)
        report["status"] = (
            "passed"
            if acceptance_report.get("status") == "passed"
            and (config.skip_model_probe or report.get("candidate_model_probe", {}).get("status") == "passed")
            and not failures
            else "failed"
        )
    except Exception as exc:  # noqa: BLE001
        record = failure_record("model_portability", f"{type(exc).__name__}: {exc}")
        report["errors"].append(record["message"])
        report["classified_failures"].append(record)
        report["classification_summary"] = classification_summary(report["classified_failures"])
    write_json(report_path, report)
    report["report_path"] = str(report_path.resolve())
    write_json(report_path, report)
    return report
