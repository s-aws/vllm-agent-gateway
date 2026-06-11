"""Phase 194 skill authoring pipeline V2 readiness gate."""

from __future__ import annotations

import hashlib
import ast
import json
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_registry_readiness_review import (
    SkillRegistryReadinessConfig,
    run_skill_registry_readiness_review,
)
from vllm_agent_gateway.skills.batches import build_skill_batch_report


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "skill_authoring_pipeline_v2_policy"
EXPECTED_REPORT_KIND = "skill_authoring_pipeline_v2_report"
EXPECTED_PHASE = 194
EXPECTED_BACKLOG_ID = "P0-BB-058"
DEFAULT_POLICY_PATH = Path("runtime") / "skill_authoring_pipeline_v2_policy.json"
DEFAULT_CANDIDATE_ROOT = Path("tests") / "fixtures" / "skill_authoring_pipeline_v2" / "phase194-readme-locator"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase194" / "phase194-skill-authoring-pipeline-v2-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase194" / "phase194-skill-authoring-pipeline-v2-report.md"
DEFAULT_BATCH_REPORT_PATH = Path("runtime-state") / "phase194" / "phase194-skill-authoring-pipeline-v2-batch-report.json"
DEFAULT_PHASE193_REPORT_PATH = Path("runtime-state") / "phase193" / "phase193-skill-registry-readiness-review-report.json"
REQUIRED_ARTIFACT_IDS = [
    "skill_batch_manifest",
    "skill_body",
    "prompt_coverage_entry",
    "eval_skeleton",
    "docs_stub",
    "docs_example",
    "regression_test_skeleton",
    "authoring_pipeline_plan",
]
REQUIRED_EVAL_GATE_IDS = [
    "routing",
    "artifact_contract",
    "natural_language_chat_output",
    "prompt_coverage",
    "blind_baseline_first",
    "holdout_prompt",
    "live_gateway",
    "anythingllm_when_applicable",
    "fixture_parity",
]
REQUIRED_LIVE_TARGETS = [
    "localhost_8000",
    "gateway_8300",
    "controller_8400",
    "workflow_router_8500",
    "documenter_8205",
    "anythingllm",
]
REQUIRED_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
REQUIRED_LIVE_COMMAND_SCRIPTS = [
    "scripts/validate_skill_authoring_pipeline_v2.py",
    "scripts/validate_skill_authoring_factory_live.py",
]


class SkillAuthoringPipelineStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class SkillAuthoringPipelineV2Config:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    candidate_root: Path = DEFAULT_CANDIDATE_ROOT
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    batch_report_path: Path = DEFAULT_BATCH_REPORT_PATH
    phase193_report_path: Path = DEFAULT_PHASE193_REPORT_PATH


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


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def validation_error(error_id: str, message: str, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    return [item for item in list_value(value) if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 194"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("acceptance_marker") != "PHASE194 SKILL AUTHORING PIPELINE V2 PASS":
        errors.append(validation_error("policy.acceptance_marker", "policy acceptance marker must match Phase 194"))
    if policy.get("gate_scope") != "draft_packet_admission_only":
        errors.append(validation_error("policy.gate_scope", "policy gate_scope must be draft_packet_admission_only"))
    if policy.get("proof_complete_required") is not False:
        errors.append(validation_error("policy.proof_complete_required", "Phase 194 is not a proof-complete promotion gate"))

    contract = dict_value(policy.get("candidate_contract"))
    if contract.get("candidate_state") != "draft_only":
        errors.append(validation_error("candidate_contract.candidate_state", "candidate state must be draft_only"))
    if contract.get("promotion_state") != "not_promoted_by_authoring_pipeline":
        errors.append(validation_error("candidate_contract.promotion_state", "promotion state must be not_promoted_by_authoring_pipeline"))
    if contract.get("manual_prompt_injection_allowed") is not False:
        errors.append(validation_error("candidate_contract.manual_prompt_injection_allowed", "manual prompt injection must be forbidden"))
    if contract.get("runtime_registry_mutation_allowed") is not False:
        errors.append(validation_error("candidate_contract.runtime_registry_mutation_allowed", "runtime registry mutation must be forbidden"))
    if contract.get("promotion_eligible_on_packet_admission") is not False:
        errors.append(validation_error("candidate_contract.promotion_eligible_on_packet_admission", "packet admission cannot make a skill promotion eligible"))
    for numeric_field in ("minimum_prompt_examples", "minimum_holdout_prompts", "minimum_acceptance_criteria"):
        if not isinstance(contract.get(numeric_field), int) or contract.get(numeric_field) < 1:
            errors.append(validation_error(f"candidate_contract.{numeric_field}", f"{numeric_field} must be a positive integer"))
    if string_list(contract.get("required_artifacts")) != REQUIRED_ARTIFACT_IDS:
        errors.append(validation_error("candidate_contract.required_artifacts", "required artifacts must match the Phase 194 draft-packet contract"))
    if string_list(contract.get("required_eval_gate_ids")) != REQUIRED_EVAL_GATE_IDS:
        errors.append(validation_error("candidate_contract.required_eval_gate_ids", "required eval gates must match the Phase 194 draft-packet contract"))

    live_requirements = dict_value(policy.get("live_validation_requirements"))
    if live_requirements.get("blind_baseline_before_local_output") is not True:
        errors.append(validation_error("live_validation_requirements.blind_baseline_before_local_output", "blind-baseline-first proof is required"))
    if live_requirements.get("anythingllm_required_when_applicable") is not True:
        errors.append(validation_error("live_validation_requirements.anythingllm_required_when_applicable", "AnythingLLM must be required when applicable"))
    if string_list(live_requirements.get("required_targets")) != REQUIRED_LIVE_TARGETS:
        errors.append(validation_error("live_validation_requirements.required_targets", "required live targets must match the Phase 194 contract"))
    if string_list(live_requirements.get("required_target_roots")) != REQUIRED_TARGET_ROOTS:
        errors.append(validation_error("live_validation_requirements.required_target_roots", "required fixture roots must match the Phase 194 contract"))

    promotion = dict_value(policy.get("promotion_requirements"))
    for key in (
        "batch_admission_must_pass",
        "prompt_coverage_starts_planned",
        "regression_skeleton_must_fail_closed",
        "phase193_readiness_must_pass",
        "manual_registry_append_forbidden",
        "candidate_absent_from_runtime_registries",
        "runtime_registry_hashes_must_match_before_after",
    ):
        if promotion.get(key) is not True:
            errors.append(validation_error(f"promotion_requirements.{key}", f"{key} must be true"))
    return errors


def candidate_file(candidate_root: Path, relative_path: str) -> Path:
    return candidate_root / relative_path


def load_json_candidate(candidate_root: Path, relative_path: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    path = candidate_file(candidate_root, relative_path)
    try:
        return read_json_object(path)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        errors.append(validation_error(f"candidate.{relative_path}", str(exc)))
        return {}


def load_phase193_report(config: SkillAuthoringPipelineV2Config) -> dict[str, Any]:
    phase193_path = resolve_path(config.config_root, config.phase193_report_path)
    if phase193_path.is_file():
        return read_json_object(phase193_path)
    return run_skill_registry_readiness_review(
        SkillRegistryReadinessConfig(
            config_root=config.config_root,
            output_path=phase193_path,
            markdown_output_path=None,
        )
    )


def source_artifacts(config_root: Path, policy: dict[str, Any], paths: dict[str, Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for key, path_text in sorted(dict_value(policy.get("required_source_paths")).items()):
        path = resolve_path(config_root, path_text)
        artifacts.append({"source_key": key, "path": str(path.resolve()), "sha256": artifact_hash(path)})
    for key, path in sorted(paths.items()):
        artifacts.append({"source_key": key, "path": str(path.resolve()), "sha256": artifact_hash(path)})
    return artifacts


def runtime_registry_paths(config_root: Path) -> dict[str, Path]:
    return {
        "skills": config_root / "runtime" / "skills.json",
        "skill_evals": config_root / "runtime" / "skill_evals.json",
        "prompt_skill_coverage": config_root / "runtime" / "prompt_skill_coverage.json",
    }


def runtime_registry_hashes(config_root: Path) -> dict[str, str | None]:
    return {key: artifact_hash(path) for key, path in runtime_registry_paths(config_root).items()}


def runtime_registry_ids(config_root: Path) -> dict[str, set[str]]:
    paths = runtime_registry_paths(config_root)
    skills_manifest = read_json_object(paths["skills"])
    evals_manifest = read_json_object(paths["skill_evals"])
    coverage_manifest = read_json_object(paths["prompt_skill_coverage"])
    return {
        "skill_ids": {
            str(item.get("id"))
            for item in list_value(skills_manifest.get("skills"))
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        },
        "eval_case_ids": {
            str(item.get("id"))
            for item in list_value(evals_manifest.get("cases"))
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        },
        "coverage_entry_ids": {
            str(item.get("id"))
            for item in list_value(coverage_manifest.get("entries"))
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        },
    }


def validate_candidate_not_installed(
    *,
    registry_ids: dict[str, set[str]],
    skill_id: str,
    eval_case_id: str,
    coverage_id: str,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if skill_id and skill_id in registry_ids.get("skill_ids", set()):
        errors.append(validation_error("candidate.runtime_registry.skill_id", "candidate skill_id already exists in runtime/skills.json"))
    if eval_case_id and eval_case_id in registry_ids.get("eval_case_ids", set()):
        errors.append(validation_error("candidate.runtime_registry.eval_case_id", "candidate eval_case_id already exists in runtime/skill_evals.json"))
    if coverage_id and coverage_id in registry_ids.get("coverage_entry_ids", set()):
        errors.append(validation_error("candidate.runtime_registry.coverage_entry_id", "candidate coverage entry already exists in runtime/prompt_skill_coverage.json"))
    return errors


def validate_runtime_hashes_unchanged(before: dict[str, str | None], after: dict[str, str | None]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for key, before_hash in sorted(before.items()):
        if before_hash != after.get(key):
            errors.append(validation_error(f"runtime_registry_mutation.{key}", f"{key} changed during Phase 194 validation"))
    return errors


def validate_phase193_report(report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("phase193.schema_version", "Phase 193 report schema_version must be 1"))
    if report.get("kind") != "skill_registry_readiness_review_report":
        errors.append(validation_error("phase193.kind", "Phase 193 report kind must be skill_registry_readiness_review_report"))
    if report.get("phase") not in (193, None):
        errors.append(validation_error("phase193.phase", "Phase 193 report phase must be 193 when present"))
    if report.get("status") != "passed":
        errors.append(validation_error("phase193.status", "Phase 193 skill registry readiness report must pass"))
    summary = dict_value(report.get("summary"))
    decision_counts = dict_value(summary.get("decision_counts"))
    blocking = sum(int(decision_counts.get(decision, 0) or 0) for decision in ("split", "merge", "retire"))
    if blocking:
        errors.append(validation_error("phase193.blocking_decisions", "Phase 193 report has split, merge, or retire decisions"))
    if summary.get("validation_error_count") not in (0, None):
        errors.append(validation_error("phase193.validation_errors", "Phase 193 report has validation errors"))
    return errors


def validate_batch_manifest(
    *,
    config_root: Path,
    candidate_root: Path,
    batch_report_path: Path,
    errors: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    batch_path = candidate_root / "skill-batch.json"
    batch_report = build_skill_batch_report(config_root, batch_path, output_path=batch_report_path)
    if batch_report.get("status") != "passed":
        errors.append(validation_error("candidate.skill_batch_manifest", "skill batch admission must pass before authoring pipeline review"))
    manifest = read_json_object(batch_path) if batch_path.is_file() else {}
    skills = list_value(manifest.get("skills"))
    eval_cases = list_value(manifest.get("eval_cases"))
    if len(skills) != 1:
        errors.append(validation_error("candidate.skill_count", "authoring pipeline V2 validates exactly one draft skill candidate at a time"))
    if len(eval_cases) != 1:
        errors.append(validation_error("candidate.eval_case_count", "authoring pipeline V2 validates exactly one eval case at a time"))
    skill = dict_value(skills[0]) if skills else {}
    eval_case = dict_value(eval_cases[0]) if eval_cases else {}
    return manifest, skill, eval_case, batch_report


def validate_artifact_paths(
    *,
    config_root: Path,
    candidate_root: Path,
    plan: dict[str, Any],
    skill: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, Path], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    artifact_paths = {
        "skill_batch_manifest": candidate_root / "skill-batch.json",
        "prompt_coverage_entry": candidate_root / "prompt-coverage-entry.json",
        "eval_skeleton": candidate_root / "eval-skeleton.json",
        "authoring_pipeline_plan": candidate_root / "authoring-pipeline-plan.json",
    }
    skill_path = resolve_path(config_root, str(skill.get("path") or ""))
    if str(skill.get("path") or ""):
        artifact_paths["skill_body"] = skill_path
    plan_paths = dict_value(plan.get("artifact_paths"))
    for key in ("docs_stub", "docs_example", "regression_test_skeleton"):
        value = plan_paths.get(key)
        if isinstance(value, str) and value.strip():
            artifact_paths[key] = resolve_path(candidate_root, value)
    required = string_list(dict_value(policy.get("candidate_contract")).get("required_artifacts"))
    missing_names = sorted(set(required) - set(artifact_paths))
    for key in missing_names:
        errors.append(validation_error(f"candidate.artifacts.{key}", f"missing artifact path for {key}"))
    for key in required:
        path = artifact_paths.get(key)
        if path is None:
            continue
        if not path.is_file():
            errors.append(validation_error(f"candidate.artifacts.{key}", f"artifact does not exist: {path}"))
        if key != "skill_body" and not path_is_inside(path, candidate_root):
            errors.append(validation_error(f"candidate.artifacts.{key}.boundary", f"artifact must stay under candidate root: {path}"))
    if "skill_body" in artifact_paths and not path_is_inside(artifact_paths["skill_body"], candidate_root):
        errors.append(validation_error("candidate.artifacts.skill_body.boundary", "draft skill body must stay under candidate root"))
    return artifact_paths, errors


def validate_coverage_entry(
    *,
    coverage: dict[str, Any],
    skill: dict[str, Any],
    eval_case: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    contract = dict_value(policy.get("candidate_contract"))
    skill_id = str(skill.get("id") or "")
    eval_case_id = str(eval_case.get("id") or "")
    workflow_id = str(eval_case.get("expected_workflow") or "")
    expected_artifacts = string_list(eval_case.get("expected_artifacts"))
    if coverage.get("status") != "planned":
        errors.append(validation_error("candidate.prompt_coverage_entry.status", "candidate prompt coverage must start as planned"))
    if coverage.get("promotion_state") != contract.get("promotion_state"):
        errors.append(validation_error("candidate.prompt_coverage_entry.promotion_state", "coverage promotion state must match policy"))
    if string_list(coverage.get("skill_ids")) != [skill_id]:
        errors.append(validation_error("candidate.prompt_coverage_entry.skill_ids", "coverage entry must reference the candidate skill only"))
    if string_list(coverage.get("eval_case_ids")) != [eval_case_id]:
        errors.append(validation_error("candidate.prompt_coverage_entry.eval_case_ids", "coverage entry must reference the candidate eval case only"))
    if coverage.get("selected_workflow") != workflow_id:
        errors.append(validation_error("candidate.prompt_coverage_entry.selected_workflow", "coverage workflow must match eval case"))
    missing_artifacts = sorted(set(expected_artifacts) - set(string_list(coverage.get("expected_artifacts"))))
    if missing_artifacts:
        errors.append(validation_error("candidate.prompt_coverage_entry.expected_artifacts", f"coverage entry missing expected artifact(s): {', '.join(missing_artifacts)}"))
    if not string_list(coverage.get("docs_examples")):
        errors.append(validation_error("candidate.prompt_coverage_entry.docs_examples", "coverage entry must include docs examples"))
    return errors, {
        "coverage_id": str(coverage.get("id") or ""),
        "coverage_status": str(coverage.get("status") or ""),
        "coverage_promotion_state": str(coverage.get("promotion_state") or ""),
    }


def validate_eval_skeleton(eval_skeleton: dict[str, Any], policy: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    contract = dict_value(policy.get("candidate_contract"))
    if eval_skeleton.get("kind") != "skill_eval_skeleton":
        errors.append(validation_error("candidate.eval_skeleton.kind", "eval skeleton kind must be skill_eval_skeleton"))
    if eval_skeleton.get("promotion_state") != contract.get("promotion_state"):
        errors.append(validation_error("candidate.eval_skeleton.promotion_state", "eval skeleton promotion state must match policy"))
    gates = [item for item in list_value(eval_skeleton.get("required_gates")) if isinstance(item, dict)]
    gate_statuses = {str(gate.get("id") or ""): str(gate.get("status") or "") for gate in gates}
    required_gate_ids = string_list(contract.get("required_eval_gate_ids"))
    missing_gates = sorted(set(required_gate_ids) - set(gate_statuses))
    extra_gates = sorted(set(gate_statuses) - set(required_gate_ids))
    if missing_gates:
        errors.append(validation_error("candidate.eval_skeleton.missing_gates", f"missing gate(s): {', '.join(missing_gates)}"))
    if extra_gates:
        errors.append(validation_error("candidate.eval_skeleton.extra_gates", f"unexpected gate(s): {', '.join(extra_gates)}"))
    invalid_statuses = sorted(gate_id for gate_id, status in gate_statuses.items() if status not in {"not_run", "planned"})
    if invalid_statuses:
        errors.append(validation_error("candidate.eval_skeleton.gate_status", f"candidate gates must remain not_run or planned: {', '.join(invalid_statuses)}"))
    return errors, {"gate_statuses": gate_statuses, "gate_count": len(gate_statuses)}


def prompt_record_key(record: object) -> str:
    if not isinstance(record, dict):
        return ""
    return str(record.get("prompt") or "").strip().lower()


def validate_prompt_records(
    records: list[Any],
    *,
    label: str,
    expected_route: str,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    for index, raw_record in enumerate(records):
        record = dict_value(raw_record)
        record_id = str(record.get("id") or "")
        prompt = str(record.get("prompt") or "").strip()
        route = str(record.get("expected_route") or "").strip()
        if not record_id:
            errors.append(validation_error(f"candidate.authoring_pipeline_plan.{label}[{index}].id", "prompt record id is required"))
        elif record_id in seen_ids:
            errors.append(validation_error(f"candidate.authoring_pipeline_plan.{label}[{index}].id", f"duplicate prompt record id: {record_id}"))
        seen_ids.add(record_id)
        if len(prompt) < 20:
            errors.append(validation_error(f"candidate.authoring_pipeline_plan.{label}[{index}].prompt", "prompt must be a descriptive natural-language request"))
        prompt_key = prompt.lower()
        if prompt_key and prompt_key in seen_prompts:
            errors.append(validation_error(f"candidate.authoring_pipeline_plan.{label}[{index}].prompt", "duplicate prompt text is not allowed"))
        seen_prompts.add(prompt_key)
        if route != expected_route:
            errors.append(validation_error(f"candidate.authoring_pipeline_plan.{label}[{index}].expected_route", "prompt expected_route must match the eval workflow"))
    return errors


def command_script(command: str) -> str:
    try:
        parts = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return ""
    if not parts:
        return ""
    for index, part in enumerate(parts):
        normalized = part.replace("\\", "/")
        if normalized.endswith(".py"):
            return normalized
        if Path(normalized).name.startswith("python") and index + 1 < len(parts):
            next_part = parts[index + 1].replace("\\", "/")
            if next_part.endswith(".py"):
                return next_part
    return ""


def validate_plan(plan: dict[str, Any], policy: dict[str, Any], eval_case: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    contract = dict_value(policy.get("candidate_contract"))
    live_requirements = dict_value(policy.get("live_validation_requirements"))
    if plan.get("kind") != "skill_authoring_pipeline_v2_candidate_plan":
        errors.append(validation_error("candidate.authoring_pipeline_plan.kind", "plan kind must be skill_authoring_pipeline_v2_candidate_plan"))
    if plan.get("promotion_state") != contract.get("promotion_state"):
        errors.append(validation_error("candidate.authoring_pipeline_plan.promotion_state", "plan promotion state must match policy"))
    if plan.get("manual_prompt_injection_allowed") is not False:
        errors.append(validation_error("candidate.authoring_pipeline_plan.manual_prompt_injection_allowed", "manual prompt injection must be false"))
    if plan.get("runtime_registry_mutation_allowed") is not False:
        errors.append(validation_error("candidate.authoring_pipeline_plan.runtime_registry_mutation_allowed", "runtime registry mutation must be false"))

    prompt_examples = list_value(plan.get("prompt_examples"))
    holdout_prompts = list_value(plan.get("holdout_prompts"))
    acceptance_criteria = [item for item in list_value(plan.get("acceptance_criteria")) if isinstance(item, dict)]
    if len(prompt_examples) < int(contract.get("minimum_prompt_examples") or 0):
        errors.append(validation_error("candidate.authoring_pipeline_plan.prompt_examples", "not enough prompt examples"))
    if len(holdout_prompts) < int(contract.get("minimum_holdout_prompts") or 0):
        errors.append(validation_error("candidate.authoring_pipeline_plan.holdout_prompts", "not enough holdout prompts"))
    if len(acceptance_criteria) < int(contract.get("minimum_acceptance_criteria") or 0):
        errors.append(validation_error("candidate.authoring_pipeline_plan.acceptance_criteria", "not enough acceptance criteria"))
    expected_route = str(eval_case.get("expected_workflow") or "")
    errors.extend(validate_prompt_records(prompt_examples, label="prompt_examples", expected_route=expected_route))
    errors.extend(validate_prompt_records(holdout_prompts, label="holdout_prompts", expected_route=expected_route))
    prompt_overlap = sorted({prompt_record_key(record) for record in prompt_examples} & {prompt_record_key(record) for record in holdout_prompts})
    prompt_overlap = [item for item in prompt_overlap if item]
    if prompt_overlap:
        errors.append(validation_error("candidate.authoring_pipeline_plan.prompt_holdout_overlap", "target prompt examples and holdouts must not use the same prompt text"))
    for index, criterion in enumerate(acceptance_criteria):
        for field in ("id", "criterion", "verification", "evidence_required"):
            if not isinstance(criterion.get(field), str) or not criterion[field].strip():
                errors.append(validation_error(f"candidate.authoring_pipeline_plan.acceptance_criteria[{index}].{field}", f"acceptance criterion {field} is required"))
        evidence_text = str(criterion.get("evidence_required") or "").lower()
        if not any(marker in evidence_text for marker in ("artifact", "report", "response", "hash", "source")):
            errors.append(validation_error(f"candidate.authoring_pipeline_plan.acceptance_criteria[{index}].evidence_required", "acceptance evidence must name a concrete artifact, report, response, hash, or source"))

    baseline_plan = dict_value(plan.get("blind_baseline_plan"))
    if baseline_plan.get("contextless_agent_first") is not True:
        errors.append(validation_error("candidate.authoring_pipeline_plan.blind_baseline_plan.contextless_agent_first", "blind baseline must be collected before local output"))
    if baseline_plan.get("local_model_output_available_to_blind_agent") is not False:
        errors.append(validation_error("candidate.authoring_pipeline_plan.blind_baseline_plan.local_model_output_available_to_blind_agent", "blind agent must not see local output first"))
    expected_baseline_outputs = {"ideal_answer_shape", "must_have_facts", "evidence_expectations", "scoring_rubric", "safety_boundaries"}
    missing_baseline_outputs = sorted(expected_baseline_outputs - set(string_list(baseline_plan.get("required_outputs"))))
    if missing_baseline_outputs:
        errors.append(validation_error("candidate.authoring_pipeline_plan.blind_baseline_plan.required_outputs", f"missing blind baseline output(s): {', '.join(missing_baseline_outputs)}"))

    live_plan = dict_value(plan.get("live_validation_plan"))
    required_targets = set(string_list(live_requirements.get("required_targets")))
    target_roots = set(string_list(live_requirements.get("required_target_roots")))
    missing_targets = sorted(required_targets - set(string_list(live_plan.get("required_targets"))))
    missing_roots = sorted(target_roots - set(string_list(live_plan.get("target_roots"))))
    if missing_targets:
        errors.append(validation_error("candidate.authoring_pipeline_plan.live_validation_plan.required_targets", f"missing target(s): {', '.join(missing_targets)}"))
    if missing_roots:
        errors.append(validation_error("candidate.authoring_pipeline_plan.live_validation_plan.target_roots", f"missing target root(s): {', '.join(missing_roots)}"))
    if live_plan.get("anythingllm_required_when_applicable") is not True:
        errors.append(validation_error("candidate.authoring_pipeline_plan.live_validation_plan.anythingllm_required_when_applicable", "AnythingLLM requirement must be explicit"))
    if not string_list(live_plan.get("commands")):
        errors.append(validation_error("candidate.authoring_pipeline_plan.live_validation_plan.commands", "live validation plan must include commands"))
    commands = string_list(live_plan.get("commands"))
    command_scripts = {command_script(command) for command in commands}
    missing_command_scripts = sorted(set(REQUIRED_LIVE_COMMAND_SCRIPTS) - command_scripts)
    if missing_command_scripts:
        errors.append(validation_error("candidate.authoring_pipeline_plan.live_validation_plan.commands", f"live validation plan must include script(s): {', '.join(missing_command_scripts)}"))
    return errors, {
        "prompt_example_count": len(prompt_examples),
        "holdout_prompt_count": len(holdout_prompts),
        "acceptance_criteria_count": len(acceptance_criteria),
        "live_target_count": len(string_list(live_plan.get("required_targets"))),
    }


def validate_regression_skeleton(path: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [validation_error("candidate.regression_test_skeleton", str(exc))]
    required_gate_ids = string_list(dict_value(policy.get("candidate_contract")).get("required_eval_gate_ids"))
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [validation_error("candidate.regression_test_skeleton.syntax", f"regression skeleton is invalid Python: {exc}")]
    test_functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    function_names = {node.name: node for node in test_functions}
    for gate_id in required_gate_ids:
        matching = [node for name, node in function_names.items() if gate_id in name]
        if not matching:
            errors.append(validation_error("candidate.regression_test_skeleton.gate_markers", f"regression skeleton missing test function for gate: {gate_id}"))
            continue
        fail_closed = False
        for node in matching:
            for statement in node.body:
                call: ast.Call | None = None
                if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                    call = statement.value
                if call is None:
                    continue
                func = call.func
                if isinstance(func, ast.Attribute) and func.attr == "fail" and isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    fail_closed = True
                    break
            if fail_closed:
                break
        if not fail_closed:
            errors.append(validation_error("candidate.regression_test_skeleton.fail_closed", f"regression skeleton gate does not fail closed: {gate_id}"))
    return errors


def build_skill_authoring_pipeline_v2_report(config: SkillAuthoringPipelineV2Config) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    candidate_root = resolve_path(config_root, config.candidate_root)
    policy_path = resolve_path(config_root, config.policy_path)
    batch_report_path = resolve_path(config_root, config.batch_report_path)
    policy = read_json_object(policy_path)
    before_runtime_hashes = runtime_registry_hashes(config_root)
    active_registry_ids = runtime_registry_ids(config_root)
    errors = validate_policy(policy)
    phase193_report = load_phase193_report(config)
    errors.extend(validate_phase193_report(phase193_report))

    manifest, skill, eval_case, batch_report = validate_batch_manifest(
        config_root=config_root,
        candidate_root=candidate_root,
        batch_report_path=batch_report_path,
        errors=errors,
    )
    coverage = load_json_candidate(candidate_root, "prompt-coverage-entry.json", errors)
    eval_skeleton = load_json_candidate(candidate_root, "eval-skeleton.json", errors)
    plan = load_json_candidate(candidate_root, "authoring-pipeline-plan.json", errors)
    artifact_paths, artifact_errors = validate_artifact_paths(
        config_root=config_root,
        candidate_root=candidate_root,
        plan=plan,
        skill=skill,
        policy=policy,
    )
    errors.extend(artifact_errors)
    coverage_errors, coverage_summary = validate_coverage_entry(
        coverage=coverage,
        skill=skill,
        eval_case=eval_case,
        policy=policy,
    )
    errors.extend(coverage_errors)
    eval_errors, eval_summary = validate_eval_skeleton(eval_skeleton, policy)
    errors.extend(eval_errors)
    plan_errors, plan_summary = validate_plan(plan, policy, eval_case)
    errors.extend(plan_errors)
    regression_path = artifact_paths.get("regression_test_skeleton")
    if regression_path is not None:
        errors.extend(validate_regression_skeleton(regression_path, policy))

    skill_id = str(skill.get("id") or "")
    eval_case_id = str(eval_case.get("id") or "")
    coverage_id = str(coverage.get("id") or "")
    errors.extend(
        validate_candidate_not_installed(
            registry_ids=active_registry_ids,
            skill_id=skill_id,
            eval_case_id=eval_case_id,
            coverage_id=coverage_id,
        )
    )
    after_runtime_hashes = runtime_registry_hashes(config_root)
    errors.extend(validate_runtime_hashes_unchanged(before_runtime_hashes, after_runtime_hashes))
    route_key = str(dict_value(skill.get("capability_contract")).get("route_key") or "")
    packet_status = "blocked" if errors else "admitted"
    proof_status = "not_run"
    promotion_eligible = False
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": SkillAuthoringPipelineStatus.FAILED.value if errors else SkillAuthoringPipelineStatus.PASSED.value,
        "gate_scope": "draft_packet_admission_only",
        "packet_status": packet_status,
        "proof_status": proof_status,
        "promotion_eligible": promotion_eligible,
        "created_at": utc_timestamp(),
        "candidate_root": str(candidate_root.resolve()),
        "candidate": {
            "batch_id": str(manifest.get("id") or ""),
            "skill_id": skill_id,
            "eval_case_id": eval_case_id,
            "prompt_family": str(eval_case.get("prompt_family") or ""),
            "route_key": route_key,
            "workflow": str(eval_case.get("expected_workflow") or ""),
            "promotion_state": str(plan.get("promotion_state") or ""),
            **coverage_summary,
            **eval_summary,
            **plan_summary,
        },
        "batch_report": {
            "status": batch_report.get("status"),
            "report_path": batch_report.get("report_path"),
            "errors": batch_report.get("errors", []),
            "summary": batch_report.get("summary", {}),
        },
        "phase193_readiness": {
            "status": phase193_report.get("status"),
            "summary": phase193_report.get("summary", {}),
        },
        "runtime_registry_mutation_check": {
            "before": before_runtime_hashes,
            "after": after_runtime_hashes,
            "status": "passed" if before_runtime_hashes == after_runtime_hashes else "failed",
        },
        "candidate_absence_check": {
            "skill_id_absent": skill_id not in active_registry_ids.get("skill_ids", set()),
            "eval_case_id_absent": eval_case_id not in active_registry_ids.get("eval_case_ids", set()),
            "coverage_entry_id_absent": coverage_id not in active_registry_ids.get("coverage_entry_ids", set()),
        },
        "gate_results": [
            {"id": gate_id, "status": eval_summary.get("gate_statuses", {}).get(gate_id, "missing")}
            for gate_id in string_list(dict_value(policy.get("candidate_contract")).get("required_eval_gate_ids"))
        ],
        "source_artifacts": source_artifacts(
            config_root,
            policy,
            {
                "policy": policy_path,
                "candidate_skill_batch": candidate_root / "skill-batch.json",
                "candidate_prompt_coverage_entry": candidate_root / "prompt-coverage-entry.json",
                "candidate_eval_skeleton": candidate_root / "eval-skeleton.json",
                "candidate_authoring_pipeline_plan": candidate_root / "authoring-pipeline-plan.json",
                "phase193_readiness_report": resolve_path(config_root, config.phase193_report_path),
                "batch_validation_report": batch_report_path,
            },
        ),
        "validation_errors": errors,
        "summary": {
            "candidate_count": 1 if skill_id else 0,
            "skill_id": skill_id,
            "batch_status": batch_report.get("status"),
            "gate_count": eval_summary.get("gate_count", 0),
            "prompt_example_count": plan_summary.get("prompt_example_count", 0),
            "holdout_prompt_count": plan_summary.get("holdout_prompt_count", 0),
            "acceptance_criteria_count": plan_summary.get("acceptance_criteria_count", 0),
            "validation_error_count": len(errors),
            "packet_status": packet_status,
            "proof_status": proof_status,
            "promotion_eligible": promotion_eligible,
            "promotion_decision": "draft_packet_admitted_not_promoted" if not errors else "blocked",
            "next_action": "work Phase 195 next" if not errors else "fix Phase 194 authoring pipeline candidate",
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    candidate = dict_value(report.get("candidate"))
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 194 Skill Authoring Pipeline V2 Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Gate scope: `{report.get('gate_scope')}`",
        f"- Packet status: `{report.get('packet_status')}`",
        f"- Proof status: `{report.get('proof_status')}`",
        f"- Promotion eligible: `{report.get('promotion_eligible')}`",
        f"- Candidate: `{candidate.get('skill_id')}`",
        f"- Route key: `{candidate.get('route_key')}`",
        f"- Batch status: `{summary.get('batch_status')}`",
        f"- Promotion decision: `{summary.get('promotion_decision')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Gates",
        "",
    ]
    for gate in list_value(report.get("gate_results")):
        if isinstance(gate, dict):
            lines.append(f"- `{gate.get('id')}`: `{gate.get('status')}`")
    errors = list_value(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        for error in errors:
            if isinstance(error, dict):
                lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    return "\n".join(lines) + "\n"


def run_skill_authoring_pipeline_v2(config: SkillAuthoringPipelineV2Config) -> dict[str, Any]:
    report = build_skill_authoring_pipeline_v2_report(config)
    output_path = resolve_path(config.config_root, config.output_path)
    write_json(output_path, report)
    markdown_output_path = None if config.markdown_output_path is None else resolve_path(config.config_root, config.markdown_output_path)
    if markdown_output_path is not None:
        write_text(markdown_output_path, render_markdown(report))
    return report
