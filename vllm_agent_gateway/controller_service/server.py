"""Local HTTP controller service.

This service exposes explicit workflow endpoints. It is intentionally separate
from role prompt proxy ports so ordinary chat requests do not silently become
stateful repo workflows.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
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
from vllm_agent_gateway.controllers.execution_planning.workflow import (
    WORKFLOW_ID as EXECUTION_PLANNING_WORKFLOW_ID,
    ExecutionPlanningInvocationRequest,
    ExecutionPlanningWorkflowError,
    invoke_execution_planning,
)
from vllm_agent_gateway.controllers.code_context.lookup import (
    WORKFLOW_ID as CODE_CONTEXT_LOOKUP_WORKFLOW_ID,
    CodeContextLookupError,
    CodeContextLookupRequest,
    invoke_code_context_lookup,
)
from vllm_agent_gateway.controllers.code_investigation.plan import (
    WORKFLOW_ID as CODE_INVESTIGATION_WORKFLOW_ID,
    CodeInvestigationError,
    CodeInvestigationRequest,
    invoke_code_investigation,
)
from vllm_agent_gateway.controllers.refactor.single_path import (
    WORKFLOW_ID as REFACTOR_SINGLE_PATH_WORKFLOW_ID,
    RefactorSinglePathError,
    RefactorSinglePathRequest,
    invoke_refactor_single_path,
)
from vllm_agent_gateway.controllers.workflow_feedback.record import (
    WORKFLOW_ID as WORKFLOW_FEEDBACK_WORKFLOW_ID,
    WorkflowFeedbackError,
    WorkflowFeedbackRecordRequest,
    invoke_workflow_feedback_record,
)
from vllm_agent_gateway.controllers.skill_batch.propose import (
    WORKFLOW_ID as SKILL_BATCH_PROPOSAL_WORKFLOW_ID,
    SkillBatchProposalError,
    SkillBatchProposalRequest,
    invoke_skill_batch_proposal,
)
from vllm_agent_gateway.controllers.skill_batch.register import (
    WORKFLOW_ID as SKILL_BATCH_REGISTRATION_WORKFLOW_ID,
    SkillBatchRegistrationError,
    SkillBatchRegistrationRequest,
    invoke_skill_batch_registration,
)
from vllm_agent_gateway.controllers.skill_eval.promote import (
    WORKFLOW_ID as SKILL_EVAL_PROMOTION_WORKFLOW_ID,
    SkillEvalPromotionError,
    SkillEvalPromotionRequest,
    invoke_skill_eval_promotion,
)
from vllm_agent_gateway.controllers.skill_lifecycle.audit import (
    WORKFLOW_ID as SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID,
    SkillLifecycleAuditError,
    SkillLifecycleAuditRequest,
    invoke_skill_lifecycle_audit,
)
from vllm_agent_gateway.controllers.skill_deprecation.deprecate import (
    WORKFLOW_ID as SKILL_DEPRECATION_WORKFLOW_ID,
    SkillDeprecationError,
    SkillDeprecationRequest,
    invoke_skill_deprecation,
)
from vllm_agent_gateway.controllers.skill_update.update import (
    WORKFLOW_ID as SKILL_UPDATE_WORKFLOW_ID,
    SkillUpdateError,
    SkillUpdateRequest,
    invoke_skill_update,
)
from vllm_agent_gateway.controllers.skill_selection.explain import (
    WORKFLOW_ID as SKILL_SELECTION_EXPLAIN_WORKFLOW_ID,
    SkillSelectionExplainError,
    SkillSelectionExplainRequest,
    invoke_skill_selection_explain,
)
from vllm_agent_gateway.controllers.skill_pack.validate import (
    WORKFLOW_ID as SKILL_PACK_VALIDATION_WORKFLOW_ID,
    SkillPackValidationError,
    SkillPackValidationRequest,
    invoke_skill_pack_validation,
)
from vllm_agent_gateway.controllers.skill_pack.install import (
    WORKFLOW_ID as SKILL_PACK_INSTALL_WORKFLOW_ID,
    SkillPackInstallError,
    SkillPackInstallRequest,
    invoke_skill_pack_install,
)
from vllm_agent_gateway.controllers.skill_scaffold.scaffold import (
    WORKFLOW_ID as SKILL_SCAFFOLD_WORKFLOW_ID,
    SkillScaffoldError,
    SkillScaffoldRequest,
    invoke_skill_scaffold,
)
from vllm_agent_gateway.controllers.tool_catalog.validate import (
    WORKFLOW_ID as TOOL_CATALOG_VALIDATION_WORKFLOW_ID,
    ToolCatalogValidationError,
    ToolCatalogValidationRequest,
    invoke_tool_catalog_validation,
)
from vllm_agent_gateway.controllers.tool_catalog.register import (
    WORKFLOW_ID as TOOL_CATALOG_REGISTRATION_WORKFLOW_ID,
    ToolCatalogRegistrationError,
    ToolCatalogRegistrationRequest,
    invoke_tool_catalog_registration,
)
from vllm_agent_gateway.controllers.task_decompose.decompose import (
    WORKFLOW_ID as TASK_DECOMPOSITION_WORKFLOW_ID,
    TaskDecompositionError,
    TaskDecompositionRequest,
    invoke_task_decomposition,
)
from vllm_agent_gateway.controllers.workflow_router.plan import (
    WORKFLOW_ID as WORKFLOW_ROUTER_WORKFLOW_ID,
    DEFAULT_ROLE_ID as WORKFLOW_ROUTER_DEFAULT_ROLE_ID,
    WorkflowRouterError,
    WorkflowRouterPlanRequest,
    extract_simple_test_fix_instruction,
    extract_small_unit_test_instruction,
    extract_small_text_edit_instruction,
    is_l1_simple_failing_test_fix_request,
    is_l1_small_unit_test_request,
    is_l1_small_text_edit_request,
    is_large_context_read_only_request,
    is_task_decomposition_request,
    is_skill_batch_proposal_request,
    invoke_workflow_router_plan,
    workflow_kind_for_request,
)
from vllm_agent_gateway.implementation.workflow import (
    ImplementationWorkflowError,
    ImplementationWorkflowInvocationRequest,
    invoke_implementation_workflow,
)
from vllm_agent_gateway.controller_envelope import (
    ControllerEnvelopeError,
    select_latest_controller_envelope,
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
WORKFLOW_ROUTER_CHAT_COMPLETIONS_PATH = "/v1/controller/workflow-router/chat/completions"
EXECUTION_PLANNING_PATH = "/v1/controller/execution-planning/plans"
CODE_CONTEXT_LOOKUP_PATH = "/v1/controller/code-context/lookups"
CODE_INVESTIGATION_PATH = "/v1/controller/code-investigation/plans"
REFACTOR_SINGLE_PATH = "/v1/controller/refactor/single-path"
WORKFLOW_FEEDBACK_PATH = "/v1/controller/workflow-feedback/records"
SKILL_BATCH_PROPOSAL_PATH = "/v1/controller/skill-batch/proposals"
SKILL_BATCH_REGISTRATION_PATH = "/v1/controller/skill-batch/registrations"
SKILL_EVAL_PROMOTION_PATH = "/v1/controller/skill-evals/promotions"
SKILL_LIFECYCLE_AUDIT_PATH = "/v1/controller/skill-lifecycle/audits"
SKILL_DEPRECATION_PATH = "/v1/controller/skill-deprecations"
SKILL_UPDATE_PATH = "/v1/controller/skill-updates"
SKILL_SELECTION_EXPLAIN_PATH = "/v1/controller/skill-selection/explanations"
SKILL_PACK_VALIDATION_PATH = "/v1/controller/skill-packs/validations"
SKILL_PACK_INSTALL_PATH = "/v1/controller/skill-packs/installations"
SKILL_SCAFFOLD_PATH = "/v1/controller/skill-scaffolds"
TOOL_CATALOG_VALIDATION_PATH = "/v1/controller/tool-catalog/validations"
TOOL_CATALOG_REGISTRATION_PATH = "/v1/controller/tool-catalog/registrations"
TASK_DECOMPOSITION_PATH = "/v1/controller/task-decompositions"
IMPLEMENTATION_WORKFLOW_ID = "implementation.workflow"
IMPLEMENTATION_WORKFLOW_PATH = "/v1/controller/implementation-runs"
WORKFLOW_ROUTER_PLAN_PATH = "/v1/controller/workflow-router/plans"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
RUN_ID_IN_TEXT_RE = re.compile(r"\b(?P<run_id>[A-Za-z][A-Za-z0-9_.:-]*-\d{8}T\d{12}Z)\b")
POSIX_TARGET_RE = re.compile(r"(?P<path>/(?:mnt|home|tmp|var|opt|workspace|repo|repos|[A-Za-z0-9._-]+)(?:/[^\s,;:'\"`<>]+)+)")
WINDOWS_TARGET_RE = re.compile(r"(?P<path>[A-Za-z]:[\\/][^\s,;:'\"`<>]+(?:[\\/][^\s,;:'\"`<>]+)*)")
TERMINAL_STATUSES = {"completed", "failed", "canceled"}
RUN_RECORD_VISIBILITY_RETRIES = 20
RUN_RECORD_VISIBILITY_SLEEP_SECONDS = 0.01
RUN_RECORD_CACHE_LOCK = threading.Lock()
RUN_RECORD_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
NATURAL_IMPLEMENTATION_PREP_EXECUTION_BUDGETS = {
    "max_context_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "max_model_calls": 10,
    "max_output_tokens": 2400,
    "timeout_seconds": 45,
}
APPROVAL_CONTINUATION_TTL_SECONDS = 24 * 60 * 60
NATURAL_LIFECYCLE_APPROVAL_REQUIRED_WORKFLOW = "__natural_lifecycle_approval_required__"
NATURAL_LIFECYCLE_APPROVAL_REQUIRED_DIR = "skill-lifecycle-approval-required"
NATURAL_ROUTE_DECISION_DIR = "workflow-router-natural-route-decisions"
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
    "parallelism",
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
DOCUMENT_REVIEW_BUDGET_FIELDS = {"max_chunks", "parallelism", "stop_after_chunks"}
EXECUTION_PLANNING_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "user_request",
    "mode",
    "skill_chain",
    "approval",
    "context",
    "packet_operations",
    "budgets",
    "output",
    "feedback",
    "role_id",
    "role_base_url",
    "model",
}
EXECUTION_PLANNING_BUDGET_FIELDS = {
    "max_context_requests",
    "max_files",
    "max_records",
    "max_model_calls",
    "max_output_tokens",
    "timeout_seconds",
}
CODE_CONTEXT_LOOKUP_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "query",
    "paths",
    "allowed_context_tools",
    "max_results",
    "max_files",
    "include_structure",
    "include_grep",
    "include_file_snippets",
    "relationship_queries",
    "role_id",
}
CODE_INVESTIGATION_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "user_request",
    "behavior",
    "entrypoint_hints",
    "queries",
    "paths",
    "allowed_context_tools",
    "max_results",
    "max_files",
    "include_tests",
    "include_structure",
    "include_grep",
    "include_file_snippets",
    "role_id",
}
REFACTOR_SINGLE_PATH_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "user_request",
    "behavior",
    "mode",
    "entrypoint_hints",
    "queries",
    "paths",
    "allowed_context_tools",
    "max_results",
    "max_files",
    "approval",
    "packet_operations",
    "budgets",
    "feedback",
    "role_id",
    "role_base_url",
    "model",
}
WORKFLOW_FEEDBACK_FIELDS = {
    "workflow",
    "schema_version",
    "target_workflow",
    "target_run_id",
    "target_root",
    "feedback",
    "tester",
    "request_payload",
    "artifact_refs",
    "role_id",
}
SKILL_BATCH_PROPOSAL_FIELDS = {
    "workflow",
    "schema_version",
    "user_request",
    "requested_batch_id",
    "metadata",
    "role_id",
}
SKILL_BATCH_REGISTRATION_FIELDS = {
    "workflow",
    "schema_version",
    "proposal_path",
    "proposal_run_id",
    "approval",
    "metadata",
    "role_id",
}
SKILL_EVAL_PROMOTION_FIELDS = {
    "workflow",
    "schema_version",
    "skill_ids",
    "registration_run_id",
    "approval",
    "proof",
    "allow_repromotion",
    "metadata",
    "role_id",
}
SKILL_LIFECYCLE_AUDIT_FIELDS = {
    "workflow",
    "schema_version",
    "skill_ids",
    "metadata",
    "role_id",
}
SKILL_DEPRECATION_FIELDS = {
    "workflow",
    "schema_version",
    "skill_id",
    "replacement_skill_id",
    "reason",
    "effective_date",
    "approval",
    "metadata",
    "role_id",
}
SKILL_UPDATE_FIELDS = {
    "workflow",
    "schema_version",
    "skill_id",
    "change_type",
    "version_bump",
    "metadata_updates",
    "skill_body_text",
    "eval_case_updates",
    "deprecation_plan_ref",
    "approval",
    "proof",
    "metadata",
    "role_id",
}
SKILL_SELECTION_EXPLAIN_FIELDS = {
    "workflow",
    "schema_version",
    "user_request",
    "workflow_id",
    "target_root",
    "max_candidate_count",
    "metadata",
    "role_id",
}
SKILL_PACK_VALIDATION_FIELDS = {
    "workflow",
    "schema_version",
    "pack_path",
    "metadata",
    "role_id",
}
SKILL_PACK_INSTALL_FIELDS = {
    "workflow",
    "schema_version",
    "pack_path",
    "approval",
    "metadata",
    "role_id",
}
SKILL_SCAFFOLD_FIELDS = {
    "workflow",
    "schema_version",
    "prompt_family_spec",
    "metadata",
    "role_id",
}
TOOL_CATALOG_VALIDATION_FIELDS = {
    "workflow",
    "schema_version",
    "tool_manifest",
    "tool_manifest_path",
    "metadata",
    "role_id",
}
TOOL_CATALOG_REGISTRATION_FIELDS = {
    "workflow",
    "schema_version",
    "tool_manifest",
    "tool_manifest_path",
    "approval",
    "metadata",
    "role_id",
}
TASK_DECOMPOSITION_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "user_request",
    "metadata",
    "role_id",
    "role_base_url",
    "model",
}
IMPLEMENTATION_WORKFLOW_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "mode",
    "packet_file",
    "packet_operations",
    "from_report",
    "resume",
    "resume_allow_arg_changes",
    "verification_commands",
    "verification_timeout_seconds",
    "max_context_tokens",
    "structure_slice_records",
    "structure_max_file_bytes",
    "no_structure_index",
    "approval",
    "metadata",
    "role_id",
}
WORKFLOW_ROUTER_FIELDS = {
    "workflow",
    "schema_version",
    "target_root",
    "user_request",
    "mode",
    "budgets",
    "approval",
    "packet_operations",
    "context",
    "feedback",
    "execution_budgets",
    "role_id",
    "role_base_url",
    "model",
}


class ControllerServiceError(RuntimeError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST, code: str = "bad_request"):
        super().__init__(message)
        self.status = status
        self.code = code


class ControllerOutputFormat(str, Enum):
    FORMAT_A = "format_a"
    JSON = "json"


class InlineArtifactKind(str, Enum):
    DEFECT_DIAGNOSIS_SUMMARY = "defect_diagnosis_summary"
    ENGINEERING_JUDGMENT_REVIEW = "engineering_judgment_review"
    CODE_EXPLANATION = "code_explanation"
    CODE_QUALITY_REVIEW = "code_quality_review"
    BEHAVIOR_EXISTENCE = "behavior_existence"
    ENDPOINT_ROUTE_LOOKUP = "endpoint_route_lookup"
    MESSAGE_SOURCE_LOOKUP = "message_source_lookup"
    MODULE_SUMMARY = "module_summary"
    DATA_MODEL_LOOKUP = "data_model_lookup"
    TABLE_READ_WRITE_LOOKUP = "table_read_write_lookup"
    COVERAGE_GAP_SUMMARY = "coverage_gap_summary"
    DOCUMENTATION_LOOKUP = "documentation_lookup"
    CLI_ENTRYPOINT_LOOKUP = "cli_entrypoint_lookup"
    CONFIGURATION_EFFECT_SUMMARY = "configuration_effect_summary"
    LOCAL_CHANGE_SUMMARY = "local_change_summary"
    DEPENDENCY_LOOKUP = "dependency_lookup"
    USAGE_SUMMARY = "usage_summary"
    CONFIGURATION_LOOKUP = "configuration_lookup"
    CI_FAILURE_SUMMARY = "ci_failure_summary"
    TEST_FAILURE_SUMMARY = "test_failure_summary"
    MULTI_FILE_BEHAVIOR_INVESTIGATION = "multi_file_behavior_investigation"
    DEPENDENCY_IMPACT_SUMMARY = "dependency_impact_summary"
    TEST_SELECTION_PLAN = "test_selection_plan"
    RUNTIME_ERROR_DIAGNOSIS = "runtime_error_diagnosis"
    REPRODUCTION_CHECKLIST = "reproduction_checklist"
    REQUEST_FLOW_MAP = "request_flow_map"
    CODE_PATH_COMPARISON = "code_path_comparison"
    CHANGE_SURFACE_SUMMARY = "change_surface_summary"
    INVESTIGATION_PLAN = "investigation_plan"
    PACKET_OPERATION_PROPOSAL = "packet_operation_proposal"
    SMALL_TEXT_EDIT_PROPOSAL = "small_text_edit_proposal"
    SMALL_UNIT_TEST_PROPOSAL = "small_unit_test_proposal"
    SIMPLE_TEST_FIX_PROPOSAL = "simple_test_fix_proposal"
    DISPOSABLE_MUTATION_DIFF = "disposable_mutation_structured_diff"
    SKILL_BATCH_PROPOSAL = "skill_batch_proposal"
    SKILL_BATCH_REGISTRATION = "skill_batch_registration"
    SKILL_EVAL_PROMOTION = "skill_eval_promotion"
    SKILL_LIFECYCLE_AUDIT = "skill_lifecycle_audit"
    SKILL_SELECTION_EXPLANATION = "skill_selection_explanation"
    SKILL_PACK_VALIDATION = "skill_pack_validation"
    SKILL_PACK_INSTALLATION = "skill_pack_installation"
    SKILL_SCAFFOLD = "skill_scaffold"
    TASK_DECOMPOSITION = "task_decomposition"


INLINE_ARTIFACT_BYTE_LIMIT = 256 * 1024
INLINE_ARTIFACT_ITEM_LIMIT = 5
DATA_MODEL_FIELD_ITEM_LIMIT = 40
FORMAT_A_SUMMARY_KEY_LIMIT = 24
FORMAT_A_ARTIFACT_LIMIT = 10
FORMAT_A_MAX_LINES = 220
FORMAT_A_MAX_CHARS = 16000
FORMAT_A_SUMMARY_KEY_PRIORITY = (
    "route_status",
    "selected_workflow",
    "downstream_workflow",
    "downstream_status",
    "next_action",
    "answer",
    "retrieval_status",
    "retrieval_category",
    "retrieval_evidence_count",
    "retrieval_artifact_page_count",
    "retrieval_artifact_source_ref_count",
    "retrieval_first_page_id",
    "retrieval_continuation_hint",
    "chunked_status",
    "chunked_stage_count",
    "chunked_completed_stage_count",
    "chunked_evidence_count",
    "chunked_claim_count",
    "chunked_artifact_page_count",
    "chunked_artifact_source_ref_count",
    "chunked_first_page_id",
    "phase222_contract_satisfied",
    "selected_context_strategy",
    "context_strategy_status",
    "context_strategy_execution_path",
    "context_strategy_reason",
    "context_strategy_prompt_class",
    "context_strategy_rationale",
    "context_strategy_blocker_count",
    "raw_prompt_stuffing",
    "source_text_retention",
    "blocker_reasons",
    "blocker_messages",
    "missing_information",
    "bounded_next_step",
    "safe_alternatives",
    "evidence_expectations",
    "mutation_policy",
    "refusal_quality_status",
    "source_changed",
    "source_tree_changed",
    "disposable_copy_changed",
    "mutation_sandbox_status",
    "mutation_diff_file_count",
    "mutation_diff_paths",
    "mutation_rollback_status",
    "selected_context_sources",
    "context_layout_status",
    "context_gap_count",
    "model_capability_status",
    "model_capability_task_class",
    "model_capability_profile_id",
    "model_capability_policy_status",
)
GOVERNED_EVIDENCE_BOUNDARY_KINDS = {
    InlineArtifactKind.DATA_MODEL_LOOKUP,
    InlineArtifactKind.CHANGE_SURFACE_SUMMARY,
}
PERSISTED_SCHEMA_FIELD_SOURCES = {
    "sql_schema_block",
    "sql_alter_add_column",
}


INLINE_ARTIFACT_KEYS: tuple[tuple[InlineArtifactKind, tuple[str, ...]], ...] = (
    (InlineArtifactKind.DEFECT_DIAGNOSIS_SUMMARY, ("downstream_defect_diagnosis_summary", "defect_diagnosis_summary")),
    (InlineArtifactKind.ENGINEERING_JUDGMENT_REVIEW, ("downstream_engineering_judgment_review", "engineering_judgment_review")),
    (InlineArtifactKind.CODE_QUALITY_REVIEW, ("downstream_code_quality_review", "code_quality_review")),
    (InlineArtifactKind.CODE_EXPLANATION, ("downstream_code_explanation", "code_explanation")),
    (InlineArtifactKind.BEHAVIOR_EXISTENCE, ("downstream_behavior_existence", "behavior_existence")),
    (InlineArtifactKind.ENDPOINT_ROUTE_LOOKUP, ("downstream_endpoint_route_lookup", "endpoint_route_lookup")),
    (InlineArtifactKind.MESSAGE_SOURCE_LOOKUP, ("downstream_message_source_lookup", "message_source_lookup")),
    (InlineArtifactKind.MODULE_SUMMARY, ("downstream_module_summary", "module_summary")),
    (InlineArtifactKind.DATA_MODEL_LOOKUP, ("downstream_data_model_lookup", "data_model_lookup")),
    (InlineArtifactKind.TABLE_READ_WRITE_LOOKUP, ("downstream_table_read_write_lookup", "table_read_write_lookup")),
    (InlineArtifactKind.COVERAGE_GAP_SUMMARY, ("downstream_coverage_gap_summary", "coverage_gap_summary")),
    (InlineArtifactKind.DOCUMENTATION_LOOKUP, ("downstream_documentation_lookup", "documentation_lookup")),
    (InlineArtifactKind.CLI_ENTRYPOINT_LOOKUP, ("downstream_cli_entrypoint_lookup", "cli_entrypoint_lookup")),
    (
        InlineArtifactKind.CONFIGURATION_EFFECT_SUMMARY,
        ("downstream_configuration_effect_summary", "configuration_effect_summary"),
    ),
    (InlineArtifactKind.LOCAL_CHANGE_SUMMARY, ("downstream_local_change_summary", "local_change_summary")),
    (InlineArtifactKind.DEPENDENCY_LOOKUP, ("downstream_dependency_lookup", "dependency_lookup")),
    (InlineArtifactKind.USAGE_SUMMARY, ("downstream_usage_summary", "usage_summary")),
    (InlineArtifactKind.CONFIGURATION_LOOKUP, ("downstream_configuration_lookup", "configuration_lookup")),
    (InlineArtifactKind.CI_FAILURE_SUMMARY, ("downstream_ci_failure_summary", "ci_failure_summary")),
    (InlineArtifactKind.TEST_FAILURE_SUMMARY, ("downstream_test_failure_summary", "test_failure_summary")),
    (
        InlineArtifactKind.MULTI_FILE_BEHAVIOR_INVESTIGATION,
        ("downstream_multi_file_behavior_investigation", "multi_file_behavior_investigation"),
    ),
    (InlineArtifactKind.DEPENDENCY_IMPACT_SUMMARY, ("downstream_dependency_impact_summary", "dependency_impact_summary")),
    (InlineArtifactKind.TEST_SELECTION_PLAN, ("downstream_test_selection_plan", "test_selection_plan")),
    (InlineArtifactKind.REPRODUCTION_CHECKLIST, ("downstream_reproduction_checklist", "reproduction_checklist")),
    (InlineArtifactKind.RUNTIME_ERROR_DIAGNOSIS, ("downstream_runtime_error_diagnosis", "runtime_error_diagnosis")),
    (InlineArtifactKind.REQUEST_FLOW_MAP, ("downstream_request_flow_map", "request_flow_map")),
    (InlineArtifactKind.CODE_PATH_COMPARISON, ("downstream_code_path_comparison", "code_path_comparison")),
    (InlineArtifactKind.CHANGE_SURFACE_SUMMARY, ("downstream_change_surface_summary", "change_surface_summary")),
    (InlineArtifactKind.INVESTIGATION_PLAN, ("downstream_investigation_plan", "investigation_plan")),
    (InlineArtifactKind.PACKET_OPERATION_PROPOSAL, ("packet_operation_proposal",)),
    (InlineArtifactKind.SMALL_TEXT_EDIT_PROPOSAL, ("small_text_edit_proposal",)),
    (InlineArtifactKind.SMALL_UNIT_TEST_PROPOSAL, ("small_unit_test_proposal",)),
    (InlineArtifactKind.SIMPLE_TEST_FIX_PROPOSAL, ("simple_test_fix_proposal",)),
    (InlineArtifactKind.DISPOSABLE_MUTATION_DIFF, ("disposable_mutation_diff",)),
    (InlineArtifactKind.SKILL_BATCH_PROPOSAL, ("downstream_skill_batch_proposal", "skill_batch_proposal")),
    (
        InlineArtifactKind.SKILL_BATCH_REGISTRATION,
        ("skill_batch_registration", "downstream_skill_batch_registration"),
    ),
    (InlineArtifactKind.SKILL_EVAL_PROMOTION, ("skill_eval_promotion", "downstream_skill_eval_promotion")),
    (InlineArtifactKind.SKILL_LIFECYCLE_AUDIT, ("skill_lifecycle_audit", "downstream_skill_lifecycle_audit")),
    (
        InlineArtifactKind.SKILL_SELECTION_EXPLANATION,
        ("skill_selection_explanation", "downstream_skill_selection_explanation"),
    ),
    (
        InlineArtifactKind.SKILL_PACK_VALIDATION,
        ("skill_pack_validation_artifact", "skill_pack_validation", "downstream_skill_pack_validation"),
    ),
    (
        InlineArtifactKind.SKILL_PACK_INSTALLATION,
        ("skill_pack_installation", "downstream_skill_pack_installation"),
    ),
    (InlineArtifactKind.SKILL_SCAFFOLD, ("skill_scaffold", "downstream_skill_scaffold")),
    (InlineArtifactKind.TASK_DECOMPOSITION, ("task_decomposition", "downstream_task_decomposition")),
)


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


@dataclass(frozen=True)
class BuiltExecutionPlanning:
    request: ExecutionPlanningInvocationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltCodeContextLookup:
    request: CodeContextLookupRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltCodeInvestigation:
    request: CodeInvestigationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltRefactorSinglePath:
    request: RefactorSinglePathRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltWorkflowFeedback:
    request: WorkflowFeedbackRecordRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillBatchProposal:
    request: SkillBatchProposalRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillBatchRegistration:
    request: SkillBatchRegistrationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillEvalPromotion:
    request: SkillEvalPromotionRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillLifecycleAudit:
    request: SkillLifecycleAuditRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillDeprecation:
    request: SkillDeprecationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillUpdate:
    request: SkillUpdateRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillSelectionExplain:
    request: SkillSelectionExplainRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillPackValidation:
    request: SkillPackValidationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillPackInstall:
    request: SkillPackInstallRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltSkillScaffold:
    request: SkillScaffoldRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltToolCatalogValidation:
    request: ToolCatalogValidationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltToolCatalogRegistration:
    request: ToolCatalogRegistrationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltTaskDecomposition:
    request: TaskDecompositionRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltImplementationWorkflow:
    request: ImplementationWorkflowInvocationRequest
    tool_policy: ResolvedControllerToolPolicy


@dataclass(frozen=True)
class BuiltWorkflowRouterPlan:
    request: WorkflowRouterPlanRequest
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
    if report.get("kind") == "execution_planning_report":
        raw_warnings = report.get("context_warnings")
        if isinstance(raw_warnings, list):
            warnings = [item for item in raw_warnings if isinstance(item, dict)]
            selected = warnings[:limit]
            if len(warnings) > limit:
                selected.append({"warning": "warnings_truncated", "available_warning_count": len(warnings), "retained": limit})
            return selected
    if report.get("kind") == "code_context_lookup_report":
        raw_warnings = report.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [item for item in raw_warnings if isinstance(item, dict)]
            selected = warnings[:limit]
            if len(warnings) > limit:
                selected.append({"warning": "warnings_truncated", "available_warning_count": len(warnings), "retained": limit})
            return selected
    if report.get("kind") == "code_investigation_report":
        raw_warnings = report.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [item for item in raw_warnings if isinstance(item, dict)]
            selected = warnings[:limit]
            if len(warnings) > limit:
                selected.append({"warning": "warnings_truncated", "available_warning_count": len(warnings), "retained": limit})
            return selected
    if report.get("kind") == "refactor_single_path_report":
        raw_warnings = report.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [item for item in raw_warnings if isinstance(item, dict)]
            selected = warnings[:limit]
            if len(warnings) > limit:
                selected.append({"warning": "warnings_truncated", "available_warning_count": len(warnings), "retained": limit})
            return selected
    if report.get("kind") == "workflow_feedback_record_report":
        raw_warnings = report.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [item for item in raw_warnings if isinstance(item, dict)]
            selected = warnings[:limit]
            if len(warnings) > limit:
                selected.append({"warning": "warnings_truncated", "available_warning_count": len(warnings), "retained": limit})
            return selected
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


def execution_planning_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "execution_planning_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def execution_planning_non_mutation(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "execution_planning_report":
        return None
    value = report.get("non_mutation")
    return value if isinstance(value, dict) else None


def code_context_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "code_context_lookup_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def code_investigation_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "code_investigation_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def refactor_single_path_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "refactor_single_path_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def workflow_feedback_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "workflow_feedback_record_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_batch_proposal_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_batch_proposal_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_batch_registration_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_batch_registration_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_eval_promotion_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_eval_promotion_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_lifecycle_audit_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_lifecycle_audit_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_deprecation_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_deprecation_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_update_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_update_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_selection_explanation_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_selection_explanation_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_pack_validation_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_pack_validation_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_pack_install_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_pack_install_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def skill_scaffold_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "skill_scaffold_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def tool_catalog_validation_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "tool_catalog_validation_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def tool_catalog_registration_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "tool_catalog_registration_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def task_decomposition_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "task_decomposition_report":
        return None
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else None


def implementation_workflow_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "implementation_report":
        return None
    changed = report.get("changed_artifacts") if isinstance(report.get("changed_artifacts"), list) else []
    verification = report.get("verification_results") if isinstance(report.get("verification_results"), list) else []
    patch_previews = [
        item.get("patch_preview")
        for item in changed
        if isinstance(item, dict) and isinstance(item.get("patch_preview"), str)
    ]
    modified_targets = [
        item.get("target_file")
        for item in changed
        if isinstance(item, dict) and item.get("target_modified") is True and isinstance(item.get("target_file"), str)
    ]
    rollback_operations = [
        item.get("rollback_operation")
        for item in changed
        if isinstance(item, dict) and isinstance(item.get("rollback_operation"), dict)
    ]
    summary = {
        "implementation_status": report.get("status"),
        "mode": report.get("mode"),
        "target_root": report.get("target_root"),
        "packet_count": report.get("packet_count"),
        "completed_packet_count": report.get("completed_packet_count"),
        "changed_artifact_count": len([item for item in changed if isinstance(item, dict)]),
        "patch_preview_count": len(patch_previews),
        "patch_previews": patch_previews[:INLINE_ARTIFACT_ITEM_LIMIT],
        "target_repository_changed": bool(modified_targets),
        "modified_targets": modified_targets[:INLINE_ARTIFACT_ITEM_LIMIT],
        "rollback_operation_count": len(rollback_operations),
        "verification_result_count": len([item for item in verification if isinstance(item, dict)]),
        "verification_statuses": [
            item.get("status")
            for item in verification
            if isinstance(item, dict) and isinstance(item.get("status"), str)
        ][:INLINE_ARTIFACT_ITEM_LIMIT],
        "next_action": "inspect_patch_preview" if report.get("mode") == "draft" else "inspect_verification_and_rollback",
    }
    return {key: value for key, value in summary.items() if value not in (None, [], {})}


def workflow_router_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get("kind") != "workflow_router_report":
        return None
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return None
    compact = dict(summary)
    decision = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    if blockers:
        blocker_reasons = [
            str(item.get("reason"))
            for item in blockers
            if isinstance(item, dict) and isinstance(item.get("reason"), str)
        ]
        blocker_messages = [
            str(item.get("message"))
            for item in blockers
            if isinstance(item, dict) and isinstance(item.get("message"), str)
        ]
        if blocker_reasons:
            compact["blocker_reasons"] = blocker_reasons[:5]
        if blocker_messages:
            compact["blocker_messages"] = blocker_messages[:5]
            compact.setdefault(
                "answer",
                f"I did not start a repository workflow. {blocker_messages[0]}",
            )
        compact.update(refusal_quality_summary_for_blockers(blocker_reasons, blocker_messages))
    return compact


def refusal_quality_summary_for_blockers(
    blocker_reasons: list[str],
    blocker_messages: list[str] | None = None,
) -> dict[str, Any]:
    reasons = [reason for reason in blocker_reasons if reason]
    primary = reasons[0] if reasons else "blocked"
    messages = [message for message in blocker_messages or [] if message]
    defaults = {
        "missing_information": [
            "a concrete target behavior, file, symbol, failing command, error, or test",
            "the expected outcome or acceptance condition",
        ],
        "bounded_next_step": (
            "Send one concrete coding task with the repository path and the specific behavior, file, symbol, "
            "error, or test to inspect."
        ),
        "safe_alternatives": [
            "start with read-only inspection",
            "prepare an approval-gated plan before mutation",
            "use a disposable copy for apply testing",
        ],
        "evidence_expectations": [
            "reproduction steps",
            "failing command or test output",
            "relevant logs, stack trace, screenshot, file, or symbol",
        ],
        "mutation_policy": "no repository workflow or source mutation started",
        "refusal_quality_status": "actionable",
    }
    by_reason: dict[str, dict[str, Any]] = {
        "ambiguous": {
            "missing_information": [
                "the specific behavior, file, symbol, error, or test to investigate",
                "the expected result or acceptance criterion",
            ],
            "bounded_next_step": "Choose one concrete target and ask for read-only investigation before implementation.",
            "safe_alternatives": [
                "start with a read-only investigation",
                "decompose the task into one small scoped request",
            ],
            "mutation_policy": "no repository workflow or source mutation started",
        },
        "blocked_approval_bypass": {
            "missing_information": [
                "approval-gated planning scope",
                "the exact change request and target files or behavior",
                "explicit approval only after a reviewed plan or packet",
            ],
            "bounded_next_step": (
                "Ask for read-only investigation or draft packet planning first; do not request skipped approval."
            ),
            "safe_alternatives": [
                "read-only investigation",
                "draft-only implementation packet",
                "disposable-copy apply after explicit approval",
            ],
            "mutation_policy": "source mutation is blocked until an approval-gated workflow allows it",
        },
        "blocked_raw_context": {
            "missing_information": [
                "the code question to answer from model-visible artifacts",
                "the target file, symbol, relationship, or behavior to inspect",
            ],
            "bounded_next_step": (
                "Ask for a code-context lookup or code investigation result instead of raw CodeGraphContext, MCP, or Cypher access."
            ),
            "safe_alternatives": [
                "code_context.lookup for curated relationships",
                "code_investigation.plan for bounded source evidence",
            ],
            "mutation_policy": "read-only only; no raw tool operation was started",
        },
        "unsupported": {
            "missing_information": [
                "a supported local development workflow request",
                "the repository path and coding task if this is actually a code request",
            ],
            "bounded_next_step": (
                "Reframe the request as a supported coding task such as explaining code, locating tests, "
                "summarizing a failure, or planning a small approval-gated change."
            ),
            "safe_alternatives": [
                "ask for supported coding workflow help",
                "use the non-router model endpoint for ordinary chat",
            ],
            "mutation_policy": "no repository workflow or source mutation started",
        },
        "unsupported_repository_layout": {
            "missing_information": [
                "a repository root containing supported source, test, config, or documentation files",
                "or an explicit supported file path",
            ],
            "bounded_next_step": "Point the request at the repository root or at a supported file path.",
            "safe_alternatives": [
                "use a supported fixture",
                "provide an explicit source, test, config, or documentation file",
            ],
            "mutation_policy": "read-only route is blocked; no source mutation started",
        },
        "low_selection_confidence": {
            "missing_information": [
                "clearer task intent",
                "target file, symbol, behavior, error, or test",
            ],
            "bounded_next_step": "Narrow the request until one workflow can be selected with confidence.",
            "safe_alternatives": [
                "ask for task decomposition",
                "start with read-only code investigation",
            ],
            "mutation_policy": "no source mutation started",
        },
    }
    summary = dict(defaults)
    summary.update(by_reason.get(primary, {}))
    if messages and not summary.get("answer"):
        summary["answer"] = f"I did not start a repository workflow. {messages[0]}"
    return summary


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
    planning_summary = execution_planning_summary(result.report)
    lookup_summary = code_context_summary(result.report)
    investigation_summary = code_investigation_summary(result.report)
    refactor_summary = refactor_single_path_summary(result.report)
    feedback_summary = workflow_feedback_summary(result.report)
    skill_batch_summary = skill_batch_proposal_summary(result.report)
    skill_batch_registration = skill_batch_registration_summary(result.report)
    skill_eval_promotion = skill_eval_promotion_summary(result.report)
    skill_lifecycle_audit = skill_lifecycle_audit_summary(result.report)
    skill_deprecation = skill_deprecation_summary(result.report)
    skill_update = skill_update_summary(result.report)
    skill_selection_explanation = skill_selection_explanation_summary(result.report)
    skill_pack_validation = skill_pack_validation_summary(result.report)
    skill_pack_install = skill_pack_install_summary(result.report)
    skill_scaffold = skill_scaffold_summary(result.report)
    tool_catalog_validation = tool_catalog_validation_summary(result.report)
    tool_catalog_registration = tool_catalog_registration_summary(result.report)
    task_decomposition = task_decomposition_summary(result.report)
    implementation_summary = implementation_workflow_summary(result.report)
    router_summary = workflow_router_summary(result.report)
    response: dict[str, Any] = {
        "run_id": result.run_id,
        "workflow": result.workflow,
        "status": result.status.value,
        "artifacts": result.artifact_paths,
        "summary": (
            planning_summary
            if planning_summary is not None
            else lookup_summary
            if lookup_summary is not None
            else investigation_summary
            if investigation_summary is not None
            else refactor_summary
            if refactor_summary is not None
            else feedback_summary
            if feedback_summary is not None
            else skill_batch_summary
            if skill_batch_summary is not None
            else skill_batch_registration
            if skill_batch_registration is not None
            else skill_eval_promotion
            if skill_eval_promotion is not None
            else skill_lifecycle_audit
            if skill_lifecycle_audit is not None
            else skill_deprecation
            if skill_deprecation is not None
            else skill_update
            if skill_update is not None
            else skill_selection_explanation
            if skill_selection_explanation is not None
            else skill_pack_validation
            if skill_pack_validation is not None
            else skill_pack_install
            if skill_pack_install is not None
            else skill_scaffold
            if skill_scaffold is not None
            else tool_catalog_validation
            if tool_catalog_validation is not None
            else tool_catalog_registration
            if tool_catalog_registration is not None
            else task_decomposition
            if task_decomposition is not None
            else implementation_summary
            if implementation_summary is not None
            else router_summary
            if router_summary is not None
            else response_summary(result.summary_text)
        ),
        "warnings": response_warnings(result.report),
        "failures": response_failures(result.failures),
        "resume_key": result.resume_key,
    }
    if tool_policy is not None:
        response["tool_policy"] = tool_policy.audit_record()
    review_summary = documenter_review_summary(result.report)
    if review_summary is not None:
        response["review_summary"] = review_summary
    non_mutation = execution_planning_non_mutation(result.report)
    if non_mutation is not None:
        response["non_mutation"] = non_mutation
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
        "non_mutation": response.get("non_mutation") if isinstance(response.get("non_mutation"), dict) else None,
        "run_lookup": f"/v1/controller/runs/{run_id}" if isinstance(run_id, str) and run_id else None,
    }


def parse_controller_output_format(value: Any, *, explicit: bool = False) -> ControllerOutputFormat | None:
    if value is None:
        return None
    if isinstance(value, ControllerOutputFormat):
        return value
    if isinstance(value, str):
        normalized = re.sub(r"[\s-]+", "_", value.strip().lower())
        aliases = {
            "format_a": ControllerOutputFormat.FORMAT_A,
            "formata": ControllerOutputFormat.FORMAT_A,
            "a": ControllerOutputFormat.FORMAT_A,
            "default": ControllerOutputFormat.FORMAT_A,
            "natural": ControllerOutputFormat.FORMAT_A,
            "natural_language": ControllerOutputFormat.FORMAT_A,
            "human": ControllerOutputFormat.FORMAT_A,
            "human_readable": ControllerOutputFormat.FORMAT_A,
            "text": ControllerOutputFormat.FORMAT_A,
            "json": ControllerOutputFormat.JSON,
            "json_object": ControllerOutputFormat.JSON,
            "json_schema": ControllerOutputFormat.JSON,
            "strict_json": ControllerOutputFormat.JSON,
        }
        selected = aliases.get(normalized)
        if selected is not None:
            return selected
    if explicit:
        allowed = ", ".join(item.value for item in ControllerOutputFormat)
        raise ControllerServiceError(
            f"Unsupported output_format. Use one of: {allowed}.",
            code="unsupported_output_format",
        )
    return None


def output_format_from_response_format(value: Any) -> ControllerOutputFormat | None:
    if value is None:
        return None
    if isinstance(value, dict):
        response_type = value.get("type")
        if not isinstance(response_type, str) or not response_type.strip():
            raise ControllerServiceError(
                "Unsupported response_format. Use type json_object, json_schema, json, or format_a.",
                code="unsupported_output_format",
            )
        return parse_controller_output_format(response_type, explicit=True)
    if isinstance(value, str):
        return parse_controller_output_format(value, explicit=True)
    raise ControllerServiceError(
        "Unsupported response_format. Use type json_object, json_schema, json, or format_a.",
        code="unsupported_output_format",
    )


def latest_user_message_text_optional(payload: dict[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user" or role is None:
            text = chat_content_to_text(message.get("content")).strip()
            if text:
                return bounded_string(text, 6000)
    return ""


def output_format_from_natural_text(text: str) -> ControllerOutputFormat | None:
    compact = lower_text = re.sub(r"\s+", " ", text.lower()).strip()
    json_patterns = (
        r"\breturn (?:the )?(?:output |response )?(?:as |in )?json\b",
        r"\brespond (?:only )?(?:with |in )json\b",
        r"\boutput (?:as |in )json\b",
        r"\bformat (?:the )?(?:output |response )?(?:as |in )json\b",
        r"\bjson only\b",
        r"\bvalid json\b",
        r"\bstrict json\b",
    )
    if any(re.search(pattern, compact) for pattern in json_patterns):
        return ControllerOutputFormat.JSON
    format_a_patterns = (
        r"\bformat ?a\b",
        r"\bnatural language\b",
        r"\bhuman[- ]readable\b",
        r"\bplain english\b",
    )
    if any(re.search(pattern, lower_text) for pattern in format_a_patterns):
        return ControllerOutputFormat.FORMAT_A
    return None


def select_controller_output_format(payload: dict[str, Any]) -> ControllerOutputFormat:
    for key in ("output_format", "agentic_output_format"):
        if key in payload:
            selected = parse_controller_output_format(payload.get(key), explicit=True)
            if selected is not None:
                return selected
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and "output_format" in metadata:
        selected = parse_controller_output_format(metadata.get("output_format"), explicit=True)
        if selected is not None:
            return selected
    selected = output_format_from_response_format(payload.get("response_format"))
    if selected is not None:
        return selected
    selected = output_format_from_natural_text(latest_user_message_text_optional(payload))
    return selected or ControllerOutputFormat.FORMAT_A


def format_summary_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def inline_text(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def path_with_line(record: dict[str, Any]) -> str:
    path = record.get("path")
    if not isinstance(path, str) or not path:
        return ""
    line = record.get("line")
    if isinstance(line, int):
        return f"{path}:{line}"
    return path


def limited_join(values: list[str], *, limit: int = INLINE_ARTIFACT_ITEM_LIMIT) -> str:
    visible = [value for value in values if value][:limit]
    if not visible:
        return ""
    suffix = f"; +{len(values) - limit} more" if len(values) > limit else ""
    return "; ".join(visible) + suffix


def command_text(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(inline_text(part, 120) for part in command)
    return inline_text(command, 300)


def artifact_kind_label(artifact: dict[str, Any]) -> str:
    kind = artifact.get("kind")
    return kind if isinstance(kind, str) and kind else "proposal"


def read_inline_artifact(path_value: Any) -> dict[str, Any] | None:
    if not isinstance(path_value, str) or not path_value.lower().endswith(".json"):
        return None
    path = Path(path_value)
    try:
        if not path.is_file() or path.stat().st_size > INLINE_ARTIFACT_BYTE_LIMIT:
            return None
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def inline_artifact_by_kind(
    artifacts: dict[str, Any],
    kind: InlineArtifactKind,
) -> dict[str, Any] | None:
    for configured_kind, keys in INLINE_ARTIFACT_KEYS:
        if configured_kind != kind:
            continue
        for key in keys:
            artifact = read_inline_artifact(artifacts.get(key))
            if artifact is not None and artifact.get("status") != "not_requested":
                return artifact
    return None


def promoted_inline_artifact_keys(kind: InlineArtifactKind) -> tuple[tuple[InlineArtifactKind, tuple[str, ...]], ...]:
    selected = [item for item in INLINE_ARTIFACT_KEYS if item[0] == kind]
    remainder = [item for item in INLINE_ARTIFACT_KEYS if item[0] != kind]
    return tuple([*selected, *remainder])


def artifact_json_by_key(artifacts: dict[str, Any], key: str) -> dict[str, Any] | None:
    return read_inline_artifact(artifacts.get(key))


def string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            items.append(item)
    return items


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def verification_records_from_artifacts(artifacts: dict[str, Any]) -> list[Any]:
    for path_value in artifacts.values():
        artifact = read_inline_artifact(path_value)
        if artifact is None:
            continue
        direct = artifact.get("verification_commands")
        if isinstance(direct, list) and direct:
            return direct
        verification_plan = artifact.get("verification_plan")
        if isinstance(verification_plan, dict):
            commands = verification_plan.get("verification_commands")
            if isinstance(commands, list) and commands:
                return commands
        tiers = artifact.get("command_tiers")
        if isinstance(tiers, list):
            tier_commands: list[Any] = []
            for tier in tiers:
                if isinstance(tier, dict):
                    tier_commands.extend(first_list(tier.get("commands")))
            if tier_commands:
                return tier_commands
    return []


def route_rules_from_route_decision(route_decision: dict[str, Any]) -> list[str]:
    evidence = route_decision.get("evidence") if isinstance(route_decision.get("evidence"), list) else []
    rules: list[str] = []
    for item in evidence:
        if isinstance(item, dict) and item.get("source") == "router_rule" and isinstance(item.get("rule"), str):
            rules.append(item["rule"])
    return rules


def inline_artifact_keys_for_response(
    response: dict[str, Any] | None,
    artifacts: dict[str, Any],
) -> tuple[tuple[InlineArtifactKind, tuple[str, ...]], ...]:
    if not isinstance(response, dict):
        return INLINE_ARTIFACT_KEYS
    route_decision = artifact_json_by_key(artifacts, "route_decision") or {}
    route_rules = set(route_rules_from_route_decision(route_decision))
    if "l2_engineering_judgment_terms" in route_rules:
        return promoted_inline_artifact_keys(InlineArtifactKind.ENGINEERING_JUDGMENT_REVIEW)
    if "l2_code_quality_review_terms" in route_rules:
        return promoted_inline_artifact_keys(InlineArtifactKind.CODE_QUALITY_REVIEW)
    if "l1_endpoint_route_lookup_terms" in route_rules:
        return promoted_inline_artifact_keys(InlineArtifactKind.ENDPOINT_ROUTE_LOOKUP)
    if "l1_data_model_lookup_terms" in route_rules:
        return promoted_inline_artifact_keys(InlineArtifactKind.DATA_MODEL_LOOKUP)
    if "l1_find_behavior_start_terms" in route_rules:
        return promoted_inline_artifact_keys(InlineArtifactKind.INVESTIGATION_PLAN)
    return INLINE_ARTIFACT_KEYS


def workflow_description_from_decision(
    route_decision: dict[str, Any],
    registry_snapshot: dict[str, Any],
    selected_workflow: str,
) -> str | None:
    workflows = registry_snapshot.get("workflows") if isinstance(registry_snapshot.get("workflows"), dict) else {}
    workflow = workflows.get(selected_workflow) if isinstance(workflows.get(selected_workflow), dict) else {}
    description = workflow.get("description")
    if isinstance(description, str) and description:
        return description
    evidence = route_decision.get("evidence") if isinstance(route_decision.get("evidence"), list) else []
    for item in evidence:
        if (
            isinstance(item, dict)
            and item.get("source") == "workflow_registry"
            and item.get("selected_workflow") == selected_workflow
            and isinstance(item.get("description"), str)
        ):
            return item["description"]
    return None


def capability_route_keys_from_decision(route_decision: dict[str, Any]) -> dict[str, str]:
    evidence = route_decision.get("evidence") if isinstance(route_decision.get("evidence"), list) else []
    for item in evidence:
        if isinstance(item, dict) and item.get("source") == "skill_registry":
            keys = item.get("capability_route_keys")
            if isinstance(keys, dict):
                return {str(key): str(value) for key, value in keys.items() if isinstance(value, str)}
    return {}


def registry_items_by_key(registry_snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = registry_snapshot.get(key)
    return value if isinstance(value, dict) else {}


def selected_workflow_display(
    route_decision: dict[str, Any],
    summary: dict[str, Any],
    fallback: Any = None,
) -> str:
    for source in (route_decision, summary):
        if "selected_workflow" not in source:
            continue
        value = source.get("selected_workflow")
        if value is None:
            return "none"
        if isinstance(value, str) and value.strip():
            return value
    downstream = summary.get("downstream_workflow")
    if isinstance(downstream, str) and downstream.strip():
        return downstream
    if isinstance(fallback, str) and fallback.strip():
        return fallback
    return "unknown"


def skill_selection_explanation_for_response(response: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    route_decision = artifact_json_by_key(artifacts, "route_decision") or {}
    if not route_decision:
        return None
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    registry_snapshot = artifact_json_by_key(artifacts, "registry_snapshot") or {}
    selected_workflow = selected_workflow_display(route_decision, summary, response.get("workflow"))
    selected_skills = string_items(route_decision.get("selected_skills")) or string_items(summary.get("selected_skill_ids"))
    selected_tools = string_items(route_decision.get("selected_tools"))
    route_rules = route_rules_from_route_decision(route_decision)
    capability_route_keys = capability_route_keys_from_decision(route_decision)
    selection_audit = route_decision.get("selection_audit") if isinstance(route_decision.get("selection_audit"), dict) else {}
    selected_audit = selection_audit.get("selected") if isinstance(selection_audit.get("selected"), dict) else {}
    workflow_candidates = (
        selection_audit.get("workflow_candidates")
        if isinstance(selection_audit.get("workflow_candidates"), dict)
        else {}
    )
    skill_candidates = selection_audit.get("skill_candidates") if isinstance(selection_audit.get("skill_candidates"), dict) else {}
    tool_candidates = selection_audit.get("tool_candidates") if isinstance(selection_audit.get("tool_candidates"), dict) else {}
    skills = registry_items_by_key(registry_snapshot, "skills")
    tools = registry_items_by_key(registry_snapshot, "tools")
    workflow_description = workflow_description_from_decision(route_decision, registry_snapshot, selected_workflow)
    skill_details: list[dict[str, Any]] = []
    for skill_id in selected_skills[:5]:
        skill = skills.get(skill_id) if isinstance(skills.get(skill_id), dict) else {}
        contract = skill.get("capability_contract") if isinstance(skill.get("capability_contract"), dict) else {}
        route_key = first_string(capability_route_keys.get(skill_id), contract.get("route_key"))
        reason = f"Selected from registry capability metadata for {selected_workflow}."
        if route_key:
            reason = f"{reason} Capability route: {route_key}."
        skill_details.append(
            {
                "skill_id": skill_id,
                "route_key": route_key,
                "description": inline_text(skill.get("description"), 180) if isinstance(skill.get("description"), str) else None,
                "reason": reason,
            }
        )
    tool_details: list[dict[str, Any]] = []
    for tool_id in selected_tools[:5]:
        tool = tools.get(tool_id) if isinstance(tools.get(tool_id), dict) else {}
        tool_details.append(
            {
                "tool_id": tool_id,
                "description": inline_text(tool.get("description"), 160) if isinstance(tool.get("description"), str) else None,
                "reason": f"Allowed by the selected workflow tool policy for {selected_workflow}.",
            }
        )
    selection_basis = "capability_contract_shortlist" if selected_skills else "route_decision"
    why_parts = [f"Selected {selected_workflow}"]
    if route_rules:
        why_parts.append(f"because router rule(s) matched: {limited_join(route_rules, limit=3)}")
    if workflow_description:
        why_parts.append(f"workflow purpose: {inline_text(workflow_description, 180)}")
    rejected_workflows = [
        str(item.get("workflow_id"))
        for item in workflow_candidates.get("rejected", [])[:5]
        if isinstance(item, dict) and isinstance(item.get("workflow_id"), str)
    ]
    rejected_skills = [
        str(item.get("skill_id"))
        for item in skill_candidates.get("rejected", [])[:5]
        if isinstance(item, dict) and isinstance(item.get("skill_id"), str)
    ]
    rejected_tools = [
        str(item.get("tool_id"))
        for item in tool_candidates.get("rejected", [])[:5]
        if isinstance(item, dict) and isinstance(item.get("tool_id"), str)
    ]
    return {
        "selected_workflow": selected_workflow,
        "confidence": route_decision.get("confidence"),
        "confidence_reasons": selected_audit.get("confidence_reasons") if isinstance(selected_audit.get("confidence_reasons"), list) else [],
        "coverage_entry_ids": selected_audit.get("coverage_entry_ids") if isinstance(selected_audit.get("coverage_entry_ids"), list) else [],
        "route_rules": route_rules,
        "workflow_description": workflow_description,
        "selection_basis": selection_basis,
        "why": "; ".join(why_parts) + ".",
        "skills": skill_details,
        "tools": tool_details,
        "rejected_candidates": {
            "workflows": rejected_workflows,
            "skills": rejected_skills,
            "tools": rejected_tools,
            "workflow_rejected_count": workflow_candidates.get("rejected_count", 0),
            "skill_rejected_count": skill_candidates.get("rejected_count", 0),
            "tool_rejected_count": tool_candidates.get("rejected_count", 0),
        },
        "grounding": [
            "route_decision.evidence",
            "route_decision.selected_skills",
            "route_decision.selected_tools",
            "route_decision.selection_audit",
            "registry_snapshot.skills",
            "registry_snapshot.tools",
        ],
    }


def context_source_explanation_for_response(response: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    route_decision = artifact_json_by_key(artifacts, "route_decision") or {}
    audit = artifact_json_by_key(artifacts, "context_source_audit") or {}
    if not audit and isinstance(route_decision.get("context_source_audit"), dict):
        audit = route_decision["context_source_audit"]
    if not audit:
        return None
    selected = audit.get("selected") if isinstance(audit.get("selected"), list) else []
    rejected = audit.get("rejected") if isinstance(audit.get("rejected"), list) else []
    layout = audit.get("layout") if isinstance(audit.get("layout"), dict) else {}
    selected_sources: list[dict[str, Any]] = []
    for item in selected[:5]:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str):
            continue
        selected_sources.append(
            {
                "source_id": source_id,
                "description": inline_text(item.get("description"), 160),
                "tool_ids": string_items(item.get("tool_ids")),
                "artifact_keys": string_items(item.get("artifact_keys")),
                "budget": item.get("budget") if isinstance(item.get("budget"), dict) else {},
                "reasons": string_items(item.get("reasons")),
            }
        )
    rejected_sources = [
        {
            "source_id": str(item.get("source_id")),
            "reasons": string_items(item.get("reasons")),
        }
        for item in rejected[:5]
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    ]
    gaps = string_items(audit.get("gaps"))
    evidence_files = string_items(audit.get("evidence_files"))
    return {
        "selected_source_ids": string_items(audit.get("selected_source_ids")),
        "selected": selected_sources,
        "rejected": rejected_sources,
        "layout": {
            "status": layout.get("status"),
            "supported_file_count": layout.get("supported_file_count"),
            "sample_files": string_items(layout.get("sample_files")),
            "scanned_file_count": layout.get("scanned_file_count"),
            "scan_limit": layout.get("scan_limit"),
            "git_present": layout.get("git_present"),
        },
        "budget": audit.get("budget") if isinstance(audit.get("budget"), dict) else {},
        "evidence_files": evidence_files,
        "gaps": gaps,
        "grounding": [
            "route_decision.context_source_audit",
            "context_source_audit",
            "route_decision.controller_request_preview.context_sources",
        ],
    }


def chat_contract_for_response(response: dict[str, Any]) -> dict[str, Any]:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    tool_policy = response.get("tool_policy") if isinstance(response.get("tool_policy"), dict) else {}
    route_decision = artifact_json_by_key(artifacts, "route_decision") or {}
    workflow = first_string(response.get("workflow")) or "workflow"
    selected_skills = string_items(route_decision.get("selected_skills")) or string_items(summary.get("selected_skill_ids"))
    selected_tools = string_items(route_decision.get("selected_tools"))
    if not selected_tools:
        selected_tools = sorted(
            set(string_items(tool_policy.get("controller_tool_ids")) + string_items(tool_policy.get("model_visible_tool_ids")))
        )
    verification_records = first_list(summary.get("verification_commands"))
    if not verification_records:
        verification_records = verification_records_from_artifacts(artifacts)
    verification_count = summary.get("verification_command_count")
    if not isinstance(verification_count, int):
        verification_count = len(verification_records)
    verification = verification_commands_summary(verification_records)
    if not verification and verification_count:
        verification = f"{verification_count} command(s)"
    selected_workflow = selected_workflow_display(route_decision, summary, workflow)
    next_action = first_string(summary.get("next_action"), route_decision.get("next_action")) or "none"
    downstream = route_decision.get("downstream") if isinstance(route_decision.get("downstream"), dict) else {}
    if (
        next_action == "execute_read_only"
        and response.get("status") == "completed"
        and (summary.get("downstream_status") == "completed" or downstream.get("status") == "completed")
    ):
        next_action = "none"
    answer = first_string(summary.get("answer"))
    return {
        "workflow": workflow,
        "status": first_string(response.get("status")) or "unknown",
        "selected_workflow": selected_workflow,
        "selected_skills": selected_skills,
        "selected_tools": selected_tools,
        "answer": answer,
        "next_action": next_action,
        "verification": verification or "none",
        "verification_command_count": verification_count,
        "selection_explanation": skill_selection_explanation_for_response(response),
        "context_explanation": context_source_explanation_for_response(response),
    }


def append_chat_contract_lines(lines: list[str], response: dict[str, Any]) -> None:
    contract = chat_contract_for_response(response)
    lines.append("")
    lines.append("Result:")
    lines.append(f"- Workflow: {contract['workflow']}")
    lines.append(f"- Status: {contract['status']}")
    lines.append(f"- Selected workflow: {contract['selected_workflow']}")
    lines.append(f"- Selected skills: {limited_join(contract['selected_skills'], limit=5) or 'none'}")
    lines.append(f"- Selected tools: {limited_join(contract['selected_tools'], limit=5) or 'none'}")
    lines.append(f"- Next action: {contract['next_action']}")
    lines.append(f"- Verification: {contract['verification']}")


def append_refusal_quality_lines(lines: list[str], summary: Any) -> None:
    if not isinstance(summary, dict) or summary.get("refusal_quality_status") != "actionable":
        return
    lines.append("")
    lines.append("Recovery:")
    blocker_reasons = summary.get("blocker_reasons") if isinstance(summary.get("blocker_reasons"), list) else []
    blocker_messages = summary.get("blocker_messages") if isinstance(summary.get("blocker_messages"), list) else []
    if blocker_reasons:
        lines.append(f"- Blocking reason: {limited_join([str(item) for item in blocker_reasons], limit=3)}")
    elif isinstance(summary.get("route_status"), str):
        lines.append(f"- Blocking reason: {summary['route_status']}")
    if blocker_messages:
        lines.append(f"- Detail: {inline_text(str(blocker_messages[0]), 260)}")
    missing = summary.get("missing_information") if isinstance(summary.get("missing_information"), list) else []
    if missing:
        lines.append(f"- Missing information: {limited_join([str(item) for item in missing], limit=4)}")
    if isinstance(summary.get("bounded_next_step"), str):
        lines.append(f"- Bounded next step: {inline_text(summary['bounded_next_step'], 300)}")
    alternatives = summary.get("safe_alternatives") if isinstance(summary.get("safe_alternatives"), list) else []
    if alternatives:
        lines.append(f"- Safe alternatives: {limited_join([str(item) for item in alternatives], limit=4)}")
    expectations = summary.get("evidence_expectations") if isinstance(summary.get("evidence_expectations"), list) else []
    if expectations:
        lines.append(f"- Evidence expected: {limited_join([str(item) for item in expectations], limit=4)}")
    if isinstance(summary.get("mutation_policy"), str):
        lines.append(f"- Mutation policy: {inline_text(summary['mutation_policy'], 260)}")


def append_skill_selection_summary_lines(lines: list[str], response: dict[str, Any]) -> None:
    explanation = skill_selection_explanation_for_response(response)
    if not explanation:
        return
    skills = explanation.get("skills") if isinstance(explanation.get("skills"), list) else []
    tools = explanation.get("tools") if isinstance(explanation.get("tools"), list) else []
    skill_summaries = []
    for item in skills[:5]:
        if not isinstance(item, dict):
            continue
        skill_id = item.get("skill_id")
        route_key = item.get("route_key")
        if isinstance(skill_id, str):
            skill_summaries.append(f"{skill_id} ({route_key})" if isinstance(route_key, str) and route_key else skill_id)
    tool_summaries = [str(item.get("tool_id")) for item in tools[:5] if isinstance(item, dict) and isinstance(item.get("tool_id"), str)]
    lines.append("")
    lines.append("Skill Selection:")
    lines.append(f"- Why: {inline_text(explanation.get('why'), 360)}")
    lines.append(f"- Route rules: {limited_join([str(rule) for rule in explanation.get('route_rules', [])], limit=5) or 'none'}")
    lines.append(
        f"- Confidence: {inline_text(explanation.get('confidence'), 40)}"
        f" ({limited_join([str(item) for item in explanation.get('confidence_reasons', [])], limit=4) or 'no reasons recorded'})"
    )
    lines.append(
        f"- Coverage entries: {limited_join([str(item) for item in explanation.get('coverage_entry_ids', [])], limit=5) or 'none'}"
    )
    lines.append(f"- Skills: {limited_join(skill_summaries, limit=5) or 'none'}")
    lines.append(f"- Tools: {limited_join(tool_summaries, limit=5) or 'none'}")
    rejected = explanation.get("rejected_candidates") if isinstance(explanation.get("rejected_candidates"), dict) else {}
    rejected_parts = []
    if rejected:
        rejected_parts.append(f"workflows {rejected.get('workflow_rejected_count', 0)}")
        rejected_parts.append(f"skills {rejected.get('skill_rejected_count', 0)}")
        rejected_parts.append(f"tools {rejected.get('tool_rejected_count', 0)}")
    lines.append(f"- Rejected candidates: {limited_join(rejected_parts, limit=3) or 'none'}")
    lines.append(f"- Grounded in: {limited_join([str(item) for item in explanation.get('grounding', [])], limit=5)}")


def append_context_source_summary_lines(lines: list[str], response: dict[str, Any]) -> None:
    explanation = context_source_explanation_for_response(response)
    if not explanation:
        return
    selected = explanation.get("selected") if isinstance(explanation.get("selected"), list) else []
    source_summaries = []
    for item in selected[:5]:
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        tools = item.get("tool_ids") if isinstance(item.get("tool_ids"), list) else []
        reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
        if isinstance(source_id, str):
            details = []
            if tools:
                details.append(f"tools {limited_join([str(tool) for tool in tools], limit=3)}")
            if reasons:
                details.append(f"reason {limited_join([str(reason) for reason in reasons], limit=2)}")
            source_summaries.append(f"{source_id} ({'; '.join(details)})" if details else source_id)
    rejected = explanation.get("rejected") if isinstance(explanation.get("rejected"), list) else []
    rejected_ids = [str(item.get("source_id")) for item in rejected[:5] if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
    layout = explanation.get("layout") if isinstance(explanation.get("layout"), dict) else {}
    budget = explanation.get("budget") if isinstance(explanation.get("budget"), dict) else {}
    lines.append("")
    lines.append("Context Sources:")
    lines.append(f"- Selected: {limited_join(source_summaries, limit=5) or 'none'}")
    lines.append(f"- Rejected: {limited_join(rejected_ids, limit=5) or 'none'}")
    lines.append(
        "- Layout: "
        f"{inline_text(layout.get('status'), 80)}; "
        f"supported files {layout.get('supported_file_count', 0)}; "
        f"scanned {layout.get('scanned_file_count', 0)} of {layout.get('scan_limit', 0)}"
    )
    lines.append(
        f"- Budget: sources {budget.get('max_selected_sources', 0)}, "
        f"scan files {budget.get('layout_scan_file_limit', 0)}"
    )
    lines.append(
        f"- Evidence files: {limited_join([str(item) for item in explanation.get('evidence_files', [])], limit=5) or 'none'}"
    )
    lines.append(f"- Gaps: {limited_join([str(item) for item in explanation.get('gaps', [])], limit=5) or 'none'}")
    lines.append(f"- Grounded in: {limited_join([str(item) for item in explanation.get('grounding', [])], limit=5)}")


def input_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        if not isinstance(name, str):
            continue
        role = record.get("role")
        values.append(f"{name} ({role})" if isinstance(role, str) and role else name)
    return limited_join(values)


def output_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if isinstance(record.get("value"), str):
            values.append(record["value"])
        elif isinstance(record.get("description"), str):
            values.append(record["description"])
        elif isinstance(record.get("symbols"), list):
            values.append(limited_join([inline_text(item, 80) for item in record["symbols"]], limit=3))
        else:
            values.append(inline_text(record, 160))
    return limited_join(values)


def side_effect_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind") if isinstance(record.get("kind"), str) else "effect"
        if isinstance(record.get("target"), str):
            values.append(f"{kind}: {record['target']}")
        elif isinstance(record.get("description"), str):
            values.append(record["description"])
        else:
            values.append(inline_text(record, 160))
    return limited_join(values)


def related_test_path_with_line(record: dict[str, Any]) -> str:
    path = record.get("path")
    if not isinstance(path, str) or not path:
        return ""
    direct = path_with_line(record)
    if direct != path:
        return direct
    evidence_refs = record.get("evidence_refs")
    if isinstance(evidence_refs, list):
        for ref in evidence_refs:
            if not isinstance(ref, dict):
                continue
            if ref.get("path") == path and isinstance(ref.get("line"), int):
                return f"{path}:{ref['line']}"
    source_refs = record.get("source_refs")
    if isinstance(source_refs, list):
        prefix = f"{path}:"
        for ref in source_refs:
            if not isinstance(ref, str) or not ref.startswith(prefix):
                continue
            tail = ref[len(prefix) :].split(":", 1)[0]
            if tail.isdigit():
                return f"{path}:{tail}"
    return path


def related_tests_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = related_test_path_with_line(record)
        if not path:
            continue
        suffix_parts: list[str] = []
        evidence_kind = record.get("evidence_kind")
        confidence = record.get("confidence")
        if isinstance(evidence_kind, str) and evidence_kind:
            suffix_parts.append(f"{evidence_kind} evidence")
        if isinstance(confidence, str) and confidence:
            suffix_parts.append(f"{confidence} confidence")
        markers = record.get("status_markers")
        if isinstance(markers, list) and markers:
            suffix_parts.append("markers: " + ", ".join(str(item) for item in markers[:3]))
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        values.append(f"{path}{suffix}")
    return limited_join(values)


def participating_files_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        if not isinstance(path, str):
            continue
        category = record.get("category")
        match_count = record.get("match_count")
        suffix_parts: list[str] = []
        if isinstance(category, str) and category:
            suffix_parts.append(category)
        if isinstance(match_count, int) and match_count:
            suffix_parts.append(f"{match_count} match(es)")
        relevance = record.get("relevance")
        if isinstance(relevance, dict) and isinstance(relevance.get("tier"), str):
            suffix_parts.append(f"{relevance['tier']} evidence")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        values.append(f"{path}{suffix}")
    return limited_join(values, limit=5)


def boundary_files_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        if not isinstance(path, str):
            continue
        role = record.get("role")
        reason = record.get("reason")
        suffix_parts: list[str] = []
        if isinstance(role, str) and role:
            suffix_parts.append(role)
        relevance = record.get("relevance")
        if isinstance(relevance, dict) and isinstance(relevance.get("tier"), str):
            suffix_parts.append(f"{relevance['tier']} evidence")
        if isinstance(reason, str) and reason:
            suffix_parts.append(inline_text(reason, 140))
        suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""
        values.append(f"{path}{suffix}")
    return limited_join(values, limit=5)


def unknowns_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        unknown = record.get("unknown")
        reason = record.get("reason")
        if isinstance(unknown, str):
            values.append(f"{unknown}: {reason}" if isinstance(reason, str) and reason else unknown)
    return limited_join(values, limit=4)


def usage_evidence_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        if not isinstance(path, str):
            continue
        role = record.get("role")
        match_count = record.get("match_count")
        suffix_parts: list[str] = []
        if isinstance(role, str) and role:
            suffix_parts.append(role)
        if isinstance(match_count, int) and match_count:
            suffix_parts.append(f"{match_count} match(es)")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        values.append(f"{path}{suffix}")
    return limited_join(values, limit=5)


def risks_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        risk = record.get("risk")
        if not isinstance(risk, str):
            continue
        level = record.get("level")
        reason = record.get("reason")
        prefix = f"{risk} ({level})" if isinstance(level, str) and level else risk
        values.append(f"{prefix}: {reason}" if isinstance(reason, str) and reason else prefix)
    return limited_join(values, limit=4)


def gaps_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        gap = record.get("gap")
        reason = record.get("reason")
        if isinstance(gap, str):
            values.append(f"{gap}: {reason}" if isinstance(reason, str) and reason else gap)
    return limited_join(values, limit=4)


def source_refs_summary(records: Any, *, limit: int = INLINE_ARTIFACT_ITEM_LIMIT) -> str:
    if not isinstance(records, list):
        return ""
    values = [path_with_line(record) for record in records if isinstance(record, dict)]
    return limited_join(values, limit=limit)


def data_model_fields_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        definition = inline_text(item.get("definition"), 120)
        path = item.get("path")
        line = item.get("line")
        ref = ""
        if isinstance(path, str) and isinstance(line, int):
            ref = f" ({path}:{line})"
        elif isinstance(path, str):
            ref = f" ({path})"
        values.append(f"{item['name']}: {definition}{ref}" if definition else f"{item['name']}{ref}")
    return limited_join(values, limit=DATA_MODEL_FIELD_ITEM_LIMIT)


def operation_target(operation: dict[str, Any]) -> str:
    path = operation.get("path")
    return path if isinstance(path, str) and path else "unknown"


def packet_operation_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for operation in records:
        if not isinstance(operation, dict):
            continue
        kind = operation.get("kind") if isinstance(operation.get("kind"), str) else "operation"
        path = operation_target(operation)
        if kind == "replace_text":
            old = inline_text(operation.get("old"), 120)
            new = inline_text(operation.get("new"), 120)
            values.append(f"{kind} {path} old={old} new={new}")
        elif kind == "append_text":
            content = inline_text(operation.get("content"), 180)
            values.append(f"{kind} {path} content={content}")
        else:
            values.append(f"{kind} {path}")
    return limited_join(values, limit=3)


def packet_operation_targets(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values = [operation_target(operation) for operation in records if isinstance(operation, dict)]
    return limited_join(values, limit=3)


def verification_commands_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for command_record in records:
        if isinstance(command_record, dict):
            values.append(command_text(command_record.get("command")))
        else:
            values.append(command_text(command_record))
    return limited_join(values, limit=3)


def safety_checks_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        check = record.get("check")
        status = record.get("status")
        if not isinstance(check, str):
            continue
        values.append(f"{check}={status}" if isinstance(status, str) and status else check)
    return limited_join(values, limit=4)


def source_mutation_from_safety_checks(records: Any) -> str | None:
    if not isinstance(records, list):
        return None
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("check") == "draft_only" and record.get("apply_allowed") is False:
            return "false"
    return None


def blockers_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        reason = record.get("reason")
        message = record.get("message")
        if isinstance(reason, str) and isinstance(message, str):
            values.append(f"{reason}: {message}")
        elif isinstance(reason, str):
            values.append(reason)
    return limited_join(values, limit=3)


def append_code_explanation_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target") if isinstance(artifact.get("target"), dict) else {}
    symbol = target.get("symbol") if isinstance(target.get("symbol"), str) else None
    path = target.get("path") if isinstance(target.get("path"), str) else None
    target_label = f"{symbol} in {path}" if symbol and path else symbol or path
    if not target_label:
        return False
    lines.append(f"- Target: {target_label}")
    if isinstance(artifact.get("status"), str):
        lines.append(f"- Status: {artifact['status']}")
    if isinstance(artifact.get("summary"), str):
        lines.append(f"- Summary: {inline_text(artifact['summary'])}")
    inputs = input_summary(artifact.get("key_inputs"))
    if inputs:
        lines.append(f"- Inputs: {inputs}")
    outputs = output_summary(artifact.get("outputs"))
    if outputs:
        lines.append(f"- Outputs: {outputs}")
    side_effects = side_effect_summary(artifact.get("side_effects"))
    if side_effects:
        lines.append(f"- Side effects: {side_effects}")
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    lines.append("- Source mutation: false")
    return True


def finding_refs_summary(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    values = [path_with_line(item) for item in records if isinstance(item, dict)]
    return limited_join(values, limit=12)


def append_code_quality_review_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target") if isinstance(artifact.get("target"), dict) else {}
    paths = target.get("paths") if isinstance(target.get("paths"), list) else []
    path_values = [item for item in paths if isinstance(item, str)]
    if path_values:
        lines.append(f"- Target: {limited_join(path_values, limit=6)}")
    status = artifact.get("status")
    if isinstance(status, str) and status:
        lines.append(f"- Status: {status}")
    mode = artifact.get("review_mode")
    if isinstance(mode, str) and mode:
        lines.append(f"- Review mode: {mode}")
    recommendation = artifact.get("recommendation")
    if isinstance(recommendation, str) and recommendation:
        lines.append(f"- Recommendation: {recommendation}")
    no_finding_reason = artifact.get("no_finding_reason")
    if isinstance(no_finding_reason, str) and no_finding_reason:
        lines.append(f"- Findings: none supported - {inline_text(no_finding_reason, 280)}")
    findings = artifact.get("findings")
    if isinstance(findings, list) and findings:
        lines.append("- Findings:")
        for finding in findings[:3]:
            if not isinstance(finding, dict):
                continue
            finding_id = finding.get("id") if isinstance(finding.get("id"), str) else "finding"
            severity = finding.get("severity") if isinstance(finding.get("severity"), str) else "unknown"
            category = finding.get("category") if isinstance(finding.get("category"), str) else "code_quality"
            title = inline_text(finding.get("title"), 220)
            lines.append(f"  - {finding_id} [{severity}/{category}]: {title}")
            refs = finding_refs_summary(finding.get("evidence_refs"))
            if refs:
                lines.append(f"    Evidence: {refs}")
            impact = inline_text(finding.get("impact"), 240)
            if impact:
                lines.append(f"    Impact: {impact}")
            remediation = inline_text(finding.get("bounded_remediation"), 240)
            if remediation:
                lines.append(f"    Bounded remediation: {remediation}")
    checklist = artifact.get("checklist")
    if isinstance(checklist, list) and checklist:
        values = [inline_text(item, 180) for item in checklist if isinstance(item, str)]
        lines.append(f"- Checklist: {limited_join(values, limit=6)}")
    comparison = artifact.get("behavior_comparison")
    if isinstance(comparison, list) and comparison:
        values: list[str] = []
        for item in comparison:
            if isinstance(item, dict):
                values.append(inline_text(item, 180))
        lines.append(f"- Behavior comparison: {limited_join(values, limit=4)}")
    test_cases = artifact.get("test_cases")
    if isinstance(test_cases, list) and test_cases:
        values = [inline_text(item, 120) for item in test_cases if isinstance(item, str)]
        lines.append(f"- Test cases: {limited_join(values, limit=6)}")
    rejected = artifact.get("rejected_false_positives")
    if isinstance(rejected, list) and rejected:
        values: list[str] = []
        for item in rejected:
            if not isinstance(item, dict):
                continue
            claim = inline_text(item.get("claim"), 120)
            reason = inline_text(item.get("reason"), 180)
            if claim and reason:
                values.append(f"{claim}: {reason}")
            elif claim:
                values.append(claim)
        joined = limited_join(values, limit=4)
        if joined:
            lines.append(f"- Rejected false positives: {joined}")
    insufficient = artifact.get("insufficient_evidence")
    if isinstance(insufficient, list) and insufficient:
        values = [inline_text(item, 160) for item in insufficient if isinstance(item, str)]
        lines.append(f"- Insufficient evidence: {limited_join(values, limit=4)}")
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def judgment_records_summary(records: Any, *, label_key: str = "title", limit: int = 5) -> str:
    if not isinstance(records, list):
        return ""
    values: list[str] = []
    for item in records:
        if isinstance(item, str):
            values.append(inline_text(item, 180))
            continue
        if not isinstance(item, dict):
            continue
        label = item.get(label_key)
        if not isinstance(label, str) or not label:
            label = item.get("name") if isinstance(item.get("name"), str) else item.get("risk")
        if not isinstance(label, str) or not label:
            label = item.get("item") if isinstance(item.get("item"), str) else item.get("claim")
        detail = item.get("reason")
        if not isinstance(detail, str) or not detail:
            detail = item.get("impact") if isinstance(item.get("impact"), str) else item.get("validation")
        if isinstance(label, str) and label and isinstance(detail, str) and detail:
            values.append(f"{inline_text(label, 100)}: {inline_text(detail, 160)}")
        elif isinstance(label, str) and label:
            values.append(inline_text(label, 180))
    return limited_join(values, limit=limit)


def append_engineering_judgment_review_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target") if isinstance(artifact.get("target"), dict) else {}
    paths = target.get("paths") if isinstance(target.get("paths"), list) else []
    path_values = [item for item in paths if isinstance(item, str)]
    if path_values:
        lines.append(f"- Target: {limited_join(path_values, limit=6)}")
    status = artifact.get("status")
    if isinstance(status, str) and status:
        lines.append(f"- Status: {status}")
    mode = artifact.get("review_mode")
    if isinstance(mode, str) and mode:
        lines.append(f"- Review mode: {mode}")
    question = inline_text(artifact.get("question"), 240)
    if question:
        lines.append(f"- Question: {question}")
    assessment = artifact.get("direct_assessment")
    if isinstance(assessment, dict):
        recommendation = inline_text(assessment.get("recommendation"), 260)
        decision = inline_text(assessment.get("decision"), 180)
        confidence = inline_text(assessment.get("confidence"), 80)
        if recommendation:
            suffix = f" (decision: {decision})" if decision else ""
            if confidence:
                suffix = f"{suffix} (confidence: {confidence})"
            lines.append(f"- Recommendation: {recommendation}{suffix}")
        reason = inline_text(assessment.get("reason"), 260)
        if reason:
            lines.append(f"- Reason: {reason}")
    evidence = judgment_records_summary(artifact.get("evidence_used"), label_key="path", limit=5)
    if evidence:
        lines.append(f"- Evidence used: {evidence}")
    alternatives = judgment_records_summary(artifact.get("alternatives"), label_key="name", limit=4)
    if alternatives:
        lines.append(f"- Alternatives: {alternatives}")
    tradeoffs = judgment_records_summary(artifact.get("tradeoffs"), label_key="dimension", limit=5)
    if tradeoffs:
        lines.append(f"- Tradeoffs: {tradeoffs}")
    risks = judgment_records_summary(artifact.get("risks_and_blockers"), label_key="risk", limit=5)
    if risks:
        lines.append(f"- Risks/blockers: {risks}")
    debt = judgment_records_summary(artifact.get("technical_debt"), label_key="item", limit=5)
    if debt:
        lines.append(f"- Technical debt: {debt}")
    validation = judgment_records_summary(artifact.get("validation_steps"), label_key="step", limit=6)
    if validation:
        lines.append(f"- Validation: {validation}")
    unknowns = judgment_records_summary(artifact.get("unknowns"), label_key="unknown", limit=4)
    if unknowns:
        lines.append(f"- Unknowns: {unknowns}")
    rejected = artifact.get("rejected_claims")
    if isinstance(rejected, list) and rejected:
        values: list[str] = []
        for item in rejected:
            if not isinstance(item, dict):
                continue
            claim = inline_text(item.get("claim"), 120)
            reason = inline_text(item.get("reason"), 180)
            if claim and reason:
                values.append(f"{claim}: {reason}")
            elif claim:
                values.append(claim)
        joined = limited_join(values, limit=4)
        if joined:
            lines.append(f"- Rejected claims: {joined}")
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=24)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_behavior_existence_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    answer = artifact.get("answer")
    if not isinstance(answer, str):
        return False
    confidence = artifact.get("confidence")
    result = answer
    if isinstance(confidence, str) and confidence:
        result = f"{answer} (confidence: {confidence})"
    lines.append(f"- Result: {result}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    evidence = artifact.get("evidence_files")
    if isinstance(evidence, list):
        values = [path_with_line(item) for item in evidence if isinstance(item, dict)]
        joined = limited_join(values)
        if joined:
            lines.append(f"- Evidence files: {joined}")
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    return True


def append_endpoint_route_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
    handlers = artifact.get("handlers")
    values: list[str] = []
    if isinstance(handlers, list):
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            path = path_with_line(handler)
            role = handler.get("role")
            evidence = handler.get("evidence")
            label = path
            if isinstance(role, str) and role:
                label = f"{label} ({role})" if label else role
            if isinstance(evidence, str) and evidence:
                label = f"{label}: {inline_text(evidence, 140)}" if label else inline_text(evidence, 140)
            values.append(label)
    joined = limited_join(values)
    if joined:
        lines.append(f"- Handler files: {joined}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_message_source_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target message: {inline_text(target, 180)}")
    sources = artifact.get("sources")
    values: list[str] = []
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            path = path_with_line(source)
            role = source.get("role")
            text = source.get("text")
            label = path
            if isinstance(role, str) and role:
                label = f"{label} ({role})" if label else role
            if isinstance(text, str) and text:
                label = f"{label}: {inline_text(text, 140)}" if label else inline_text(text, 140)
            values.append(label)
    joined = limited_join(values)
    if joined:
        lines.append(f"- Sources: {joined}")
    assessment = artifact.get("user_facing_assessment")
    if isinstance(assessment, dict):
        status = assessment.get("status")
        reason = assessment.get("reason")
        if isinstance(status, str) and status:
            suffix = f" - {inline_text(reason, 180)}" if isinstance(reason, str) and reason else ""
            lines.append(f"- User-facing: {status}{suffix}")
        targets = related_tests_summary(assessment.get("recommended_test_targets"))
        if targets:
            lines.append(f"- Test targets: {targets}")
        else:
            lines.append("- Test targets: no bounded related tests found")
        verification = verification_commands_summary(assessment.get("verification_commands"))
        if verification:
            lines.append(f"- Verification: {verification}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_module_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target") if isinstance(artifact.get("target"), dict) else {}
    path = target.get("path") if isinstance(target.get("path"), str) else None
    if path:
        lines.append(f"- Target module: {path}")
    if isinstance(artifact.get("summary"), str):
        lines.append(f"- Summary: {inline_text(artifact['summary'])}")
    responsibilities = artifact.get("responsibilities")
    if isinstance(responsibilities, list):
        values = [
            inline_text(item.get("description"), 180)
            for item in responsibilities
            if isinstance(item, dict) and isinstance(item.get("description"), str)
        ]
        joined = limited_join(values, limit=3)
        if joined:
            lines.append(f"- Responsibilities: {joined}")
    definitions = artifact.get("definitions")
    if isinstance(definitions, list):
        values = [
            f"{item.get('name')} ({item.get('kind')})"
            for item in definitions
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        joined = limited_join(values)
        if joined:
            lines.append(f"- Definitions: {joined}")
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_data_model_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target model/schema: {target}")
    fields = artifact.get("fields")
    if isinstance(fields, list):
        joined = data_model_fields_summary(fields)
        if joined:
            lines.append(f"- Fields: {joined}")
    files = artifact.get("model_files")
    if isinstance(files, list):
        joined = limited_join([inline_text(item, 120) for item in files if isinstance(item, str)])
        if joined:
            lines.append(f"- Model files: {joined}")
    symbols = artifact.get("model_symbols")
    if isinstance(symbols, list):
        symbol_values: list[str] = []
        for symbol in symbols:
            if not isinstance(symbol, dict):
                continue
            name = symbol.get("name")
            if not isinstance(name, str) or not name:
                continue
            kind = symbol.get("kind")
            path = path_with_line(symbol)
            label = name
            if isinstance(kind, str) and kind:
                label = f"{label} ({kind})"
            if path:
                label = f"{label} at {path}"
            symbol_values.append(label)
        joined = limited_join(symbol_values, limit=8)
        if joined:
            lines.append(f"- Model symbols: {joined}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_table_read_write_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    if artifact.get("status") == "not_requested":
        return False
    target = artifact.get("target_table")
    if isinstance(target, str) and target:
        lines.append(f"- Target table: {target}")
    summary = artifact.get("access_summary") if isinstance(artifact.get("access_summary"), dict) else {}
    lines.append(
        "- Access counts: "
        f"definitions={summary.get('definition_count', 0)}, "
        f"reads={summary.get('read_count', 0)}, "
        f"writes={summary.get('write_count', 0)}"
    )
    for label, key in (
        ("Definition sites", "definition_sites"),
        ("Read sites", "read_sites"),
        ("Write sites", "write_sites"),
    ):
        sites = artifact.get(key)
        if not isinstance(sites, list):
            continue
        values = []
        for site in sites:
            if not isinstance(site, dict):
                continue
            path = path_with_line(site)
            evidence = site.get("evidence")
            label_text = path
            if isinstance(evidence, str) and evidence:
                label_text = f"{label_text}: {inline_text(evidence, 120)}" if label_text else inline_text(evidence, 120)
            if label_text:
                values.append(label_text)
        joined = limited_join(values)
        if joined:
            lines.append(f"- {label}: {joined}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_coverage_gap_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
    covered_tests = artifact.get("covered_tests")
    if isinstance(covered_tests, list):
        tests = related_tests_summary(covered_tests)
        lines.append(f"- Related tests: {tests or 'none found in bounded evidence'}")
    source_files = artifact.get("source_files")
    if isinstance(source_files, list):
        values = [
            inline_text(item.get("path"), 140)
            for item in source_files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        joined = limited_join(values)
        if joined:
            lines.append(f"- Source files: {joined}")
    gaps = gaps_summary(artifact.get("coverage_gaps"))
    lines.append(f"- Coverage gaps: {gaps or 'none reported'}")
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Recommended commands: {verification}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_documentation_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
    docs = artifact.get("documentation_files")
    if isinstance(docs, list):
        values: list[str] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            path = path_with_line(doc)
            role = doc.get("role")
            snippet = doc.get("snippet")
            label = path
            if isinstance(role, str) and role:
                label = f"{label} ({role})" if label else role
            if isinstance(snippet, str) and snippet:
                label = f"{label}: {inline_text(snippet, 140)}" if label else inline_text(snippet, 140)
            values.append(label)
        lines.append(f"- Documentation files: {limited_join(values) or 'none found in bounded evidence'}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_cli_entrypoint_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target entrypoint: {inline_text(target, 180)}")
    entrypoints = artifact.get("entrypoints")
    values: list[str] = []
    if isinstance(entrypoints, list):
        for entrypoint in entrypoints:
            if not isinstance(entrypoint, dict):
                continue
            path = path_with_line(entrypoint)
            kind = entrypoint.get("kind")
            command = command_text(entrypoint.get("command"))
            label = path
            if isinstance(kind, str) and kind:
                label = f"{label} ({kind})" if label else kind
            if command:
                label = f"{label}: {command}" if label else command
            values.append(label)
    lines.append(f"- Entrypoints: {limited_join(values) or 'none found in bounded evidence'}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_configuration_effect_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target config: {inline_text(target, 180)}")
    effects = artifact.get("runtime_effects")
    if isinstance(effects, list):
        values = [
            inline_text(item.get("summary"), 180)
            for item in effects
            if isinstance(item, dict) and isinstance(item.get("summary"), str)
        ]
        lines.append(f"- Runtime effect: {limited_join(values, limit=3) or 'unknown from bounded evidence'}")
    references = artifact.get("references")
    if isinstance(references, list):
        values: list[str] = []
        for reference in references:
            if not isinstance(reference, dict):
                continue
            path = path_with_line(reference)
            role = reference.get("role")
            text = reference.get("text")
            label = path
            if isinstance(role, str) and role:
                label = f"{label} ({role})" if label else role
            if isinstance(text, str) and text:
                label = f"{label}: {inline_text(text, 140)}" if label else inline_text(text, 140)
            values.append(label)
        joined = limited_join(values)
        if joined:
            lines.append(f"- References: {joined}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_local_change_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    status = artifact.get("status")
    if isinstance(status, str) and status:
        lines.append(f"- Local change status: {status}")
    git_status = artifact.get("git_status")
    lines.append(f"- Git status: {inline_text(git_status, 220) if isinstance(git_status, str) and git_status else 'not available'}")
    commits = artifact.get("recent_commits")
    commit_values: list[str] = []
    if isinstance(commits, list):
        commit_values = [
            inline_text(item.get("summary"), 160)
            for item in commits
            if isinstance(item, dict) and isinstance(item.get("summary"), str)
        ]
    lines.append(f"- Recent commits: {limited_join(commit_values) or 'not available'}")
    changed_files = artifact.get("changed_files")
    if isinstance(changed_files, list):
        values = [
            f"{item.get('path')} ({item.get('status')})"
            for item in changed_files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        lines.append(f"- Changed files: {limited_join(values) or 'none reported'}")
    if isinstance(artifact.get("diff_stat"), str) and artifact["diff_stat"]:
        lines.append(f"- Diff stat: {inline_text(artifact['diff_stat'], 220)}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_dependency_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
    imports = artifact.get("imports")
    if isinstance(imports, list):
        grouped: dict[str, dict[str, Any]] = {}
        for item in imports:
            if not isinstance(item, dict):
                continue
            module = item.get("module")
            name = item.get("name")
            if not isinstance(module, str) or not module:
                continue
            record = grouped.setdefault(module, {"names": [], "first_ref": path_with_line(item)})
            if isinstance(name, str) and name and name not in record["names"]:
                record["names"].append(name)
        project_modules = [module for module in grouped if "." in module]
        other_modules = [module for module in grouped if "." not in module]
        values: list[str] = []
        for module in [*project_modules, *other_modules]:
            record = grouped[module]
            names = record["names"]
            if len(names) == 1:
                label = f"{module}.{names[0]}"
            elif names:
                label = f"{module}.{names[0]}, {names[1]}, +{len(names) - 2} more" if len(names) > 2 else f"{module}.{names[0]}, {names[1]}"
            else:
                label = module
            ref = record.get("first_ref")
            values.append(f"{label} ({ref})" if isinstance(ref, str) and ref else label)
        joined = limited_join(values, limit=10)
        if joined:
            lines.append(f"- Imports: {joined}")
    relationships = artifact.get("relationships")
    if isinstance(relationships, list) and not imports:
        values = [
            f"{path_with_line(item)}: {inline_text(item.get('explanation'), 140)}"
            for item in relationships
            if isinstance(item, dict)
        ]
        joined = limited_join(values)
        if joined:
            lines.append(f"- Import relationships: {joined}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    source_refs = source_refs_summary(artifact.get("source_refs"))
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_usage_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if not isinstance(target, str) or not target:
        return False
    lines.append(f"- Target: {target}")
    lines.append(
        f"- Usage count: {artifact.get('usage_count', 0)} across {artifact.get('group_count', 0)} file(s)"
    )
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    groups = artifact.get("groups")
    if isinstance(groups, list):
        values: list[str] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            path = group.get("path")
            if not isinstance(path, str):
                continue
            summary = group.get("summary") if isinstance(group.get("summary"), str) else ""
            values.append(f"{path} ({group.get('usage_count', 0)}): {inline_text(summary, 160)}")
        joined = limited_join(values)
        if joined:
            lines.append(f"- Files: {joined}")
    return True


def append_configuration_lookup_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    target = artifact.get("target")
    if not isinstance(target, str) or not target:
        return False
    lines.append(f"- Target: {target}")
    lines.append(
        f"- References: {artifact.get('reference_count', 0)} across {artifact.get('group_count', 0)} file(s)"
    )
    groups = artifact.get("groups")
    if isinstance(groups, list):
        values: list[str] = []
        runtime_effects: list[str] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            path = group.get("path")
            if not isinstance(path, str):
                continue
            roles = group.get("roles") if isinstance(group.get("roles"), list) else []
            values.append(f"{path} ({', '.join(str(role) for role in roles)})")
            references = group.get("references") if isinstance(group.get("references"), list) else []
            for reference in references:
                if isinstance(reference, dict) and isinstance(reference.get("likely_runtime_effect"), str):
                    runtime_effects.append(reference["likely_runtime_effect"])
        joined = limited_join(values)
        if joined:
            lines.append(f"- Files: {joined}")
        effects = limited_join([inline_text(item, 180) for item in runtime_effects], limit=2)
        if effects:
            lines.append(f"- Runtime effect: {effects}")
    if isinstance(artifact.get("reason"), str):
        lines.append(f"- Reason: {inline_text(artifact['reason'])}")
    return True


def append_defect_diagnosis_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 220)}")
        added = True
    status = artifact.get("status")
    if isinstance(status, str) and status:
        lines.append(f"- Status: {status}")
        added = True
    observed = artifact.get("observed_failure") if isinstance(artifact.get("observed_failure"), dict) else {}
    observed_summary = observed.get("summary")
    if isinstance(observed_summary, str) and observed_summary:
        lines.append(f"- Observed failure: {inline_text(observed_summary, 260)}")
        added = True
    primary_error = observed.get("primary_error") if isinstance(observed.get("primary_error"), dict) else {}
    error_type = primary_error.get("type") if isinstance(primary_error.get("type"), str) else None
    error_message = primary_error.get("message") if isinstance(primary_error.get("message"), str) else None
    if error_type or error_message:
        lines.append(f"- Primary error: {inline_text(': '.join(item for item in [error_type, error_message] if item), 260)}")
        added = True
    failed_tests = related_tests_summary(observed.get("failed_tests"))
    if failed_tests:
        lines.append(f"- Failed tests: {failed_tests}")
        added = True
    first_command = observed.get("first_failing_command") if isinstance(observed.get("first_failing_command"), dict) else {}
    rendered_first = command_text(first_command.get("command")) if first_command else ""
    if rendered_first:
        lines.append(f"- First failing command: {rendered_first}")
        added = True
    cause = artifact.get("likely_root_cause") if isinstance(artifact.get("likely_root_cause"), dict) else {}
    cause_summary = cause.get("summary") if isinstance(cause.get("summary"), str) else None
    confidence = cause.get("confidence") if isinstance(cause.get("confidence"), str) else None
    if cause_summary:
        suffix = f" (confidence: {confidence})" if confidence else ""
        lines.append(f"- Likely root cause: {inline_text(cause_summary, 320)}{suffix}")
        added = True
    reproduction = artifact.get("reproduction_steps")
    if isinstance(reproduction, list):
        values: list[str] = []
        for item in reproduction:
            if not isinstance(item, dict) or not isinstance(item.get("step"), str):
                continue
            detail_parts: list[str] = []
            path = item.get("path")
            if isinstance(path, str) and path:
                detail_parts.append(path)
            test_name = item.get("test_name")
            if isinstance(test_name, str) and test_name:
                detail_parts.append(test_name)
            command = command_text(item.get("command")) if item.get("command") else ""
            if command:
                detail_parts.append(command)
            detail = f" ({'; '.join(detail_parts)})" if detail_parts else ""
            values.append(f"{item['step']}{detail}")
        joined = limited_join(values, limit=4)
        if joined:
            lines.append(f"- Reproduction steps: {joined}")
            added = True
    test_levels = artifact.get("test_levels")
    if isinstance(test_levels, list):
        for level in test_levels[:4]:
            if not isinstance(level, dict):
                continue
            level_name = first_string(level.get("level"), level.get("tier")) or "test"
            commands = verification_commands_summary(level.get("commands"))
            rationale = level.get("rationale") if isinstance(level.get("rationale"), str) else ""
            covered = level.get("covered_risk") if isinstance(level.get("covered_risk"), str) else ""
            confidence = level.get("confidence") if isinstance(level.get("confidence"), str) else ""
            if "smallest" in level_name:
                label = "Smallest test"
            elif level_name in {"broad", "broader_regression"} or "broad" in level_name:
                label = "Broader regression test"
            else:
                label = f"{level_name.title()} test"
            parts = [part for part in (commands, rationale, covered, f"confidence: {confidence}" if confidence else "") if part]
            if parts:
                lines.append(f"- {label}: {inline_text('; '.join(parts), 360)}")
                added = True
    observability = artifact.get("observability_evidence")
    if isinstance(observability, list):
        values: list[str] = []
        for item in observability:
            if not isinstance(item, dict):
                continue
            signal = item.get("signal")
            location = item.get("location")
            why = item.get("why")
            if not isinstance(signal, str):
                continue
            label = signal
            if isinstance(location, str) and location:
                label = f"{label} @ {location}"
            if isinstance(why, str) and why:
                label = f"{label}: {why}"
            values.append(label)
        joined = limited_join(values, limit=4)
        if joined:
            lines.append(f"- Observability evidence: {joined}")
            added = True
    missing = gaps_summary(artifact.get("missing_data"))
    if missing:
        lines.append(f"- Missing data: {missing}")
        added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    evidence_files = participating_files_summary(artifact.get("evidence_files"))
    if evidence_files:
        lines.append(f"- Evidence files: {evidence_files}")
        added = True
    refs = source_refs_summary(artifact.get("source_refs"), limit=8)
    if refs:
        lines.append(f"- Source refs: {refs}")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_ci_failure_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    first = artifact.get("first_failing_command") if isinstance(artifact.get("first_failing_command"), dict) else {}
    command = first.get("command") if isinstance(first.get("command"), str) else None
    if command:
        lines.append(f"- First failing command: {inline_text(command, 180)}")
    error = artifact.get("primary_error") if isinstance(artifact.get("primary_error"), dict) else {}
    error_type = error.get("type") if isinstance(error.get("type"), str) else None
    error_message = error.get("message") if isinstance(error.get("message"), str) else None
    if error_type or error_message:
        lines.append(f"- Primary error: {inline_text(': '.join(item for item in [error_type, error_message] if item))}")
    if isinstance(artifact.get("likely_cause"), str):
        lines.append(f"- Likely cause: {inline_text(artifact['likely_cause'])}")
    next_command = artifact.get("next_local_command") if isinstance(artifact.get("next_local_command"), dict) else {}
    rendered = command_text(next_command.get("command")) if next_command else ""
    if rendered:
        lines.append(f"- Next local command: {rendered}")
    failed_tests = related_tests_summary(artifact.get("failed_tests"))
    if failed_tests:
        lines.append(f"- Failed tests: {failed_tests}")
    evidence = participating_files_summary(artifact.get("evidence_files"))
    if evidence:
        lines.append(f"- Evidence files: {evidence}")
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    return bool(lines)


def append_test_failure_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    failed_tests = artifact.get("failed_tests")
    if isinstance(failed_tests, list):
        values: list[str] = []
        for failed in failed_tests:
            if not isinstance(failed, dict):
                continue
            path = failed.get("path")
            if not isinstance(path, str):
                continue
            test_name = failed.get("test_name")
            values.append(f"{path}::{test_name}" if isinstance(test_name, str) and test_name else path)
        joined = limited_join(values)
        if joined:
            lines.append(f"- Failed tests: {joined}")
    error = artifact.get("primary_error") if isinstance(artifact.get("primary_error"), dict) else {}
    error_type = error.get("type") if isinstance(error.get("type"), str) else None
    error_message = error.get("message") if isinstance(error.get("message"), str) else None
    if error_type or error_message:
        lines.append(f"- Primary error: {inline_text(': '.join(item for item in [error_type, error_message] if item))}")
    if isinstance(artifact.get("likely_cause"), str):
        lines.append(f"- Likely cause: {inline_text(artifact['likely_cause'])}")
    root_cause = artifact.get("root_cause_hypothesis")
    if isinstance(root_cause, dict) and isinstance(root_cause.get("summary"), str):
        confidence = root_cause.get("confidence")
        suffix = f" (confidence: {confidence})" if isinstance(confidence, str) and confidence else ""
        lines.append(f"- Root cause hypothesis: {inline_text(root_cause['summary'])}{suffix}")
    fix_plan = artifact.get("smallest_safe_fix_plan")
    if isinstance(fix_plan, list):
        values: list[str] = []
        for step in fix_plan:
            if not isinstance(step, dict) or not isinstance(step.get("step"), str):
                continue
            path = step.get("path")
            suffix = f" ({path})" if isinstance(path, str) and path else ""
            values.append(f"{step['step']}{suffix}")
        joined = limited_join(values, limit=3)
        if joined:
            lines.append(f"- Smallest safe fix plan: {joined}")
    commands = artifact.get("verification_commands")
    if isinstance(commands, list):
        values: list[str] = []
        for command in commands:
            if isinstance(command, dict):
                values.append(command_text(command.get("command")))
            else:
                values.append(command_text(command))
        joined = limited_join(values, limit=3)
        if joined:
            lines.append(f"- Verification: {joined}")
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
    steps = artifact.get("next_inspection_steps")
    if isinstance(steps, list):
        values: list[str] = []
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("step"), str):
                continue
            path = step.get("path")
            suffix = f" ({path})" if isinstance(path, str) and path else ""
            values.append(f"{step['step']}{suffix}")
        joined = limited_join(values, limit=3)
        if joined:
            lines.append(f"- Next steps: {joined}")
    return len(lines) > 0


def append_multi_file_behavior_investigation_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    beginning = artifact.get("beginning_point")
    if isinstance(beginning, dict):
        beginning_path = path_with_line(beginning)
        if beginning_path:
            lines.append(f"- Beginning point: {beginning_path}")
            added = True
    participating = participating_files_summary(artifact.get("participating_files"))
    if participating:
        lines.append(f"- Participating files: {participating}")
        added = True
    usages = usage_evidence_summary(artifact.get("usage_evidence"))
    if usages:
        lines.append(f"- Callers/usages: {usages}")
        added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
        added = True
    risks = risks_summary(artifact.get("risks"))
    if risks:
        lines.append(f"- Risks: {risks}")
        added = True
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
        added = True
    else:
        lines.append("- Verification: no bounded command found")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_dependency_impact_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
        added = True
    impacted = participating_files_summary(artifact.get("impacted_files"))
    if impacted:
        lines.append(f"- Impacted files: {impacted}")
        added = True
    usages = usage_evidence_summary(artifact.get("callers_usages"))
    if usages:
        lines.append(f"- Callers/usages: {usages}")
        added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    risk_level = artifact.get("risk_level")
    if isinstance(risk_level, str) and risk_level:
        lines.append(f"- Risk level: {risk_level}")
        added = True
    risks = risks_summary(artifact.get("risks"))
    if risks:
        lines.append(f"- Risks: {risks}")
        added = True
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
        added = True
    else:
        lines.append("- Verification: no bounded command found")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_test_selection_plan_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
        added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    else:
        lines.append("- Related tests: none found in bounded evidence")
        added = True
    tiers = artifact.get("command_tiers")
    if isinstance(tiers, list):
        rationale_values: list[str] = []
        risk_values: list[str] = []
        for tier in tiers:
            if not isinstance(tier, dict):
                continue
            tier_name = tier.get("tier")
            if not isinstance(tier_name, str):
                continue
            commands = verification_commands_summary(tier.get("commands"))
            label = {
                "smallest": "Smallest command",
                "medium": "Medium command",
                "broad": "Broad command",
            }.get(tier_name, f"{tier_name.title()} command")
            if commands:
                lines.append(f"- {label}: {commands}")
                added = True
            rationale = tier.get("rationale")
            if isinstance(rationale, str) and rationale:
                rationale_values.append(f"{tier_name}: {rationale}")
            covered_risk = tier.get("covered_risk")
            if isinstance(covered_risk, str) and covered_risk:
                risk_values.append(f"{tier_name}: {covered_risk}")
        rationale = limited_join(rationale_values, limit=3)
        if rationale:
            lines.append(f"- Rationale: {rationale}")
            added = True
        risks = limited_join(risk_values, limit=3)
        if risks:
            lines.append(f"- Covered risks: {risks}")
            added = True
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
        added = True
    confidence = artifact.get("confidence")
    if isinstance(confidence, str) and confidence:
        lines.append(f"- Confidence: {confidence}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_runtime_error_diagnosis_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    error = artifact.get("observed_error") if isinstance(artifact.get("observed_error"), dict) else {}
    error_type = error.get("type") if isinstance(error.get("type"), str) else None
    error_message = error.get("message") if isinstance(error.get("message"), str) else None
    if error_type or error_message:
        lines.append(f"- Observed error: {inline_text(': '.join(item for item in [error_type, error_message] if item))}")
        added = True
    cause = artifact.get("likely_cause")
    if isinstance(cause, dict) and isinstance(cause.get("summary"), str):
        confidence = cause.get("confidence")
        suffix = f" (confidence: {confidence})" if isinstance(confidence, str) and confidence else ""
        lines.append(f"- Likely cause: {inline_text(cause['summary'])}{suffix}")
        added = True
    evidence = participating_files_summary(artifact.get("evidence_files"))
    if evidence:
        lines.append(f"- Evidence files: {evidence}")
        added = True
    steps = artifact.get("next_inspection_steps")
    if isinstance(steps, list):
        values: list[str] = []
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("step"), str):
                continue
            path = step.get("path")
            suffix = f" ({path})" if isinstance(path, str) and path else ""
            values.append(f"{step['step']}{suffix}")
        joined = limited_join(values, limit=3)
        if joined:
            lines.append(f"- Next inspection: {joined}")
            added = True
    risks = risks_summary(artifact.get("risks"))
    if risks:
        lines.append(f"- Risks: {risks}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
        added = True
    else:
        lines.append("- Verification: no bounded command found")
        added = True
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_reproduction_checklist_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    error = artifact.get("observed_error") if isinstance(artifact.get("observed_error"), dict) else {}
    error_type = error.get("type") if isinstance(error.get("type"), str) else None
    error_message = error.get("message") if isinstance(error.get("message"), str) else None
    if error_type or error_message:
        lines.append(f"- Observed error: {inline_text(': '.join(item for item in [error_type, error_message] if item))}")
        added = True
    checklist = artifact.get("minimal_reproduction_checklist")
    if isinstance(checklist, list):
        values: list[str] = []
        for item in checklist:
            if not isinstance(item, dict) or not isinstance(item.get("step"), str):
                continue
            path = item.get("path")
            suffix = f" ({path})" if isinstance(path, str) and path else ""
            values.append(f"{item['step']}{suffix}")
        joined = limited_join(values, limit=4)
        if joined:
            lines.append(f"- Reproduction checklist: {joined}")
            added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    command = artifact.get("next_local_command") if isinstance(artifact.get("next_local_command"), dict) else {}
    rendered = command_text(command.get("command")) if command else ""
    if rendered:
        lines.append(f"- Next local command: {rendered}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_request_flow_map_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    target_value = artifact.get("target")
    if isinstance(target_value, str) and target_value:
        lines.append(f"- Target: {inline_text(target_value, 180)}")
        added = True
    target = artifact.get("target_flow")
    if isinstance(target, str) and target:
        lines.append(f"- Target flow: {inline_text(target, 180)}")
        added = True
    handlers = artifact.get("handler_files")
    handler_values: list[str] = []
    if isinstance(handlers, list):
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            path = path_with_line(handler)
            role = handler.get("role")
            evidence = handler.get("evidence")
            label = path
            if isinstance(role, str) and role:
                label = f"{label} ({role})" if label else role
            if isinstance(evidence, str) and evidence:
                label = f"{label}: {inline_text(evidence, 140)}" if label else inline_text(evidence, 140)
            if label:
                handler_values.append(label)
    handler_summary = limited_join(handler_values, limit=5)
    if handler_summary:
        lines.append(f"- Handler files: {handler_summary}")
        added = True
    steps = artifact.get("flow_steps")
    if isinstance(steps, list):
        values: list[str] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            path = path_with_line(step)
            role = step.get("role")
            evidence = step.get("evidence")
            label = path
            if isinstance(role, str) and role:
                label = f"{label} ({role})" if label else role
            if isinstance(evidence, str) and evidence:
                label = f"{label}: {inline_text(evidence, 140)}" if label else inline_text(evidence, 140)
            if label:
                values.append(label)
        joined = limited_join(values, limit=5)
        if joined:
            lines.append(f"- Flow steps: {joined}")
            added = True
    participating = participating_files_summary(artifact.get("participating_files"))
    if participating:
        lines.append(f"- Participating files: {participating}")
        added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    else:
        lines.append("- Related tests: none found in bounded evidence")
        added = True
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
        added = True
    risks = risks_summary(artifact.get("risks"))
    if risks:
        lines.append(f"- Risks: {risks}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
        added = True
    else:
        lines.append("- Verification: no bounded command found")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_code_path_comparison_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Comparison target: {inline_text(target, 180)}")
        added = True
    candidates = artifact.get("candidate_paths")
    if isinstance(candidates, list):
        values: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("name")
            evidence = participating_files_summary(candidate.get("evidence"))
            if isinstance(name, str) and name:
                values.append(f"{name}: {evidence}" if evidence else name)
        joined = limited_join(values, limit=4)
        if joined:
            lines.append(f"- Candidate paths: {joined}")
            added = True
    recommended = artifact.get("recommended_path")
    if isinstance(recommended, dict):
        name = recommended.get("name")
        confidence = recommended.get("confidence")
        if isinstance(name, str) and name:
            suffix = f" (confidence: {confidence})" if isinstance(confidence, str) and confidence else ""
            lines.append(f"- Recommended path: {name}{suffix}")
            added = True
    risks = risks_summary(artifact.get("risks"))
    if risks:
        lines.append(f"- Risks: {risks}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_change_surface_summary_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    target = artifact.get("target")
    if isinstance(target, str) and target:
        lines.append(f"- Target: {inline_text(target, 180)}")
        added = True
    files = participating_files_summary(artifact.get("change_surface_files"))
    if files:
        lines.append(f"- Change surface files: {files}")
        added = True
    files_to_touch = boundary_files_summary(artifact.get("files_to_touch"))
    if files_to_touch:
        lines.append(f"- Files to touch: {files_to_touch}")
        added = True
    files_not_to_touch = boundary_files_summary(artifact.get("files_not_to_touch"))
    if files_not_to_touch:
        lines.append(f"- Files not to touch: {files_not_to_touch}")
        added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    risk_level = artifact.get("risk_level")
    if isinstance(risk_level, str) and risk_level:
        lines.append(f"- Risk level: {risk_level}")
        added = True
    implementation_status = artifact.get("implementation_status")
    if isinstance(implementation_status, str) and implementation_status:
        lines.append(f"- Implementation status: {implementation_status}")
        added = True
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
        added = True
    risks = risks_summary(artifact.get("risks"))
    if risks:
        lines.append(f"- Risks: {risks}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    unknowns = unknowns_summary(artifact.get("unknowns"))
    if unknowns:
        lines.append(f"- Unknowns: {unknowns}")
        added = True
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
        added = True
    else:
        lines.append("- Verification: no bounded command found")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_investigation_plan_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    added = False
    beginning = artifact.get("likely_beginning_point")
    if isinstance(beginning, dict):
        beginning_path = path_with_line(beginning)
        if beginning_path:
            lines.append(f"- Beginning point: {beginning_path}")
            added = True
    related_tests = related_tests_summary(artifact.get("related_tests"))
    if related_tests:
        lines.append(f"- Related tests: {related_tests}")
        added = True
    evidence_files = participating_files_summary(artifact.get("participating_files"))
    if evidence_files:
        lines.append(f"- Evidence files: {evidence_files}")
        added = True
    verification_plan = artifact.get("verification_plan")
    if isinstance(verification_plan, dict):
        commands = verification_plan.get("verification_commands")
        if isinstance(commands, list):
            values: list[str] = []
            for command in commands:
                if isinstance(command, dict):
                    values.append(command_text(command.get("command")))
                else:
                    values.append(command_text(command))
            joined = limited_join(values, limit=3)
            if joined:
                lines.append(f"- Recommended commands: {joined}")
                added = True
    source_refs = source_refs_summary(artifact.get("source_refs"), limit=20)
    if source_refs:
        lines.append(f"- Source refs: {source_refs}")
        added = True
    gaps = gaps_summary(artifact.get("gaps"))
    if gaps:
        lines.append(f"- Gaps: {gaps}")
        added = True
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        lines.append("- Source mutation: false")
        added = True
    return added


def append_draft_proposal_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    kind = artifact_kind_label(artifact)
    lines.append(f"- Proposal artifact: {kind}")
    if isinstance(artifact.get("status"), str):
        lines.append(f"- Status: {artifact['status']}")
    operations = artifact.get("packet_operations")
    targets = packet_operation_targets(operations)
    if targets:
        lines.append(f"- Target file: {targets}")
    operation_summary = packet_operation_summary(operations)
    if operation_summary:
        lines.append(f"- Operation: {operation_summary}")
    verification = verification_commands_summary(artifact.get("verification_commands"))
    if verification:
        lines.append(f"- Verification: {verification}")
    safety = safety_checks_summary(artifact.get("safety_checks"))
    if safety:
        lines.append(f"- Safety checks: {safety}")
    source_artifact_key = artifact.get("source_artifact_key")
    if isinstance(source_artifact_key, str) and source_artifact_key:
        lines.append(f"- Evidence source: {source_artifact_key}")
    source_mutation = source_mutation_from_safety_checks(artifact.get("safety_checks"))
    if source_mutation is not None:
        lines.append(f"- Source mutation: {source_mutation}")
    elif artifact.get("kind") == "workflow_router_packet_operation_proposal":
        lines.append("- Source mutation: false")
    if artifact.get("failed_test"):
        lines.append(f"- Failed test: {inline_text(artifact['failed_test'])}")
    blockers = blockers_summary(artifact.get("blockers"))
    if blockers:
        lines.append(f"- Blockers: {blockers}")
    lines.append("- Approval: required before apply")
    return True


def append_skill_batch_proposal_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Proposal artifact: skill_batch_proposal")
    run_id = artifact.get("run_id")
    if isinstance(run_id, str) and run_id:
        lines.append(f"- Proposal run id: {run_id}")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        lines.append(f"- Proposed skills: {summary.get('skill_count', 0)}")
        lines.append(f"- Eval cases: {summary.get('eval_case_count', 0)}")
        lines.append(f"- Batch validation: {summary.get('batch_validation_status')}")
        lines.append(f"- Do not admit: {summary.get('do_not_admit_count', 0)}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Next action: {summary.get('next_action')}")
    manifest = artifact.get("draft_batch_manifest") if isinstance(artifact.get("draft_batch_manifest"), dict) else {}
    skills = manifest.get("skills") if isinstance(manifest.get("skills"), list) else []
    skill_ids = [item.get("id") for item in skills if isinstance(item, dict) and isinstance(item.get("id"), str)]
    if skill_ids:
        lines.append(f"- Skill IDs: {limited_join(skill_ids, limit=5)}")
    do_not_admit = artifact.get("do_not_admit") if isinstance(artifact.get("do_not_admit"), list) else []
    if do_not_admit:
        reasons: list[str] = []
        for item in do_not_admit[:3]:
            if isinstance(item, dict):
                errors = item.get("errors")
                if isinstance(errors, list) and errors:
                    reasons.append(inline_text(errors[0], 240))
                elif isinstance(item.get("action"), str):
                    reasons.append(item["action"])
        if reasons:
            lines.append(f"- Do-not-admit reason: {limited_join(reasons, limit=3)}")
    return True


def append_skill_batch_registration_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Registration artifact: skill_batch_registration")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        skill_ids = summary.get("installed_skill_ids") if isinstance(summary.get("installed_skill_ids"), list) else []
        eval_ids = summary.get("installed_eval_case_ids") if isinstance(summary.get("installed_eval_case_ids"), list) else []
        lines.append(f"- Installed skills: {limited_join([str(item) for item in skill_ids], limit=5) or 'none'}")
        lines.append(f"- Eval cases: {limited_join([str(item) for item in eval_ids], limit=5) or 'none'}")
        lines.append(f"- Batch validation: {summary.get('batch_validation_status')}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Target repository changed: {summary.get('target_repository_changed')}")
        lines.append(f"- Next action: {summary.get('next_action')}")
    proposal_run_id = artifact.get("proposal_run_id")
    if isinstance(proposal_run_id, str) and proposal_run_id:
        lines.append(f"- Source proposal run id: {proposal_run_id}")
    hash_proof = artifact.get("hash_proof") if isinstance(artifact.get("hash_proof"), dict) else {}
    changed = hash_proof.get("changed") if isinstance(hash_proof.get("changed"), list) else []
    if changed:
        lines.append(f"- Changed runtime files: {limited_join([str(item) for item in changed], limit=5)}")
    rollback = artifact.get("rollback_instructions") if isinstance(artifact.get("rollback_instructions"), dict) else {}
    restore = rollback.get("restore_backups") if isinstance(rollback.get("restore_backups"), dict) else {}
    if restore:
        lines.append("- Rollback: restore recorded runtime JSON backups and remove installed skill files")
    return True


def append_skill_eval_promotion_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Promotion artifact: skill_eval_promotion")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        skill_ids = summary.get("promoted_skill_ids") if isinstance(summary.get("promoted_skill_ids"), list) else []
        eval_ids = summary.get("eval_case_ids") if isinstance(summary.get("eval_case_ids"), list) else []
        changed = summary.get("changed_runtime_files") if isinstance(summary.get("changed_runtime_files"), list) else []
        lines.append(f"- Promoted skills: {limited_join([str(item) for item in skill_ids], limit=5) or 'none'}")
        lines.append(f"- Eval cases: {limited_join([str(item) for item in eval_ids], limit=5) or 'none'}")
        lines.append(f"- Metadata eval: {summary.get('metadata_eval_status')}")
        lines.append(f"- Scale report: {summary.get('scale_report_status')}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Changed runtime files: {limited_join([str(item) for item in changed], limit=5) or 'none'}")
        lines.append(f"- Target repository changed: {summary.get('target_repository_changed')}")
        lines.append(f"- Next action: {summary.get('next_action')}")
    hash_proof = artifact.get("hash_proof") if isinstance(artifact.get("hash_proof"), dict) else {}
    changed = hash_proof.get("changed") if isinstance(hash_proof.get("changed"), list) else []
    if changed:
        lines.append(f"- Hash proof changed: {limited_join([str(item) for item in changed], limit=5)}")
    rollback = artifact.get("rollback_instructions") if isinstance(artifact.get("rollback_instructions"), dict) else {}
    restore = rollback.get("restore_backups") if isinstance(rollback.get("restore_backups"), dict) else {}
    if restore:
        lines.append("- Rollback: restore recorded runtime/skills.json backup")
    return True


def append_skill_lifecycle_audit_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Audit artifact: skill_lifecycle_audit")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Lifecycle status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        lines.append(f"- Skills audited: {summary.get('skill_count', 0)}")
        status_counts = summary.get("status_counts") if isinstance(summary.get("status_counts"), dict) else {}
        queue_counts = summary.get("queue_counts") if isinstance(summary.get("queue_counts"), dict) else {}
        if status_counts:
            lines.append(
                "- Status counts: "
                + limited_join([f"{key}={status_counts[key]}" for key in sorted(status_counts)], limit=8)
            )
        if queue_counts:
            lines.append(
                "- Next actions: "
                + limited_join([f"{key}={queue_counts[key]}" for key in sorted(queue_counts)], limit=8)
            )
        lines.append(f"- Blockers: {summary.get('blocker_count', 0)}")
        lines.append(f"- Orphan eval cases: {summary.get('orphan_eval_case_count', 0)}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Target repository changed: {summary.get('target_repository_changed')}")
    queue = artifact.get("action_queue") if isinstance(artifact.get("action_queue"), list) else []
    actionable = [
        item
        for item in queue
        if isinstance(item, dict) and item.get("action") in {"promote", "keep_draft", "revise", "deprecate"}
    ][:5]
    if actionable:
        lines.append("- Queue:")
        for item in actionable:
            blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
            blocker_codes = [str(blocker.get("code")) for blocker in blockers if isinstance(blocker, dict) and blocker.get("code")]
            suffix = f" blockers={limited_join(blocker_codes, limit=3)}" if blocker_codes else ""
            lines.append(f"  - {item.get('skill_id')}: {item.get('action')}{suffix}")
    else:
        lines.append("- Queue: no action required")
    return True


def append_skill_selection_explanation_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Explanation artifact: skill_selection_explanation")
    workflow_id = artifact.get("workflow_id")
    lines.append(f"- Workflow: {workflow_id or 'none'}")
    selection = artifact.get("selection") if isinstance(artifact.get("selection"), dict) else {}
    selected = selection.get("selected") if isinstance(selection.get("selected"), list) else []
    selected_ids = [
        str(item.get("skill_id"))
        for item in selected
        if isinstance(item, dict) and isinstance(item.get("skill_id"), str)
    ]
    lines.append(f"- Selected skills: {limited_join(selected_ids, limit=5) or 'none'}")
    route_keys = []
    trigger_summaries = []
    for item in selected[:5]:
        if not isinstance(item, dict):
            continue
        skill_id = item.get("skill_id")
        route_key = item.get("route_key")
        if isinstance(skill_id, str) and isinstance(route_key, str):
            route_keys.append(f"{skill_id}={route_key}")
        hits = item.get("trigger_hits") if isinstance(item.get("trigger_hits"), list) else []
        if isinstance(skill_id, str) and hits:
            trigger_summaries.append(f"{skill_id}: {limited_join([str(hit) for hit in hits], limit=3)}")
    lines.append(f"- Route keys: {limited_join(route_keys, limit=5) or 'none'}")
    if trigger_summaries:
        lines.append(f"- Trigger hits: {limited_join(trigger_summaries, limit=3)}")
    lines.append(f"- Candidates: {selection.get('candidate_count', 0)}")
    lines.append(f"- Filtered out: {selection.get('filtered_count', 0)}")
    lines.append(f"- Deprecated exclusions: {len(selection.get('deprecated_exclusions', [])) if isinstance(selection.get('deprecated_exclusions'), list) else 0}")
    lines.append(f"- Body reads during selection: {selection.get('body_reads_during_selection', 0)}")
    lines.append(f"- Target repository changed: {artifact.get('target_repository_changed')}")
    blockers = selection.get("blockers") if isinstance(selection.get("blockers"), list) else []
    if blockers:
        reasons = [
            str(item.get("reason"))
            for item in blockers
            if isinstance(item, dict) and isinstance(item.get("reason"), str)
        ]
        lines.append(f"- Blockers: {limited_join(reasons, limit=3)}")
    return True


def append_skill_pack_validation_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Validation artifact: skill_pack_validation")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        lines.append(f"- Pack: {summary.get('pack_id')}")
        lines.append(f"- Version: {summary.get('pack_version')}")
        lines.append(f"- Skills: {summary.get('skill_count', 0)}")
        lines.append(f"- Eval cases: {summary.get('eval_case_count', 0)}")
        lines.append(f"- Namespaces: {summary.get('namespace_count', 0)}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Target repository changed: {summary.get('target_repository_changed')}")
        lines.append(f"- Next action: {summary.get('next_action')}")
    errors = artifact.get("errors") if isinstance(artifact.get("errors"), list) else []
    if errors:
        lines.append(f"- Errors: {limited_join([inline_text(error, 220) for error in errors], limit=3)}")
    return True


def append_skill_pack_install_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Installation artifact: skill_pack_installation")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        skill_ids = summary.get("installed_skill_ids") if isinstance(summary.get("installed_skill_ids"), list) else []
        eval_ids = summary.get("installed_eval_case_ids") if isinstance(summary.get("installed_eval_case_ids"), list) else []
        lines.append(f"- Pack: {summary.get('pack_id')}")
        lines.append(f"- Version: {summary.get('pack_version')}")
        lines.append(f"- Installed skills: {limited_join([str(item) for item in skill_ids], limit=5) or 'none'}")
        lines.append(f"- Eval cases: {limited_join([str(item) for item in eval_ids], limit=5) or 'none'}")
        lines.append(f"- Pack validation: {summary.get('pack_validation_status')}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Target repository changed: {summary.get('target_repository_changed')}")
        lines.append(f"- Next action: {summary.get('next_action')}")
    hash_proof = artifact.get("hash_proof") if isinstance(artifact.get("hash_proof"), dict) else {}
    changed = hash_proof.get("changed") if isinstance(hash_proof.get("changed"), list) else []
    if changed:
        lines.append(f"- Changed runtime files: {limited_join([str(item) for item in changed], limit=5)}")
    rollback = artifact.get("rollback_instructions") if isinstance(artifact.get("rollback_instructions"), dict) else {}
    restore = rollback.get("restore_backups") if isinstance(rollback.get("restore_backups"), dict) else {}
    if restore:
        lines.append("- Rollback: restore recorded runtime JSON backups and remove installed skill files")
    return True


def append_skill_scaffold_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    lines.append("- Scaffold artifact: skill_scaffold")
    status = artifact.get("status")
    if isinstance(status, str):
        lines.append(f"- Status: {status}")
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if summary:
        lines.append(f"- Skill ID: {summary.get('skill_id')}")
        lines.append(f"- Eval case: {summary.get('eval_case_id')}")
        lines.append(f"- Output artifact: {summary.get('output_artifact')}")
        lines.append(f"- Live suite: {summary.get('live_suite')}")
        lines.append(f"- Batch validation: {summary.get('batch_validation_status')}")
        lines.append(f"- Do not admit: {summary.get('do_not_admit_count', 0)}")
        if summary.get("authoring_factory_status"):
            lines.append(f"- Authoring factory: {summary.get('authoring_factory_status')}")
        if summary.get("promotion_state"):
            lines.append(f"- Promotion state: {summary.get('promotion_state')}")
        lines.append(f"- Runtime registry changed: {summary.get('runtime_registry_changed')}")
        lines.append(f"- Target repository changed: {summary.get('target_repository_changed')}")
        lines.append(f"- Next action: {summary.get('next_action')}")
    artifact_paths = artifact.get("artifacts") if isinstance(artifact.get("artifacts"), dict) else {}
    factory_sidecars = [
        key
        for key in (
            "prompt_coverage_entry",
            "eval_skeleton",
            "docs_stub",
            "docs_example_stub",
            "regression_test_skeleton",
            "authoring_factory_report",
        )
        if isinstance(artifact_paths.get(key), str)
    ]
    if factory_sidecars:
        lines.append(f"- Factory sidecars: {limited_join(factory_sidecars, limit=6)}")
    do_not_admit = artifact.get("do_not_admit") if isinstance(artifact.get("do_not_admit"), list) else []
    if do_not_admit:
        reasons = []
        for item in do_not_admit[:3]:
            if isinstance(item, dict):
                errors = item.get("errors") if isinstance(item.get("errors"), list) else []
                if errors:
                    reasons.append(inline_text(errors[0], 220))
                elif isinstance(item.get("action"), str):
                    reasons.append(item["action"])
        if reasons:
            lines.append(f"- Do-not-admit reason: {limited_join(reasons, limit=3)}")
    return True


def append_task_decomposition_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    if artifact.get("kind") != "task_decomposition":
        return False
    lines.append("- Decomposition artifact: task_decomposition")
    lines.append(f"- Work-package schema: {artifact.get('work_package_schema_version')}")
    lines.append(f"- Decomposition status: {artifact.get('status')}")
    lines.append(f"- Prompt family: {artifact.get('prompt_family')}")
    lines.append(f"- Risk level: {artifact.get('risk_level')}")
    deferred_to_phase = artifact.get("deferred_to_phase")
    if deferred_to_phase:
        lines.append(f"- Deferred to phase: {deferred_to_phase}")
    requirements_translation = (
        artifact.get("requirements_translation")
        if isinstance(artifact.get("requirements_translation"), dict)
        else {}
    )
    if requirements_translation:
        business_requirements = (
            requirements_translation.get("source_business_requirements")
            if isinstance(requirements_translation.get("source_business_requirements"), list)
            else []
        )
        technical_requirements = (
            requirements_translation.get("technical_requirements")
            if isinstance(requirements_translation.get("technical_requirements"), list)
            else []
        )
        assumptions = (
            requirements_translation.get("explicit_assumptions")
            if isinstance(requirements_translation.get("explicit_assumptions"), list)
            else []
        )
        rejected = (
            requirements_translation.get("rejected_assumptions")
            if isinstance(requirements_translation.get("rejected_assumptions"), list)
            else []
        )
        estimate = (
            requirements_translation.get("effort_estimate")
            if isinstance(requirements_translation.get("effort_estimate"), dict)
            else {}
        )
        revision = (
            requirements_translation.get("estimate_revision")
            if isinstance(requirements_translation.get("estimate_revision"), dict)
            else {}
        )
        lines.append("Requirements Translation:")
        br_lines = [
            f"{item.get('id')}: {inline_text(item.get('text'), 160)}"
            for item in business_requirements[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        tr_lines = [
            f"{item.get('id')}: {inline_text(item.get('requirement'), 180)}"
            for item in technical_requirements[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        assumption_lines = [
            f"{item.get('id')}: {inline_text(item.get('assumption'), 140)}"
            for item in assumptions[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        rejected_lines = [
            f"{item.get('id')}: {inline_text(item.get('assumption'), 140)}"
            for item in rejected[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        if br_lines:
            lines.append(f"- Business requirements: {limited_join(br_lines)}")
        if tr_lines:
            lines.append(f"- Technical requirements: {limited_join(tr_lines)}")
        if assumption_lines:
            lines.append(f"- Explicit assumptions: {limited_join(assumption_lines)}")
        if rejected_lines:
            lines.append(f"- Rejected assumptions: {limited_join(rejected_lines)}")
        if estimate:
            estimate_bits = [
                f"band={inline_text(estimate.get('estimate_band'), 40)}",
                f"cycles={inline_text(estimate.get('cycle_count_range'), 60)}",
                f"confidence={inline_text(estimate.get('confidence'), 40)}",
            ]
            lines.append(f"- Effort estimate: {', '.join(estimate_bits)}")
            triggers = string_items(estimate.get("revision_triggers"))
            if triggers:
                lines.append(f"- Revision triggers: {limited_join(triggers, limit=3)}")
        if revision.get("status") == "revised":
            lines.append("- Estimate revision: revised; review required before implementation prep")
    incremental_plan = (
        artifact.get("incremental_implementation_plan")
        if isinstance(artifact.get("incremental_implementation_plan"), dict)
        else {}
    )
    if incremental_plan:
        changesets = (
            incremental_plan.get("changesets")
            if isinstance(incremental_plan.get("changesets"), list)
            else []
        )
        version_control = (
            incremental_plan.get("version_control_plan")
            if isinstance(incremental_plan.get("version_control_plan"), dict)
            else {}
        )
        source_apply = (
            incremental_plan.get("source_apply_policy")
            if isinstance(incremental_plan.get("source_apply_policy"), dict)
            else {}
        )
        lines.append("Incremental Implementation Plan:")
        changeset_lines: list[str] = []
        verification_lines: list[str] = []
        commit_lines: list[str] = []
        for item in changesets[:INLINE_ARTIFACT_ITEM_LIMIT]:
            if not isinstance(item, dict):
                continue
            changeset_lines.append(
                f"{item.get('id')}: {inline_text(item.get('title'), 120)} -> {inline_text(item.get('functional_outcome'), 160)}"
            )
            commands = string_items(item.get("verification_commands"))
            if commands:
                verification_lines.append(f"{item.get('id')}: {limited_join(commands, limit=2)}")
            commit_message = item.get("commit_message") if isinstance(item.get("commit_message"), dict) else {}
            subject = commit_message.get("subject") if isinstance(commit_message.get("subject"), str) else ""
            if subject:
                commit_lines.append(f"{item.get('id')}: {inline_text(subject, 90)}")
        if changeset_lines:
            lines.append(f"- Changesets: {limited_join(changeset_lines)}")
        if verification_lines:
            lines.append(f"- Changeset verification: {limited_join(verification_lines)}")
        if commit_lines:
            lines.append(f"- Commit messages: {limited_join(commit_lines)}")
        if version_control:
            lines.append(f"- Commit order: {limited_join(string_items(version_control.get('commit_order')))}")
            lines.append(f"- Branch: {inline_text(version_control.get('branch_name'), 100)}")
            lines.append(f"- Version-control policy: {inline_text(version_control.get('commit_policy'), 180)}")
        if source_apply:
            lines.append(f"- Source apply policy: {inline_text(source_apply.get('status'), 100)}")
    delivery_mentorship = (
        artifact.get("delivery_mentorship")
        if isinstance(artifact.get("delivery_mentorship"), dict)
        else {}
    )
    if delivery_mentorship:
        delivery_sequence = (
            delivery_mentorship.get("delivery_sequence")
            if isinstance(delivery_mentorship.get("delivery_sequence"), list)
            else []
        )
        testing_strategy = (
            delivery_mentorship.get("testing_strategy")
            if isinstance(delivery_mentorship.get("testing_strategy"), dict)
            else {}
        )
        testing_tiers = (
            testing_strategy.get("tiers")
            if isinstance(testing_strategy.get("tiers"), list)
            else []
        )
        deployment = (
            delivery_mentorship.get("deployment_readiness")
            if isinstance(delivery_mentorship.get("deployment_readiness"), dict)
            else {}
        )
        source_apply = (
            delivery_mentorship.get("source_apply_policy")
            if isinstance(delivery_mentorship.get("source_apply_policy"), dict)
            else {}
        )
        source_request = (
            delivery_mentorship.get("source_request")
            if isinstance(delivery_mentorship.get("source_request"), dict)
            else {}
        )
        lines.append("Delivery Mentorship Plan:")
        if source_request:
            source_text = source_request.get("text") if isinstance(source_request.get("text"), str) else ""
            domain_terms = string_items(source_request.get("domain_terms"))
            if source_text:
                lines.append(f"- Intake focus: {inline_text(source_text, 220)}")
            if domain_terms:
                lines.append(f"- Prompt-derived terms: {limited_join(domain_terms, limit=6)}")
        risk_controls = string_items(delivery_mentorship.get("case_specific_risk_controls"))
        if risk_controls:
            lines.append(f"- Risk controls: {limited_join(risk_controls, limit=6)}")
        sequence_lines = [
            f"{item.get('id')}: {inline_text(item.get('stage'), 70)} -> {inline_text(item.get('deliverable'), 150)}"
            for item in delivery_sequence[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        why_lines = [
            f"{item.get('id')}: {inline_text(item.get('why'), 160)}"
            for item in delivery_sequence[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        tier_lines = [
            f"{item.get('tier')}: {inline_text(item.get('purpose'), 150)}"
            for item in testing_tiers[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        mentorship_notes = string_items(delivery_mentorship.get("mentorship_notes"))
        quality_practices = string_items(delivery_mentorship.get("code_quality_practices"))
        debugging_steps = string_items(delivery_mentorship.get("debugging_methodology"))
        readiness_checks = string_items(deployment.get("checks"))
        done_items = string_items(delivery_mentorship.get("definition_of_done"))
        stop_conditions = (
            delivery_mentorship.get("stop_conditions")
            if isinstance(delivery_mentorship.get("stop_conditions"), list)
            else []
        )
        stop_items = [
            f"{item.get('code')}: {inline_text(item.get('reason'), 140)}"
            for item in stop_conditions[:INLINE_ARTIFACT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        if sequence_lines:
            lines.append(f"- Delivery sequence: {limited_join(sequence_lines)}")
        if why_lines:
            lines.append(f"- Why these steps: {limited_join(why_lines)}")
        if tier_lines:
            lines.append(f"- Testing strategy: {limited_join(tier_lines)}")
        if debugging_steps:
            lines.append(f"- Debugging method: {limited_join(debugging_steps, limit=3)}")
        if quality_practices:
            lines.append(f"- Code quality practices: {limited_join(quality_practices, limit=3)}")
        if readiness_checks:
            lines.append(f"- Deployment readiness: {limited_join(readiness_checks, limit=4)}")
        if mentorship_notes:
            lines.append(f"- Mentorship notes: {limited_join(mentorship_notes, limit=3)}")
        if done_items:
            lines.append(f"- Definition of done: {limited_join(done_items, limit=4)}")
        if stop_items:
            lines.append(f"- Stop conditions: {limited_join(stop_items, limit=3)}")
        if source_apply:
            deployment_status = source_apply.get("deployment_status")
            lines.append(
                f"- Source apply policy: {inline_text(source_apply.get('status'), 100)}"
                + (f"; deployment={inline_text(deployment_status, 80)}" if deployment_status else "")
            )
    work_packages = artifact.get("work_packages") if isinstance(artifact.get("work_packages"), list) else []
    if work_packages:
        package_lines: list[str] = []
        for item in work_packages[:INLINE_ARTIFACT_ITEM_LIMIT]:
            if not isinstance(item, dict):
                continue
            workflow = item.get("workflow_id") if isinstance(item.get("workflow_id"), str) else "approval_gate"
            title = inline_text(item.get("title"), 120)
            stage = inline_text(item.get("stage"), 80)
            gate = item.get("approval_gate") if isinstance(item.get("approval_gate"), dict) else {}
            approval_scope = gate.get("scope") if item.get("approval_required") is True else "none"
            package_lines.append(f"{item.get('id')}: {title} ({stage}, {workflow}, gate={approval_scope})")
        if package_lines:
            lines.append(f"- Work packages: {limited_join(package_lines)}")
        stop_lines: list[str] = []
        verification_lines: list[str] = []
        acceptance_lines: list[str] = []
        for item in work_packages[:INLINE_ARTIFACT_ITEM_LIMIT]:
            if not isinstance(item, dict):
                continue
            package_id = item.get("id")
            criteria = item.get("acceptance_criteria") if isinstance(item.get("acceptance_criteria"), list) else []
            criteria_names = [
                criterion.get("id")
                for criterion in criteria[:2]
                if isinstance(criterion, dict) and isinstance(criterion.get("id"), str)
            ]
            if criteria_names:
                acceptance_lines.append(f"{package_id}: {limited_join(criteria_names, limit=2)}")
            stops = item.get("stop_conditions") if isinstance(item.get("stop_conditions"), list) else []
            stop_codes = [
                stop.get("code")
                for stop in stops[:2]
                if isinstance(stop, dict) and isinstance(stop.get("code"), str)
            ]
            if stop_codes:
                stop_lines.append(f"{package_id}: {limited_join(stop_codes, limit=2)}")
            verification = item.get("verification") if isinstance(item.get("verification"), dict) else {}
            status = verification.get("status")
            proof_gates = string_items(verification.get("proof_gates"))
            if isinstance(status, str):
                detail = status
                if proof_gates:
                    detail = f"{detail} ({limited_join(proof_gates, limit=2)})"
                verification_lines.append(f"{package_id}: {inline_text(detail, 180)}")
        if acceptance_lines:
            lines.append(f"- Acceptance criteria: {limited_join(acceptance_lines)}")
        if stop_lines:
            lines.append(f"- Stop conditions: {limited_join(stop_lines)}")
        if verification_lines:
            lines.append(f"- Package verification: {limited_join(verification_lines)}")
    edges = artifact.get("dependency_edges") if isinstance(artifact.get("dependency_edges"), list) else []
    if edges:
        edge_lines = []
        for edge in edges[:INLINE_ARTIFACT_ITEM_LIMIT]:
            if isinstance(edge, dict):
                edge_lines.append(f"{edge.get('from')}->{edge.get('to')}")
        if edge_lines:
            lines.append(f"- Dependencies: {limited_join(edge_lines)}")
    gates = artifact.get("approval_gates") if isinstance(artifact.get("approval_gates"), list) else []
    if gates:
        gate_lines = []
        for gate in gates[:INLINE_ARTIFACT_ITEM_LIMIT]:
            if isinstance(gate, dict):
                gate_id = inline_text(gate.get("id") or gate, 80)
                package_id = inline_text(gate.get("package_id"), 40)
                scope = inline_text(gate.get("approval_scope"), 80)
                gate_lines.append(f"{gate_id} ({package_id}, {scope})")
        if gate_lines:
            lines.append(f"- Approval gates: {limited_join(gate_lines)}")
    workflows = string_items(artifact.get("selected_workflow_ids"))
    skills = string_items(artifact.get("selected_skill_ids"))
    tools = string_items(artifact.get("selected_tool_ids"))
    lines.append(f"- Selected workflows: {limited_join(workflows) if workflows else 'none'}")
    lines.append(f"- Selected skills: {limited_join(skills) if skills else 'none'}")
    lines.append(f"- Selected tools: {limited_join(tools) if tools else 'none'}")
    uncertainty = artifact.get("uncertainty") if isinstance(artifact.get("uncertainty"), list) else []
    if uncertainty:
        uncertainty_lines = []
        for item in uncertainty[:INLINE_ARTIFACT_ITEM_LIMIT]:
            if isinstance(item, dict):
                uncertainty_lines.append(inline_text(item.get("code") or item.get("reason") or item, 180))
        if uncertainty_lines:
            lines.append(f"- Uncertainty: {limited_join(uncertainty_lines)}")
    verification = artifact.get("verification_strategy") if isinstance(artifact.get("verification_strategy"), dict) else {}
    if verification:
        proof_gates = string_items(verification.get("proof_gates"))
        commands = verification.get("commands") if isinstance(verification.get("commands"), list) else []
        if commands:
            lines.append(f"- Verification: {limited_join([command_text(command) for command in commands])}")
        elif proof_gates:
            lines.append(f"- Verification: {limited_join(proof_gates)}")
        elif isinstance(verification.get("reason"), str):
            lines.append(f"- Verification: {inline_text(verification.get('reason'), 220)}")
    lines.append(f"- Source mutation: {artifact.get('target_repository_changed')}")
    lines.append(f"- Runtime registry mutation: {artifact.get('runtime_registry_changed')}")
    next_action = artifact.get("next_action")
    if isinstance(next_action, str):
        lines.append(f"- Next action: {next_action}")
    return True


def append_disposable_mutation_diff_answer(lines: list[str], artifact: dict[str, Any]) -> bool:
    if artifact.get("kind") != InlineArtifactKind.DISPOSABLE_MUTATION_DIFF.value:
        return False
    lines.append("- Diff artifact: disposable_mutation_structured_diff")
    lines.append(f"- Status: {artifact.get('status')}")
    lines.append(f"- Changed files: {artifact.get('changed_file_count', 0)}")
    records = artifact.get("records") if isinstance(artifact.get("records"), list) else []
    record_lines: list[str] = []
    for record in records[:INLINE_ARTIFACT_ITEM_LIMIT]:
        if not isinstance(record, dict):
            continue
        path = inline_text(record.get("path"), 160)
        kind = inline_text(record.get("operation_kind"), 80)
        status = inline_text(record.get("status"), 80)
        added = record.get("added_line_count", 0)
        removed = record.get("removed_line_count", 0)
        record_lines.append(f"{path} ({kind}, +{added}/-{removed}, {status})")
    if record_lines:
        lines.append(f"- Files: {limited_join(record_lines)}")
    truncated = [
        str(record.get("path"))
        for record in records
        if isinstance(record, dict) and record.get("diff_truncated") is True and isinstance(record.get("path"), str)
    ]
    if truncated:
        lines.append(f"- Truncated diffs: {limited_join(truncated)}")
    copy_root = artifact.get("disposable_copy_root")
    if isinstance(copy_root, str) and copy_root:
        lines.append(f"- Disposable copy: {copy_root}")
    return True


def inline_artifact_answer_renderers() -> dict[InlineArtifactKind, Any]:
    return {
        InlineArtifactKind.DEFECT_DIAGNOSIS_SUMMARY: append_defect_diagnosis_summary_answer,
        InlineArtifactKind.ENGINEERING_JUDGMENT_REVIEW: append_engineering_judgment_review_answer,
        InlineArtifactKind.CODE_QUALITY_REVIEW: append_code_quality_review_answer,
        InlineArtifactKind.CODE_EXPLANATION: append_code_explanation_answer,
        InlineArtifactKind.BEHAVIOR_EXISTENCE: append_behavior_existence_answer,
        InlineArtifactKind.ENDPOINT_ROUTE_LOOKUP: append_endpoint_route_lookup_answer,
        InlineArtifactKind.MESSAGE_SOURCE_LOOKUP: append_message_source_lookup_answer,
        InlineArtifactKind.MODULE_SUMMARY: append_module_summary_answer,
        InlineArtifactKind.DATA_MODEL_LOOKUP: append_data_model_lookup_answer,
        InlineArtifactKind.TABLE_READ_WRITE_LOOKUP: append_table_read_write_lookup_answer,
        InlineArtifactKind.COVERAGE_GAP_SUMMARY: append_coverage_gap_summary_answer,
        InlineArtifactKind.DOCUMENTATION_LOOKUP: append_documentation_lookup_answer,
        InlineArtifactKind.CLI_ENTRYPOINT_LOOKUP: append_cli_entrypoint_lookup_answer,
        InlineArtifactKind.CONFIGURATION_EFFECT_SUMMARY: append_configuration_effect_summary_answer,
        InlineArtifactKind.LOCAL_CHANGE_SUMMARY: append_local_change_summary_answer,
        InlineArtifactKind.DEPENDENCY_LOOKUP: append_dependency_lookup_answer,
        InlineArtifactKind.USAGE_SUMMARY: append_usage_summary_answer,
        InlineArtifactKind.CONFIGURATION_LOOKUP: append_configuration_lookup_answer,
        InlineArtifactKind.CI_FAILURE_SUMMARY: append_ci_failure_summary_answer,
        InlineArtifactKind.TEST_FAILURE_SUMMARY: append_test_failure_summary_answer,
        InlineArtifactKind.MULTI_FILE_BEHAVIOR_INVESTIGATION: append_multi_file_behavior_investigation_answer,
        InlineArtifactKind.DEPENDENCY_IMPACT_SUMMARY: append_dependency_impact_summary_answer,
        InlineArtifactKind.TEST_SELECTION_PLAN: append_test_selection_plan_answer,
        InlineArtifactKind.RUNTIME_ERROR_DIAGNOSIS: append_runtime_error_diagnosis_answer,
        InlineArtifactKind.REPRODUCTION_CHECKLIST: append_reproduction_checklist_answer,
        InlineArtifactKind.REQUEST_FLOW_MAP: append_request_flow_map_answer,
        InlineArtifactKind.CODE_PATH_COMPARISON: append_code_path_comparison_answer,
        InlineArtifactKind.CHANGE_SURFACE_SUMMARY: append_change_surface_summary_answer,
        InlineArtifactKind.INVESTIGATION_PLAN: append_investigation_plan_answer,
        InlineArtifactKind.PACKET_OPERATION_PROPOSAL: append_draft_proposal_answer,
        InlineArtifactKind.SMALL_TEXT_EDIT_PROPOSAL: append_draft_proposal_answer,
        InlineArtifactKind.SMALL_UNIT_TEST_PROPOSAL: append_draft_proposal_answer,
        InlineArtifactKind.SIMPLE_TEST_FIX_PROPOSAL: append_draft_proposal_answer,
        InlineArtifactKind.DISPOSABLE_MUTATION_DIFF: append_disposable_mutation_diff_answer,
        InlineArtifactKind.SKILL_BATCH_PROPOSAL: append_skill_batch_proposal_answer,
        InlineArtifactKind.SKILL_BATCH_REGISTRATION: append_skill_batch_registration_answer,
        InlineArtifactKind.SKILL_EVAL_PROMOTION: append_skill_eval_promotion_answer,
        InlineArtifactKind.SKILL_LIFECYCLE_AUDIT: append_skill_lifecycle_audit_answer,
        InlineArtifactKind.SKILL_SELECTION_EXPLANATION: append_skill_selection_explanation_answer,
        InlineArtifactKind.SKILL_PACK_VALIDATION: append_skill_pack_validation_answer,
        InlineArtifactKind.SKILL_PACK_INSTALLATION: append_skill_pack_install_answer,
        InlineArtifactKind.SKILL_SCAFFOLD: append_skill_scaffold_answer,
        InlineArtifactKind.TASK_DECOMPOSITION: append_task_decomposition_answer,
    }


def inline_artifact_answer_heading(kind: InlineArtifactKind) -> str:
    if kind in {
        InlineArtifactKind.PACKET_OPERATION_PROPOSAL,
        InlineArtifactKind.SMALL_TEXT_EDIT_PROPOSAL,
        InlineArtifactKind.SMALL_UNIT_TEST_PROPOSAL,
        InlineArtifactKind.SIMPLE_TEST_FIX_PROPOSAL,
        InlineArtifactKind.SKILL_BATCH_PROPOSAL,
    }:
        return "Draft proposal:"
    if kind == InlineArtifactKind.SKILL_BATCH_REGISTRATION:
        return "Registration:"
    if kind == InlineArtifactKind.SKILL_EVAL_PROMOTION:
        return "Promotion:"
    if kind == InlineArtifactKind.SKILL_LIFECYCLE_AUDIT:
        return "Lifecycle Audit:"
    if kind == InlineArtifactKind.SKILL_SELECTION_EXPLANATION:
        return "Skill Selection:"
    if kind == InlineArtifactKind.SKILL_PACK_VALIDATION:
        return "Skill Pack Validation:"
    if kind == InlineArtifactKind.SKILL_PACK_INSTALLATION:
        return "Skill Pack Installation:"
    if kind == InlineArtifactKind.SKILL_SCAFFOLD:
        return "Skill Scaffold:"
    if kind == InlineArtifactKind.TASK_DECOMPOSITION:
        return "Task Decomposition:"
    if kind == InlineArtifactKind.DISPOSABLE_MUTATION_DIFF:
        return "Disposable Apply:"
    if kind == InlineArtifactKind.CODE_QUALITY_REVIEW:
        return "Code Quality Review:"
    if kind == InlineArtifactKind.ENGINEERING_JUDGMENT_REVIEW:
        return "Engineering Judgment:"
    if kind == InlineArtifactKind.DEFECT_DIAGNOSIS_SUMMARY:
        return "Defect Diagnosis:"
    return "Answer:"


def evidence_boundary_string(value: Any, label: str, errors: list[str]) -> str:
    if isinstance(value, str) and value.strip():
        return value
    errors.append(f"{label} must be a non-empty string")
    return ""


def evidence_boundary_list(value: Any, label: str, errors: list[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    errors.append(f"{label} must be a list")
    return []


def evidence_boundary_object_list(value: Any, label: str, errors: list[str]) -> list[dict[str, Any]]:
    records = evidence_boundary_list(value, label, errors)
    objects = [item for item in records if isinstance(item, dict)]
    if len(objects) != len(records):
        errors.append(f"{label} must contain only objects")
    return objects


def source_ref_errors(records: list[dict[str, Any]], label: str) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record.get("path"), str) or not record.get("path"):
            errors.append(f"{label}[{index}].path must be a non-empty string")
        line = record.get("line")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
            errors.append(f"{label}[{index}].line must be an integer when present")
    return errors


def data_model_evidence_boundary_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = evidence_boundary_string(artifact.get("status"), "data_model_lookup.status", errors)
    fields = evidence_boundary_object_list(artifact.get("fields"), "data_model_lookup.fields", errors)
    model_files = evidence_boundary_list(artifact.get("model_files"), "data_model_lookup.model_files", errors)
    source_refs = evidence_boundary_object_list(artifact.get("source_refs"), "data_model_lookup.source_refs", errors)
    evidence_boundary_list(artifact.get("gaps"), "data_model_lookup.gaps", errors)
    if artifact.get("mutation_policy") != "read_only_no_source_mutation":
        errors.append("data_model_lookup.mutation_policy must be read_only_no_source_mutation")
    if status == "ready":
        if not fields:
            errors.append("ready data_model_lookup requires at least one persisted schema field")
        if not model_files:
            errors.append("ready data_model_lookup requires model_files")
        if not source_refs:
            errors.append("ready data_model_lookup requires source_refs")
    for index, field in enumerate(fields):
        field_name = field.get("name")
        if not isinstance(field_name, str) or not field_name.strip():
            errors.append(f"data_model_lookup.fields[{index}].name must be a non-empty string")
        field_path = field.get("path")
        if not isinstance(field_path, str) or not field_path.strip():
            errors.append(f"data_model_lookup.fields[{index}].path must be a non-empty string")
        source = field.get("source")
        scope_label = field.get("evidence_scope") or field.get("scope") or field.get("field_scope")
        if source not in PERSISTED_SCHEMA_FIELD_SOURCES and not scope_label:
            errors.append(
                f"data_model_lookup.fields[{index}].source must be persisted schema evidence or explicitly label its scope"
            )
        if isinstance(source, str) and "runtime" in source.lower() and not scope_label:
            errors.append(f"data_model_lookup.fields[{index}] mixes runtime evidence without an explicit scope label")
    for index, model_file in enumerate(model_files):
        if not isinstance(model_file, str) or not model_file.strip():
            errors.append(f"data_model_lookup.model_files[{index}] must be a non-empty string")
    errors.extend(source_ref_errors(source_refs, "data_model_lookup.source_refs"))
    return errors


def boundary_path_set(records: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("path")) for item in records if isinstance(item.get("path"), str) and item.get("path")}


def change_surface_evidence_boundary_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = evidence_boundary_string(artifact.get("status"), "change_surface_summary.status", errors)
    files_to_touch = evidence_boundary_object_list(
        artifact.get("files_to_touch"),
        "change_surface_summary.files_to_touch",
        errors,
    )
    files_not_to_touch = evidence_boundary_object_list(
        artifact.get("files_not_to_touch"),
        "change_surface_summary.files_not_to_touch",
        errors,
    )
    unknowns = evidence_boundary_object_list(artifact.get("unknowns"), "change_surface_summary.unknowns", errors)
    risks = evidence_boundary_object_list(artifact.get("risks"), "change_surface_summary.risks", errors)
    gaps = evidence_boundary_list(artifact.get("gaps"), "change_surface_summary.gaps", errors)
    verification = evidence_boundary_list(
        artifact.get("verification_commands"),
        "change_surface_summary.verification_commands",
        errors,
    )
    source_refs = evidence_boundary_object_list(
        artifact.get("source_refs"),
        "change_surface_summary.source_refs",
        errors,
    )
    if artifact.get("mutation_policy") != "read_only_no_source_mutation":
        errors.append("change_surface_summary.mutation_policy must be read_only_no_source_mutation")
    implementation_status = artifact.get("implementation_status")
    if not isinstance(implementation_status, str) or "approval" not in implementation_status:
        errors.append("change_surface_summary.implementation_status must keep implementation behind approval")
    if status == "ready":
        if not files_to_touch and not any(item.get("unknown") == "files_to_touch" for item in unknowns):
            errors.append("ready change_surface_summary requires files_to_touch or an explicit files_to_touch unknown")
        if not files_not_to_touch and not any(item.get("unknown") == "files_not_to_touch" for item in unknowns):
            errors.append("ready change_surface_summary requires files_not_to_touch or an explicit files_not_to_touch unknown")
        if not risks:
            errors.append("ready change_surface_summary requires risks")
        if not verification:
            errors.append("ready change_surface_summary requires verification_commands")
        if not source_refs:
            errors.append("ready change_surface_summary requires source_refs")
    touch_paths = boundary_path_set(files_to_touch)
    no_touch_paths = boundary_path_set(files_not_to_touch)
    overlap = sorted(touch_paths & no_touch_paths)
    if overlap:
        errors.append("change_surface_summary paths cannot appear in both files_to_touch and files_not_to_touch: " + ", ".join(overlap))
    for label, records in (
        ("change_surface_summary.files_to_touch", files_to_touch),
        ("change_surface_summary.files_not_to_touch", files_not_to_touch),
    ):
        for index, record in enumerate(records):
            if not isinstance(record.get("path"), str) or not record.get("path"):
                errors.append(f"{label}[{index}].path must be a non-empty string")
            if not isinstance(record.get("reason"), str) or not record.get("reason"):
                errors.append(f"{label}[{index}].reason must explain the boundary decision")
    for index, unknown in enumerate(unknowns):
        if not isinstance(unknown.get("unknown"), str) or not unknown.get("unknown"):
            errors.append(f"change_surface_summary.unknowns[{index}].unknown must be a non-empty string")
        if not isinstance(unknown.get("reason"), str) or not unknown.get("reason"):
            errors.append(f"change_surface_summary.unknowns[{index}].reason must explain the uncertainty")
    for index, risk in enumerate(risks):
        if not isinstance(risk.get("risk"), str) or not risk.get("risk"):
            errors.append(f"change_surface_summary.risks[{index}].risk must be a non-empty string")
    for index, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            continue
        if not isinstance(gap.get("gap"), str) or not gap.get("gap"):
            errors.append(f"change_surface_summary.gaps[{index}].gap must be a non-empty string")
    errors.extend(source_ref_errors(source_refs, "change_surface_summary.source_refs"))
    return errors


def evidence_boundary_errors_for_artifact(kind: InlineArtifactKind, artifact: dict[str, Any]) -> list[str]:
    if kind == InlineArtifactKind.DATA_MODEL_LOOKUP:
        return data_model_evidence_boundary_errors(artifact)
    if kind == InlineArtifactKind.CHANGE_SURFACE_SUMMARY:
        return change_surface_evidence_boundary_errors(artifact)
    return []


def evidence_boundary_failure_contract(
    *,
    kind: InlineArtifactKind,
    key: str,
    artifact: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    heading = "Evidence Boundary Gate:"
    answer_lines = [
        "- Evidence boundary status: failed",
        f"- Artifact: {kind.value}",
        "- Blocking issues: " + limited_join(errors, limit=5),
        "- Next action: repair the controller artifact evidence boundary before accepting this chat answer",
    ]
    if artifact.get("mutation_policy") == "read_only_no_source_mutation":
        answer_lines.append("- Source mutation: false")
    return {
        "kind": "inline_artifact_answer_contract",
        "artifact_kind": kind.value,
        "artifact_key": key,
        "artifact_status": artifact.get("status"),
        "heading": heading,
        "lines": answer_lines,
        "text": "\n".join([heading, *answer_lines]),
        "source_mutation": "false" if artifact.get("mutation_policy") == "read_only_no_source_mutation" else None,
        "evidence_boundary_status": "failed",
        "evidence_boundary_errors": errors,
    }


def primary_answer_contract_for_response(response: dict[str, Any]) -> dict[str, Any] | None:
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    answer = first_string(summary.get("answer"))
    if not answer:
        return None
    return {
        "kind": "primary_summary_answer_contract",
        "source": "summary.answer",
        "route_status": summary.get("route_status") if isinstance(summary.get("route_status"), str) else None,
        "selected_workflow": summary.get("selected_workflow")
        if isinstance(summary.get("selected_workflow"), str)
        else None,
        "heading": "Answer:",
        "text": answer,
    }


def inline_artifact_answer_contract_for_response(response: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    renderers = inline_artifact_answer_renderers()
    for kind, keys in inline_artifact_keys_for_response(response, artifacts):
        renderer = renderers.get(kind)
        if renderer is None:
            continue
        for key in keys:
            artifact = read_inline_artifact(artifacts.get(key))
            if artifact is None or artifact.get("status") == "not_requested":
                continue
            boundary_errors = (
                evidence_boundary_errors_for_artifact(kind, artifact)
                if kind in GOVERNED_EVIDENCE_BOUNDARY_KINDS
                else []
            )
            if boundary_errors:
                return evidence_boundary_failure_contract(
                    kind=kind,
                    key=key,
                    artifact=artifact,
                    errors=boundary_errors,
                )
            answer_lines: list[str] = []
            if not renderer(answer_lines, artifact):
                break
            heading = inline_artifact_answer_heading(kind)
            answer_text_lines = [heading, *answer_lines]
            return {
                "kind": "inline_artifact_answer_contract",
                "artifact_kind": kind.value,
                "artifact_key": key,
                "artifact_status": artifact.get("status"),
                "heading": heading,
                "lines": answer_lines,
                "text": "\n".join(answer_text_lines),
                "source_mutation": "false"
                if any(line.strip().lower() == "- source mutation: false" for line in answer_lines)
                else None,
                "evidence_boundary_status": "passed" if kind in GOVERNED_EVIDENCE_BOUNDARY_KINDS else None,
                "evidence_boundary_errors": [],
            }
            break
    return None


def append_inline_artifact_answer(
    lines: list[str],
    artifacts: dict[str, Any],
    response: dict[str, Any] | None = None,
) -> None:
    contract_response = dict(response) if isinstance(response, dict) else {}
    contract_response["artifacts"] = artifacts
    contract = inline_artifact_answer_contract_for_response(contract_response)
    if contract is None:
        return
    answer_lines = contract.get("lines") if isinstance(contract.get("lines"), list) else []
    lines.append("")
    lines.append(str(contract["heading"]))
    lines.extend(str(line) for line in answer_lines)


def append_summary_lines(lines: list[str], summary: Any) -> None:
    if not summary:
        return
    lines.append("")
    lines.append("Summary:")
    if isinstance(summary, dict):
        keys = [key for key in FORMAT_A_SUMMARY_KEY_PRIORITY if key in summary] + [
            key for key in sorted(summary) if key not in FORMAT_A_SUMMARY_KEY_PRIORITY
        ]
        for key in keys[:FORMAT_A_SUMMARY_KEY_LIMIT]:
            value = "none" if key == "selected_workflow" and summary[key] is None else format_summary_value(summary[key])
            lines.append(f"- {key}: {value}")
        if len(keys) > FORMAT_A_SUMMARY_KEY_LIMIT:
            lines.append(f"- ... omitted {len(keys) - FORMAT_A_SUMMARY_KEY_LIMIT} summary field(s)")
    else:
        lines.append(str(summary))


def append_approval_state_lines(lines: list[str], summary: Any) -> None:
    if not isinstance(summary, dict):
        return
    status = summary.get("approval_state_status")
    if not isinstance(status, str) or not status:
        return
    approval_type = summary.get("approval_type")
    next_action = summary.get("approval_state_next_action")
    lines.append("")
    lines.append("Approval:")
    lines.append(f"- State: {status}")
    if isinstance(approval_type, str) and approval_type and approval_type != "none":
        lines.append(f"- Type: {approval_type}")
    if isinstance(next_action, str) and next_action:
        lines.append(f"- Next: {next_action}")


def append_artifact_lines(lines: list[str], artifacts: dict[str, Any]) -> None:
    if not artifacts:
        return
    lines.append("")
    lines.append("Artifacts:")
    keys = sorted(artifacts)
    for key in keys[:FORMAT_A_ARTIFACT_LIMIT]:
        lines.append(f"- {key}: {artifacts[key]}")
    if len(keys) > FORMAT_A_ARTIFACT_LIMIT:
        lines.append(f"- ... omitted {len(keys) - FORMAT_A_ARTIFACT_LIMIT} artifact(s)")


def bounded_format_a_text(lines: list[str]) -> str:
    bounded = list(lines)
    if len(bounded) > FORMAT_A_MAX_LINES:
        omitted = len(bounded) - FORMAT_A_MAX_LINES + 1
        bounded = bounded[: FORMAT_A_MAX_LINES - 1]
        bounded.append(f"... omitted {omitted} line(s) due to format_a line limit")
    text = "\n".join(bounded)
    if len(text) <= FORMAT_A_MAX_CHARS:
        return text
    marker = "\n... omitted content due to format_a character limit"
    return text[: max(0, FORMAT_A_MAX_CHARS - len(marker))] + marker


def assistant_content_format_a(response: dict[str, Any]) -> str:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    workflow = response.get("workflow") or "workflow"
    status = response.get("status") or "unknown"
    run_id = response.get("run_id")
    lines: list[str] = []
    primary_answer = primary_answer_contract_for_response(response)
    if primary_answer is not None:
        lines.extend([str(primary_answer["heading"]), str(primary_answer["text"]), ""])
    lines.extend(
        [
            f"I completed {workflow}." if status == "completed" else f"{workflow} finished with status {status}.",
            f"{workflow} {status}",
            f"run_id: {run_id}",
            f"warnings: {response.get('warning_count', 0)}",
            f"failures: {response.get('failure_count', 0)}",
        ]
    )
    review_summary = response.get("review_summary") if isinstance(response.get("review_summary"), dict) else {}
    if review_summary:
        lines.extend(
            [
                f"reviewed_files: {review_summary.get('reviewed_file_count', 0)}",
                f"chunks: {review_summary.get('chunks_processed', 0)} of {review_summary.get('chunks_total', 0)}",
                f"skipped_followups: {review_summary.get('skipped_followup_count', 0)}",
            ]
        )
    append_chat_contract_lines(lines, response)
    append_refusal_quality_lines(lines, response.get("summary"))
    append_skill_selection_summary_lines(lines, response)
    append_context_source_summary_lines(lines, response)
    append_summary_lines(lines, response.get("summary"))
    append_approval_state_lines(lines, response.get("summary"))
    append_inline_artifact_answer(lines, artifacts, response)
    append_artifact_lines(lines, artifacts)
    if response.get("run_lookup"):
        lines.append("")
        lines.append(f"Run record: {response['run_lookup']}")
    return bounded_format_a_text(lines)


def task_decomposition_contract_for_response(response: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    artifact = inline_artifact_by_kind(artifacts, InlineArtifactKind.TASK_DECOMPOSITION)
    if artifact is None:
        return None
    packages = artifact.get("work_packages") if isinstance(artifact.get("work_packages"), list) else []
    compact_packages: list[dict[str, Any]] = []
    for item in packages:
        if not isinstance(item, dict):
            continue
        dependency_contract = item.get("dependency_contract") if isinstance(item.get("dependency_contract"), dict) else {}
        approval_gate = item.get("approval_gate") if isinstance(item.get("approval_gate"), dict) else {}
        verification = item.get("verification") if isinstance(item.get("verification"), dict) else {}
        compact_packages.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "stage": item.get("stage"),
                "workflow_id": item.get("workflow_id"),
                "depends_on": item.get("depends_on") if isinstance(item.get("depends_on"), list) else [],
                "blocks": dependency_contract.get("blocks") if isinstance(dependency_contract.get("blocks"), list) else [],
                "approval_gate": {
                    "required": approval_gate.get("required") is True,
                    "scope": approval_gate.get("scope"),
                    "decision_options": approval_gate.get("decision_options")
                    if isinstance(approval_gate.get("decision_options"), list)
                    else [],
                },
                "mutation_policy": item.get("mutation_policy"),
                "acceptance_criteria": item.get("acceptance_criteria")
                if isinstance(item.get("acceptance_criteria"), list)
                else [],
                "scope_boundary": item.get("scope_boundary")
                if isinstance(item.get("scope_boundary"), dict)
                else {},
                "stop_conditions": item.get("stop_conditions")
                if isinstance(item.get("stop_conditions"), list)
                else [],
                "verification": {
                    "status": verification.get("status"),
                    "commands": verification.get("commands") if isinstance(verification.get("commands"), list) else [],
                    "proof_gates": verification.get("proof_gates")
                    if isinstance(verification.get("proof_gates"), list)
                    else [],
                },
                "expected_artifacts": item.get("expected_artifacts")
                if isinstance(item.get("expected_artifacts"), list)
                else [],
            }
        )
    return {
        "kind": "task_decomposition_contract",
        "work_package_schema_version": artifact.get("work_package_schema_version"),
        "status": artifact.get("status"),
        "prompt_family": artifact.get("prompt_family"),
        "risk_level": artifact.get("risk_level"),
        "deferred_to_phase": artifact.get("deferred_to_phase"),
        "work_packages": compact_packages,
        "dependency_edges": artifact.get("dependency_edges") if isinstance(artifact.get("dependency_edges"), list) else [],
        "approval_gates": artifact.get("approval_gates") if isinstance(artifact.get("approval_gates"), list) else [],
        "tenet_contract": artifact.get("tenet_contract") if isinstance(artifact.get("tenet_contract"), dict) else {},
        "requirements_translation": artifact.get("requirements_translation")
        if isinstance(artifact.get("requirements_translation"), dict)
        else {},
        "incremental_implementation_plan": artifact.get("incremental_implementation_plan")
        if isinstance(artifact.get("incremental_implementation_plan"), dict)
        else {},
        "delivery_mentorship": artifact.get("delivery_mentorship")
        if isinstance(artifact.get("delivery_mentorship"), dict)
        else {},
        "verification_strategy": artifact.get("verification_strategy")
        if isinstance(artifact.get("verification_strategy"), dict)
        else {},
        "blockers": artifact.get("blockers") if isinstance(artifact.get("blockers"), list) else [],
        "next_action": artifact.get("next_action"),
        "target_repository_changed": artifact.get("target_repository_changed"),
        "runtime_registry_changed": artifact.get("runtime_registry_changed"),
    }


def assistant_content_json(response: dict[str, Any]) -> str:
    return json.dumps(
        {
            "kind": "agentic_controller_chat_response",
            "output_format": ControllerOutputFormat.JSON.value,
            "run_id": response.get("run_id"),
            "workflow": response.get("workflow"),
            "status": response.get("status"),
            "summary": response.get("summary"),
            "artifacts": response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {},
            "warning_count": response.get("warning_count", 0),
            "warnings": response.get("warnings") if isinstance(response.get("warnings"), list) else [],
            "failure_count": response.get("failure_count", 0),
            "failures": response.get("failures") if isinstance(response.get("failures"), list) else [],
            "chat_contract": chat_contract_for_response(response),
            "selection_explanation": skill_selection_explanation_for_response(response),
            "context_explanation": context_source_explanation_for_response(response),
            "primary_answer_contract": primary_answer_contract_for_response(response),
            "inline_answer_contract": inline_artifact_answer_contract_for_response(response),
            "task_decomposition_contract": task_decomposition_contract_for_response(response),
            "tool_policy": response.get("tool_policy"),
            "review_summary": response.get("review_summary"),
            "non_mutation": response.get("non_mutation"),
            "run_lookup": response.get("run_lookup"),
        },
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )


def assistant_content_for_controller_response(
    response: dict[str, Any],
    output_format: ControllerOutputFormat = ControllerOutputFormat.FORMAT_A,
) -> str:
    if output_format == ControllerOutputFormat.JSON:
        return assistant_content_json(response)
    return assistant_content_format_a(response)


def chat_completion_response(payload: dict[str, Any], service_response: dict[str, Any]) -> dict[str, Any]:
    compact = compact_service_response(service_response)
    output_format = select_controller_output_format(payload)
    compact["output_format"] = output_format.value
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
                    "content": assistant_content_for_controller_response(compact, output_format),
                },
                "finish_reason": "stop",
            }
        ],
        "agentic_controller_response": compact,
    }


def chat_completion_stream_events(response: dict[str, Any]) -> list[dict[str, Any] | str]:
    compact = response.get("agentic_controller_response") if isinstance(response.get("agentic_controller_response"), dict) else {}
    run_id = compact.get("run_id") or response.get("id") or utc_now()
    created = response.get("created") if isinstance(response.get("created"), int) else int(datetime.now(timezone.utc).timestamp())
    model = response.get("model") if isinstance(response.get("model"), str) else "agentic-controller"
    choices = response.get("choices") if isinstance(response.get("choices"), list) else []
    first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    content = message.get("content") if isinstance(message.get("content"), str) else ""
    chunk_id = f"agentic-controller-stream-{run_id}"
    return [
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
            "agentic_controller_response": compact,
        },
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        },
        "[DONE]",
    ]


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
    with temp_path.open("wb") as handle:
        handle.write(json_bytes(record))
        handle.flush()
        os.fsync(handle.fileno())
    temp_path.replace(path)
    with RUN_RECORD_CACHE_LOCK:
        RUN_RECORD_CACHE[(str(config.run_registry_root.resolve()), run_id)] = json.loads(json.dumps(record))
    for _ in range(RUN_RECORD_VISIBILITY_RETRIES):
        if path.exists():
            return
        time.sleep(RUN_RECORD_VISIBILITY_SLEEP_SECONDS)
    raise ControllerServiceError(
        "Run record was not visible after persistence.",
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="run_record_persistence_failed",
    )


def load_run_record(config: ControllerServiceConfig, run_id: str) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ControllerServiceError("Invalid run_id.", status=HTTPStatus.BAD_REQUEST, code="invalid_run_id")
    path = config.run_registry_root / f"{run_id}.json"
    for _ in range(RUN_RECORD_VISIBILITY_RETRIES):
        if path.exists():
            break
        time.sleep(RUN_RECORD_VISIBILITY_SLEEP_SECONDS)
    if not path.exists():
        with RUN_RECORD_CACHE_LOCK:
            cached = RUN_RECORD_CACHE.get((str(config.run_registry_root.resolve()), run_id))
        if cached is not None:
            return json.loads(json.dumps(cached))
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


def parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def approval_continuation_marker(record: dict[str, Any]) -> dict[str, Any]:
    marker = record.get("approval_continuation")
    return marker if isinstance(marker, dict) else {}


def validate_approval_continuation_source(config: ControllerServiceConfig, run_id: str) -> dict[str, Any]:
    record = load_run_record(config, run_id)
    marker = approval_continuation_marker(record)
    marker_status = marker.get("status")
    if marker_status == "consumed":
        raise ControllerServiceError(
            "Approval has already been consumed by a continuation run.",
            status=HTTPStatus.CONFLICT,
            code="approval_already_consumed",
        )
    if marker_status == "denied":
        raise ControllerServiceError(
            "Approval was denied and cannot be continued.",
            status=HTTPStatus.CONFLICT,
            code="approval_denied",
        )
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if summary.get("approval_state_status") != "waiting_for_approval" or summary.get("approval_type") != "packet_design":
        raise ControllerServiceError(
            "The referenced run is not waiting for packet-design approval.",
            status=HTTPStatus.CONFLICT,
            code="approval_not_pending",
        )
    updated_at = parse_utc_timestamp(record.get("updated_at"))
    if updated_at is not None:
        age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age_seconds > APPROVAL_CONTINUATION_TTL_SECONDS:
            raise ControllerServiceError(
                "Packet-design approval has expired; start a fresh planning run.",
                status=HTTPStatus.CONFLICT,
                code="approval_expired",
            )
    return record


def mark_approval_continuation_consumed(
    config: ControllerServiceConfig,
    source_run_id: str,
    continuation_run_id: str | None,
) -> None:
    record = load_run_record(config, source_run_id)
    record["approval_continuation"] = {
        "status": "consumed",
        "continuation_run_id": continuation_run_id,
        "consumed_at": utc_now(),
    }
    persist_run_record(config, record)


def mark_approval_continuation_denied(config: ControllerServiceConfig, source_run_id: str) -> None:
    record = load_run_record(config, source_run_id)
    record["approval_continuation"] = {
        "status": "denied",
        "denied_at": utc_now(),
    }
    persist_run_record(config, record)


def run_record_path(config: ControllerServiceConfig, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ControllerServiceError("Invalid run_id.", status=HTTPStatus.BAD_REQUEST, code="invalid_run_id")
    return config.run_registry_root / f"{run_id}.json"


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControllerServiceError(f"{label} must be a JSON object.")
    return value


def extract_harness_controller_request(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("stream") is True:
        raise ControllerServiceError("Streaming harness responses are not supported yet.", code="stream_not_supported")
    messages = payload.get("messages")
    if not isinstance(messages, list) and "agentic_controller_request" not in payload:
        raise ControllerServiceError(
            "Harness adapter requests must include messages or a top-level agentic_controller_request.",
            code="missing_controller_envelope",
        )
    try:
        envelope = select_latest_controller_envelope(payload, require_message_objects=True)
    except ControllerEnvelopeError as exc:
        raise ControllerServiceError(str(exc), code=exc.code) from exc
    if envelope is None:
        raise ControllerServiceError(
            "Harness adapter requires an explicit JSON agentic_controller_request envelope. "
            "Natural-language chat text is not a workflow request.",
            code="missing_controller_envelope",
        )
    return envelope


def chat_content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for part in (chat_content_to_text(item) for item in value) if part)
    if isinstance(value, dict):
        for key in ("text", "input_text", "content"):
            text = value.get(key)
            if isinstance(text, str):
                return text
            if isinstance(text, (list, dict)):
                return chat_content_to_text(text)
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def latest_user_message_text(payload: dict[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ControllerServiceError(
            "Workflow-router chat requests must include OpenAI-style messages.",
            code="missing_messages",
        )
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user" or role is None:
            text = chat_content_to_text(message.get("content")).strip()
            if text:
                return bounded_string(text, 6000)
    raise ControllerServiceError("Workflow-router chat requires a non-empty latest user message.", code="missing_user_message")


def strip_path_punctuation(value: str) -> str:
    return value.strip().rstrip(".,;:)]}\"'")


def target_paths_from_natural_text(user_request: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for pattern in (WINDOWS_TARGET_RE, POSIX_TARGET_RE):
        for match in pattern.finditer(user_request):
            if pattern is POSIX_TARGET_RE:
                start = match.start("path")
                if start > 0 and user_request[start - 1] not in " \t\r\n\"'`([":
                    continue
            candidate = strip_path_punctuation(match.group("path"))
            if candidate and candidate not in seen:
                paths.append(candidate)
                seen.add(candidate)
    return paths


def natural_text_without_target_paths(user_request: str) -> str:
    text = user_request
    for pattern in (WINDOWS_TARGET_RE, POSIX_TARGET_RE):
        text = pattern.sub(" ", text)
    return text


def target_root_from_natural_request(user_request: str, payload: dict[str, Any]) -> str:
    payload_target = payload.get("target_root")
    if isinstance(payload_target, str) and payload_target.strip():
        return payload_target
    for candidate in target_paths_from_natural_text(user_request):
        return candidate
    raise ControllerServiceError(
        "Workflow-router natural-language requests must name an allowed target_root path.",
        code="missing_target_root",
    )


def is_natural_control_request_without_target(user_request: str) -> bool:
    text = user_request.lower()
    control_terms = (
        "explain skill selection",
        "skill selection for",
        "skill.selection.explain",
        "scaffold a skill",
        "skill.scaffold",
        "skill_id:",
        "prompt_family:",
        "workflow_id:",
        "skill.update",
        "update skill",
        "update skill metadata",
        "skill.deprecate",
        "deprecate a skill",
        "deprecate skill",
        "skill lifecycle",
        "skill_lifecycle",
        "skill batch",
        "skill_batch",
        "register skill",
        "promote skill",
        "skill pack",
        "skill_pack",
        "tool catalog",
        "tool_catalog",
    )
    return any(term in text for term in control_terms)


def no_target_guidance_kind(user_request: str, payload: dict[str, Any]) -> str | None:
    payload_target = payload.get("target_root")
    if isinstance(payload_target, str) and payload_target.strip():
        return None
    if target_paths_from_natural_text(user_request):
        return None
    if RUN_ID_IN_TEXT_RE.search(user_request):
        return None
    if is_natural_control_request_without_target(user_request):
        return None
    guidance_request = re.sub(r"\btracking\s+tag\s*:\s*\S+", " ", user_request, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-z0-9]+", " ", guidance_request.lower()).strip()
    if normalized in {"hi", "hello", "hey", "ping", "test", "hello there"}:
        return "general_chat_no_target"
    if normalized in {"help", "what can you do", "what can you do for me", "how can you help"}:
        return "general_help_no_target"
    coding_or_mutation_terms = {
        "add",
        "bug",
        "change",
        "code",
        "debug",
        "edit",
        "error",
        "explain",
        "failure",
        "file",
        "find",
        "fix",
        "function",
        "investigate",
        "locate",
        "refactor",
        "repo",
        "repository",
        "test",
        "update",
        "without approval",
        "skip approval",
        "bypass approval",
    }
    guidance_request_lower = guidance_request.lower()
    if any(term in guidance_request_lower for term in coding_or_mutation_terms):
        if any(term in guidance_request_lower for term in ("without approval", "skip approval", "bypass approval")):
            return "blocked_missing_target_and_approval"
        return "missing_target_root_for_coding_request"
    return None


def infer_workflow_router_mode(user_request: str) -> str:
    text = user_request.lower()
    if is_skill_batch_proposal_request(text):
        return "execute_read_only"
    if is_task_decomposition_request(text):
        return "execute_read_only"
    if is_large_context_read_only_request(text):
        return "execute_read_only"
    if (
        is_l1_simple_failing_test_fix_request(text)
        or is_l1_small_unit_test_request(text)
        or is_l1_small_text_edit_request(text)
    ):
        return "plan_only"
    read_only_terms = {
        "investigate",
        "inspect",
        "look up",
        "find",
        "explain",
        "what does",
        "what is",
        "where is",
        "where are",
        "which script",
        "which file",
        "which tests",
        "summarize",
        "map the",
        "compare",
        "identify the change surface",
        "start at",
        "beginning point",
        "diagnose",
        "root cause",
        "why did",
        "why does",
        "source refs",
        "references",
        "return value",
        "side effects",
        "related tests",
        "stop before implementation",
        "read-only",
        "read only",
        "do not edit",
        "do not change",
        "do not mutate",
        "don't edit",
        "don't change",
        "don't mutate",
        "without editing",
        "without changing",
        "without mutating",
    }
    if any(term in text for term in read_only_terms):
        return "execute_read_only"
    return "plan_only"


def approval_continuation_run_id(user_request: str) -> str | None:
    text = user_request.lower()
    if not any(term in text for term in ("approve", "approved", "approval")):
        return None
    if not any(term in text for term in ("packet", "implementation prep", "implementation_prepping", "implementation-prep")):
        return None
    match = RUN_ID_IN_TEXT_RE.search(user_request)
    return match.group("run_id") if match else None


def approval_denial_run_id(user_request: str) -> str | None:
    text = natural_text_without_target_paths(user_request).lower()
    denial_terms = ("deny", "denied", "reject", "rejected", "do not approve", "don't approve")
    if not any(term in text for term in denial_terms):
        return None
    if not any(term in text for term in ("packet", "implementation prep", "implementation_prepping", "implementation-prep", "approval")):
        return None
    match = RUN_ID_IN_TEXT_RE.search(user_request)
    return match.group("run_id") if match else None


def approval_continuation_scope_change_requested(user_request: str) -> bool:
    text = natural_text_without_target_paths(user_request).lower()
    if "disposable copy" in text:
        return False
    safe_negations = (
        "do not apply",
        "do not mutate",
        "do not edit",
        "don't apply",
        "don't mutate",
        "don't edit",
        "without applying",
        "without mutating",
        "without editing",
    )
    normalized = text
    for phrase in safe_negations:
        normalized = normalized.replace(phrase, " ")
    scope_change_terms = (
        "apply now",
        "apply the change",
        "apply changes",
        "apply this change",
        "make the change",
        "make changes",
        "edit the source",
        "edit source",
        "write to source",
        "write files",
        "mutate source",
        "mutate the source",
        "mutate target",
        "mutate the target",
        "real apply",
        "commit the change",
    )
    return any(term in normalized for term in scope_change_terms)


def run_ids_from_text(user_request: str) -> list[str]:
    run_ids: list[str] = []
    seen: set[str] = set()
    for match in RUN_ID_IN_TEXT_RE.finditer(user_request):
        run_id = match.group("run_id")
        if run_id not in seen:
            run_ids.append(run_id)
            seen.add(run_id)
    return run_ids


FEEDBACK_LABEL_RE = re.compile(
    r"\b(useful|wrong|missing|too\s+slow|too_slow|too\s+noisy|too_noisy|confusing|unsafe)\s*:",
    re.IGNORECASE,
)


def feedback_label_segment(user_request: str, labels: set[str]) -> str | None:
    matches = list(FEEDBACK_LABEL_RE.finditer(user_request))
    for index, match in enumerate(matches):
        label = re.sub(r"\s+", "_", match.group(1).lower())
        if label not in labels:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(user_request)
        return user_request[start:end].strip()
    return None


def feedback_segment_is_noop(segment: str) -> bool:
    value = segment.strip().lower().strip(" \t\r\n.,;:!")
    if value in {"", "none", "nothing", "n/a", "na", "not applicable", "no issues", "no issue", "no gaps", "no gap"}:
        return True
    return bool(re.fullmatch(r"none\s+(for|needed|observed|found|reported)\b.*", value))


def natural_feedback_requested(user_request: str) -> bool:
    text = user_request.lower()
    if not run_ids_from_text(user_request):
        return False
    explicit_feedback_terms = (
        "record feedback",
        "capture feedback",
        "feedback for",
        "feedback:",
    )
    if any(term in text for term in explicit_feedback_terms):
        return True
    if approval_continuation_run_id(user_request) is not None:
        return False
    feedback_terms = (
        "feedback",
        "useful",
        "wrong",
        "missing",
        "too slow",
        "too_slow",
        "too noisy",
        "too_noisy",
        "confusing",
        "unsafe",
        "worked",
        "passed",
        "failed",
        "did not work",
        "didn't work",
    )
    return any(term in text for term in feedback_terms)


def natural_feedback_from_text(user_request: str) -> dict[str, Any]:
    text = user_request.lower()
    feedback = {
        "useful": [],
        "wrong": [],
        "missing": [],
        "too_slow": [],
        "too_noisy": [],
        "confusing": [],
        "unsafe": [],
        "notes": bounded_string(user_request, 4000),
    }
    if any(term in text for term in ("useful", "worked", "passed")):
        feedback["useful"].append(bounded_string(user_request, 1000))
    if any(term in text for term in ("wrong", "failed", "did not work", "didn't work")):
        feedback["wrong"].append(bounded_string(user_request, 1000))
    missing_segment = feedback_label_segment(user_request, {"missing"})
    if missing_segment is not None:
        if not feedback_segment_is_noop(missing_segment):
            feedback["missing"].append(bounded_string(user_request, 1000))
    elif "missing" in text:
        feedback["missing"].append(bounded_string(user_request, 1000))
    if any(term in text for term in ("too slow", "too_slow")):
        feedback["too_slow"].append(bounded_string(user_request, 1000))
    if any(term in text for term in ("too noisy", "too_noisy")):
        feedback["too_noisy"].append(bounded_string(user_request, 1000))
    if any(term in text for term in ("confusing", "unclear", "hard to understand")):
        feedback["confusing"].append(bounded_string(user_request, 1000))
    if any(term in text for term in ("unsafe", "dangerous", "security issue", "mutated source")):
        feedback["unsafe"].append(bounded_string(user_request, 1000))
    return feedback


def prompt_case_id_from_text(user_request: str) -> str | None:
    patterns = (
        r"\bprompt\s+case\s*[:#-]?\s*([A-Za-z0-9_.:-]+)",
        r"\bcase_id\s*[:#-]?\s*([A-Za-z0-9_.:-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_request, flags=re.IGNORECASE)
        if match:
            return match.group(1).rstrip(".,;:)")
    return None


def natural_skill_batch_registration_requested(user_request: str) -> bool:
    text = user_request.lower()
    if not run_ids_from_text(user_request):
        return False
    approval_terms = ("approve", "approved", "approval")
    registration_terms = ("register", "install", "admit")
    subject_terms = ("skill batch", "skill-batch", "skill registry", "skill proposal")
    return (
        any(term in text for term in approval_terms)
        and any(term in text for term in registration_terms)
        and any(term in text for term in subject_terms)
    )


def proposal_artifact_path_from_run_record(record: dict[str, Any]) -> str | None:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    for key in ("downstream_skill_batch_proposal", "skill_batch_proposal", "proposal"):
        value = artifacts.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def natural_skill_batch_registration_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_batch_registration_requested(user_request):
        return None
    run_ids = run_ids_from_text(user_request)
    source_run_id = run_ids[-1]
    try:
        source_record = load_run_record(config, source_run_id)
    except ControllerServiceError as exc:
        raise ControllerServiceError(
            "Skill-batch registration requires a known prior proposal or workflow-router run_id.",
            status=exc.status,
            code=exc.code,
        ) from exc
    proposal_path = proposal_artifact_path_from_run_record(source_record)
    request: dict[str, Any] = {
        "workflow": SKILL_BATCH_REGISTRATION_WORKFLOW_ID,
        "schema_version": 1,
        "approval": {
            "status": "approved_for_skill_registration",
            "scope": "skill_batch_registration",
            "runtime_registry_append": True,
            "skill_body_install": True,
            "approval_refs": [f"natural_skill_batch_registration:{source_run_id}"],
        },
        "metadata": {
            "source": "workflow_router_natural_skill_batch_registration",
            "source_run_id": source_run_id,
            "message": bounded_string(user_request, 1000),
        },
    }
    if proposal_path:
        request["proposal_path"] = proposal_path
    else:
        request["proposal_run_id"] = source_run_id
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_skill_lifecycle_audit_requested(user_request: str) -> bool:
    text = user_request.lower()
    audit_terms = ("audit", "inspect", "show", "summarize", "review")
    lifecycle_terms = ("skill lifecycle", "lifecycle audit", "lifecycle queue", "skill audit")
    action_terms = ("promote", "promotion", "revise", "deprecate", "draft skills", "validated skills")
    return (
        any(term in text for term in audit_terms)
        and (any(term in text for term in lifecycle_terms) or ("skills" in text and any(term in text for term in action_terms)))
    )


def natural_skill_lifecycle_audit_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_lifecycle_audit_requested(user_request):
        return None
    request: dict[str, Any] = {
        "workflow": SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID,
        "schema_version": 1,
        "metadata": {
            "source": "workflow_router_natural_skill_lifecycle_audit",
            "message": bounded_string(user_request, 1000),
        },
    }
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_skill_selection_explain_requested(user_request: str) -> bool:
    text = user_request.lower()
    explain_terms = ("explain", "why", "show", "inspect", "summarize")
    selection_terms = (
        "skill selection",
        "selected skill",
        "skill selected",
        "why was this skill",
        "why did it choose",
        "why did you choose",
        "why did you select",
    )
    return any(term in text for term in explain_terms) and any(term in text for term in selection_terms)


def skill_selection_subject_from_text(user_request: str) -> str:
    patterns = (
        r"skill selection\s*(?:for|about)?\s*:\s*(?P<subject>.+)",
        r"selected skill\s*(?:for|about)?\s*:\s*(?P<subject>.+)",
        r"why (?:did|was).+?skill.+?(?:for|about)\s*:\s*(?P<subject>.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_request, flags=re.IGNORECASE | re.DOTALL)
        if match:
            subject = match.group("subject").strip()
            if subject:
                return bounded_string(subject, 4000)
    return bounded_string(user_request, 4000)


def natural_skill_selection_explain_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_selection_explain_requested(user_request):
        return None
    subject = skill_selection_subject_from_text(user_request)
    workflow_id, _reason, _evidence = workflow_kind_for_request(subject)
    request: dict[str, Any] = {
        "workflow": SKILL_SELECTION_EXPLAIN_WORKFLOW_ID,
        "schema_version": 1,
        "user_request": subject,
        "max_candidate_count": 5,
        "metadata": {
            "source": "workflow_router_natural_skill_selection_explain",
            "message": bounded_string(user_request, 1000),
        },
    }
    try:
        request["target_root"] = target_root_from_natural_request(user_request, payload)
    except ControllerServiceError:
        pass
    if workflow_id is not None:
        request["workflow_id"] = workflow_id
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def normalize_natural_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def json_objects_from_text(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            objects.append(value)
    return objects


def natural_structured_object(user_request: str) -> dict[str, Any]:
    for value in json_objects_from_text(user_request):
        envelope = value.get("agentic_controller_request")
        if isinstance(envelope, dict):
            return envelope
        return value
    return {}


def natural_label_value(user_request: str, labels: tuple[str, ...]) -> str | None:
    wanted = {normalize_natural_label(label) for label in labels}
    for raw_line in user_request.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        colon_index = line.find(":")
        equals_index = line.find("=")
        indexes = [index for index in (colon_index, equals_index) if index >= 0]
        if not indexes:
            continue
        split_at = min(indexes)
        label = normalize_natural_label(line[:split_at])
        if label in wanted:
            value = line[split_at + 1 :].strip()
            return value or None
    return None


def natural_json_value_after_label(user_request: str, labels: tuple[str, ...]) -> Any:
    value = natural_label_value(user_request, labels)
    if value is None:
        return None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(value)
    except json.JSONDecodeError:
        return None
    return parsed


def natural_string_value(
    user_request: str,
    structured: dict[str, Any],
    key: str,
    labels: tuple[str, ...] | None = None,
) -> str | None:
    value = structured.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    labeled = natural_label_value(user_request, labels or (key,))
    return labeled.strip() if isinstance(labeled, str) and labeled.strip() else None


def natural_list_value(
    user_request: str,
    structured: dict[str, Any],
    key: str,
    labels: tuple[str, ...] | None = None,
) -> list[str] | None:
    value = structured.get(key)
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return [item.strip() for item in value]
    parsed = natural_json_value_after_label(user_request, labels or (key,))
    if isinstance(parsed, list) and all(isinstance(item, str) and item.strip() for item in parsed):
        return [item.strip() for item in parsed]
    labeled = natural_label_value(user_request, labels or (key,))
    if isinstance(labeled, str) and labeled.strip():
        return [item.strip() for item in re.split(r"[,;]", labeled) if item.strip()]
    return None


def natural_dict_value(
    user_request: str,
    structured: dict[str, Any],
    key: str,
    labels: tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    value = structured.get(key)
    if isinstance(value, dict):
        return value
    parsed = natural_json_value_after_label(user_request, labels or (key,))
    return parsed if isinstance(parsed, dict) else None


def natural_json_list_of_objects(
    user_request: str,
    structured: dict[str, Any],
    key: str,
    labels: tuple[str, ...] | None = None,
) -> list[dict[str, Any]] | None:
    value = structured.get(key)
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    parsed = natural_json_value_after_label(user_request, labels or (key,))
    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
        return parsed
    return None


def natural_path_value(
    user_request: str,
    structured: dict[str, Any],
    key: str,
    labels: tuple[str, ...] | None = None,
    *,
    require_json_suffix: bool = False,
) -> str | None:
    value = natural_string_value(user_request, structured, key, labels)
    if value:
        return strip_path_punctuation(value)
    for pattern in (WINDOWS_TARGET_RE, POSIX_TARGET_RE):
        for match in pattern.finditer(user_request):
            candidate = strip_path_punctuation(match.group("path"))
            if candidate and (not require_json_suffix or candidate.lower().endswith(".json")):
                return candidate
    return None


def natural_skill_scaffold_requested(user_request: str) -> bool:
    text = user_request.lower()
    return "scaffold" in text and "skill" in text


def natural_skill_scaffold_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_scaffold_requested(user_request):
        return None
    structured = natural_structured_object(user_request)
    prompt_family_spec = structured.get("prompt_family_spec") if isinstance(structured.get("prompt_family_spec"), dict) else {}
    if not prompt_family_spec:
        prompt_family_spec = structured
    spec: dict[str, Any] = {}
    string_fields = {
        "skill_id": ("skill_id", "skill id"),
        "description": ("description",),
        "prompt_family": ("prompt_family", "prompt family"),
        "natural_prompt": ("natural_prompt", "natural prompt"),
        "workflow_id": ("workflow_id", "workflow id", "workflow"),
        "route_key": ("route_key", "route key"),
        "output_artifact": ("output_artifact", "output artifact"),
        "live_suite": ("live_suite", "live suite"),
    }
    for key, labels in string_fields.items():
        value = natural_string_value(user_request, prompt_family_spec, key, labels)
        if value is not None:
            spec[key] = value
    for key, labels in {
        "trigger_terms": ("trigger_terms", "trigger terms", "triggers"),
        "task_types": ("task_types", "task types"),
    }.items():
        value = natural_list_value(user_request, prompt_family_spec, key, labels)
        if value is not None:
            spec[key] = value
    for key in ("owner", "safety_level", "mutation_policy", "approval_boundary", "eval_case_id"):
        value = natural_string_value(user_request, prompt_family_spec, key, (key,))
        if value is not None:
            spec[key] = value
    docs = natural_list_value(user_request, prompt_family_spec, "docs", ("docs", "doc refs"))
    if docs is not None:
        spec["docs"] = docs
    role_id = payload.get("role_id")
    request: dict[str, Any] = {
        "workflow": SKILL_SCAFFOLD_WORKFLOW_ID,
        "schema_version": 1,
        "prompt_family_spec": spec,
        "metadata": {
            "source": "workflow_router_natural_skill_scaffold",
            "message": bounded_string(user_request, 1000),
        },
    }
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_skill_pack_validation_requested(user_request: str) -> bool:
    text = user_request.lower()
    return "pack" in text and "skill" in text and any(term in text for term in ("validate", "validation", "check"))


def natural_skill_pack_install_requested(user_request: str) -> bool:
    text = user_request.lower()
    return "pack" in text and "skill" in text and any(term in text for term in ("install", "admit", "register"))


def natural_skill_update_requested(user_request: str) -> bool:
    text = user_request.lower()
    return "skill.update" in text or ("skill" in text and any(term in text for term in ("update", "change metadata", "metadata update")))


def natural_skill_deprecation_requested(user_request: str) -> bool:
    text = user_request.lower()
    return "skill.deprecate" in text or ("skill" in text and any(term in text for term in ("deprecate", "deprecation")))


def explicit_natural_approval(user_request: str, workflow: str) -> bool:
    text = re.sub(r"\s+", " ", user_request.lower()).strip()
    phrases = {
        SKILL_PACK_INSTALL_WORKFLOW_ID: (
            "approved for skill pack install",
            "approve skill pack install",
            "approved for skill_pack.install",
            "approve skill_pack.install",
        ),
        SKILL_UPDATE_WORKFLOW_ID: (
            "approved for skill update",
            "approve skill update",
            "approved for skill.update",
            "approve skill.update",
        ),
        SKILL_DEPRECATION_WORKFLOW_ID: (
            "approved for skill deprecation",
            "approve skill deprecation",
            "approved for skill.deprecate",
            "approve skill.deprecate",
        ),
    }.get(workflow, ())
    return any(phrase in text for phrase in phrases)


def skill_update_categories_from_request(request: dict[str, Any]) -> set[str]:
    categories: set[str] = set()
    if isinstance(request.get("metadata_updates"), dict) and request["metadata_updates"]:
        categories.add("metadata")
    if isinstance(request.get("skill_body_text"), str):
        categories.add("body")
    if isinstance(request.get("eval_case_updates"), list) and request["eval_case_updates"]:
        categories.add("eval_case")
    return categories


def approval_template_for_workflow(workflow: str, request: dict[str, Any], approval_ref: str) -> dict[str, Any]:
    if workflow == SKILL_PACK_INSTALL_WORKFLOW_ID:
        return {
            "status": "approved_for_skill_pack_install",
            "scope": "skill_pack_install",
            "runtime_registry_append": True,
            "skill_body_install": True,
            "approval_refs": [approval_ref],
        }
    if workflow == SKILL_UPDATE_WORKFLOW_ID:
        categories = skill_update_categories_from_request(request)
        return {
            "status": "approved_for_skill_update",
            "scope": "skill_update",
            "runtime_registry_update": True,
            "skill_metadata_update": True,
            "skill_body_update": "body" in categories,
            "eval_case_update": "eval_case" in categories,
            "approval_refs": [approval_ref],
        }
    if workflow == SKILL_DEPRECATION_WORKFLOW_ID:
        return {
            "status": "approved_for_skill_deprecation",
            "scope": "skill_deprecation",
            "eval_status_update": True,
            "runtime_registry_update": True,
            "approval_refs": [approval_ref],
        }
    return {"approval_refs": [approval_ref]}


def natural_approval_for_workflow(
    user_request: str,
    structured: dict[str, Any],
    workflow: str,
    request: dict[str, Any],
    *,
    source_run_id: str | None,
) -> dict[str, Any] | None:
    approval = structured.get("approval")
    if isinstance(approval, dict):
        return approval
    if not explicit_natural_approval(user_request, workflow):
        return None
    suffix = source_run_id or "inline"
    approval_ref = f"natural_{workflow.replace('.', '_')}:{suffix}"
    return approval_template_for_workflow(workflow, request, approval_ref)


def missing_lifecycle_request_fields(workflow: str, request: dict[str, Any]) -> list[str]:
    if workflow == SKILL_PACK_INSTALL_WORKFLOW_ID:
        required = ("pack_path",)
    elif workflow == SKILL_UPDATE_WORKFLOW_ID:
        required = ("skill_id", "change_type", "version_bump")
    elif workflow == SKILL_DEPRECATION_WORKFLOW_ID:
        required = ("skill_id", "replacement_skill_id", "reason", "effective_date")
    else:
        required = ()
    missing = [key for key in required if not request.get(key)]
    if workflow == SKILL_UPDATE_WORKFLOW_ID and not skill_update_categories_from_request(request):
        missing.append("metadata_updates_or_skill_body_text_or_eval_case_updates")
    return missing


def read_json_artifact(path_value: Any) -> dict[str, Any] | None:
    if not isinstance(path_value, str):
        return None
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def approval_requirement_from_run(config: ControllerServiceConfig, run_id: str) -> dict[str, Any] | None:
    try:
        record = load_run_record(config, run_id)
    except ControllerServiceError:
        return None
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    requirement = read_json_artifact(artifacts.get("approval_requirement"))
    if isinstance(requirement, dict) and requirement.get("kind") == "natural_lifecycle_approval_requirement":
        return requirement
    return None


def prior_lifecycle_request_from_approval_run(
    config: ControllerServiceConfig,
    user_request: str,
    workflow: str,
) -> tuple[dict[str, Any], str] | None:
    if not explicit_natural_approval(user_request, workflow):
        return None
    for run_id in reversed(run_ids_from_text(user_request)):
        requirement = approval_requirement_from_run(config, run_id)
        if not isinstance(requirement, dict):
            continue
        proposed = requirement.get("proposed_request")
        if isinstance(proposed, dict) and proposed.get("workflow") == workflow:
            return deepcopy_json_object(proposed), run_id
    return None


def deepcopy_json_object(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=True))


def natural_lifecycle_approval_required_response(
    *,
    config: ControllerServiceConfig,
    user_request: str,
    proposed_request: dict[str, Any],
    missing_request_fields: list[str],
    approval_present: bool,
) -> dict[str, Any]:
    workflow = str(proposed_request.get("workflow") or "skill_lifecycle")
    run_id = f"skill-lifecycle-approval-required-{natural_artifact_timestamp()}"
    run_dir = config.output_root / NATURAL_LIFECYCLE_APPROVAL_REQUIRED_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    required_approval = approval_template_for_workflow(
        workflow,
        proposed_request,
        f"natural_{workflow.replace('.', '_')}:{run_id}",
    )
    approval_phrase = {
        SKILL_PACK_INSTALL_WORKFLOW_ID: "Approved for skill pack install",
        SKILL_UPDATE_WORKFLOW_ID: "Approved for skill update",
        SKILL_DEPRECATION_WORKFLOW_ID: "Approved for skill deprecation",
    }.get(workflow, "Approved for lifecycle operation")
    summary = {
        "route_status": "approval_required",
        "selected_workflow": workflow,
        "approval_status": "present_but_request_fields_missing" if approval_present else "missing_explicit_approval",
        "required_approval": required_approval,
        "missing_request_fields": missing_request_fields,
        "runtime_registry_changed": False,
        "target_repository_changed": False,
        "next_action": f"{approval_phrase} run_id {run_id}",
    }
    requirement = {
        "kind": "natural_lifecycle_approval_requirement",
        "schema_version": 1,
        "workflow": workflow,
        "run_id": run_id,
        "status": "approval_required",
        "summary": summary,
        "proposed_request": proposed_request,
        "required_approval": required_approval,
        "missing_request_fields": missing_request_fields,
        "source_message": bounded_string(user_request, 4000),
        "created_at": utc_now(),
    }
    request_artifact = {
        "kind": "natural_lifecycle_approval_required_request",
        "schema_version": 1,
        "workflow": workflow,
        "run_id": run_id,
        "user_request": bounded_string(user_request, 4000),
        "created_at": utc_now(),
    }
    requirement_path = run_dir / "approval-requirement.json"
    request_path = run_dir / "request.json"
    requirement_path.write_bytes(json_bytes(requirement))
    request_path.write_bytes(json_bytes(request_artifact))
    response = {
        "run_id": run_id,
        "workflow": workflow,
        "status": "approval_required",
        "artifacts": {
            "request": str(request_path),
            "approval_requirement": str(requirement_path),
        },
        "summary": summary,
        "warnings": [],
        "failures": [],
        "resume_key": {"schema_version": 1, "approval_requirement": str(requirement_path)},
    }
    persist_run_record(config, response)
    return response


def natural_skill_pack_validation_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_pack_validation_requested(user_request):
        return None
    structured = natural_structured_object(user_request)
    pack_path = natural_path_value(
        user_request,
        structured,
        "pack_path",
        ("pack_path", "pack path", "path"),
        require_json_suffix=True,
    )
    request: dict[str, Any] = {
        "workflow": SKILL_PACK_VALIDATION_WORKFLOW_ID,
        "schema_version": 1,
        "pack_path": pack_path,
        "metadata": {
            "source": "workflow_router_natural_skill_pack_validation",
            "message": bounded_string(user_request, 1000),
        },
    }
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_skill_pack_install_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_pack_install_requested(user_request):
        return None
    structured = natural_structured_object(user_request)
    prior = prior_lifecycle_request_from_approval_run(config, user_request, SKILL_PACK_INSTALL_WORKFLOW_ID)
    source_run_id: str | None = None
    if prior is not None:
        request, source_run_id = prior
    else:
        request = {
            "workflow": SKILL_PACK_INSTALL_WORKFLOW_ID,
            "schema_version": 1,
            "pack_path": natural_path_value(
                user_request,
                structured,
                "pack_path",
                ("pack_path", "pack path", "path"),
                require_json_suffix=True,
            ),
            "metadata": {
                "source": "workflow_router_natural_skill_pack_install",
                "message": bounded_string(user_request, 1000),
            },
        }
    approval = natural_approval_for_workflow(
        user_request,
        structured,
        SKILL_PACK_INSTALL_WORKFLOW_ID,
        request,
        source_run_id=source_run_id,
    )
    missing_fields = missing_lifecycle_request_fields(SKILL_PACK_INSTALL_WORKFLOW_ID, request)
    if approval is None or missing_fields:
        return {
            "workflow": NATURAL_LIFECYCLE_APPROVAL_REQUIRED_WORKFLOW,
            "proposed_request": request,
            "response": natural_lifecycle_approval_required_response(
                config=config,
                user_request=user_request,
                proposed_request=request,
                missing_request_fields=missing_fields,
                approval_present=approval is not None,
            ),
        }
    request = {**request, "approval": approval}
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_skill_update_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_update_requested(user_request):
        return None
    structured = natural_structured_object(user_request)
    prior = prior_lifecycle_request_from_approval_run(config, user_request, SKILL_UPDATE_WORKFLOW_ID)
    source_run_id: str | None = None
    if prior is not None:
        request, source_run_id = prior
    else:
        request = {
            "workflow": SKILL_UPDATE_WORKFLOW_ID,
            "schema_version": 1,
            "skill_id": natural_string_value(user_request, structured, "skill_id", ("skill_id", "skill id")),
            "change_type": natural_string_value(user_request, structured, "change_type", ("change_type", "change type")),
            "version_bump": natural_string_value(user_request, structured, "version_bump", ("version_bump", "version bump")),
            "metadata_updates": natural_dict_value(
                user_request,
                structured,
                "metadata_updates",
                ("metadata_updates", "metadata updates"),
            )
            or {},
            "skill_body_text": natural_string_value(
                user_request,
                structured,
                "skill_body_text",
                ("skill_body_text", "skill body text"),
            ),
            "eval_case_updates": natural_json_list_of_objects(
                user_request,
                structured,
                "eval_case_updates",
                ("eval_case_updates", "eval case updates"),
            )
            or [],
            "metadata": {
                "source": "workflow_router_natural_skill_update",
                "message": bounded_string(user_request, 1000),
            },
        }
        if not request.get("skill_body_text"):
            request.pop("skill_body_text", None)
    approval = natural_approval_for_workflow(
        user_request,
        structured,
        SKILL_UPDATE_WORKFLOW_ID,
        request,
        source_run_id=source_run_id,
    )
    missing_fields = missing_lifecycle_request_fields(SKILL_UPDATE_WORKFLOW_ID, request)
    if approval is None or missing_fields:
        return {
            "workflow": NATURAL_LIFECYCLE_APPROVAL_REQUIRED_WORKFLOW,
            "proposed_request": request,
            "response": natural_lifecycle_approval_required_response(
                config=config,
                user_request=user_request,
                proposed_request=request,
                missing_request_fields=missing_fields,
                approval_present=approval is not None,
            ),
        }
    request = {**request, "approval": approval}
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_skill_deprecation_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_skill_deprecation_requested(user_request):
        return None
    structured = natural_structured_object(user_request)
    prior = prior_lifecycle_request_from_approval_run(config, user_request, SKILL_DEPRECATION_WORKFLOW_ID)
    source_run_id: str | None = None
    if prior is not None:
        request, source_run_id = prior
    else:
        request = {
            "workflow": SKILL_DEPRECATION_WORKFLOW_ID,
            "schema_version": 1,
            "skill_id": natural_string_value(user_request, structured, "skill_id", ("skill_id", "skill id")),
            "replacement_skill_id": natural_string_value(
                user_request,
                structured,
                "replacement_skill_id",
                ("replacement_skill_id", "replacement skill id", "replacement"),
            ),
            "reason": natural_string_value(user_request, structured, "reason", ("reason",)),
            "effective_date": natural_string_value(
                user_request,
                structured,
                "effective_date",
                ("effective_date", "effective date"),
            ),
            "metadata": {
                "source": "workflow_router_natural_skill_deprecation",
                "message": bounded_string(user_request, 1000),
            },
        }
    approval = natural_approval_for_workflow(
        user_request,
        structured,
        SKILL_DEPRECATION_WORKFLOW_ID,
        request,
        source_run_id=source_run_id,
    )
    missing_fields = missing_lifecycle_request_fields(SKILL_DEPRECATION_WORKFLOW_ID, request)
    if approval is None or missing_fields:
        return {
            "workflow": NATURAL_LIFECYCLE_APPROVAL_REQUIRED_WORKFLOW,
            "proposed_request": request,
            "response": natural_lifecycle_approval_required_response(
                config=config,
                user_request=user_request,
                proposed_request=request,
                missing_request_fields=missing_fields,
                approval_present=approval is not None,
            ),
        }
    request = {**request, "approval": approval}
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_lifecycle_operation_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    for builder in (
        natural_skill_scaffold_payload,
        natural_skill_pack_validation_payload,
        natural_skill_pack_install_payload,
        natural_skill_update_payload,
        natural_skill_deprecation_payload,
    ):
        request = builder(payload, user_request, config)
        if request is not None:
            return request
    return None


def extract_json_packet_operations(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            operations = value.get("packet_operations")
            if isinstance(operations, list) and all(isinstance(item, dict) for item in operations):
                return operations
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    return []


def packet_operations_from_natural_request(payload: dict[str, Any], user_request: str) -> list[dict[str, Any]]:
    operations = payload.get("packet_operations")
    if isinstance(operations, list) and all(isinstance(item, dict) for item in operations):
        return operations
    return extract_json_packet_operations(user_request)


def packet_objective_requested(user_request: str) -> bool:
    text = user_request.lower()
    return bool(run_ids_from_text(user_request)) and (
        "packet objective" in text
        or "packet_objective" in text
        or "implementation objective" in text
    )


def packet_objective_from_text(user_request: str) -> str:
    marker_patterns = (
        r"packet[_ -]objective\s*:\s*(?P<objective>.+)",
        r"implementation objective\s*:\s*(?P<objective>.+)",
    )
    for pattern in marker_patterns:
        match = re.search(pattern, user_request, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return bounded_string(match.group("objective").strip(), 2000)
    objective = RUN_ID_IN_TEXT_RE.sub("", user_request)
    objective = re.sub(r"\b(for|from)\s+run\b", "", objective, flags=re.IGNORECASE)
    return bounded_string(objective.strip(), 2000)


def natural_implementation_prep_execution_budgets(payload: dict[str, Any]) -> dict[str, Any]:
    budgets = payload.get("execution_budgets")
    if isinstance(budgets, dict):
        return budgets
    return dict(NATURAL_IMPLEMENTATION_PREP_EXECUTION_BUDGETS)


def draft_only_small_text_edit_requested(user_request: str) -> bool:
    text = re.sub(r"`[^`]*`|\"[^\"]*\"|'[^']*'", " ", user_request.lower())
    text = WINDOWS_TARGET_RE.sub(" ", text)
    text = POSIX_TARGET_RE.sub(" ", text)
    return any(term in text for term in ("draft", "draft-only", "draft only", "dry run", "do not mutate", "do not edit files"))


def natural_small_text_edit_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not is_l1_small_text_edit_request(user_request.lower()):
        return None
    if not draft_only_small_text_edit_requested(user_request):
        return None
    instruction = extract_small_text_edit_instruction(user_request)
    if instruction is None:
        return None
    target_root = target_root_from_natural_request(user_request, payload)
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            f"{user_request} Use draft mode only, do not mutate the target repository, "
            "and produce exact packet operations only from the named target file and anchor."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "draft_text_edit_packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["natural_l1_small_text_edit:draft_only_request"],
        },
        "packet_operations": [],
        "context": {
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_small_text_edit",
                    "small_text_edit": instruction,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def natural_small_unit_test_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not is_l1_small_unit_test_request(user_request.lower()):
        return None
    if not draft_only_small_text_edit_requested(user_request):
        return None
    instruction = extract_small_unit_test_instruction(user_request)
    if instruction is None:
        return None
    target_root = target_root_from_natural_request(user_request, payload)
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            f"{user_request} Use draft mode only, do not mutate the target repository, "
            "select an existing related pytest file, and produce exact packet operations only."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "draft_unit_test_packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["natural_l1_small_unit_test:draft_only_request"],
        },
        "packet_operations": [],
        "context": {
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_small_unit_test",
                    "small_unit_test": instruction,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def natural_simple_test_fix_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not is_l1_simple_failing_test_fix_request(user_request.lower()):
        return None
    if not draft_only_small_text_edit_requested(user_request):
        return None
    instruction = extract_simple_test_fix_instruction(user_request)
    if instruction is None:
        return None
    target_root = target_root_from_natural_request(user_request, payload)
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            f"{user_request} Use draft mode only, do not mutate the target repository, "
            "and produce exact packet operations only when the failing test maps to a supported simple fix."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "draft_simple_test_fix_packet_design_only",
            "apply_allowed": False,
            "approval_refs": ["natural_l1_simple_test_fix:draft_only_request"],
        },
        "packet_operations": [],
        "context": {
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_simple_test_fix",
                    "simple_test_fix": instruction,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def narrowed_edit_objective_requested(user_request: str) -> bool:
    text = user_request.lower()
    return bool(run_ids_from_text(user_request)) and (
        "narrowed edit objective" in text
        or "narrowed_edit_objective" in text
        or "narrowed objective" in text
        or "behavior delta" in text
    )


def narrowed_edit_objective_from_text(user_request: str) -> str:
    marker_patterns = (
        r"narrowed[_ -]edit[_ -]objective\s*:\s*(?P<objective>.+)",
        r"narrowed[_ -]objective\s*:\s*(?P<objective>.+)",
        r"behavior delta\s*:\s*(?P<objective>.+)",
    )
    for pattern in marker_patterns:
        match = re.search(pattern, user_request, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return bounded_string(match.group("objective").strip(), 2000)
    objective = RUN_ID_IN_TEXT_RE.sub("", user_request)
    objective = re.sub(r"\b(for|from)\s+run\b", "", objective, flags=re.IGNORECASE)
    return bounded_string(objective.strip(), 2000)


def run_artifact_json(record: dict[str, Any], artifact_key: str) -> dict[str, Any] | None:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    artifact_path = artifacts.get(artifact_key)
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        return None
    try:
        value = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def approved_run_id_from_packet_objective_source(record: dict[str, Any]) -> str | None:
    decision = run_artifact_json(record, "route_decision")
    proposal_summary = decision.get("packet_operation_proposal") if isinstance(decision, dict) else None
    if isinstance(proposal_summary, dict):
        approved_run_id = proposal_summary.get("approved_run_id")
        if isinstance(approved_run_id, str) and approved_run_id.strip():
            return approved_run_id
    proposal = run_artifact_json(record, "packet_operation_proposal")
    if isinstance(proposal, dict):
        approved_run_id = proposal.get("approved_run_id")
        if isinstance(approved_run_id, str) and approved_run_id.strip():
            return approved_run_id
    return None


def packet_objective_from_narrowed_source(record: dict[str, Any]) -> str | None:
    decision = run_artifact_json(record, "route_decision")
    if not isinstance(decision, dict):
        return None
    packet_objective = decision.get("packet_objective")
    if isinstance(packet_objective, dict):
        objective = packet_objective.get("objective")
        if isinstance(objective, str) and objective.strip():
            return bounded_string(objective.strip(), 2000)
    outcome = decision.get("packet_objective_outcome")
    if isinstance(outcome, dict):
        objective = outcome.get("objective")
        if isinstance(objective, str) and objective.strip():
            return bounded_string(objective.strip(), 2000)
    return None


def prior_run_target_root(config: ControllerServiceConfig, run_id: str) -> str | None:
    try:
        record = load_run_record(config, run_id)
    except ControllerServiceError:
        return None
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    target_root = summary.get("target_root")
    if isinstance(target_root, str) and target_root.strip():
        return target_root
    request_payload = record.get("request_payload") if isinstance(record.get("request_payload"), dict) else {}
    target_root = request_payload.get("target_root")
    return target_root if isinstance(target_root, str) and target_root.strip() else None


def natural_workflow_feedback_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not natural_feedback_requested(user_request):
        return None
    run_ids = run_ids_from_text(user_request)
    target_run_id = run_ids[-1]
    try:
        target_record = load_run_record(config, target_run_id)
    except ControllerServiceError as exc:
        raise ControllerServiceError(
            "Natural feedback requires a known prior run_id.",
            status=exc.status,
            code=exc.code,
        ) from exc
    target_workflow = target_record.get("workflow")
    if not isinstance(target_workflow, str) or not target_workflow.strip():
        raise ControllerServiceError(
            "Natural feedback target run record does not include a workflow.",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="invalid_run_record",
        )
    target_root = prior_run_target_root(config, target_run_id)
    artifact_refs: dict[str, Any] = {
        "source": "workflow_router_natural_feedback",
        "mentioned_run_ids": run_ids,
    }
    prompt_case_id = prompt_case_id_from_text(user_request)
    if prompt_case_id:
        artifact_refs["prompt_case_id"] = prompt_case_id
    related_run_ids = [run_id for run_id in run_ids if run_id != target_run_id]
    if related_run_ids:
        artifact_refs["related_run_ids"] = related_run_ids
    request: dict[str, Any] = {
        "workflow": WORKFLOW_FEEDBACK_WORKFLOW_ID,
        "schema_version": 1,
        "target_workflow": target_workflow,
        "target_run_id": target_run_id,
        "feedback": natural_feedback_from_text(user_request),
        "tester": {
            "id": "natural-workflow-router",
            "surface": "workflow-router-chat",
        },
        "request_payload": {
            "source": "workflow_router_natural_feedback",
            "message": bounded_string(user_request, 1000),
        },
        "artifact_refs": artifact_refs,
    }
    if target_root:
        request["target_root"] = target_root
    role_id = payload.get("role_id")
    if isinstance(role_id, str) and role_id.strip():
        request["role_id"] = role_id
    return request


def natural_packet_objective_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not packet_objective_requested(user_request):
        return None
    run_ids = run_ids_from_text(user_request)
    source_run_id = run_ids[-1]
    try:
        source_record = load_run_record(config, source_run_id)
    except ControllerServiceError as exc:
        raise ControllerServiceError(
            "Packet-objective follow-up requires a known prior workflow-router run_id.",
            status=exc.status,
            code=exc.code,
        ) from exc
    target_root = prior_run_target_root(config, source_run_id)
    if target_root is None:
        raise ControllerServiceError(
            "Packet-objective follow-up could not recover target_root from the prior run.",
            code="missing_target_root",
        )
    approved_run_id = approved_run_id_from_packet_objective_source(source_record)
    if approved_run_id is None:
        raise ControllerServiceError(
            "Packet-objective follow-up could not recover the approved investigation run_id.",
            code="missing_approved_run_id",
        )
    objective = packet_objective_from_text(user_request)
    if not objective:
        raise ControllerServiceError(
            "Packet-objective follow-up requires objective text.",
            code="missing_packet_objective",
        )
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Prepare implementation packet candidates for this packet objective: "
            f"{objective} Use draft mode only, do not mutate the target repository, "
            "and do not search the target repo for workflow run IDs."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": [
                f"natural_packet_objective:{source_run_id}",
                f"natural_approval:{approved_run_id}",
            ],
        },
        "packet_operations": packet_operations_from_natural_request(payload, user_request),
        "context": {
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_packet_objective",
                    "source_run_id": source_run_id,
                    "approved_run_id": approved_run_id,
                    "packet_objective": objective,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def approved_investigation_packet_prep_requested(user_request: str) -> bool:
    text = user_request.lower()
    if not run_ids_from_text(user_request):
        return False
    packet_terms = (
        "packet operations",
        "packet_operations",
        "implementation packet",
        "implementation prep",
        "implementation-prep",
        "dry-run implementation",
        "dry run implementation",
    )
    investigation_terms = (
        "approved investigation",
        "approved read-only investigation",
        "approved read only investigation",
        "convert this investigation",
        "convert the investigation",
        "from this investigation",
        "from the investigation",
    )
    draft_terms = ("draft only", "draft-only", "dry run", "do not mutate", "do not edit", "do not apply")
    return any(term in text for term in packet_terms) and any(term in text for term in investigation_terms) and any(
        term in text for term in draft_terms
    )


def run_record_has_packet_seed_artifact(record: dict[str, Any]) -> bool:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    return any(
        isinstance(artifacts.get(key), str) and artifacts.get(key)
        for key in ("downstream_investigation_plan", "downstream_refactor_plan")
    )


def natural_approved_investigation_packet_prep_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not approved_investigation_packet_prep_requested(user_request):
        return None
    source_run_id = run_ids_from_text(user_request)[-1]
    try:
        source_record = load_run_record(config, source_run_id)
    except ControllerServiceError as exc:
        raise ControllerServiceError(
            "Approved-investigation packet prep requires a known prior workflow-router run_id.",
            status=exc.status,
            code=exc.code,
        ) from exc
    if source_record.get("status") != "completed":
        raise ControllerServiceError(
            "Approved-investigation packet prep requires a completed prior run.",
            status=HTTPStatus.CONFLICT,
            code="source_run_not_completed",
        )
    if not run_record_has_packet_seed_artifact(source_record):
        raise ControllerServiceError(
            "Approved-investigation packet prep requires a prior run with an implementation packet seed artifact.",
            status=HTTPStatus.CONFLICT,
            code="missing_packet_seed_artifact",
        )
    target_root = prior_run_target_root(config, source_run_id)
    if target_root is None:
        raise ControllerServiceError(
            "Approved-investigation packet prep could not recover target_root from the prior run.",
            code="missing_target_root",
        )
    objective = packet_objective_from_text(user_request)
    if not objective:
        raise ControllerServiceError(
            "Approved-investigation packet prep requires an implementation objective.",
            code="missing_packet_objective",
        )
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Prepare implementation packet candidates from an approved read-only investigation. "
            f"Implementation objective: {objective} "
            "Use draft mode only, do not mutate the target repository, "
            "and use the prior investigation artifact as the packet seed."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": [f"natural_approved_investigation:{source_run_id}"],
        },
        "packet_operations": packet_operations_from_natural_request(payload, user_request),
        "context": {
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_approved_investigation_packet_prep",
                    "approved_run_id": source_run_id,
                    "packet_objective": objective,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def natural_narrowed_edit_objective_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not narrowed_edit_objective_requested(user_request):
        return None
    run_ids = run_ids_from_text(user_request)
    source_run_id = run_ids[-1]
    try:
        source_record = load_run_record(config, source_run_id)
    except ControllerServiceError as exc:
        raise ControllerServiceError(
            "Narrowed-edit follow-up requires a known prior workflow-router run_id.",
            status=exc.status,
            code=exc.code,
        ) from exc
    target_root = prior_run_target_root(config, source_run_id)
    if target_root is None:
        raise ControllerServiceError(
            "Narrowed-edit follow-up could not recover target_root from the prior run.",
            code="missing_target_root",
        )
    approved_run_id = approved_run_id_from_packet_objective_source(source_record)
    if approved_run_id is None:
        raise ControllerServiceError(
            "Narrowed-edit follow-up could not recover the approved investigation run_id.",
            code="missing_approved_run_id",
        )
    packet_objective = packet_objective_from_narrowed_source(source_record)
    if packet_objective is None:
        raise ControllerServiceError(
            "Narrowed-edit follow-up could not recover the prior packet objective.",
            code="missing_packet_objective",
        )
    narrowed_objective = narrowed_edit_objective_from_text(user_request)
    if not narrowed_objective:
        raise ControllerServiceError(
            "Narrowed-edit follow-up requires objective text.",
            code="missing_narrowed_edit_objective",
        )
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Prepare implementation packet candidates for this narrowed edit objective: "
            f"{narrowed_objective} Prior packet objective: {packet_objective} "
            "Use draft mode only, do not mutate the target repository, "
            "and do not search the target repo for workflow run IDs."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": [
                f"natural_narrowed_edit_objective:{source_run_id}",
                f"natural_approval:{approved_run_id}",
            ],
        },
        "packet_operations": packet_operations_from_natural_request(payload, user_request),
        "context": {
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_narrowed_edit_objective",
                    "source_run_id": source_run_id,
                    "approved_run_id": approved_run_id,
                    "packet_objective": packet_objective,
                    "narrowed_edit_objective": narrowed_objective,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def natural_approval_continuation_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    approved_run_id = approval_continuation_run_id(user_request)
    if approved_run_id is None:
        return None
    validate_approval_continuation_source(config, approved_run_id)
    if approval_continuation_scope_change_requested(user_request):
        raise ControllerServiceError(
            "Approval continuation is scoped to draft packet design only; source apply or mutation requires a separate approval path.",
            status=HTTPStatus.CONFLICT,
            code="approval_scope_changed",
        )
    target_root = prior_run_target_root(config, approved_run_id)
    if target_root is None:
        raise ControllerServiceError(
            "Approval continuation requires a known prior workflow-router run_id with a recoverable target_root.",
            code="missing_target_root",
        )
    payload_target = payload.get("target_root")
    if isinstance(payload_target, str) and payload_target.strip():
        if Path(payload_target).resolve() != Path(target_root).resolve():
            raise ControllerServiceError(
                "Approval continuation target_root must match the referenced run target_root.",
                status=HTTPStatus.CONFLICT,
                code="approval_scope_changed",
            )
    mentioned_targets = target_paths_from_natural_text(user_request)
    for mentioned_target in mentioned_targets:
        if Path(mentioned_target).resolve() != Path(target_root).resolve():
            raise ControllerServiceError(
                "Approval continuation target path must match the referenced run target_root.",
                status=HTTPStatus.CONFLICT,
                code="approval_scope_changed",
            )
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Prepare implementation packet candidates for approved exact packet operations. "
            "Use draft mode only, do not mutate the target repository, and do not search the target repo for approval run IDs."
        ),
        "mode": "implementation_prep",
        "approval": {
            "status": "approved_for_packet_design",
            "scope": "packet_design_only",
            "apply_allowed": False,
            "approval_refs": [f"natural_approval:{approved_run_id}"],
        },
        "packet_operations": packet_operations_from_natural_request(payload, user_request),
        "context": {
            "approval_continuation_source_run_id": approved_run_id,
            "allowed_context_tools": ["structure_index", "git_grep", "read_file", "manual"],
            "bounded_context": [
                {
                    "source": "workflow_router_natural_approval",
                    "approved_run_id": approved_run_id,
                }
            ],
        },
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
        "execution_budgets": natural_implementation_prep_execution_budgets(payload),
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def block_denied_natural_approval(user_request: str, config: ControllerServiceConfig) -> None:
    denied_run_id = approval_denial_run_id(user_request)
    if denied_run_id is None:
        return
    validate_approval_continuation_source(config, denied_run_id)
    mark_approval_continuation_denied(config, denied_run_id)
    raise ControllerServiceError(
        "Packet-design approval was denied. No continuation will run.",
        status=HTTPStatus.CONFLICT,
        code="approval_denied",
    )


def disposable_copy_apply_requested(user_request: str) -> bool:
    text = user_request.lower()
    explicit_copy_only = (
        "only to a disposable copy" in text
        or "to a disposable copy only" in text
        or "disposable copy only" in text
    )
    source_unchanged_proof = (
        "source repo did not change" in text
        or "source repository did not change" in text
        or "do not mutate the source" in text
        or "do not mutate the source repo" in text
        or "do not mutate the source repository" in text
    )
    return (
        "disposable copy" in text
        and "apply" in text
        and ("approved" in text or "approval" in text or (explicit_copy_only and source_unchanged_proof))
        and ("packet_operations" in text or "packet operation" in text)
    )


def natural_disposable_copy_apply_payload(
    payload: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any] | None:
    if not disposable_copy_apply_requested(user_request):
        return None
    packet_operations = packet_operations_from_natural_request(payload, user_request)
    if not packet_operations:
        raise ControllerServiceError(
            "Disposable-copy apply requires exact packet_operations JSON in the message.",
            code="missing_packet_operations",
        )
    target_root = target_root_from_natural_request(user_request, payload)
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": (
            "Apply approved exact packet operations to a disposable copy only. "
            "Do not mutate the source target repository."
        ),
        "mode": "apply_disposable_copy",
        "approval": {
            "status": "approved_for_disposable_apply",
            "scope": "natural_workflow_router_disposable_copy_only",
            "apply_allowed": True,
            "apply_scope": "disposable_copy_only",
            "approval_refs": ["natural_disposable_copy_apply"],
        },
        "packet_operations": packet_operations,
        "budgets": {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        "feedback": {
            "tester_feedback": bounded_string(user_request, 1000),
        },
    }
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def natural_workflow_router_payload(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    user_request = latest_user_message_text(payload)
    skill_selection_explain_payload = natural_skill_selection_explain_payload(payload, user_request, config)
    if skill_selection_explain_payload is not None:
        return skill_selection_explain_payload
    lifecycle_operation_payload = natural_lifecycle_operation_payload(payload, user_request, config)
    if lifecycle_operation_payload is not None:
        return lifecycle_operation_payload
    skill_lifecycle_audit_payload = natural_skill_lifecycle_audit_payload(payload, user_request, config)
    if skill_lifecycle_audit_payload is not None:
        return skill_lifecycle_audit_payload
    skill_batch_registration_payload = natural_skill_batch_registration_payload(payload, user_request, config)
    if skill_batch_registration_payload is not None:
        return skill_batch_registration_payload
    block_denied_natural_approval(user_request, config)
    approved_investigation_packet_prep_payload = natural_approved_investigation_packet_prep_payload(
        payload,
        user_request,
        config,
    )
    if approved_investigation_packet_prep_payload is not None:
        return approved_investigation_packet_prep_payload
    narrowed_objective_payload = natural_narrowed_edit_objective_payload(payload, user_request, config)
    if narrowed_objective_payload is not None:
        return narrowed_objective_payload
    packet_objective_payload = natural_packet_objective_payload(payload, user_request, config)
    if packet_objective_payload is not None:
        return packet_objective_payload
    disposable_apply_payload = natural_disposable_copy_apply_payload(payload, user_request, config)
    if disposable_apply_payload is not None:
        return disposable_apply_payload
    simple_test_fix_payload = natural_simple_test_fix_payload(payload, user_request, config)
    if simple_test_fix_payload is not None:
        return simple_test_fix_payload
    small_unit_test_payload = natural_small_unit_test_payload(payload, user_request, config)
    if small_unit_test_payload is not None:
        return small_unit_test_payload
    small_text_edit_payload = natural_small_text_edit_payload(payload, user_request, config)
    if small_text_edit_payload is not None:
        return small_text_edit_payload
    feedback_payload = natural_workflow_feedback_payload(payload, user_request, config)
    if feedback_payload is not None:
        return feedback_payload
    approval_payload = natural_approval_continuation_payload(payload, user_request, config)
    if approval_payload is not None:
        return approval_payload
    target_root = target_root_from_natural_request(user_request, payload)
    budgets = payload.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {
            "max_model_calls": 3,
            "max_selected_skills": 5,
            "max_selected_tools": 5,
        }
    request: dict[str, Any] = {
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "schema_version": 1,
        "target_root": target_root,
        "user_request": user_request,
        "mode": infer_workflow_router_mode(user_request),
        "budgets": budgets,
    }
    if isinstance(payload.get("context"), dict):
        request["context"] = payload["context"]
    role_base_url = payload.get("role_base_url")
    if isinstance(role_base_url, str) and role_base_url.strip():
        request["role_base_url"] = role_base_url
    return request


def is_general_chat_without_target(user_request: str, payload: dict[str, Any]) -> bool:
    return no_target_guidance_kind(user_request, payload) == "general_chat_no_target"


def no_target_guidance_summary(kind: str) -> dict[str, Any]:
    if kind == "general_chat_no_target":
        return {
            "route_status": "general_chat_no_target",
            "selected_workflow": "none",
            "answer": "Hi. For coding workflow help, include an allowed target_root path and the task you want planned or investigated.",
            "next_action": (
                "Example: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what a function does. "
                "For ordinary model chat, use the non-router model endpoint instead of the workflow-router gateway."
            ),
            "missing_information": ["allowed target_root path", "concrete coding task"],
            "bounded_next_step": (
                "Send one coding prompt with a repository path and the behavior, file, symbol, error, or test to inspect."
            ),
            "safe_alternatives": ["use the non-router model endpoint for ordinary chat"],
            "evidence_expectations": ["repository path", "specific coding target"],
            "mutation_policy": "no repository workflow or source mutation started",
            "refusal_quality_status": "actionable",
            "source_changed": False,
            "source_tree_changed": False,
        }
    if kind == "general_help_no_target":
        return {
            "route_status": "general_help_no_target",
            "selected_workflow": "none",
            "answer": (
                "I can help with local coding workflows when you include an allowed target_root path and a concrete task. "
                "I can inspect code, explain functions or files, find related tests, summarize failures, locate config, "
                "plan small changes, and prepare approval-gated implementation packets."
            ),
            "next_action": (
                "Send a prompt like: In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
                "find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only."
            ),
            "missing_information": ["allowed target_root path", "concrete coding task"],
            "bounded_next_step": (
                "Pick one supported task, such as code explanation, related-test lookup, failure summary, "
                "configuration lookup, or a small approval-gated change plan."
            ),
            "safe_alternatives": ["ask for supported workflow examples", "use the non-router model endpoint for ordinary chat"],
            "evidence_expectations": ["repository path", "specific file, symbol, behavior, error, or test"],
            "mutation_policy": "no repository workflow or source mutation started",
            "refusal_quality_status": "actionable",
            "source_changed": False,
            "source_tree_changed": False,
        }
    if kind == "blocked_missing_target_and_approval":
        return {
            "route_status": "blocked_missing_target_and_approval",
            "selected_workflow": "none",
            "answer": (
                "I cannot change files or bypass approval from this prompt. I did not start a repository workflow."
            ),
            "next_action": (
                "Provide an allowed target_root path, a concrete change request, and use approval-gated planning. "
                "I can start with read-only inspection."
            ),
            "blocker_reasons": ["missing_target_root", "blocked_approval_bypass"],
            "missing_information": [
                "allowed target_root path",
                "concrete change request",
                "approval-gated planning scope",
            ],
            "bounded_next_step": (
                "Start with read-only inspection or a draft plan, then request approval after the plan is reviewable."
            ),
            "safe_alternatives": [
                "read-only investigation",
                "draft-only implementation packet",
                "disposable-copy apply after explicit approval",
            ],
            "evidence_expectations": ["target files or behavior", "acceptance criteria", "verification command or test"],
            "mutation_policy": "source mutation and approval bypass are blocked",
            "refusal_quality_status": "actionable",
            "source_changed": False,
            "source_tree_changed": False,
        }
    return {
        "route_status": "missing_target_root_for_coding_request",
        "selected_workflow": "none",
        "answer": (
            "I need an allowed target_root path before I can inspect code. I did not start a repository workflow."
        ),
        "next_action": (
            "Include the repository path and the specific behavior, file, symbol, error, or test you want investigated."
        ),
        "blocker_reasons": ["missing_target_root"],
        "missing_information": [
            "allowed target_root path",
            "specific behavior, file, symbol, error, or test to investigate",
        ],
        "bounded_next_step": (
            "Resend the request with an allowed repository path and one concrete coding target."
        ),
        "safe_alternatives": ["start with read-only investigation", "ask for supported prompt examples"],
        "evidence_expectations": ["repository path", "expected behavior or failing command when debugging"],
        "mutation_policy": "no repository workflow or source mutation started",
        "refusal_quality_status": "actionable",
        "source_changed": False,
        "source_tree_changed": False,
    }


def general_workflow_router_chat_response(
    user_request: str,
    config: ControllerServiceConfig,
    *,
    kind: str = "general_chat_no_target",
) -> dict[str, Any]:
    run_id = f"workflow-router-general-{natural_artifact_timestamp()}"
    response = {
        "run_id": run_id,
        "workflow": WORKFLOW_ROUTER_WORKFLOW_ID,
        "status": "completed",
        "artifacts": {},
        "summary": no_target_guidance_summary(kind),
        "warnings": [],
        "failures": [],
        "resume_key": None,
    }
    persist_run_record(config, response)
    return response


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
        parallelism=int_with_default(merged, "parallelism", 1),
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


def build_execution_planning(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltExecutionPlanning:
    unknown = sorted(set(payload) - EXECUTION_PLANNING_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", EXECUTION_PLANNING_WORKFLOW_ID)
    if workflow != EXECUTION_PLANNING_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be execution_planning.plan.", code="unsupported_workflow")

    budgets = require_object(payload.get("budgets", {}), "budgets")
    unknown_budgets = sorted(set(budgets) - EXECUTION_PLANNING_BUDGET_FIELDS)
    if unknown_budgets:
        raise ControllerServiceError(f"Unsupported budget field(s): {', '.join(unknown_budgets)}")

    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    mode = optional_string(payload, "mode") or "investigation_only"
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            EXECUTION_PLANNING_WORKFLOW_ID,
            role_id,
            {"mode": mode},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc

    request = ExecutionPlanningInvocationRequest.from_payload(
        payload,
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.output_root,
        role_base_url=optional_string(payload, "role_base_url") or config.default_role_base_url,
    )
    return BuiltExecutionPlanning(request=request, tool_policy=tool_policy)


def build_code_context_lookup(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltCodeContextLookup:
    unknown = sorted(set(payload) - CODE_CONTEXT_LOOKUP_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", CODE_CONTEXT_LOOKUP_WORKFLOW_ID)
    if workflow != CODE_CONTEXT_LOOKUP_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be code_context.lookup.", code="unsupported_workflow")
    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            CODE_CONTEXT_LOOKUP_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = CodeContextLookupRequest.from_payload(
        payload,
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.output_root,
    )
    return BuiltCodeContextLookup(request=request, tool_policy=tool_policy)


def build_code_investigation(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltCodeInvestigation:
    unknown = sorted(set(payload) - CODE_INVESTIGATION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", CODE_INVESTIGATION_WORKFLOW_ID)
    if workflow != CODE_INVESTIGATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be code_investigation.plan.", code="unsupported_workflow")
    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            CODE_INVESTIGATION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = CodeInvestigationRequest.from_payload(
        payload,
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.output_root,
    )
    return BuiltCodeInvestigation(request=request, tool_policy=tool_policy)


def build_refactor_single_path(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltRefactorSinglePath:
    unknown = sorted(set(payload) - REFACTOR_SINGLE_PATH_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", REFACTOR_SINGLE_PATH_WORKFLOW_ID)
    if workflow != REFACTOR_SINGLE_PATH_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be refactor.single_path.", code="unsupported_workflow")
    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    role_id = optional_string(payload, "role_id") or "architect/default"
    mode = optional_string(payload, "mode") or "investigation_only"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            REFACTOR_SINGLE_PATH_WORKFLOW_ID,
            role_id,
            {"mode": mode},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = RefactorSinglePathRequest.from_payload(
        payload,
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.output_root,
        role_base_url=optional_string(payload, "role_base_url") or config.default_role_base_url,
    )
    return BuiltRefactorSinglePath(request=request, tool_policy=tool_policy)


def build_workflow_feedback(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltWorkflowFeedback:
    unknown = sorted(set(payload) - WORKFLOW_FEEDBACK_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", WORKFLOW_FEEDBACK_WORKFLOW_ID)
    if workflow != WORKFLOW_FEEDBACK_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be workflow_feedback.record.", code="unsupported_workflow")
    target_root: Path | None = None
    target_root_value = optional_string(payload, "target_root")
    if target_root_value:
        target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            WORKFLOW_FEEDBACK_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = WorkflowFeedbackRecordRequest.from_payload(
        payload,
        output_root=config.output_root,
        run_registry_root=config.run_registry_root,
        target_root=target_root,
    )
    return BuiltWorkflowFeedback(request=request, tool_policy=tool_policy)


def build_skill_batch_proposal(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillBatchProposal:
    unknown = sorted(set(payload) - SKILL_BATCH_PROPOSAL_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_BATCH_PROPOSAL_WORKFLOW_ID)
    if workflow != SKILL_BATCH_PROPOSAL_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill_batch.propose.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_BATCH_PROPOSAL_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillBatchProposalRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillBatchProposal(request=request, tool_policy=tool_policy)


def build_skill_batch_registration(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillBatchRegistration:
    unknown = sorted(set(payload) - SKILL_BATCH_REGISTRATION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_BATCH_REGISTRATION_WORKFLOW_ID)
    if workflow != SKILL_BATCH_REGISTRATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill_batch.register.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_BATCH_REGISTRATION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillBatchRegistrationRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillBatchRegistration(request=request, tool_policy=tool_policy)


def build_skill_eval_promotion(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillEvalPromotion:
    unknown = sorted(set(payload) - SKILL_EVAL_PROMOTION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_EVAL_PROMOTION_WORKFLOW_ID)
    if workflow != SKILL_EVAL_PROMOTION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill_eval.promote.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_EVAL_PROMOTION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillEvalPromotionRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillEvalPromotion(request=request, tool_policy=tool_policy)


def build_skill_lifecycle_audit(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillLifecycleAudit:
    unknown = sorted(set(payload) - SKILL_LIFECYCLE_AUDIT_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID)
    if workflow != SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill_lifecycle.audit.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillLifecycleAuditRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillLifecycleAudit(request=request, tool_policy=tool_policy)


def build_skill_deprecation(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillDeprecation:
    unknown = sorted(set(payload) - SKILL_DEPRECATION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_DEPRECATION_WORKFLOW_ID)
    if workflow != SKILL_DEPRECATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill.deprecate.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_DEPRECATION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillDeprecationRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillDeprecation(request=request, tool_policy=tool_policy)


def build_skill_update(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillUpdate:
    unknown = sorted(set(payload) - SKILL_UPDATE_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_UPDATE_WORKFLOW_ID)
    if workflow != SKILL_UPDATE_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill.update.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_UPDATE_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillUpdateRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillUpdate(request=request, tool_policy=tool_policy)


def build_skill_selection_explain(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillSelectionExplain:
    unknown = sorted(set(payload) - SKILL_SELECTION_EXPLAIN_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_SELECTION_EXPLAIN_WORKFLOW_ID)
    if workflow != SKILL_SELECTION_EXPLAIN_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill.selection.explain.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_SELECTION_EXPLAIN_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillSelectionExplainRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillSelectionExplain(request=request, tool_policy=tool_policy)


def build_skill_pack_validation(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillPackValidation:
    unknown = sorted(set(payload) - SKILL_PACK_VALIDATION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_PACK_VALIDATION_WORKFLOW_ID)
    if workflow != SKILL_PACK_VALIDATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill_pack.validate.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_PACK_VALIDATION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillPackValidationRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillPackValidation(request=request, tool_policy=tool_policy)


def build_skill_pack_install(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillPackInstall:
    unknown = sorted(set(payload) - SKILL_PACK_INSTALL_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_PACK_INSTALL_WORKFLOW_ID)
    if workflow != SKILL_PACK_INSTALL_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill_pack.install.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_PACK_INSTALL_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillPackInstallRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillPackInstall(request=request, tool_policy=tool_policy)


def build_skill_scaffold(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltSkillScaffold:
    unknown = sorted(set(payload) - SKILL_SCAFFOLD_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", SKILL_SCAFFOLD_WORKFLOW_ID)
    if workflow != SKILL_SCAFFOLD_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be skill.scaffold.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            SKILL_SCAFFOLD_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = SkillScaffoldRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltSkillScaffold(request=request, tool_policy=tool_policy)


def build_tool_catalog_validation(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltToolCatalogValidation:
    unknown = sorted(set(payload) - TOOL_CATALOG_VALIDATION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", TOOL_CATALOG_VALIDATION_WORKFLOW_ID)
    if workflow != TOOL_CATALOG_VALIDATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be tool_catalog.validate.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            TOOL_CATALOG_VALIDATION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = ToolCatalogValidationRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltToolCatalogValidation(request=request, tool_policy=tool_policy)


def build_tool_catalog_registration(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltToolCatalogRegistration:
    unknown = sorted(set(payload) - TOOL_CATALOG_REGISTRATION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", TOOL_CATALOG_REGISTRATION_WORKFLOW_ID)
    if workflow != TOOL_CATALOG_REGISTRATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be tool_catalog.register.", code="unsupported_workflow")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            TOOL_CATALOG_REGISTRATION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = ToolCatalogRegistrationRequest.from_payload(
        payload,
        config_root=config.config_root,
        output_root=config.output_root,
    )
    return BuiltToolCatalogRegistration(request=request, tool_policy=tool_policy)


def build_task_decomposition(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltTaskDecomposition:
    unknown = sorted(set(payload) - TASK_DECOMPOSITION_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", TASK_DECOMPOSITION_WORKFLOW_ID)
    if workflow != TASK_DECOMPOSITION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be task.decompose.", code="unsupported_workflow")
    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    role_id = optional_string(payload, "role_id") or "architect/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            TASK_DECOMPOSITION_WORKFLOW_ID,
            role_id,
            {},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = TaskDecompositionRequest.from_payload(
        payload,
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.output_root,
    )
    return BuiltTaskDecomposition(request=request, tool_policy=tool_policy)


def normalize_implementation_mode(value: Any) -> str:
    if value is None:
        return "draft"
    if not isinstance(value, str):
        raise ControllerServiceError("mode must be a string.")
    normalized = re.sub(r"[\s-]+", "_", value.strip().lower())
    aliases = {
        "draft": "draft",
        "dry_run": "draft",
        "dryrun": "draft",
        "preview": "draft",
        "apply": "apply",
        "real_apply": "apply",
        "real": "apply",
    }
    mode = aliases.get(normalized)
    if mode is None:
        raise ControllerServiceError("mode must be draft, dry_run, apply, or real_apply.")
    return mode


def protected_frozen_target(target_root: Path) -> bool:
    protected_names = {
        "coinbase_testing_repo_frozen_tmp",
        "coinbase_testing_repo_frozen_tmp.github",
    }
    return target_root.resolve().name in protected_names


def implementation_approval_blockers(
    *,
    mode: str,
    approval: Any,
    target_root: Path,
) -> list[dict[str, str]]:
    if not isinstance(approval, dict):
        return [{"reason": "missing_implementation_approval", "message": "approval must be a JSON object."}]
    blockers: list[dict[str, str]] = []
    if mode == "draft":
        allowed_statuses = {
            "approved_for_packet_design",
            "approved_for_small_change_dry_run",
            "approved_for_dry_run",
        }
        if approval.get("status") not in allowed_statuses:
            blockers.append(
                {
                    "reason": "draft_approval_required",
                    "message": "draft mode requires approval.status approved for packet design or dry-run.",
                }
            )
        if approval.get("apply_allowed") is True:
            blockers.append(
                {
                    "reason": "draft_apply_not_allowed",
                    "message": "draft mode requires approval.apply_allowed to be false or omitted.",
                }
            )
    else:
        if approval.get("status") != "approved_for_real_apply":
            blockers.append(
                {
                    "reason": "real_apply_approval_required",
                    "message": "apply mode requires approval.status=approved_for_real_apply.",
                }
            )
        if approval.get("apply_allowed") is not True:
            blockers.append(
                {
                    "reason": "real_apply_allowed_required",
                    "message": "apply mode requires approval.apply_allowed=true.",
                }
            )
        if approval.get("apply_scope") != "target_root":
            blockers.append(
                {
                    "reason": "real_apply_scope_required",
                    "message": "apply mode requires approval.apply_scope=target_root.",
                }
            )
        if approval.get("explicit_real_apply") is not True:
            blockers.append(
                {
                    "reason": "explicit_real_apply_required",
                    "message": "apply mode requires approval.explicit_real_apply=true.",
                }
            )
        if protected_frozen_target(target_root):
            blockers.append(
                {
                    "reason": "protected_frozen_real_apply_denied",
                    "message": "real apply is blocked for protected frozen fixture roots; use a disposable copy.",
                }
            )
    return blockers


def implementation_verification_commands(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_commands = payload.get("verification_commands", [])
    if not isinstance(raw_commands, list) or not all(isinstance(item, dict) for item in raw_commands):
        raise ControllerServiceError("verification_commands must be a list of objects.")
    return [dict(item) for item in raw_commands]


def implementation_packet_operations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_operations = payload.get("packet_operations")
    if raw_operations is None:
        return []
    if not isinstance(raw_operations, list) or not all(isinstance(item, dict) for item in raw_operations):
        raise ControllerServiceError("packet_operations must be a list of objects.")
    return [dict(item) for item in raw_operations]


def implementation_packet_file_from_operations(
    *,
    config: ControllerServiceConfig,
    packet_operations: list[dict[str, Any]],
    verification_commands: list[dict[str, Any]],
) -> Path:
    run_dir = config.output_root / "implementation-controller-packets" / controller_run_id()
    run_dir.mkdir(parents=True, exist_ok=True)
    packets: list[dict[str, Any]] = []
    for index, operation in enumerate(packet_operations, 1):
        path = operation.get("path")
        kind = operation.get("kind")
        packets.append(
            {
                "id": f"CONTROLLED-IMPLEMENTATION-{index:04d}",
                "task": "apply_approved_small_change_packet_operation",
                "target_files": [path] if isinstance(path, str) else [],
                "allowed_operations": [kind] if isinstance(kind, str) else [],
                "operation": operation,
                "source_refs": [{"path": path}] if isinstance(path, str) else [],
                "acceptance_criteria": ["Approved packet operation applies only to the declared target file."],
                "max_context_tokens": 2000,
            }
        )
    packet_file = run_dir / "packet-operations.json"
    packet_file.write_bytes(
        json_bytes(
            {
                "schema_version": 1,
                "packets": packets,
                "verification_commands": verification_commands,
            }
        )
    )
    return require_under_output_root(packet_file, config.output_root, "packet_file")


def implementation_source_path(payload: dict[str, Any], key: str, config: ControllerServiceConfig) -> Path | None:
    value = optional_string(payload, key)
    if not value:
        return None
    return require_under_output_root(resolve_path(value), config.output_root, key)


def build_implementation_workflow(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltImplementationWorkflow:
    unknown = sorted(set(payload) - IMPLEMENTATION_WORKFLOW_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", IMPLEMENTATION_WORKFLOW_ID)
    if workflow != IMPLEMENTATION_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be implementation.workflow.", code="unsupported_workflow")
    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    mode = normalize_implementation_mode(payload.get("mode"))
    blockers = implementation_approval_blockers(
        mode=mode,
        approval=payload.get("approval"),
        target_root=target_root,
    )
    if blockers:
        raise ControllerServiceError(
            blockers[0]["message"],
            status=HTTPStatus.FORBIDDEN,
            code=blockers[0]["reason"],
        )
    role_id = optional_string(payload, "role_id") or "implementer/default"
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            IMPLEMENTATION_WORKFLOW_ID,
            role_id,
            {"mode": mode},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc

    verification_commands = implementation_verification_commands(payload)
    packet_operations = implementation_packet_operations(payload)
    packet_file = implementation_source_path(payload, "packet_file", config)
    from_report = implementation_source_path(payload, "from_report", config)
    resume = implementation_source_path(payload, "resume", config)
    source_count = sum(
        1
        for value in (
            bool(packet_operations),
            packet_file is not None,
            from_report is not None,
            resume is not None,
        )
        if value
    )
    if source_count != 1:
        raise ControllerServiceError(
            "Provide exactly one of packet_operations, packet_file, from_report, or resume.",
            code="invalid_implementation_source",
        )
    if packet_operations:
        packet_file = implementation_packet_file_from_operations(
            config=config,
            packet_operations=packet_operations,
            verification_commands=verification_commands,
        )
        verification_commands = []
    request = ImplementationWorkflowInvocationRequest(
        target_root=target_root,
        output_dir=config.output_root / "implementation-workflow",
        mode=mode,
        packet_file=packet_file,
        from_report=from_report,
        verification_commands=verification_commands,
        verification_timeout_seconds=int_with_default(payload, "verification_timeout_seconds", 120),
        max_context_tokens=int_with_default(payload, "max_context_tokens", 4000),
        structure_slice_records=int_with_default(payload, "structure_slice_records", 40),
        structure_max_file_bytes=int_with_default(payload, "structure_max_file_bytes", 64 * 1024),
        no_structure_index=optional_bool(payload, "no_structure_index", False),
        resume=resume,
        resume_allow_arg_changes=optional_bool(payload, "resume_allow_arg_changes", False),
    )
    return BuiltImplementationWorkflow(request=request, tool_policy=tool_policy)


def build_workflow_router_plan(payload: dict[str, Any], config: ControllerServiceConfig) -> BuiltWorkflowRouterPlan:
    unknown = sorted(set(payload) - WORKFLOW_ROUTER_FIELDS)
    if unknown:
        raise ControllerServiceError(f"Unsupported request field(s): {', '.join(unknown)}")
    workflow = payload.get("workflow", WORKFLOW_ROUTER_WORKFLOW_ID)
    if workflow != WORKFLOW_ROUTER_WORKFLOW_ID:
        raise ControllerServiceError("workflow must be workflow_router.plan.", code="unsupported_workflow")
    target_root_value = optional_string(payload, "target_root")
    if not target_root_value:
        raise ControllerServiceError("target_root is required.")
    target_root = require_under_any(resolve_path(target_root_value), config.allowed_target_roots, "target_root")
    mode = optional_string(payload, "mode") or "plan_only"
    role_id = optional_string(payload, "role_id") or WORKFLOW_ROUTER_DEFAULT_ROLE_ID
    try:
        tool_policy = resolve_controller_tool_policy(
            config.config_root,
            WORKFLOW_ROUTER_WORKFLOW_ID,
            role_id,
            {"mode": mode},
            [],
        )
    except ControllerToolPolicyError as exc:
        raise ControllerServiceError(
            str(exc),
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="tool_policy_denied",
        ) from exc
    request = WorkflowRouterPlanRequest.from_payload(
        payload,
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.output_root,
        role_base_url=optional_string(payload, "role_base_url") or config.default_role_base_url,
    )
    return BuiltWorkflowRouterPlan(request=request, tool_policy=tool_policy)


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


def handle_execution_planning(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_execution_planning(payload, config)
    result = invoke_execution_planning(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_code_context_lookup(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_code_context_lookup(payload, config)
    result = invoke_code_context_lookup(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_code_investigation(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_code_investigation(payload, config)
    result = invoke_code_investigation(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_refactor_single_path(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_refactor_single_path(payload, config)
    result = invoke_refactor_single_path(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_workflow_feedback(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_workflow_feedback(payload, config)
    result = invoke_workflow_feedback_record(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_batch_proposal(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_batch_proposal(payload, config)
    result = invoke_skill_batch_proposal(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_batch_registration(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_batch_registration(payload, config)
    result = invoke_skill_batch_registration(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_eval_promotion(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_eval_promotion(payload, config)
    result = invoke_skill_eval_promotion(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_lifecycle_audit(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_lifecycle_audit(payload, config)
    result = invoke_skill_lifecycle_audit(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_deprecation(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_deprecation(payload, config)
    result = invoke_skill_deprecation(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_update(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_update(payload, config)
    result = invoke_skill_update(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_selection_explain(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_selection_explain(payload, config)
    result = invoke_skill_selection_explain(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_pack_validation(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_pack_validation(payload, config)
    result = invoke_skill_pack_validation(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_pack_install(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_pack_install(payload, config)
    result = invoke_skill_pack_install(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_skill_scaffold(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_skill_scaffold(payload, config)
    result = invoke_skill_scaffold(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_tool_catalog_validation(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_tool_catalog_validation(payload, config)
    result = invoke_tool_catalog_validation(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_tool_catalog_registration(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_tool_catalog_registration(payload, config)
    result = invoke_tool_catalog_registration(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_task_decomposition(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_task_decomposition(payload, config)
    result = invoke_task_decomposition(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_implementation_workflow(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_implementation_workflow(payload, config)
    result = invoke_implementation_workflow(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def handle_workflow_router_plan(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    built = build_workflow_router_plan(payload, config)
    result = invoke_workflow_router_plan(built.request)
    response = service_response_from_result(result, built.tool_policy)
    persist_run_record(config, response)
    return response


def write_natural_route_artifacts(
    *,
    response: dict[str, Any],
    controller_request: dict[str, Any],
    user_request: str,
    config: ControllerServiceConfig,
) -> dict[str, Any]:
    run_id = response.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        return response
    artifacts = response.get("artifacts") if isinstance(response.get("artifacts"), dict) else {}
    run_dir = config.output_root / NATURAL_ROUTE_DECISION_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    workflow = response.get("workflow") if isinstance(response.get("workflow"), str) else controller_request.get("workflow")
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    artifacts = {**artifacts}
    if "route_decision" not in artifacts:
        route_decision = {
            "kind": "natural_lifecycle_route_decision",
            "schema_version": 1,
            "run_id": run_id,
            "selected_workflow": workflow,
            "response_status": response.get("status"),
            "route_status": summary.get("route_status") or response.get("status"),
            "approval_present": isinstance(controller_request.get("approval"), dict),
            "approval_required": response.get("status") == "approval_required",
            "source_message": bounded_string(user_request, 4000),
            "controller_request": {
                key: value
                for key, value in controller_request.items()
                if key not in {"approval", "skill_body_text"}
            },
            "created_at": utc_now(),
        }
        route_path = run_dir / "route-decision.json"
        route_path.write_bytes(json_bytes(route_decision))
        artifacts["route_decision"] = str(route_path)
    approval = controller_request.get("approval")
    if isinstance(approval, dict):
        approval_proof = {
            "kind": "natural_lifecycle_approval_proof",
            "schema_version": 1,
            "run_id": run_id,
            "workflow": workflow,
            "approval": approval,
            "source_message": bounded_string(user_request, 1000),
            "created_at": utc_now(),
        }
        approval_path = run_dir / "approval-proof.json"
        approval_path.write_bytes(json_bytes(approval_proof))
        artifacts["approval_proof"] = str(approval_path)
    response["artifacts"] = artifacts
    persist_run_record(config, response)
    return response


def handle_harness_chat_completion(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    controller_request = extract_harness_controller_request(payload)
    workflow = controller_request.get("workflow")
    if workflow == "documenter.review":
        response = handle_documenter_review(controller_request, config)
    elif workflow == EXECUTION_PLANNING_WORKFLOW_ID:
        response = handle_execution_planning(controller_request, config)
    elif workflow == CODE_CONTEXT_LOOKUP_WORKFLOW_ID:
        response = handle_code_context_lookup(controller_request, config)
    elif workflow == CODE_INVESTIGATION_WORKFLOW_ID:
        response = handle_code_investigation(controller_request, config)
    elif workflow == REFACTOR_SINGLE_PATH_WORKFLOW_ID:
        response = handle_refactor_single_path(controller_request, config)
    elif workflow == WORKFLOW_FEEDBACK_WORKFLOW_ID:
        response = handle_workflow_feedback(controller_request, config)
    elif workflow == SKILL_BATCH_PROPOSAL_WORKFLOW_ID:
        response = handle_skill_batch_proposal(controller_request, config)
    elif workflow == SKILL_BATCH_REGISTRATION_WORKFLOW_ID:
        response = handle_skill_batch_registration(controller_request, config)
    elif workflow == SKILL_EVAL_PROMOTION_WORKFLOW_ID:
        response = handle_skill_eval_promotion(controller_request, config)
    elif workflow == SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID:
        response = handle_skill_lifecycle_audit(controller_request, config)
    elif workflow == SKILL_DEPRECATION_WORKFLOW_ID:
        response = handle_skill_deprecation(controller_request, config)
    elif workflow == SKILL_UPDATE_WORKFLOW_ID:
        response = handle_skill_update(controller_request, config)
    elif workflow == SKILL_SELECTION_EXPLAIN_WORKFLOW_ID:
        response = handle_skill_selection_explain(controller_request, config)
    elif workflow == SKILL_PACK_VALIDATION_WORKFLOW_ID:
        response = handle_skill_pack_validation(controller_request, config)
    elif workflow == SKILL_PACK_INSTALL_WORKFLOW_ID:
        response = handle_skill_pack_install(controller_request, config)
    elif workflow == SKILL_SCAFFOLD_WORKFLOW_ID:
        response = handle_skill_scaffold(controller_request, config)
    elif workflow == IMPLEMENTATION_WORKFLOW_ID:
        response = handle_implementation_workflow(controller_request, config)
    elif workflow == WORKFLOW_ROUTER_WORKFLOW_ID:
        response = handle_workflow_router_plan(controller_request, config)
    else:
        raise ControllerServiceError(
            "Harness adapter supports workflow=documenter.review, workflow=execution_planning.plan, "
            "workflow=code_context.lookup, workflow=code_investigation.plan, workflow=refactor.single_path, "
            "workflow=workflow_feedback.record, workflow=skill_batch.propose, workflow=skill_batch.register, "
            "workflow=skill_eval.promote, workflow=skill_lifecycle.audit, workflow=skill.deprecate, "
            "workflow=skill.update, workflow=skill.selection.explain, workflow=skill_pack.validate, "
            "workflow=skill_pack.install, workflow=skill.scaffold, workflow=implementation.workflow, "
            "or workflow=workflow_router.plan.",
            code="unsupported_workflow",
        )
    return chat_completion_response(payload, response)


def handle_workflow_router_chat_completion(payload: dict[str, Any], config: ControllerServiceConfig) -> dict[str, Any]:
    user_request = latest_user_message_text(payload)
    guidance_kind = no_target_guidance_kind(user_request, payload)
    if guidance_kind is not None:
        return chat_completion_response(
            payload,
            general_workflow_router_chat_response(user_request, config, kind=guidance_kind),
        )
    controller_request = natural_workflow_router_payload(payload, config)
    workflow = controller_request.get("workflow")
    if workflow == NATURAL_LIFECYCLE_APPROVAL_REQUIRED_WORKFLOW:
        response = controller_request["response"]
        response = write_natural_route_artifacts(
            response=response,
            controller_request=controller_request.get("proposed_request", {}),
            user_request=user_request,
            config=config,
        )
    elif workflow == WORKFLOW_FEEDBACK_WORKFLOW_ID:
        response = handle_workflow_feedback(controller_request, config)
    elif workflow == SKILL_BATCH_REGISTRATION_WORKFLOW_ID:
        response = handle_skill_batch_registration(controller_request, config)
    elif workflow == SKILL_LIFECYCLE_AUDIT_WORKFLOW_ID:
        response = handle_skill_lifecycle_audit(controller_request, config)
    elif workflow == SKILL_DEPRECATION_WORKFLOW_ID:
        response = handle_skill_deprecation(controller_request, config)
    elif workflow == SKILL_UPDATE_WORKFLOW_ID:
        response = handle_skill_update(controller_request, config)
    elif workflow == SKILL_SELECTION_EXPLAIN_WORKFLOW_ID:
        response = handle_skill_selection_explain(controller_request, config)
    elif workflow == SKILL_PACK_VALIDATION_WORKFLOW_ID:
        response = handle_skill_pack_validation(controller_request, config)
    elif workflow == SKILL_PACK_INSTALL_WORKFLOW_ID:
        response = handle_skill_pack_install(controller_request, config)
    elif workflow == SKILL_SCAFFOLD_WORKFLOW_ID:
        response = handle_skill_scaffold(controller_request, config)
    elif workflow == WORKFLOW_ROUTER_WORKFLOW_ID:
        response = handle_workflow_router_plan(controller_request, config)
        request_context = controller_request.get("context") if isinstance(controller_request.get("context"), dict) else {}
        source_run_id = request_context.get("approval_continuation_source_run_id")
        if isinstance(source_run_id, str) and source_run_id.strip():
            continuation_run_id = response.get("run_id") if isinstance(response.get("run_id"), str) else None
            mark_approval_continuation_consumed(config, source_run_id, continuation_run_id)
    else:
        raise ControllerServiceError(
            "Workflow-router chat produced an unsupported controller workflow.",
            code="unsupported_workflow",
        )
    if workflow != NATURAL_LIFECYCLE_APPROVAL_REQUIRED_WORKFLOW:
        response = write_natural_route_artifacts(
            response=response,
            controller_request=controller_request,
            user_request=user_request,
            config=config,
        )
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
        with RUN_RECORD_CACHE_LOCK:
            RUN_RECORD_CACHE.pop((str(config.run_registry_root.resolve()), run_id), None)
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
            if self.path == EXECUTION_PLANNING_PATH:
                self.write_json(HTTPStatus.OK, handle_execution_planning(payload, self.server.config))
                return
            if self.path == CODE_CONTEXT_LOOKUP_PATH:
                self.write_json(HTTPStatus.OK, handle_code_context_lookup(payload, self.server.config))
                return
            if self.path == CODE_INVESTIGATION_PATH:
                self.write_json(HTTPStatus.OK, handle_code_investigation(payload, self.server.config))
                return
            if self.path == REFACTOR_SINGLE_PATH:
                self.write_json(HTTPStatus.OK, handle_refactor_single_path(payload, self.server.config))
                return
            if self.path == WORKFLOW_FEEDBACK_PATH:
                self.write_json(HTTPStatus.OK, handle_workflow_feedback(payload, self.server.config))
                return
            if self.path == SKILL_BATCH_PROPOSAL_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_batch_proposal(payload, self.server.config))
                return
            if self.path == SKILL_BATCH_REGISTRATION_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_batch_registration(payload, self.server.config))
                return
            if self.path == SKILL_EVAL_PROMOTION_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_eval_promotion(payload, self.server.config))
                return
            if self.path == SKILL_LIFECYCLE_AUDIT_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_lifecycle_audit(payload, self.server.config))
                return
            if self.path == SKILL_DEPRECATION_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_deprecation(payload, self.server.config))
                return
            if self.path == SKILL_UPDATE_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_update(payload, self.server.config))
                return
            if self.path == SKILL_SELECTION_EXPLAIN_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_selection_explain(payload, self.server.config))
                return
            if self.path == SKILL_PACK_VALIDATION_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_pack_validation(payload, self.server.config))
                return
            if self.path == SKILL_PACK_INSTALL_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_pack_install(payload, self.server.config))
                return
            if self.path == SKILL_SCAFFOLD_PATH:
                self.write_json(HTTPStatus.OK, handle_skill_scaffold(payload, self.server.config))
                return
            if self.path == TOOL_CATALOG_VALIDATION_PATH:
                self.write_json(HTTPStatus.OK, handle_tool_catalog_validation(payload, self.server.config))
                return
            if self.path == TOOL_CATALOG_REGISTRATION_PATH:
                self.write_json(HTTPStatus.OK, handle_tool_catalog_registration(payload, self.server.config))
                return
            if self.path == TASK_DECOMPOSITION_PATH:
                self.write_json(HTTPStatus.OK, handle_task_decomposition(payload, self.server.config))
                return
            if self.path == IMPLEMENTATION_WORKFLOW_PATH:
                self.write_json(HTTPStatus.OK, handle_implementation_workflow(payload, self.server.config))
                return
            if self.path == WORKFLOW_ROUTER_PLAN_PATH:
                self.write_json(HTTPStatus.OK, handle_workflow_router_plan(payload, self.server.config))
                return
            if self.path == HARNESS_CHAT_COMPLETIONS_PATH:
                self.write_json(HTTPStatus.OK, handle_harness_chat_completion(payload, self.server.config))
                return
            if self.path == WORKFLOW_ROUTER_CHAT_COMPLETIONS_PATH:
                response = handle_workflow_router_chat_completion(payload, self.server.config)
                if payload.get("stream") is True:
                    self.write_chat_completion_stream(response)
                else:
                    self.write_json(HTTPStatus.OK, response)
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
        except ExecutionPlanningWorkflowError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except CodeContextLookupError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except CodeInvestigationError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except RefactorSinglePathError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except WorkflowFeedbackError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillBatchProposalError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillBatchRegistrationError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillEvalPromotionError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillLifecycleAuditError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillDeprecationError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillUpdateError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillSelectionExplainError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillPackValidationError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillPackInstallError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except SkillScaffoldError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except ToolCatalogValidationError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except ToolCatalogRegistrationError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except TaskDecompositionError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
        except ImplementationWorkflowError as exc:
            self.write_error(
                ControllerServiceError(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY, code="implementation_workflow_error")
            )
        except WorkflowRouterError as exc:
            self.write_error(ControllerServiceError(str(exc), status=exc.status, code=exc.code))
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
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()
        self.close_connection = True

    def write_chat_completion_stream(self, value: dict[str, Any]) -> None:
        lines: list[bytes] = []
        for event in chat_completion_stream_events(value):
            if isinstance(event, str):
                event_text = event
            else:
                event_text = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
            lines.append(f"data: {event_text}\n\n".encode("utf-8"))
        data = b"".join(lines)
        self.send_response(int(HTTPStatus.OK))
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        return


class ControllerHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

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
