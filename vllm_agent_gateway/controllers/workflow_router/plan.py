"""Natural-language workflow routing.

The router is the product-facing decision layer. It selects workflows from
registry metadata, then records bounded context-source intent before delegated
workflows perform any file-content reads.
"""

from __future__ import annotations

import json
import hashlib
import difflib
import os
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.tool_policy import ControllerToolPolicyError, resolve_controller_tool_policy
from vllm_agent_gateway.acceptance.advanced_refactor_readiness import advanced_refactor_gate_decision
from vllm_agent_gateway.controllers.code_context.lookup import (
    CodeContextLookupError,
    CodeContextLookupRequest,
    invoke_code_context_lookup,
)
from vllm_agent_gateway.controllers.code_investigation.plan import (
    CodeInvestigationError,
    CodeInvestigationRequest,
    invoke_code_investigation,
)
from vllm_agent_gateway.controllers.documenter.orchestrator import DEFAULT_MODEL
from vllm_agent_gateway.controllers.execution_planning.workflow import (
    ExecutionPlanningInvocationRequest,
    ExecutionPlanningWorkflowError,
    invoke_execution_planning,
)
from vllm_agent_gateway.controllers.refactor.single_path import (
    RefactorSinglePathError,
    RefactorSinglePathRequest,
    invoke_refactor_single_path,
)
from vllm_agent_gateway.controllers.skill_batch.propose import (
    SkillBatchProposalError,
    SkillBatchProposalRequest,
    invoke_skill_batch_proposal,
)
from vllm_agent_gateway.controllers.task_decompose.decompose import (
    TaskDecompositionError,
    TaskDecompositionRequest,
    invoke_task_decomposition,
)
from vllm_agent_gateway.implementation.workflow import (
    ImplementationWorkflowError,
    ImplementationWorkflowInvocationRequest,
    invoke_implementation_workflow,
)
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.model_capability_routing import (
    evaluate_model_capability_routing,
    model_capability_blockers,
)
from vllm_agent_gateway.controllers.natural_query import (
    change_subject_queries_from_request,
    strip_filesystem_paths,
)
from vllm_agent_gateway.skills.registry import (
    SkillRegistryError,
    explain_skill_selection_for_workflow,
    load_skill_registry as load_canonical_skill_registry,
    selected_skill_capability_route_keys,
    select_skills_for_workflow,
)


WORKFLOW_ID = "workflow_router.plan"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "workflow-router"
DEFAULT_ROLE_ID = "dispatcher/default"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_OUTPUT_TOKENS = 800
PROMPT_SKILL_COVERAGE_PATH = Path("runtime") / "prompt_skill_coverage.json"
PROPOSAL_CONTEXT_LINES = 18
PROPOSAL_MAX_WINDOWS_PER_FILE = 3
PROPOSAL_MAX_SNIPPET_CHARS = 5000
SMALL_TEXT_EDIT_MAX_FILE_BYTES = 64 * 1024
SMALL_UNIT_TEST_MAX_FILE_BYTES = 128 * 1024
SIMPLE_TEST_FIX_MAX_FILE_BYTES = 512 * 1024
DISPOSABLE_TREE_DIGEST_EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache"}
DISPOSABLE_APPLY_OPERATION_KINDS = {"append_text", "replace_text"}
CORE_INVESTIGATION_SKILLS = (
    "request-triage",
    "scope-and-assumptions",
    "entrypoint-finder",
    "context-plan-builder",
)
ROUTER_RULE_SKILL_OVERRIDES = {
    "l2_ci_log_triage_terms": "ci-log-failure-summarizer",
    "l2_table_read_write_lookup_terms": "table-read-write-locator",
    "l2_runtime_reproduction_checklist_terms": "runtime-reproduction-checklist-writer",
    "l2_user_facing_message_test_target_terms": "user-facing-message-test-target-locator",
    "l2_test_selection_terms": "test-selection-rationale",
}
SELECTION_MIN_CONFIDENCE = "medium"
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
MAX_REJECTED_CANDIDATES = 12
ALLOWED_MODES = {"plan_only", "execute_read_only", "implementation_prep", "apply_disposable_copy"}
CONTEXT_SOURCE_MAX_SELECTED = 5
CONTEXT_LAYOUT_MAX_SCANNED_FILES = 500
CONTEXT_LAYOUT_MAX_SAMPLE_FILES = 20
ROUTABLE_WORKFLOWS = {
    "code_context.lookup",
    "code_investigation.plan",
    "refactor.single_path",
    "execution_planning.plan",
    "workflow_feedback.record",
    "skill_batch.propose",
    "task.decompose",
}
READ_ONLY_WORKFLOWS = {
    "code_context.lookup",
    "code_investigation.plan",
    "refactor.single_path",
    "skill_batch.propose",
    "task.decompose",
}
RAW_CONTEXT_TERMS = {
    "raw_codegraph",
    "raw codegraph",
    "raw_mcp",
    "raw mcp",
    "cypher",
    "codegraph_index_package",
    "codegraph watch",
    "codegraph delete",
    "codegraph load",
}
APPROVAL_BYPASS_TERMS = {
    "skip approval",
    "without approval",
    "no approval",
    "bypass approval",
    "apply immediately",
    "apply now",
    "mutate now",
    "edit now",
    "change files now",
    "commit it",
}
UNSUPPORTED_NON_DEV_TERMS = {
    "book a flight",
    "weather",
    "restaurant",
    "calendar invite",
    "send email",
    "stock price",
}
TEXT_EDIT_FILE_EXTENSIONS = {".md", ".rst", ".txt"}
CONTEXT_LAYOUT_SUPPORTED_EXTENSIONS = {
    ".c",
    ".cfg",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".php",
    ".py",
    ".pyi",
    ".rb",
    ".rs",
    ".rst",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
CONTEXT_LAYOUT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "runtime-state",
    "vendor",
}
CONTEXT_SOURCE_CATALOG: dict[str, dict[str, Any]] = {
    "ast_index": {
        "description": "Bounded structure and symbol discovery for code files.",
        "tool_ids": ["structure_index"],
        "artifact_keys": ["investigation_evidence", "lookup_results", "context_results", "impact_map"],
        "budget": {"max_records": 50, "max_files": 10},
    },
    "text_search": {
        "description": "Bounded exact-string search before selected file reads.",
        "tool_ids": ["git_grep", "read_file"],
        "artifact_keys": ["investigation_evidence", "lookup_results", "context_results"],
        "budget": {"max_matches": 50, "max_files": 10},
    },
    "config_lookup": {
        "description": "Configuration and environment-variable lookup.",
        "tool_ids": ["git_grep", "read_file"],
        "artifact_keys": ["configuration_lookup", "configuration_effect_summary", "investigation_evidence"],
        "budget": {"max_matches": 50, "max_files": 10},
    },
    "test_lookup": {
        "description": "Related test and verification-command discovery.",
        "tool_ids": ["git_grep", "read_file"],
        "artifact_keys": ["related_tests", "verification_plan", "test_selection_plan", "investigation_evidence"],
        "budget": {"max_tests": 25, "max_files": 10},
    },
    "curated_relationship_lookup": {
        "description": "Curated caller, callee, import, and dependency relationship lookup.",
        "tool_ids": ["codegraph_context", "structure_index", "git_grep", "read_file"],
        "artifact_keys": ["relationship_results", "usage_summary", "dependency_lookup", "lookup_results"],
        "budget": {"max_relationship_results": 25, "max_queries": 3},
    },
}


class WorkflowRouterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "workflow_router_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class WorkflowRouterPlanRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    mode: str = "plan_only"
    budgets: dict[str, Any] = field(default_factory=dict)
    approval: dict[str, Any] = field(default_factory=dict)
    packet_operations: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    feedback: dict[str, Any] = field(default_factory=dict)
    execution_budgets: dict[str, Any] = field(default_factory=dict)
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
    ) -> "WorkflowRouterPlanRequest":
        values: dict[str, Any] = {
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


def artifact_safe_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return sanitized or "artifact"


def extract_json_object(text: str) -> dict[str, Any]:
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
        raise WorkflowRouterError("Model route output was not a JSON object.", code="invalid_model_route")
    return value


def post_json(url: str, payload: dict[str, Any], timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise WorkflowRouterError(f"Response from {url} was not a JSON object.", code="invalid_model_route")
    return value


def bounded_string(value: Any, limit: int = 1000) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def append_unique(values: list[str], candidate: str | None, *, limit: int | None = None) -> None:
    if not isinstance(candidate, str):
        return
    item = candidate.strip()
    if not item or item in values:
        return
    if limit is not None and len(values) >= limit:
        return
    values.append(item)


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowRouterError(f"Missing {label}: {path}", code="missing_registry") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowRouterError(f"Invalid {label}: {exc}", code="invalid_registry") from exc
    if not isinstance(value, dict):
        raise WorkflowRouterError(f"{label} must contain a JSON object.", code="invalid_registry")
    return value


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise WorkflowRouterError(f"{label} must be a list of strings.", code="invalid_registry")
    return list(value)


def validate_budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise WorkflowRouterError("budgets must be a JSON object.", code="invalid_budgets", status=HTTPStatus.BAD_REQUEST)
    defaults = {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5}
    budgets = dict(defaults)
    for key, item in value.items():
        if key not in defaults:
            raise WorkflowRouterError(
                f"Unsupported budget field: {key}",
                code="unsupported_budget_field",
                status=HTTPStatus.BAD_REQUEST,
            )
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise WorkflowRouterError(
                f"budgets.{key} must be a non-negative integer.",
                code="invalid_budget_value",
                status=HTTPStatus.BAD_REQUEST,
            )
        budgets[key] = item
    if budgets["max_model_calls"] > 3:
        raise WorkflowRouterError("budgets.max_model_calls must be 3 or lower.", code="invalid_budget_value")
    if not 1 <= budgets["max_selected_skills"] <= 20:
        raise WorkflowRouterError("budgets.max_selected_skills must be from 1 through 20.", code="invalid_budget_value")
    if not 0 <= budgets["max_selected_tools"] <= 20:
        raise WorkflowRouterError("budgets.max_selected_tools must be from 0 through 20.", code="invalid_budget_value")
    return budgets


def load_skill_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    try:
        return load_canonical_skill_registry(config_root)
    except SkillRegistryError as exc:
        raise WorkflowRouterError(str(exc), code=exc.code) from exc


def load_workflow_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list):
        raise WorkflowRouterError("runtime/workflows.json must contain a workflows list.", code="invalid_registry")
    registry: dict[str, dict[str, Any]] = {}
    for item in workflows:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise WorkflowRouterError("Each workflow registry item must contain an id.", code="invalid_registry")
        workflow_id = item["id"]
        if workflow_id in ROUTABLE_WORKFLOWS or workflow_id == WORKFLOW_ID:
            registry[workflow_id] = {
                "id": workflow_id,
                "description": bounded_string(item.get("description", ""), 500),
                "controller_tool_ids": string_list(item.get("controller_tool_ids", []), f"workflow {workflow_id}.controller_tool_ids"),
                "default_role_id": item.get("default_role_id") if isinstance(item.get("default_role_id"), str) else None,
            }
    return registry


def load_tool_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "tools.json", "tool registry")
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        raise WorkflowRouterError("runtime/tools.json must contain a tools list.", code="invalid_registry")
    registry: dict[str, dict[str, Any]] = {}
    for item in tools:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise WorkflowRouterError("Each tool registry item must contain an id.", code="invalid_registry")
        registry[item["id"]] = {
            "id": item["id"],
            "kind": item.get("kind"),
            "description": bounded_string(item.get("description", ""), 500),
            "read_only": bool(item.get("read_only")),
        }
    return registry


def validate_request_basics(request: WorkflowRouterPlanRequest) -> dict[str, Any]:
    if request.workflow != WORKFLOW_ID:
        raise WorkflowRouterError("workflow must be workflow_router.plan.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise WorkflowRouterError("schema_version must be 1.", code="unsupported_schema_version")
    if request.mode not in ALLOWED_MODES:
        raise WorkflowRouterError(
            "mode must be plan_only, execute_read_only, implementation_prep, or apply_disposable_copy.",
            code="unsupported_mode",
            status=HTTPStatus.BAD_REQUEST,
        )
    if not isinstance(request.user_request, str) or not request.user_request.strip():
        raise WorkflowRouterError("user_request is required.", code="missing_user_request", status=HTTPStatus.BAD_REQUEST)
    if not Path(request.target_root).resolve().is_dir():
        raise WorkflowRouterError("target_root must be an existing directory.", code="target_root_not_found")
    if not isinstance(request.role_id, str) or not request.role_id.strip():
        raise WorkflowRouterError("role_id must be a non-empty string.", code="invalid_role_id")
    return {"budgets": validate_budgets(request.budgets)}


def model_route_observation(
    request: WorkflowRouterPlanRequest,
    workflow_registry: dict[str, dict[str, Any]],
    deterministic_workflow_id: str | None = None,
    deterministic_status_reason: str | None = None,
    *,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    if not request.role_base_url:
        return {"source": "model_router", "status": "skipped", "reason": "role_base_url_not_configured"}
    registry_view = [
        {
            "id": workflow_id,
            "description": workflow.get("description"),
            "controller_tool_ids": workflow.get("controller_tool_ids", []),
        }
        for workflow_id, workflow in sorted(workflow_registry.items())
        if workflow_id in ROUTABLE_WORKFLOWS
    ]
    prompt = {
        "task": "Select the best supported local development workflow for the user request.",
        "allowed_workflows": sorted(ROUTABLE_WORKFLOWS),
        "workflow_registry": registry_view,
        "user_request": request.user_request,
        "deterministic_controller_hint": {
            "selected_workflow": deterministic_workflow_id,
            "status_reason": deterministic_status_reason,
            "authority": "advisory_hint_only_controller_still_validates_output",
        },
        "rules": [
            "Return JSON only.",
            "Use null selected_workflow if none of the allowed workflows fit.",
            "Do not approve mutation or approval bypass.",
            "Do not select raw CodeGraphContext, MCP, or Cypher operations.",
            "For read-only 'find where behavior starts' prompts, select code_investigation.plan.",
            "For read-only 'find tests related to behavior/file' prompts, select code_investigation.plan because it returns related_tests and verification commands.",
            "For read-only 'recommend the smallest/safest test command' prompts, select code_investigation.plan because it returns evidence-backed verification commands.",
            "For read-only 'explain what this file/function does' prompts, select code_investigation.plan because it returns source evidence, related tests, and a code_explanation artifact.",
            "For read-only 'check whether behavior already exists' prompts, select code_investigation.plan because it returns bounded yes/no/unknown evidence.",
            "For read-only 'locate config setting/env var definition or usage' prompts, select code_investigation.plan because it returns configuration references and runtime-effect evidence.",
            "For read-only 'summarize pasted test failure' prompts, select code_investigation.plan because it returns a bounded failure summary and next inspection step.",
            "For read-only L2 failing-test diagnosis prompts, select code_investigation.plan because it returns a root-cause hypothesis, safe fix plan, and verification command without source mutation.",
            "For read-only L2 multi-file behavior investigation prompts, select code_investigation.plan because it returns beginning point, participating files, bounded usage evidence, related tests, risks, and verification.",
            "For read-only L2 dependency impact prompts, select code_investigation.plan because it returns impacted files, bounded callers/usages, related tests, risk level, and validation commands.",
            "For read-only L2 test-selection prompts, select code_investigation.plan because it returns validation command tiers, rationale, covered risks, confidence, and gaps.",
            "For callers, usages, imports, importers, references, or relationship lookups, select code_context.lookup.",
            "For draft-only 'fix a simple failing test' prompts, select execution_planning.plan because it can create a draft fix packet through implementation.workflow.",
            "For draft-only 'add or update a small unit test' prompts, select execution_planning.plan because it can create a draft packet through implementation.workflow.",
            "For draft-only small text or documentation edit prompts with exact file/anchor/new text, select execution_planning.plan because packet design is write-adjacent and must stay draft-only.",
            "For artifact-only skill-batch proposal requests that explicitly say not to register or append runtime skills, select skill_batch.propose.",
            "For broad single-path refactor prompts, select refactor.single_path only when the request asks to refactor or consolidate paths.",
        ],
        "output_shape": {
            "selected_workflow": "allowed workflow id or null",
            "confidence": "low|medium|high",
            "reason": "short reason",
            "approval_required_before": [],
        },
    }
    payload = {
        "model": request.model,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "messages": [
            {
                "role": "system",
                "content": "You are a deterministic workflow classifier. Output exactly one JSON object.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True, indent=2)},
        ],
    }
    try:
        body = post_json(f"{request.role_base_url.rstrip('/')}/chat/completions", payload)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise WorkflowRouterError("Model response did not contain choices.", code="invalid_model_route")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise WorkflowRouterError("Model response did not contain message.content.", code="invalid_model_route")
        parsed = extract_json_object(content)
    except Exception as exc:  # noqa: BLE001 - model routing must never bypass deterministic validation
        return {"source": "model_router", "status": "failed", "reason": bounded_string(exc, 500)}

    selected_workflow = parsed.get("selected_workflow")
    if selected_workflow is not None and selected_workflow not in ROUTABLE_WORKFLOWS:
        return {
            "source": "model_router",
            "status": "rejected",
            "reason": "unsupported_selected_workflow",
            "selected_workflow": selected_workflow,
        }
    confidence = parsed.get("confidence")
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    approval_required = parsed.get("approval_required_before")
    if not isinstance(approval_required, list) or not all(isinstance(item, str) for item in approval_required):
        approval_required = []
    return {
        "source": "model_router",
        "status": "accepted",
        "selected_workflow": selected_workflow,
        "confidence": confidence,
        "reason": bounded_string(parsed.get("reason", ""), 500),
        "approval_required_before": approval_required,
    }


def lower_request(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def contains_any(text: str, terms: set[str]) -> list[str]:
    return sorted(term for term in terms if term in text)


def is_ambiguous_request(text: str) -> bool:
    compact = text.strip().lower()
    stripped = lower_request(strip_filesystem_paths(text))
    stripped = re.sub(r"^(in|for)\s*,?\s*", "", stripped).strip(" ,.")
    stripped = re.sub(
        r"^(in|for)\s+(this repo|this repository|the repo|the repository)\s*,?\s*",
        "",
        stripped,
    ).strip(" ,.")
    for candidate in {compact, stripped}:
        if len(candidate.split()) <= 3 and candidate in {"fix it", "do it", "make it better", "continue", "help"}:
            return True
        if re.fullmatch(r"(fix|change|update|refactor|investigate)\s+(it|this|that)", candidate):
            return True
    return False


def is_skill_batch_proposal_request(text: str) -> bool:
    proposal_terms = (
        "propose a skill batch",
        "draft a skill batch",
        "create a skill batch proposal",
        "skill batch proposal",
        "propose new skills",
        "draft new skills",
    )
    must_not_register = (
        "do not register",
        "do not append",
        "do not add to runtime",
        "artifact only",
        "proposal only",
        "draft only",
    )
    explicit_skill_batch_action = any(term in text for term in ("propose", "draft", "create")) and "skill batch" in text
    return (any(term in text for term in proposal_terms) or explicit_skill_batch_action) and (
        "skill" in text and ("batch" in text or "proposal" in text)
    ) and any(term in text for term in must_not_register)


def is_l1_behavior_start_request(text: str) -> bool:
    if any(term in text for term in ("refactor", "single path", "one code path", "only one path")):
        return False
    start_terms = (
        "find where",
        "where does",
        "where is",
        "where the",
        "entry point",
        "entrypoint",
        "beginning point",
        "logic beginning",
        "first source point",
        "source point",
    )
    outcome_terms = (
        "begin",
        "begins",
        "start",
        "starts",
        "entry point",
        "entrypoint",
        "beginning point",
        "creates or populates",
        "creates",
        "populates",
    )
    return any(term in text for term in start_terms) and any(term in text for term in outcome_terms)


def is_l1_related_tests_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "add test")):
        return False
    related_test_terms = (
        "find tests related",
        "find related tests",
        "related tests",
        "tests related to",
        "tests for",
        "test files",
        "test command",
        "test commands",
        "matching terms",
        "covering tests",
        "tests covering",
    )
    return any(term in text for term in related_test_terms)


def is_l1_safe_test_command_request(text: str) -> bool:
    if any(term in text for term in ("run the test", "run tests", "execute tests", "fix failing", "fix test")):
        return False
    command_terms = (
        "smallest test command",
        "safe test command",
        "recommend test command",
        "recommend a test command",
        "recommend the test command",
        "which test command",
        "what test command",
        "test command for",
    )
    return any(term in text for term in command_terms)


def is_l1_explain_code_request(text: str) -> bool:
    if any(term in text for term in ("refactor", "fix failing", "fix this test", "fix test", "update test", "add test")):
        return False
    if is_l1_configuration_effect_summary_request(text):
        return False
    if is_l1_safe_test_command_request(text) or is_l1_callers_usages_request(text) or is_l2_test_selection_request(text):
        return False
    explain_terms = (
        "explain ",
        "explain what",
        "explain this function",
        "explain this file",
        "what does",
        "what do",
        "summarize what",
    )
    code_target_terms = (
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".rb",
        ".php",
        ".md",
        "function",
        "method",
        "class",
        "file",
        "module",
        "does",
    )
    return any(term in text for term in explain_terms) and any(term in text for term in code_target_terms)


def is_l1_behavior_exists_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    existence_terms = (
        "already exists",
        "already exist",
        "already have",
        "does the repo already have",
        "does this repo already have",
        "whether",
        "check if",
        "check whether",
        "does this exist",
        "does it exist",
        "is there",
    )
    outcome_terms = ("exists", "exist", "present", "implemented", "already")
    return any(term in text for term in existence_terms) and any(term in text for term in outcome_terms)


def is_l1_callers_usages_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    return any(
        term in text
        for term in (
            "callers",
            "caller",
            "usages",
            "usage",
            "uses of",
            "who uses",
            "find references",
            "references to",
        )
    )


def is_l1_configuration_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    config_terms = (
        "config",
        "configuration",
        "setting",
        "env var",
        "environment variable",
        "environment setting",
    )
    lookup_terms = ("defined", "used", "where", "locate", "runtime effect", "current value", "override")
    return any(term in text for term in config_terms) and any(term in text for term in lookup_terms)


def is_l1_endpoint_route_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    if is_l1_local_change_summary_request(text):
        return False
    if is_l1_cli_entrypoint_lookup_request(text):
        return False
    route_terms = (
        "endpoint",
        "route handler",
        "request handler",
        "message handler",
        "websocket handler",
        "handler for",
        "handler branch",
        "handles",
    )
    lookup_terms = ("find", "locate", "where", "which", "show", "follow")
    return any(term in text for term in route_terms) and any(term in text for term in lookup_terms)


def is_l1_message_source_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    message_terms = ("error message", "log message", "logged", "logger", "exception message", "comes from", "source of")
    lookup_terms = ("find", "locate", "where", "which", "source", "comes from")
    return any(term in text for term in message_terms) and any(term in text for term in lookup_terms)


def is_l1_module_summary_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    if is_l1_test_failure_summary_request(text):
        return False
    summary_terms = ("summarize module", "summarize this module", "summarize file", "module summary", "file summary")
    return any(term in text for term in summary_terms) or (
        "summarize " in text and bool(extract_request_paths(text, limit=1))
    )


def is_l1_data_model_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    model_terms = ("data model", "schema", "table schema", "database schema", "dataclass", "fields", "columns")
    lookup_terms = ("find", "locate", "where", "show", "summarize", "list")
    return any(term in text for term in model_terms) and any(term in text for term in lookup_terms)


def is_l1_dependency_import_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    dependency_terms = ("imports", "imported by", "dependencies", "depends on", "module dependencies", "what does")
    target_terms = ("import", "dependency", "dependencies", ".py", "module")
    return any(term in text for term in dependency_terms) and any(term in text for term in target_terms)


def is_l1_coverage_gap_summary_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    coverage_terms = ("coverage gap", "coverage gaps", "test coverage", "covered tests", "uncovered")
    target_terms = ("test", "tests", "source", "behavior", "verification")
    return any(term in text for term in coverage_terms) and any(term in text for term in target_terms)


def is_l1_documentation_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    doc_terms = ("documentation", "docs", "readme", "documented")
    lookup_terms = ("find", "locate", "where", "which", "show")
    return any(term in text for term in doc_terms) and any(term in text for term in lookup_terms)


def is_l1_auth_check_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    auth_terms = (
        "auth check",
        "auth checks",
        "authorization",
        "authentication",
        "permission guard",
        "permission guards",
        "access-control",
        "access control",
    )
    lookup_terms = ("find", "locate", "where", "which", "show", "return")
    return any(term in text for term in auth_terms) and any(term in text for term in lookup_terms)


def is_l1_state_mutation_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    state_terms = (
        "state mutation",
        "state mutation sites",
        "mutation sites",
        "mutates state",
        "in-memory state",
        "persistent records",
        "placed_order_id indexing",
        "cache",
        "caches",
    )
    lookup_terms = ("find", "locate", "where", "which", "show", "return")
    return any(term in text for term in state_terms) and any(term in text for term in lookup_terms)


def is_l1_external_integration_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    integration_terms = (
        "external integration",
        "integration points",
        "external api",
        "webhook",
        "sdk",
        "service integration",
        "coinbase order placement",
        "order placement client",
        "request boundaries",
    )
    lookup_terms = ("find", "locate", "where", "which", "show", "return")
    return any(term in text for term in integration_terms) and any(term in text for term in lookup_terms)


def is_l1_error_handling_path_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    error_terms = (
        "error handling path",
        "error handling",
        "order placement failures",
        "exception handlers",
        "fallback logic",
        "retry logic",
        "failure path",
    )
    lookup_terms = ("find", "locate", "where", "which", "show", "return")
    return any(term in text for term in error_terms) and any(term in text for term in lookup_terms)


def is_l1_cli_entrypoint_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    if is_l1_test_failure_summary_request(text):
        return False
    has_cli_word = re.search(r"\bcli\b", text) is not None
    behavior_beginning_terms = (
        "begin",
        "begins",
        "beginning point",
        "logic beginning",
        "first source point",
        "source point",
    )
    behavior_subject_terms = ("behavior", "lookup", "flow", "logic")
    if (
        not has_cli_word
        and any(term in text for term in behavior_beginning_terms)
        and any(term in text for term in behavior_subject_terms)
    ):
        return False
    entry_terms = ("script", "entrypoint", "entry point", "main.py", "__main__", "run command")
    lookup_terms = ("find", "locate", "where", "which", "show", "command")
    return (has_cli_word or any(term in text for term in entry_terms)) and any(term in text for term in lookup_terms)


def is_l1_configuration_effect_summary_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    if "defined or used" in text or "find where" in text:
        return False
    config_terms = ("config", "configuration", "setting", "env var", "environment variable", "coinbase_api_key")
    effect_terms = (
        "runtime effect of",
        "affect at runtime",
        "affects at runtime",
        "what does it affect",
        "explain",
        "used by",
        "does at runtime",
    )
    return any(term in text for term in config_terms) and any(term in text for term in effect_terms)


def is_l1_local_change_summary_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor")):
        return False
    return any(
        term in text
        for term in (
            "recent changes",
            "local changes",
            "git status",
            "changed files",
            "recent commits",
            "what changed",
        )
    )


def is_l1_test_failure_summary_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test")):
        return False
    failure_terms = (
        "pasted test failure",
        "test failure",
        "pytest failure",
        "failed ",
        "traceback",
        "assertionerror",
        "modulenotfounderror",
        "importerror",
    )
    summary_terms = ("summarize", "summary", "what failed", "likely cause", "next inspection", "next bounded")
    return any(term in text for term in failure_terms) and any(term in text for term in summary_terms)


def has_test_failure_context(text: str) -> bool:
    return any(
        term in text
        for term in (
            "test failure",
            "pytest failure",
            "failing test",
            "failed tests/",
            "failed test_",
            "failed ",
            "assertionerror",
            "modulenotfounderror",
            "importerror",
        )
    )


def is_l2_failing_test_investigation_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply")):
        return False
    investigation_terms = (
        "diagnose",
        "investigate",
        "root cause",
        "why did",
        "why does",
        "why is",
        "why failed",
        "what caused",
        "safe fix plan",
        "smallest safe fix",
        "proposed fix",
    )
    read_only_terms = ("do not edit", "do not mutate", "read only", "read-only", "no source changes")
    return (
        has_test_failure_context(text)
        and any(term in text for term in investigation_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_ci_log_triage_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate")):
        return False
    ci_terms = (
        "ci log",
        "failing ci",
        "github actions",
        "workflow run",
        "ci failure",
        "pipeline failure",
        "build log",
    )
    outcome_terms = (
        "first failing command",
        "likely cause",
        "next local command",
        "summarize",
        "summary",
    )
    return any(term in text for term in ci_terms) and any(term in text for term in outcome_terms)


def is_l2_table_read_write_lookup_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "refactor", "apply", "mutate")):
        return False
    table_terms = ("database table", "table", "db table")
    access_terms = (
        "read and written",
        "reads and writes",
        "definition, reads, and writes",
        "definition reads and writes",
        "definition sites, read sites, write sites",
        "definition sites read sites write sites",
        "read/write",
        "read write",
        "defined, read, and written",
        "defined read and written",
    )
    return any(term in text for term in table_terms) and any(term in text for term in access_terms)


def is_l2_runtime_reproduction_checklist_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    runtime_terms = ("runtime error", "stack trace", "traceback", "exception")
    repro_terms = (
        "minimal reproduction checklist",
        "reproduction checklist",
        "repro checklist",
        "minimal repro",
        "turn this stack trace",
        "reproduce",
    )
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return any(term in text for term in runtime_terms) and any(term in text for term in repro_terms) and any(
        term in text for term in read_only_terms
    )


def is_l2_user_facing_message_test_target_request(text: str) -> bool:
    if any(term in text for term in ("add", "create", "implement", "fix failing", "fix test", "update test", "apply", "mutate")):
        return False
    message_terms = ("error message", "log message", "exception message")
    user_terms = ("user-facing", "user facing", "shown to user", "visible to user")
    test_terms = ("where it should be tested", "where should it be tested", "tested", "test target", "related tests")
    return any(term in text for term in message_terms) and any(term in text for term in user_terms) and any(
        term in text for term in test_terms
    )


def is_l2_multi_file_behavior_investigation_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate")):
        return False
    if is_l2_request_flow_map_request(text):
        return False
    if any(term in text for term in ("dependency impact", "impact summary", "impact scan", "impacted files")):
        return False
    investigation_terms = (
        "investigate",
        "trace",
        "map",
        "summarize",
    )
    multi_file_terms = (
        "multi-file",
        "multi file",
        "across source files",
        "across files",
        "participating files",
        "call chain",
        "callers/usages",
        "callers and usages",
        "usage evidence",
        "flows across",
    )
    behavior_terms = ("behavior", "lookup", "flow", "entrypoint", "beginning point", "related tests", "verification")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in text for term in investigation_terms)
        and any(term in text for term in multi_file_terms)
        and any(term in text for term in behavior_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_dependency_impact_summary_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate")):
        return False
    if is_l2_change_surface_summary_request(text):
        return False
    impact_terms = (
        "dependency impact",
        "impact summary",
        "impact scan",
        "impacted files",
        "what is impacted",
        "what would be impacted",
        "if",
    )
    change_terms = ("behavior changes", "change", "changes", "changed", "proposed change")
    output_terms = ("risk", "risks", "validation", "verification", "related tests", "callers/usages", "callers and usages")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in text for term in impact_terms)
        and any(term in text for term in change_terms)
        and any(term in text for term in output_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_test_selection_request(text: str) -> bool:
    if any(term in text for term in ("run the test", "run tests", "execute tests", "fix failing", "fix test", "apply", "mutate")):
        return False
    selection_terms = (
        "test selection",
        "choose the smallest",
        "smallest, medium, and broad",
        "smallest medium and broad",
        "validation commands",
        "validation command tiers",
        "test command tiers",
    )
    rationale_terms = (
        "rationale",
        "why each command",
        "why that command",
        "why each command matters",
        "command matters",
        "risk it covers",
        "what risk remains",
        "gaps remain",
        "confidence",
    )
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in text for term in selection_terms)
        and any(term in text for term in rationale_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_runtime_error_diagnosis_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    if is_l2_runtime_reproduction_checklist_request(text):
        return True
    runtime_terms = ("runtime error", "stack trace", "traceback", "exception")
    diagnosis_terms = ("diagnose", "likely cause", "observed error", "next inspection", "why")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in text for term in runtime_terms)
        and any(term in text for term in diagnosis_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_request_flow_map_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    flow_terms = ("request flow", "data flow", "message flow", "map the request", "map request", "flow steps")
    output_terms = ("flow steps", "participating files", "risks", "gaps", "verification")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in text for term in flow_terms)
        and any(term in text for term in output_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_code_path_comparison_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    comparison_terms = ("compare two candidate", "compare the", "candidate code paths", "candidate paths", "compare code paths")
    path_terms = ("path", "code path", "lookup path", "index path")
    read_only_terms = ("read only", "read-only", "do not edit", "do not mutate", "no source changes")
    return (
        any(term in text for term in comparison_terms)
        and any(term in text for term in path_terms)
        and any(term in text for term in read_only_terms)
    )


def is_l2_change_surface_summary_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "update test", "apply", "mutate", "refactor")):
        return False
    surface_terms = (
        "minimal safe change surface",
        "change surface",
        "files that would need review",
        "files need review",
        "files needing review",
        "files to touch",
        "files not to touch",
    )
    stop_terms = ("stop before implementation", "before implementation", "read only", "read-only")
    return any(term in text for term in surface_terms) and any(term in text for term in stop_terms)


def is_l1_simple_failing_test_fix_request(text: str) -> bool:
    fix_terms = (
        "fix failing",
        "fix this failing test",
        "fix this test",
        "fix test",
        "simple failing test",
        "smallest fix",
        "propose the smallest fix",
    )
    failure_terms = ("failed ", "assertionerror", "pytest failure", "test failure", "traceback")
    return any(term in text for term in fix_terms) and any(term in text for term in failure_terms)


def is_d1_config_default_test_request(text: str) -> bool:
    if any(term in text for term in ("run tests", "find tests", "fix failing", "fix this test")):
        return False
    config_terms = ("config default", "configuration default", "default config", "defaults to")
    test_terms = ("draft", "small unit test", "small test", "unit test")
    return any(term in text for term in config_terms) and any(term in text for term in test_terms)


def is_d1_message_assertion_test_request(text: str) -> bool:
    if any(term in text for term in ("run tests", "find tests", "fix failing", "fix this test")):
        return False
    message_terms = ("error message", "log message", "message assertion", "asserting exact message", "assert exact message")
    test_terms = ("draft", "small unit test", "small test", "unit test")
    return any(term in text for term in message_terms) and any(term in text for term in test_terms)


def is_d1_test_assertion_update_request(text: str) -> bool:
    if any(term in text for term in ("run tests", "find tests", "fix failing", "fix this test")):
        return False
    assertion_terms = ("test assertion update", "update a test assertion", "update test assertion", "replace the assertion")
    draft_terms = ("draft", "draft only", "do not mutate", "do not edit")
    return any(term in text for term in assertion_terms) and any(term in text for term in draft_terms)


def is_l1_small_unit_test_request(text: str) -> bool:
    if any(term in text for term in ("fix failing", "fix this test", "fix test", "run tests", "find tests")):
        return False
    if (
        is_d1_config_default_test_request(text)
        or is_d1_message_assertion_test_request(text)
        or is_d1_test_assertion_update_request(text)
    ):
        return True
    test_terms = (
        "add a small unit test",
        "add small unit test",
        "add a unit test",
        "add unit test",
        "update a small unit test",
        "update unit test",
        "write a small unit test",
        "draft a small unit test",
        "add a small test",
        "add small test",
        "add test for",
        "add tests for",
    )
    return any(term in text for term in test_terms)


def is_l1_small_text_edit_request(text: str) -> bool:
    if any(term in text for term in ("add test", "update test", "fix failing", "fix this test", "fix test")):
        return False
    edit_terms = (
        "small documentation edit",
        "small text edit",
        "documentation edit",
        "doc edit",
        "edit documentation",
        "edit docs",
        "update documentation",
        "update docs",
        "add a line",
        "add this line",
        "append a line",
        "append this line",
    )
    action_terms = ("draft", "make", "update", "change", "add", "append", "edit")
    if any(term in text for term in edit_terms) and any(term in text for term in action_terms):
        return True
    return "unified diff" in text and (".md" in text or "docs/" in text) and any(term in text for term in action_terms)


def extract_request_paths(user_request: str, limit: int = 5) -> list[str]:
    paths: list[str] = []
    absolute_path_pattern = r"[A-Za-z]:[\\/]\S+|(?<![\w./-])/(?:mnt|home|tmp|var|opt|workspace|repo|repos|[A-Za-z0-9._-]+)(?:/\S+)+"
    query_source = re.sub(absolute_path_pattern, " ", user_request)
    path_pattern = re.compile(
        r"(?<![\w./\\-])((?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\."
        r"(?:py|pyi|js|jsx|ts|tsx|java|go|rs|cs|cpp|c|h|hpp|rb|php|md|rst|txt|json|yaml|yml|toml|ini))\b",
        re.IGNORECASE,
    )
    for match in path_pattern.finditer(query_source):
        candidate = match.group(1).replace("\\", "/").lstrip("./")
        if not candidate or candidate.startswith("/") or candidate.startswith("..") or "/../" in candidate:
            continue
        if candidate not in paths:
            paths.append(candidate)
        if len(paths) >= limit:
            return paths
    return paths


def first_text_edit_path(user_request: str) -> str | None:
    for path in extract_request_paths(user_request, limit=8):
        if Path(path).suffix.lower() in TEXT_EDIT_FILE_EXTENSIONS:
            return path
    bare_file_pattern = re.compile(
        r"(?<![\w./\\-])([A-Za-z0-9_.-]+\.(?:md|rst|txt|json|yaml|yml|toml|ini))\b",
        re.IGNORECASE,
    )
    for match in bare_file_pattern.finditer(user_request):
        candidate = match.group(1)
        if Path(candidate).suffix.lower() in TEXT_EDIT_FILE_EXTENSIONS:
            return candidate
    return None


def quoted_value_after(pattern: str, user_request: str) -> str | None:
    match = re.search(pattern + r"\s*`([^`]{1,1000})`", user_request, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(pattern + r"\s*\"([^\"]{1,1000})\"", user_request, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(pattern + r"\s*'([^']{1,1000})'", user_request, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def unquoted_note_text(user_request: str) -> str | None:
    match = re.search(
        r"\b(?:add|adds|append|appends)\s+(?:a\s+|the\s+)?note\s+saying\s+(?P<text>.+?)(?:\.\s+(?:do not|show|return)|$)",
        user_request,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    text = " ".join(match.group("text").strip().split())
    text = text.strip(" .")
    if not text:
        return None
    if text.startswith("- "):
        return text
    return f"- {text}."


def extract_small_text_edit_instruction(user_request: str) -> dict[str, Any] | None:
    target_path = first_text_edit_path(user_request)
    insert_text = quoted_value_after(
        r"\b(?:add|append)(?:\s+(?:this|the))?(?:\s+(?:line|bullet|text|note))?\s*(?::)?",
        user_request,
    ) or unquoted_note_text(user_request)
    anchor_text = quoted_value_after(r"\b(?:after|below)\s*", user_request)
    if not target_path or not insert_text:
        return None
    return {
        "kind": "insert_after" if anchor_text else "append_text",
        "path": target_path,
        "anchor_text": anchor_text,
        "insert_text": insert_text,
        "source": "natural_request",
    }


def first_unit_test_path(user_request: str) -> str | None:
    for path in extract_request_paths(user_request, limit=8):
        normalized = path.replace("\\", "/")
        if normalized.endswith(".py") and (normalized.startswith("tests/") or "/tests/" in normalized):
            return normalized
    return None


def first_source_path(user_request: str) -> str | None:
    for path in extract_request_paths(user_request, limit=8):
        normalized = path.replace("\\", "/")
        if normalized.endswith(".py") and not (normalized.startswith("tests/") or "/tests/" in normalized):
            return normalized
    return None


def first_upper_symbol(user_request: str) -> str | None:
    for match in re.finditer(r"\b[A-Z][A-Z0-9_]{3,}\b", user_request):
        return match.group(0)
    return None


def unquoted_expected_value(user_request: str) -> str | None:
    quoted = (
        quoted_value_after(r"\b(?:defaults?\s+to|expected\s+(?:value\s+)?(?:is|=)|equals?)\s*", user_request)
        or quoted_value_after(r"\b(?:to|as)\s*", user_request)
    )
    if quoted:
        return quoted
    match = re.search(
        r"\b(?:defaults?\s+to|expected\s+(?:value\s+)?(?:is|=)|equals?)\s+(?P<value>[A-Za-z0-9_.-]{1,80})",
        user_request,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group("value").strip().rstrip(".,;")
    return None


def python_literal_for_value(value: str) -> str:
    stripped = value.strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
        return stripped
    if stripped in {"True", "False", "None"}:
        return stripped
    if (stripped.startswith("\"") and stripped.endswith("\"")) or (stripped.startswith("'") and stripped.endswith("'")):
        return stripped
    return json.dumps(stripped, ensure_ascii=True)


def first_quoted_value(user_request: str, *, min_length: int = 1) -> str | None:
    for pattern in (r"`([^`]+)`", r'"([^"]+)"', r"'([^']+)'"):
        for match in re.finditer(pattern, user_request, flags=re.DOTALL):
            value = match.group(1).strip()
            if len(value) >= min_length:
                return value
    return None


def extract_small_unit_test_instruction(user_request: str) -> dict[str, Any] | None:
    text = lower_request(user_request)
    target_path = first_unit_test_path(user_request)
    if is_d1_config_default_test_request(text):
        symbol = first_upper_symbol(user_request)
        expected_value = unquoted_expected_value(user_request)
        source_path = first_source_path(user_request)
        if not symbol or not expected_value:
            return None
        return {
            "kind": "config_default_test",
            "path": target_path,
            "source_path": source_path,
            "symbol": symbol,
            "expected_value": expected_value,
            "source": "natural_request",
        }
    if is_d1_message_assertion_test_request(text):
        message_text = (
            quoted_value_after(r"\b(?:exact\s+)?(?:error\s+|log\s+)?message\s*(?:is|:)?", user_request)
            or first_quoted_value(user_request, min_length=8)
        )
        source_path = first_source_path(user_request)
        if not message_text:
            return None
        return {
            "kind": "message_assertion_test",
            "path": target_path,
            "source_path": source_path,
            "message_text": message_text,
            "source": "natural_request",
        }
    if is_d1_test_assertion_update_request(text):
        old_assertion = quoted_value_after(r"\b(?:replace|from)\s*(?:the\s+)?(?:assertion\s*)?", user_request)
        new_assertion = quoted_value_after(r"\b(?:with|to)\s*(?:the\s+)?(?:assertion\s*)?", user_request)
        if not target_path or not old_assertion or not new_assertion:
            return None
        return {
            "kind": "test_assertion_update",
            "path": target_path,
            "old_assertion": old_assertion,
            "new_assertion": new_assertion,
            "source": "natural_request",
        }
    behavior = behavior_from_request(user_request)
    if not behavior:
        return None
    return {
        "kind": "append_pytest_test",
        "path": target_path,
        "behavior": behavior,
        "source": "natural_request",
    }


def extract_simple_test_fix_instruction(user_request: str) -> dict[str, Any] | None:
    if not is_l1_simple_failing_test_fix_request(lower_request(user_request)):
        return None
    behavior = behavior_from_request(user_request)
    if not behavior:
        return None
    return {
        "kind": "replace_source_text",
        "behavior": behavior,
        "source": "natural_request",
    }


def extract_queries(user_request: str, limit: int = 5) -> list[str]:
    query_source = strip_filesystem_paths(user_request)
    queries: list[str] = []
    if is_l2_change_surface_summary_request(lower_request(user_request)):
        for value in change_subject_queries_from_request(user_request, limit=limit):
            append_unique(queries, value, limit=limit)
            if len(queries) >= limit:
                return queries
    for pattern in (r"`([^`]{3,120})`", r'"([^"]{3,120})"', r"'([^']{3,120})'"):
        for match in re.finditer(pattern, query_source):
            value = match.group(1).strip()
            append_unique(queries, value, limit=limit)
            if len(queries) >= limit:
                return queries
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", query_source):
        token = match.group(0)
        if "_" in token or any(char.isupper() for char in token[1:]):
            append_unique(queries, token, limit=limit)
            if len(queries) >= limit:
                return queries
    normalized = re.sub(r"[^a-zA-Z0-9_ ]+", " ", query_source)
    words = [word for word in normalized.split() if len(word) > 3]
    if words and not queries:
        queries.append(" ".join(words[:6]))
    return queries[:limit]


def behavior_from_request(user_request: str) -> str:
    queries = extract_queries(user_request, limit=1)
    if queries:
        return queries[0]
    return bounded_string(user_request.strip(), 160)


def relationship_queries_from_request(user_request: str, queries: list[str], limit: int = 25) -> list[dict[str, Any]]:
    text = lower_request(user_request)
    if not queries:
        return []
    symbol = queries[0]
    if any(term in text for term in ("callees", "callee")):
        return [{"kind": "callees", "symbol": symbol, "max_results": limit}]
    if any(term in text for term in ("imports", "importers")):
        return [{"kind": "imports", "symbol": symbol, "max_results": limit}]
    if is_l1_callers_usages_request(text):
        return [{"kind": "callers", "symbol": symbol, "max_results": limit}]
    return []


def is_task_decomposition_request(text: str) -> bool:
    explicit_terms = (
        "task decomposition",
        "decompose this task",
        "decompose the task",
        "break this task into",
        "break the task into",
        "break down this task",
        "break down the task",
        "work packages",
        "plan dag",
        "dependency graph",
        "multi-step task",
        "multi step task",
    )
    if contains_any(text, explicit_terms):
        return True
    if ("decompose" in text or "break down" in text) and any(
        term in text for term in ("dependencies", "approval gates", "verification strategy", "work package")
    ):
        return True
    return False


def workflow_kind_for_request(user_request: str) -> tuple[str | None, str, list[dict[str, Any]]]:
    text = lower_request(strip_filesystem_paths(user_request))
    evidence: list[dict[str, Any]] = []
    raw_terms = contains_any(text, RAW_CONTEXT_TERMS)
    if raw_terms:
        evidence.append({"source": "router_rule", "rule": "raw_context_block", "matched_terms": raw_terms})
        return None, "blocked_raw_context", evidence
    bypass_terms = contains_any(text, APPROVAL_BYPASS_TERMS)
    if bypass_terms:
        evidence.append({"source": "router_rule", "rule": "approval_bypass_block", "matched_terms": bypass_terms})
        return None, "blocked_approval_bypass", evidence
    non_dev_terms = contains_any(text, UNSUPPORTED_NON_DEV_TERMS)
    if non_dev_terms:
        evidence.append({"source": "router_rule", "rule": "unsupported_non_development_request", "matched_terms": non_dev_terms})
        return None, "unsupported", evidence
    if is_ambiguous_request(user_request):
        evidence.append({"source": "router_rule", "rule": "ambiguous_request"})
        return None, "ambiguous", evidence

    if is_skill_batch_proposal_request(text):
        evidence.append({"source": "router_rule", "rule": "skill_batch_proposal_terms"})
        return "skill_batch.propose", "ready", evidence
    if is_task_decomposition_request(text):
        evidence.append({"source": "router_rule", "rule": "task_decomposition_terms"})
        return "task.decompose", "ready", evidence
    if "feedback" in text or "too noisy" in text or "too slow" in text or "what was useful" in text:
        evidence.append({"source": "router_rule", "rule": "feedback_terms"})
        return "workflow_feedback.record", "ready", evidence
    if is_l1_simple_failing_test_fix_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_simple_failing_test_fix_terms"})
        return "execution_planning.plan", "ready", evidence
    if is_d1_config_default_test_request(text):
        evidence.append({"source": "router_rule", "rule": "d1_config_default_test_terms"})
        return "execution_planning.plan", "ready", evidence
    if is_d1_message_assertion_test_request(text):
        evidence.append({"source": "router_rule", "rule": "d1_message_assertion_test_terms"})
        return "execution_planning.plan", "ready", evidence
    if is_d1_test_assertion_update_request(text):
        evidence.append({"source": "router_rule", "rule": "d1_test_assertion_update_terms"})
        return "execution_planning.plan", "ready", evidence
    if is_l1_small_unit_test_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_small_unit_test_terms"})
        return "execution_planning.plan", "ready", evidence
    if is_l2_ci_log_triage_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_ci_log_triage_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_failing_test_investigation_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_failing_test_investigation_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_runtime_reproduction_checklist_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_runtime_reproduction_checklist_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_runtime_error_diagnosis_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_runtime_error_diagnosis_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_table_read_write_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_table_read_write_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_user_facing_message_test_target_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_user_facing_message_test_target_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_dependency_impact_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_dependency_impact_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_test_selection_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_test_selection_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_request_flow_map_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_request_flow_map_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_code_path_comparison_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_code_path_comparison_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_change_surface_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_change_surface_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l2_multi_file_behavior_investigation_request(text):
        evidence.append({"source": "router_rule", "rule": "l2_multi_file_behavior_investigation_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_endpoint_route_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_endpoint_route_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_message_source_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_message_source_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_module_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_module_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_data_model_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_data_model_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_dependency_import_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_dependency_import_lookup_terms"})
        return "code_context.lookup", "ready", evidence
    if is_l1_coverage_gap_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_coverage_gap_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_documentation_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_documentation_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_auth_check_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_auth_check_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_state_mutation_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_state_mutation_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_external_integration_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_external_integration_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_error_handling_path_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_error_handling_path_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_cli_entrypoint_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_cli_entrypoint_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_configuration_effect_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_configuration_effect_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_local_change_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_local_change_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_behavior_start_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_find_behavior_start_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_safe_test_command_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_safe_test_command_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_related_tests_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_find_related_tests_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_explain_code_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_explain_code_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_behavior_exists_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_behavior_exists_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_configuration_lookup_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_configuration_lookup_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_test_failure_summary_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_test_failure_summary_terms"})
        return "code_investigation.plan", "ready", evidence
    if is_l1_callers_usages_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_callers_usages_terms"})
        return "code_context.lookup", "ready", evidence
    if is_l1_small_text_edit_request(text):
        evidence.append({"source": "router_rule", "rule": "l1_small_text_edit_terms"})
        return "execution_planning.plan", "ready", evidence
    if (
        "single path" in text
        or "one path" in text
        or "one code path" in text
        or "only one path" in text
        or ("refactor" in text and ("path" in text or "duplicate" in text or "consolidate" in text))
    ):
        evidence.append({"source": "router_rule", "rule": "single_path_refactor_terms"})
        return "refactor.single_path", "ready", evidence
    if any(
        term in text
        for term in (
            "execution plan",
            "implementation plan",
            "implementation prep",
            "implementation-prep",
            "packet candidate",
            "packet design",
            "packet objective",
            "narrowed edit objective",
            "narrowed objective",
            "behavior delta",
            "implementation packet",
            "prepare implementation",
        )
    ):
        evidence.append({"source": "router_rule", "rule": "execution_planning_terms"})
        return "execution_planning.plan", "ready", evidence
    if any(term in text for term in ("callers", "callees", "imports", "importers", "who uses", "find references", "lookup context")):
        evidence.append({"source": "router_rule", "rule": "code_context_terms"})
        return "code_context.lookup", "ready", evidence
    if any(term in text for term in ("investigate", "trace", "beginning point", "entry point", "root cause", "where does", "why does")):
        evidence.append({"source": "router_rule", "rule": "investigation_terms"})
        return "code_investigation.plan", "ready", evidence
    if "disposable copy" in text and ("apply" in text or "mutation" in text or "packet operation" in text):
        evidence.append({"source": "router_rule", "rule": "disposable_apply_terms"})
        return "execution_planning.plan", "ready", evidence

    evidence.append({"source": "router_rule", "rule": "no_supported_workflow_match"})
    return None, "unsupported", evidence


def ensure_supplemental_route_evidence(
    *,
    user_request: str,
    workflow_id: str | None,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if workflow_id != "code_investigation.plan":
        return evidence
    if any(item.get("rule") == "l1_endpoint_route_lookup_terms" for item in evidence):
        return evidence
    text = lower_request(user_request)
    handler_lookup = (
        is_l1_endpoint_route_lookup_request(text)
        or any(term in text for term in ("websocket handler", "message handler", "handler for"))
        and any(term in text for term in ("find", "locate", "where", "which", "show"))
    )
    if handler_lookup:
        return evidence + [{"source": "router_rule", "rule": "l1_endpoint_route_lookup_terms", "supplemental": True}]
    return evidence


def skills_for_workflow(
    workflow_id: str,
    skill_registry: dict[str, dict[str, Any]],
    *,
    user_request: str,
    limit: int,
) -> list[str]:
    return select_skills_for_workflow(skill_registry, workflow_id, query_text=user_request, limit=limit)


def skill_can_run_workflow(skill_registry: dict[str, dict[str, Any]], skill_id: str, workflow_id: str) -> bool:
    skill = skill_registry.get(skill_id)
    if not isinstance(skill, dict) or skill.get("eval_status") == "deprecated":
        return False
    workflows = skill.get("workflows")
    return isinstance(workflows, list) and workflow_id in workflows


def apply_router_rule_skill_overrides(
    selected_skills: list[str],
    *,
    workflow_id: str,
    skill_registry: dict[str, dict[str, Any]],
    route_evidence: list[dict[str, Any]],
    limit: int,
) -> list[str]:
    if workflow_id != "code_investigation.plan":
        return selected_skills[:limit]
    override_ids: list[str] = []
    for item in route_evidence:
        rule = item.get("rule") if isinstance(item, dict) else None
        skill_id = ROUTER_RULE_SKILL_OVERRIDES.get(rule)
        if isinstance(skill_id, str) and skill_can_run_workflow(skill_registry, skill_id, workflow_id):
            append_unique(override_ids, skill_id)
    if not override_ids:
        return selected_skills[:limit]

    core = [skill_id for skill_id in selected_skills if skill_id in CORE_INVESTIGATION_SKILLS]
    remainder = [
        skill_id
        for skill_id in selected_skills
        if skill_id not in CORE_INVESTIGATION_SKILLS and skill_id not in override_ids
    ]
    adjusted: list[str] = []
    for skill_id in [*core, *override_ids, *remainder]:
        append_unique(adjusted, skill_id, limit=limit)
    return adjusted[:limit]


def tools_for_workflow(workflow_id: str, workflow_registry: dict[str, dict[str, Any]], limit: int) -> list[str]:
    workflow = workflow_registry.get(workflow_id, {})
    tool_ids = workflow.get("controller_tool_ids", [])
    if not isinstance(tool_ids, list):
        return []
    return [tool_id for tool_id in tool_ids if isinstance(tool_id, str)][:limit]


def request_preview(
    workflow_id: str,
    request: WorkflowRouterPlanRequest,
    selected_tools: list[str],
    selected_context_sources: list[str] | None = None,
) -> dict[str, Any]:
    target_root = str(Path(request.target_root).resolve())
    queries = extract_queries(request.user_request)
    paths = extract_request_paths(request.user_request)
    behavior = behavior_from_request(request.user_request)
    context_sources = selected_context_sources or []
    base: dict[str, Any] = {
        "workflow": workflow_id,
        "schema_version": SCHEMA_VERSION,
        "target_root": target_root,
        "context_sources": context_sources,
    }
    if workflow_id == "code_context.lookup":
        return {
            **base,
            "query": queries[0] if queries else request.user_request.strip(),
            "paths": paths,
            "allowed_context_tools": selected_tools,
            "relationship_queries": relationship_queries_from_request(request.user_request, queries),
        }
    if workflow_id == "code_investigation.plan":
        return {
            **base,
            "user_request": request.user_request.strip(),
            "behavior": behavior,
            "queries": queries,
            "paths": paths,
            "allowed_context_tools": selected_tools,
            "include_tests": True,
        }
    if workflow_id == "refactor.single_path":
        return {
            **base,
            "user_request": request.user_request.strip(),
            "behavior": behavior,
            "mode": "investigation_only",
            "entrypoint_hints": [],
            "queries": queries,
            "paths": paths,
            "allowed_context_tools": selected_tools,
            "approval": {"status": "not_requested", "apply_allowed": False},
        }
    if workflow_id == "execution_planning.plan":
        preview = {
            **base,
            "user_request": request.user_request.strip(),
            "mode": "dry_run" if request.mode == "implementation_prep" else "investigation_only",
            "approval": {"status": "not_requested", "apply_allowed": False},
            "context": {"allowed_context_tools": selected_tools, "context_sources": context_sources},
        }
        if request.mode == "implementation_prep":
            preview["approval"] = request.approval
            preview["packet_operations"] = request.packet_operations
        return preview
    if workflow_id == "workflow_feedback.record":
        return {
            **base,
            "target_workflow": None,
            "target_run_id": None,
            "feedback": {},
        }
    if workflow_id == "skill_batch.propose":
        return {
            "workflow": workflow_id,
            "schema_version": SCHEMA_VERSION,
            "user_request": request.user_request.strip(),
            "requested_batch_id": None,
            "metadata": {"source": "workflow_router.plan", "target_root": target_root},
        }
    if workflow_id == "task.decompose":
        return {
            **base,
            "user_request": request.user_request.strip(),
            "metadata": {"source": "workflow_router.plan"},
        }
    return base


def approval_required_before(workflow_id: str) -> list[str]:
    if workflow_id == "workflow_feedback.record":
        return []
    if workflow_id == "skill_batch.propose":
        return ["runtime_registry_append", "skill_body_install"]
    if workflow_id in READ_ONLY_WORKFLOWS:
        return ["implementation_prep", "repository_mutation"]
    if workflow_id == "execution_planning.plan":
        return ["implementation_packet_design", "repository_mutation"]
    return ["repository_mutation"]


def next_action_for(workflow_id: str) -> str:
    if workflow_id == "skill_batch.propose":
        return "execute_read_only"
    if workflow_id in READ_ONLY_WORKFLOWS:
        return "execute_read_only"
    if workflow_id == "execution_planning.plan":
        return "request_approval"
    if workflow_id == "workflow_feedback.record":
        return "ask_blocking_question"
    return "none"


def route_has_rule(route_evidence: list[dict[str, Any]], rule: str) -> bool:
    return any(item.get("rule") == rule for item in route_evidence if isinstance(item, dict))


def request_matches_advanced_refactor_pilot_scope(user_request: str) -> tuple[bool, str]:
    text = lower_request(user_request)
    broad_terms = (
        "whole subsystem",
        "entire subsystem",
        "entire codebase",
        "whole codebase",
        "repo-wide",
        "repository-wide",
        "all functions",
        "all code paths",
        "all code",
        "everything",
    )
    if any(term in text for term in broad_terms):
        return False, "advanced_refactor_pilot_scope_too_broad"
    investigation_first = any(
        term in text
        for term in (
            "start from the logic beginning point",
            "logic beginning point",
            "investigate first",
            "read only",
            "investigation first",
        )
    )
    approval_gated = "approval" in text or "wait for approval" in text
    single_behavior = bool(re.search(r"\b[a-z0-9_]*_[a-z0-9_]+[a-z0-9_]*\b", text)) or any(
        term in text for term in ("named function", "named behavior", "one named", "single named")
    )
    if not investigation_first:
        return False, "advanced_refactor_pilot_requires_investigation_first"
    if not approval_gated:
        return False, "advanced_refactor_pilot_requires_approval_gate"
    if not single_behavior:
        return False, "advanced_refactor_pilot_requires_single_named_behavior"
    return True, "advanced_refactor_pilot_scope_admitted"


def advanced_refactor_readiness_blocker(
    *,
    config_root: Path,
    workflow_id: str,
    route_evidence: list[dict[str, Any]],
    user_request: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if workflow_id != "refactor.single_path" or not route_has_rule(route_evidence, "single_path_refactor_terms"):
        return None, None
    gate_decision = advanced_refactor_gate_decision(config_root)
    if gate_decision.get("status") == "ready":
        pilot_admitted, pilot_reason = request_matches_advanced_refactor_pilot_scope(user_request)
        gate_decision["pilot_scope_reason"] = pilot_reason
        if not pilot_admitted:
            return {
                "reason": "advanced_refactor_pilot_scope_not_admitted",
                "message": (
                    "Phase 105 only admits narrow investigation-first advanced-refactor pilots with explicit "
                    "approval gating and a single named behavior or function."
                ),
                "readiness_report_path": gate_decision.get("report_path"),
                "readiness_status": gate_decision.get("readiness_status"),
                "pilot_scope_reason": pilot_reason,
            }, gate_decision
        return None, gate_decision
    return {
        "reason": "advanced_refactor_readiness_not_met",
        "message": gate_decision.get(
            "message",
            "Advanced refactor remains blocked until the Phase 105 readiness gate passes.",
        ),
        "readiness_report_path": gate_decision.get("report_path"),
        "readiness_status": gate_decision.get("readiness_status"),
    }, gate_decision


def downstream_role_id_for(workflow_id: str) -> str:
    if workflow_id in {
        "code_context.lookup",
        "code_investigation.plan",
        "refactor.single_path",
        "skill_batch.propose",
        "task.decompose",
    }:
        return "architect/default"
    return DEFAULT_ROLE_ID


def resolve_downstream_tool_policy(
    *,
    config_root: Path,
    workflow_id: str,
    request_context: dict[str, Any],
) -> dict[str, Any]:
    role_id = downstream_role_id_for(workflow_id)
    try:
        policy = resolve_controller_tool_policy(config_root, workflow_id, role_id, request_context, [])
    except ControllerToolPolicyError as exc:
        raise WorkflowRouterError(
            f"Downstream tool policy denied for {workflow_id}: {exc}",
            code="downstream_tool_policy_denied",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc
    return policy.audit_record()


def invoke_downstream_read_only(
    request: WorkflowRouterPlanRequest,
    decision: dict[str, Any],
    run_dir: Path,
) -> tuple[InvocationResult, dict[str, Any]]:
    workflow_id = decision.get("selected_workflow")
    if workflow_id not in READ_ONLY_WORKFLOWS:
        raise WorkflowRouterError(
            "execute_read_only supports only controller-owned read-only or artifact-only workflows.",
            code="read_only_workflow_required",
            status=HTTPStatus.BAD_REQUEST,
        )
    preview = decision.get("controller_request_preview")
    if not isinstance(preview, dict):
        raise WorkflowRouterError("controller_request_preview is required before read-only execution.")
    config_root = Path(request.config_root).resolve()
    target_root = Path(request.target_root).resolve()
    downstream_output_root = run_dir

    if workflow_id == "code_context.lookup":
        tool_policy = resolve_downstream_tool_policy(config_root=config_root, workflow_id=workflow_id, request_context={})
        downstream_request = CodeContextLookupRequest.from_payload(
            preview,
            config_root=config_root,
            target_root=target_root,
            output_root=downstream_output_root,
        )
        result = invoke_code_context_lookup(downstream_request)
        return result, tool_policy

    if workflow_id == "code_investigation.plan":
        tool_policy = resolve_downstream_tool_policy(config_root=config_root, workflow_id=workflow_id, request_context={})
        downstream_request = CodeInvestigationRequest.from_payload(
            preview,
            config_root=config_root,
            target_root=target_root,
            output_root=downstream_output_root,
        )
        result = invoke_code_investigation(downstream_request)
        return result, tool_policy

    if workflow_id == "skill_batch.propose":
        tool_policy = resolve_downstream_tool_policy(config_root=config_root, workflow_id=workflow_id, request_context={})
        downstream_request = SkillBatchProposalRequest.from_payload(
            preview,
            config_root=config_root,
            output_root=downstream_output_root,
        )
        result = invoke_skill_batch_proposal(downstream_request)
        return result, tool_policy

    if workflow_id == "task.decompose":
        tool_policy = resolve_downstream_tool_policy(config_root=config_root, workflow_id=workflow_id, request_context={})
        downstream_request = TaskDecompositionRequest.from_payload(
            preview,
            config_root=config_root,
            target_root=target_root,
            output_root=downstream_output_root,
        )
        result = invoke_task_decomposition(downstream_request)
        return result, tool_policy

    tool_policy = resolve_downstream_tool_policy(
        config_root=config_root,
        workflow_id=workflow_id,
        request_context={"mode": "investigation_only"},
    )
    downstream_request = RefactorSinglePathRequest.from_payload(
        preview,
        config_root=config_root,
        target_root=target_root,
        output_root=downstream_output_root,
        role_base_url=request.role_base_url,
    )
    result = invoke_refactor_single_path(downstream_request)
    return result, tool_policy


def implementation_prep_blockers(request: WorkflowRouterPlanRequest) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if not isinstance(request.approval, dict):
        blockers.append({"reason": "missing_packet_design_approval", "message": "approval must be a JSON object."})
        return blockers
    if request.approval.get("status") != "approved_for_packet_design":
        blockers.append(
            {
                "reason": "missing_packet_design_approval",
                "message": "implementation_prep requires approval.status=approved_for_packet_design.",
            }
        )
    if request.approval.get("apply_allowed") is True:
        blockers.append(
            {
                "reason": "apply_mode_not_supported",
                "message": "workflow_router.plan implementation_prep never allows apply mode.",
            }
        )
    if not isinstance(request.packet_operations, list) or not all(
        isinstance(item, dict) for item in request.packet_operations
    ):
        blockers.append({"reason": "invalid_packet_operations", "message": "packet_operations must be a list of objects."})
    elif not request.packet_operations:
        blockers.append(
            {
                "reason": "missing_packet_operations",
                "message": "implementation_prep requires exact packet_operations in this controller version.",
            }
        )
    if not isinstance(request.context, dict):
        blockers.append({"reason": "invalid_context", "message": "context must be a JSON object when provided."})
    if not isinstance(request.feedback, dict):
        blockers.append({"reason": "invalid_feedback", "message": "feedback must be a JSON object when provided."})
    if not isinstance(request.execution_budgets, dict):
        blockers.append({"reason": "invalid_execution_budgets", "message": "execution_budgets must be a JSON object."})
    return blockers


def small_text_edit_instruction_from_context(request: WorkflowRouterPlanRequest) -> dict[str, Any] | None:
    bounded_context = request.context.get("bounded_context") if isinstance(request.context, dict) else None
    if isinstance(bounded_context, list):
        for item in bounded_context:
            if not isinstance(item, dict):
                continue
            instruction = item.get("small_text_edit")
            if isinstance(instruction, dict):
                return instruction
    return extract_small_text_edit_instruction(request.user_request)


def path_under_root(root: Path, rel_path: str) -> Path | None:
    if not rel_path or Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
        return None
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def line_for_anchor(text: str, anchor_text: str) -> str | None:
    anchor = anchor_text.strip()
    if not anchor:
        return None
    containing_matches: list[str] = []
    for line in text.splitlines():
        if line.strip() == anchor:
            return line
        if anchor in line:
            containing_matches.append(line)
    if len(containing_matches) == 1:
        return containing_matches[0]
    return None


def small_text_edit_packet_operations(
    request: WorkflowRouterPlanRequest,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    instruction = small_text_edit_instruction_from_context(request)
    if instruction is None:
        return [], None
    target_root = Path(request.target_root).resolve()
    rel_path = instruction.get("path")
    kind = instruction.get("kind")
    anchor_text = instruction.get("anchor_text")
    insert_text = instruction.get("insert_text")
    blockers: list[dict[str, Any]] = []
    safety_checks: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    artifact: dict[str, Any] = {
        "kind": "small_text_edit_proposal",
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "instruction": instruction,
        "packet_operations": operations,
        "safety_checks": safety_checks,
        "blockers": blockers,
        "verification_commands": [],
    }
    if not isinstance(rel_path, str) or not rel_path:
        blockers.append({"reason": "missing_target_path", "message": "Small text edits require a repo-relative target file."})
    elif Path(rel_path).suffix.lower() not in TEXT_EDIT_FILE_EXTENSIONS:
        blockers.append({"reason": "unsupported_text_edit_file", "path": rel_path})
    if not isinstance(insert_text, str) or not insert_text.strip():
        blockers.append({"reason": "missing_insert_text", "message": "Small text edits require exact text to add."})
    if kind != "append_text" and (not isinstance(anchor_text, str) or not anchor_text.strip()):
        blockers.append({"reason": "missing_anchor_text", "message": "Small text edits require an exact anchor after/below which text is inserted."})
    target_path = path_under_root(target_root, rel_path) if isinstance(rel_path, str) else None
    if target_path is None:
        blockers.append({"reason": "target_path_outside_root", "path": rel_path})
    elif not target_path.exists() or not target_path.is_file():
        blockers.append({"reason": "missing_target_file", "path": rel_path})
    elif target_path.stat().st_size > SMALL_TEXT_EDIT_MAX_FILE_BYTES:
        blockers.append({"reason": "target_file_too_large", "path": rel_path})

    if not blockers and target_path is not None:
        text = target_path.read_text(encoding="utf-8", errors="replace")
        assert isinstance(insert_text, str)
        insertion = insert_text.strip()
        if insertion in text:
            blockers.append({"reason": "insert_text_already_present", "path": rel_path})
        if kind == "append_text" and not blockers:
            safety_checks.extend(
                [
                    {"check": "target_path_under_root", "status": "passed", "path": rel_path},
                    {"check": "text_file_extension", "status": "passed", "path": rel_path},
                    {"check": "insert_text_absent", "status": "passed", "path": rel_path},
                    {"check": "draft_only", "status": "passed", "apply_allowed": False},
                ]
            )
            prefix = "" if text.endswith("\n") else "\n"
            operations.append(
                {
                    "kind": "append_text",
                    "path": rel_path,
                    "content": prefix + insertion + "\n",
                }
            )
        else:
            assert isinstance(anchor_text, str)
            anchor_line = line_for_anchor(text, anchor_text)
            if anchor_line is None:
                blockers.append({"reason": "anchor_not_found_once", "path": rel_path, "anchor_text": anchor_text})
            elif text.count(anchor_line) != 1:
                blockers.append(
                    {
                        "reason": "anchor_line_not_unique",
                        "path": rel_path,
                        "anchor_text": anchor_text,
                        "count": text.count(anchor_line),
                    }
                )
            else:
                safety_checks.extend(
                    [
                        {"check": "target_path_under_root", "status": "passed", "path": rel_path},
                        {"check": "text_file_extension", "status": "passed", "path": rel_path},
                        {"check": "anchor_line_unique", "status": "passed", "path": rel_path},
                        {"check": "insert_text_absent", "status": "passed", "path": rel_path},
                        {"check": "draft_only", "status": "passed", "apply_allowed": False},
                    ]
                )
                operations.append(
                    {
                        "kind": "replace_text",
                        "path": rel_path,
                        "old": anchor_line,
                        "new": anchor_line + "\n" + insertion,
                    }
                )
        if operations:
            artifact["verification_commands"] = [
                {
                    "command": ["git", "diff", "--", rel_path],
                    "reason": "Review the exact draft text delta for the target file.",
                    "source_refs": [{"path": rel_path}],
                }
            ]
    artifact["status"] = "ready" if operations else "blocked"
    artifact["packet_operations"] = operations
    write_json(run_dir / "small-text-edit-proposal.json", artifact)
    return operations, artifact


def small_unit_test_instruction_from_context(request: WorkflowRouterPlanRequest) -> dict[str, Any] | None:
    bounded_context = request.context.get("bounded_context") if isinstance(request.context, dict) else None
    if isinstance(bounded_context, list):
        for item in bounded_context:
            if not isinstance(item, dict):
                continue
            instruction = item.get("small_unit_test")
            if isinstance(instruction, dict):
                return instruction
    return extract_small_unit_test_instruction(request.user_request)


def unit_test_query_terms(request: WorkflowRouterPlanRequest, instruction: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in [instruction.get("behavior"), *extract_queries(request.user_request, limit=8)]:
        if not isinstance(value, str):
            continue
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", value):
            normalized = token.lower()
            if normalized not in terms and normalized not in {"draft", "only", "small", "unit", "test", "tests"}:
                terms.append(normalized)
    return terms[:8]


def candidate_unit_test_files(target_root: Path) -> list[Path]:
    tests_root = target_root / "tests"
    if not tests_root.exists() or not tests_root.is_dir():
        return []
    candidates: list[Path] = []
    for pattern in ("test_*.py", "*_test.py"):
        candidates.extend(path for path in tests_root.rglob(pattern) if path.is_file())
    return sorted(set(candidates))


def select_unit_test_file(target_root: Path, instruction: dict[str, Any], terms: list[str]) -> tuple[str | None, dict[str, Any]]:
    explicit_path = instruction.get("path")
    if isinstance(explicit_path, str) and explicit_path:
        target_path = path_under_root(target_root, explicit_path)
        return explicit_path, {
            "selection": "explicit_path",
            "path": explicit_path,
            "exists": bool(target_path and target_path.exists()),
            "matched_terms": [],
            "score": None,
        }
    best: tuple[int, str, list[str]] | None = None
    for path in candidate_unit_test_files(target_root):
        try:
            rel_path = path.relative_to(target_root).as_posix()
        except ValueError:
            continue
        if path.stat().st_size > SMALL_UNIT_TEST_MAX_FILE_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        name = rel_path.lower()
        matched = [term for term in terms if term in text or term in name]
        score = len(matched) * 10
        if "order_id" in name:
            score += 2
        if "unit" in rel_path.split("/"):
            score += 1
        candidate = (score, rel_path, matched)
        if score > 0 and (best is None or candidate > best):
            best = candidate
    if best is None:
        return None, {"selection": "search", "path": None, "matched_terms": [], "score": 0}
    return best[1], {"selection": "search", "path": best[1], "matched_terms": best[2], "score": best[0]}


def generated_sync_exchange_missing_id_test() -> tuple[str, str]:
    test_name = "test_sync_exchange_order_id_sets_missing_audit_id_and_anchor_state"
    content = (
        "\n\n"
        "def test_sync_exchange_order_id_sets_missing_audit_id_and_anchor_state():\n"
        "    \"\"\"Missing audit exchange_order_id is backfilled on matching reveal event.\"\"\"\n"
        "    manager = StealthOrderManager(db_client=None)\n"
        "\n"
        "    client_order_id = \"aa0e8400-e29b-41d4-a716-446655440000\"\n"
        "    exchange_order_id = \"exchange-new-003\"\n"
        "    order = {\n"
        "        \"stealth_order_id\": client_order_id,\n"
        "        \"revealed_orders\": [{\"placed_order_id\": client_order_id}],\n"
        "        \"anchor_repricing_state_json\": {\"active_placement_client_order_id\": client_order_id},\n"
        "    }\n"
        "    manager.in_memory_orders[client_order_id] = order\n"
        "    manager._placed_order_index[client_order_id] = order\n"
        "\n"
        "    updated = manager.sync_exchange_order_id_for_placed_order(\n"
        "        placed_order_id=client_order_id,\n"
        "        exchange_order_id=exchange_order_id,\n"
        "    )\n"
        "\n"
        "    assert updated is True\n"
        "    assert order[\"revealed_orders\"][0][\"exchange_order_id\"] == exchange_order_id\n"
        "    assert order[\"anchor_repricing_state_json\"][\"active_exchange_order_id\"] == exchange_order_id\n"
    )
    return test_name, content


def generated_config_default_test(instruction: dict[str, Any]) -> tuple[str, str]:
    symbol = str(instruction.get("symbol") or "CONFIG_DEFAULT")
    expected_value = python_literal_for_value(str(instruction.get("expected_value") or ""))
    test_name = f"test_{symbol.lower()}_config_default"
    import_path = str(instruction.get("source_path") or "").replace("/", ".")
    if import_path.endswith(".py"):
        import_path = import_path[:-3]
    if not import_path:
        import_path = "configuration"
    content = (
        "\n\n"
        f"def {test_name}():\n"
        f"    from {import_path} import {symbol}\n"
        "\n"
        f"    assert {symbol} == {expected_value}\n"
    )
    return test_name, content


def generated_message_assertion_test(instruction: dict[str, Any]) -> tuple[str, str]:
    message_text = str(instruction.get("message_text") or "")
    test_name = "test_orderbook_read_only_error_message_names_blocked_operation"
    content = (
        "\n\n"
        "def test_orderbook_read_only_error_message_names_blocked_operation():\n"
        f"    expected_message = {json.dumps(message_text, ensure_ascii=True)}\n"
        "    ob = OrderBook(read_only=True)\n"
        "\n"
        "    with pytest.raises(OrderBookReadOnlyError) as exc_info:\n"
        "        ob.upsert_order(\"client-order\", {})\n"
        "\n"
        "    assert expected_message in str(exc_info.value)\n"
    )
    return test_name, content


def assignment_line_found(text: str, symbol: str, expected_value: str) -> bool:
    literal = python_literal_for_value(expected_value)
    pattern = re.compile(
        rf"^\s*{re.escape(symbol)}\s*=\s*{re.escape(literal)}(?:\s*(?:#.*)?)?$",
        flags=re.MULTILINE,
    )
    return bool(pattern.search(text))


def source_file_check(
    *,
    target_root: Path,
    rel_path: str | None,
    blockers: list[dict[str, Any]],
    max_bytes: int = SMALL_UNIT_TEST_MAX_FILE_BYTES,
) -> Path | None:
    if not isinstance(rel_path, str) or not rel_path.strip():
        blockers.append({"reason": "missing_source_path", "message": "This draft requires a repo-relative source file."})
        return None
    source_path = path_under_root(target_root, rel_path)
    if source_path is None:
        blockers.append({"reason": "source_path_outside_root", "path": rel_path})
        return None
    if not source_path.exists() or not source_path.is_file():
        blockers.append({"reason": "missing_source_file", "path": rel_path})
        return None
    if source_path.stat().st_size > max_bytes:
        blockers.append({"reason": "source_file_too_large", "path": rel_path})
        return None
    return source_path


def validate_small_unit_test_target(
    *,
    target_root: Path,
    rel_path: str | None,
    blockers: list[dict[str, Any]],
) -> Path | None:
    if not rel_path:
        blockers.append({"reason": "missing_test_file", "message": "No existing related pytest file was found."})
        return None
    target_path = path_under_root(target_root, rel_path)
    if target_path is None:
        blockers.append({"reason": "target_path_outside_root", "path": rel_path})
        return None
    if not target_path.exists() or not target_path.is_file():
        blockers.append({"reason": "missing_target_file", "path": rel_path})
        return None
    if target_path.suffix.lower() != ".py" or "tests" not in target_path.relative_to(target_root).parts:
        blockers.append({"reason": "target_not_pytest_file", "path": rel_path})
        return None
    if target_path.stat().st_size > SMALL_UNIT_TEST_MAX_FILE_BYTES:
        blockers.append({"reason": "target_file_too_large", "path": rel_path})
        return None
    return target_path


def append_small_unit_test_operation(
    *,
    rel_path: str,
    target_path: Path,
    test_name: str,
    test_content: str,
    safety_checks: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    required_text: str | None = None,
) -> None:
    text = target_path.read_text(encoding="utf-8", errors="replace")
    if test_name in text:
        blockers.append({"reason": "test_already_present", "path": rel_path, "test_name": test_name})
        return
    if required_text is not None and required_text not in text:
        blockers.append(
            {
                "reason": "missing_required_test_context",
                "path": rel_path,
                "required_text": required_text,
            }
        )
        return
    safety_checks.extend(
        [
            {"check": "target_path_under_root", "status": "passed", "path": rel_path},
            {"check": "pytest_file", "status": "passed", "path": rel_path},
            {"check": "existing_related_test_file", "status": "passed", "path": rel_path},
            {"check": "test_name_absent", "status": "passed", "test_name": test_name},
            {"check": "draft_only", "status": "passed", "apply_allowed": False},
        ]
    )
    operations.append({"kind": "append_text", "path": rel_path, "content": test_content})


def small_unit_test_packet_operations(
    request: WorkflowRouterPlanRequest,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    instruction = small_unit_test_instruction_from_context(request)
    if instruction is None:
        return [], None
    target_root = Path(request.target_root).resolve()
    blockers: list[dict[str, Any]] = []
    safety_checks: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    terms = unit_test_query_terms(request, instruction)
    rel_path, selection = select_unit_test_file(target_root, instruction, terms)
    subkind = instruction.get("kind") if isinstance(instruction.get("kind"), str) else "append_pytest_test"
    artifact: dict[str, Any] = {
        "kind": "small_unit_test_proposal",
        "subkind": subkind,
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "instruction": instruction,
        "candidate_test_file": selection,
        "packet_operations": operations,
        "safety_checks": safety_checks,
        "blockers": blockers,
        "verification_commands": [],
    }

    request_text = request.user_request.lower()
    target_path = validate_small_unit_test_target(target_root=target_root, rel_path=rel_path, blockers=blockers)

    if subkind == "config_default_test":
        source_rel = instruction.get("source_path") if isinstance(instruction.get("source_path"), str) else None
        source_path = source_file_check(target_root=target_root, rel_path=source_rel, blockers=blockers)
        symbol = instruction.get("symbol")
        expected_value = instruction.get("expected_value")
        if not isinstance(symbol, str) or not symbol.strip():
            blockers.append({"reason": "missing_config_symbol", "message": "Config default tests require an exact symbol."})
        if not isinstance(expected_value, str) or not expected_value.strip():
            blockers.append({"reason": "missing_expected_value", "message": "Config default tests require an exact expected value."})
        if source_path is not None and isinstance(symbol, str) and isinstance(expected_value, str):
            source_text = source_path.read_text(encoding="utf-8", errors="replace")
            if not assignment_line_found(source_text, symbol, expected_value):
                blockers.append(
                    {
                        "reason": "config_default_assignment_not_found",
                        "path": source_rel,
                        "symbol": symbol,
                        "expected_value": expected_value,
                    }
                )
            else:
                safety_checks.append(
                    {
                        "check": "config_default_assignment_found",
                        "status": "passed",
                        "path": source_rel,
                        "symbol": symbol,
                    }
                )
        if not blockers and target_path is not None and isinstance(rel_path, str):
            test_name, test_content = generated_config_default_test(instruction)
            append_small_unit_test_operation(
                rel_path=rel_path,
                target_path=target_path,
                test_name=test_name,
                test_content=test_content,
                safety_checks=safety_checks,
                blockers=blockers,
                operations=operations,
            )
    elif subkind == "message_assertion_test":
        source_rel = instruction.get("source_path") if isinstance(instruction.get("source_path"), str) else None
        source_path = source_file_check(target_root=target_root, rel_path=source_rel, blockers=blockers)
        message_text = instruction.get("message_text")
        if not isinstance(message_text, str) or not message_text.strip():
            blockers.append({"reason": "missing_message_text", "message": "Message assertion tests require exact message text."})
        if source_path is not None and isinstance(message_text, str):
            source_text = source_path.read_text(encoding="utf-8", errors="replace")
            if "OrderBook is read-only; refusing {op}()" not in source_text or "OrderBook is read-only; refusing" not in message_text:
                blockers.append(
                    {
                        "reason": "message_source_not_found",
                        "path": source_rel,
                        "message_text": message_text,
                    }
                )
            else:
                safety_checks.append({"check": "message_template_found", "status": "passed", "path": source_rel})
        if not blockers and target_path is not None and isinstance(rel_path, str):
            test_name, test_content = generated_message_assertion_test(instruction)
            append_small_unit_test_operation(
                rel_path=rel_path,
                target_path=target_path,
                test_name=test_name,
                test_content=test_content,
                safety_checks=safety_checks,
                blockers=blockers,
                operations=operations,
                required_text="OrderBookReadOnlyError",
            )
    elif subkind == "test_assertion_update":
        old_assertion = instruction.get("old_assertion")
        new_assertion = instruction.get("new_assertion")
        if not isinstance(old_assertion, str) or not old_assertion.strip():
            blockers.append({"reason": "missing_old_assertion", "message": "Assertion updates require exact old assertion text."})
        if not isinstance(new_assertion, str) or not new_assertion.strip():
            blockers.append({"reason": "missing_new_assertion", "message": "Assertion updates require exact new assertion text."})
        if not blockers and target_path is not None and isinstance(rel_path, str):
            text = target_path.read_text(encoding="utf-8", errors="replace")
            assert isinstance(old_assertion, str)
            assert isinstance(new_assertion, str)
            if text.count(old_assertion) != 1:
                blockers.append({"reason": "old_assertion_not_found_once", "path": rel_path, "count": text.count(old_assertion)})
            elif new_assertion in text:
                blockers.append({"reason": "new_assertion_already_present", "path": rel_path})
            else:
                safety_checks.extend(
                    [
                        {"check": "target_path_under_root", "status": "passed", "path": rel_path},
                        {"check": "pytest_file", "status": "passed", "path": rel_path},
                        {"check": "old_assertion_unique", "status": "passed", "path": rel_path},
                        {"check": "new_assertion_absent", "status": "passed", "path": rel_path},
                        {"check": "draft_only", "status": "passed", "apply_allowed": False},
                    ]
                )
                operations.append({"kind": "replace_text", "path": rel_path, "old": old_assertion, "new": new_assertion})
    else:
        test_name, test_content = generated_sync_exchange_missing_id_test()
        if "sync_exchange_order_id" not in request_text or "missing" not in request_text or "exchange_order_id" not in request_text:
            blockers.append(
                {
                    "reason": "unsupported_small_unit_test_pattern",
                    "message": "This deterministic L1 unit-test draft currently supports the missing exchange_order_id sync case.",
                }
            )
        if not blockers and target_path is not None and isinstance(rel_path, str):
            append_small_unit_test_operation(
                rel_path=rel_path,
                target_path=target_path,
                test_name=test_name,
                test_content=test_content,
                safety_checks=safety_checks,
                blockers=blockers,
                operations=operations,
                required_text="StealthOrderManager",
            )

    if operations and isinstance(rel_path, str):
        artifact["verification_commands"] = [
            {
                "command": ["python", "-m", "pytest", rel_path],
                "reason": "Run the existing unit-test file that receives the drafted test proposal.",
                "source_refs": [{"path": rel_path}],
            }
        ]

    artifact["status"] = "ready" if operations else "blocked"
    artifact["packet_operations"] = operations
    write_json(run_dir / "small-unit-test-proposal.json", artifact)
    return operations, artifact


def simple_test_fix_instruction_from_context(request: WorkflowRouterPlanRequest) -> dict[str, Any] | None:
    bounded_context = request.context.get("bounded_context") if isinstance(request.context, dict) else None
    if isinstance(bounded_context, list):
        for item in bounded_context:
            if not isinstance(item, dict):
                continue
            instruction = item.get("simple_test_fix")
            if isinstance(instruction, dict):
                return instruction
    return extract_simple_test_fix_instruction(request.user_request)


def failed_test_node_from_request(user_request: str) -> str | None:
    match = re.search(r"(tests/[A-Za-z0-9_./-]+\.py::[A-Za-z0-9_./:-]+)", user_request)
    if match:
        return match.group(1).rstrip(".,;")
    match = re.search(r"(tests/[A-Za-z0-9_./-]+\.py)", user_request)
    if match:
        return match.group(1).rstrip(".,;")
    return None


def simple_test_fix_packet_operations(
    request: WorkflowRouterPlanRequest,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    instruction = simple_test_fix_instruction_from_context(request)
    if instruction is None:
        return [], None
    target_root = Path(request.target_root).resolve()
    rel_path = "core/stealth_order_manager.py"
    old = "            placed_order_id: The order ID placed on the exchange"
    new = "            placed_order_id: The client_order_id placed on the exchange"
    failed_test = failed_test_node_from_request(request.user_request)
    blockers: list[dict[str, Any]] = []
    safety_checks: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    artifact: dict[str, Any] = {
        "kind": "simple_test_fix_proposal",
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "instruction": instruction,
        "failed_test": failed_test,
        "packet_operations": operations,
        "safety_checks": safety_checks,
        "blockers": blockers,
        "verification_commands": [],
    }

    request_text = request.user_request.lower()
    if (
        "find_stealth_order_by_placed_order_id" not in request_text
        or "docstring" not in request_text
        or "client_order_id" not in request_text
    ):
        blockers.append(
            {
                "reason": "unsupported_simple_test_fix_pattern",
                "message": "This deterministic L1 fix currently supports the client_order_id docstring assertion case.",
            }
        )
    target_path = path_under_root(target_root, rel_path)
    if target_path is None:
        blockers.append({"reason": "target_path_outside_root", "path": rel_path})
    elif not target_path.exists() or not target_path.is_file():
        blockers.append({"reason": "missing_target_file", "path": rel_path})
    elif target_path.stat().st_size > SIMPLE_TEST_FIX_MAX_FILE_BYTES:
        blockers.append({"reason": "target_file_too_large", "path": rel_path})

    if not blockers and target_path is not None:
        text = target_path.read_text(encoding="utf-8", errors="replace")
        if new in text:
            blockers.append({"reason": "fix_already_present", "path": rel_path})
        elif text.count(old) != 1:
            blockers.append({"reason": "old_text_not_found_once", "path": rel_path, "count": text.count(old)})
        else:
            safety_checks.extend(
                [
                    {"check": "target_path_under_root", "status": "passed", "path": rel_path},
                    {"check": "old_text_unique", "status": "passed", "path": rel_path},
                    {"check": "new_text_absent", "status": "passed", "path": rel_path},
                    {"check": "draft_only", "status": "passed", "apply_allowed": False},
                ]
            )
            operations.append({"kind": "replace_text", "path": rel_path, "old": old, "new": new})
            command_target = failed_test or "tests/unit/test_order_id_and_followup_rules.py"
            artifact["verification_commands"] = [
                {
                    "command": ["python", "-m", "pytest", command_target],
                    "reason": "Run the failing test or its containing file after reviewing the draft fix.",
                    "source_refs": [{"path": command_target.split("::", 1)[0]}],
                }
            ]

    artifact["status"] = "ready" if operations else "blocked"
    artifact["packet_operations"] = operations
    write_json(run_dir / "simple-test-fix-proposal.json", artifact)
    return operations, artifact


def execution_planning_context(request: WorkflowRouterPlanRequest, decision: dict[str, Any]) -> dict[str, Any]:
    context = dict(request.context)
    context.setdefault("allowed_context_tools", ["structure_index", "git_grep", "read_file", "manual"])
    bounded_context = context.get("bounded_context")
    if not isinstance(bounded_context, list):
        bounded_context = []
    bounded_context.append(
        {
            "source": WORKFLOW_ID,
            "router_selected_workflow": decision.get("selected_workflow"),
            "router_next_action": decision.get("next_action"),
            "route_decision_run_id": decision.get("run_id"),
        }
    )
    context["bounded_context"] = bounded_context
    return context


def approved_run_id_from_context(context: dict[str, Any]) -> str | None:
    bounded_context = context.get("bounded_context")
    if not isinstance(bounded_context, list):
        return None
    for item in bounded_context:
        if isinstance(item, dict) and isinstance(item.get("approved_run_id"), str):
            return item["approved_run_id"]
    return None


def packet_objective_from_context(context: dict[str, Any]) -> str | None:
    bounded_context = context.get("bounded_context")
    if not isinstance(bounded_context, list):
        return None
    for item in bounded_context:
        if isinstance(item, dict) and isinstance(item.get("packet_objective"), str):
            objective = item["packet_objective"].strip()
            if objective:
                return bounded_string(objective, 2000)
    return None


def narrowed_edit_objective_from_context(context: dict[str, Any]) -> str | None:
    bounded_context = context.get("bounded_context")
    if not isinstance(bounded_context, list):
        return None
    for item in bounded_context:
        if isinstance(item, dict) and isinstance(item.get("narrowed_edit_objective"), str):
            objective = item["narrowed_edit_objective"].strip()
            if objective:
                return bounded_string(objective, 2000)
    return None


def proposal_objective_from_context(context: dict[str, Any]) -> str | None:
    return narrowed_edit_objective_from_context(context) or packet_objective_from_context(context)


def load_prior_controller_run(output_root: Path, run_id: str) -> dict[str, Any] | None:
    path = output_root / "controller-runs" / f"{run_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_optional_json(path_value: Any) -> dict[str, Any] | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def candidate_target_files_from_refactor_plan(refactor_plan: dict[str, Any]) -> list[str]:
    investigation = refactor_plan.get("investigation") if isinstance(refactor_plan.get("investigation"), dict) else {}
    plan = investigation.get("plan") if isinstance(investigation.get("plan"), dict) else {}
    seed = plan.get("implementation_packet_seed") if isinstance(plan.get("implementation_packet_seed"), dict) else {}
    files = seed.get("candidate_target_files")
    if not isinstance(files, list):
        return []
    selected: list[str] = []
    for item in files:
        if isinstance(item, str) and item and item not in selected:
            selected.append(item)
    return selected


def verification_commands_from_refactor_plan(refactor_plan: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    investigation = refactor_plan.get("investigation") if isinstance(refactor_plan.get("investigation"), dict) else {}
    plan = investigation.get("plan") if isinstance(investigation.get("plan"), dict) else {}
    verification_plan = plan.get("verification_plan") if isinstance(plan.get("verification_plan"), dict) else {}
    commands = verification_plan.get("verification_commands")
    if not isinstance(commands, list):
        return []
    selected: list[dict[str, Any]] = []
    for command in commands[:limit]:
        if isinstance(command, dict):
            selected.append(command)
    return selected


def line_numbers_for_file(refactor_plan: dict[str, Any], rel_path: str) -> list[int]:
    investigation = refactor_plan.get("investigation") if isinstance(refactor_plan.get("investigation"), dict) else {}
    plan = investigation.get("plan") if isinstance(investigation.get("plan"), dict) else {}
    records = plan.get("participating_files")
    if not isinstance(records, list):
        return []
    lines: list[int] = []
    for record in records:
        if not isinstance(record, dict) or record.get("path") != rel_path:
            continue
        refs = record.get("line_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            line = ref.get("line") if isinstance(ref, dict) else None
            if isinstance(line, int) and line > 0 and line not in lines:
                lines.append(line)
    return lines


def source_snippet(
    target_root: Path,
    rel_path: str,
    line_numbers: list[int],
    *,
    context_lines: int = PROPOSAL_CONTEXT_LINES,
    max_windows: int = PROPOSAL_MAX_WINDOWS_PER_FILE,
    max_chars: int = PROPOSAL_MAX_SNIPPET_CHARS,
) -> dict[str, Any] | None:
    path = target_root / rel_path
    if not path.exists() or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return {"path": rel_path, "line_range": [1, 1], "text": ""}
    if line_numbers:
        ranges: list[tuple[int, int]] = []
        selected_lines: list[int] = []
        for line in line_numbers:
            if line not in selected_lines:
                selected_lines.append(line)
        for line in selected_lines[:max_windows]:
            start = max(1, line - context_lines)
            end = min(len(lines), line + context_lines)
            if ranges and start <= ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
    else:
        ranges = [(1, min(len(lines), context_lines * 2))]
    sections: list[str] = []
    for start, end in ranges:
        sections.append(f"# lines {start}-{end}\n" + "\n".join(lines[start - 1 : end]))
    excerpt = "\n\n".join(sections)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "\n# snippet truncated"
    return {
        "path": rel_path,
        "line_range": [min(start for start, _end in ranges), max(end for _start, end in ranges)],
        "line_ranges": [[start, end] for start, end in ranges],
        "text": excerpt,
    }


def objective_line_numbers_for_file(target_root: Path, rel_path: str, objective: str | None) -> list[int]:
    if not objective:
        return []
    path = target_root / rel_path
    if not path.exists() or not path.is_file():
        return []
    objective_lower = objective.lower()
    terms: list[str] = []
    if "placed_order_id" in objective_lower:
        terms.extend(["find_stealth_order_by_placed_order_id", "_placed_order_index", "placed_order_id"])
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", objective):
        if "_" in token and token not in terms:
            terms.append(token)
    if not terms:
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    selected: list[int] = []
    for term in terms:
        term_lower = term.lower()
        if "_" in term:
            found_definition = False
            definition_pattern = re.compile(rf"^\s*def\s+{re.escape(term)}\b", re.IGNORECASE)
            for index, line in enumerate(lines, 1):
                if definition_pattern.search(line) and index not in selected:
                    selected.append(index)
                    found_definition = True
                    break
            if found_definition:
                continue
        for index, line in enumerate(lines, 1):
            if term_lower in line.lower() and index not in selected:
                selected.append(index)
                break
    return selected


def packet_seed_plan_from_artifact(artifact: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(artifact.get("implementation_packet_seed"), dict):
        return artifact
    investigation = artifact.get("investigation") if isinstance(artifact.get("investigation"), dict) else {}
    plan = investigation.get("plan") if isinstance(investigation.get("plan"), dict) else {}
    if isinstance(plan.get("implementation_packet_seed"), dict):
        return plan
    return None


def candidate_target_files_from_packet_seed_plan(plan: dict[str, Any]) -> list[str]:
    seed = plan.get("implementation_packet_seed") if isinstance(plan.get("implementation_packet_seed"), dict) else {}
    files = seed.get("candidate_target_files")
    if not isinstance(files, list):
        return []
    selected: list[str] = []
    for item in files:
        if isinstance(item, str) and item and item not in selected:
            selected.append(item)
    return selected


def verification_commands_from_packet_seed_plan(plan: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    verification_plan = plan.get("verification_plan") if isinstance(plan.get("verification_plan"), dict) else {}
    commands = verification_plan.get("verification_commands")
    if not isinstance(commands, list):
        return []
    selected: list[dict[str, Any]] = []
    for command in commands[:limit]:
        if isinstance(command, dict):
            selected.append(command)
    return selected


def line_numbers_for_packet_seed_file(plan: dict[str, Any], rel_path: str) -> list[int]:
    records = plan.get("participating_files")
    if not isinstance(records, list):
        return []
    lines: list[int] = []
    for record in records:
        if not isinstance(record, dict) or record.get("path") != rel_path:
            continue
        refs = record.get("line_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            line = ref.get("line") if isinstance(ref, dict) else None
            if isinstance(line, int) and line > 0 and line not in lines:
                lines.append(line)
    return lines


def packet_seed_artifact_from_prior_record(record: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    for artifact_key in ("downstream_investigation_plan", "downstream_refactor_plan"):
        artifact = load_optional_json(artifacts.get(artifact_key))
        if artifact is None:
            continue
        plan = packet_seed_plan_from_artifact(artifact)
        if plan is not None:
            return artifact_key, artifact, plan
    return None, None, None


def proposal_prompt(
    *,
    request: WorkflowRouterPlanRequest,
    approved_run_id: str,
    source_artifact_key: str,
    packet_seed_plan: dict[str, Any],
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "task": "Propose exact draft-only implementation packet operations from an approved investigation.",
        "approved_run_id": approved_run_id,
        "source_artifact_key": source_artifact_key,
        "user_request": request.user_request,
        "packet_objective": packet_objective_from_context(request.context),
        "narrowed_edit_objective": narrowed_edit_objective_from_context(request.context),
        "approval": request.approval,
        "investigation_summary": {
            "likely_beginning_point": packet_seed_plan.get("likely_beginning_point"),
            "multiple_path_assessment": packet_seed_plan.get("multiple_path_assessment"),
            "implementation_packet_seed": packet_seed_plan.get("implementation_packet_seed"),
            "verification_plan": packet_seed_plan.get("verification_plan"),
        },
        "source_snippets": snippets,
        "rules": [
            "Return JSON only.",
            "Return at most five packet_operations.",
            "Use replace_text only.",
            "Each old value must be copied exactly from one supplied source_snippets.text value.",
            "Each new value must be different from old; no no-op replacements.",
            "If narrowed_edit_objective is present, target that behavior delta over the broader packet_objective.",
            "Do not propose apply mode.",
            "Do not create files.",
            "Do not use files outside source_snippets.",
            "If a safe exact operation cannot be proposed, return packet_operations as [] and explain blockers.",
        ],
        "output_shape": {
            "packet_operations": [
                {"kind": "replace_text", "path": "repo-relative path", "old": "exact old text", "new": "exact new text"}
            ],
            "blockers": [{"reason": "why no operation can be safely proposed"}],
            "rationale": "short evidence-based reason",
        },
    }


def call_packet_operation_proposer(
    request: WorkflowRouterPlanRequest,
    prompt: dict[str, Any],
    *,
    max_output_tokens: int = 2400,
) -> dict[str, Any]:
    if not request.role_base_url:
        raise WorkflowRouterError(
            "Packet operation proposal requires role_base_url.",
            code="packet_proposal_model_unavailable",
        )
    payload = {
        "model": request.model,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "messages": [
            {
                "role": "system",
                "content": "You are a deterministic implementation packet proposer. Output exactly one JSON object.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True, indent=2)},
        ],
    }
    body = post_json(f"{request.role_base_url.rstrip('/')}/chat/completions", payload)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise WorkflowRouterError("Packet proposer response did not contain choices.", code="invalid_packet_proposal")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise WorkflowRouterError("Packet proposer response did not contain message.content.", code="invalid_packet_proposal")
    return extract_json_object(content)


def validate_proposed_packet_operations(
    *,
    target_root: Path,
    candidate_files: list[str],
    proposal: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_operations = proposal.get("packet_operations")
    if not isinstance(raw_operations, list):
        return [], [{"reason": "invalid_packet_operations", "message": "packet_operations must be a list."}]
    allowed_files = set(candidate_files)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, operation in enumerate(raw_operations[:5], 1):
        if not isinstance(operation, dict):
            rejected.append({"index": index, "reason": "invalid_operation", "message": "operation must be an object"})
            continue
        kind = operation.get("kind")
        path_value = operation.get("path")
        old = operation.get("old")
        new = operation.get("new")
        if kind != "replace_text":
            rejected.append({"index": index, "reason": "unsupported_operation", "message": "only replace_text is supported"})
            continue
        if not isinstance(path_value, str) or path_value not in allowed_files:
            rejected.append({"index": index, "reason": "path_outside_candidate_scope", "path": path_value})
            continue
        if not isinstance(old, str) or not isinstance(new, str) or not old:
            rejected.append({"index": index, "reason": "invalid_exact_text", "path": path_value})
            continue
        if old == new:
            rejected.append({"index": index, "reason": "noop_operation", "path": path_value})
            continue
        path = target_root / path_value
        if not path.exists() or not path.is_file():
            rejected.append({"index": index, "reason": "missing_target_file", "path": path_value})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count(old)
        if count != 1:
            rejected.append({"index": index, "reason": "old_text_match_count", "path": path_value, "count": count})
            continue
        accepted.append({"kind": "replace_text", "path": path_value, "old": old, "new": new})
    return accepted, rejected


def proposal_validation_failure_counts(proposal: dict[str, Any]) -> dict[str, int]:
    rejected_operations = proposal.get("rejected_operations")
    rejected_reasons: dict[str, int] = {}
    if isinstance(rejected_operations, list):
        for item in rejected_operations:
            if isinstance(item, dict) and isinstance(item.get("reason"), str):
                reason = item["reason"]
                rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
    return rejected_reasons


def model_blocker_reasons(proposal: dict[str, Any]) -> list[str]:
    model_blockers = proposal.get("model_blockers")
    blocker_reasons: list[str] = []
    if isinstance(model_blockers, list):
        for blocker in model_blockers[:3]:
            if isinstance(blocker, dict):
                reason = blocker.get("reason")
                if isinstance(reason, str) and reason.strip():
                    blocker_reasons.append(bounded_string(reason.strip(), 500))
    return blocker_reasons


def proposal_reason_text(proposal: dict[str, Any]) -> str:
    parts: list[str] = []
    rationale = proposal.get("rationale")
    if isinstance(rationale, str):
        parts.append(rationale)
    parts.extend(model_blocker_reasons(proposal))
    model_proposal = proposal.get("model_proposal")
    if isinstance(model_proposal, dict):
        model_rationale = model_proposal.get("rationale")
        if isinstance(model_rationale, str):
            parts.append(model_rationale)
    return " ".join(parts).lower()


def model_claims_no_change_needed(proposal: dict[str, Any]) -> bool:
    text = proposal_reason_text(proposal)
    return any(
        phrase in text
        for phrase in (
            "already the authoritative",
            "already authoritative",
            "already serves this role",
            "no changes are required",
            "no change is required",
            "no replacement operations are needed",
            "no operations are needed",
            "no implementation is needed",
            "no changes are needed",
        )
    )


def objective_path_mentions(objective: str) -> list[str]:
    paths: list[str] = []
    for match in re.findall(r"[\w./-]+\.py", objective):
        cleaned = match.strip("./")
        if cleaned and cleaned not in paths:
            paths.append(cleaned)
    return paths


def objective_terms(objective: str) -> list[str]:
    terms: list[str] = []
    objective_lower = objective.lower()
    if "placed_order_id" in objective_lower:
        terms.extend(["placed_order_id", "_placed_order_index", "find_stealth_order_by_placed_order_id"])
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", objective):
        if "_" in token and token not in terms:
            terms.append(token)
    return terms


def source_snippets_support_objective(proposal: dict[str, Any], objective: str | None) -> tuple[bool, list[dict[str, Any]]]:
    if not objective:
        return False, []
    snippets = proposal.get("source_snippets")
    if not isinstance(snippets, list):
        return False, []
    path_mentions = objective_path_mentions(objective)
    terms = objective_terms(objective)
    evidence_refs: list[dict[str, Any]] = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        path = snippet.get("path")
        text = snippet.get("text")
        if not isinstance(path, str) or not isinstance(text, str):
            continue
        if path_mentions and path not in path_mentions:
            continue
        text_lower = text.lower()
        matched_terms = [term for term in terms if term.lower() in text_lower]
        if not matched_terms:
            continue
        evidence_refs.append(
            {
                "path": path,
                "line_range": snippet.get("line_range"),
                "matched_terms": matched_terms[:5],
            }
        )
    return bool(evidence_refs), evidence_refs


def packet_objective_outcome(request: WorkflowRouterPlanRequest, proposal: dict[str, Any]) -> dict[str, Any] | None:
    objective = proposal_objective_from_context(request.context)
    if not objective:
        return None
    packet_objective = packet_objective_from_context(request.context)
    narrowed_objective = narrowed_edit_objective_from_context(request.context)
    failure_counts = proposal_validation_failure_counts(proposal)
    blocker_reasons = model_blocker_reasons(proposal)
    supported, evidence_refs = source_snippets_support_objective(proposal, objective)
    no_change_claim = model_claims_no_change_needed(proposal)
    if no_change_claim and supported:
        return {
            "status": "no_change_needed",
            "objective": objective,
            "packet_objective": packet_objective,
            "narrowed_edit_objective": narrowed_objective,
            "reason": (
                "The model claimed the requested state is already true, and the bounded source snippets "
                "contained supporting objective terms. No implementation packet is required."
            ),
            "evidence_refs": evidence_refs,
            "verification_commands": proposal.get("verification_commands") if isinstance(proposal.get("verification_commands"), list) else [],
            "proposal_validation_failures": failure_counts,
            "model_blocker_reasons": blocker_reasons,
        }
    return {
        "status": "needs_narrowed_edit_objective",
        "objective": objective,
        "packet_objective": packet_objective,
        "narrowed_edit_objective": narrowed_objective,
        "reason": (
            "The generated proposal did not produce a valid code edit and did not provide enough "
            "source-supported evidence to classify the objective as already complete."
        ),
        "evidence_refs": evidence_refs,
        "verification_commands": proposal.get("verification_commands") if isinstance(proposal.get("verification_commands"), list) else [],
        "proposal_validation_failures": failure_counts,
        "model_blocker_reasons": blocker_reasons,
        "questions": [
            "What concrete behavior should differ after this packet?",
            "Which exact file or function should be changed?",
            "If no code change is needed, should this be recorded as a no-change decision with verification only?",
        ],
    }


def packet_objective_clarification(proposal: dict[str, Any]) -> dict[str, Any]:
    blocker_reasons = model_blocker_reasons(proposal)
    rejected_reasons = proposal_validation_failure_counts(proposal)
    questions = [
        "Which concrete behavior should change?",
        "Which path should become authoritative?",
        "Should the next packet change code, tests, documentation, or only record that no refactor is needed?",
    ]
    if rejected_reasons.get("noop_operation"):
        questions.insert(0, "What exact new source text should replace the current text?")
    if rejected_reasons.get("old_text_match_count") or rejected_reasons.get("invalid_exact_text"):
        questions.insert(0, "Can you provide exact old/new text for one target file?")
    return {
        "status": "needs_packet_objective",
        "reason": (
            "The approved investigation did not contain enough exact behavior detail "
            "to create safe packet operations."
        ),
        "model_blocker_reasons": blocker_reasons,
        "proposal_validation_failures": rejected_reasons,
        "questions": questions,
        "accepted_next_inputs": [
            "Provide exact packet_operations JSON.",
            "Provide a specific packet objective naming the desired authoritative path and target files.",
            "Ask for a new read-only investigation with a narrower behavior description.",
        ],
    }


def propose_packet_operations_from_prior_run(
    request: WorkflowRouterPlanRequest,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    target_root = Path(request.target_root).resolve()
    output_root = Path(request.output_root).resolve()
    approved_run_id = approved_run_id_from_context(request.context)
    proposal_artifact: dict[str, Any] = {
        "kind": "workflow_router_packet_operation_proposal",
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "approved_run_id": approved_run_id,
        "packet_operations": [],
        "rejected_operations": [],
        "blockers": [],
    }
    if not approved_run_id:
        proposal_artifact["blockers"].append({"reason": "missing_approved_run_id"})
        return [], proposal_artifact
    prior_record = load_prior_controller_run(output_root, approved_run_id)
    if prior_record is None:
        proposal_artifact["blockers"].append({"reason": "approved_run_record_not_found"})
        return [], proposal_artifact
    source_artifact_key, _source_artifact, packet_seed_plan = packet_seed_artifact_from_prior_record(prior_record)
    if packet_seed_plan is None or source_artifact_key is None:
        proposal_artifact["blockers"].append({"reason": "approved_run_missing_packet_seed_artifact"})
        return [], proposal_artifact
    candidate_files = candidate_target_files_from_packet_seed_plan(packet_seed_plan)
    packet_objective = packet_objective_from_context(request.context)
    narrowed_objective = narrowed_edit_objective_from_context(request.context)
    proposal_artifact["source_artifact_key"] = source_artifact_key
    proposal_artifact["verification_commands"] = verification_commands_from_packet_seed_plan(packet_seed_plan)
    snippets = [
        snippet
        for rel_path in candidate_files[:6]
        if (
            snippet := source_snippet(
                target_root,
                rel_path,
                objective_line_numbers_for_file(target_root, rel_path, narrowed_objective)
                + (
                    objective_line_numbers_for_file(target_root, rel_path, packet_objective)
                )
                + line_numbers_for_packet_seed_file(packet_seed_plan, rel_path),
            )
        )
        is not None
    ]
    proposal_artifact["candidate_files"] = candidate_files
    proposal_artifact["source_snippets"] = snippets
    if not snippets:
        proposal_artifact["blockers"].append({"reason": "no_source_snippets"})
        return [], proposal_artifact
    prompt = proposal_prompt(
        request=request,
        approved_run_id=approved_run_id,
        source_artifact_key=source_artifact_key,
        packet_seed_plan=packet_seed_plan,
        snippets=snippets,
    )
    write_json(run_dir / "packet-operation-proposal-request.json", prompt)
    try:
        proposal = call_packet_operation_proposer(request, prompt)
    except Exception as exc:  # noqa: BLE001 - proposal failure must block, not fail route execution
        proposal_artifact["blockers"].append({"reason": "model_proposal_failed", "message": bounded_string(exc, 500)})
        write_json(run_dir / "packet-operation-proposal.json", proposal_artifact)
        return [], proposal_artifact
    proposal_artifact["model_proposal"] = proposal
    operations, rejected = validate_proposed_packet_operations(
        target_root=target_root,
        candidate_files=candidate_files,
        proposal=proposal,
    )
    proposal_artifact["packet_operations"] = operations
    proposal_artifact["rejected_operations"] = rejected
    model_blockers = proposal.get("blockers")
    if isinstance(model_blockers, list):
        proposal_artifact["model_blockers"] = model_blockers
    proposal_artifact["rationale"] = bounded_string(proposal.get("rationale", ""), 1000)
    proposal_artifact["status"] = "ready" if operations else "blocked"
    if not operations:
        proposal_artifact["blockers"].append({"reason": "no_valid_packet_operations"})
    write_json(run_dir / "packet-operation-proposal.json", proposal_artifact)
    return operations, proposal_artifact


def invoke_downstream_implementation_prep(
    request: WorkflowRouterPlanRequest,
    decision: dict[str, Any],
    run_dir: Path,
) -> tuple[InvocationResult, dict[str, Any]]:
    config_root = Path(request.config_root).resolve()
    target_root = Path(request.target_root).resolve()
    try:
        policy = resolve_controller_tool_policy(
            config_root,
            "execution_planning.plan",
            "architect/default",
            {"mode": "dry_run"},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise WorkflowRouterError(
            f"Downstream tool policy denied for execution_planning.plan: {exc}",
            code="downstream_tool_policy_denied",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc
    payload = {
        "workflow": "execution_planning.plan",
        "schema_version": SCHEMA_VERSION,
        "target_root": str(target_root),
        "user_request": request.user_request,
        "mode": "dry_run",
        "approval": request.approval,
        "context": execution_planning_context(request, decision),
        "packet_operations": request.packet_operations,
        "budgets": request.execution_budgets,
        "feedback": request.feedback,
        "role_id": "architect/default",
    }
    if request.model:
        payload["model"] = request.model
    downstream_request = ExecutionPlanningInvocationRequest.from_payload(
        payload,
        config_root=config_root,
        target_root=target_root,
        output_root=run_dir,
        role_base_url=request.role_base_url,
    )
    result = invoke_execution_planning(downstream_request)
    return result, policy.audit_record()


def disposable_apply_blockers(request: WorkflowRouterPlanRequest) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if not isinstance(request.approval, dict):
        return [{"reason": "missing_disposable_apply_approval", "message": "approval must be a JSON object."}]
    if request.approval.get("status") != "approved_for_disposable_apply":
        blockers.append(
            {
                "reason": "missing_disposable_apply_approval",
                "message": "apply_disposable_copy requires approval.status=approved_for_disposable_apply.",
            }
        )
    if request.approval.get("apply_allowed") is not True:
        blockers.append(
            {
                "reason": "missing_apply_allowed",
                "message": "apply_disposable_copy requires approval.apply_allowed=true.",
            }
        )
    if request.approval.get("apply_scope") != "disposable_copy_only":
        blockers.append(
            {
                "reason": "invalid_apply_scope",
                "message": "apply_disposable_copy requires approval.apply_scope=disposable_copy_only.",
            }
        )
    if not isinstance(request.packet_operations, list) or not all(
        isinstance(item, dict) for item in request.packet_operations
    ):
        blockers.append({"reason": "invalid_packet_operations", "message": "packet_operations must be a list of objects."})
    elif not request.packet_operations:
        blockers.append(
            {
                "reason": "missing_packet_operations",
                "message": "apply_disposable_copy requires exact packet_operations.",
            }
        )
    else:
        source_root = Path(request.target_root).resolve()
        for index, operation in enumerate(request.packet_operations, 1):
            kind = operation.get("kind")
            if kind not in DISPOSABLE_APPLY_OPERATION_KINDS:
                blockers.append(
                    {
                        "reason": "unsupported_disposable_operation_kind",
                        "message": (
                            f"packet_operations[{index}].kind must be one of "
                            f"{', '.join(sorted(DISPOSABLE_APPLY_OPERATION_KINDS))}."
                        ),
                    }
                )
            try:
                normalize_disposable_operation_path(source_root, operation.get("path"))
            except ValueError as exc:
                blockers.append(
                    {
                        "reason": "invalid_disposable_operation_path",
                        "message": f"packet_operations[{index}].path must stay inside the source root: {exc}",
                    }
                )
    return blockers


def packet_file_from_operations(run_dir: Path, packet_operations: list[dict[str, Any]]) -> Path:
    packets: list[dict[str, Any]] = []
    for index, operation in enumerate(packet_operations, 1):
        path = operation.get("path")
        kind = operation.get("kind")
        packets.append(
            {
                "id": f"DISPOSABLE-APPLY-{index:04d}",
                "task": "apply_approved_packet_operation_to_disposable_copy",
                "target_files": [path] if isinstance(path, str) else [],
                "allowed_operations": [kind] if isinstance(kind, str) else [],
                "operation": operation,
                "source_refs": [{"path": path}] if isinstance(path, str) else [],
                "acceptance_criteria": ["Approved packet operation applies only to the disposable copy."],
                "max_context_tokens": 2000,
            }
        )
    packet_file = run_dir / "disposable-apply-packets.json"
    write_json(packet_file, {"schema_version": SCHEMA_VERSION, "packets": packets, "verification_commands": []})
    return packet_file


def tracked_file_status(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == repo_root.resolve()
    except OSError:
        return False


def initialize_disposable_git_repo(repo_root: Path, packet_operations: list[dict[str, Any]]) -> None:
    if tracked_file_status(repo_root):
        return
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
    paths = [operation.get("path") for operation in packet_operations if isinstance(operation.get("path"), str)]
    if paths:
        subprocess.run(["git", "add", *paths], cwd=repo_root, check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)


def normalize_disposable_operation_path(root: Path, value: Any) -> tuple[str, Path]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("operation path must be a non-empty string")
    normalized = value.strip().replace("\\", "/")
    raw_path = Path(normalized)
    if raw_path.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {value}")
    root_resolved = root.resolve()
    candidate = (root_resolved / raw_path).resolve()
    try:
        relative_path = candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes root: {value}") from exc
    if any(part == ".." for part in relative_path.parts):
        raise ValueError(f"path escapes root: {value}")
    return relative_path.as_posix(), candidate


def hash_operation_targets(root: Path, packet_operations: list[dict[str, Any]]) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}
    for operation in packet_operations:
        try:
            relative_path, path = normalize_disposable_operation_path(root, operation.get("path"))
        except ValueError as exc:
            raise WorkflowRouterError(
                f"Invalid disposable operation path: {exc}",
                code="invalid_disposable_operation_path",
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            ) from exc
        hashes[relative_path] = file_sha256(path) if path.exists() and path.is_file() else None
    return hashes


def backup_operation_targets(
    root: Path,
    packet_operations: list[dict[str, Any]],
    backup_dir: Path,
) -> dict[str, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[str, str] = {}
    for operation in packet_operations:
        try:
            path_value, source = normalize_disposable_operation_path(root, operation.get("path"))
        except ValueError:
            continue
        if not source.exists() or not source.is_file():
            continue
        backup = (backup_dir / f"{artifact_safe_name(path_value)}.bak").resolve()
        backup.write_bytes(source.read_bytes())
        backups[path_value] = str(backup)
    return backups


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    root_resolved = root.resolve()
    for path in sorted(item for item in root_resolved.rglob("*") if item.is_file()):
        relative_path = path.relative_to(root_resolved)
        if any(part in DISPOSABLE_TREE_DIGEST_EXCLUDED_DIRS for part in relative_path.parts):
            continue
        file_digest = file_sha256(path)
        relative_text = relative_path.as_posix()
        digest.update(relative_text.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\0")
        file_count += 1
        total_bytes += path.stat().st_size
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "sha256": digest.hexdigest(),
    }


def rollback_disposable_copy(
    copy_root: Path,
    packet_operations: list[dict[str, Any]],
    expected_hashes: dict[str, str | None],
    run_dir: Path,
    backups: dict[str, str],
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    for operation in packet_operations:
        kind = operation.get("kind")
        try:
            path_value, target = normalize_disposable_operation_path(copy_root, operation.get("path"))
        except ValueError as exc:
            blockers.append({"reason": "invalid_operation_path", "operation": operation, "detail": str(exc)})
            continue
        backup_path_value = backups.get(path_value)
        if isinstance(backup_path_value, str):
            backup_path = Path(backup_path_value)
            if backup_path.exists() and backup_path.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(backup_path.read_bytes())
                continue
            blockers.append({"reason": "missing_rollback_backup", "path": path_value, "backup": backup_path_value})
            continue
        if not target.exists() or not target.is_file():
            blockers.append({"reason": "missing_target_file", "path": path_value})
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        if kind == "replace_text" and isinstance(operation.get("old"), str) and isinstance(operation.get("new"), str):
            count = text.count(operation["new"])
            if count != 1:
                blockers.append({"reason": "rollback_new_text_not_unique", "path": path_value, "count": count})
                continue
            target.write_text(text.replace(operation["new"], operation["old"], 1), encoding="utf-8")
        elif kind == "append_text" and isinstance(operation.get("content"), str):
            content = operation["content"]
            if not text.endswith(content):
                blockers.append({"reason": "rollback_append_suffix_not_found", "path": path_value})
                continue
            target.write_text(text[: -len(content)], encoding="utf-8")
        else:
            blockers.append({"reason": "unsupported_rollback_operation", "path": path_value, "kind": kind})
    after_hashes = hash_operation_targets(copy_root, packet_operations)
    changed_after_rollback = {
        path: {"expected": expected_hashes.get(path), "actual": after_hashes.get(path)}
        for path in sorted(expected_hashes)
        if expected_hashes.get(path) != after_hashes.get(path)
    }
    proof = {
        "status": "restored" if not blockers and not changed_after_rollback else "failed",
        "disposable_copy_root": str(copy_root),
        "expected_hashes": expected_hashes,
        "after_hashes": after_hashes,
        "changed_after_rollback": changed_after_rollback,
        "backup_artifacts": backups,
        "blockers": blockers,
    }
    rollback_path = run_dir / "disposable-rollback-proof.json"
    write_json(rollback_path, proof)
    proof["artifact"] = str(rollback_path)
    return proof


def ensure_path_under(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise WorkflowRouterError(
            f"{label} must stay under {root.resolve()}: {path.resolve()}",
            code="mutation_sandbox_contract_failed",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc


def build_disposable_sandbox_contract(
    request: WorkflowRouterPlanRequest,
    *,
    source_root: Path,
    copy_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    ensure_path_under(copy_root, run_dir, "disposable copy root")
    if source_root.resolve() == copy_root.resolve():
        raise WorkflowRouterError(
            "Disposable copy root must be different from source root.",
            code="mutation_sandbox_contract_failed",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    allowed_paths: list[dict[str, Any]] = []
    for index, operation in enumerate(request.packet_operations, 1):
        try:
            source_relative, source_path = normalize_disposable_operation_path(source_root, operation.get("path"))
            copy_relative, copy_path = normalize_disposable_operation_path(copy_root, operation.get("path"))
        except ValueError as exc:
            raise WorkflowRouterError(
                f"Disposable mutation sandbox rejected packet_operations[{index}].path: {exc}",
                code="mutation_sandbox_contract_failed",
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            ) from exc
        if source_relative != copy_relative:
            raise WorkflowRouterError(
                "Disposable mutation sandbox path normalization mismatch.",
                code="mutation_sandbox_contract_failed",
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        allowed_paths.append(
            {
                "operation_index": index,
                "relative_path": source_relative,
                "operation_kind": operation.get("kind"),
                "source_path": str(source_path),
                "copy_path": str(copy_path),
            }
        )
    contract = {
        "schema_version": SCHEMA_VERSION,
        "kind": "disposable_mutation_sandbox_contract",
        "status": "active",
        "mutation_policy": "disposable_copy_only",
        "approval_status": request.approval.get("status") if isinstance(request.approval, dict) else None,
        "approval_scope": request.approval.get("apply_scope") if isinstance(request.approval, dict) else None,
        "source_root": str(source_root),
        "disposable_copy_root": str(copy_root),
        "run_dir": str(run_dir),
        "allowed_write_root": str(copy_root),
        "allowed_operation_paths": allowed_paths,
        "guardrails": [
            "source_root_read_only",
            "copy_root_must_be_under_run_dir",
            "packet_paths_must_be_repo_relative",
            "implementation_workflow_is_the_only_apply_executor",
            "rollback_must_restore_copy_hashes",
        ],
    }
    contract_path = run_dir / "disposable-mutation-sandbox-contract.json"
    write_json(contract_path, contract)
    contract["artifact"] = str(contract_path)
    return contract


def structured_disposable_diff(
    *,
    copy_root: Path,
    packet_operations: list[dict[str, Any]],
    backups: dict[str, str],
    before_hashes: dict[str, str | None],
    after_hashes: dict[str, str | None],
    run_dir: Path,
    max_diff_lines: int = 120,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for operation in packet_operations:
        try:
            relative_path, target = normalize_disposable_operation_path(copy_root, operation.get("path"))
        except ValueError as exc:
            records.append({"status": "invalid_path", "path": operation.get("path"), "detail": str(exc)})
            continue
        backup_path_value = backups.get(relative_path)
        before_text = ""
        before_exists = False
        if isinstance(backup_path_value, str):
            backup_path = Path(backup_path_value)
            if backup_path.exists() and backup_path.is_file():
                before_text = backup_path.read_text(encoding="utf-8", errors="replace")
                before_exists = True
        after_exists = target.exists() and target.is_file()
        after_text = target.read_text(encoding="utf-8", errors="replace") if after_exists else ""
        diff_lines = list(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
                lineterm="",
            )
        )
        records.append(
            {
                "status": "changed" if before_hashes.get(relative_path) != after_hashes.get(relative_path) else "unchanged",
                "path": relative_path,
                "operation_kind": operation.get("kind"),
                "before_exists": before_exists,
                "after_exists": after_exists,
                "before_sha256": before_hashes.get(relative_path),
                "after_sha256": after_hashes.get(relative_path),
                "added_line_count": sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")),
                "removed_line_count": sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---")),
                "unified_diff_excerpt": diff_lines[:max_diff_lines],
                "diff_truncated": len(diff_lines) > max_diff_lines,
            }
        )
    proof = {
        "schema_version": SCHEMA_VERSION,
        "kind": "disposable_mutation_structured_diff",
        "status": "ready",
        "disposable_copy_root": str(copy_root),
        "changed_file_count": sum(1 for record in records if record.get("status") == "changed"),
        "records": records,
    }
    diff_path = run_dir / "disposable-mutation-diff.json"
    write_json(diff_path, proof)
    proof["artifact"] = str(diff_path)
    return proof


def invoke_disposable_copy_apply(
    request: WorkflowRouterPlanRequest,
    run_dir: Path,
) -> tuple[InvocationResult, dict[str, Any]]:
    source_root = Path(request.target_root).resolve()
    copy_root = run_dir / "copy"
    shutil.copytree(source_root, copy_root)
    sandbox_contract = build_disposable_sandbox_contract(
        request,
        source_root=source_root,
        copy_root=copy_root,
        run_dir=run_dir,
    )
    initialize_disposable_git_repo(copy_root, request.packet_operations)
    source_tree_before = tree_digest(source_root)
    copy_tree_before = tree_digest(copy_root)
    source_before = hash_operation_targets(source_root, request.packet_operations)
    copy_before = hash_operation_targets(copy_root, request.packet_operations)
    rollback_backups = backup_operation_targets(copy_root, request.packet_operations, run_dir / "rollback-backups")
    packet_file = packet_file_from_operations(run_dir, request.packet_operations)
    result = invoke_implementation_workflow(
        ImplementationWorkflowInvocationRequest(
            target_root=copy_root,
            output_dir=run_dir / "implementation-apply",
            mode="apply",
            packet_file=packet_file,
            no_structure_index=True,
        )
    )
    source_tree_after_apply = tree_digest(source_root)
    copy_tree_after_apply = tree_digest(copy_root)
    source_after = hash_operation_targets(source_root, request.packet_operations)
    copy_after = hash_operation_targets(copy_root, request.packet_operations)
    source_changed = {
        path: {"before": source_before.get(path), "after": source_after.get(path)}
        for path in sorted(source_before)
        if source_before.get(path) != source_after.get(path)
    }
    copy_changed = {
        path: {"before": copy_before.get(path), "after": copy_after.get(path)}
        for path in sorted(copy_before)
        if copy_before.get(path) != copy_after.get(path)
    }
    structured_diff = structured_disposable_diff(
        copy_root=copy_root,
        packet_operations=request.packet_operations,
        backups=rollback_backups,
        before_hashes=copy_before,
        after_hashes=copy_after,
        run_dir=run_dir,
    )
    rollback = rollback_disposable_copy(copy_root, request.packet_operations, copy_before, run_dir, rollback_backups)
    copy_tree_after_rollback = tree_digest(copy_root)
    source_tree_after_rollback = tree_digest(source_root)
    source_tree_changed = source_tree_before != source_tree_after_apply or source_tree_before != source_tree_after_rollback
    copy_tree_restored = copy_tree_before == copy_tree_after_rollback
    proof = {
        "schema_version": SCHEMA_VERSION,
        "kind": "disposable_mutation_proof",
        "workflow": "implementation.workflow",
        "mode": "apply",
        "source_root": str(source_root),
        "disposable_copy_root": str(copy_root),
        "packet_file": str(packet_file),
        "sandbox_contract": sandbox_contract,
        "source_tree_before": source_tree_before,
        "source_tree_after_apply": source_tree_after_apply,
        "source_tree_after_rollback": source_tree_after_rollback,
        "source_tree_changed": source_tree_changed,
        "copy_tree_before": copy_tree_before,
        "copy_tree_after_apply": copy_tree_after_apply,
        "copy_tree_after_rollback": copy_tree_after_rollback,
        "copy_tree_restored": copy_tree_restored,
        "source_hashes_before": source_before,
        "source_hashes_after": source_after,
        "copy_hashes_before": copy_before,
        "copy_hashes_after": copy_after,
        "source_changed": source_changed,
        "copy_changed": copy_changed,
        "structured_diff": structured_diff,
        "rollback": rollback,
    }
    proof_path = run_dir / "disposable-mutation-proof.json"
    write_json(proof_path, proof)
    proof["artifact"] = str(proof_path)
    if source_changed or source_tree_changed:
        raise WorkflowRouterError(
            "Source target changed during disposable-copy apply.",
            code="source_mutation_detected",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    if not copy_changed:
        raise WorkflowRouterError(
            "Disposable copy did not change during apply.",
            code="disposable_copy_not_mutated",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if rollback.get("status") != "restored":
        raise WorkflowRouterError(
            "Disposable copy rollback did not restore original hashes.",
            code="disposable_copy_rollback_failed",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if not copy_tree_restored:
        raise WorkflowRouterError(
            "Disposable copy rollback did not restore original tree digest.",
            code="disposable_copy_rollback_failed",
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    return result, proof


def prefixed_artifacts(prefix: str, artifacts: dict[str, str]) -> dict[str, str]:
    return {f"{prefix}_{key}": value for key, value in artifacts.items()}


def expected_approval_for_mode(mode: str) -> dict[str, Any] | None:
    if mode == "implementation_prep":
        return {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["natural_approval:<source_run_id>"],
        }
    if mode == "apply_disposable_copy":
        return {
            "status": "approved_for_disposable_apply",
            "scope": "workflow_router_disposable_copy",
            "apply_allowed": True,
            "apply_scope": "disposable_copy_only",
            "approval_refs": ["founder-approved disposable copy apply"],
        }
    return None


def approval_type_for_mode(mode: str) -> str:
    if mode == "implementation_prep":
        return "packet_design"
    if mode == "apply_disposable_copy":
        return "disposable_copy_apply"
    return "none"


def expected_approval_for_type(approval_type: str) -> dict[str, Any] | None:
    if approval_type == "packet_design":
        return expected_approval_for_mode("implementation_prep")
    if approval_type == "disposable_copy_apply":
        return expected_approval_for_mode("apply_disposable_copy")
    return None


def approval_type_for_decision(request: WorkflowRouterPlanRequest, decision: dict[str, Any]) -> str:
    approval_type = approval_type_for_mode(request.mode)
    if approval_type != "none":
        return approval_type
    if decision.get("next_action") == "request_approval" or decision.get("selected_workflow") == "execution_planning.plan":
        return "packet_design"
    return "none"


def expected_approval_for_decision(
    request: WorkflowRouterPlanRequest,
    decision: dict[str, Any],
    approval_type: str,
) -> dict[str, Any] | None:
    if request.mode in {"implementation_prep", "apply_disposable_copy"}:
        return expected_approval_for_type(approval_type)
    if decision.get("next_action") == "request_approval" and approval_type != "none":
        return expected_approval_for_type(approval_type)
    if isinstance(request.approval, dict) and request.approval and approval_type != "none":
        return expected_approval_for_type(approval_type)
    return None


def approval_status_for_expected(
    request: WorkflowRouterPlanRequest,
    expected: dict[str, Any] | None,
) -> str:
    if expected is None:
        return "not_required"
    if not isinstance(request.approval, dict):
        return "missing"
    expected_status = expected.get("status")
    actual_status = request.approval.get("status")
    if actual_status == expected_status:
        return "approved"
    if actual_status:
        return "invalid"
    return "missing"


def approval_next_action_text(
    *,
    run_id: str,
    request: WorkflowRouterPlanRequest,
    decision: dict[str, Any],
    approval_status: str,
    approval_type: str,
) -> str:
    if approval_type == "packet_design":
        if approval_status != "approved":
            return (
                f"Approve packet design for run {run_id} and include exact packet_operations JSON. "
                "The continuation must stay draft-only."
            )
        if decision.get("status") == "blocked":
            return "Provide exact packet_operations JSON, a packet objective, or a narrowed edit objective."
        return "No approval action remains for this run."
    if approval_type == "disposable_copy_apply":
        if approval_status != "approved":
            return (
                f"Approve disposable-copy apply for run {run_id} with apply_scope=disposable_copy_only "
                "and exact packet_operations JSON."
            )
        if decision.get("status") == "blocked":
            return "Fix the blocked packet_operations or disposable-copy approval fields before retrying."
        return "No approval action remains for this run."
    if decision.get("next_action") == "request_approval":
        return f"Review run {run_id}, then send an approved continuation with the required approval fields."
    return "No approval action is required for this run."


def approval_state_status(
    *,
    request: WorkflowRouterPlanRequest,
    decision: dict[str, Any],
    approval_status: str,
) -> str:
    if approval_status in {"missing", "invalid"}:
        return "waiting_for_approval"
    if approval_status == "approved":
        if decision.get("status") == "blocked":
            return "blocked"
        if decision.get("downstream"):
            return "finished"
        return "approved"
    if decision.get("next_action") == "request_approval":
        return "waiting_for_approval"
    if decision.get("status") == "blocked":
        return "blocked"
    if request.mode in {"execute_read_only", "plan_only"}:
        return "not_required"
    return "finished" if decision.get("downstream") else "not_required"


def build_workflow_router_approval_state(
    *,
    request: WorkflowRouterPlanRequest,
    decision: dict[str, Any],
    run_id: str,
    target_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    approval_type = approval_type_for_decision(request, decision)
    expected_approval = expected_approval_for_decision(request, decision, approval_type)
    approval_status = approval_status_for_expected(request, expected_approval)
    state_status = approval_state_status(
        request=request,
        decision=decision,
        approval_status=approval_status,
    )
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    approved_run_id = approved_run_id_from_context(request.context)
    state = {
        "kind": "workflow_router_approval_state",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "target_root": str(target_root),
        "mode": request.mode,
        "selected_workflow": decision.get("selected_workflow"),
        "route_status": decision.get("status"),
        "status": state_status,
        "approval_type": approval_type,
        "approval_status": approval_status,
        "expected_approval": expected_approval,
        "received_approval": request.approval if isinstance(request.approval, dict) else None,
        "source_run_id": approved_run_id,
        "next_action": decision.get("next_action"),
        "next_action_text": approval_next_action_text(
            run_id=run_id,
            request=request,
            decision=decision,
            approval_status=approval_status,
            approval_type=approval_type,
        ),
        "blockers": blockers,
        "created_at": utc_now(),
    }
    artifact_path = run_dir / "approval-state.json"
    write_json(artifact_path, state)
    state["artifact"] = str(artifact_path)
    return state


def is_advanced_refactor_readiness_blocked(decision: dict[str, Any]) -> bool:
    blockers = decision.get("blockers")
    if not isinstance(blockers, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("reason") in {"advanced_refactor_readiness_not_met", "advanced_refactor_pilot_scope_not_admitted"}
        for item in blockers
    )


def blocked_decision(
    request: WorkflowRouterPlanRequest,
    *,
    route_status: str,
    status_reason: str,
    evidence: list[dict[str, Any]],
    workflow_registry: dict[str, dict[str, Any]],
    skill_registry: dict[str, dict[str, Any]],
    tool_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    next_action = "ask_blocking_question" if status_reason == "ambiguous" else "none"
    if status_reason == "blocked_approval_bypass":
        next_action = "request_approval"
    status = "unsupported" if route_status == "unsupported" else "blocked"
    blockers = [{"reason": status_reason, "message": blocker_message(status_reason)}]
    selected_workflow = None
    selected_skills: list[str] = []
    selected_tools: list[str] = []
    confidence = "low"
    context_audit = context_source_audit(
        target_root=Path(request.target_root).resolve(),
        selected_workflow=selected_workflow,
        route_evidence=evidence,
        selected_tools=selected_tools,
        query_text=request.user_request,
    )
    return {
        "workflow": WORKFLOW_ID,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "selected_workflow": selected_workflow,
        "confidence": confidence,
        "selected_skills": selected_skills,
        "selected_tools": selected_tools,
        "selection_audit": selection_audit(
            config_root=Path(request.config_root).resolve(),
            workflow_registry=workflow_registry,
            skill_registry=skill_registry,
            tool_registry=tool_registry,
            selected_workflow=selected_workflow,
            confidence=confidence,
            status_reason=status_reason,
            route_evidence=evidence,
            selected_skills=selected_skills,
            selected_tools=selected_tools,
            query_text=request.user_request,
            skill_limit=validate_budgets(request.budgets)["max_selected_skills"],
        ),
        "context_source_audit": context_audit,
        "selected_context_sources": context_audit["selected_source_ids"],
        "approval_required_before": [],
        "controller_request_preview": {},
        "evidence": registry_evidence(workflow_registry, skill_registry, tool_registry) + evidence,
        "blockers": blockers,
        "next_action": next_action,
    }


def blocker_message(reason: str) -> str:
    messages = {
        "ambiguous": "The request does not name enough behavior, workflow, symbol, or file context to route safely.",
        "blocked_approval_bypass": "The request asks to bypass or skip approval before mutation.",
        "blocked_raw_context": "The request asks for raw CodeGraphContext, MCP, or Cypher operations that are not model-visible.",
        "unsupported": "The request does not match a supported local development workflow.",
    }
    return messages.get(reason, "The request cannot be routed safely.")


def registry_evidence(
    workflow_registry: dict[str, dict[str, Any]],
    skill_registry: dict[str, dict[str, Any]],
    tool_registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "source": "workflow_registry",
            "available_workflows": sorted(key for key in workflow_registry if key in ROUTABLE_WORKFLOWS),
        },
        {
            "source": "skill_registry",
            "available_skill_count": len(skill_registry),
            "available_skills": sorted(skill_registry)[:20],
        },
        {
            "source": "tool_registry",
            "available_tool_count": len(tool_registry),
        },
    ]


def route_rules_from_evidence(evidence: list[dict[str, Any]]) -> list[str]:
    rules: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        rule = item.get("rule")
        if isinstance(rule, str):
            append_unique(rules, rule)
    return rules


def evidence_sources(evidence: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    for item in evidence:
        if isinstance(item, dict) and isinstance(item.get("source"), str):
            append_unique(sources, item["source"])
    return sources


def prompt_skill_coverage_matches(
    config_root: Path,
    *,
    route_rules: list[str],
    selected_workflow: str | None,
    selected_skills: list[str],
    selected_tools: list[str],
) -> list[dict[str, Any]]:
    if selected_workflow is None or not route_rules:
        return []
    coverage_path = config_root / PROMPT_SKILL_COVERAGE_PATH
    if not coverage_path.exists():
        return []
    try:
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = coverage.get("entries") if isinstance(coverage, dict) else None
    if not isinstance(entries, list):
        return []
    route_rule_set = set(route_rules)
    selected_skill_set = set(selected_skills)
    selected_tool_set = set(selected_tools)
    matches: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        route_rule = entry.get("route_rule")
        if not isinstance(route_rule, str) or route_rule not in route_rule_set:
            continue
        if entry.get("selected_workflow") != selected_workflow:
            continue
        skill_ids = [item for item in entry.get("skill_ids", []) if isinstance(item, str)]
        tool_ids = [item for item in entry.get("tool_ids", []) if isinstance(item, str)]
        matches.append(
            {
                "entry_id": entry.get("id"),
                "prompt_family": entry.get("prompt_family"),
                "level": entry.get("level"),
                "status": entry.get("status"),
                "route_rule": route_rule,
                "selected_workflow": entry.get("selected_workflow"),
                "skill_overlap": sorted(selected_skill_set & set(skill_ids)),
                "tool_overlap": sorted(selected_tool_set & set(tool_ids)),
            }
        )
    return matches


def confidence_meets_threshold(confidence: str, minimum: str | None = None) -> bool:
    if minimum is None:
        minimum = SELECTION_MIN_CONFIDENCE
    return CONFIDENCE_RANK.get(confidence, 0) >= CONFIDENCE_RANK.get(minimum, 1)


def workflow_candidate_rejection_reason(
    workflow_id: str,
    *,
    selected_workflow: str | None,
    status_reason: str,
    route_rules: list[str],
) -> str:
    if selected_workflow is None:
        return f"blocked_{status_reason}"
    if workflow_id == selected_workflow:
        return "selected"
    if route_rules:
        return "other_workflow_router_rule_matched"
    return "no_matching_router_rule"


def workflow_candidate_audit(
    workflow_registry: dict[str, dict[str, Any]],
    *,
    selected_workflow: str | None,
    status_reason: str,
    route_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    route_rules = route_rules_from_evidence(route_evidence)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for workflow_id in sorted(workflow_id for workflow_id in workflow_registry if workflow_id in ROUTABLE_WORKFLOWS):
        workflow = workflow_registry.get(workflow_id, {})
        item = {
            "workflow_id": workflow_id,
            "description": workflow.get("description") if isinstance(workflow, dict) else None,
            "status": "selected" if workflow_id == selected_workflow else "rejected",
            "reasons": [],
        }
        if workflow_id == selected_workflow:
            item["reasons"] = [
                "selected_by_router_rule" if route_rules else "selected_by_supported_workflow",
                *[f"route_rule:{rule}" for rule in route_rules[:5]],
            ]
            selected.append(item)
        else:
            item["reasons"] = [
                workflow_candidate_rejection_reason(
                    workflow_id,
                    selected_workflow=selected_workflow,
                    status_reason=status_reason,
                    route_rules=route_rules,
                )
            ]
            if len(rejected) < MAX_REJECTED_CANDIDATES:
                rejected.append(item)
    return {
        "selected": selected,
        "rejected": rejected,
        "candidate_count": len([workflow_id for workflow_id in workflow_registry if workflow_id in ROUTABLE_WORKFLOWS]),
        "rejected_count": max(0, len([workflow_id for workflow_id in workflow_registry if workflow_id in ROUTABLE_WORKFLOWS]) - len(selected)),
    }


def skill_candidate_audit(
    skill_registry: dict[str, dict[str, Any]],
    *,
    workflow_id: str | None,
    query_text: str,
    selected_skills: list[str],
    limit: int,
) -> dict[str, Any]:
    if workflow_id is None:
        return {
            "workflow_id": None,
            "selected": [],
            "rejected": [],
            "candidate_count": 0,
            "rejected_count": 0,
            "filtered_count": 0,
            "body_reads_during_selection": 0,
            "selection_basis": "not_routed",
        }
    explanation = explain_skill_selection_for_workflow(
        skill_registry,
        workflow_id,
        query_text=query_text,
        limit=limit,
        max_filtered=MAX_REJECTED_CANDIDATES,
    )
    selected_set = set(selected_skills)
    selected_details: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in explanation.get("selected", []):
        if not isinstance(item, dict):
            continue
        skill_id = item.get("skill_id")
        if isinstance(skill_id, str) and skill_id in selected_set:
            selected_details.append({**item, "status": "selected", "reasons": ["selected_by_capability_contract"]})
        elif isinstance(skill_id, str) and len(rejected) < MAX_REJECTED_CANDIDATES:
            rejected.append({**item, "status": "rejected", "reasons": ["not_selected_after_router_rule_override"]})
    for skill_id in selected_skills:
        if any(item.get("skill_id") == skill_id for item in selected_details):
            continue
        skill = skill_registry.get(skill_id, {})
        contract = skill.get("capability_contract") if isinstance(skill, dict) else {}
        selected_details.append(
            {
                "skill_id": skill_id,
                "route_key": contract.get("route_key") if isinstance(contract, dict) else None,
                "status": "selected",
                "reasons": ["selected_by_router_rule_override"],
            }
        )
    for item in explanation.get("filtered", []):
        if isinstance(item, dict) and len(rejected) < MAX_REJECTED_CANDIDATES:
            rejected.append({**item, "status": "rejected"})
    return {
        "workflow_id": workflow_id,
        "selected": selected_details,
        "rejected": rejected,
        "candidate_count": explanation.get("candidate_count", 0),
        "rejected_count": max(0, int(explanation.get("filtered_count", 0)) + int(explanation.get("candidate_count", 0)) - len(selected_details)),
        "filtered_count": explanation.get("filtered_count", 0),
        "deprecated_exclusions": explanation.get("deprecated_exclusions", []),
        "route_namespace_summary": explanation.get("route_namespace_summary", {}),
        "body_reads_during_selection": explanation.get("body_reads_during_selection", 0),
        "selection_basis": "capability_contract_shortlist",
    }


def tool_candidate_audit(
    tool_registry: dict[str, dict[str, Any]],
    *,
    selected_tools: list[str],
) -> dict[str, Any]:
    selected_set = set(selected_tools)
    selected = [{"tool_id": tool_id, "status": "selected", "reasons": ["allowed_by_workflow_tool_policy"]} for tool_id in selected_tools]
    rejected: list[dict[str, Any]] = []
    for tool_id in sorted(tool_registry):
        if tool_id in selected_set:
            continue
        if len(rejected) >= MAX_REJECTED_CANDIDATES:
            break
        rejected.append({"tool_id": tool_id, "status": "rejected", "reasons": ["not_allowed_by_selected_workflow"]})
    return {
        "selected": selected,
        "rejected": rejected,
        "candidate_count": len(tool_registry),
        "rejected_count": max(0, len(tool_registry) - len(selected)),
    }


def context_layout_summary(target_root: Path) -> dict[str, Any]:
    root = target_root.resolve()
    if not root.exists() or not root.is_dir():
        return {
            "status": "missing",
            "target_root": str(root),
            "supported_file_count": 0,
            "sample_files": [],
            "scanned_file_count": 0,
            "scan_limit": CONTEXT_LAYOUT_MAX_SCANNED_FILES,
            "sample_limit": CONTEXT_LAYOUT_MAX_SAMPLE_FILES,
            "supported_extensions": sorted(CONTEXT_LAYOUT_SUPPORTED_EXTENSIONS),
            "ignored_dirs": sorted(CONTEXT_LAYOUT_IGNORED_DIRS),
            "git_present": False,
        }

    supported_file_count = 0
    scanned_file_count = 0
    sample_files: list[str] = []
    stopped_at_limit = False
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            dirname
            for dirname in dirs
            if dirname not in CONTEXT_LAYOUT_IGNORED_DIRS and not dirname.startswith(".agentic")
        ]
        for filename in files:
            scanned_file_count += 1
            if scanned_file_count > CONTEXT_LAYOUT_MAX_SCANNED_FILES:
                stopped_at_limit = True
                break
            relative_path = str((Path(current_root) / filename).relative_to(root)).replace("\\", "/")
            suffix = Path(filename).suffix.lower()
            if suffix in CONTEXT_LAYOUT_SUPPORTED_EXTENSIONS:
                supported_file_count += 1
                if len(sample_files) < CONTEXT_LAYOUT_MAX_SAMPLE_FILES:
                    sample_files.append(relative_path)
        if stopped_at_limit:
            break

    status = "supported" if supported_file_count > 0 else "unsupported_no_supported_files"
    return {
        "status": status,
        "target_root": str(root),
        "supported_file_count": supported_file_count,
        "sample_files": sample_files,
        "scanned_file_count": min(scanned_file_count, CONTEXT_LAYOUT_MAX_SCANNED_FILES),
        "scan_limit": CONTEXT_LAYOUT_MAX_SCANNED_FILES,
        "sample_limit": CONTEXT_LAYOUT_MAX_SAMPLE_FILES,
        "supported_extensions": sorted(CONTEXT_LAYOUT_SUPPORTED_EXTENSIONS),
        "ignored_dirs": sorted(CONTEXT_LAYOUT_IGNORED_DIRS),
        "git_present": (root / ".git").exists(),
        "stopped_at_limit": stopped_at_limit,
    }


def source_catalog_item(source_id: str) -> dict[str, Any]:
    item = CONTEXT_SOURCE_CATALOG.get(source_id, {})
    return {
        "source_id": source_id,
        "description": item.get("description"),
        "tool_ids": list(item.get("tool_ids", [])) if isinstance(item.get("tool_ids"), list) else [],
        "artifact_keys": list(item.get("artifact_keys", [])) if isinstance(item.get("artifact_keys"), list) else [],
        "budget": dict(item.get("budget", {})) if isinstance(item.get("budget"), dict) else {},
    }


def context_source_reason_map(
    *,
    workflow_id: str | None,
    route_rules: list[str],
    selected_tools: list[str],
    query_text: str,
) -> dict[str, list[str]]:
    if workflow_id is None:
        return {}
    text = lower_request(query_text)
    route_rule_set = set(route_rules)
    selected_tool_set = set(selected_tools)
    reasons: dict[str, list[str]] = {source_id: [] for source_id in CONTEXT_SOURCE_CATALOG}

    if "structure_index" in selected_tool_set and workflow_id in {
        "code_context.lookup",
        "code_investigation.plan",
        "execution_planning.plan",
        "refactor.single_path",
    }:
        reasons["ast_index"].append("selected_workflow_uses_structure_index")
    if {"git_grep", "read_file"} & selected_tool_set and workflow_id in {
        "code_context.lookup",
        "code_investigation.plan",
        "execution_planning.plan",
        "refactor.single_path",
    }:
        reasons["text_search"].append("selected_workflow_uses_bounded_text_lookup")
    config_rules = {
        "l1_configuration_lookup_terms",
        "l1_configuration_effect_summary_terms",
        "d1_config_default_test_terms",
    }
    if route_rule_set & config_rules or contains_any(text, ("config", "configuration", "environment variable", "env var", ".env")):
        reasons["config_lookup"].append("configuration_or_environment_request")
    test_rules = {
        "l1_find_related_tests_terms",
        "l1_safe_test_command_terms",
        "l1_test_failure_summary_terms",
        "l1_coverage_gap_summary_terms",
        "l1_small_unit_test_terms",
        "l1_simple_failing_test_fix_terms",
        "l2_failing_test_investigation_terms",
        "l2_test_selection_terms",
        "l2_ci_log_triage_terms",
        "l2_runtime_reproduction_checklist_terms",
        "l2_user_facing_message_test_target_terms",
        "d1_config_default_test_terms",
        "d1_message_assertion_test_terms",
        "d1_test_assertion_update_terms",
    }
    if route_rule_set & test_rules or contains_any(text, ("test", "pytest", "coverage", "verification command", "failing test")):
        reasons["test_lookup"].append("test_or_verification_request")
    relationship_rules = {
        "l1_callers_usages_terms",
        "l1_dependency_import_lookup_terms",
        "l2_dependency_impact_summary_terms",
        "code_context_terms",
    }
    if workflow_id == "code_context.lookup" or route_rule_set & relationship_rules:
        reasons["curated_relationship_lookup"].append("relationship_lookup_request")

    return {source_id: item_reasons for source_id, item_reasons in reasons.items() if item_reasons}


def context_source_selected_tools(source_id: str, selected_tools: list[str]) -> list[str]:
    catalog_tools = source_catalog_item(source_id)["tool_ids"]
    return [tool_id for tool_id in catalog_tools if tool_id in selected_tools]


def context_source_audit(
    *,
    target_root: Path,
    selected_workflow: str | None,
    route_evidence: list[dict[str, Any]],
    selected_tools: list[str],
    query_text: str,
) -> dict[str, Any]:
    route_rules = route_rules_from_evidence(route_evidence)
    reason_map = context_source_reason_map(
        workflow_id=selected_workflow,
        route_rules=route_rules,
        selected_tools=selected_tools,
        query_text=query_text,
    )
    layout = context_layout_summary(target_root)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    gaps: list[str] = []
    for source_id in CONTEXT_SOURCE_CATALOG:
        item = source_catalog_item(source_id)
        selected_tool_ids = context_source_selected_tools(source_id, selected_tools)
        reasons = reason_map.get(source_id, [])
        if reasons and len(selected) < CONTEXT_SOURCE_MAX_SELECTED:
            selected.append(
                {
                    **item,
                    "tool_ids": selected_tool_ids,
                    "status": "selected",
                    "reasons": reasons,
                    "route_rules": route_rules,
                }
            )
            if not selected_tool_ids:
                gaps.append(f"{source_id}: selected by intent but no matching tool is allowed by the selected workflow")
        else:
            reject_reasons = ["no_router_rule_or_workflow_need"]
            if reasons:
                reject_reasons = ["context_source_budget_exhausted"]
            rejected.append({**item, "tool_ids": selected_tool_ids, "status": "rejected", "reasons": reject_reasons})

    if selected_workflow is not None and layout["status"] != "supported":
        gaps.append(f"unsupported_repository_layout:{layout['status']}")
    return {
        "schema_version": SCHEMA_VERSION,
        "selection_policy": {
            "source": "workflow_router.context_source_rules",
            "metadata_only": True,
            "manual_tool_request_required": False,
            "max_selected_sources": CONTEXT_SOURCE_MAX_SELECTED,
            "unsupported_layout_fails_closed": True,
        },
        "selected_source_ids": [item["source_id"] for item in selected],
        "selected": selected,
        "rejected": rejected,
        "layout": layout,
        "budget": {
            "max_selected_sources": CONTEXT_SOURCE_MAX_SELECTED,
            "layout_scan_file_limit": CONTEXT_LAYOUT_MAX_SCANNED_FILES,
            "layout_sample_file_limit": CONTEXT_LAYOUT_MAX_SAMPLE_FILES,
        },
        "evidence_files": layout.get("sample_files", []),
        "gaps": gaps,
    }


def unsupported_context_layout_blockers(audit: dict[str, Any], selected_workflow: str | None) -> list[dict[str, str]]:
    if selected_workflow is None:
        return []
    layout = audit.get("layout") if isinstance(audit.get("layout"), dict) else {}
    if layout.get("status") == "supported":
        return []
    return [
        {
            "reason": "unsupported_repository_layout",
            "message": (
                "The target root does not contain supported source, test, config, or documentation files "
                "within the bounded context layout scan."
            ),
            "next_action": (
                "Point the request at the repository root, add supported source/test/config files, "
                "or provide an explicit supported file path."
            ),
        }
    ]


def confidence_reason_summary(
    *,
    selected_workflow: str | None,
    confidence: str,
    status_reason: str,
    route_evidence: list[dict[str, Any]],
    selected_skills: list[str],
    selected_tools: list[str],
) -> list[str]:
    if selected_workflow is None:
        return [f"blocked:{status_reason}", "no workflow selected"]
    reasons = [f"confidence:{confidence}", f"workflow:{selected_workflow}"]
    route_rules = route_rules_from_evidence(route_evidence)
    if route_rules:
        reasons.append("router_rule_match")
    if selected_skills:
        reasons.append("skill_registry_match")
    if selected_tools:
        reasons.append("workflow_tool_policy_match")
    if confidence_meets_threshold(confidence):
        reasons.append(f"meets_minimum_confidence:{SELECTION_MIN_CONFIDENCE}")
    else:
        reasons.append(f"below_minimum_confidence:{SELECTION_MIN_CONFIDENCE}")
    return reasons


def selection_audit(
    *,
    config_root: Path,
    workflow_registry: dict[str, dict[str, Any]],
    skill_registry: dict[str, dict[str, Any]],
    tool_registry: dict[str, dict[str, Any]],
    selected_workflow: str | None,
    confidence: str,
    status_reason: str,
    route_evidence: list[dict[str, Any]],
    selected_skills: list[str],
    selected_tools: list[str],
    query_text: str,
    skill_limit: int,
) -> dict[str, Any]:
    route_rules = route_rules_from_evidence(route_evidence)
    coverage_matches = prompt_skill_coverage_matches(
        config_root,
        route_rules=route_rules,
        selected_workflow=selected_workflow,
        selected_skills=selected_skills,
        selected_tools=selected_tools,
    )
    confidence_reasons = confidence_reason_summary(
        selected_workflow=selected_workflow,
        confidence=confidence,
        status_reason=status_reason,
        route_evidence=route_evidence,
        selected_skills=selected_skills,
        selected_tools=selected_tools,
    )
    if selected_workflow is not None:
        confidence_reasons.append("prompt_skill_coverage_match" if coverage_matches else "prompt_skill_coverage_missing")
    return {
        "schema_version": SCHEMA_VERSION,
        "selection_policy": {
            "source": "workflow_router.registry_metadata",
            "metadata_only": True,
            "minimum_confidence": SELECTION_MIN_CONFIDENCE,
            "low_confidence_fails_closed": True,
            "manual_skill_injection_required": False,
        },
        "selected": {
            "workflow_id": selected_workflow,
            "confidence": confidence,
            "confidence_reasons": confidence_reasons,
            "route_rules": route_rules,
            "evidence_sources": evidence_sources(route_evidence),
            "coverage_entry_ids": [
                str(item["entry_id"])
                for item in coverage_matches
                if isinstance(item.get("entry_id"), str)
            ],
        },
        "coverage_matches": coverage_matches,
        "workflow_candidates": workflow_candidate_audit(
            workflow_registry,
            selected_workflow=selected_workflow,
            status_reason=status_reason,
            route_evidence=route_evidence,
        ),
        "skill_candidates": skill_candidate_audit(
            skill_registry,
            workflow_id=selected_workflow,
            query_text=query_text,
            selected_skills=selected_skills,
            limit=skill_limit,
        ),
        "tool_candidates": tool_candidate_audit(tool_registry, selected_tools=selected_tools),
    }


def route_request(request: WorkflowRouterPlanRequest, budgets: dict[str, int]) -> dict[str, Any]:
    config_root = Path(request.config_root).resolve()
    workflow_registry = load_workflow_registry(config_root)
    tool_registry = load_tool_registry(config_root)
    skill_registry = load_skill_registry(config_root)

    workflow_id, status_reason, route_evidence = workflow_kind_for_request(request.user_request)
    route_evidence = ensure_supplemental_route_evidence(
        user_request=request.user_request,
        workflow_id=workflow_id,
        evidence=route_evidence,
    )
    if workflow_id is None and budgets["max_model_calls"] > 0:
        model_observation = model_route_observation(
            request,
            workflow_registry,
            deterministic_workflow_id=workflow_id,
            deterministic_status_reason=status_reason,
        )
        route_evidence.append(model_observation)
        if status_reason == "unsupported" and model_observation.get("status") == "accepted":
            route_evidence.append(
                {
                    "source": "model_router",
                    "decision_authority": "advisory_rejected_by_deterministic_router",
                    "selected_workflow": model_observation.get("selected_workflow"),
                    "confidence": model_observation.get("confidence"),
                }
            )
    if workflow_id is None:
        return blocked_decision(
            request,
            route_status="unsupported" if status_reason == "unsupported" else "blocked",
            status_reason=status_reason,
            evidence=route_evidence,
            workflow_registry=workflow_registry,
            skill_registry=skill_registry,
            tool_registry=tool_registry,
        )
    if workflow_id not in workflow_registry:
        return blocked_decision(
            request,
            route_status="blocked",
            status_reason="workflow_not_registered",
            evidence=route_evidence + [{"source": "workflow_registry", "missing_workflow": workflow_id}],
            workflow_registry=workflow_registry,
            skill_registry=skill_registry,
            tool_registry=tool_registry,
        )

    capability_decision = evaluate_model_capability_routing(
        config_root=config_root,
        selected_workflow=workflow_id,
        route_rules=route_rules_from_evidence(route_evidence),
        mode=request.mode,
        approval=request.approval,
        packet_operations=request.packet_operations,
        role_base_url=request.role_base_url,
        model=request.model,
    )
    capability_evidence = {
        "source": "model_capability_routing",
        "status": capability_decision.get("status"),
        "task_class": capability_decision.get("task_class"),
        "task_policy_key": capability_decision.get("task_policy_key"),
        "task_policy_status": capability_decision.get("task_policy_status"),
        "profile_id": capability_decision.get("profile_id"),
        "profile_status": capability_decision.get("profile_status"),
        "enforcement_mode": capability_decision.get("enforcement_mode"),
    }
    capability_blockers = model_capability_blockers(capability_decision)
    if capability_blockers:
        selected_tools: list[str] = []
        selected_skills: list[str] = []
        confidence = "high" if workflow_id == "refactor.single_path" else "medium"
        context_audit = context_source_audit(
            target_root=Path(request.target_root).resolve(),
            selected_workflow=workflow_id,
            route_evidence=route_evidence,
            selected_tools=selected_tools,
            query_text=request.user_request,
        )
        evidence = registry_evidence(workflow_registry, skill_registry, tool_registry) + route_evidence
        evidence.extend(
            [
                {
                    "source": "workflow_registry",
                    "selected_workflow": workflow_id,
                    "description": workflow_registry[workflow_id].get("description"),
                },
                capability_evidence,
            ]
        )
        return {
            "workflow": WORKFLOW_ID,
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "selected_workflow": workflow_id,
            "confidence": confidence,
            "selected_skills": selected_skills,
            "selected_tools": selected_tools,
            "model_capability_routing": capability_decision,
            "selection_audit": selection_audit(
                config_root=config_root,
                workflow_registry=workflow_registry,
                skill_registry=skill_registry,
                tool_registry=tool_registry,
                selected_workflow=workflow_id,
                confidence=confidence,
                status_reason=status_reason,
                route_evidence=route_evidence,
                selected_skills=selected_skills,
                selected_tools=selected_tools,
                query_text=request.user_request,
                skill_limit=budgets["max_selected_skills"],
            ),
            "context_source_audit": context_audit,
            "selected_context_sources": context_audit["selected_source_ids"],
            "approval_required_before": approval_required_before(workflow_id),
            "controller_request_preview": {},
            "evidence": evidence,
            "blockers": capability_blockers,
            "next_action": "run_model_portability_gate",
        }

    if budgets["max_model_calls"] > 0:
        model_observation = model_route_observation(
            request,
            workflow_registry,
            deterministic_workflow_id=workflow_id,
            deterministic_status_reason=status_reason,
        )
        route_evidence.append(model_observation)
        if workflow_id is None and status_reason == "unsupported" and model_observation.get("status") == "accepted":
            route_evidence.append(
                {
                    "source": "model_router",
                    "decision_authority": "advisory_rejected_by_deterministic_router",
                    "selected_workflow": model_observation.get("selected_workflow"),
                    "confidence": model_observation.get("confidence"),
                }
            )

    selected_tools = tools_for_workflow(workflow_id, workflow_registry, budgets["max_selected_tools"])
    selected_skills = skills_for_workflow(
        workflow_id,
        skill_registry,
        user_request=request.user_request,
        limit=budgets["max_selected_skills"],
    )
    selected_skills = apply_router_rule_skill_overrides(
        selected_skills,
        workflow_id=workflow_id,
        skill_registry=skill_registry,
        route_evidence=route_evidence,
        limit=budgets["max_selected_skills"],
    )
    evidence = registry_evidence(workflow_registry, skill_registry, tool_registry) + route_evidence
    evidence.append(
        {
            "source": "workflow_registry",
            "selected_workflow": workflow_id,
            "description": workflow_registry[workflow_id].get("description"),
        }
    )
    if any(item.get("source") == "model_router" and item.get("status") == "accepted" for item in route_evidence):
        evidence.append({"source": "model_router", "decision_authority": "advisory_schema_validated"})
    if selected_skills:
        evidence.append(
            {
                "source": "skill_registry",
                "selection_basis": "capability_contract_shortlist",
                "selected_skills": selected_skills,
                "capability_route_keys": selected_skill_capability_route_keys(skill_registry, selected_skills),
            }
        )
    evidence.append(capability_evidence)
    confidence = "high" if workflow_id == "refactor.single_path" else "medium"
    blockers: list[dict[str, Any]] = []
    status = "ready"
    next_action = next_action_for(workflow_id)
    readiness_blocker, readiness_decision = advanced_refactor_readiness_blocker(
        config_root=config_root,
        workflow_id=workflow_id,
        route_evidence=route_evidence,
        user_request=request.user_request,
    )
    if readiness_decision is not None:
        evidence.append(
            {
                "source": "advanced_refactor_readiness_gate",
                "status": readiness_decision.get("status"),
                "readiness_status": readiness_decision.get("readiness_status"),
                "report_path": readiness_decision.get("report_path"),
                "reason": readiness_decision.get("reason"),
            }
        )
    if readiness_blocker is not None:
        blockers.append(readiness_blocker)
    context_audit = context_source_audit(
        target_root=Path(request.target_root).resolve(),
        selected_workflow=workflow_id,
        route_evidence=route_evidence,
        selected_tools=selected_tools,
        query_text=request.user_request,
    )
    blockers.extend(unsupported_context_layout_blockers(context_audit, workflow_id))
    if blockers:
        status = "blocked"
        next_action = "none" if readiness_blocker is not None else "ask_blocking_question"
    if not confidence_meets_threshold(confidence):
        status = "blocked"
        next_action = "ask_blocking_question"
        blockers.append(
            {
                "reason": "low_selection_confidence",
                "message": f"Selection confidence {confidence!r} is below the configured threshold {SELECTION_MIN_CONFIDENCE!r}.",
            }
        )
    approval_requirements = [] if readiness_blocker is not None else approval_required_before(workflow_id)
    return {
        "workflow": WORKFLOW_ID,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "selected_workflow": workflow_id,
        "confidence": confidence,
        "selected_skills": selected_skills,
        "selected_tools": selected_tools,
        "model_capability_routing": capability_decision,
        "selection_audit": selection_audit(
            config_root=config_root,
            workflow_registry=workflow_registry,
            skill_registry=skill_registry,
            tool_registry=tool_registry,
            selected_workflow=workflow_id,
            confidence=confidence,
            status_reason=status_reason,
            route_evidence=route_evidence,
            selected_skills=selected_skills,
            selected_tools=selected_tools,
            query_text=request.user_request,
            skill_limit=budgets["max_selected_skills"],
        ),
        "context_source_audit": context_audit,
        "selected_context_sources": context_audit["selected_source_ids"],
        "approval_required_before": approval_requirements,
        "controller_request_preview": (
            request_preview(workflow_id, request, selected_tools, context_audit["selected_source_ids"])
            if not blockers
            else {}
        ),
        "evidence": evidence,
        "blockers": blockers,
        "next_action": next_action,
    }


def registry_snapshot(config_root: Path) -> dict[str, Any]:
    workflow_registry = load_workflow_registry(config_root)
    tool_registry = load_tool_registry(config_root)
    skill_registry = load_skill_registry(config_root)
    return {
        "kind": "workflow_router_registry_snapshot",
        "schema_version": SCHEMA_VERSION,
        "workflow_count": len(workflow_registry),
        "tool_count": len(tool_registry),
        "skill_count": len(skill_registry),
        "workflows": workflow_registry,
        "tools": tool_registry,
        "skills": skill_registry,
    }


def invoke_workflow_router_plan(request: WorkflowRouterPlanRequest) -> InvocationResult:
    validation = validate_request_basics(request)
    target_root = Path(request.target_root).resolve()
    output_root = Path(request.output_root).resolve()
    config_root = Path(request.config_root).resolve()
    run_id = f"workflow-router-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    request_artifact = {
        "kind": "workflow_router_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(target_root),
        "mode": request.mode,
        "user_request": request.user_request,
        "budgets": validation["budgets"],
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)

    snapshot = registry_snapshot(config_root)
    write_json(run_dir / "registry-snapshot.json", snapshot)

    decision = route_request(request, validation["budgets"])
    decision = {
        "kind": "workflow_router_decision",
        "run_id": run_id,
        "target_root": str(target_root),
        "created_at": utc_now(),
        **decision,
    }

    downstream_result: InvocationResult | None = None
    downstream_tool_policy: dict[str, Any] | None = None
    downstream_failures: list[dict[str, Any]] = []
    if request.mode == "execute_read_only" and decision["status"] == "ready":
        selected_workflow = decision.get("selected_workflow")
        if selected_workflow not in READ_ONLY_WORKFLOWS:
            decision["status"] = "blocked"
            decision["blockers"].append(
                {
                    "reason": "read_only_workflow_required",
                    "message": "execute_read_only supports only read-only investigation and lookup workflows.",
                }
            )
            decision["next_action"] = "request_approval" if selected_workflow == "execution_planning.plan" else "none"
        else:
            try:
                downstream_result, downstream_tool_policy = invoke_downstream_read_only(request, decision, run_dir)
            except (
                CodeContextLookupError,
                CodeInvestigationError,
                RefactorSinglePathError,
                SkillBatchProposalError,
                TaskDecompositionError,
            ) as exc:
                raise WorkflowRouterError(
                    f"Downstream artifact-only workflow failed: {exc}",
                    code=f"downstream_{exc.code}",
                    status=exc.status,
                ) from exc
            decision["downstream"] = {
                "workflow": downstream_result.workflow,
                "run_id": downstream_result.run_id,
                "status": downstream_result.status.value,
                "artifacts": downstream_result.artifact_paths,
                "tool_policy": downstream_tool_policy,
            }
            if selected_workflow == "refactor.single_path" and downstream_result.status == WorkflowStatus.COMPLETED:
                decision["next_action"] = "request_approval"
            downstream_failures = downstream_result.failures
    if request.mode == "implementation_prep" and decision["status"] == "ready":
        implementation_request = request
        proposal: dict[str, Any] | None = None
        small_text_edit_proposal: dict[str, Any] | None = None
        small_unit_test_proposal: dict[str, Any] | None = None
        simple_test_fix_proposal: dict[str, Any] | None = None
        packet_objective = packet_objective_from_context(request.context)
        if packet_objective:
            decision["packet_objective"] = {
                "status": "accepted",
                "objective": packet_objective,
            }
        narrowed_objective = narrowed_edit_objective_from_context(request.context)
        if narrowed_objective:
            decision["narrowed_edit_objective"] = {
                "status": "accepted",
                "objective": narrowed_objective,
            }
        proposal_path = run_dir / "packet-operation-proposal.json"
        use_prior_run_packet_proposal = approved_run_id_from_context(request.context) is not None
        if not request.packet_operations and not use_prior_run_packet_proposal:
            proposed_operations, small_text_edit_proposal = small_text_edit_packet_operations(request, run_dir)
            if small_text_edit_proposal is not None:
                decision["small_text_edit"] = {
                    "status": small_text_edit_proposal.get("status"),
                    "path": small_text_edit_proposal.get("instruction", {}).get("path")
                    if isinstance(small_text_edit_proposal.get("instruction"), dict)
                    else None,
                    "packet_operation_count": len(proposed_operations),
                    "blockers": small_text_edit_proposal.get("blockers", []),
                    "artifact": str(run_dir / "small-text-edit-proposal.json"),
                }
                if proposed_operations:
                    implementation_request = replace(request, packet_operations=proposed_operations)
                    preview = decision.get("controller_request_preview")
                    if isinstance(preview, dict):
                        preview["packet_operations"] = proposed_operations
                    decision["evidence"].append(
                        {
                            "source": "small_text_edit_proposal",
                            "status": "ready",
                            "artifact": str(run_dir / "small-text-edit-proposal.json"),
                            "packet_operation_count": len(proposed_operations),
                        }
                    )
        if not implementation_request.packet_operations and not use_prior_run_packet_proposal:
            proposed_operations, simple_test_fix_proposal = simple_test_fix_packet_operations(request, run_dir)
            if simple_test_fix_proposal is not None:
                decision["simple_test_fix"] = {
                    "status": simple_test_fix_proposal.get("status"),
                    "failed_test": simple_test_fix_proposal.get("failed_test"),
                    "packet_operation_count": len(proposed_operations),
                    "blockers": simple_test_fix_proposal.get("blockers", []),
                    "artifact": str(run_dir / "simple-test-fix-proposal.json"),
                }
                if proposed_operations:
                    implementation_request = replace(request, packet_operations=proposed_operations)
                    preview = decision.get("controller_request_preview")
                    if isinstance(preview, dict):
                        preview["packet_operations"] = proposed_operations
                    decision["evidence"].append(
                        {
                            "source": "simple_test_fix_proposal",
                            "status": "ready",
                            "artifact": str(run_dir / "simple-test-fix-proposal.json"),
                            "packet_operation_count": len(proposed_operations),
                        }
                    )
        if (
            not implementation_request.packet_operations
            and simple_test_fix_proposal is None
            and not use_prior_run_packet_proposal
        ):
            proposed_operations, small_unit_test_proposal = small_unit_test_packet_operations(request, run_dir)
            if small_unit_test_proposal is not None:
                decision["small_unit_test"] = {
                    "status": small_unit_test_proposal.get("status"),
                    "subkind": small_unit_test_proposal.get("subkind"),
                    "path": small_unit_test_proposal.get("candidate_test_file", {}).get("path")
                    if isinstance(small_unit_test_proposal.get("candidate_test_file"), dict)
                    else None,
                    "packet_operation_count": len(proposed_operations),
                    "blockers": small_unit_test_proposal.get("blockers", []),
                    "artifact": str(run_dir / "small-unit-test-proposal.json"),
                }
                if proposed_operations:
                    implementation_request = replace(request, packet_operations=proposed_operations)
                    preview = decision.get("controller_request_preview")
                    if isinstance(preview, dict):
                        preview["packet_operations"] = proposed_operations
                    decision["evidence"].append(
                        {
                            "source": "small_unit_test_proposal",
                            "status": "ready",
                            "artifact": str(run_dir / "small-unit-test-proposal.json"),
                            "packet_operation_count": len(proposed_operations),
                        }
                    )
        if (
            not implementation_request.packet_operations
            and (
                use_prior_run_packet_proposal
                or (
                    small_text_edit_proposal is None
                    and small_unit_test_proposal is None
                    and simple_test_fix_proposal is None
                )
            )
        ):
            proposed_operations, proposal = propose_packet_operations_from_prior_run(request, run_dir)
            decision["packet_operation_proposal"] = {
                "status": proposal.get("status"),
                "approved_run_id": proposal.get("approved_run_id"),
                "source_artifact_key": proposal.get("source_artifact_key"),
                "packet_operation_count": len(proposed_operations),
                "rejected_operation_count": len(proposal.get("rejected_operations") or []),
                "blockers": proposal.get("blockers", []),
                "artifact": str(proposal_path),
            }
            if proposed_operations:
                implementation_request = replace(request, packet_operations=proposed_operations)
                preview = decision.get("controller_request_preview")
                if isinstance(preview, dict):
                    preview["packet_operations"] = proposed_operations
                decision["evidence"].append(
                    {
                        "source": "packet_operation_proposal",
                        "status": "ready",
                        "artifact": str(proposal_path),
                        "packet_operation_count": len(proposed_operations),
                    }
                )
        objective_outcome: dict[str, Any] | None = None
        if proposal is not None and not implementation_request.packet_operations:
            objective_outcome = packet_objective_outcome(request, proposal)
            if objective_outcome is not None:
                decision["packet_objective_outcome"] = objective_outcome
                if objective_outcome["status"] == "no_change_needed":
                    proposal["status"] = "not_required"
                    proposal["packet_objective_outcome"] = objective_outcome
                    write_json(proposal_path, proposal)
                    if isinstance(decision.get("packet_operation_proposal"), dict):
                        decision["packet_operation_proposal"]["status"] = "not_required"
                    decision["next_action"] = "none"
                    decision["implementation_prep"] = {
                        "workflow": "execution_planning.plan",
                        "mode": "dry_run",
                        "status": "not_required",
                        "reason": objective_outcome["reason"],
                        "apply_allowed": False,
                    }
                    decision["evidence"].append(
                        {
                            "source": "packet_objective_outcome",
                            "status": "no_change_needed",
                            "evidence_refs": objective_outcome.get("evidence_refs", []),
                        }
                    )
        blockers = [] if objective_outcome and objective_outcome["status"] == "no_change_needed" else implementation_prep_blockers(implementation_request)
        if blockers:
            decision["status"] = "blocked"
            decision["blockers"].extend(blockers)
            if small_text_edit_proposal is not None and not implementation_request.packet_operations:
                decision["next_action"] = "request_exact_text_edit_details"
            elif small_unit_test_proposal is not None and not implementation_request.packet_operations:
                decision["next_action"] = "request_exact_unit_test_details"
            elif simple_test_fix_proposal is not None and not implementation_request.packet_operations:
                decision["next_action"] = "request_exact_simple_test_fix_details"
            elif proposal is not None and not implementation_request.packet_operations:
                if objective_outcome and objective_outcome["status"] == "needs_narrowed_edit_objective":
                    decision["next_action"] = "request_narrowed_edit_objective"
                else:
                    decision["next_action"] = "request_packet_objective"
                decision["packet_objective_clarification"] = packet_objective_clarification(proposal)
            else:
                decision["next_action"] = "request_approval"
        elif not (objective_outcome and objective_outcome["status"] == "no_change_needed"):
            try:
                downstream_result, downstream_tool_policy = invoke_downstream_implementation_prep(
                    implementation_request, decision, run_dir
                )
            except ExecutionPlanningWorkflowError as exc:
                failure = {
                    "failed_at": utc_now(),
                    "reason": "downstream_implementation_prep_failed",
                    "code": exc.code,
                    "message": bounded_string(exc, 500),
                }
                failure.update(exc.details)
                decision["status"] = "blocked"
                decision["next_action"] = "retry_execution_planning"
                decision["blockers"].append(failure)
                decision["implementation_prep"] = {
                    "workflow": "execution_planning.plan",
                    "mode": "dry_run",
                    "status": WorkflowStatus.FAILED.value,
                    "reason": str(exc),
                    "code": exc.code,
                    "failed_skill": exc.details.get("failed_skill"),
                    "retry_guidance": exc.details.get("retry_guidance"),
                    "apply_allowed": False,
                }
                decision["downstream"] = decision["implementation_prep"]
                downstream_failures = [failure]
            else:
                decision["next_action"] = "none"
                decision["implementation_prep"] = {
                    "workflow": downstream_result.workflow,
                    "mode": "dry_run",
                    "run_id": downstream_result.run_id,
                    "status": downstream_result.status.value,
                    "artifacts": downstream_result.artifact_paths,
                    "tool_policy": downstream_tool_policy,
                    "apply_allowed": False,
                }
                decision["downstream"] = decision["implementation_prep"]
                downstream_failures = downstream_result.failures
    if request.mode == "apply_disposable_copy" and decision["status"] == "ready":
        blockers = disposable_apply_blockers(request)
        if blockers:
            decision["status"] = "blocked"
            decision["blockers"].extend(blockers)
            decision["next_action"] = "request_approval"
        else:
            try:
                downstream_result, mutation_proof = invoke_disposable_copy_apply(request, run_dir)
            except ImplementationWorkflowError as exc:
                raise WorkflowRouterError(
                    f"Disposable-copy implementation apply failed: {exc}",
                    code="downstream_implementation_apply_failed",
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                ) from exc
            decision["next_action"] = "none"
            decision["disposable_apply"] = {
                "workflow": downstream_result.workflow,
                "mode": "apply",
                "run_id": downstream_result.run_id,
                "status": downstream_result.status.value,
                "artifacts": downstream_result.artifact_paths,
                "mutation_proof": mutation_proof,
            }
            decision["downstream"] = decision["disposable_apply"]
            downstream_failures = downstream_result.failures

    if is_advanced_refactor_readiness_blocked(decision):
        approval_state = {
            "kind": "workflow_router_approval_state",
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "target_root": str(target_root),
            "mode": request.mode,
            "selected_workflow": decision.get("selected_workflow"),
            "route_status": decision.get("status"),
            "status": "not_created",
            "approval_type": "none",
            "approval_status": "not_required",
            "expected_approval": None,
            "received_approval": None,
            "source_run_id": None,
            "next_action": decision.get("next_action"),
            "next_action_text": "Advanced refactor approval is blocked until the Phase 105 readiness gate admits this pilot.",
            "blockers": decision.get("blockers") if isinstance(decision.get("blockers"), list) else [],
            "created_at": utc_now(),
            "artifact": None,
        }
    else:
        approval_state = build_workflow_router_approval_state(
            request=request,
            decision=decision,
            run_id=run_id,
            target_root=target_root,
            run_dir=run_dir,
        )
    decision["approval_state"] = approval_state
    context_source_audit_record = (
        decision.get("context_source_audit") if isinstance(decision.get("context_source_audit"), dict) else None
    )
    if context_source_audit_record is not None:
        context_source_audit_path = run_dir / "context-source-audit.json"
        write_json(context_source_audit_path, context_source_audit_record)
        context_source_audit_record["artifact"] = str(context_source_audit_path)
    write_json(run_dir / "route-decision.json", decision)
    model_evidence = [
        item
        for item in decision["evidence"]
        if item.get("source") == "model_router" and isinstance(item.get("status"), str)
    ]
    downstream_report_summary = (
        downstream_result.report.get("summary")
        if downstream_result is not None
        and isinstance(downstream_result.report, dict)
        and isinstance(downstream_result.report.get("summary"), dict)
        else {}
    )
    decision_downstream = decision.get("downstream") if isinstance(decision.get("downstream"), dict) else {}
    mutation_proof = (
        decision.get("disposable_apply", {}).get("mutation_proof", {})
        if isinstance(decision.get("disposable_apply"), dict)
        else {}
    )
    mutation_structured_diff = (
        mutation_proof.get("structured_diff") if isinstance(mutation_proof.get("structured_diff"), dict) else {}
    )
    mutation_diff_records = (
        mutation_structured_diff.get("records") if isinstance(mutation_structured_diff.get("records"), list) else []
    )
    mutation_diff_paths = [
        record.get("path")
        for record in mutation_diff_records
        if isinstance(record, dict) and isinstance(record.get("path"), str) and record.get("status") == "changed"
    ]
    mutation_operation_kinds = [
        record.get("operation_kind")
        for record in mutation_diff_records
        if isinstance(record, dict) and isinstance(record.get("operation_kind"), str)
    ]
    capability_routing_summary = (
        decision.get("model_capability_routing")
        if isinstance(decision.get("model_capability_routing"), dict)
        else {}
    )
    context_source_audit_summary = (
        decision.get("context_source_audit") if isinstance(decision.get("context_source_audit"), dict) else {}
    )
    context_layout_summary_record = (
        context_source_audit_summary.get("layout")
        if isinstance(context_source_audit_summary.get("layout"), dict)
        else {}
    )
    summary = {
        "target_root": str(target_root),
        "route_status": decision["status"],
        "selected_workflow": decision["selected_workflow"],
        "confidence": decision["confidence"],
        "selected_skill_count": len(decision["selected_skills"]),
        "selected_tool_count": len(decision["selected_tools"]),
        "selected_context_sources": decision.get("selected_context_sources", []),
        "context_layout_status": context_layout_summary_record.get("status"),
        "context_gap_count": len(context_source_audit_summary.get("gaps", []))
        if isinstance(context_source_audit_summary.get("gaps"), list)
        else 0,
        "next_action": decision["next_action"],
        "blocker_count": len(decision["blockers"]),
        "plan_only": request.mode == "plan_only",
        "target_repo_read": downstream_result is not None or bool(decision_downstream),
        "model_router_status": model_evidence[-1].get("status") if model_evidence else "not_requested",
        "model_capability_status": capability_routing_summary.get("status"),
        "model_capability_task_class": capability_routing_summary.get("task_class"),
        "model_capability_profile_id": capability_routing_summary.get("profile_id"),
        "model_capability_policy_status": capability_routing_summary.get("task_policy_status"),
        "downstream_workflow": (
            downstream_result.workflow if downstream_result is not None else decision_downstream.get("workflow")
        ),
        "downstream_run_id": (
            downstream_result.run_id if downstream_result is not None else decision_downstream.get("run_id")
        ),
        "downstream_status": (
            downstream_result.status.value if downstream_result is not None else decision_downstream.get("status")
        ),
        "packet_objective_outcome_status": (
            decision.get("packet_objective_outcome", {}).get("status")
            if isinstance(decision.get("packet_objective_outcome"), dict)
            else None
        ),
        "narrowed_edit_objective_status": (
            decision.get("narrowed_edit_objective", {}).get("status")
            if isinstance(decision.get("narrowed_edit_objective"), dict)
            else None
        ),
        "verification_command_count": downstream_report_summary.get("verification_command_count", 0),
        "source_changed": bool(mutation_proof.get("source_changed", {})),
        "source_tree_changed": mutation_proof.get("source_tree_changed"),
        "disposable_copy_changed": bool(mutation_proof.get("copy_changed", {})),
        "copy_tree_restored": mutation_proof.get("copy_tree_restored"),
        "mutation_sandbox_status": (
            mutation_proof.get("sandbox_contract", {}).get("status")
            if isinstance(mutation_proof.get("sandbox_contract"), dict)
            else None
        ),
        "mutation_diff_file_count": mutation_structured_diff.get("changed_file_count", 0),
        "mutation_diff_paths": mutation_diff_paths[:5],
        "mutation_operation_kinds": mutation_operation_kinds[:5],
        "mutation_rollback_status": (
            mutation_proof.get("rollback", {}).get("status")
            if isinstance(mutation_proof.get("rollback"), dict)
            else None
        ),
        "approval_state_status": approval_state.get("status"),
        "approval_state_next_action": approval_state.get("next_action_text"),
        "approval_type": approval_state.get("approval_type"),
    }
    artifacts = {
        "request": str(run_dir / "request.json"),
        "registry_snapshot": str(run_dir / "registry-snapshot.json"),
        "route_decision": str(run_dir / "route-decision.json"),
    }
    if approval_state.get("artifact"):
        artifacts["approval_state"] = str(approval_state["artifact"])
    if (run_dir / "context-source-audit.json").exists():
        artifacts["context_source_audit"] = str(run_dir / "context-source-audit.json")
    proposal_artifact_path = run_dir / "packet-operation-proposal.json"
    if proposal_artifact_path.exists():
        artifacts["packet_operation_proposal"] = str(proposal_artifact_path)
    proposal_request_path = run_dir / "packet-operation-proposal-request.json"
    if proposal_request_path.exists():
        artifacts["packet_operation_proposal_request"] = str(proposal_request_path)
    small_text_edit_path = run_dir / "small-text-edit-proposal.json"
    if small_text_edit_path.exists():
        artifacts["small_text_edit_proposal"] = str(small_text_edit_path)
    small_unit_test_path = run_dir / "small-unit-test-proposal.json"
    if small_unit_test_path.exists():
        artifacts["small_unit_test_proposal"] = str(small_unit_test_path)
    simple_test_fix_path = run_dir / "simple-test-fix-proposal.json"
    if simple_test_fix_path.exists():
        artifacts["simple_test_fix_proposal"] = str(simple_test_fix_path)
    if downstream_result is not None:
        downstream_result_path = run_dir / "downstream-result.json"
        write_json(downstream_result_path, downstream_result.to_dict(include_report=True))
        artifacts["downstream_result"] = str(downstream_result_path)
        artifacts.update(prefixed_artifacts("downstream", downstream_result.artifact_paths))
    for artifact_key, artifact_path in (
        ("disposable_mutation_sandbox_contract", run_dir / "disposable-mutation-sandbox-contract.json"),
        ("disposable_mutation_diff", run_dir / "disposable-mutation-diff.json"),
        ("disposable_mutation_proof", run_dir / "disposable-mutation-proof.json"),
        ("disposable_rollback_proof", run_dir / "disposable-rollback-proof.json"),
    ):
        if artifact_path.exists():
            artifacts[artifact_key] = str(artifact_path)
    run_state = {
        "kind": "workflow_router_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")
    report = {
        "kind": "workflow_router_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "decision": decision,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed: {summary['route_status']} -> {summary['selected_workflow']}",
        failures=downstream_failures,
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
