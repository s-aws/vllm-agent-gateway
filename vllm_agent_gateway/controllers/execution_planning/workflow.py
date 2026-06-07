"""Controller-owned execution planning workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.documenter.orchestrator import DEFAULT_MODEL
from vllm_agent_gateway.implementation.workflow import (
    ImplementationWorkflowInvocationRequest,
    invoke_implementation_workflow,
    normalize_verification_commands,
)
from vllm_agent_gateway.controllers.verification import (
    controller_verification_commands,
    discover_related_tests,
    merge_controller_verification_commands,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.structure_index.indexer import build_code_structure_index, build_index_slice


WORKFLOW_ID = "execution_planning.plan"
SCHEMA_VERSION = 1
DEFAULT_ROLE_ID = "architect/default"
DEFAULT_OUTPUT_DIR = "execution-planning"
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_OUTPUT_TOKENS = 4600
ALLOWED_MODES = {"investigation_only", "implementation_prep", "dry_run"}
ALLOWED_CONTEXT_TOOLS = {"structure_index", "git_grep", "read_file", "manual"}
IGNORED_LOOKUP_DIRS = {
    ".agentic_reports",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tmp_pytest",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
DEFAULT_SKILL_CHAIN = [
    "request-triage",
    "scope-and-assumptions",
    "entrypoint-finder",
    "context-plan-builder",
    "impact-map-builder",
    "execution-plan-writer",
    "implementation-packet-designer",
    "verification-planner",
    "feedback-capture",
]
ARTIFACT_NAMES = {
    "request": "request.json",
    "request_triage": "request-triage.json",
    "scope_and_assumptions": "scope-and-assumptions.json",
    "entrypoint_finder": "entrypoint-finder.json",
    "context_plan": "context-plan.json",
    "context_results": "context-results.json",
    "context_results_for_model": "context-results-for-model.json",
    "impact_map": "impact-map.json",
    "execution_plan": "execution-plan.json",
    "implementation_packet_candidates": "implementation-packet-candidates.json",
    "packet_preview": "packet-preview.json",
    "verification_plan": "verification-plan.json",
    "implementation_workflow_report": "implementation-workflow-report.json",
    "feedback_record": "feedback-record.json",
    "run_state": "run-state.json",
}
REQUIRED_KEYS: dict[str, list[str]] = {
    "request-triage": [
        "request_type",
        "requires_repo_context",
        "requires_user_approval_before_write",
        "suggested_next_skill",
        "reason",
        "open_questions",
    ],
    "scope-and-assumptions": ["problem", "clarification", "goal", "scope", "next_step"],
    "entrypoint-finder": ["anchors", "entrypoint_candidates", "selected_entrypoint", "followup_context_needed", "stop"],
    "context-plan-builder": [
        "context_plan_id",
        "entrypoint",
        "context_requests",
        "request_order",
        "context_budget",
        "excluded_context",
        "next_step",
        "stop",
    ],
    "impact-map-builder": [
        "impact_map_id",
        "objective",
        "basis",
        "behavior_paths",
        "affected_files",
        "affected_symbols",
        "dependencies",
        "related_tests",
        "duplicate_or_parallel_paths",
        "risks",
        "unknowns",
        "next_step",
        "stop",
    ],
    "execution-plan-writer": [
        "plan_id",
        "plan_mode",
        "objective",
        "basis",
        "preconditions",
        "steps",
        "approval_required",
        "verification_strategy",
        "containment",
        "next_step",
        "stop",
    ],
    "implementation-packet-designer": [
        "packet_set_id",
        "source_plan_id",
        "approval",
        "workflow_compatibility",
        "packet_candidates",
        "blocked_packets",
        "packet_file_preview",
        "next_step",
        "stop",
    ],
    "verification-planner": [
        "verification_plan_id",
        "source_plan_id",
        "source_packet_set_id",
        "basis",
        "verification_commands",
        "manual_checks",
        "coverage_gaps",
        "rejected_commands",
        "next_step",
        "stop",
    ],
    "feedback-capture": [
        "workflow_id",
        "run_id",
        "useful",
        "wrong",
        "missing",
        "too_slow_or_noisy",
        "next_adjustments",
    ],
}


class ExecutionPlanningWorkflowError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "execution_planning_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


@dataclass(frozen=True)
class ExecutionPlanningInvocationRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    mode: str = "investigation_only"
    skill_chain: list[str] = field(default_factory=lambda: list(DEFAULT_SKILL_CHAIN))
    approval: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    packet_operations: list[dict[str, Any]] = field(default_factory=list)
    budgets: dict[str, Any] = field(default_factory=dict)
    feedback: dict[str, Any] = field(default_factory=dict)
    role_id: str = DEFAULT_ROLE_ID
    role_base_url: str | None = None
    model: str = field(default_factory=lambda: os.environ.get("AGENTIC_GATEWAY_MODEL", DEFAULT_MODEL))

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        target_root: Path,
        output_root: Path,
        role_base_url: str | None,
    ) -> "ExecutionPlanningInvocationRequest":
        values = {
            "config_root": config_root,
            "target_root": target_root,
            "output_root": output_root,
            "role_base_url": role_base_url,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def list_value(value: dict[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    return item if isinstance(item, list) else []


def stop_required(value: dict[str, Any]) -> bool:
    stop = value.get("stop")
    return isinstance(stop, dict) and stop.get("required") is True


def strip_thinking_and_extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ExecutionPlanningWorkflowError("Model output was not a JSON object.", code="invalid_skill_output")
    return value


def assert_required_keys(skill_name: str, value: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_KEYS[skill_name] if key not in value]
    if missing:
        raise ExecutionPlanningWorkflowError(
            f"{skill_name} output missing required keys: {', '.join(missing)}",
            code="invalid_skill_output",
        )


def json_request(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ExecutionPlanningWorkflowError(f"Response from {url} was not a JSON object.")
    return value


def read_skill(skill_root: Path, skill_name: str) -> str:
    path = skill_root / skill_name / "SKILL.md"
    if not path.exists():
        raise ExecutionPlanningWorkflowError(f"Missing skill file: {path}", code="missing_skill")
    return path.read_text(encoding="utf-8")


def chat_skill(
    *,
    role_base_url: str,
    model: str,
    skill_root: Path,
    skill_name: str,
    case_input: dict[str, Any],
    timeout_seconds: int,
    max_output_tokens: int,
    retry_reason: str | None = None,
) -> dict[str, Any]:
    skill_text = read_skill(skill_root, skill_name)
    retry_instruction = ""
    if retry_reason:
        retry_instruction = (
            "The previous response for this skill was rejected by the controller validator:\n"
            f"{retry_reason}\n\n"
            "Retry with a shorter valid JSON object only. Keep arrays concise, preserve the required output keys, "
            "and do not include markdown, comments, explanations, tool calls, or chain-of-thought.\n\n"
        )
    prompt = retry_instruction + (
        "Use the following project-local SKILL.md instructions exactly.\n\n"
        f"<skill_name>{skill_name}</skill_name>\n\n"
        f"<skill>\n{skill_text}\n</skill>\n\n"
        "Case input JSON:\n"
        f"{json.dumps(case_input, ensure_ascii=True, indent=2)}\n\n"
        "Return exactly one JSON object matching the skill output shape. "
        "Do not include markdown, comments, explanations, tool calls, or chain-of-thought."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "messages": [
            {
                "role": "system",
                "content": "You are a deterministic planning model. Output only valid JSON. Never invoke tools.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    try:
        body = json_request(f"{role_base_url.rstrip('/')}/chat/completions", payload, timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - convert transport into workflow error
        raise ExecutionPlanningWorkflowError(
            f"Model call failed for {skill_name}: {exc}",
            code="model_call_failed",
            details={
                "failed_skill": skill_name,
                "timeout_seconds": timeout_seconds,
                "max_output_tokens": max_output_tokens,
            },
        ) from exc
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExecutionPlanningWorkflowError(
            "Model response did not contain choices.",
            code="invalid_skill_output",
            details={"failed_skill": skill_name},
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ExecutionPlanningWorkflowError(
            "Model response did not contain message.content.",
            code="invalid_skill_output",
            details={"failed_skill": skill_name},
        )
    try:
        value = strip_thinking_and_extract_json(content)
    except (json.JSONDecodeError, ExecutionPlanningWorkflowError) as exc:
        raise ExecutionPlanningWorkflowError(
            f"{skill_name} did not return parseable JSON: {exc}",
            code="invalid_skill_output",
            details={"failed_skill": skill_name},
        ) from exc
    assert_required_keys(skill_name, value)
    return value


def role_base_url_from_manifest(config_root: Path, role_id: str) -> str:
    roles_path = config_root / "runtime" / "roles.json"
    try:
        roles = json.loads(roles_path.read_text(encoding="utf-8")).get("roles")
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionPlanningWorkflowError(f"Unable to read role manifest: {roles_path}: {exc}") from exc
    if not isinstance(roles, list):
        raise ExecutionPlanningWorkflowError("runtime/roles.json must contain a roles list.")
    for role in roles:
        if isinstance(role, dict) and role.get("id") == role_id:
            port = role.get("port")
            if not isinstance(port, int):
                raise ExecutionPlanningWorkflowError(f"Role {role_id} is missing an integer port.")
            host = os.environ.get("CONTROLLER_ROLE_CONNECT_HOST") or os.environ.get("ROLE_CONNECT_HOST") or "127.0.0.1"
            return f"http://{host}:{port}/v1"
    raise ExecutionPlanningWorkflowError(f"Role is not defined in runtime/roles.json: {role_id}")


def normalize_repo_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_read_text(path: Path, max_chars: int = 8000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= max_chars else text[:max_chars] + "\n...[truncated]"


def find_line_refs(text: str, needle: str, path: str) -> list[str]:
    if not needle:
        return []
    refs: list[str] = []
    for index, line in enumerate(text.splitlines(), 1):
        if needle in line:
            refs.append(f"{path}:{index}")
    return refs[:10]


def target_is_git_toplevel(target_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if result.returncode != 0:
        return False
    try:
        top_level = Path(result.stdout.strip()).resolve()
    except OSError:
        return False
    return top_level == target_root.resolve()


def run_git_grep(target_root: Path, query: str, max_results: int) -> list[str]:
    if not target_is_git_toplevel(target_root):
        return scan_exact_matches(target_root, query, max_results)
    result = subprocess.run(
        ["git", "grep", "-n", query],
        cwd=target_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode not in {0, 1}:
        return scan_exact_matches(target_root, query, max_results)
    return [line for line in result.stdout.splitlines() if line][:max_results]


def scan_exact_matches(target_root: Path, query: str, max_results: int) -> list[str]:
    matches: list[str] = []
    root = target_root.resolve()
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_LOOKUP_DIRS and not name.endswith(".egg-info") and not name.endswith(".dist-info")
        ]
        current_path = Path(current_root)
        for filename in sorted(filenames):
            path = current_path / filename
            if path.is_symlink():
                continue
            try:
                if path.stat().st_size > 1024 * 1024:
                    continue
                rel_path = path.resolve().relative_to(root).as_posix()
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if query in line:
                    matches.append(f"{rel_path}:{line_no}:{line}")
                    if len(matches) >= max_results:
                        return matches
    return matches


def build_structure_context(target_root: Path, targets: list[str], max_records: int) -> dict[str, Any]:
    try:
        index = build_code_structure_index(target_root=target_root, file_scope="tracked")
        fallback_warnings: list[dict[str, Any]] = []
    except Exception as exc:  # noqa: BLE001 - copied validation trees may not have .git metadata
        index = build_code_structure_index(target_root=target_root, file_scope="all")
        fallback_warnings = [
            {
                "source": "structure_index",
                "reason": "tracked_scope_unavailable",
                "detail": str(exc),
                "fallback": "all_supported_files",
            }
        ]
    slice_value = build_index_slice(index, paths=targets or None, max_records=max_records)
    return {
        "summary": (
            f"file_scope={index.get('file_scope')} "
            f"selected_files={index.get('selected_file_count')} "
            f"indexed_files={index.get('summary', {}).get('indexed_file_count')}"
        ),
        "slice": slice_value,
        "warnings": fallback_warnings + [item for item in index.get("discovery_warnings", []) if isinstance(item, dict)],
    }


def context_tools_from_request(context: dict[str, Any]) -> set[str]:
    values = context.get("allowed_context_tools", [])
    if values is None:
        return set()
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ExecutionPlanningWorkflowError("context.allowed_context_tools must be a list of strings.")
    return set(values)


def reject_raw_codegraph(context_tools: set[str], context: dict[str, Any]) -> None:
    forbidden = {
        "raw_mcp_cypher",
        "codegraph_index_package",
        "codegraph_watch",
        "codegraph_delete",
        "codegraph_load_bundle",
        "raw_codegraph_context",
    }
    present = sorted(context_tools & forbidden)
    raw_text = json.dumps(context, ensure_ascii=True).lower()
    if present or "cypher" in raw_text or "raw codegraph" in raw_text:
        raise ExecutionPlanningWorkflowError(
            "Raw CodeGraphContext operations are not allowed for execution_planning.plan.",
            code="raw_codegraph_not_allowed",
            status=HTTPStatus.BAD_REQUEST,
        )


def validate_packet_operations(packet_operations: list[dict[str, Any]], target_root: Path) -> None:
    for index, operation in enumerate(packet_operations):
        if not isinstance(operation, dict):
            raise ExecutionPlanningWorkflowError("packet_operations entries must be objects.")
        kind = operation.get("kind")
        path_value = operation.get("path")
        if kind not in {"append_text", "replace_text", "create_file"}:
            raise ExecutionPlanningWorkflowError(f"packet_operations[{index}].kind is unsupported.")
        if not isinstance(path_value, str) or not path_value:
            raise ExecutionPlanningWorkflowError(f"packet_operations[{index}].path is required.")
        rel_path = normalize_repo_path(path_value)
        candidate = (target_root / rel_path).resolve()
        try:
            candidate.relative_to(target_root)
        except ValueError as exc:
            raise ExecutionPlanningWorkflowError(
                f"packet_operations[{index}].path is outside target_root.",
                code="target_root_not_allowed",
                status=HTTPStatus.FORBIDDEN,
            ) from exc
        if kind == "replace_text":
            old = operation.get("old")
            new = operation.get("new")
            if not isinstance(old, str) or not isinstance(new, str):
                raise ExecutionPlanningWorkflowError("replace_text packet operations require old and new strings.")
            if not candidate.exists():
                raise ExecutionPlanningWorkflowError(f"replace_text target does not exist: {rel_path}")
            if old not in candidate.read_text(encoding="utf-8", errors="replace"):
                raise ExecutionPlanningWorkflowError(f"replace_text old text was not found in {rel_path}.")


def packet_preview_packets(value: dict[str, Any]) -> list[dict[str, Any]]:
    preview = value.get("packet_file_preview")
    if not isinstance(preview, dict):
        return []
    packets = preview.get("packets")
    if not isinstance(packets, list):
        return []
    return [packet for packet in packets if isinstance(packet, dict)]


def plan_actions(value: dict[str, Any]) -> list[str]:
    return [
        step["action"]
        for step in list_value(value, "steps")
        if isinstance(step, dict) and isinstance(step.get("action"), str)
    ]


def verification_command_lists(value: dict[str, Any]) -> list[list[str]]:
    commands: list[list[str]] = []
    for item in list_value(value, "verification_commands"):
        if isinstance(item, dict) and isinstance(item.get("command"), list):
            command = item["command"]
            if all(isinstance(part, str) for part in command):
                commands.append(command)
    return commands


def packet_operation_verification_commands(packet_operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for operation in packet_operations:
        path = operation.get("path")
        if not isinstance(path, str) or not path or path in seen_paths:
            continue
        seen_paths.add(path)
        commands.append(
            {
                "id": f"packet-diff-{len(commands) + 1:04d}",
                "command": ["git", "diff", "--", path],
                "reason": "Review the exact draft packet delta for the target file.",
                "associated_files": [path],
                "timeout_seconds": 120,
                "source_refs": [path],
            }
        )
    return commands


def collect_selected_files(
    target_root: Path,
    impact: dict[str, Any],
    packet_design: dict[str, Any] | None,
    packet_operations: list[dict[str, Any]],
) -> list[str]:
    selected: set[str] = set()
    for key in ("affected_files", "related_tests"):
        for item in list_value(impact, key):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                selected.add(normalize_repo_path(item["path"]))
    for operation in packet_operations:
        if isinstance(operation.get("path"), str):
            selected.add(normalize_repo_path(operation["path"]))
    if packet_design:
        for packet in packet_preview_packets(packet_design):
            operation = packet.get("operation")
            if isinstance(operation, dict) and isinstance(operation.get("path"), str):
                selected.add(normalize_repo_path(operation["path"]))
            for path in packet.get("target_files", []):
                if isinstance(path, str):
                    selected.add(normalize_repo_path(path))
    return sorted(rel for rel in selected if (target_root / rel).exists())


def hash_selected_files(target_root: Path, selected_files: list[str]) -> dict[str, str]:
    return {rel: file_digest(target_root / rel) for rel in selected_files if (target_root / rel).exists()}


def gather_context_results(
    *,
    target_root: Path,
    context_plan: dict[str, Any],
    request_context: dict[str, Any],
    packet_operations: list[dict[str, Any]],
    user_request: str,
    budgets: dict[str, Any],
) -> dict[str, Any]:
    max_records = int(budgets.get("max_records", 50))
    max_files = int(budgets.get("max_files", 10))
    results: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    supplied = request_context.get("bounded_context")
    if isinstance(supplied, list):
        for index, item in enumerate(supplied[:max_records], 1):
            if isinstance(item, dict):
                results.append({"id": item.get("id") or f"CTX-SUPPLIED-{index:04d}", "source": "supplied", **item})

    for index, operation in enumerate(packet_operations, 1):
        path_value = operation.get("path")
        if not isinstance(path_value, str):
            continue
        rel_path = normalize_repo_path(path_value)
        path = target_root / rel_path
        if not path.exists():
            continue
        text = safe_read_text(path)
        old_text = operation.get("old") if isinstance(operation.get("old"), str) else ""
        refs = find_line_refs(text, old_text.splitlines()[0] if old_text else "", rel_path)
        results.append(
            {
                "id": f"CTX-PACKET-{index:04d}",
                "purpose": "packet_operation",
                "source": "read_file",
                "summary": f"Packet operation target {rel_path} was read for exact operation validation.",
                "source_refs": refs or [rel_path],
                "exact_text": old_text,
                "operation": operation,
            }
        )

    related_tests = discover_related_tests(
        target_root,
        packet_operations,
        user_request,
        max_files,
    )
    if related_tests is not None:
        results.append(related_tests)

    processed_files: set[str] = set()
    for request in list_value(context_plan, "context_requests"):
        if not isinstance(request, dict):
            continue
        request_id = request.get("id") if isinstance(request.get("id"), str) else f"CTX-{len(results) + 1:04d}"
        tool = request.get("suggested_tool")
        query = request.get("query")
        targets = request.get("targets") if isinstance(request.get("targets"), list) else []
        targets = [normalize_repo_path(item) for item in targets if isinstance(item, str)]
        max_results = request.get("max_results") if isinstance(request.get("max_results"), int) else 25
        max_results = min(max_results, max_records)
        if tool == "read_file":
            for rel_path in targets[:max_files]:
                if rel_path in processed_files:
                    continue
                path = target_root / rel_path
                if not path.exists():
                    warnings.append({"id": request_id, "tool": tool, "reason": "missing_file", "path": rel_path})
                    continue
                processed_files.add(rel_path)
                results.append(
                    {
                        "id": request_id,
                        "purpose": request.get("purpose"),
                        "source": "read_file",
                        "summary": f"Read selected file {rel_path}.",
                        "source_refs": [rel_path],
                        "excerpt": safe_read_text(path, 3000),
                    }
                )
        elif tool == "git_grep" and isinstance(query, str) and query:
            matches = run_git_grep(target_root, query, max_results)
            results.append(
                {
                    "id": request_id,
                    "purpose": request.get("purpose"),
                    "source": "git_grep",
                    "summary": f"Exact-string grep for {query!r} returned {len(matches)} matches.",
                    "source_refs": matches[:max_results],
                    "matches": matches[:max_results],
                }
            )
        elif tool == "structure_index":
            try:
                structure = build_structure_context(target_root, targets, max_records)
                results.append(
                    {
                        "id": request_id,
                        "purpose": request.get("purpose"),
                        "source": "structure_index",
                        "summary": structure["summary"],
                        "source_refs": targets,
                        "slice": structure["slice"],
                    }
                )
                for warning in structure.get("warnings", []):
                    if isinstance(warning, dict):
                        warnings.append({"id": request_id, "tool": tool, **warning})
            except Exception as exc:  # noqa: BLE001 - context should degrade into warnings
                warnings.append({"id": request_id, "tool": tool, "reason": "unavailable", "detail": str(exc)})
        elif tool == "manual":
            results.append(
                {
                    "id": request_id,
                    "purpose": request.get("purpose"),
                    "source": "manual",
                    "summary": str(request.get("reason") or "Manual clarification required."),
                    "source_refs": [],
                }
            )

    return {
        "kind": "execution_planning_context_results",
        "schema_version": SCHEMA_VERSION,
        "results": results[:max_records],
        "warnings": warnings,
    }


def json_size_bytes(value: dict[str, Any] | list[Any]) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def bounded_list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def compact_structure_slice(slice_value: Any) -> dict[str, Any]:
    text = json.dumps(slice_value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    paths: list[str] = []
    symbols: list[str] = []
    for path in re.findall(r'"path":"([^"]+)"', text):
        if path not in paths:
            paths.append(path)
        if len(paths) >= 12:
            break
    for symbol in re.findall(r'"(?:name|symbol)":"([^"]+)"', text):
        if symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= 20:
            break
    return {
        "summary": "Structure index slice compacted for model input; full slice remains in context-results.json.",
        "original_size_bytes": len(text.encode("utf-8")),
        "paths": paths,
        "symbols": symbols,
    }


def compact_context_result_for_model(result: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("id", "purpose", "source", "summary"):
        value = result.get(key)
        if value is not None:
            compact[key] = value
    source_refs = bounded_list(result.get("source_refs"), 10)
    if source_refs:
        compact["source_refs"] = source_refs

    source = result.get("source")
    if source == "read_file" and result.get("purpose") == "packet_operation":
        for key in ("exact_text", "operation"):
            value = result.get(key)
            if value is not None:
                compact[key] = value
        return compact

    if source == "structure_index":
        compact["slice_summary"] = compact_structure_slice(result.get("slice"))
        return compact

    if source == "git_grep":
        matches = bounded_list(result.get("matches"), 8)
        if matches:
            compact["matches"] = matches
            compact["truncated_match_count"] = max(0, len(bounded_list(result.get("matches"), 10_000)) - len(matches))
        return compact

    if source == "test_discovery":
        related_tests = []
        for item in bounded_list(result.get("related_test_files"), 5):
            if not isinstance(item, dict):
                continue
            compact_item = {
                "path": item.get("path"),
                "matched_terms": bounded_list(item.get("matched_terms"), 8),
                "source_refs": bounded_list(item.get("source_refs"), 3),
            }
            related_tests.append(compact_item)
        if related_tests:
            compact["related_test_files"] = related_tests
        matched_terms = bounded_list(result.get("matched_terms"), 8)
        if matched_terms:
            compact["matched_terms"] = matched_terms
        return compact

    if source == "supplied":
        for key in (
            "source_run_id",
            "approved_run_id",
            "packet_objective",
            "narrowed_edit_objective",
            "message",
        ):
            value = result.get(key)
            if value is not None:
                compact[key] = value
        return compact

    excerpt = result.get("excerpt")
    if isinstance(excerpt, str):
        compact["excerpt"] = excerpt[:1200]
        if len(excerpt) > 1200:
            compact["excerpt_truncated"] = True
    return compact


def compact_context_results_for_model(context_results: dict[str, Any]) -> dict[str, Any]:
    raw_results = context_results.get("results")
    results = raw_results if isinstance(raw_results, list) else []
    compact_results: list[dict[str, Any]] = []
    seen_structure_keys: set[tuple[Any, ...]] = set()
    deduplicated_count = 0
    compacted_slice_count = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("source") == "structure_index":
            refs = tuple(bounded_list(result.get("source_refs"), 10))
            key = (result.get("source"), refs)
            if key in seen_structure_keys:
                deduplicated_count += 1
                continue
            seen_structure_keys.add(key)
            compacted_slice_count += 1
        compact_results.append(compact_context_result_for_model(result))

    original_size = json_size_bytes(context_results)
    compact_value = {
        "kind": "execution_planning_context_results_for_model",
        "schema_version": SCHEMA_VERSION,
        "source_kind": context_results.get("kind"),
        "results": compact_results,
        "warnings": bounded_list(context_results.get("warnings"), 20),
        "compaction": {
            "original_result_count": len(results),
            "compacted_result_count": len(compact_results),
            "deduplicated_result_count": deduplicated_count,
            "compacted_structure_slice_count": compacted_slice_count,
            "original_size_bytes": original_size,
        },
    }
    compact_value["compaction"]["compact_size_bytes"] = json_size_bytes(compact_value)
    return compact_value


def packet_operations_for_model(packet_operations: list[dict[str, Any]]) -> Any:
    return packet_operations if packet_operations else None


def approved_step_id(plan: dict[str, Any]) -> str:
    for step in list_value(plan, "steps"):
        if isinstance(step, dict) and step.get("action") == "design_packet" and isinstance(step.get("id"), str):
            return step["id"]
    raise ExecutionPlanningWorkflowError("execution-plan-writer did not emit a design_packet step.")


def invoke_packet_preview_workflow(
    target_root: Path,
    run_dir: Path,
    packet_preview: dict[str, Any],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agentic-controller-packet-") as temp_dir:
        packet_file = Path(temp_dir) / "packet-preview.json"
        packet_file.write_text(json.dumps(packet_preview, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        result = invoke_implementation_workflow(
            ImplementationWorkflowInvocationRequest(
                target_root=target_root,
                output_dir=run_dir / "implementation-workflow",
                mode="draft",
                packet_file=packet_file,
                no_structure_index=True,
            )
        )
    return result.to_dict(include_report=True)


L1_DRAFT_PACKET_PROFILES: dict[str, dict[str, Any]] = {
    "workflow_router_natural_small_text_edit": {
        "scope": "draft_text_edit_packet_design_only",
        "id_prefix": "L1-TEXT-EDIT",
        "context_plan_id": "L1-TEXT-EDIT-CONTEXT",
        "packet_set_id": "L1-TEXT-EDIT-PACKETS",
        "source_plan_id": "L1-TEXT-EDIT-PLAN",
        "step_id": "L1-TEXT-EDIT-STEP-0001",
        "verification_plan_id": "L1-TEXT-EDIT-VERIFY",
        "task": "Draft exact small text edit packet.",
        "request_type": "documentation",
        "deterministic_path": "l1_small_text_edit",
        "useful_observation": "Deterministic L1 text edit draft completed.",
        "summary_text": f"{WORKFLOW_ID} deterministic L1 small text edit completed.",
        "notes": ["Deterministic L1 small text edit path used exact controller-generated packet operations."],
    },
    "workflow_router_natural_small_unit_test": {
        "scope": "draft_unit_test_packet_design_only",
        "id_prefix": "L1-UNIT-TEST",
        "context_plan_id": "L1-UNIT-TEST-CONTEXT",
        "packet_set_id": "L1-UNIT-TEST-PACKETS",
        "source_plan_id": "L1-UNIT-TEST-PLAN",
        "step_id": "L1-UNIT-TEST-STEP-0001",
        "verification_plan_id": "L1-UNIT-TEST-VERIFY",
        "task": "Draft exact small unit-test packet.",
        "request_type": "unit_test",
        "deterministic_path": "l1_small_unit_test",
        "useful_observation": "Deterministic L1 unit-test draft completed.",
        "summary_text": f"{WORKFLOW_ID} deterministic L1 small unit-test draft completed.",
        "notes": ["Deterministic L1 small unit-test path used exact controller-generated packet operations."],
    },
    "workflow_router_natural_simple_test_fix": {
        "scope": "draft_simple_test_fix_packet_design_only",
        "id_prefix": "L1-SIMPLE-FIX",
        "context_plan_id": "L1-SIMPLE-FIX-CONTEXT",
        "packet_set_id": "L1-SIMPLE-FIX-PACKETS",
        "source_plan_id": "L1-SIMPLE-FIX-PLAN",
        "step_id": "L1-SIMPLE-FIX-STEP-0001",
        "verification_plan_id": "L1-SIMPLE-FIX-VERIFY",
        "task": "Draft exact simple failing-test fix packet.",
        "request_type": "simple_test_fix",
        "deterministic_path": "l1_simple_failing_test_fix",
        "useful_observation": "Deterministic L1 simple failing-test fix draft completed.",
        "summary_text": f"{WORKFLOW_ID} deterministic L1 simple failing-test fix draft completed.",
        "notes": ["Deterministic L1 simple failing-test fix path used exact controller-generated packet operations."],
    },
    "workflow_router_natural_packet_objective": {
        "scope": "packet_design_only",
        "id_prefix": "GENERIC-PACKET-OBJECTIVE",
        "context_plan_id": "GENERIC-PACKET-OBJECTIVE-CONTEXT",
        "packet_set_id": "GENERIC-PACKET-OBJECTIVE-PACKETS",
        "source_plan_id": "GENERIC-PACKET-OBJECTIVE-PLAN",
        "step_id": "GENERIC-PACKET-OBJECTIVE-STEP-0001",
        "verification_plan_id": "GENERIC-PACKET-OBJECTIVE-VERIFY",
        "task": "Draft exact implementation packet from narrowed packet objective.",
        "request_type": "implementation_prep",
        "deterministic_path": "generic_packet_objective",
        "useful_observation": "Deterministic generic packet-objective draft completed.",
        "summary_text": f"{WORKFLOW_ID} deterministic generic packet-objective draft completed.",
        "notes": ["Deterministic generic packet-objective path used exact controller-generated packet operations."],
    },
    "workflow_router_natural_approved_investigation_packet_prep": {
        "scope": "packet_design_only",
        "id_prefix": "APPROVED-INVESTIGATION-PACKET",
        "context_plan_id": "APPROVED-INVESTIGATION-PACKET-CONTEXT",
        "packet_set_id": "APPROVED-INVESTIGATION-PACKET-PACKETS",
        "source_plan_id": "APPROVED-INVESTIGATION-PACKET-PLAN",
        "step_id": "APPROVED-INVESTIGATION-PACKET-STEP-0001",
        "verification_plan_id": "APPROVED-INVESTIGATION-PACKET-VERIFY",
        "task": "Draft exact implementation packet from approved investigation.",
        "request_type": "implementation_prep",
        "deterministic_path": "approved_investigation_packet_prep",
        "useful_observation": "Deterministic approved-investigation packet prep completed.",
        "summary_text": f"{WORKFLOW_ID} deterministic approved-investigation packet prep completed.",
        "notes": ["Deterministic approved-investigation packet-prep path used exact controller-generated packet operations."],
    },
    "workflow_router_natural_approval": {
        "scope": "packet_design_only",
        "id_prefix": "APPROVAL-CONTINUATION-PACKET",
        "context_plan_id": "APPROVAL-CONTINUATION-PACKET-CONTEXT",
        "packet_set_id": "APPROVAL-CONTINUATION-PACKET-PACKETS",
        "source_plan_id": "APPROVAL-CONTINUATION-PACKET-PLAN",
        "step_id": "APPROVAL-CONTINUATION-PACKET-STEP-0001",
        "verification_plan_id": "APPROVAL-CONTINUATION-PACKET-VERIFY",
        "task": "Draft exact implementation packet from approved continuation.",
        "request_type": "implementation_prep",
        "deterministic_path": "approval_continuation_packet_prep",
        "useful_observation": "Deterministic approval-continuation packet prep completed.",
        "summary_text": f"{WORKFLOW_ID} deterministic approval-continuation packet prep completed.",
        "notes": ["Deterministic approval-continuation path used exact controller-supplied packet operations."],
    },
}


def deterministic_l1_packet_draft_profile(request: ExecutionPlanningInvocationRequest) -> dict[str, Any] | None:
    bounded_context = request.context.get("bounded_context")
    if not isinstance(bounded_context, list):
        return None
    for item in bounded_context:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        profile = L1_DRAFT_PACKET_PROFILES.get(source)
        if profile is not None and request.approval.get("scope") == profile["scope"]:
            return profile
    return None


def packet_preview_from_operations(
    packet_operations: list[dict[str, Any]],
    *,
    id_prefix: str = "L1-PACKET",
    task: str = "Draft exact packet operation.",
) -> dict[str, Any]:
    packets: list[dict[str, Any]] = []
    for index, operation in enumerate(packet_operations, 1):
        path = operation.get("path")
        kind = operation.get("kind")
        packets.append(
            {
                "id": f"{id_prefix}-{index:04d}",
                "task": task,
                "target_files": [path] if isinstance(path, str) else [],
                "allowed_operations": [kind] if isinstance(kind, str) else [],
                "operation": operation,
                "source_refs": [{"path": path}] if isinstance(path, str) else [],
                "acceptance_criteria": [
                    "The packet preview uses only the exact controller-generated operation.",
                    "The target repository is not mutated during dry run.",
                ],
                "max_context_tokens": 2000,
            }
        )
    return {"schema_version": SCHEMA_VERSION, "packets": packets, "verification_commands": []}


def deterministic_l1_packet_draft_plan(
    request: ExecutionPlanningInvocationRequest,
    *,
    target_root: Path,
    run_dir: Path,
    artifacts: dict[str, str],
    budgets: dict[str, int],
    run_id: str,
    profile: dict[str, Any],
) -> InvocationResult:
    context_plan = {
        "context_plan_id": profile["context_plan_id"],
        "entrypoint": {
            "path": request.packet_operations[0].get("path") if request.packet_operations else None,
            "symbol": None,
            "confidence": "high",
        },
        "context_requests": [],
        "request_order": [],
        "context_budget": {
            "max_requests": budgets["max_context_requests"],
            "max_files": budgets["max_files"],
            "max_records": budgets["max_records"],
            "allow_broad_scan": False,
        },
        "excluded_context": [],
        "next_step": {"suggested_skill": "implementation-packet-designer", "reason": "Exact operation supplied."},
        "stop": {"required": False, "reason": None, "open_questions": []},
    }
    write_json(run_dir / ARTIFACT_NAMES["context_plan"], context_plan)
    artifacts["context_plan"] = str(run_dir / ARTIFACT_NAMES["context_plan"])

    context_results = gather_context_results(
        target_root=target_root,
        context_plan=context_plan,
        request_context=request.context,
        packet_operations=request.packet_operations,
        user_request=request.user_request,
        budgets=budgets,
    )
    write_json(run_dir / ARTIFACT_NAMES["context_results"], context_results)
    artifacts["context_results"] = str(run_dir / ARTIFACT_NAMES["context_results"])
    context_results_for_model = compact_context_results_for_model(context_results)
    write_json(run_dir / ARTIFACT_NAMES["context_results_for_model"], context_results_for_model)
    artifacts["context_results_for_model"] = str(run_dir / ARTIFACT_NAMES["context_results_for_model"])

    packet_preview = packet_preview_from_operations(
        request.packet_operations,
        id_prefix=profile["id_prefix"],
        task=profile["task"],
    )
    packet_design = {
        "packet_set_id": profile["packet_set_id"],
        "source_plan_id": profile["source_plan_id"],
        "approval": {
            "status": "approved",
            "approved_step_ids": [profile["step_id"]],
            "approval_refs": request.approval.get("approval_refs", []),
        },
        "workflow_compatibility": {
            "target_workflow": "implementation.workflow",
            "schema_version": 1,
            "supported_operations": ["append_text", "replace_text", "create_file"],
            "default_mode": "draft",
            "apply_mode_allowed_by_this_skill": False,
            "notes": profile["notes"],
        },
        "packet_candidates": [
            {**packet, "source_step_id": profile["step_id"]}
            for packet in packet_preview["packets"]
        ],
        "blocked_packets": [],
        "packet_file_preview": packet_preview,
        "next_step": {"suggested_skill": "verification-planner", "reason": "Draft packet is ready."},
        "stop": {"required": False, "reason": None, "open_questions": []},
    }
    write_json(run_dir / ARTIFACT_NAMES["implementation_packet_candidates"], packet_design)
    artifacts["implementation_packet_candidates"] = str(run_dir / ARTIFACT_NAMES["implementation_packet_candidates"])
    write_json(run_dir / ARTIFACT_NAMES["packet_preview"], packet_preview)
    artifacts["packet_preview"] = str(run_dir / ARTIFACT_NAMES["packet_preview"])

    verification_plan = {
        "verification_plan_id": profile["verification_plan_id"],
        "source_plan_id": profile["source_plan_id"],
        "source_packet_set_id": profile["packet_set_id"],
        "basis": {
            "target_files": [operation.get("path") for operation in request.packet_operations if isinstance(operation.get("path"), str)],
            "packet_ids": [packet["id"] for packet in packet_preview["packets"]],
            "acceptance_criteria": ["Review packet preview and implementation draft artifacts."],
            "related_tests": [],
            "risks": [],
            "unknowns": [],
        },
        "verification_commands": [],
        "manual_checks": [
            {
                "id": "manual-0001",
                "description": "Inspect packet-preview.json and implementation-workflow-report.json for the exact draft delta.",
            }
        ],
        "coverage_gaps": [],
        "rejected_commands": [],
        "next_step": {"suggested_skill": "feedback-capture", "reason": "Capture draft result."},
        "stop": {"required": False, "reason": None, "open_questions": []},
    }
    merge_controller_verification_commands(
        verification_plan,
        packet_operation_verification_commands(request.packet_operations)
        + controller_verification_commands(context_results),
    )
    write_json(run_dir / ARTIFACT_NAMES["verification_plan"], verification_plan)
    artifacts["verification_plan"] = str(run_dir / ARTIFACT_NAMES["verification_plan"])

    selected_files = sorted(
        {
            normalize_repo_path(operation["path"])
            for operation in request.packet_operations
            if isinstance(operation.get("path"), str)
        }
    )
    before_hashes = hash_selected_files(target_root, selected_files)
    implementation_workflow_report = invoke_packet_preview_workflow(target_root, run_dir, packet_preview)
    write_json(run_dir / ARTIFACT_NAMES["implementation_workflow_report"], implementation_workflow_report)
    artifacts["implementation_workflow_report"] = str(run_dir / ARTIFACT_NAMES["implementation_workflow_report"])
    if implementation_workflow_report.get("status") != WorkflowStatus.COMPLETED.value:
        raise ExecutionPlanningWorkflowError("implementation.workflow draft run did not complete.")
    after_hashes = hash_selected_files(target_root, selected_files)
    changed_files = [rel for rel in selected_files if before_hashes.get(rel) != after_hashes.get(rel)]
    if changed_files:
        raise ExecutionPlanningWorkflowError(
            f"Selected target files changed during deterministic dry run: {', '.join(changed_files)}",
            code="draft_mutation_detected",
        )

    feedback = {
        "workflow_id": WORKFLOW_ID,
        "run_id": run_id,
        "useful": [{"id": "USEFUL-0001", "observation": profile["useful_observation"], "evidence_refs": []}],
        "wrong": [],
        "missing": [],
        "too_slow_or_noisy": [],
        "next_adjustments": [],
    }
    write_json(run_dir / ARTIFACT_NAMES["feedback_record"], feedback)
    artifacts["feedback_record"] = str(run_dir / ARTIFACT_NAMES["feedback_record"])

    summary = {
        "request_type": profile["request_type"],
        "selected_entrypoint": context_plan["entrypoint"],
        "plan_mode": "implementation_prep",
        "plan_actions": ["design_packet"],
        "packet_candidates": len(packet_design["packet_candidates"]),
        "packet_file_preview_packets": len(packet_preview["packets"]),
        "verification_commands": verification_command_lists(verification_plan),
        "repo_mutated": bool(changed_files),
        "next_required_decision": "review artifacts and approve or reject follow-up work",
        "feedback_useful": len(feedback["useful"]),
        "feedback_missing": len(feedback["missing"]),
        "context_compaction": context_results_for_model.get("compaction"),
        "deterministic_path": profile["deterministic_path"],
        "verification_command_count": len(verification_command_lists(verification_plan)),
    }
    non_mutation = {
        "checked": bool(selected_files),
        "selected_files": selected_files,
        "before_hashes": before_hashes,
        "after_hashes": after_hashes,
        "changed_files": changed_files,
    }
    report = {
        "kind": "execution_planning_report",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "workflow": WORKFLOW_ID,
        "status": WorkflowStatus.COMPLETED.value,
        "mode": request.mode,
        "target_root": str(target_root),
        "skill_chain": [],
        "artifacts": artifacts,
        "summary": summary,
        "context_warnings": context_results.get("warnings", []),
        "non_mutation": non_mutation,
        "model_call_count": 0,
    }
    run_state = {
        "kind": "execution_planning_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "mode": request.mode,
        "target_root": str(target_root),
        "artifacts": artifacts,
        "summary": summary,
        "non_mutation": non_mutation,
        "updated_at": utc_now(),
    }
    write_run_state(run_dir, run_state)
    artifacts["run_state"] = str(run_dir / ARTIFACT_NAMES["run_state"])
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=profile["summary_text"],
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / ARTIFACT_NAMES["run_state"])},
        report=report,
        run_id=run_id,
    )


def validate_request_basics(request: ExecutionPlanningInvocationRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise ExecutionPlanningWorkflowError("workflow must be execution_planning.plan.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise ExecutionPlanningWorkflowError("schema_version must be 1.")
    if request.mode not in ALLOWED_MODES:
        raise ExecutionPlanningWorkflowError("Unsupported execution planning mode.", code="unsupported_mode")
    if not isinstance(request.user_request, str) or not request.user_request.strip():
        raise ExecutionPlanningWorkflowError("user_request is required.")
    unsupported_skills = sorted(set(request.skill_chain) - set(DEFAULT_SKILL_CHAIN))
    if unsupported_skills:
        raise ExecutionPlanningWorkflowError(
            f"Unsupported skill(s): {', '.join(unsupported_skills)}",
            code="unsupported_skill",
        )
    if not all(isinstance(skill, str) for skill in request.skill_chain):
        raise ExecutionPlanningWorkflowError("skill_chain must be a list of strings.")
    if request.mode in {"implementation_prep", "dry_run"}:
        approval_status = request.approval.get("status")
        if approval_status != "approved_for_packet_design":
            raise ExecutionPlanningWorkflowError(
                "implementation_prep and dry_run require packet-design approval.",
                code="missing_packet_design_approval",
                status=HTTPStatus.BAD_REQUEST,
            )
        if request.approval.get("apply_allowed") is True:
            raise ExecutionPlanningWorkflowError(
                "Apply mode is not supported by execution_planning.plan.",
                code="apply_mode_not_supported",
                status=HTTPStatus.BAD_REQUEST,
            )
        if not request.packet_operations:
            raise ExecutionPlanningWorkflowError(
                "implementation_prep and dry_run require packet_operations in this controller version.",
                code="missing_packet_operations",
                status=HTTPStatus.BAD_REQUEST,
            )


def validate_budgets(budgets: dict[str, Any]) -> dict[str, int]:
    allowed = {
        "max_context_requests",
        "max_files",
        "max_records",
        "max_model_calls",
        "max_output_tokens",
        "timeout_seconds",
    }
    unknown = sorted(set(budgets) - allowed)
    if unknown:
        raise ExecutionPlanningWorkflowError(f"Unsupported budget field(s): {', '.join(unknown)}")
    defaults = {
        "max_context_requests": 5,
        "max_files": 10,
        "max_records": 50,
        "max_model_calls": 12,
        "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
    }
    resolved: dict[str, int] = {}
    for key, default in defaults.items():
        value = budgets.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ExecutionPlanningWorkflowError(f"Budget {key} must be an integer >= 1.")
        resolved[key] = value
    return resolved


def artifact_paths(run_dir: Path, keys: list[str]) -> dict[str, str]:
    return {key: str(run_dir / ARTIFACT_NAMES[key]) for key in keys}


def write_run_state(run_dir: Path, state: dict[str, Any]) -> Path:
    path = run_dir / ARTIFACT_NAMES["run_state"]
    write_json(path, state)
    return path


def invoke_execution_planning(request: ExecutionPlanningInvocationRequest) -> InvocationResult:
    validate_request_basics(request)
    target_root = Path(request.target_root).resolve()
    config_root = Path(request.config_root).resolve()
    output_root = Path(request.output_root).resolve()
    budgets = validate_budgets(request.budgets)
    context_tools = context_tools_from_request(request.context)
    reject_raw_codegraph(context_tools, request.context)
    unsupported_tools = sorted(context_tools - ALLOWED_CONTEXT_TOOLS)
    if unsupported_tools:
        raise ExecutionPlanningWorkflowError(
            f"Unsupported context tool(s): {', '.join(unsupported_tools)}",
            code="unsupported_context_tool",
            status=HTTPStatus.BAD_REQUEST,
        )
    validate_packet_operations(request.packet_operations, target_root)

    run_id = f"execution-planning-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    skill_root = config_root / ".qwen" / "skills"
    role_base_url = request.role_base_url or role_base_url_from_manifest(config_root, request.role_id)
    artifacts: dict[str, str] = {}
    failures: list[dict[str, Any]] = []
    outputs: dict[str, dict[str, Any]] = {}
    model_call_count = 0

    request_artifact = {
        "kind": "execution_planning_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(target_root),
        "mode": request.mode,
        "user_request": request.user_request,
        "skill_chain": request.skill_chain,
        "approval": request.approval,
        "context": request.context,
        "packet_operations": request.packet_operations,
        "budgets": budgets,
        "created_at": utc_now(),
    }
    write_json(run_dir / ARTIFACT_NAMES["request"], request_artifact)
    artifacts["request"] = str(run_dir / ARTIFACT_NAMES["request"])

    l1_draft_profile = deterministic_l1_packet_draft_profile(request)
    if request.mode in {"implementation_prep", "dry_run"} and l1_draft_profile is not None:
        return deterministic_l1_packet_draft_plan(
            request,
            target_root=target_root,
            run_dir=run_dir,
            artifacts=artifacts,
            budgets=budgets,
            run_id=run_id,
            profile=l1_draft_profile,
        )

    def call(skill_name: str, case_input: dict[str, Any], artifact_key: str) -> dict[str, Any]:
        nonlocal model_call_count
        retry_reason: str | None = None
        for attempt in range(2):
            model_call_count += 1
            if model_call_count > budgets["max_model_calls"]:
                raise ExecutionPlanningWorkflowError(
                    "Model call budget exceeded.",
                    code="budget_exceeded",
                    details={
                        "failed_skill": skill_name,
                        "artifact_key": artifact_key,
                        "attempt": attempt + 1,
                        "model_call_count": model_call_count,
                        "max_model_calls": budgets["max_model_calls"],
                        "retry_guidance": "Increase max_model_calls or reduce the requested skill chain.",
                    },
                )
            started_at = time.monotonic()
            try:
                value = chat_skill(
                    role_base_url=role_base_url,
                    model=request.model,
                    skill_root=skill_root,
                    skill_name=skill_name,
                    case_input=case_input,
                    timeout_seconds=budgets["timeout_seconds"],
                    max_output_tokens=budgets["max_output_tokens"],
                    retry_reason=retry_reason,
                )
                break
            except ExecutionPlanningWorkflowError as exc:
                if exc.code == "invalid_skill_output" and attempt == 0:
                    retry_reason = str(exc)
                    continue
                elapsed_seconds = round(time.monotonic() - started_at, 3)
                details = {
                    **exc.details,
                    "failed_skill": skill_name,
                    "artifact_key": artifact_key,
                    "attempt": attempt + 1,
                    "model_call_count": model_call_count,
                    "max_model_calls": budgets["max_model_calls"],
                    "model_call_elapsed_seconds": elapsed_seconds,
                    "timeout_seconds": budgets["timeout_seconds"],
                    "max_output_tokens": budgets["max_output_tokens"],
                    "retry_guidance": (
                        "Inspect the failed skill input and reduce model-visible context before retrying."
                    ),
                }
                raise ExecutionPlanningWorkflowError(
                    str(exc),
                    code=exc.code,
                    status=exc.status,
                    details=details,
                ) from exc
        outputs[skill_name] = value
        write_json(run_dir / ARTIFACT_NAMES[artifact_key], value)
        artifacts[artifact_key] = str(run_dir / ARTIFACT_NAMES[artifact_key])
        return value

    try:
        triage = call(
            "request-triage",
            {
                "user_request": request.user_request,
                "target_root": str(target_root),
                "requested_mode": request.mode,
                "approval": request.approval,
                "packet_operations_requested": bool(request.packet_operations),
            },
            "request_triage",
        )
        scope = call(
            "scope-and-assumptions",
            {
                "request_type": triage.get("request_type"),
                "user_request": request.user_request,
                "target_root": str(target_root),
                "known_target": request.context.get("entrypoint_hints"),
                "known_bounded_context": request.context.get("bounded_context", []),
                "write_policy": request.approval,
                "mode": request.mode,
            },
            "scope_and_assumptions",
        )
        entrypoint = call(
            "entrypoint-finder",
            {
                "request_type": triage.get("request_type"),
                "user_request": request.user_request,
                "scope": scope.get("scope"),
                "goal": scope.get("goal"),
                "bounded_context": request.context.get("bounded_context", []),
                "entrypoint_hints": request.context.get("entrypoint_hints", []),
                "packet_operations": packet_operations_for_model(request.packet_operations),
            },
            "entrypoint_finder",
        )
        if stop_required(entrypoint):
            raise ExecutionPlanningWorkflowError("entrypoint-finder stopped; see artifact for open questions.")
        context_plan = call(
            "context-plan-builder",
            {
                "objective": request.user_request,
                "selected_entrypoint": entrypoint.get("selected_entrypoint"),
                "followup_context_needed": entrypoint.get("followup_context_needed"),
                "allowed_tools": sorted(ALLOWED_CONTEXT_TOOLS),
                "target_root": str(target_root),
                "budgets": budgets,
            },
            "context_plan",
        )
        if stop_required(context_plan):
            raise ExecutionPlanningWorkflowError("context-plan-builder stopped; see artifact for open questions.")
        context_results = gather_context_results(
            target_root=target_root,
            context_plan=context_plan,
            request_context=request.context,
            packet_operations=request.packet_operations,
            user_request=request.user_request,
            budgets=budgets,
        )
        write_json(run_dir / ARTIFACT_NAMES["context_results"], context_results)
        artifacts["context_results"] = str(run_dir / ARTIFACT_NAMES["context_results"])
        context_results_for_model = compact_context_results_for_model(context_results)
        write_json(run_dir / ARTIFACT_NAMES["context_results_for_model"], context_results_for_model)
        artifacts["context_results_for_model"] = str(run_dir / ARTIFACT_NAMES["context_results_for_model"])

        impact = call(
            "impact-map-builder",
            {
                "request_type": triage.get("request_type"),
                "objective": request.user_request,
                "entrypoint": entrypoint.get("selected_entrypoint"),
                "context_plan": context_plan,
                "context_results": context_results_for_model["results"],
                "context_compaction": context_results_for_model["compaction"],
            },
            "impact_map",
        )
        if stop_required(impact):
            raise ExecutionPlanningWorkflowError("impact-map-builder stopped; see artifact for open questions.")

        plan = call(
            "execution-plan-writer",
            {
                "request_type": triage.get("request_type"),
                "objective": request.user_request,
                "entrypoint": entrypoint.get("selected_entrypoint"),
                "impact_map": impact,
                "user_approvals": request.approval.get("approval_refs", []),
                "mode": request.mode,
                "operation_details": (
                    request.packet_operations[0]
                    if len(request.packet_operations) == 1
                    else request.packet_operations
                ),
            },
            "execution_plan",
        )
        if stop_required(plan):
            raise ExecutionPlanningWorkflowError("execution-plan-writer stopped; see artifact for open questions.")

        packet_design: dict[str, Any] | None = None
        verification_plan: dict[str, Any] | None = None
        implementation_workflow_report: dict[str, Any] | None = None
        selected_files: list[str] = []
        before_hashes: dict[str, str] = {}
        after_hashes: dict[str, str] = {}
        changed_files: list[str] = []

        if request.mode in {"implementation_prep", "dry_run"}:
            design_step_id = approved_step_id(plan)
            packet_design = call(
                "implementation-packet-designer",
                {
                    "execution_plan": plan,
                    "impact_map": impact,
                    "approved_step_ids": [design_step_id],
                    "approval_refs": request.approval.get("approval_refs", []),
                    "requested_mode": "draft",
                    "operation_details": [
                        {**operation, "source_step_id": design_step_id}
                        for operation in request.packet_operations
                    ],
                },
                "implementation_packet_candidates",
            )
            if stop_required(packet_design):
                raise ExecutionPlanningWorkflowError(
                    "implementation-packet-designer stopped; see artifact for open questions."
                )
            preview = packet_design.get("packet_file_preview")
            if not isinstance(preview, dict) or not packet_preview_packets(packet_design):
                raise ExecutionPlanningWorkflowError(
                    "implementation-packet-designer did not produce packet_file_preview.packets.",
                    code="invalid_skill_output",
                )
            write_json(run_dir / ARTIFACT_NAMES["packet_preview"], preview)
            artifacts["packet_preview"] = str(run_dir / ARTIFACT_NAMES["packet_preview"])

            verification_plan = call(
                "verification-planner",
                {
                    "execution_plan": plan,
                    "packet_design": packet_design,
                    "impact_map": impact,
                },
                "verification_plan",
            )
            if stop_required(verification_plan):
                raise ExecutionPlanningWorkflowError("verification-planner stopped; see artifact for open questions.")
            merge_controller_verification_commands(
                verification_plan,
                controller_verification_commands(context_results),
            )
            write_json(run_dir / ARTIFACT_NAMES["verification_plan"], verification_plan)
            normalize_verification_commands(verification_plan.get("verification_commands"))

            selected_files = collect_selected_files(target_root, impact, packet_design, request.packet_operations)
            before_hashes = hash_selected_files(target_root, selected_files)
            if request.mode == "dry_run":
                implementation_workflow_report = invoke_packet_preview_workflow(
                    target_root,
                    run_dir,
                    preview,
                )
                write_json(run_dir / ARTIFACT_NAMES["implementation_workflow_report"], implementation_workflow_report)
                artifacts["implementation_workflow_report"] = str(run_dir / ARTIFACT_NAMES["implementation_workflow_report"])
                if implementation_workflow_report.get("status") != WorkflowStatus.COMPLETED.value:
                    raise ExecutionPlanningWorkflowError("implementation.workflow draft run did not complete.")
            after_hashes = hash_selected_files(target_root, selected_files)
            changed_files = [rel for rel in selected_files if before_hashes.get(rel) != after_hashes.get(rel)]
            if changed_files:
                raise ExecutionPlanningWorkflowError(
                    f"Selected target files changed during dry run: {', '.join(changed_files)}",
                    code="draft_mutation_detected",
                )

        feedback = call(
            "feedback-capture",
            {
                "workflow_id": WORKFLOW_ID,
                "run_id": run_id,
                "result_summary": {
                    "workflow": WORKFLOW_ID,
                    "mode": request.mode,
                    "target_root": str(target_root),
                    "selected_entrypoint": entrypoint.get("selected_entrypoint"),
                    "plan_mode": plan.get("plan_mode"),
                    "plan_actions": plan_actions(plan),
                    "packet_preview_packets": (
                        len(packet_preview_packets(packet_design)) if packet_design is not None else 0
                    ),
                    "verification_commands": (
                        verification_command_lists(verification_plan) if verification_plan is not None else []
                    ),
                    "repo_mutated": bool(changed_files),
                    "changed_files": changed_files,
                },
                "tester_feedback": request.feedback.get("tester_feedback")
                if isinstance(request.feedback.get("tester_feedback"), str)
                else "Capture workflow validation result and remaining gaps.",
            },
            "feedback_record",
        )

        status = WorkflowStatus.COMPLETED
        summary = {
            "request_type": triage.get("request_type"),
            "selected_entrypoint": entrypoint.get("selected_entrypoint"),
            "plan_mode": plan.get("plan_mode"),
            "plan_actions": plan_actions(plan),
            "packet_candidates": (
                len(packet_design.get("packet_candidates") or []) if packet_design is not None else 0
            ),
            "packet_file_preview_packets": (
                len(packet_preview_packets(packet_design)) if packet_design is not None else 0
            ),
            "verification_commands": (
                verification_command_lists(verification_plan) if verification_plan is not None else []
            ),
            "repo_mutated": bool(changed_files),
            "next_required_decision": "review artifacts and approve or reject follow-up work",
            "feedback_useful": len(feedback.get("useful") or []),
            "feedback_missing": len(feedback.get("missing") or []),
            "context_compaction": context_results_for_model.get("compaction"),
        }
        non_mutation = {
            "checked": bool(selected_files),
            "selected_files": selected_files,
            "before_hashes": before_hashes,
            "after_hashes": after_hashes,
            "changed_files": changed_files,
        }
        report = {
            "kind": "execution_planning_report",
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "workflow": WORKFLOW_ID,
            "status": status.value,
            "mode": request.mode,
            "target_root": str(target_root),
            "skill_chain": request.skill_chain,
            "artifacts": artifacts,
            "summary": summary,
            "context_warnings": context_results.get("warnings", []),
            "non_mutation": non_mutation,
            "model_call_count": model_call_count,
        }
        run_state = {
            "kind": "execution_planning_run_state",
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "workflow": WORKFLOW_ID,
            "status": status.value,
            "mode": request.mode,
            "target_root": str(target_root),
            "artifacts": artifacts,
            "summary": summary,
            "non_mutation": non_mutation,
            "updated_at": utc_now(),
        }
        state_path = write_run_state(run_dir, run_state)
        artifacts["run_state"] = str(state_path)
        report["artifacts"] = artifacts
        return InvocationResult(
            workflow=WORKFLOW_ID,
            status=status,
            artifact_paths=artifacts,
            summary_text=f"{WORKFLOW_ID} {status.value}: {summary['packet_candidates']} packet candidates",
            failures=failures,
            resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(state_path)},
            report=report,
            run_id=run_id,
        )
    except ExecutionPlanningWorkflowError as exc:
        failure = {"failed_at": utc_now(), "code": exc.code, "message": str(exc)}
        failure.update(exc.details)
        failures.append(failure)
        state_path = write_run_state(
            run_dir,
            {
                "kind": "execution_planning_run_state",
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "workflow": WORKFLOW_ID,
                "status": WorkflowStatus.FAILED.value,
                "mode": request.mode,
                "target_root": str(target_root),
                "artifacts": artifacts,
                "failures": failures,
                "model_call_count": model_call_count,
                "updated_at": utc_now(),
            },
        )
        artifacts["run_state"] = str(state_path)
        raise
