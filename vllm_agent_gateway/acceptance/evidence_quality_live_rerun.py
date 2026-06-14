"""Evidence-quality live rerun gate for Phase 208."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    artifact_json,
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    run_id_from_text,
    text_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "evidence_quality_live_rerun_policy"
EXPECTED_REPORT_KIND = "evidence_quality_live_rerun_report"
EXPECTED_PHASE = 208
EXPECTED_BACKLOG_ID = "P0-M4-208"
EXPECTED_MILESTONE_ID = "M4"
DEFAULT_POLICY_PATH = Path("runtime") / "evidence_quality_live_rerun_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase208" / "phase208-evidence-quality-live-rerun-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase208" / "phase208-evidence-quality-live-rerun-report.md"
DEFAULT_PREFLIGHT_OUTPUT_PATH = (
    Path("runtime-state") / "phase208" / "phase208-evidence-quality-live-rerun-preflight-report.json"
)
DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "phase208" / "phase208-evidence-quality-live-rerun-preflight-report.md"
)


class EvidenceQualityLiveStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PREFLIGHT_PASSED = "preflight_passed"


class EvidenceQualitySurface(str, Enum):
    GATEWAY = "gateway"
    ANYTHINGLLM = "anythingllm"


@dataclass(frozen=True)
class EvidenceQualityLiveRerunConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    include_gateway: bool = True
    include_anythingllm: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900
    case_ids: tuple[str, ...] = ()
    target_roots: tuple[str, ...] = ()
    allow_partial: bool = False
    live: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def default_output_path(*, live: bool) -> Path:
    return DEFAULT_OUTPUT_PATH if live else DEFAULT_PREFLIGHT_OUTPUT_PATH


def default_markdown_output_path(*, live: bool) -> Path:
    return DEFAULT_MARKDOWN_OUTPUT_PATH if live else DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH


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


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def bool_value(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 208")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(policy.get("policy_version") or "")):
        errors.append("policy.policy_version must use semantic version x.y.z")
    purpose = str(policy.get("purpose") or "").lower()
    for phrase in ("workflow-router gateway", "anythingllm", "phase 207 source proofs"):
        if phrase not in purpose:
            errors.append(f"policy.purpose must mention {phrase!r}")
    for key in ("phase206_audit_pack_report_path", "phase207_source_hash_gate_report_path"):
        if not isinstance(policy.get(key), str) or not str(policy[key]).strip():
            errors.append(f"policy.{key} must be a non-empty string")
    if set(string_list(policy.get("required_surfaces"))) != {
        EvidenceQualitySurface.GATEWAY.value,
        EvidenceQualitySurface.ANYTHINGLLM.value,
    }:
        errors.append("policy.required_surfaces must be gateway and anythingllm")
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append("policy.required_target_roots must include both frozen Coinbase fixture roots")
    if policy.get("mirror_phase206_prompts_to_required_roots") is not True:
        errors.append("policy.mirror_phase206_prompts_to_required_roots must be true")
    if int_value(policy.get("minimum_audit_case_count"), 0) < 4:
        errors.append("policy.minimum_audit_case_count must be at least 4")
    if int_value(policy.get("minimum_holdout_case_count"), 0) < 4:
        errors.append("policy.minimum_holdout_case_count must be at least 4")
    if int_value(policy.get("minimum_live_response_count"), 0) < 32:
        errors.append("policy.minimum_live_response_count must be at least 32")
    if int_value(policy.get("minimum_response_score"), 0) < 80:
        errors.append("policy.minimum_response_score must be at least 80")
    if int_value(policy.get("minimum_baseline_score"), 0) < 80:
        errors.append("policy.minimum_baseline_score must be at least 80")
    if policy.get("source_hash_revalidation_required") is not True:
        errors.append("policy.source_hash_revalidation_required must be true")
    phase207_source_root = policy.get("phase207_source_root")
    if not isinstance(phase207_source_root, str) or phase207_source_root not in string_list(policy.get("required_target_roots")):
        errors.append("policy.phase207_source_root must be one of policy.required_target_roots")
    if policy.get("mirrored_root_line_hash_revalidation_required") is not True:
        errors.append("policy.mirrored_root_line_hash_revalidation_required must be true")
    if policy.get("target_root_artifact_proof_required") is not True:
        errors.append("policy.target_root_artifact_proof_required must be true")
    for marker in ("Answer:", "Skill Selection:", "Context Sources:", "Source mutation: false"):
        if marker not in string_list(policy.get("required_chat_markers")):
            errors.append(f"policy.required_chat_markers must include {marker!r}")
    summary = dict_value(policy.get("required_summary"))
    if summary.get("selected_workflow") != "code_investigation.plan":
        errors.append("policy.required_summary.selected_workflow must be code_investigation.plan")
    if summary.get("downstream_status") != "completed":
        errors.append("policy.required_summary.downstream_status must be completed")
    if summary.get("source_changed") is not False:
        errors.append("policy.required_summary.source_changed must be false")
    requirements = object_list(policy.get("case_requirements"))
    if len(requirements) < int_value(policy.get("minimum_audit_case_count"), 4):
        errors.append("policy.case_requirements must cover each Phase 206 audit case")
    seen: set[str] = set()
    for requirement in requirements:
        case_id = requirement.get("audit_case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append("policy.case_requirements[].audit_case_id must be non-empty")
            continue
        if case_id in seen:
            errors.append(f"policy.case_requirements duplicates {case_id}")
        seen.add(case_id)
        if not isinstance(requirement.get("route_rule"), str) or not requirement["route_rule"]:
            errors.append(f"policy.case_requirements[{case_id}].route_rule must be non-empty")
        if not string_list(requirement.get("required_markers")):
            errors.append(f"policy.case_requirements[{case_id}].required_markers must be non-empty")
        if int_value(requirement.get("minimum_expected_source_ref_hits"), 0) < 1:
            errors.append(f"policy.case_requirements[{case_id}].minimum_expected_source_ref_hits must be at least 1")
    holdouts = object_list(policy.get("holdout_cases"))
    if len(holdouts) < int_value(policy.get("minimum_holdout_case_count"), 4):
        errors.append("policy.holdout_cases must satisfy policy.minimum_holdout_case_count")
    holdout_ids: set[str] = set()
    requirement_ids = {str(item.get("audit_case_id")) for item in requirements if isinstance(item.get("audit_case_id"), str)}
    for holdout in holdouts:
        holdout_id = holdout.get("holdout_case_id")
        audit_case_id = holdout.get("audit_case_id")
        if not isinstance(holdout_id, str) or not holdout_id:
            errors.append("policy.holdout_cases[].holdout_case_id must be non-empty")
            continue
        if holdout_id in holdout_ids:
            errors.append(f"policy.holdout_cases duplicates {holdout_id}")
        holdout_ids.add(holdout_id)
        if not isinstance(audit_case_id, str) or audit_case_id not in requirement_ids:
            errors.append(f"policy.holdout_cases[{holdout_id}].audit_case_id must reference a case requirement")
        if not isinstance(holdout.get("route_rule"), str) or not holdout["route_rule"]:
            errors.append(f"policy.holdout_cases[{holdout_id}].route_rule must be non-empty")
        prompt_template = holdout.get("prompt_template")
        if not isinstance(prompt_template, str) or "{target_root}" not in prompt_template:
            errors.append(f"policy.holdout_cases[{holdout_id}].prompt_template must include {{target_root}}")
    return errors


def validate_source_reports(config_root: Path, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    phase206_path = resolve_path(config_root, str(policy.get("phase206_audit_pack_report_path", "")))
    phase207_path = resolve_path(config_root, str(policy.get("phase207_source_hash_gate_report_path", "")))
    if not phase206_path.is_file():
        errors.append(f"Phase 206 audit-pack report missing at {phase206_path}")
    else:
        phase206 = read_json_object(phase206_path)
        if phase206.get("status") != "passed":
            errors.append("Phase 206 audit-pack report status must be passed")
        if phase206.get("phase") != 206:
            errors.append("Phase 206 audit-pack report phase must be 206")
        if dict_value(phase206.get("summary")).get("phase207_ready") is not True:
            errors.append("Phase 206 audit-pack report must have summary.phase207_ready=true")
        if len(object_list(phase206.get("audit_cases"))) < int_value(policy.get("minimum_audit_case_count"), 4):
            errors.append("Phase 206 audit-pack report does not contain enough audit cases")
        if object_list(phase206.get("errors")) or string_list(phase206.get("errors")):
            errors.append("Phase 206 audit-pack report must not contain errors")
    if not phase207_path.is_file():
        errors.append(f"Phase 207 source-hash report missing at {phase207_path}")
    else:
        phase207 = read_json_object(phase207_path)
        if phase207.get("status") != "passed":
            errors.append("Phase 207 source-hash report status must be passed")
        if phase207.get("phase") != 207:
            errors.append("Phase 207 source-hash report phase must be 207")
        summary = dict_value(phase207.get("summary"))
        if summary.get("phase208_ready") is not True:
            errors.append("Phase 207 source-hash report must have summary.phase208_ready=true")
        if int_value(summary.get("source_hash_count"), 0) < 4:
            errors.append("Phase 207 source-hash report source_hash_count must be at least 4")
        if int_value(summary.get("negative_control_count"), 0) < 3:
            errors.append("Phase 207 source-hash report negative_control_count must be at least 3")
        if object_list(phase207.get("errors")) or string_list(phase207.get("errors")):
            errors.append("Phase 207 source-hash report must not contain errors")
    return errors


def phase206_cases(config_root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    report = read_json_object(resolve_path(config_root, str(policy["phase206_audit_pack_report_path"])))
    return object_list(report.get("audit_cases"))


def phase207_cases_by_audit_id(config_root: Path, policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    report = read_json_object(resolve_path(config_root, str(policy["phase207_source_hash_gate_report_path"])))
    by_id: dict[str, dict[str, Any]] = {}
    for case in object_list(report.get("cases")):
        audit_case_id = case.get("audit_case_id")
        if isinstance(audit_case_id, str):
            by_id[audit_case_id] = case
    return by_id


def case_requirements_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("audit_case_id")): item
        for item in object_list(policy.get("case_requirements"))
        if isinstance(item.get("audit_case_id"), str)
    }


def baseline_case_id(case: dict[str, Any]) -> str:
    value = case.get("audit_case_id") or case.get("case_id")
    return str(value or "")


def live_case_id(case: dict[str, Any]) -> str:
    value = case.get("holdout_case_id") or case.get("case_id") or case.get("audit_case_id")
    return str(value or "")


def live_case_prompt_family(case: dict[str, Any], baseline_cases_by_id: dict[str, dict[str, Any]]) -> str:
    value = case.get("prompt_family")
    if isinstance(value, str) and value:
        return value
    baseline = baseline_cases_by_id.get(baseline_case_id(case), {})
    return str(baseline.get("prompt_family") or "")


def selected_live_cases(
    audit_cases: list[dict[str, Any]],
    policy: dict[str, Any],
    config: EvidenceQualityLiveRerunConfig,
) -> list[dict[str, Any]]:
    cases = list(audit_cases)
    cases.extend(object_list(policy.get("holdout_cases")))
    if not config.case_ids:
        return cases
    wanted = set(config.case_ids)
    return [
        case
        for case in cases
        if live_case_id(case) in wanted or (not case.get("holdout_case_id") and baseline_case_id(case) in wanted)
    ]


def target_roots(policy: dict[str, Any], config: EvidenceQualityLiveRerunConfig) -> list[str]:
    roots = list(config.target_roots) if config.target_roots else string_list(policy.get("required_target_roots"))
    return roots


def surfaces(config: EvidenceQualityLiveRerunConfig) -> list[EvidenceQualitySurface]:
    selected: list[EvidenceQualitySurface] = []
    if config.include_gateway:
        selected.append(EvidenceQualitySurface.GATEWAY)
    if config.include_anythingllm:
        selected.append(EvidenceQualitySurface.ANYTHINGLLM)
    return selected


def prompt_for_root(case: dict[str, Any], target_root: str) -> str:
    prompt_template = case.get("prompt_template")
    if isinstance(prompt_template, str) and prompt_template:
        return prompt_template.replace("{target_root}", target_root)
    prompt = str(case.get("prompt") or "")
    source_root = str(case.get("target_root") or "")
    if source_root and source_root in prompt:
        return prompt.replace(source_root, target_root)
    return f"In {target_root}, {prompt}"


def source_proofs_for_case(phase207_by_id: dict[str, dict[str, Any]], audit_case_id: str) -> list[dict[str, Any]]:
    return object_list(phase207_by_id.get(audit_case_id, {}).get("source_proofs"))


def proof_label(proof: dict[str, Any]) -> str:
    path = proof.get("path")
    line = proof.get("line")
    if isinstance(path, str) and isinstance(line, int):
        return f"{path}:{line}"
    return str(path or "")


def proof_labels(proofs: list[dict[str, Any]]) -> list[str]:
    return [label for label in (proof_label(proof) for proof in proofs) if label]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_line_text(path: Path, line_number: int) -> str | None:
    if line_number < 1:
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_number > len(lines):
        return None
    return lines[line_number - 1]


def source_hash_revalidation(
    *,
    policy: dict[str, Any],
    target_root: str,
    proofs: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    revalidated_count = 0
    root = Path(target_root)
    require_file_hash = target_root == str(policy.get("phase207_source_root"))
    for proof in proofs:
        path = proof.get("path")
        line = proof.get("line")
        query = proof.get("query")
        if not isinstance(path, str) or not isinstance(line, int):
            errors.append("source proof must include path and integer line")
            continue
        target_path = root / path
        if not target_path.is_file():
            errors.append(f"source proof target missing at {target_path}")
            continue
        expected_sha = proof.get("sha256")
        if not isinstance(expected_sha, str) or not expected_sha:
            errors.append(f"source proof sha256 missing for {path}")
        elif file_sha256(target_path) != expected_sha:
            if require_file_hash:
                errors.append(f"source proof file hash mismatch for {path}")
            else:
                warnings.append(f"mirrored root file hash differs for {path}; line hash was still checked")
        line_text = source_line_text(target_path, line)
        if line_text is None:
            errors.append(f"source proof line missing for {path}:{line}")
            continue
        expected_line_sha = proof.get("line_sha256")
        if not isinstance(expected_line_sha, str) or not expected_line_sha:
            errors.append(f"source proof line_sha256 missing for {path}:{line}")
            continue
        if text_sha256(line_text) != expected_line_sha:
            errors.append(f"source proof line hash mismatch for {path}:{line}")
            continue
        if not isinstance(query, str) or not query:
            errors.append(f"source proof query missing for {path}:{line}")
            continue
        if query not in line_text:
            errors.append(f"source proof query {query!r} missing from {path}:{line}")
            continue
        revalidated_count += 1
    return {
        "errors": errors,
        "warnings": warnings,
        "revalidated_count": revalidated_count,
        "file_hash_required": require_file_hash,
    }


def artifact_from_record(record: dict[str, Any], key: str) -> dict[str, Any] | None:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    if key not in artifacts:
        return None
    try:
        return artifact_json(record, key)
    except Exception:
        return None


def loaded_artifacts(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    for key in artifacts:
        if not isinstance(key, str):
            continue
        artifact = artifact_from_record(record, key)
        if artifact is not None:
            values[key] = artifact
    return values


def artifact_source_ref_labels(artifacts: dict[str, dict[str, Any]]) -> set[str]:
    labels: set[str] = set()
    for artifact in artifacts.values():
        refs = object_list(artifact.get("source_refs"))
        for ref in refs:
            path = ref.get("path")
            line = ref.get("line")
            if isinstance(path, str) and isinstance(line, int):
                labels.add(f"{path}:{line}")
            elif isinstance(path, str):
                labels.add(path)
    return labels


def route_rules_from_decision(route_decision: dict[str, Any]) -> set[str]:
    rules: set[str] = set()
    for item in object_list(route_decision.get("evidence")):
        rule = item.get("rule")
        if isinstance(rule, str):
            rules.add(rule)
    selected = dict_value(route_decision.get("selection_audit")).get("selected")
    for rule in string_list(dict_value(selected).get("route_rules")):
        rules.add(rule)
    return rules


def target_root_proof_errors(
    *,
    run_record: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    target_root: str,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    proofs: list[str] = []
    summary = dict_value(run_record.get("summary"))
    if summary.get("target_root") == target_root:
        proofs.append("run_record.summary.target_root")
    elif isinstance(summary.get("target_root"), str):
        errors.append(f"run_record.summary.target_root must be {target_root}")
    for key, artifact in artifacts.items():
        artifact_root = artifact.get("target_root")
        if artifact_root == target_root:
            proofs.append(f"{key}.target_root")
        elif isinstance(artifact_root, str) and artifact_root:
            errors.append(f"{key}.target_root must be {target_root}")
        artifact_summary = dict_value(artifact.get("summary"))
        if artifact_summary.get("target_root") == target_root:
            proofs.append(f"{key}.summary.target_root")
        elif isinstance(artifact_summary.get("target_root"), str):
            errors.append(f"{key}.summary.target_root must be {target_root}")
        report_summary = dict_value(dict_value(artifact.get("report")).get("summary"))
        if report_summary.get("target_root") == target_root:
            proofs.append(f"{key}.report.summary.target_root")
        elif isinstance(report_summary.get("target_root"), str):
            errors.append(f"{key}.report.summary.target_root must be {target_root}")
        request_text = artifact.get("user_request")
        if isinstance(request_text, str) and target_root in request_text:
            proofs.append(f"{key}.user_request")
    if not proofs:
        errors.append("controller artifacts did not prove the requested target_root was used")
    return errors, proofs


def dimension_result(dimension: str, text: str, *, visible_hits: list[str], artifact_hits: list[str]) -> tuple[bool, str]:
    has = text.__contains__
    if dimension == "beginning_point_or_target_fit":
        passed = any(has(marker) for marker in ("Beginning point:", "Target:", "Files to touch:", "Related tests:", "Smallest command:"))
        return passed, "answer names the requested target or beginning point"
    if dimension == "call_chain_or_behavior_link":
        passed = any(
            has(marker)
            for marker in (
                "Beginning point:",
                "Evidence files:",
                "Participating files:",
                "Callers/usages:",
                "Rationale:",
                "Related tests:",
                "Files to touch:",
            )
        )
        return passed, "answer links the behavior to bounded files, tests, or rationale"
    if dimension == "source_specificity":
        passed = has("Source refs:") and bool(visible_hits)
        return passed, "answer exposes path:line source refs matching Phase 207 proof"
    if dimension == "directness":
        passed = bool(visible_hits or artifact_hits)
        return passed, "answer or artifacts cite direct Phase 207 source proof"
    if dimension == "test_or_validation_fit":
        passed = any(has(marker) for marker in ("Related tests:", "Recommended commands:", "Smallest command:", "Verification:"))
        return passed, "answer includes related tests or validation commands"
    if dimension == "gap_and_risk_labeling":
        passed = any(has(marker) for marker in ("Gaps:", "Risks:", "Risk level:", "Covered risks:", "Confidence:"))
        return passed, "answer labels confidence, gaps, risks, or remaining risk"
    if dimension == "relevance_ordering":
        if all(has(marker) for marker in ("Smallest command:", "Medium command:", "Broad command:")):
            passed = text.index("Smallest command:") < text.index("Medium command:") < text.index("Broad command:")
            return passed, "validation commands are ordered smallest to broad"
        passed = has("Source refs:") and (has("Related tests:") or bool(visible_hits))
        return passed, "answer presents direct source/test evidence before broad artifact review"
    if dimension == "chat_usefulness":
        passed = has("Answer:") and has("Source mutation: false")
        return passed, "answer is chat-visible and includes safety boundary"
    passed = bool(visible_hits)
    return passed, "fallback dimension check requires visible source-proof evidence"


def baseline_comparison(
    *,
    policy: dict[str, Any],
    baseline_case: dict[str, Any],
    text: str,
    visible_hits: list[str],
    artifact_hits: list[str],
) -> dict[str, Any]:
    baseline = dict_value(baseline_case.get("blind_baseline"))
    rubric = object_list(baseline.get("scoring_rubric"))
    total_points = 0
    passed_points = 0
    dimensions: list[dict[str, Any]] = []
    for item in rubric:
        dimension = str(item.get("dimension") or "")
        points = int_value(item.get("points"), 0)
        if not dimension or points <= 0:
            continue
        total_points += points
        passed, evidence = dimension_result(dimension, text, visible_hits=visible_hits, artifact_hits=artifact_hits)
        if passed:
            passed_points += points
        dimensions.append(
            {
                "dimension": dimension,
                "points": points,
                "status": "passed" if passed else "failed",
                "evidence": evidence,
            }
        )
    score = int(round((passed_points / total_points) * 100)) if total_points else 0
    errors: list[str] = []
    if score < int_value(policy.get("minimum_baseline_score"), 80):
        errors.append(f"blind baseline dimension score {score} below policy.minimum_baseline_score")
    return {
        "score": score,
        "passed_points": passed_points,
        "total_points": total_points,
        "dimensions": dimensions,
        "errors": errors,
        "ideal_answer_shape_count": len(string_list(baseline.get("ideal_answer_shape"))),
        "must_have_evidence_count": len(string_list(baseline.get("must_have_evidence"))),
    }


def validate_live_response(
    *,
    policy: dict[str, Any],
    audit_case: dict[str, Any],
    baseline_case: dict[str, Any],
    requirement: dict[str, Any],
    phase207_by_id: dict[str, dict[str, Any]],
    surface: str,
    target_root: str,
    text: str,
    run_record: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    score = 100
    summary = dict_value(run_record.get("summary"))
    required_summary = dict_value(policy.get("required_summary"))
    if run_record.get("status") != "completed":
        errors.append("controller run status must be completed")
        score -= 20
    for key, expected in required_summary.items():
        if summary.get(key) != expected:
            errors.append(f"summary.{key} must be {expected!r}")
            score -= 10
    route_decision = artifact_from_record(run_record, "route_decision") or {}
    if route_decision.get("selected_workflow") != "code_investigation.plan":
        errors.append("route_decision.selected_workflow must be code_investigation.plan")
        score -= 20
    route_rule = str(audit_case.get("route_rule") or requirement.get("route_rule") or "")
    route_rules = route_rules_from_decision(route_decision)
    if route_rule and route_rule not in route_rules:
        errors.append(f"route decision missing expected rule {route_rule}")
        score -= 15
    for marker in string_list(policy.get("required_chat_markers")):
        if marker not in text:
            errors.append(f"chat text missing global marker {marker!r}")
            score -= 8
    for marker in string_list(requirement.get("required_markers")):
        if marker not in text:
            errors.append(f"chat text missing case marker {marker!r}")
            score -= 8
    artifacts = loaded_artifacts(run_record)
    baseline_id = baseline_case_id(baseline_case)
    source_proofs = source_proofs_for_case(phase207_by_id, baseline_id)
    expected_labels = proof_labels(source_proofs)
    visible_hits = [label for label in expected_labels if label in text]
    minimum_hits = int_value(requirement.get("minimum_expected_source_ref_hits"), 1)
    if len(visible_hits) < minimum_hits:
        errors.append(f"chat text did not expose at least {minimum_hits} Phase 207 source proof ref(s)")
        score -= 18
    artifact_labels = artifact_source_ref_labels(artifacts)
    artifact_hits = sorted(label for label in expected_labels if label in artifact_labels)
    if not artifact_hits:
        warnings.append("no artifact source_refs matched Phase 207 source proofs")
        score -= 5
    source_hash_result = source_hash_revalidation(policy=policy, target_root=target_root, proofs=source_proofs)
    source_hash_errors = string_list(source_hash_result.get("errors"))
    if source_hash_errors:
        errors.extend(source_hash_errors)
        score -= 20
    source_hash_warnings = string_list(source_hash_result.get("warnings"))
    if source_hash_warnings:
        warnings.extend(source_hash_warnings)
    target_root_errors, target_root_proofs = target_root_proof_errors(
        run_record=run_record,
        artifacts=artifacts,
        target_root=target_root,
    )
    if target_root_errors:
        errors.extend(target_root_errors)
        score -= 15
    baseline = baseline_comparison(
        policy=policy,
        baseline_case=baseline_case,
        text=text,
        visible_hits=visible_hits,
        artifact_hits=artifact_hits,
    )
    if baseline["errors"]:
        errors.extend(baseline["errors"])
        score -= 15
    if "source_changed" in summary and summary.get("source_changed") is not False:
        errors.append("summary.source_changed must remain false")
        score -= 15
    if run_record.get("failure_count") not in (None, 0):
        errors.append("controller run failure_count must be zero")
        score -= 15
    score = max(0, score)
    return {
        "surface": surface,
        "target_root": target_root,
        "audit_case_id": baseline_id,
        "live_case_id": live_case_id(audit_case),
        "case_type": "holdout" if audit_case.get("holdout_case_id") else "audit",
        "prompt_family": baseline_case.get("prompt_family"),
        "run_id": run_id,
        "status": "passed" if not errors and score >= int_value(policy.get("minimum_response_score"), 85) else "failed",
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "route_rules": sorted(route_rules),
        "visible_source_ref_hits": visible_hits,
        "artifact_source_ref_hits": artifact_hits,
        "expected_source_refs": expected_labels,
        "target_root_proofs": sorted(set(target_root_proofs)),
        "source_hash_revalidated_count": int_value(source_hash_result.get("revalidated_count"), 0),
        "source_hash_file_required": bool_value(source_hash_result.get("file_hash_required"), False),
        "baseline_comparison": baseline,
        "chat_excerpt": text[:1200],
    }


def gateway_live_response(
    config: EvidenceQualityLiveRerunConfig,
    *,
    audit_case: dict[str, Any],
    target_root: str,
) -> tuple[str, dict[str, Any], str]:
    prompt = prompt_for_root(audit_case, target_root)
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    run_id = str(compact.get("run_id") or run_id_from_text(text))
    if run_id == "unknown":
        raise RuntimeError("gateway response did not include a workflow-router run_id")
    return text, controller_run_record(config, run_id), run_id


def anythingllm_live_response(
    config: EvidenceQualityLiveRerunConfig,
    *,
    audit_case: dict[str, Any],
    target_root: str,
    api_key: str,
) -> tuple[str, dict[str, Any], str]:
    prompt = prompt_for_root(audit_case, target_root)
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": prompt,
            "mode": "chat",
            "sessionId": f"phase208-evidence-{str(audit_case.get('case_id')).lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("AnythingLLM response did not include a workflow-router run_id")
    return text, controller_run_record(config, run_id), run_id


def run_live_case(
    config: EvidenceQualityLiveRerunConfig,
    *,
    policy: dict[str, Any],
    audit_case: dict[str, Any],
    baseline_case: dict[str, Any],
    requirement: dict[str, Any],
    phase207_by_id: dict[str, dict[str, Any]],
    surface: EvidenceQualitySurface,
    target_root: str,
    api_key: str | None,
) -> dict[str, Any]:
    before = fixture_state(target_root)
    try:
        if surface == EvidenceQualitySurface.GATEWAY:
            text, record, run_id = gateway_live_response(config, audit_case=audit_case, target_root=target_root)
        elif surface == EvidenceQualitySurface.ANYTHINGLLM:
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM live validation")
            text, record, run_id = anythingllm_live_response(
                config,
                audit_case=audit_case,
                target_root=target_root,
                api_key=api_key,
            )
        else:
            raise RuntimeError(f"unsupported surface {surface}")
        result = validate_live_response(
            policy=policy,
            audit_case=audit_case,
            baseline_case=baseline_case,
            requirement=requirement,
            phase207_by_id=phase207_by_id,
            surface=surface.value,
            target_root=target_root,
            text=text,
            run_record=record,
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 - acceptance reports classify all failures
        result = {
            "surface": surface.value,
            "target_root": target_root,
            "audit_case_id": baseline_case_id(baseline_case),
            "live_case_id": live_case_id(audit_case),
            "case_type": "holdout" if audit_case.get("holdout_case_id") else "audit",
            "prompt_family": baseline_case.get("prompt_family"),
            "run_id": "unknown",
            "status": "failed",
            "score": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "warnings": [],
            "route_rules": [],
            "visible_source_ref_hits": [],
            "artifact_source_ref_hits": [],
            "expected_source_refs": proof_labels(
                source_proofs_for_case(phase207_by_id, baseline_case_id(baseline_case))
            ),
            "target_root_proofs": [],
            "source_hash_revalidated_count": 0,
            "baseline_comparison": {},
            "chat_excerpt": "",
        }
    finally:
        try:
            assert_fixture_state_unchanged(before, target_root, f"phase208 {surface.value} {live_case_id(audit_case)}")
        except Exception as exc:  # noqa: BLE001
            result.setdefault("errors", []).append(f"fixture mutation check failed: {type(exc).__name__}: {exc}")
            result["status"] = "failed"
    return result


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 208 Evidence Quality Live Rerun",
        "",
        f"- Status: {report.get('status')}",
        f"- Generated at: {report.get('generated_at')}",
        f"- Live: {report.get('live')}",
        f"- Response count: {dict_value(report.get('summary')).get('response_count', 0)}",
        f"- Failed response count: {dict_value(report.get('summary')).get('failed_response_count', 0)}",
        "",
        "## Responses",
    ]
    for response in object_list(report.get("responses")):
        lines.extend(
            [
                "",
                (
                    f"- {response.get('status')}: {response.get('surface')} "
                    f"{response.get('live_case_id', response.get('audit_case_id'))} "
                    f"(baseline {response.get('audit_case_id')}) {response.get('target_root')} "
                    f"score={response.get('score')} "
                    f"baseline={dict_value(response.get('baseline_comparison')).get('score')} "
                    f"run={response.get('run_id')}"
                ),
            ]
        )
        for error in string_list(response.get("errors")):
            lines.append(f"  - error: {error}")
        hits = string_list(response.get("visible_source_ref_hits"))
        if hits:
            lines.append("  - visible source refs: " + ", ".join(hits))
    if string_list(report.get("errors")):
        lines.extend(["", "## Errors"])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines).rstrip() + "\n"


def validate_evidence_quality_live_rerun(config: EvidenceQualityLiveRerunConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path or default_output_path(live=config.live))
    markdown_output_path = resolve_path(
        config_root,
        config.markdown_output_path or default_markdown_output_path(live=config.live),
    )
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    errors.extend(validate_source_reports(config_root, policy))
    responses: list[dict[str, Any]] = []
    audit_cases: list[dict[str, Any]] = []
    baseline_cases_by_id: dict[str, dict[str, Any]] = {}
    selected_roots: list[str] = []
    selected_surfaces: list[str] = []

    if not errors:
        source_audit_cases = phase206_cases(config_root, policy)
        baseline_cases_by_id = {str(case.get("case_id")): case for case in source_audit_cases if isinstance(case.get("case_id"), str)}
        audit_cases = selected_live_cases(source_audit_cases, policy, config)
        requirements = case_requirements_by_id(policy)
        missing_requirements = sorted(
            baseline_case_id(case)
            for case in audit_cases
            if baseline_case_id(case) not in requirements
        )
        if missing_requirements:
            errors.append("Phase 208 policy missing requirements for audit cases: " + ", ".join(missing_requirements))
        missing_baselines = sorted(
            baseline_case_id(case)
            for case in audit_cases
            if baseline_case_id(case) not in baseline_cases_by_id
        )
        if missing_baselines:
            errors.append("Phase 208 live cases missing Phase 206 baseline cases: " + ", ".join(missing_baselines))
        selected_roots = target_roots(policy, config)
        for root in selected_roots:
            if not Path(root).is_dir():
                errors.append(f"required target root is missing: {root}")
        selected_surfaces = [surface.value for surface in surfaces(config)]
        if not config.allow_partial:
            if set(selected_surfaces) != set(string_list(policy.get("required_surfaces"))):
                errors.append("live closeout must include gateway and AnythingLLM surfaces")
            if set(selected_roots) != set(string_list(policy.get("required_target_roots"))):
                errors.append("live closeout must include both required frozen target roots")
            audit_case_count = sum(1 for case in audit_cases if not case.get("holdout_case_id"))
            holdout_case_count = sum(1 for case in audit_cases if case.get("holdout_case_id"))
            if audit_case_count < int_value(policy.get("minimum_audit_case_count"), 4):
                errors.append("live closeout must include all Phase 206 audit cases")
            if holdout_case_count < int_value(policy.get("minimum_holdout_case_count"), 4):
                errors.append("live closeout must include all Phase 208 holdout cases")

    if config.live and not errors:
        phase207_by_id = phase207_cases_by_audit_id(config_root, policy)
        requirements = case_requirements_by_id(policy)
        api_key = os.environ.get(config.api_key_env)
        for surface in surfaces(config):
            for root in selected_roots:
                for audit_case in audit_cases:
                    baseline_id = baseline_case_id(audit_case)
                    requirement = requirements[baseline_id]
                    baseline_case = baseline_cases_by_id[baseline_id]
                    responses.append(
                        run_live_case(
                            config,
                            policy=policy,
                            audit_case=audit_case,
                            baseline_case=baseline_case,
                            requirement=requirement,
                            phase207_by_id=phase207_by_id,
                            surface=surface,
                            target_root=root,
                            api_key=api_key,
                        )
                    )
        if not config.allow_partial and len(responses) < int_value(policy.get("minimum_live_response_count"), 16):
            errors.append("live response count below policy.minimum_live_response_count")

    failed_responses = [item for item in responses if item.get("status") != "passed"]
    status = EvidenceQualityLiveStatus.FAILED.value
    if not errors and not config.live:
        status = EvidenceQualityLiveStatus.PREFLIGHT_PASSED.value
    elif not errors and not failed_responses:
        status = EvidenceQualityLiveStatus.PASSED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "live": config.live,
        "policy_path": str(policy_path),
        "errors": errors,
        "responses": responses,
        "summary": {
            "audit_case_count": sum(1 for case in audit_cases if not case.get("holdout_case_id")),
            "holdout_case_count": sum(1 for case in audit_cases if case.get("holdout_case_id")),
            "live_case_count": len(audit_cases),
            "target_root_count": len(selected_roots),
            "surface_count": len(selected_surfaces),
            "response_count": len(responses),
            "failed_response_count": len(failed_responses),
            "source_hash_revalidated_count": sum(int_value(item.get("source_hash_revalidated_count"), 0) for item in responses),
            "baseline_scores": [
                dict_value(item.get("baseline_comparison")).get("score")
                for item in responses
                if item.get("baseline_comparison")
            ],
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
            "phase209_ready": status == EvidenceQualityLiveStatus.PASSED.value,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
