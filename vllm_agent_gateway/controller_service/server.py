"""Local HTTP controller service.

This service exposes explicit workflow endpoints. It is intentionally separate
from role prompt proxy ports so ordinary chat requests do not silently become
stateful repo workflows.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.documenter.orchestrator import (
    DOCUMENT_SCOPES,
    MODES,
    REVIEW_SCOPES,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_IN_MEMORY_DOC_BYTES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_ROLE_ID,
    DEFAULT_VISIBLE_CANDIDATE_LIMIT,
    DEFAULT_VISIBLE_CANDIDATE_TOKEN_LIMIT,
    DocumenterInvocationRequest,
    OrchestratorError,
    invoke_documenter,
)
from vllm_agent_gateway.controller_service.tool_policy import (
    ControllerToolPolicyError,
    ResolvedControllerToolPolicy,
    resolve_controller_tool_policy,
)
from vllm_agent_gateway.invocation import InvocationResult


DEFAULT_CONTROLLER_HOST = "127.0.0.1"
DEFAULT_CONTROLLER_PORT = 8400
HARNESS_CHAT_COMPLETIONS_PATH = "/v1/controller/harness/chat/completions"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
TERMINAL_STATUSES = {"completed", "failed", "canceled"}
DOCUMENT_REVIEW_FIELDS = {
    "workflow",
    "target_root",
    "seed_doc",
    "seed",
    "doc",
    "mode",
    "document_scope",
    "review_scope",
    "role_id",
    "role_base_url",
    "model_visible_tool_ids",
    "model",
    "chunk_token_limit",
    "chunk_overlap_lines",
    "visible_candidate_limit",
    "visible_candidate_token_limit",
    "max_chunks",
    "all_chunks",
    "include_followups",
    "followup_depth",
    "max_followup_files",
    "allow_nonvisible_followups",
    "criteria",
    "allow_untracked_doc",
    "resume",
    "resume_allow_arg_changes",
    "summary_output",
    "write_draft",
    "stop_after_chunks",
    "dry_run",
    "timeout",
    "max_output_tokens",
    "max_in_memory_doc_bytes",
    "allow_large_in_memory_docs",
    "budgets",
    "async",
}
DOCUMENT_REVIEW_BUDGET_FIELDS = {"max_chunks", "stop_after_chunks"}


class ControllerServiceError(RuntimeError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST, code: str = "bad_request"):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class ControllerServiceConfig:
    config_root: Path
    output_root: Path
    allowed_target_roots: tuple[Path, ...]
    host: str = DEFAULT_CONTROLLER_HOST
    port: int = DEFAULT_CONTROLLER_PORT
    default_role_base_url: str | None = None

    @property
    def run_registry_root(self) -> Path:
        return self.output_root / "controller-runs"


@dataclass(frozen=True)
class BuiltDocumenterReview:
    request: DocumenterInvocationRequest
    tool_policy: ResolvedControllerToolPolicy


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def controller_run_id() -> str:
    return datetime.now(timezone.utc).strftime("controller-%Y%m%dT%H%M%S%fZ")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def require_under_any(path: Path, roots: tuple[Path, ...], label: str) -> Path:
    resolved = path.resolve()
    if not any(is_under(resolved, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise ControllerServiceError(
            f"{label} is outside allowed target roots: {resolved}. Allowed roots: {allowed}",
            status=HTTPStatus.FORBIDDEN,
            code="target_root_not_allowed",
        )
    return resolved


def require_under_output_root(path: Path, output_root: Path, label: str) -> Path:
    resolved = path.resolve()
    if not is_under(resolved, output_root):
        raise ControllerServiceError(
            f"{label} must stay under controller output root: {resolved}",
            status=HTTPStatus.FORBIDDEN,
            code="output_path_not_allowed",
        )
    return resolved


def bounded_string(value: Any, limit: int = 2000) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def response_warnings(report: dict[str, Any] | None, limit: int = 50) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    warnings: list[dict[str, Any]] = []
    for key in ("discovery_warnings", "validation_warnings"):
        raw = report.get(key)
        if isinstance(raw, list):
            warnings.extend(item for item in raw if isinstance(item, dict))
    for chunk in report.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        raw = chunk.get("validation_warnings")
        if isinstance(raw, list):
            warnings.extend(
                {"doc_id": chunk.get("doc_id"), "chunk_id": chunk.get("chunk_id"), **item}
                for item in raw
                if isinstance(item, dict)
            )
    selected = warnings[:limit]
    if len(warnings) > limit:
        selected.append({"warning": "warnings_truncated", "available_warning_count": len(warnings), "retained": limit})
    return selected


def response_failures(failures: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    selected = failures[:limit]
    if len(failures) > limit:
        selected.append({"failure": "failures_truncated", "available_failure_count": len(failures), "retained": limit})
    return selected


def response_summary(text: str | None) -> str | None:
    return bounded_string(text, 4000) if isinstance(text, str) else None


def documenter_review_summary(report: dict[str, Any] | None, limit: int = 10) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "documenter_orchestrator_report":
        return None
    reviewed_files = report.get("reviewed_files") if isinstance(report.get("reviewed_files"), list) else []
    reviewed_doc_ids = [
        item.get("doc_id")
        for item in reviewed_files
        if isinstance(item, dict) and isinstance(item.get("doc_id"), str)
    ]
    followup_policy = report.get("followup_policy") if isinstance(report.get("followup_policy"), dict) else {}
    skipped_followups = (
        followup_policy.get("skipped_followups")
        if isinstance(followup_policy.get("skipped_followups"), list)
        else []
    )
    accepted_followups = (
        followup_policy.get("accepted_followups")
        if isinstance(followup_policy.get("accepted_followups"), list)
        else []
    )
    discovery_warnings = (
        report.get("discovery_warnings")
        if isinstance(report.get("discovery_warnings"), list)
        else []
    )
    document_manifest = report.get("document_manifest") if isinstance(report.get("document_manifest"), dict) else {}
    summary = {
        "target_root": report.get("target_root"),
        "seed_doc_id": report.get("seed_doc_id") or report.get("doc_id"),
        "document_scope": report.get("document_scope"),
        "review_scope": report.get("review_scope"),
        "document_count": document_manifest.get("document_count"),
        "reviewed_file_count": len(reviewed_doc_ids),
        "reviewed_files": reviewed_doc_ids[:limit],
        "reviewed_files_truncated": len(reviewed_doc_ids) > limit,
        "chunks_processed": report.get("chunks_processed"),
        "chunks_total": report.get("chunks_total"),
        "truncated_after_chunks": bool(report.get("truncated_after_chunks")),
        "accepted_followup_count": len([item for item in accepted_followups if isinstance(item, dict)]),
        "skipped_followup_count": len([item for item in skipped_followups if isinstance(item, dict)]),
        "discovery_warning_count": len([item for item in discovery_warnings if isinstance(item, dict)]),
    }
    return {key: value for key, value in summary.items() if value is not None}


def compact_tool_policy_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "workflow": value.get("workflow"),
        "role_id": value.get("role_id"),
        "controller_tool_ids": value.get("controller_tool_ids") if isinstance(value.get("controller_tool_ids"), list) else [],
        "model_visible_tool_ids": value.get("model_visible_tool_ids") if isinstance(value.get("model_visible_tool_ids"), list) else [],
        "denied_tool_ids": value.get("denied_tool_ids") if isinstance(value.get("denied_tool_ids"), list) else [],
        "controller_actions": value.get("controller_actions") if isinstance(value.get("controller_actions"), list) else [],
    }


def service_response_from_result(
    result: InvocationResult,
    tool_policy: ResolvedControllerToolPolicy | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "run_id": result.run_id,
        "workflow": result.workflow,
        "status": result.status.value,
        "artifacts": result.artifact_paths,
        "summary": response_summary(result.summary_text),
        "warnings": response_warnings(result.report),
        "failures": response_failures(result.failures),
        "resume_key": result.resume_key,
    }
    if tool_policy is not None:
        response["tool_policy"] = tool_policy.audit_record()
    review_summary = documenter_review_summary(result.report)
    if review_summary is not None:
        response["review_summary"] = review_summary
    return response

def compact_service_response(response: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    warnings = response.get("warnings") if isinstance(response.get("warnings"), list) else []
    failures = response.get("failures") if isinstance(response.get("failures"), list) else []
    run_id = response.get("run_id")
    return {
        "run_id": run_id,
        "workflow": response.get("workflow"),
        "status": response.get("status"),
        "artifacts": response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {},
        "summary": response.get("summary"),
        "warning_count": len(warnings),
        "warnings": warnings[:limit],
        "failure_count": len(failures),
        "failures": failures[:limit],
        "tool_policy": compact_tool_policy_record(response.get("tool_policy")),
        "review_summary": response.get("review_summary") if isinstance(response.get("review_summary"), dict) else None,
        "run_lookup": f"/v1/controller/runs/{run_id}" if isinstance(run_id, str) and run_id else None,
    }


def assistant_content_for_controller_response(response: dict[str, Any]) -> str:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    lines = [
        f"{response.get('workflow')} {response.get('status')}",
        f"run_id: {response.get('run_id')}",
        f"warnings: {response.get('warning_count', 0)}",
        f"failures: {response.get('failure_count', 0)}",
    ]
    review_summary = response.get("review_summary") if isinstance(response.get("review_summary"), dict) else {}
    if review_summary:
        lines.extend(
            [
                f"reviewed_files: {review_summary.get('reviewed_file_count', 0)}",
                f"chunks: {review_summary.get('chunks_processed', 0)} of {review_summary.get('chunks_total', 0)}",
                f"skipped_followups: {review_summary.get('skipped_followup_count', 0)}",
            ]
        )
    if response.get("summary"):
        lines.append("")
        lines.append(str(response["summary"]))
    if artifacts:
        lines.append("")
        lines.append("Artifacts:")
        for key in sorted(artifacts):
            lines.append(f"- {key}: {artifacts[key]}")
    if response.get("run_lookup"):
        lines.append("")
        lines.append(f"Run record: {response['run_lookup']}")
    return "\n".join(lines)


def chat_completion_response(payload: dict[str, Any], service_response: dict[str, Any]) -> dict[str, Any]:
    compact = compact_service_response(service_response)
    run_id = compact.get("run_id") or utc_now()
    model = payload.get("model") if isinstance(payload.get("model"), str) else "agentic-controller"
    return {
        "id": f"agentic-controller-{run_id}",
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_content_for_controller_response(compact),
                },
                "finish_reason": "stop",
            }
        ],
        "agentic_controller_response": compact,
    }


def persist_run_record(config: ControllerServiceConfig, response: dict[str, Any]) -> None:
    run_id = response.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return
    if not RUN_ID_RE.fullmatch(run_id):
        return
    record = {"schema_version": 1, "kind": "controller_run_record", "updated_at": utc_now(), **response}
    config.run_registry_root.mkdir(parents=True, exist_ok=True)
    path = config.run_registry_root / f"{run_id}.json"
    temp_path = config.run_registry_root / f".{run_id}.{threading.get_ident()}.tmp"
    temp_path.write_bytes(json_bytes(record))
    temp_path.replace(path)


def load_run_record(config: ControllerServiceConfig, run_id: str) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ControllerServiceError("Invalid run_id.", status=HTTPStatus.BAD_REQUEST, code="invalid_run_id")
    path = config.run_registry_root / f"{run_id}.json"
    if not path.exists():
        raise ControllerServiceError("Run not found.", status=HTTPStatus.NOT_FOUND, code="run_not_found")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ControllerServiceError(
            f"Stored run record is invalid: {exc}",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="invalid_run_record",
        ) from exc
    if not isinstance(value, dict):
        raise ControllerServiceError(
            "Stored run record must be a JSON object.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="invalid_run_record",
        )
    return value


def run_record_path(config: ControllerServiceConfig, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ControllerServiceError("Invalid run_id.", status=HTTPStatus.BAD_REQUEST, code="invalid_run_id")
    return config.run_registry_root / f"{run_id}.json"


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControllerServiceError(f"{label} must be a JSON object.")
    return value


def decode_json_object_text(value: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def envelope_from_message_content(content: Any) -> dict[str, Any] | None:
    if isinstance(content, str):
        decoded = decode_json_object_text(content)
        if isinstance(decoded, dict) and "agentic_controller_request" in decoded:
            return require_object(decoded["agentic_controller_request"], "agentic_controller_request")
        return None
    if isinstance(content, list):
        found: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
                continue
            decoded = decode_json_object_text(part["text"])
            if isinstance(decoded, dict) and "agentic_controller_request" in decoded:
                found.append(require_object(decoded["agentic_controller_request"], "agentic_controller_request"))
        if len(found) > 1:
            raise ControllerServiceError(
                "Exactly one agentic_controller_request envelope is allowed.",
                code="multiple_controller_envelopes",
            )
        return found[0] if found else None
    return None


def extract_harness_controller_request(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("stream") is True:
        raise ControllerServiceError("Streaming harness responses are not supported yet.", code="stream_not_supported")
    found: list[dict[str, Any]] = []
    if "agentic_controller_request" in payload:
        found.append(require_object(payload["agentic_controller_request"], "agentic_controller_request"))
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                raise ControllerServiceError("messages entries must be objects.")
            envelope = envelope_from_message_content(message.get("content"))
            if envelope is not None:
                found.append(envelope)
    elif "agentic_controller_request" not in payload:
        raise ControllerServiceError(
            "Harness adapter requests must include messages or a top-level agentic_controller_request.",
            code="missing_controller_envelope",
        )
    if not found:
        raise ControllerServiceError(
            "Harness adapter requires an explicit JSON agentic_controller_request envelope. "
            "Natural-language chat text is not a workflow request.",
            code="missing_controller_envelope",
        )
    if len(found) > 1:
        raise ControllerServiceError(
            "Exactly one agentic_controller_request envelope is allowed.",
            code="multiple_controller_envelopes",
        )
    return found[0]


def optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ControllerServiceError(f"{key} must be a string.")
    return value


def optional_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ControllerServiceError(f"{key} must be a boolean.")
    return value


def optional_int(payload: dict[str, Any], key: str, default: int | None = None) -> int | None:
    value = payload.get(key, default)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ControllerServiceError(f"{key} must be an integer.")
    return value


def int_with_default(payload: dict[str, Any], key: str, default: int) -> int:
    value = optional_int(payload, key, default)
    assert value is not None
    return value


def optional_string_list(payload: dict[str, Any], key: str) -> list[str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ControllerServiceError(f"{key} must be a list of strings.")
    return value


def optional_seed_doc(payload: dict[str, Any]) -> str | None:
    values = {
        key: optional_string(payload, key)
        for key in ("seed_doc", "seed", "doc")
        if payload.get(key) is not None
    }
    non_empty = {key: value for key, value in values.items() if value}
    unique = set(non_empty.values())
    if len(unique) > 1:
        raise ControllerServiceError("seed_doc, seed, and doc must not specify different values.")
    return next(iter(unique), None)


def build_documenter_review(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltDocumenterReview:
    unknown = sorted(set(payload) - DOCUMENT_REVIEW_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", "documenter.review")
    if workflow != "documenter.review":
        raise ControllerServiceError("workflow must be documenter.review.")

    budgets = require_object(payload.get("budgets", {}), "budgets")
    unknown_budgets = sorted(set(budgets) - DOCUMENT_REVIEW_BUDGET_FIELDS)
    if unknown_budgets:
        raise ControllerServiceError(f"Unsupported budget field(s): {', '.join(unknown_budgets)}")
    merged = {**payload, **budgets}

    target_root_value = optional_string(merged, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")

    mode = optional_string(merged, "mode") or "full"
    if mode not in MODES or mode == "summarize":
        raise ControllerServiceError("mode must be review or full for documenter review requests.")
    document_scope = optional_string(merged, "document_scope") or "tracked"
    if document_scope not in DOCUMENT_SCOPES:
        raise ControllerServiceError("document_scope must be tracked or all.")
    review_scope = optional_string(merged, "review_scope") or "auto"
    if review_scope not in REVIEW_SCOPES:
        raise ControllerServiceError("review_scope must be auto, manifest, or seed.")
    role_id = optional_string(merged, "role_id") or DEFAULT_ROLE_ID
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            workflow,
            role_id,
            {
                "mode": mode,
                "document_scope": document_scope,
                "review_scope": review_scope,
            },
            optional_string_list(merged, "model_visible_tool_ids"),
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc

    output_dir = config.output_root / DEFAULT_OUTPUT_DIR
    resume_path: Path | None = None
    resume_value = optional_string(merged, "resume")
    if resume_value:
        raw_resume_path = Path(resume_value)
        resume_candidate = raw_resume_path if raw_resume_path.is_absolute() else config.output_root / raw_resume_path
        resume_path = require_under_output_root(resume_candidate.resolve(), config.output_root, "resume")
    summary_output_value = optional_string(merged, "summary_output")
    summary_output: Path | None = None
    if summary_output_value:
        raw_summary_path = Path(summary_output_value)
        summary_candidate = raw_summary_path if raw_summary_path.is_absolute() else config.output_root / raw_summary_path
        summary_output = require_under_output_root(summary_candidate.resolve(), config.output_root, "summary_output")

    request = DocumenterInvocationRequest(
        mode=mode,
        config_root=config.config_root,
        target_root=target_root,
        doc=optional_seed_doc(merged),
        document_scope=document_scope,
        review_scope=review_scope,
        role_id=role_id,
        role_base_url=optional_string(merged, "role_base_url") or config.default_role_base_url,
        model=optional_string(merged, "model") or DocumenterInvocationRequest().model,
        chunk_token_limit=int_with_default(merged, "chunk_token_limit", 1000),
        chunk_overlap_lines=int_with_default(merged, "chunk_overlap_lines", 8),
        visible_candidate_limit=int_with_default(
            merged,
            "visible_candidate_limit",
            DEFAULT_VISIBLE_CANDIDATE_LIMIT,
        ),
        visible_candidate_token_limit=int_with_default(
            merged,
            "visible_candidate_token_limit",
            DEFAULT_VISIBLE_CANDIDATE_TOKEN_LIMIT,
        ),
        max_chunks=optional_int(merged, "max_chunks"),
        all_chunks=optional_bool(merged, "all_chunks", False),
        include_followups=optional_bool(merged, "include_followups", False),
        followup_depth=int_with_default(merged, "followup_depth", 0),
        max_followup_files=int_with_default(merged, "max_followup_files", 5),
        allow_nonvisible_followups=optional_bool(merged, "allow_nonvisible_followups", False),
        criteria=optional_string_list(merged, "criteria"),
        output_dir=output_dir,
        allow_untracked_doc=optional_bool(merged, "allow_untracked_doc", False),
        list_docs=False,
        report=None,
        resume=resume_path,
        resume_allow_arg_changes=optional_bool(merged, "resume_allow_arg_changes", False),
        summary_output=summary_output,
        write_draft=optional_bool(merged, "write_draft", False),
        stop_after_chunks=optional_int(merged, "stop_after_chunks"),
        dry_run=optional_bool(merged, "dry_run", False),
        timeout=int_with_default(merged, "timeout", 600),
        max_output_tokens=int_with_default(merged, "max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS),
        max_in_memory_doc_bytes=int_with_default(
            merged,
            "max_in_memory_doc_bytes",
            DEFAULT_MAX_IN_MEMORY_DOC_BYTES,
        ),
        allow_large_in_memory_docs=optional_bool(merged, "allow_large_in_memory_docs", False),
    )
    return BuiltDocumenterReview(request=request, tool_policy=tool_policy)


def build_documenter_request(payload: dict[str, Any], config: ControllerServiceConfig) -> DocumenterInvocationRequest:
    return build_documenter_review(payload, config).request


def async_initial_response(
    run_id: str,
    workflow: str,
    stop_requested_path: Path,
    tool_policy: ResolvedControllerToolPolicy,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "run_id": run_id,
        "workflow": workflow,
        "status": "queued",
        "artifacts": {},
        "summary": None,
        "warnings": [],
        "failures": [],
        "resume_key": None,
        "tool_policy": tool_policy.audit_record(),
        "lifecycle": {
            "async": True,
            "created_at": now,
            "updated_at": now,
            "cancel_requested": False,
            "stop_requested_path": str(stop_requested_path),
        },
    }


def response_with_lifecycle(
    response: dict[str, Any],
    run_id: str,
    workflow_run_id: str | None,
    stop_requested_path: Path,
) -> dict[str, Any]:
    lifecycle = response.get("lifecycle") if isinstance(response.get("lifecycle"), dict) else {}
    return {
        **response,
        "run_id": run_id,
        "workflow_run_id": workflow_run_id,
        "lifecycle": {
            **lifecycle,
            "async": True,
            "updated_at": utc_now(),
            "cancel_requested": stop_requested_path.exists(),
            "stop_requested_path": str(stop_requested_path),
        },
    }


def mark_async_run_running(config: ControllerServiceConfig, run_id: str) -> bool:
    record = load_run_record(config, run_id)
    lifecycle = record.get("lifecycle") if isinstance(record.get("lifecycle"), dict) else {}
    stop_path_value = lifecycle.get("stop_requested_path")
    if isinstance(stop_path_value, str) and Path(stop_path_value).exists():
        record["status"] = "canceled"
        record["failures"] = [
            {
                "failed_at": utc_now(),
                "stage": "queued",
                "reason": "controller_service_stop_requested",
            }
        ]
        record["lifecycle"] = {**lifecycle, "cancel_requested": True, "updated_at": utc_now()}
        persist_run_record(config, record)
        return False
    record["status"] = "running"
    record["lifecycle"] = {**lifecycle, "updated_at": utc_now()}
    persist_run_record(config, record)
    return True


def run_documenter_worker(
    config: ControllerServiceConfig,
    run_id: str,
    request: DocumenterInvocationRequest,
    tool_policy: ResolvedControllerToolPolicy,
    stop_requested_path: Path,
) -> None:
    try:
        if not mark_async_run_running(config, run_id):
            return
        result = invoke_documenter(request)
        response = response_with_lifecycle(
            service_response_from_result(result, tool_policy),
            run_id,
            result.run_id,
            stop_requested_path,
        )
        persist_run_record(config, response)
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        record = {
            "run_id": run_id,
            "workflow": "documenter.review",
            "status": "failed",
            "artifacts": {},
            "summary": None,
            "warnings": [],
            "failures": [
                {
                    "failed_at": utc_now(),
                    "stage": "async_worker",
                    "error": bounded_string(exc),
                }
            ],
            "resume_key": None,
            "tool_policy": tool_policy.audit_record(),
            "lifecycle": {
                "async": True,
                "updated_at": utc_now(),
                "cancel_requested": stop_requested_path.exists(),
                "stop_requested_path": str(stop_requested_path),
            },
        }
        persist_run_record(config, record)


def start_async_documenter_review(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_documenter_review(payload, config)
    run_id = controller_run_id()
    stop_requested_path = config.run_registry_root / f"{run_id}.stop.json"
    request = replace(built.request, stop_requested_path=stop_requested_path)
    response = async_initial_response(run_id, "documenter.review", stop_requested_path, built.tool_policy)
    response["status"] = "running"
    response["lifecycle"] = {**response["lifecycle"], "updated_at": utc_now()}
    persist_run_record(config, response)
    thread = threading.Thread(
        target=run_documenter_worker,
        args=(config, run_id, request, built.tool_policy, stop_requested_path),
        daemon=True,
        name=f"controller-{run_id}",
    )
    thread.start()
    return response


def handle_documenter_review(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    if optional_bool(payload, "async", False):
        return start_async_documenter_review(payload, config)
    built = build_documenter_review(payload, config)
    result = invoke_documenter(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_harness_chat_completion(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    controller_request = extract_harness_controller_request(payload)
    workflow = controller_request.get("workflow")
    if workflow != "documenter.review":
        raise ControllerServiceError("Only workflow=documenter.review is supported by the Phase 3 harness adapter.")
    response = handle_documenter_review(controller_request, config)
    return chat_completion_response(payload, response)


def cancel_run(run_id: str, config: ControllerServiceConfig) -> dict[str, Any]:
    record = load_run_record(config, run_id)
    status = record.get("status")
    if status in TERMINAL_STATUSES:
        raise ControllerServiceError(
            f"Run is already terminal with status {status!r}.",
            status=HTTPStatus.CONFLICT,
            code="run_not_cancelable",
        )
    lifecycle = record.get("lifecycle") if isinstance(record.get("lifecycle"), dict) else {}
    stop_path_value = lifecycle.get("stop_requested_path")
    if not isinstance(stop_path_value, str):
        raise ControllerServiceError(
            "Run does not support stop-after-current-packet cancellation.",
            status=HTTPStatus.CONFLICT,
            code="run_not_cancelable",
        )
    stop_path = require_under_output_root(Path(stop_path_value).resolve(), config.output_root, "stop_requested_path")
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_bytes(json_bytes({"run_id": run_id, "requested_at": utc_now(), "action": "stop_after_current_packet"}))
    record["status"] = "cancel_requested"
    record["lifecycle"] = {
        **lifecycle,
        "cancel_requested": True,
        "cancel_requested_at": utc_now(),
        "updated_at": utc_now(),
    }
    persist_run_record(config, record)
    return record


def cleanup_run_records(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    max_age_seconds = int_with_default(payload, "max_age_seconds", 24 * 60 * 60)
    if max_age_seconds < 0:
        raise ControllerServiceError("max_age_seconds cannot be negative.")
    statuses = optional_string_list(payload, "statuses") or sorted(TERMINAL_STATUSES)
    unsupported = sorted(set(statuses) - (TERMINAL_STATUSES | {"paused"}))
    if unsupported:
        raise ControllerServiceError(f"Unsupported cleanup status value(s): {', '.join(unsupported)}")
    threshold = time.time() - max_age_seconds
    deleted: list[str] = []
    for path in sorted(config.run_registry_root.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("kind") != "controller_run_record":
            continue
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            continue
        if record.get("status") not in statuses:
            continue
        if max_age_seconds > 0 and path.stat().st_mtime > threshold:
            continue
        lifecycle = record.get("lifecycle") if isinstance(record.get("lifecycle"), dict) else {}
        stop_path_value = lifecycle.get("stop_requested_path")
        if isinstance(stop_path_value, str):
            stop_path = Path(stop_path_value)
            if stop_path.exists() and is_under(stop_path, config.output_root):
                stop_path.unlink()
        path.unlink()
        deleted.append(run_id)
    return {
        "schema_version": 1,
        "kind": "controller_run_cleanup",
        "deleted_run_ids": deleted,
        "deleted_count": len(deleted),
        "statuses": statuses,
        "max_age_seconds": max_age_seconds,
    }


class ControllerRequestHandler(BaseHTTPRequestHandler):
    server: "ControllerHTTPServer"

    def do_GET(self) -> None:
        if self.path == "/health":
            self.write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "kind": "controller_service",
                    "allowed_target_roots": [str(path) for path in self.server.config.allowed_target_roots],
                    "output_root": str(self.server.config.output_root),
                },
            )
            return
        prefix = "/v1/controller/runs/"
        if self.path.startswith(prefix):
            run_id = self.path[len(prefix) :].strip("/")
            try:
                self.write_json(HTTPStatus.OK, load_run_record(self.server.config, run_id))
            except ControllerServiceError as exc:
                self.write_error(exc)
            return
        self.write_error(ControllerServiceError("Not found.", status=HTTPStatus.NOT_FOUND, code="not_found"))

    def do_POST(self) -> None:
        try:
            payload = self.read_json_body()
            if self.path == "/v1/controller/documenter/reviews":
                response = handle_documenter_review(payload, self.server.config)
                status = HTTPStatus.ACCEPTED if response.get("status") in {"queued", "running"} else HTTPStatus.OK
                self.write_json(status, response)
                return
            if self.path == HARNESS_CHAT_COMPLETIONS_PATH:
                self.write_json(HTTPStatus.OK, handle_harness_chat_completion(payload, self.server.config))
                return
            if self.path == "/v1/controller/runs/cleanup":
                self.write_json(HTTPStatus.OK, cleanup_run_records(payload, self.server.config))
                return
            run_prefix = "/v1/controller/runs/"
            cancel_suffix = "/cancel"
            if self.path.startswith(run_prefix) and self.path.endswith(cancel_suffix):
                run_id = self.path[len(run_prefix) : -len(cancel_suffix)].strip("/")
                self.write_json(HTTPStatus.OK, cancel_run(run_id, self.server.config))
                return
            raise ControllerServiceError("Not found.", status=HTTPStatus.NOT_FOUND, code="not_found")
        except ControllerServiceError as exc:
            self.write_error(exc)
        except OrchestratorError as exc:
            self.write_error(ControllerServiceError(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY, code="workflow_error"))
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self.write_error(
                ControllerServiceError(
                    f"Unexpected controller service error: {bounded_string(exc)}",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    code="internal_error",
                )
            )

    def read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ControllerServiceError("Content-Length must be an integer.") from exc
        if length < 1:
            raise ControllerServiceError("Request body is required.")
        if length > 1024 * 1024:
            raise ControllerServiceError("Request body exceeds 1 MiB limit.", status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ControllerServiceError(f"Invalid JSON request body: {exc}") from exc
        return require_object(value, "request body")

    def write_error(self, exc: ControllerServiceError) -> None:
        self.write_json(exc.status, {"error": {"code": exc.code, "message": str(exc)}})

    def write_json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
        data = json_bytes(value)
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


class ControllerHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], config: ControllerServiceConfig):
        super().__init__(server_address, ControllerRequestHandler)
        self.config = config


def create_server(config: ControllerServiceConfig) -> ControllerHTTPServer:
    config.output_root.mkdir(parents=True, exist_ok=True)
    config.run_registry_root.mkdir(parents=True, exist_ok=True)
    return ControllerHTTPServer((config.host, config.port), config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the explicit local controller service.")
    parser.add_argument("--host", default=DEFAULT_CONTROLLER_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_CONTROLLER_PORT)
    parser.add_argument("--config-root", default=".")
    parser.add_argument("--output-root", default=".agentic_controller")
    parser.add_argument(
        "--allowed-target-root",
        action="append",
        default=[],
        help="Allowed repository root. May be repeated. Defaults to --config-root.",
    )
    parser.add_argument("--default-role-base-url", default=None)
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> ControllerServiceConfig:
    config_root = resolve_path(args.config_root)
    output_root = resolve_path(args.output_root)
    raw_allowed = args.allowed_target_root or [str(config_root)]
    allowed = tuple(resolve_path(path) for path in raw_allowed)
    if args.port < 1 or args.port > 65535:
        raise ControllerServiceError("--port must be between 1 and 65535.")
    return ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=allowed,
        host=args.host,
        port=args.port,
        default_role_base_url=args.default_role_base_url,
    )


def main() -> int:
    try:
        config = config_from_args(parse_args())
        server = create_server(config)
    except ControllerServiceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"controller service listening on http://{config.host}:{config.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
