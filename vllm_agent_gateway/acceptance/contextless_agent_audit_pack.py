"""Governed contextless-agent audit pack validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "contextless_agent_audit_pack_policy"
EXPECTED_SAMPLE_KIND = "contextless_agent_audit_pack_sample_reports"
EXPECTED_REPORT_KIND = "contextless_agent_audit_pack_validation_report"
EXPECTED_PHASE = 185
EXPECTED_BACKLOG_ID = "P0-BB-049"
DEFAULT_POLICY_PATH = Path("runtime") / "contextless_agent_audit_pack_policy.json"
DEFAULT_SAMPLE_REPORTS_PATH = Path("runtime") / "contextless_agent_audit_pack_sample_reports.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "contextless-agent-audit-pack"
    / "phase185"
    / "phase185-contextless-agent-audit-pack-report.json"
)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_STEP_IDS = [
    "prompt_intake",
    "blind_baseline",
    "local_stack_run",
    "comparison_scoring",
    "repair_recommendation",
    "rerun_and_holdouts",
    "closure_summary",
]
REQUIRED_TEMPLATE_IDS = {
    "ideal_answer_baseline",
    "local_answer_scoring",
    "repair_recommendation",
    "holdout_rerun_review",
}
REQUIRED_REPORT_FIELDS = {
    "report_id",
    "prompt_family",
    "prompt",
    "prompt_hash",
    "target_root",
    "blind_agent",
    "blind_baseline",
    "local_run",
    "comparison",
    "repair_decision",
    "closure",
}
REQUIRED_LOCAL_SURFACES = {
    "localhost_8000_model",
    "workflow_router_gateway",
    "anythingllm",
}
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}


class AuditPackStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ContextlessAgentAuditPackConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    sample_reports_path: Path = DEFAULT_SAMPLE_REPORTS_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
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


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(error("policy.schema_version", "must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(error("policy.kind", f"must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(error("policy.phase", "must be 185"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(error("policy.priority_backlog_id", f"must be {EXPECTED_BACKLOG_ID}"))
    version = policy.get("policy_version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append(error("policy.policy_version", "must use semantic version x.y.z"))
    purpose = str(policy.get("purpose") or "").lower()
    if "baseline before local" not in purpose:
        errors.append(error("policy.purpose", "must explicitly require baseline before local output"))
    if "not a substitute for live local-stack proof" not in purpose:
        errors.append(error("policy.purpose", "must state the pack is not a substitute for live local-stack proof"))

    context = dict_value(policy.get("context_policy"))
    expected_context = {
        "fresh_contextless_agent": True,
        "fork_context": False,
        "session_history_allowed": False,
        "local_model_output_visible_to_baseline_agent": False,
    }
    for key, expected in expected_context.items():
        if context.get(key) is not expected:
            errors.append(error(f"policy.context_policy.{key}", f"must be {expected!r}"))
    if not string_list(context.get("allowed_inputs")):
        errors.append(error("policy.context_policy.allowed_inputs", "must be a non-empty string list"))
    forbidden_inputs = {item.lower() for item in string_list(context.get("forbidden_inputs"))}
    if "local model output before baseline" not in forbidden_inputs:
        errors.append(
            error(
                "policy.context_policy.forbidden_inputs",
                "must forbid local model output before baseline collection",
            )
        )

    steps = object_list(policy.get("process_steps"))
    step_ids = [str(item.get("id")) for item in steps if isinstance(item.get("id"), str)]
    if step_ids != REQUIRED_STEP_IDS:
        errors.append(error("policy.process_steps", f"must be ordered exactly as {REQUIRED_STEP_IDS}"))
    for index, step in enumerate(steps):
        prefix = f"policy.process_steps[{index}]"
        if not isinstance(step.get("owner"), str) or not step["owner"].strip():
            errors.append(error(f"{prefix}.owner", "must be a non-empty string"))
        if not string_list(step.get("required_outputs")):
            errors.append(error(f"{prefix}.required_outputs", "must be a non-empty string list"))

    templates = object_list(policy.get("prompt_templates"))
    template_ids = {str(item.get("id")) for item in templates if isinstance(item.get("id"), str)}
    if template_ids != REQUIRED_TEMPLATE_IDS:
        errors.append(error("policy.prompt_templates", f"must contain exactly {sorted(REQUIRED_TEMPLATE_IDS)}"))
    for index, template in enumerate(templates):
        prefix = f"policy.prompt_templates[{index}]"
        prompt_text = str(template.get("prompt_text") or "")
        if "{prompt}" not in prompt_text:
            errors.append(error(f"{prefix}.prompt_text", "must contain {prompt}"))
        if not string_list(template.get("required_output_sections")):
            errors.append(error(f"{prefix}.required_output_sections", "must be a non-empty string list"))
        if template.get("id") == "ideal_answer_baseline":
            lower_text = prompt_text.lower()
            if "do not inspect local model output" not in lower_text:
                errors.append(
                    error(
                        f"{prefix}.prompt_text",
                        "baseline template must forbid inspecting local model output",
                    )
                )

    limits = dict_value(policy.get("recursion_limits"))
    max_rounds = limits.get("max_rounds")
    max_repair_cycles = limits.get("max_repair_cycles_per_issue")
    if not isinstance(max_rounds, int) or max_rounds < 1 or max_rounds > 3:
        errors.append(error("policy.recursion_limits.max_rounds", "must be an integer from 1 through 3"))
    if not isinstance(max_repair_cycles, int) or max_repair_cycles < 1 or max_repair_cycles > 2:
        errors.append(error("policy.recursion_limits.max_repair_cycles_per_issue", "must be an integer from 1 through 2"))
    if not string_list(limits.get("stop_conditions")):
        errors.append(error("policy.recursion_limits.stop_conditions", "must be a non-empty string list"))

    live = dict_value(policy.get("live_validation_requirements"))
    surfaces = set(string_list(live.get("required_surfaces")))
    if not REQUIRED_LOCAL_SURFACES.issubset(surfaces):
        errors.append(error("policy.live_validation_requirements.required_surfaces", "must include model, workflow router, and AnythingLLM"))
    target_roots = set(string_list(live.get("required_target_roots")))
    if target_roots != REQUIRED_TARGET_ROOTS:
        errors.append(error("policy.live_validation_requirements.required_target_roots", "must include both frozen Coinbase fixtures"))
    if live.get("protected_fixture_mutation_blocks_pass") is not True:
        errors.append(error("policy.live_validation_requirements.protected_fixture_mutation_blocks_pass", "must be true"))

    contract = dict_value(policy.get("report_contract"))
    if set(string_list(contract.get("required_fields"))) != REQUIRED_REPORT_FIELDS:
        errors.append(error("policy.report_contract.required_fields", "must match the required audit report fields"))
    ordering = dict_value(contract.get("ordering_rules"))
    for key in ("baseline_created_before_local_run", "same_prompt_hash_for_baseline_and_local", "blind_agent_is_contextless"):
        if ordering.get(key) is not True:
            errors.append(error(f"policy.report_contract.ordering_rules.{key}", "must be true"))
    if not isinstance(policy.get("sample_reports_path"), str) or not policy["sample_reports_path"].strip():
        errors.append(error("policy.sample_reports_path", "must be a non-empty path string"))
    return errors


def validate_sample_reports(sample_reports: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if sample_reports.get("schema_version") != SCHEMA_VERSION:
        errors.append(error("sample_reports.schema_version", "must be 1"))
    if sample_reports.get("kind") != EXPECTED_SAMPLE_KIND:
        errors.append(error("sample_reports.kind", f"must be {EXPECTED_SAMPLE_KIND}"))
    if sample_reports.get("phase") != EXPECTED_PHASE:
        errors.append(error("sample_reports.phase", "must be 185"))
    if sample_reports.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(error("sample_reports.priority_backlog_id", f"must be {EXPECTED_BACKLOG_ID}"))
    reports = object_list(sample_reports.get("reports"))
    if len(reports) < 3:
        errors.append(error("sample_reports.reports", "must include at least three sample reports"))

    required_target_roots = set(
        string_list(dict_value(policy.get("live_validation_requirements")).get("required_target_roots"))
    ) or REQUIRED_TARGET_ROOTS
    required_surfaces = set(
        string_list(dict_value(policy.get("live_validation_requirements")).get("required_surfaces"))
    ) or REQUIRED_LOCAL_SURFACES
    seen_families: set[str] = set()
    for index, report in enumerate(reports):
        prefix = f"sample_reports.reports[{index}]"
        missing = sorted(REQUIRED_REPORT_FIELDS - set(report))
        if missing:
            errors.append(error(prefix, f"missing required fields: {missing}"))
            continue
        prompt_family = report.get("prompt_family")
        if isinstance(prompt_family, str):
            seen_families.add(prompt_family)
        prompt = report.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(error(f"{prefix}.prompt", "must be a non-empty string"))
        prompt_hash = report.get("prompt_hash")
        if not isinstance(prompt_hash, str) or not HASH_RE.fullmatch(prompt_hash):
            errors.append(error(f"{prefix}.prompt_hash", "must be a 64-character lowercase sha256 hex string"))
        elif isinstance(prompt, str) and prompt_hash != sha256_text(prompt):
            errors.append(error(f"{prefix}.prompt_hash", "must be the sha256 hash of report.prompt"))
        if report.get("target_root") not in required_target_roots:
            errors.append(error(f"{prefix}.target_root", "must be one of the required frozen target roots"))

        blind_agent = dict_value(report.get("blind_agent"))
        if blind_agent.get("fork_context") is not False:
            errors.append(error(f"{prefix}.blind_agent.fork_context", "must be false"))
        if blind_agent.get("session_history_allowed") is not False:
            errors.append(error(f"{prefix}.blind_agent.session_history_allowed", "must be false"))
        if blind_agent.get("local_model_output_seen") is not False:
            errors.append(error(f"{prefix}.blind_agent.local_model_output_seen", "must be false"))

        baseline = dict_value(report.get("blind_baseline"))
        local_run = dict_value(report.get("local_run"))
        baseline_time = parse_timestamp(baseline.get("created_at"))
        local_time = parse_timestamp(local_run.get("started_at"))
        if baseline_time is None:
            errors.append(error(f"{prefix}.blind_baseline.created_at", "must be an ISO timestamp"))
        if local_time is None:
            errors.append(error(f"{prefix}.local_run.started_at", "must be an ISO timestamp"))
        if baseline_time is not None and local_time is not None and baseline_time > local_time:
            errors.append(error(f"{prefix}.blind_baseline.created_at", "must be before local_run.started_at"))
        for section in (
            "ideal_answer_shape",
            "must_have_facts",
            "evidence_expectations",
            "safety_boundaries",
            "output_expectations",
            "scoring_rubric",
        ):
            value = baseline.get(section)
            if section == "ideal_answer_shape":
                if not isinstance(value, str) or not value.strip():
                    errors.append(error(f"{prefix}.blind_baseline.{section}", "must be a non-empty string"))
            elif not string_list(value):
                errors.append(error(f"{prefix}.blind_baseline.{section}", "must be a non-empty string list"))

        for hash_path, value in (
            (f"{prefix}.blind_baseline.prompt_hash", baseline.get("prompt_hash")),
            (f"{prefix}.local_run.prompt_hash", local_run.get("prompt_hash")),
            (f"{prefix}.comparison.prompt_hash", dict_value(report.get("comparison")).get("prompt_hash")),
        ):
            if value != prompt_hash:
                errors.append(error(hash_path, "must match report.prompt_hash"))

        route_surfaces = set(string_list(local_run.get("route_surfaces")))
        if not required_surfaces.issubset(route_surfaces):
            errors.append(error(f"{prefix}.local_run.route_surfaces", "must include all required local-stack surfaces"))
        if not isinstance(local_run.get("run_id"), str) or not str(local_run.get("run_id")).startswith("workflow-router-"):
            errors.append(error(f"{prefix}.local_run.run_id", "must be a workflow-router run id"))
        if local_run.get("status") != "passed":
            errors.append(error(f"{prefix}.local_run.status", "must be passed for sample reports"))
        if not isinstance(local_run.get("response_text"), str) and not isinstance(local_run.get("response_ref"), str):
            errors.append(error(f"{prefix}.local_run.response_text", "must provide response_text or response_ref"))
        if isinstance(local_run.get("response_text"), str) and not local_run["response_text"].strip():
            errors.append(error(f"{prefix}.local_run.response_text", "must be non-empty when present"))
        if isinstance(local_run.get("response_ref"), str) and not local_run["response_ref"].strip():
            errors.append(error(f"{prefix}.local_run.response_ref", "must be non-empty when present"))
        route_evidence = dict_value(local_run.get("route_evidence"))
        if not route_evidence:
            errors.append(error(f"{prefix}.local_run.route_evidence", "must be a non-empty object"))
        elif not isinstance(route_evidence.get("selected_workflow"), str) or not route_evidence["selected_workflow"].strip():
            errors.append(error(f"{prefix}.local_run.route_evidence.selected_workflow", "must be a non-empty string"))
        fixture_proof = dict_value(local_run.get("fixture_mutation_proof"))
        if fixture_proof.get("fixture_unchanged") is not True:
            errors.append(error(f"{prefix}.local_run.fixture_mutation_proof.fixture_unchanged", "must be true"))

        comparison = dict_value(report.get("comparison"))
        score = comparison.get("score")
        if not isinstance(score, int) or score < 0 or score > 100:
            errors.append(error(f"{prefix}.comparison.score", "must be an integer from 0 through 100"))
        if score is not None and isinstance(score, int) and score < 85:
            errors.append(error(f"{prefix}.comparison.score", "must be at least 85 for passing sample reports"))
        if not string_list(comparison.get("rubric_dimensions")):
            errors.append(error(f"{prefix}.comparison.rubric_dimensions", "must be a non-empty string list"))
        if "baseline-before-local" not in string_list(comparison.get("proof_flags")):
            errors.append(error(f"{prefix}.comparison.proof_flags", "must include baseline-before-local"))

        repair = dict_value(report.get("repair_decision"))
        if repair.get("status") not in {"no_repair_needed", "repair_required", "deferred_scope_expansion"}:
            errors.append(error(f"{prefix}.repair_decision.status", "must be a known repair decision"))
        if not isinstance(repair.get("reason"), str) or not repair["reason"].strip():
            errors.append(error(f"{prefix}.repair_decision.reason", "must be a non-empty string"))

        closure = dict_value(report.get("closure"))
        if closure.get("final_status") not in {"passed", "needs_repair", "deferred_scope_expansion"}:
            errors.append(error(f"{prefix}.closure.final_status", "must be a known final status"))
        if closure.get("fixture_unchanged") is not True:
            errors.append(error(f"{prefix}.closure.fixture_unchanged", "must be true"))
        if not string_list(closure.get("validation_refs")):
            errors.append(error(f"{prefix}.closure.validation_refs", "must be a non-empty string list"))
        if not string_list(closure.get("live_stack_proof_refs")):
            errors.append(error(f"{prefix}.closure.live_stack_proof_refs", "must be a non-empty string list"))

    if len(seen_families) < 3:
        errors.append(error("sample_reports.reports", "must cover at least three prompt families"))
    return errors


def build_validation_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sample_reports: dict[str, Any],
    policy_path: Path,
    sample_reports_path: Path,
) -> dict[str, Any]:
    policy_errors = validate_policy(policy)
    sample_errors = validate_sample_reports(sample_reports, policy)
    validation_errors = [
        {"source": "policy", **item} for item in policy_errors
    ] + [
        {"source": "sample_reports", **item} for item in sample_errors
    ]
    reports = object_list(sample_reports.get("reports"))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": AuditPackStatus.PASSED.value if not validation_errors else AuditPackStatus.FAILED.value,
        "summary": {
            "policy_path": str(policy_path),
            "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
            "sample_reports_path": str(sample_reports_path),
            "sample_reports_sha256": sha256_file(sample_reports_path) if sample_reports_path.is_file() else None,
            "template_count": len(object_list(policy.get("prompt_templates"))),
            "process_step_count": len(object_list(policy.get("process_steps"))),
            "sample_report_count": len(reports),
            "prompt_family_count": len(
                {item.get("prompt_family") for item in reports if isinstance(item.get("prompt_family"), str)}
            ),
            "validation_error_count": len(validation_errors),
        },
        "validation_errors": validation_errors,
        "config_root": str(config_root),
    }
    return report


def run_contextless_agent_audit_pack(config: ContextlessAgentAuditPackConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    sample_reports_path = resolve_path(config_root, config.sample_reports_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    sample_reports = read_json_object(sample_reports_path)
    report = build_validation_report(
        config_root=config_root,
        policy=policy,
        sample_reports=sample_reports,
        policy_path=policy_path,
        sample_reports_path=sample_reports_path,
    )
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
