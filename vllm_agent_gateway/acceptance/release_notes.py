"""Release notes validation for Priority 0 release hardening."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "release_notes_policy"
EXPECTED_REPORT_KIND = "release_notes_validation_report"
EXPECTED_PHASE = 146
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "release_notes_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "release-notes" / "phase146"
REQUIRED_INPUT_KEYS = (
    "stable_chat_quality_release",
    "chat_quality_release_snapshot",
    "natural_output_format_preference",
    "founder_feedback_triage_dashboard",
    "stable_release_blocker_closure",
    "gateway_anythingllm_health_drift",
    "founder_test_prompt_pack",
    "founder_prompt_catalog",
    "founder_smoke_report",
    "stable_proof",
    "advanced_refactor_readiness",
)
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}
REQUIRED_HEALTH_CATEGORIES = {
    "anythingllm",
    "controller",
    "fixtures",
    "gateway_config",
    "port_health",
    "role_proxy",
}
REQUIRED_PORT_CHECK_IDS = {
    "port.architect_default",
    "port.controller",
    "port.dispatcher_default",
    "port.documenter_default",
    "port.implementer_default",
    "port.llm_gateway",
    "port.model",
    "port.researcher_default",
    "port.reviewer_code",
    "port.tester_code",
    "port.workflow_router_gateway",
}
REQUIRED_GATEWAY_PREFERENCES = {
    "default_format_a",
    "natural_format_a",
    "natural_json",
    "explicit_output_format_json",
    "openai_response_format_json",
}
REQUIRED_ANYTHINGLLM_PREFERENCES = {
    "default_format_a",
    "natural_format_a",
    "natural_json",
}


@dataclass(frozen=True)
class ReleaseNotesConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"release-notes-{utc_timestamp()}.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(f"policy.phase must be {EXPECTED_PHASE}")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if not isinstance(policy.get("release_notes_path"), str) or not policy["release_notes_path"]:
        errors.append("policy.release_notes_path must be a path string")
    inputs = policy.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("policy.inputs must be an object")
    else:
        for key in REQUIRED_INPUT_KEYS:
            if not isinstance(inputs.get(key), str) or not inputs[key]:
                errors.append(f"policy.inputs.{key} must be a path string")
    for field in ("required_sections", "required_markers", "forbidden_claim_markers"):
        if not string_list(policy.get(field)):
            errors.append(f"policy.{field} must be a non-empty string list")
    return errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "priority_backlog_id": payload.get("priority_backlog_id"),
    }


def report_source_errors(
    label: str,
    payload: dict[str, Any],
    *,
    expected_kind: str,
    expected_phase: int | None = None,
) -> list[str]:
    errors: list[str] = []
    if payload.get("kind") != expected_kind:
        errors.append(f"{label}.kind must be {expected_kind}")
    if payload.get("status") != "passed":
        errors.append(f"{label}.status must be passed")
    if expected_phase is not None and payload.get("phase") != expected_phase:
        errors.append(f"{label}.phase must be {expected_phase}")
    source_errors = payload.get("errors")
    if isinstance(source_errors, list) and source_errors:
        errors.append(f"{label}.errors must be empty")
    return errors


def summary_object(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def case_ids_from_tiers(tiers: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_tier: dict[str, list[str]] = {}
    for tier in tiers:
        tier_name = tier.get("tier")
        if isinstance(tier_name, str):
            by_tier[tier_name] = string_list(tier.get("case_ids"))
    return by_tier


def docs_link_errors(*, root_readme_text: str, docs_index_text: str, examples_index_text: str) -> list[str]:
    errors: list[str] = []
    if "README.release-notes.md" not in root_readme_text:
        errors.append("root README must link README.release-notes.md")
    if "../README.release-notes.md" not in docs_index_text:
        errors.append("docs/README.md must link ../README.release-notes.md")
    if "examples/release-notes.md" not in docs_index_text:
        errors.append("docs/README.md must link examples/release-notes.md")
    if "(release-notes.md)" not in examples_index_text:
        errors.append("docs/examples/README.md must link release-notes.md")
    return errors


def markdown_section_present(text: str, heading: str) -> bool:
    return f"## {heading}" in text or f"# {heading}" in text


def notes_content_errors(policy: dict[str, Any], text: str) -> list[str]:
    errors: list[str] = []
    lower_text = text.lower()
    for section in string_list(policy.get("required_sections")):
        if not markdown_section_present(text, section):
            errors.append(f"release notes missing section: {section}")
    for marker in string_list(policy.get("required_markers")):
        if marker not in text:
            errors.append(f"release notes missing marker: {marker}")
    for marker in string_list(policy.get("forbidden_claim_markers")):
        if marker.lower() in lower_text:
            errors.append(f"release notes contain forbidden claim marker: {marker}")
    return errors


def evidence_errors(
    *,
    stable_release: dict[str, Any],
    snapshot: dict[str, Any],
    natural_output: dict[str, Any],
    feedback_dashboard: dict[str, Any],
    blocker_closure: dict[str, Any],
    health_drift: dict[str, Any],
    prompt_pack: dict[str, Any],
    prompt_catalog: dict[str, Any],
    founder_smoke: dict[str, Any],
    stable_proof: dict[str, Any],
    advanced_readiness: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    errors.extend(
        report_source_errors(
            "stable_chat_quality_release",
            stable_release,
            expected_kind="stable_chat_quality_release_report",
            expected_phase=130,
        )
    )
    if stable_release.get("readiness") != "ready_for_founder_testing":
        errors.append("stable_chat_quality_release.readiness must be ready_for_founder_testing")
    summary = summary_object(stable_release)
    if summary.get("gate_count") != 11:
        errors.append("stable_chat_quality_release.summary.gate_count must be 11")
    if summary.get("passed_gate_count") != 11:
        errors.append("stable_chat_quality_release.summary.passed_gate_count must be 11")
    if summary.get("blocker_count") != 0:
        errors.append("stable_chat_quality_release.summary.blocker_count must be 0")
    errors.extend(
        report_source_errors(
            "chat_quality_release_snapshot",
            snapshot,
            expected_kind="chat_quality_release_snapshot",
            expected_phase=136,
        )
    )
    snapshot_summary = summary_object(snapshot)
    if snapshot_summary.get("release_readiness") != "ready_for_founder_testing":
        errors.append("chat_quality_release_snapshot.summary.release_readiness must be ready_for_founder_testing")
    if snapshot_summary.get("missing_artifact_count") != 0:
        errors.append("chat_quality_release_snapshot.summary.missing_artifact_count must be 0")
    if snapshot_summary.get("missing_doc_count") != 0:
        errors.append("chat_quality_release_snapshot.summary.missing_doc_count must be 0")
    if snapshot_summary.get("founder_smoke_failed") != 0:
        errors.append("chat_quality_release_snapshot.summary.founder_smoke_failed must be 0")
    if snapshot_summary.get("actionable_feedback_count") != 0:
        errors.append("chat_quality_release_snapshot.summary.actionable_feedback_count must be 0")
    errors.extend(
        report_source_errors(
            "natural_output_format_preference",
            natural_output,
            expected_kind="natural_output_format_preference_live_report",
            expected_phase=144,
        )
    )
    natural_cases = list_of_dicts(natural_output.get("cases"))
    if natural_output.get("case_count") != 4 or len(natural_cases) != 4:
        errors.append("natural_output_format_preference must have exactly 4 cases")
    target_roots = set(string_list(natural_output.get("target_roots")))
    if target_roots != REQUIRED_TARGET_ROOTS:
        errors.append("natural_output_format_preference.target_roots must cover both frozen Coinbase fixtures")
    mutation = natural_output.get("mutation_proof") if isinstance(natural_output.get("mutation_proof"), dict) else {}
    if mutation.get("runtime_changed_files") != []:
        errors.append("natural_output_format_preference.mutation_proof.runtime_changed_files must be empty")
    target_changed = mutation.get("target_changed_files")
    if not isinstance(target_changed, dict) or set(target_changed.keys()) != REQUIRED_TARGET_ROOTS:
        errors.append("natural_output_format_preference.mutation_proof.target_changed_files must cover both fixtures")
    elif any(value != [] for value in target_changed.values()):
        errors.append("natural_output_format_preference.mutation_proof.target_changed_files must be empty for each fixture")
    if mutation.get("target_git_changed") != {}:
        errors.append("natural_output_format_preference.mutation_proof.target_git_changed must be empty")
    for case in natural_cases:
        case_id = case.get("case_id", "<unknown>")
        if case.get("target_root") not in REQUIRED_TARGET_ROOTS:
            errors.append(f"natural_output_format_preference.{case_id}.target_root must be a frozen Coinbase fixture")
        responses = case.get("responses") if isinstance(case.get("responses"), dict) else {}
        for surface, required_prefs in (
            ("gateway", REQUIRED_GATEWAY_PREFERENCES),
            ("anythingllm", REQUIRED_ANYTHINGLLM_PREFERENCES),
        ):
            response = responses.get(surface) if isinstance(responses.get(surface), dict) else {}
            if response.get("status") != "passed":
                errors.append(f"natural_output_format_preference.{case_id}.{surface}.status must be passed")
            preferences = response.get("preferences") if isinstance(response.get("preferences"), dict) else {}
            missing = required_prefs - set(preferences.keys())
            if missing:
                errors.append(
                    f"natural_output_format_preference.{case_id}.{surface}.preferences missing {sorted(missing)}"
                )
            for pref in required_prefs & set(preferences.keys()):
                pref_payload = preferences.get(pref)
                if not isinstance(pref_payload, dict) or pref_payload.get("status") != "passed":
                    errors.append(
                        f"natural_output_format_preference.{case_id}.{surface}.{pref}.status must be passed"
                    )
    errors.extend(
        report_source_errors(
            "founder_feedback_triage_dashboard",
            feedback_dashboard,
            expected_kind="founder_feedback_triage_dashboard",
            expected_phase=145,
        )
    )
    feedback_summary = summary_object(feedback_dashboard)
    if feedback_summary.get("open_next_action_count") != 0:
        errors.append("founder_feedback_triage_dashboard.summary.open_next_action_count must be 0")
    if feedback_summary.get("unresolved_feedback_count") != 0:
        errors.append("founder_feedback_triage_dashboard.summary.unresolved_feedback_count must be 0")
    if feedback_summary.get("blocker_count") != 0:
        errors.append("founder_feedback_triage_dashboard.summary.blocker_count must be 0")
    errors.extend(
        report_source_errors(
            "stable_release_blocker_closure",
            blocker_closure,
            expected_kind="stable_release_blocker_closure_report",
            expected_phase=131,
        )
    )
    closure_summary = summary_object(blocker_closure)
    if closure_summary.get("unresolved_blocker_count") != 0:
        errors.append("stable_release_blocker_closure.summary.unresolved_blocker_count must be 0")
    errors.extend(
        report_source_errors(
            "gateway_anythingllm_health_drift",
            health_drift,
            expected_kind="gateway_anythingllm_health_drift_report",
            expected_phase=141,
        )
    )
    health_summary = summary_object(health_drift)
    if health_summary.get("check_count") != 29:
        errors.append("gateway_anythingllm_health_drift.summary.check_count must be 29")
    if health_summary.get("failed_check_count") != 0:
        errors.append("gateway_anythingllm_health_drift.summary.failed_check_count must be 0")
    if health_summary.get("finding_count") != 0:
        errors.append("gateway_anythingllm_health_drift.summary.finding_count must be 0")
    if health_summary.get("unclassified_finding_count") != 0:
        errors.append("gateway_anythingllm_health_drift.summary.unclassified_finding_count must be 0")
    if set(string_list(health_drift.get("checked_categories"))) != REQUIRED_HEALTH_CATEGORIES:
        errors.append("gateway_anythingllm_health_drift.checked_categories must match required categories")
    if health_drift.get("missing_required_categories") != []:
        errors.append("gateway_anythingllm_health_drift.missing_required_categories must be empty")
    if health_drift.get("missing_port_check_ids") != []:
        errors.append("gateway_anythingllm_health_drift.missing_port_check_ids must be empty")
    if set(string_list(health_drift.get("port_check_ids"))) != REQUIRED_PORT_CHECK_IDS:
        errors.append("gateway_anythingllm_health_drift.port_check_ids must match required ports")
    if health_drift.get("doctor_status") != "passed":
        errors.append("gateway_anythingllm_health_drift.doctor_status must be passed")
    if prompt_pack.get("kind") != "founder_test_prompt_pack":
        errors.append("founder_test_prompt_pack.kind must be founder_test_prompt_pack")
    if prompt_pack.get("phase") != 137:
        errors.append("founder_test_prompt_pack.phase must be 137")
    tiers = list_of_dicts(prompt_pack.get("tiers"))
    tier_case_ids = case_ids_from_tiers(tiers)
    smoke_ids = tier_case_ids.get("smoke", [])
    expanded_ids = tier_case_ids.get("expanded_read_only", [])
    all_pack_ids = smoke_ids + expanded_ids
    if len(smoke_ids) != 4:
        errors.append("founder_test_prompt_pack.smoke case count must be 4")
    if len(expanded_ids) != 10:
        errors.append("founder_test_prompt_pack.expanded_read_only case count must be 10")
    if len(all_pack_ids) != 14 or len(set(all_pack_ids)) != 14:
        errors.append("founder_test_prompt_pack total case count must be 14 unique cases")
    forbidden_tiers = {"draft", "apply", "advanced_refactor", "refactor"}
    if forbidden_tiers & set(tier_case_ids.keys()):
        errors.append("founder_test_prompt_pack must not include draft/apply/refactor tiers")
    if prompt_catalog.get("kind") != "prompt_catalog":
        errors.append("founder_prompt_catalog.kind must be prompt_catalog")
    catalog_cases = list_of_dicts(prompt_catalog.get("cases"))
    cases_by_id = {case.get("case_id"): case for case in catalog_cases if isinstance(case.get("case_id"), str)}
    missing_catalog_ids = [case_id for case_id in all_pack_ids if case_id not in cases_by_id]
    if missing_catalog_ids:
        errors.append(f"founder_test_prompt_pack case IDs missing from catalog: {missing_catalog_ids}")
    packed_roots = {cases_by_id[case_id].get("target_root") for case_id in all_pack_ids if case_id in cases_by_id}
    if packed_roots != REQUIRED_TARGET_ROOTS:
        errors.append("founder_test_prompt_pack catalog cases must cover both frozen Coinbase fixtures")
    for case_id in all_pack_ids:
        case = cases_by_id.get(case_id, {})
        tags = set(string_list(case.get("tags")))
        if tags & {"draft", "apply", "advanced-refactor"}:
            errors.append(f"founder_test_prompt_pack.{case_id} must not be draft/apply/advanced-refactor")
        if case.get("expected_workflow") not in {"code_context.lookup", "code_investigation.plan", "task.decompose"}:
            errors.append(f"founder_test_prompt_pack.{case_id} must use a read-only or planning workflow")
        forbidden = " ".join(string_list(case.get("forbidden_markers"))).lower()
        if "source mutation" not in forbidden and "source_changed" not in forbidden:
            errors.append(f"founder_test_prompt_pack.{case_id} must forbid source mutation markers")
    errors.extend(
        report_source_errors(
            "founder_smoke_report",
            founder_smoke,
            expected_kind="founder_field_prompt_evaluation",
        )
    )
    smoke_summary = summary_object(founder_smoke)
    if smoke_summary.get("passed") != 4 or smoke_summary.get("failed") != 0:
        errors.append("founder_smoke_report.summary must be passed=4 and failed=0")
    if len(list_of_dicts(founder_smoke.get("cases"))) != 4:
        errors.append("founder_smoke_report.cases must contain 4 cases")
    preflight = founder_smoke.get("anythingllm_preflight")
    if not isinstance(preflight, dict) or preflight.get("status") != "passed":
        errors.append("founder_smoke_report.anythingllm_preflight.status must be passed")
    else:
        if preflight.get("ping_status") != 200:
            errors.append("founder_smoke_report.anythingllm_preflight.ping_status must be 200")
        if preflight.get("workspace_status") != 200:
            errors.append("founder_smoke_report.anythingllm_preflight.workspace_status must be 200")
    errors.extend(
        report_source_errors(
            "stable_proof",
            stable_proof,
            expected_kind="v1_acceptance_report",
        )
    )
    if stable_proof.get("profile") != "v1.1-release-candidate":
        errors.append("stable_proof.profile must be v1.1-release-candidate")
    if stable_proof.get("proof_kind") != "stable_channel_activation_proof":
        errors.append("stable_proof.proof_kind must be stable_channel_activation_proof")
    boundary = stable_proof.get("known_boundary")
    if not isinstance(boundary, str) or "Advanced broad refactor orchestration remains deferred" not in boundary:
        errors.append("stable_proof.known_boundary must defer advanced broad refactor orchestration")
    errors.extend(
        report_source_errors(
            "advanced_refactor_readiness",
            advanced_readiness,
            expected_kind="advanced_refactor_readiness_report",
        )
    )
    advanced_summary = summary_object(advanced_readiness)
    if advanced_summary.get("broad_refactor_runtime_enabled") is not False:
        errors.append("advanced_refactor_readiness.summary.broad_refactor_runtime_enabled must be false")
    if advanced_summary.get("stable_promotion_enabled") is not False:
        errors.append("advanced_refactor_readiness.summary.stable_promotion_enabled must be false")
    return errors


def build_release_notes_report(
    *,
    policy: dict[str, Any],
    notes_text: str,
    root_readme_text: str,
    docs_index_text: str,
    examples_index_text: str,
    stable_release: dict[str, Any],
    snapshot: dict[str, Any],
    natural_output: dict[str, Any],
    feedback_dashboard: dict[str, Any],
    blocker_closure: dict[str, Any],
    health_drift: dict[str, Any],
    prompt_pack: dict[str, Any],
    prompt_catalog: dict[str, Any],
    founder_smoke: dict[str, Any],
    stable_proof: dict[str, Any],
    advanced_readiness: dict[str, Any],
    policy_path: Path | None = None,
    notes_path: Path | None = None,
    root_readme_path: Path | None = None,
    docs_index_path: Path | None = None,
    examples_index_path: Path | None = None,
    stable_release_path: Path | None = None,
    snapshot_path: Path | None = None,
    natural_output_path: Path | None = None,
    feedback_dashboard_path: Path | None = None,
    blocker_closure_path: Path | None = None,
    health_drift_path: Path | None = None,
    prompt_pack_path: Path | None = None,
    prompt_catalog_path: Path | None = None,
    founder_smoke_path: Path | None = None,
    stable_proof_path: Path | None = None,
    advanced_readiness_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(notes_content_errors(policy, notes_text))
    errors.extend(
        docs_link_errors(
            root_readme_text=root_readme_text,
            docs_index_text=docs_index_text,
            examples_index_text=examples_index_text,
        )
    )
    errors.extend(
        evidence_errors(
            stable_release=stable_release,
            snapshot=snapshot,
            natural_output=natural_output,
            feedback_dashboard=feedback_dashboard,
            blocker_closure=blocker_closure,
            health_drift=health_drift,
            prompt_pack=prompt_pack,
            prompt_catalog=prompt_catalog,
            founder_smoke=founder_smoke,
            stable_proof=stable_proof,
            advanced_readiness=advanced_readiness,
        )
    )
    stable_summary = summary_object(stable_release)
    snapshot_summary = summary_object(snapshot)
    feedback_summary = summary_object(feedback_dashboard)
    health_summary = summary_object(health_drift)
    tier_case_ids = case_ids_from_tiers(list_of_dicts(prompt_pack.get("tiers")))
    smoke_summary = summary_object(founder_smoke)
    advanced_summary = summary_object(advanced_readiness)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": "passed" if not errors else "failed",
        "generated_at": utc_timestamp(),
        "source_refs": {
            "policy": source_ref(policy_path, policy),
            "release_notes": {
                "path": str(notes_path) if notes_path else None,
                "sha256": artifact_hash(notes_path),
            },
            "root_readme": {
                "path": str(root_readme_path) if root_readme_path else None,
                "sha256": artifact_hash(root_readme_path),
            },
            "docs_index": {
                "path": str(docs_index_path) if docs_index_path else None,
                "sha256": artifact_hash(docs_index_path),
            },
            "examples_index": {
                "path": str(examples_index_path) if examples_index_path else None,
                "sha256": artifact_hash(examples_index_path),
            },
            "stable_chat_quality_release": source_ref(stable_release_path, stable_release),
            "chat_quality_release_snapshot": source_ref(snapshot_path, snapshot),
            "natural_output_format_preference": source_ref(natural_output_path, natural_output),
            "founder_feedback_triage_dashboard": source_ref(feedback_dashboard_path, feedback_dashboard),
            "stable_release_blocker_closure": source_ref(blocker_closure_path, blocker_closure),
            "gateway_anythingllm_health_drift": source_ref(health_drift_path, health_drift),
            "founder_test_prompt_pack": source_ref(prompt_pack_path, prompt_pack),
            "founder_prompt_catalog": source_ref(prompt_catalog_path, prompt_catalog),
            "founder_smoke_report": source_ref(founder_smoke_path, founder_smoke),
            "stable_proof": source_ref(stable_proof_path, stable_proof),
            "advanced_refactor_readiness": source_ref(advanced_readiness_path, advanced_readiness),
        },
        "summary": {
            "required_section_count": len(string_list(policy.get("required_sections"))),
            "required_marker_count": len(string_list(policy.get("required_markers"))),
            "forbidden_marker_count": len(string_list(policy.get("forbidden_claim_markers"))),
            "stable_gate_count": stable_summary.get("gate_count"),
            "stable_passed_gate_count": stable_summary.get("passed_gate_count"),
            "stable_blocker_count": stable_summary.get("blocker_count"),
            "snapshot_missing_artifact_count": snapshot_summary.get("missing_artifact_count"),
            "snapshot_missing_doc_count": snapshot_summary.get("missing_doc_count"),
            "natural_output_case_count": natural_output.get("case_count"),
            "feedback_unresolved_count": feedback_summary.get("unresolved_feedback_count"),
            "feedback_open_next_action_count": feedback_summary.get("open_next_action_count"),
            "health_check_count": health_summary.get("check_count"),
            "health_failed_check_count": health_summary.get("failed_check_count"),
            "founder_pack_smoke_case_count": len(tier_case_ids.get("smoke", [])),
            "founder_pack_expanded_read_only_case_count": len(tier_case_ids.get("expanded_read_only", [])),
            "founder_smoke_passed_count": smoke_summary.get("passed"),
            "founder_smoke_failed_count": smoke_summary.get("failed"),
            "advanced_refactor_runtime_enabled": advanced_summary.get("broad_refactor_runtime_enabled"),
            "advanced_refactor_stable_promotion_enabled": advanced_summary.get("stable_promotion_enabled"),
            "error_count": len(errors),
        },
        "errors": errors,
    }


def validate_release_notes_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    notes_text: str,
    root_readme_text: str,
    docs_index_text: str,
    examples_index_text: str,
    stable_release: dict[str, Any],
    snapshot: dict[str, Any],
    natural_output: dict[str, Any],
    feedback_dashboard: dict[str, Any],
    blocker_closure: dict[str, Any],
    health_drift: dict[str, Any],
    prompt_pack: dict[str, Any],
    prompt_catalog: dict[str, Any],
    founder_smoke: dict[str, Any],
    stable_proof: dict[str, Any],
    advanced_readiness: dict[str, Any],
    policy_path: Path | None = None,
    notes_path: Path | None = None,
    root_readme_path: Path | None = None,
    docs_index_path: Path | None = None,
    examples_index_path: Path | None = None,
    stable_release_path: Path | None = None,
    snapshot_path: Path | None = None,
    natural_output_path: Path | None = None,
    feedback_dashboard_path: Path | None = None,
    blocker_closure_path: Path | None = None,
    health_drift_path: Path | None = None,
    prompt_pack_path: Path | None = None,
    prompt_catalog_path: Path | None = None,
    founder_smoke_path: Path | None = None,
    stable_proof_path: Path | None = None,
    advanced_readiness_path: Path | None = None,
) -> list[str]:
    expected = build_release_notes_report(
        policy=policy,
        notes_text=notes_text,
        root_readme_text=root_readme_text,
        docs_index_text=docs_index_text,
        examples_index_text=examples_index_text,
        stable_release=stable_release,
        snapshot=snapshot,
        natural_output=natural_output,
        feedback_dashboard=feedback_dashboard,
        blocker_closure=blocker_closure,
        health_drift=health_drift,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        founder_smoke=founder_smoke,
        stable_proof=stable_proof,
        advanced_readiness=advanced_readiness,
        policy_path=policy_path,
        notes_path=notes_path,
        root_readme_path=root_readme_path,
        docs_index_path=docs_index_path,
        examples_index_path=examples_index_path,
        stable_release_path=stable_release_path,
        snapshot_path=snapshot_path,
        natural_output_path=natural_output_path,
        feedback_dashboard_path=feedback_dashboard_path,
        blocker_closure_path=blocker_closure_path,
        health_drift_path=health_drift_path,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
        founder_smoke_path=founder_smoke_path,
        stable_proof_path=stable_proof_path,
        advanced_readiness_path=advanced_readiness_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "source_refs",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt release notes report")
    return errors


def run_release_notes_validation(config: ReleaseNotesConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    inputs = policy.get("inputs") if isinstance(policy.get("inputs"), dict) else {}
    notes_path = resolve_path(config_root, str(policy.get("release_notes_path", "")))
    stable_path = resolve_path(config_root, str(inputs.get("stable_chat_quality_release", "")))
    snapshot_path = resolve_path(config_root, str(inputs.get("chat_quality_release_snapshot", "")))
    natural_path = resolve_path(config_root, str(inputs.get("natural_output_format_preference", "")))
    feedback_path = resolve_path(config_root, str(inputs.get("founder_feedback_triage_dashboard", "")))
    closure_path = resolve_path(config_root, str(inputs.get("stable_release_blocker_closure", "")))
    health_path = resolve_path(config_root, str(inputs.get("gateway_anythingllm_health_drift", "")))
    prompt_pack_path = resolve_path(config_root, str(inputs.get("founder_test_prompt_pack", "")))
    prompt_catalog_path = resolve_path(config_root, str(inputs.get("founder_prompt_catalog", "")))
    founder_smoke_path = resolve_path(config_root, str(inputs.get("founder_smoke_report", "")))
    stable_proof_path = resolve_path(config_root, str(inputs.get("stable_proof", "")))
    advanced_path = resolve_path(config_root, str(inputs.get("advanced_refactor_readiness", "")))
    root_readme_path = config_root / "README.md"
    docs_index_path = config_root / "docs" / "README.md"
    examples_index_path = config_root / "docs" / "examples" / "README.md"
    required_paths = [
        policy_path,
        notes_path,
        root_readme_path,
        docs_index_path,
        examples_index_path,
        stable_path,
        snapshot_path,
        natural_path,
        feedback_path,
        closure_path,
        health_path,
        prompt_pack_path,
        prompt_catalog_path,
        founder_smoke_path,
        stable_proof_path,
        advanced_path,
    ]
    missing_paths = [path for path in required_paths if config.require_artifacts and not path.is_file()]
    notes_text = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else ""
    root_readme_text = root_readme_path.read_text(encoding="utf-8") if root_readme_path.is_file() else ""
    docs_index_text = docs_index_path.read_text(encoding="utf-8") if docs_index_path.is_file() else ""
    examples_index_text = examples_index_path.read_text(encoding="utf-8") if examples_index_path.is_file() else ""
    stable = read_json_object(stable_path) if stable_path.is_file() else {}
    snapshot = read_json_object(snapshot_path) if snapshot_path.is_file() else {}
    natural = read_json_object(natural_path) if natural_path.is_file() else {}
    feedback = read_json_object(feedback_path) if feedback_path.is_file() else {}
    closure = read_json_object(closure_path) if closure_path.is_file() else {}
    health = read_json_object(health_path) if health_path.is_file() else {}
    prompt_pack = read_json_object(prompt_pack_path) if prompt_pack_path.is_file() else {}
    prompt_catalog = read_json_object(prompt_catalog_path) if prompt_catalog_path.is_file() else {}
    founder_smoke = read_json_object(founder_smoke_path) if founder_smoke_path.is_file() else {}
    stable_proof = read_json_object(stable_proof_path) if stable_proof_path.is_file() else {}
    advanced = read_json_object(advanced_path) if advanced_path.is_file() else {}
    report = build_release_notes_report(
        policy=policy,
        notes_text=notes_text,
        root_readme_text=root_readme_text,
        docs_index_text=docs_index_text,
        examples_index_text=examples_index_text,
        stable_release=stable,
        snapshot=snapshot,
        natural_output=natural,
        feedback_dashboard=feedback,
        blocker_closure=closure,
        health_drift=health,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        founder_smoke=founder_smoke,
        stable_proof=stable_proof,
        advanced_readiness=advanced,
        policy_path=policy_path if policy_path.is_file() else None,
        notes_path=notes_path if notes_path.is_file() else None,
        root_readme_path=root_readme_path if root_readme_path.is_file() else None,
        docs_index_path=docs_index_path if docs_index_path.is_file() else None,
        examples_index_path=examples_index_path if examples_index_path.is_file() else None,
        stable_release_path=stable_path if stable_path.is_file() else None,
        snapshot_path=snapshot_path if snapshot_path.is_file() else None,
        natural_output_path=natural_path if natural_path.is_file() else None,
        feedback_dashboard_path=feedback_path if feedback_path.is_file() else None,
        blocker_closure_path=closure_path if closure_path.is_file() else None,
        health_drift_path=health_path if health_path.is_file() else None,
        prompt_pack_path=prompt_pack_path if prompt_pack_path.is_file() else None,
        prompt_catalog_path=prompt_catalog_path if prompt_catalog_path.is_file() else None,
        founder_smoke_path=founder_smoke_path if founder_smoke_path.is_file() else None,
        stable_proof_path=stable_proof_path if stable_proof_path.is_file() else None,
        advanced_readiness_path=advanced_path if advanced_path.is_file() else None,
    )
    if missing_paths:
        report["status"] = "failed"
        report["errors"] = list(report.get("errors", [])) + [
            f"required artifact is missing: {path}" for path in missing_paths
        ]
    validation_errors = validate_release_notes_report(
        report,
        policy=policy,
        notes_text=notes_text,
        root_readme_text=root_readme_text,
        docs_index_text=docs_index_text,
        examples_index_text=examples_index_text,
        stable_release=stable,
        snapshot=snapshot,
        natural_output=natural,
        feedback_dashboard=feedback,
        blocker_closure=closure,
        health_drift=health,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        founder_smoke=founder_smoke,
        stable_proof=stable_proof,
        advanced_readiness=advanced,
        policy_path=policy_path if policy_path.is_file() else None,
        notes_path=notes_path if notes_path.is_file() else None,
        root_readme_path=root_readme_path if root_readme_path.is_file() else None,
        docs_index_path=docs_index_path if docs_index_path.is_file() else None,
        examples_index_path=examples_index_path if examples_index_path.is_file() else None,
        stable_release_path=stable_path if stable_path.is_file() else None,
        snapshot_path=snapshot_path if snapshot_path.is_file() else None,
        natural_output_path=natural_path if natural_path.is_file() else None,
        feedback_dashboard_path=feedback_path if feedback_path.is_file() else None,
        blocker_closure_path=closure_path if closure_path.is_file() else None,
        health_drift_path=health_path if health_path.is_file() else None,
        prompt_pack_path=prompt_pack_path if prompt_pack_path.is_file() else None,
        prompt_catalog_path=prompt_catalog_path if prompt_catalog_path.is_file() else None,
        founder_smoke_path=founder_smoke_path if founder_smoke_path.is_file() else None,
        stable_proof_path=stable_proof_path if stable_proof_path.is_file() else None,
        advanced_readiness_path=advanced_path if advanced_path.is_file() else None,
    )
    if validation_errors:
        report["status"] = "failed"
        report["errors"] = list(report.get("errors", [])) + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
