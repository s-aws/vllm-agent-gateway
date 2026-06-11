"""Phase 195 release-candidate founder trial pack validation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "release_candidate_founder_trial_pack_policy"
EXPECTED_PACK_KIND = "release_candidate_founder_trial_pack"
EXPECTED_REPORT_KIND = "release_candidate_founder_trial_pack_report"
EXPECTED_PHASE = 195
EXPECTED_BACKLOG_ID = "P0-BB-059"
DEFAULT_POLICY_PATH = Path("runtime") / "release_candidate_founder_trial_pack_policy.json"
DEFAULT_PACK_PATH = Path("runtime") / "release_candidate_founder_trial_pack.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase195" / "phase195-release-candidate-founder-trial-pack-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase195" / "phase195-release-candidate-founder-trial-pack-report.md"
CHAT_VISIBLE_HEADINGS = {
    "Answer:",
    "Task Decomposition:",
    "Draft proposal:",
    "Lifecycle Audit:",
    "Skill Selection:",
}


class FounderTrialPackStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class FounderTrialPackConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    pack_path: Path = DEFAULT_PACK_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_proof_artifacts: bool = True
    validate_fixture_state: bool = False


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


def directory_fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for item in sorted(child for child in path.rglob("*") if child.is_file()):
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        data = item.read_bytes()
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\0")
        file_count += 1
        total_bytes += len(data)
    return {"file_count": file_count, "total_bytes": total_bytes, "sha256": digest.hexdigest()}


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


def validation_error(error_id: str, message: str, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def expected_phase_from_path(path: str) -> int | None:
    name = Path(path).name
    if not name.startswith("phase"):
        return None
    digits = []
    for char in name.removeprefix("phase"):
        if char.isdigit():
            digits.append(char)
            continue
        break
    return int("".join(digits)) if digits else None


def catalog_cases(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("case_id")): item
        for item in object_list(catalog.get("cases"))
        if isinstance(item.get("case_id"), str)
    }


def stage_case_ids(pack: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(stage.get("id")): string_list(stage.get("prompt_case_ids"))
        for stage in object_list(pack.get("trial_stages"))
        if isinstance(stage.get("id"), str) and stage.get("prompt_case_ids") is not None
    }


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 195"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("acceptance_marker") != "PHASE195 RELEASE CANDIDATE FOUNDER TRIAL PACK PASS":
        errors.append(validation_error("policy.acceptance_marker", "policy acceptance marker must match Phase 195"))
    if dict_value(policy.get("required_anythingllm")).get("llm_base_url") != "http://127.0.0.1:8500/v1":
        errors.append(validation_error("policy.required_anythingllm.llm_base_url", "AnythingLLM workflow testing must target 8500/v1"))
    if policy.get("proof_artifact_mode_required_for_release") is not True:
        errors.append(
            validation_error(
                "policy.proof_artifact_mode_required_for_release",
                "release-candidate closure must require proof artifact mode",
            )
        )
    for list_field in (
        "required_target_roots",
        "required_prompt_case_ids",
        "forbidden_prompt_tags",
        "required_setup_command_markers",
        "required_feedback_template_markers",
        "required_docs",
        "required_proof_refs",
    ):
        if not string_list(policy.get(list_field)):
            errors.append(validation_error(f"policy.{list_field}", f"{list_field} must be a non-empty list"))
    stage_cases = dict_value(policy.get("required_stage_case_ids"))
    for stage_id in ("founder-smoke", "expanded-read-only"):
        if not string_list(stage_cases.get(stage_id)):
            errors.append(validation_error(f"policy.required_stage_case_ids.{stage_id}", f"{stage_id} case IDs are required"))
    feedback = dict_value(policy.get("feedback_capture"))
    if feedback.get("destination") != "runtime-state/phase195/founder-feedback.jsonl":
        errors.append(validation_error("policy.feedback_capture.destination", "feedback destination must be runtime-state/phase195/founder-feedback.jsonl"))
    if not string_list(feedback.get("allowed_classifications")):
        errors.append(validation_error("policy.feedback_capture.allowed_classifications", "feedback classifications are required"))
    if not string_list(feedback.get("allowed_severities")):
        errors.append(validation_error("policy.feedback_capture.allowed_severities", "feedback severities are required"))
    if not string_list(feedback.get("required_record_fields")):
        errors.append(validation_error("policy.feedback_capture.required_record_fields", "feedback record fields are required"))
    fixture_safety = dict_value(policy.get("fixture_safety"))
    if fixture_safety.get("source_mutation_allowed") is not False:
        errors.append(validation_error("policy.fixture_safety.source_mutation_allowed", "source mutation must be forbidden"))
    if not string_list(fixture_safety.get("required_integrity_commands")):
        errors.append(validation_error("policy.fixture_safety.required_integrity_commands", "fixture integrity commands are required"))
    if not string_list(policy.get("required_recovery_keys")):
        errors.append(validation_error("policy.required_recovery_keys", "required recovery keys are required"))
    return errors


def load_prompt_sources(config_root: Path, pack: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    sources = dict_value(pack.get("prompt_sources"))
    prompt_pack_path = resolve_path(config_root, str(sources.get("founder_test_prompt_pack") or ""))
    catalog_path = resolve_path(config_root, str(sources.get("prompt_catalog") or ""))
    prompt_pack = read_json_object(prompt_pack_path)
    catalog = read_json_object(catalog_path)
    return prompt_pack, catalog, prompt_pack_path, catalog_path


def validate_pack(
    *,
    config_root: Path,
    policy: dict[str, Any],
    pack: dict[str, Any],
    prompt_pack: dict[str, Any],
    catalog: dict[str, Any],
    require_proof_artifacts: bool,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("proof_artifact_mode_required_for_release") is True and not require_proof_artifacts:
        errors.append(
            validation_error(
                "run.proof_artifacts.required",
                "Phase 195 release-candidate validation must run with proof artifact mode enabled",
                "critical",
            )
        )
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("pack.schema_version", "pack.schema_version must be 1"))
    if pack.get("kind") != EXPECTED_PACK_KIND:
        errors.append(validation_error("pack.kind", f"pack.kind must be {EXPECTED_PACK_KIND}"))
    if pack.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("pack.phase", "pack.phase must be 195"))
    if pack.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("pack.priority_backlog_id", f"pack.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if pack.get("status") != "ready_for_founder_trial":
        errors.append(validation_error("pack.status", "pack.status must be ready_for_founder_trial"))

    required_anythingllm = dict_value(policy.get("required_anythingllm"))
    anythingllm = dict_value(pack.get("anythingllm"))
    for key, expected in sorted(required_anythingllm.items()):
        if anythingllm.get(key) != expected:
            errors.append(validation_error(f"pack.anythingllm.{key}", f"AnythingLLM {key} must be {expected}"))
    if string_list(pack.get("target_roots")) != string_list(policy.get("required_target_roots")):
        errors.append(validation_error("pack.target_roots", "target roots must match policy order and values"))

    stages = object_list(pack.get("trial_stages"))
    stage_ids = [str(stage.get("id")) for stage in stages if isinstance(stage.get("id"), str)]
    if "setup-readiness" not in stage_ids:
        errors.append(validation_error("pack.trial_stages.setup-readiness", "setup-readiness stage is required"))
    if "founder-smoke" not in stage_ids:
        errors.append(validation_error("pack.trial_stages.founder-smoke", "founder-smoke stage is required"))
    if "expanded-read-only" not in stage_ids:
        errors.append(validation_error("pack.trial_stages.expanded-read-only", "expanded-read-only stage is required"))
    case_ids_by_stage = stage_case_ids(pack)
    required_stage_case_ids = dict_value(policy.get("required_stage_case_ids"))
    for stage_id, expected_ids in sorted(required_stage_case_ids.items()):
        if case_ids_by_stage.get(stage_id) != string_list(expected_ids):
            errors.append(validation_error(f"pack.trial_stages.{stage_id}.prompt_case_ids", f"{stage_id} prompt case IDs must match policy"))
    selected_case_ids = [case_id for ids in case_ids_by_stage.values() for case_id in ids]
    if duplicate_values(selected_case_ids):
        errors.append(validation_error("pack.trial_stages.prompt_case_ids", "prompt case IDs must not be duplicated across stages"))
    required_prompt_ids = set(string_list(policy.get("required_prompt_case_ids")))
    missing_required = sorted(required_prompt_ids - set(selected_case_ids))
    if missing_required:
        errors.append(validation_error("pack.trial_stages.required_prompt_case_ids", f"missing required prompt case(s): {', '.join(missing_required)}"))

    catalog_by_id = catalog_cases(catalog)
    unknown_cases = sorted(set(selected_case_ids) - set(catalog_by_id))
    if unknown_cases:
        errors.append(validation_error("pack.trial_stages.unknown_prompt_case_ids", f"unknown prompt case(s): {', '.join(unknown_cases)}"))
    founder_pack_ids = {case_id for tier in object_list(prompt_pack.get("tiers")) for case_id in string_list(tier.get("case_ids"))}
    missing_from_founder_pack = sorted(set(selected_case_ids) - founder_pack_ids)
    if missing_from_founder_pack:
        errors.append(validation_error("pack.prompt_sources.founder_test_prompt_pack", f"case(s) are not in founder_test_prompt_pack: {', '.join(missing_from_founder_pack)}"))

    forbidden_tags = set(string_list(policy.get("forbidden_prompt_tags")))
    selected_cases = [catalog_by_id[case_id] for case_id in selected_case_ids if case_id in catalog_by_id]
    target_roots = {str(case.get("target_root")) for case in selected_cases}
    missing_roots = sorted(set(string_list(policy.get("required_target_roots"))) - target_roots)
    if missing_roots:
        errors.append(validation_error("pack.prompt_cases.target_roots", f"selected prompts do not cover target root(s): {', '.join(missing_roots)}"))
    for case in selected_cases:
        case_id = str(case.get("case_id"))
        tags = set(string_list(case.get("tags")))
        forbidden = sorted(tags & forbidden_tags)
        if forbidden:
            errors.append(validation_error(f"pack.prompt_cases.{case_id}.tags", f"forbidden founder trial tag(s): {', '.join(forbidden)}"))
        if str(case.get("expected_workflow") or "") == "refactor.single_path":
            errors.append(validation_error(f"pack.prompt_cases.{case_id}.workflow", "advanced refactor workflow is not allowed in founder trial pack"))
        expected_markers = string_list(case.get("expected_markers"))
        if not (set(expected_markers) & CHAT_VISIBLE_HEADINGS):
            errors.append(validation_error(f"pack.prompt_cases.{case_id}.expected_markers", "trial prompt must require a governed chat-visible answer heading"))
        if not string_list(case.get("semantic_markers")):
            errors.append(validation_error(f"pack.prompt_cases.{case_id}.semantic_markers", "trial prompt must include semantic answer markers"))

    setup_stage = next((stage for stage in stages if stage.get("id") == "setup-readiness"), {})
    setup_commands = object_list(setup_stage.get("commands"))
    if not setup_commands:
        errors.append(validation_error("pack.trial_stages.setup-readiness.commands", "setup commands must be structured objects"))
    command_text = "\n".join(str(command.get("command") or "") for command in setup_commands)
    for marker in string_list(policy.get("required_setup_command_markers")):
        if marker not in command_text:
            errors.append(validation_error("pack.trial_stages.setup-readiness.commands", f"setup stage missing command marker: {marker}"))
    for index, command in enumerate(setup_commands):
        for field in ("command", "expected_marker", "failure_recovery"):
            if not isinstance(command.get(field), str) or not command[field].strip():
                errors.append(validation_error(f"pack.trial_stages.setup-readiness.commands[{index}].{field}", f"setup command {field} is required"))
        if command.get("required_before_prompt_testing") is not True:
            errors.append(validation_error(f"pack.trial_stages.setup-readiness.commands[{index}].required_before_prompt_testing", "setup command must be required before prompt testing"))

    feedback = dict_value(pack.get("feedback_capture"))
    templates = object_list(feedback.get("templates"))
    if len(templates) < 3:
        errors.append(validation_error("pack.feedback_capture.templates", "at least three feedback templates are required"))
    policy_feedback = dict_value(policy.get("feedback_capture"))
    if feedback.get("destination") != policy_feedback.get("destination"):
        errors.append(validation_error("pack.feedback_capture.destination", "feedback destination must match policy"))
    allowed_classifications = set(string_list(policy_feedback.get("allowed_classifications")))
    allowed_severities = set(string_list(policy_feedback.get("allowed_severities")))
    if set(string_list(feedback.get("allowed_classifications"))) != allowed_classifications:
        errors.append(validation_error("pack.feedback_capture.allowed_classifications", "feedback classifications must match policy"))
    if set(string_list(feedback.get("allowed_severities"))) != allowed_severities:
        errors.append(validation_error("pack.feedback_capture.allowed_severities", "feedback severities must match policy"))
    required_feedback_fields = set(string_list(policy_feedback.get("required_record_fields")))
    if set(string_list(feedback.get("required_fields"))) != required_feedback_fields:
        errors.append(validation_error("pack.feedback_capture.required_fields", "feedback required fields must match the Phase 195 contract"))
    for template in templates:
        text = str(template.get("template") or "")
        for field in ("id", "classification", "severity", "template"):
            if not isinstance(template.get(field), str) or not template[field].strip():
                errors.append(validation_error(f"pack.feedback_capture.{template.get('id')}.{field}", f"feedback template {field} is required"))
        if str(template.get("classification") or "") not in allowed_classifications:
            errors.append(validation_error(f"pack.feedback_capture.{template.get('id')}.classification", "feedback template classification must be allowed by policy"))
        if str(template.get("severity") or "") not in allowed_severities:
            errors.append(validation_error(f"pack.feedback_capture.{template.get('id')}.severity", "feedback template severity must be allowed by policy"))
        for marker in string_list(policy.get("required_feedback_template_markers")):
            if marker not in text:
                errors.append(validation_error(f"pack.feedback_capture.{template.get('id')}.template", f"feedback template missing marker: {marker}"))

    if dict_value(pack.get("mutation_safety")).get("source_mutation_allowed") is not False:
        errors.append(validation_error("pack.mutation_safety.source_mutation_allowed", "founder trial pack must be read-only"))
    if "refactor.single_path" not in string_list(dict_value(pack.get("mutation_safety")).get("forbidden_workflows")):
        errors.append(validation_error("pack.mutation_safety.forbidden_workflows", "advanced refactor workflow must be explicitly forbidden"))
    known_limits = string_list(pack.get("known_limits"))
    if not any("Advanced broad refactor" in item for item in known_limits):
        errors.append(validation_error("pack.known_limits.advanced_refactor", "known limits must state advanced broad refactor is not released"))
    if not any("8500/v1" in item for item in known_limits):
        errors.append(validation_error("pack.known_limits.anythingllm_target", "known limits must name the AnythingLLM workflow-router target"))
    fixture_safety = dict_value(pack.get("fixture_safety"))
    integrity_commands = object_list(fixture_safety.get("integrity_commands"))
    required_integrity_markers = string_list(dict_value(policy.get("fixture_safety")).get("required_integrity_commands"))
    integrity_command_text = "\n".join(str(item.get("command") or "") for item in integrity_commands)
    for marker in required_integrity_markers:
        if marker not in integrity_command_text:
            errors.append(validation_error("pack.fixture_safety.integrity_commands", f"missing fixture integrity command: {marker}"))
    non_git_commands = [
        str(item.get("command") or "")
        for item in integrity_commands
        if item.get("target_root") == "/mnt/c/coinbase_testing_repo_frozen_tmp"
    ]
    if not any("before.sha256" in command for command in non_git_commands):
        errors.append(validation_error("pack.fixture_safety.non_git.before", "non-git fixture must have a before hash command"))
    if not any("after.sha256" in command for command in non_git_commands):
        errors.append(validation_error("pack.fixture_safety.non_git.after", "non-git fixture must have an after hash command"))
    if not any(command.strip().startswith("diff -u") for command in non_git_commands):
        errors.append(validation_error("pack.fixture_safety.non_git.diff", "non-git fixture must have a diff command"))
    for index, command in enumerate(integrity_commands):
        for field in ("target_root", "command", "expected_output", "when"):
            if field == "expected_output":
                if not isinstance(command.get(field), str):
                    errors.append(validation_error(f"pack.fixture_safety.integrity_commands[{index}].{field}", f"fixture integrity command {field} is required"))
                continue
            if not isinstance(command.get(field), str) or not command[field].strip():
                errors.append(validation_error(f"pack.fixture_safety.integrity_commands[{index}].{field}", f"fixture integrity command {field} is required"))
    if not string_list(fixture_safety.get("recovery")):
        errors.append(validation_error("pack.fixture_safety.recovery", "fixture recovery instructions are required"))
    recovery = dict_value(pack.get("recovery"))
    for key in string_list(policy.get("required_recovery_keys")):
        if not isinstance(recovery.get(key), str) or not recovery[key].strip():
            errors.append(validation_error(f"pack.recovery.{key}", f"recovery.{key} is required"))

    for doc_path in string_list(policy.get("required_docs")):
        if not resolve_path(config_root, doc_path).is_file():
            errors.append(validation_error("pack.docs", f"required doc is missing: {doc_path}"))
    proof_refs = string_list(pack.get("proof_refs"))
    for proof_ref in string_list(policy.get("required_proof_refs")):
        if proof_ref not in proof_refs:
            errors.append(validation_error("pack.proof_refs", f"required proof ref is missing: {proof_ref}"))
            continue
        if require_proof_artifacts:
            proof_path = resolve_path(config_root, proof_ref)
            if not proof_path.is_file():
                errors.append(validation_error("pack.proof_refs.artifact", f"required proof artifact is missing: {proof_ref}"))
                continue
            try:
                proof_report = read_json_object(proof_path)
            except (OSError, json.JSONDecodeError, RuntimeError) as exc:
                errors.append(validation_error("pack.proof_refs.artifact_json", f"required proof artifact is not valid JSON: {proof_ref}: {exc}"))
                continue
            expected_phase = expected_phase_from_path(proof_ref)
            if expected_phase is not None and proof_report.get("phase") != expected_phase:
                errors.append(validation_error("pack.proof_refs.artifact_phase", f"proof artifact phase mismatch for {proof_ref}"))
            if proof_report.get("status") != "passed":
                errors.append(validation_error("pack.proof_refs.artifact_status", f"proof artifact must have status=passed: {proof_ref}"))
            if not isinstance(proof_report.get("kind"), str) or not proof_report["kind"].strip():
                errors.append(validation_error("pack.proof_refs.artifact_kind", f"proof artifact must include kind: {proof_ref}"))
            validation_error_count = dict_value(proof_report.get("summary")).get("validation_error_count")
            if isinstance(validation_error_count, int) and validation_error_count != 0:
                errors.append(validation_error("pack.proof_refs.artifact_validation_errors", f"proof artifact has validation errors: {proof_ref}"))
    return errors


def validate_feedback_records(config_root: Path, policy: dict[str, Any], pack: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    feedback = dict_value(pack.get("feedback_capture"))
    policy_feedback = dict_value(policy.get("feedback_capture"))
    feedback_path = resolve_path(config_root, str(feedback.get("destination") or ""))
    required_fields = string_list(policy_feedback.get("required_record_fields"))
    allowed_classifications = set(string_list(policy_feedback.get("allowed_classifications")))
    allowed_severities = set(string_list(policy_feedback.get("allowed_severities")))
    summary: dict[str, Any] = {
        "path": str(feedback_path),
        "present": feedback_path.is_file(),
        "record_count": 0,
        "validated": False,
    }
    if not feedback_path.exists():
        return summary, errors
    if not feedback_path.is_file():
        errors.append(validation_error("feedback_records.path", "feedback destination exists but is not a file"))
        return summary, errors
    for line_number, line in enumerate(feedback_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        summary["record_count"] += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(validation_error("feedback_records.json", f"feedback line {line_number} is not valid JSON: {exc}"))
            continue
        if not isinstance(record, dict):
            errors.append(validation_error("feedback_records.object", f"feedback line {line_number} must be a JSON object"))
            continue
        for field in required_fields:
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append(validation_error("feedback_records.required_fields", f"feedback line {line_number} missing field: {field}"))
        if record.get("classification") not in allowed_classifications:
            errors.append(validation_error("feedback_records.classification", f"feedback line {line_number} has unsupported classification"))
        if record.get("severity") not in allowed_severities:
            errors.append(validation_error("feedback_records.severity", f"feedback line {line_number} has unsupported severity"))
        if isinstance(record.get("target_run_id"), str) and not record["target_run_id"].startswith("workflow-router-"):
            errors.append(validation_error("feedback_records.target_run_id", f"feedback line {line_number} target_run_id must start with workflow-router-"))
    summary["validated"] = not errors
    return summary, errors


def validate_live_fixture_state(pack: dict[str, Any], enabled: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    summary: dict[str, Any] = {"validated": enabled, "roots": []}
    if not enabled:
        return summary, errors
    for root_value in string_list(pack.get("target_roots")):
        root = Path(root_value)
        root_summary: dict[str, Any] = {"root": root_value, "exists": root.exists()}
        summary["roots"].append(root_summary)
        if not root.exists() or not root.is_dir():
            errors.append(validation_error("fixture_state.root", f"fixture root is missing or not a directory: {root_value}"))
            continue
        if (root / ".git").exists():
            result = subprocess.run(
                ["git", "-C", str(root), "status", "--short"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            root_summary["git_status_exit_code"] = result.returncode
            root_summary["git_status_line_count"] = len([line for line in result.stdout.splitlines() if line.strip()])
            root_summary["git_status_sample"] = result.stdout.splitlines()[:10]
            if result.returncode != 0:
                errors.append(validation_error("fixture_state.git_status", f"git status failed for fixture root {root_value}: {result.stderr.strip()}"))
            if result.stdout.strip():
                errors.append(validation_error("fixture_state.git_dirty", f"git fixture root has uncommitted changes: {root_value}"))
        else:
            root_summary.update(directory_fingerprint(root))
    return summary, errors


def selected_case_summaries(catalog: dict[str, Any], case_ids: list[str]) -> list[dict[str, Any]]:
    by_id = catalog_cases(catalog)
    summaries: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = by_id.get(case_id)
        if not case:
            continue
        summaries.append(
            {
                "case_id": case_id,
                "prompt": case.get("prompt"),
                "refined_prompt": case.get("refined_prompt") or "",
                "expected_workflow": case.get("expected_workflow"),
                "target_root": case.get("target_root"),
                "expected_rule": case.get("expected_rule"),
                "expected_markers": case.get("expected_markers"),
                "semantic_markers": case.get("semantic_markers"),
                "baseline_target": case.get("baseline_target"),
            }
        )
    return summaries


def source_artifacts(
    *,
    policy_path: Path,
    pack_path: Path,
    prompt_pack_path: Path,
    catalog_path: Path,
) -> list[dict[str, Any]]:
    return [
        {"source_key": "policy", "path": str(policy_path.resolve()), "sha256": artifact_hash(policy_path)},
        {"source_key": "pack", "path": str(pack_path.resolve()), "sha256": artifact_hash(pack_path)},
        {"source_key": "founder_test_prompt_pack", "path": str(prompt_pack_path.resolve()), "sha256": artifact_hash(prompt_pack_path)},
        {"source_key": "prompt_catalog", "path": str(catalog_path.resolve()), "sha256": artifact_hash(catalog_path)},
    ]


def build_founder_trial_pack_report(config: FounderTrialPackConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    pack_path = resolve_path(config_root, config.pack_path)
    policy = read_json_object(policy_path)
    pack = read_json_object(pack_path)
    prompt_pack, catalog, prompt_pack_path, catalog_path = load_prompt_sources(config_root, pack)
    errors = validate_policy(policy)
    errors.extend(
        validate_pack(
            config_root=config_root,
            policy=policy,
            pack=pack,
            prompt_pack=prompt_pack,
            catalog=catalog,
            require_proof_artifacts=config.require_proof_artifacts,
        )
    )
    feedback_record_summary, feedback_record_errors = validate_feedback_records(config_root, policy, pack)
    errors.extend(feedback_record_errors)
    fixture_state_summary, fixture_state_errors = validate_live_fixture_state(pack, config.validate_fixture_state)
    errors.extend(fixture_state_errors)
    case_ids_by_stage = stage_case_ids(pack)
    selected_case_ids = [case_id for ids in case_ids_by_stage.values() for case_id in ids]
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderTrialPackStatus.FAILED.value if errors else FounderTrialPackStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "pack_status": pack.get("status"),
        "anythingllm": pack.get("anythingllm"),
        "target_roots": pack.get("target_roots"),
        "stage_ids": [stage.get("id") for stage in object_list(pack.get("trial_stages"))],
        "case_ids_by_stage": case_ids_by_stage,
        "selected_case_summaries": selected_case_summaries(catalog, selected_case_ids),
        "proof_artifact_mode": {
            "required_for_release": policy.get("proof_artifact_mode_required_for_release"),
            "enabled_for_this_run": config.require_proof_artifacts,
        },
        "fixture_state": fixture_state_summary,
        "known_limits": pack.get("known_limits"),
        "setup_commands": [
            {
                "command": command.get("command"),
                "expected_marker": command.get("expected_marker"),
                "failure_recovery": command.get("failure_recovery"),
            }
            for stage in object_list(pack.get("trial_stages"))
            if stage.get("id") == "setup-readiness"
            for command in object_list(stage.get("commands"))
        ],
        "fixture_safety": pack.get("fixture_safety"),
        "feedback_capture": pack.get("feedback_capture"),
        "feedback_records": feedback_record_summary,
        "recovery": pack.get("recovery"),
        "feedback_template_ids": [template.get("id") for template in object_list(dict_value(pack.get("feedback_capture")).get("templates"))],
        "source_artifacts": source_artifacts(
            policy_path=policy_path,
            pack_path=pack_path,
            prompt_pack_path=prompt_pack_path,
            catalog_path=catalog_path,
        ),
        "validation_errors": errors,
        "summary": {
            "stage_count": len(object_list(pack.get("trial_stages"))),
            "prompt_case_count": len(selected_case_ids),
            "smoke_case_count": len(case_ids_by_stage.get("founder-smoke", [])),
            "expanded_case_count": len(case_ids_by_stage.get("expanded-read-only", [])),
            "target_root_count": len(set(str(case.get("target_root")) for case in selected_case_summaries(catalog, selected_case_ids))),
            "feedback_template_count": len(object_list(dict_value(pack.get("feedback_capture")).get("templates"))),
            "known_limit_count": len(string_list(pack.get("known_limits"))),
            "proof_ref_count": len(string_list(pack.get("proof_refs"))),
            "validation_error_count": len(errors),
            "next_action": "work Phase 196 next" if not errors else "fix Phase 195 founder trial pack",
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 195 Release Candidate Founder Trial Pack Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Prompt cases: `{summary.get('prompt_case_count')}`",
        f"- Smoke cases: `{summary.get('smoke_case_count')}`",
        f"- Expanded cases: `{summary.get('expanded_case_count')}`",
        f"- Target roots: `{summary.get('target_root_count')}`",
        f"- Feedback templates: `{summary.get('feedback_template_count')}`",
        f"- Validation errors: `{summary.get('validation_error_count')}`",
        f"- Next action: `{summary.get('next_action')}`",
        "",
        "## Prompt Cases",
        "",
    ]
    for case in object_list(report.get("selected_case_summaries")):
        lines.append(f"- `{case.get('case_id')}`: `{case.get('expected_workflow')}` on `{case.get('target_root')}`")
        lines.append(f"  - Prompt: {case.get('prompt')}")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors", ""])
        for error in errors:
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    return "\n".join(lines) + "\n"


def run_founder_trial_pack(config: FounderTrialPackConfig) -> dict[str, Any]:
    report = build_founder_trial_pack_report(config)
    output_path = resolve_path(config.config_root, config.output_path)
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        write_text(resolve_path(config.config_root, config.markdown_output_path), render_markdown(report))
    return report
