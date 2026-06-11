"""Phase 196 current V1 product readiness reassessment gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "v1_product_readiness_reassessment_policy"
EXPECTED_REPORT_KIND = "v1_product_readiness_reassessment_report"
EXPECTED_PHASE = 196
EXPECTED_BACKLOG_ID = "P0-BB-060"
DEFAULT_POLICY_PATH = Path("runtime") / "v1_product_readiness_reassessment_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase196" / "phase196-v1-product-readiness-reassessment-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase196" / "phase196-v1-product-readiness-reassessment-report.md"

REQUIRED_REPORT_IDS = {
    "v1_stable_release_decision",
    "stable_release_refresh",
    "release_notes",
    "model_swap_smoke_probe",
    "prompt_family_drift_detection",
    "chat_answer_scoring_v2",
    "skill_registry_readiness_review",
    "skill_authoring_pipeline_v2",
    "release_candidate_founder_trial_pack",
}
REQUIRED_RELEASE_SCOPE = {
    "local_founder_beta",
    "anythingllm_workflow_router_path",
    "current_localhost_model",
    "two_frozen_coinbase_fixtures",
    "format_a_and_json_output",
    "read_only_l1_l2_chat_quality",
    "draft_only_skill_authoring_packets",
    "structured_founder_feedback_capture",
}
REQUIRED_RELEASE_LIMITATIONS = {
    "not_production_deployment",
    "not_advanced_broad_refactor_orchestration",
    "not_mutation_capable_founder_prompt_pack",
    "not_every_repository_language_or_coding_task",
    "not_direct_mutation_of_protected_fixtures",
    "not_automatic_model_selection",
    "not_unbounded_skill_library_scale",
}


class V1ReadinessReassessmentStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class V1ReadinessRecommendation(str, Enum):
    RELEASE = "release_for_broader_founder_beta"
    REPAIR = "priority0_repair_cycle_required"
    SCOPE_REDUCTION = "scope_reduction_required"
    ROADMAP_EXPANSION = "roadmap_expansion_required"
    STALE = "blocked_stale_or_invalid_evidence"


@dataclass(frozen=True)
class V1ProductReadinessReassessmentConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


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


def validation_error(error_id: str, message: str, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 196"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("allowed_recommendations"))) != {item.value for item in V1ReadinessRecommendation}:
        errors.append(validation_error("policy.allowed_recommendations", "allowed recommendations must match the Phase 196 decision set"))
    report_ids = [str(item.get("id")) for item in object_list(policy.get("required_reports")) if isinstance(item.get("id"), str)]
    if set(report_ids) != REQUIRED_REPORT_IDS:
        errors.append(validation_error("policy.required_reports", "required reports must match the current Phase 191-195 proof set"))
    if len(report_ids) != len(set(report_ids)):
        errors.append(validation_error("policy.required_reports.duplicates", "required report ids must be unique"))
    for index, item in enumerate(object_list(policy.get("required_reports"))):
        prefix = f"policy.required_reports[{index}]"
        for key in ("id", "path", "expected_kind", "expected_status"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(validation_error(f"{prefix}.{key}", f"{prefix}.{key} must be a non-empty string"))
        if not isinstance(item.get("expected_phase"), int):
            errors.append(validation_error(f"{prefix}.expected_phase", f"{prefix}.expected_phase must be an integer"))
    if set(string_list(policy.get("release_scope"))) != REQUIRED_RELEASE_SCOPE:
        errors.append(validation_error("policy.release_scope", "release scope must match the governed Phase 196 scope"))
    if set(string_list(policy.get("release_limitations"))) != REQUIRED_RELEASE_LIMITATIONS:
        errors.append(validation_error("policy.release_limitations", "release limitations must match the governed Phase 196 limitations"))
    if len(string_list(policy.get("blocker_rules"))) < 8:
        errors.append(validation_error("policy.blocker_rules", "blocker rules must be explicit and non-trivial"))
    if len(object_list(policy.get("advisory_rules"))) < 3:
        errors.append(validation_error("policy.advisory_rules", "at least three advisory rules are required"))
    if not string_list(policy.get("required_docs")):
        errors.append(validation_error("policy.required_docs", "required docs are required"))
    live_proof = dict_value(policy.get("required_live_runtime_proof"))
    for key in (
        "path",
        "expected_kind",
        "expected_status",
        "required_model_id",
        "required_gateway_url",
        "required_anythingllm_target_url",
        "required_anythingllm_api_url",
    ):
        if not isinstance(live_proof.get(key), str) or not live_proof[key].strip():
            errors.append(validation_error(f"policy.required_live_runtime_proof.{key}", f"live runtime proof {key} is required"))
    if live_proof.get("expected_phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.required_live_runtime_proof.expected_phase", "live runtime proof phase must be 196"))
    if set(string_list(live_proof.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_live_runtime_proof.required_target_roots", "live runtime proof must cover both frozen Coinbase fixtures"))
    if not string_list(live_proof.get("required_output_markers")):
        errors.append(validation_error("policy.required_live_runtime_proof.required_output_markers", "live runtime proof output markers are required"))
    if len(string_list(policy.get("next_unapproved_phase_candidates"))) < 3:
        errors.append(validation_error("policy.next_unapproved_phase_candidates", "next phase candidates are required"))
    return errors


def load_report_inputs(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[dict[str, str]]]:
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    for item in object_list(policy.get("required_reports")):
        report_id = str(item.get("id"))
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            sources[report_id] = (None, {})
            errors.append(validation_error(f"{report_id}.path", "required report path is invalid", source=report_id))
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            sources[report_id] = (path, {})
            if require_artifacts:
                errors.append(validation_error(f"{report_id}.missing", f"required report is missing: {raw_path}", source=report_id))
            continue
        try:
            sources[report_id] = (path, read_json_object(path))
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            sources[report_id] = (path, {})
            errors.append(validation_error(f"{report_id}.malformed", f"required report is malformed: {type(exc).__name__}: {exc}", source=report_id))
    return sources, errors


def validate_report_contract(policy: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for item in object_list(policy.get("required_reports")):
        report_id = str(item.get("id"))
        path, payload = sources.get(report_id, (None, {}))
        if path is None or not path.is_file():
            blockers.append(validation_error(f"{report_id}.missing", "required report is missing", source=report_id))
        if payload.get("kind") != item.get("expected_kind"):
            blockers.append(validation_error(f"{report_id}.kind", f"kind must be {item.get('expected_kind')}", source=report_id))
        if payload.get("status") != item.get("expected_status"):
            blockers.append(validation_error(f"{report_id}.status", f"status must be {item.get('expected_status')}", source=report_id))
        if payload.get("phase") != item.get("expected_phase"):
            blockers.append(validation_error(f"{report_id}.phase", f"phase must be {item.get('expected_phase')}", source=report_id))
        validation_error_count = dict_value(payload.get("summary")).get("validation_error_count")
        if isinstance(validation_error_count, int) and validation_error_count != 0:
            blockers.append(validation_error(f"{report_id}.validation_errors", "validation_error_count must be 0", source=report_id))
        if object_list(payload.get("validation_errors")):
            blockers.append(validation_error(f"{report_id}.validation_errors_list", "validation_errors must be empty", source=report_id))
    return blockers


def validate_phase_specific_blockers(sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    phase192 = sources.get("chat_answer_scoring_v2", (None, {}))[1]
    if dict_value(phase192.get("summary")).get("failed_case_count") != 0:
        blockers.append(validation_error("phase192.failed_cases", "Phase 192 must have zero failed scored cases", source="chat_answer_scoring_v2"))
    phase193 = sources.get("skill_registry_readiness_review", (None, {}))[1]
    if dict_value(phase193.get("summary")).get("semantic_conflict_count") != 0:
        blockers.append(validation_error("phase193.semantic_conflicts", "Phase 193 must have zero semantic conflicts", source="skill_registry_readiness_review"))
    phase194 = sources.get("skill_authoring_pipeline_v2", (None, {}))[1]
    summary194 = dict_value(phase194.get("summary"))
    if summary194.get("promotion_eligible") is not False or summary194.get("proof_status") != "not_run":
        blockers.append(
            validation_error(
                "phase194.promotion_boundary",
                "Phase 194 must remain draft-packet admission only until stable promotion proof exists",
                source="skill_authoring_pipeline_v2",
            )
        )
    phase195 = sources.get("release_candidate_founder_trial_pack", (None, {}))[1]
    summary195 = dict_value(phase195.get("summary"))
    fixture_state = dict_value(phase195.get("fixture_state"))
    proof_mode = dict_value(phase195.get("proof_artifact_mode"))
    if fixture_state.get("validated") is not True:
        blockers.append(validation_error("phase195.fixture_state", "Phase 195 strict fixture-state validation must be enabled", source="release_candidate_founder_trial_pack"))
    if proof_mode.get("enabled_for_this_run") is not True:
        blockers.append(validation_error("phase195.proof_artifact_mode", "Phase 195 must run with proof artifact mode enabled", source="release_candidate_founder_trial_pack"))
    if summary195.get("smoke_case_count", 0) < 4 or summary195.get("expanded_case_count", 0) < 10:
        blockers.append(validation_error("phase195.prompt_pack", "Phase 195 must include smoke and expanded prompt cases", source="release_candidate_founder_trial_pack"))
    if summary195.get("target_root_count") != 2:
        blockers.append(validation_error("phase195.target_roots", "Phase 195 must cover both frozen Coinbase fixtures", source="release_candidate_founder_trial_pack"))
    return blockers


def load_live_runtime_proof(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    live_policy = dict_value(policy.get("required_live_runtime_proof"))
    raw_path = live_policy.get("path")
    if not isinstance(raw_path, str):
        return None, {}, [validation_error("live_runtime_proof.path", "live runtime proof path is invalid", source="live_runtime_proof")]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        errors = []
        if require_artifacts:
            errors.append(validation_error("live_runtime_proof.missing", f"required live runtime proof is missing: {raw_path}", source="live_runtime_proof"))
        return path, {}, errors
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error("live_runtime_proof.malformed", f"live runtime proof is malformed: {type(exc).__name__}: {exc}", source="live_runtime_proof")]


def validate_live_runtime_proof(policy: dict[str, Any], path: Path | None, payload: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    live_policy = dict_value(policy.get("required_live_runtime_proof"))
    if path is None or not path.is_file():
        blockers.append(validation_error("live_runtime_proof.missing", "required live runtime proof is missing", source="live_runtime_proof"))
        return blockers
    expected = {
        "kind": live_policy.get("expected_kind"),
        "status": live_policy.get("expected_status"),
        "phase": live_policy.get("expected_phase"),
    }
    for key, expected_value in expected.items():
        if payload.get(key) != expected_value:
            blockers.append(validation_error(f"live_runtime_proof.{key}", f"live runtime proof {key} must be {expected_value}", source="live_runtime_proof"))
    if payload.get("model_id") != live_policy.get("required_model_id"):
        blockers.append(validation_error("live_runtime_proof.model_id", "live runtime proof model_id does not match policy", source="live_runtime_proof"))
    if payload.get("gateway_url") != live_policy.get("required_gateway_url"):
        blockers.append(validation_error("live_runtime_proof.gateway_url", "live runtime proof gateway_url does not match policy", source="live_runtime_proof"))
    if payload.get("anythingllm_target_url") != live_policy.get("required_anythingllm_target_url"):
        blockers.append(validation_error("live_runtime_proof.anythingllm_target_url", "AnythingLLM must target the workflow-router gateway", source="live_runtime_proof"))
    if payload.get("anythingllm_api_url") != live_policy.get("required_anythingllm_api_url"):
        blockers.append(validation_error("live_runtime_proof.anythingllm_api_url", "AnythingLLM API URL does not match policy", source="live_runtime_proof"))
    if set(string_list(payload.get("target_roots"))) != set(string_list(live_policy.get("required_target_roots"))):
        blockers.append(validation_error("live_runtime_proof.target_roots", "live runtime proof must cover both frozen fixture roots", source="live_runtime_proof"))
    run_ids = dict_value(payload.get("run_ids"))
    for key in ("gateway", "anythingllm"):
        values = string_list(run_ids.get(key))
        if not values or not all(value.startswith("workflow-router-") for value in values):
            blockers.append(validation_error(f"live_runtime_proof.run_ids.{key}", f"live runtime proof must include {key} workflow-router run IDs", source="live_runtime_proof"))
    output_markers = set(string_list(payload.get("output_markers")))
    for marker in string_list(live_policy.get("required_output_markers")):
        if marker not in output_markers:
            blockers.append(validation_error("live_runtime_proof.output_markers", f"live runtime proof missing output marker: {marker}", source="live_runtime_proof"))
    fixture_integrity = dict_value(payload.get("fixture_integrity"))
    if fixture_integrity.get("status") != "passed":
        blockers.append(validation_error("live_runtime_proof.fixture_integrity", "live runtime proof fixture integrity must pass", source="live_runtime_proof"))
    if object_list(payload.get("errors")):
        blockers.append(validation_error("live_runtime_proof.errors", "live runtime proof errors must be empty", source="live_runtime_proof"))
    return blockers


def advisory_records(policy: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rule in object_list(policy.get("advisory_rules")):
        condition = rule.get("condition")
        include = condition == "always"
        if condition == "advisory_case_count_gt_zero":
            include = dict_value(sources.get("chat_answer_scoring_v2", (None, {}))[1].get("summary")).get("advisory_case_count", 0) > 0
        if condition == "promotion_eligible_false":
            include = dict_value(sources.get("skill_authoring_pipeline_v2", (None, {}))[1].get("summary")).get("promotion_eligible") is False
        if include:
            records.append(
                {
                    "id": rule.get("id"),
                    "severity": rule.get("severity"),
                    "source": rule.get("source"),
                    "statement": rule.get("statement"),
                }
            )
    return records


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    docs: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": raw_path, "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            blockers.append(validation_error(f"doc_missing.{raw_path}", f"required doc is missing: {raw_path}", "medium", "documentation"))
    return docs, blockers


def readiness_summary(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    blockers: list[dict[str, str]],
    advisories: list[dict[str, Any]],
) -> dict[str, Any]:
    phase192_summary = dict_value(sources.get("chat_answer_scoring_v2", (None, {}))[1].get("summary"))
    phase195_summary = dict_value(sources.get("release_candidate_founder_trial_pack", (None, {}))[1].get("summary"))
    return {
        "required_report_count": len(REQUIRED_REPORT_IDS),
        "release_blocker_count": len(blockers),
        "advisory_count": len(advisories),
        "average_chat_answer_score": phase192_summary.get("average_score"),
        "failed_scored_case_count": phase192_summary.get("failed_case_count"),
        "phase195_prompt_case_count": phase195_summary.get("prompt_case_count"),
        "phase195_target_root_count": phase195_summary.get("target_root_count"),
        "release_scope_count": len(string_list(policy.get("release_scope"))),
        "release_limitation_count": len(string_list(policy.get("release_limitations"))),
    }


def build_v1_product_readiness_reassessment_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    live_proof_path: Path | None = None,
    live_proof: dict[str, Any] | None = None,
    load_errors: list[dict[str, str]] | None = None,
    live_proof_load_errors: list[dict[str, str]] | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    blockers.extend(validate_policy(policy))
    blockers.extend(load_errors or [])
    blockers.extend(validate_report_contract(policy, sources))
    blockers.extend(validate_phase_specific_blockers(sources))
    blockers.extend(live_proof_load_errors or [])
    blockers.extend(validate_live_runtime_proof(policy, live_proof_path, live_proof or {}))
    docs, doc_blockers = doc_records(config_root, policy)
    blockers.extend(doc_blockers)
    advisories = advisory_records(policy, sources)
    recommendation = V1ReadinessRecommendation.STALE.value if blockers else V1ReadinessRecommendation.RELEASE.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": V1ReadinessReassessmentStatus.FAILED.value if blockers else V1ReadinessReassessmentStatus.PASSED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "recommendation": recommendation,
        "release_scope": string_list(policy.get("release_scope")),
        "release_limitations": string_list(policy.get("release_limitations")),
        "release_blockers": blockers,
        "advisories": advisories,
        "source_refs": {source_id: source_ref(path, payload) for source_id, (path, payload) in sorted(sources.items())},
        "live_runtime_proof": source_ref(live_proof_path, live_proof or {}),
        "docs": docs,
        "next_unapproved_phase_candidates": string_list(policy.get("next_unapproved_phase_candidates")),
        "summary": readiness_summary(policy, sources, blockers, advisories),
    }
    report["summary"]["recommendation"] = recommendation
    return report


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "status",
            "policy_path",
            "policy_sha256",
            "recommendation",
            "release_scope",
            "release_limitations",
            "release_blockers",
            "advisories",
            "source_refs",
            "live_runtime_proof",
            "docs",
            "next_unapproved_phase_candidates",
            "summary",
        )
    }


def validate_v1_product_readiness_reassessment_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    live_proof_path: Path | None = None,
    live_proof: dict[str, Any] | None = None,
    load_errors: list[dict[str, str]] | None = None,
    live_proof_load_errors: list[dict[str, str]] | None = None,
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_v1_product_readiness_reassessment_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        live_proof_path=live_proof_path,
        live_proof=live_proof,
        load_errors=load_errors,
        live_proof_load_errors=live_proof_load_errors,
        policy_path=policy_path,
    )
    if stable_report_view(report) != stable_report_view(expected):
        return ["report must match rebuilt V1 product readiness reassessment"]
    return []


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 196 V1 Product Readiness Reassessment",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Recommendation: `{report.get('recommendation')}`",
        f"- Release blockers: `{summary.get('release_blocker_count')}`",
        f"- Advisories: `{summary.get('advisory_count')}`",
        f"- Average chat answer score: `{summary.get('average_chat_answer_score')}`",
        "",
        "## Release Scope",
        "",
    ]
    lines.extend(f"- `{item}`" for item in string_list(report.get("release_scope")))
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- `{item}`" for item in string_list(report.get("release_limitations")))
    lines.extend(["", "## Blockers", ""])
    blockers = object_list(report.get("release_blockers"))
    lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Advisories", ""])
    advisories = object_list(report.get("advisories"))
    lines.extend(f"- `{item.get('id')}`: {item.get('statement')}" for item in advisories) if advisories else lines.append("- none")
    lines.extend(["", "## Next Unapproved Phase Candidates", ""])
    lines.extend(f"- {item}" for item in string_list(report.get("next_unapproved_phase_candidates")))
    return "\n".join(lines) + "\n"


def run_v1_product_readiness_reassessment(config: V1ProductReadinessReassessmentConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, load_errors = load_report_inputs(config_root, policy, require_artifacts=config.require_artifacts)
    live_proof_path, live_proof, live_proof_load_errors = load_live_runtime_proof(
        config_root,
        policy,
        require_artifacts=config.require_artifacts,
    )
    report = build_v1_product_readiness_reassessment_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        live_proof_path=live_proof_path,
        live_proof=live_proof,
        load_errors=load_errors,
        live_proof_load_errors=live_proof_load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_v1_product_readiness_reassessment_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        live_proof_path=live_proof_path,
        live_proof=live_proof,
        load_errors=load_errors,
        live_proof_load_errors=live_proof_load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = V1ReadinessReassessmentStatus.FAILED.value
        report["recommendation"] = V1ReadinessRecommendation.STALE.value
        report["release_blockers"] = [
            *object_list(report.get("release_blockers")),
            *[
                validation_error(f"self_validation.{index}", error, "critical", "v1_product_readiness_reassessment")
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["release_blocker_count"] = len(report["release_blockers"])
        report["summary"]["recommendation"] = report["recommendation"]
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if config.markdown_output_path is not None:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_text(markdown_path, render_markdown(report))
        report["markdown_report_path"] = str(markdown_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path is not None:
        write_text(resolve_path(config_root, config.markdown_output_path), render_markdown(report))
    return report
