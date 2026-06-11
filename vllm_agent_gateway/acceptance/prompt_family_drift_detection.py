"""Phase 191 prompt-family drift detection governance."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "prompt_family_drift_detection_policy"
EXPECTED_REPORT_KIND = "prompt_family_drift_detection_report"
EXPECTED_PHASE = 191
EXPECTED_BACKLOG_ID = "P0-BB-055"
DEFAULT_POLICY_PATH = Path("runtime") / "prompt_family_drift_detection_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase191" / "phase191-prompt-family-drift-detection-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase191" / "phase191-prompt-family-drift-detection-report.md"
ROLE_KEYS = ("target", "holdout", "regression", "promotion_candidate", "retired")
DECISIONS = ("in_coverage", "holdout", "partial_drift", "out_of_coverage")
WEAK_LAYERS = (
    "none",
    "workflow",
    "router",
    "skill",
    "tool",
    "policy",
    "docs",
    "test_coverage",
    "prompt_governance",
    "runtime_proof",
)
VERIFICATION_GATES = (
    "static_registry",
    "live_gateway_anythingllm",
    "prompt_governance_update",
    "workflow_repair",
    "new_skill_tool_proposal",
    "unsupported_scope_backlog",
)
REQUIRED_REPORT_FIELDS = (
    "prompt_id",
    "prompt_text",
    "prompt_family",
    "decision",
    "confidence",
    "expected_intent",
    "matched_workflow",
    "matched_skill",
    "matched_router_path",
    "missing_or_weak_layer",
    "evidence_artifacts_checked",
    "reasoning_summary",
    "required_verification_gate",
    "recommended_next_action",
    "coverage_version_or_commit",
    "timestamp",
)


class PromptFamilyDriftDetectionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class PromptFamilyDriftDetectionConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH


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


def source_path_config(policy: dict[str, Any]) -> dict[str, str]:
    return {
        "catalog": str(policy.get("source_catalog_path") or ""),
        "skill_coverage": str(policy.get("source_skill_coverage_path") or ""),
        "corpus_governance": str(policy.get("source_corpus_governance_path") or ""),
        "holdout_bank": str(policy.get("source_holdout_bank_path") or ""),
        "prompt_pack": str(policy.get("source_prompt_pack_path") or ""),
    }


def source_paths(config_root: Path, policy: dict[str, Any]) -> dict[str, Path]:
    return {key: resolve_path(config_root, value) for key, value in source_path_config(policy).items()}


def source_artifacts(sources: dict[str, dict[str, Any]], paths: dict[str, Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for key in sorted(paths):
        path = paths[key]
        artifacts.append(
            {
                "source_key": key,
                "path": str(path.resolve()),
                "sha256": artifact_hash(path),
                "kind": sources.get(key, {}).get("kind"),
            }
        )
    return artifacts


def coverage_by_entry_id(coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(entry.get("id")): entry for entry in object_list(coverage.get("entries")) if isinstance(entry.get("id"), str)}


def coverage_by_route_rule(coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in object_list(coverage.get("entries")):
        route_rule = str(entry.get("route_rule") or "")
        if route_rule and route_rule not in lookup:
            lookup[route_rule] = entry
    return lookup


def duplicate_route_rules(coverage: dict[str, Any]) -> list[str]:
    counts = Counter(str(entry.get("route_rule") or "") for entry in object_list(coverage.get("entries")))
    return sorted(route_rule for route_rule, count in counts.items() if route_rule and count > 1)


def catalog_case_ids(catalog: dict[str, Any]) -> list[str]:
    return [str(case.get("case_id")) for case in object_list(catalog.get("cases")) if isinstance(case.get("case_id"), str)]


def catalog_cases_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(case.get("case_id")): case for case in object_list(catalog.get("cases")) if isinstance(case.get("case_id"), str)}


def role_sets(governance: dict[str, Any]) -> dict[str, set[str]]:
    roles = dict_value(governance.get("roles"))
    return {role: set(string_list(roles.get(role))) for role in ROLE_KEYS}


def roles_for_case(case_id: str, roles: dict[str, set[str]]) -> list[str]:
    return [role for role in ROLE_KEYS if case_id in roles.get(role, set())]


def corpus_family_relationships(governance: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    targets: dict[str, list[str]] = defaultdict(list)
    holdouts: dict[str, list[str]] = defaultdict(list)
    for link in object_list(governance.get("target_holdout_links")):
        family = str(link.get("family") or "")
        target_case_id = str(link.get("target_case_id") or "")
        if family and target_case_id:
            targets[target_case_id].append(family)
        if family:
            for holdout_id in string_list(link.get("holdout_case_ids")):
                holdouts[holdout_id].append(family)
    case_ids = sorted(set(targets) | set(holdouts))
    return {
        case_id: {
            "target_for_families": sorted(set(targets.get(case_id, []))),
            "holdout_for_families": sorted(set(holdouts.get(case_id, []))),
        }
        for case_id in case_ids
    }


def prompt_pack_case_ids(prompt_pack: dict[str, Any]) -> set[str]:
    case_ids: set[str] = set()
    for tier in object_list(prompt_pack.get("tiers")):
        case_ids.update(string_list(tier.get("case_ids")))
    return case_ids


def prompt_pack_tiers(prompt_pack: dict[str, Any]) -> list[str]:
    return [str(tier.get("tier")) for tier in object_list(prompt_pack.get("tiers")) if isinstance(tier.get("tier"), str)]


def docs_exist(config_root: Path, entry: dict[str, Any]) -> bool:
    return all(resolve_path(config_root, path).is_file() for path in string_list(entry.get("docs_examples")))


def evidence_artifact_paths(artifacts: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("path")) for item in artifacts]


def coverage_version(artifacts: list[dict[str, Any]]) -> str:
    coverage = next((item for item in artifacts if item.get("source_key") == "skill_coverage"), {})
    sha = str(coverage.get("sha256") or "")
    return sha[:12] if sha else "unknown"


def validation_error(error_id: str, message: str, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 191"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("acceptance_marker") != "PHASE191 PROMPT FAMILY DRIFT DETECTION PASS":
        errors.append(validation_error("policy.acceptance_marker", "policy.acceptance_marker must match the Phase 191 marker"))

    for key, value in source_path_config(policy).items():
        if not value:
            errors.append(validation_error(f"policy.source_path.{key}", f"{key} source path is required"))

    contract = dict_value(policy.get("decision_contract"))
    if string_list(contract.get("allowed_decisions")) != list(DECISIONS):
        errors.append(validation_error("decision_contract.allowed_decisions", "allowed decisions must match the Phase 191 contract"))
    if string_list(contract.get("allowed_weak_layers")) != list(WEAK_LAYERS):
        errors.append(validation_error("decision_contract.allowed_weak_layers", "allowed weak layers must match the Phase 191 contract"))
    if string_list(contract.get("allowed_required_verification_gates")) != list(VERIFICATION_GATES):
        errors.append(validation_error("decision_contract.allowed_required_verification_gates", "allowed verification gates must match the Phase 191 contract"))
    if string_list(contract.get("required_report_fields")) != list(REQUIRED_REPORT_FIELDS):
        errors.append(validation_error("decision_contract.required_report_fields", "required report fields must match the contextless audit contract"))

    probes = object_list(policy.get("drift_probe_cases"))
    seen_probe_ids: set[str] = set()
    decision_set = set()
    for index, probe in enumerate(probes):
        prefix = f"drift_probe_cases[{index}]"
        probe_id = str(probe.get("prompt_id") or "")
        if not probe_id:
            errors.append(validation_error(f"{prefix}.prompt_id", "prompt_id is required"))
        elif probe_id in seen_probe_ids:
            errors.append(validation_error(f"{prefix}.prompt_id", f"duplicate prompt_id {probe_id}"))
        seen_probe_ids.add(probe_id)
        decision = str(probe.get("expected_decision") or "")
        decision_set.add(decision)
        if decision not in DECISIONS:
            errors.append(validation_error(f"{prefix}.expected_decision", f"expected_decision must be one of {', '.join(DECISIONS)}"))
        if not str(probe.get("prompt_text") or "").strip():
            errors.append(validation_error(f"{prefix}.prompt_text", "prompt_text is required"))
        if not str(probe.get("expected_intent") or "").strip():
            errors.append(validation_error(f"{prefix}.expected_intent", "expected_intent is required"))
        if str(probe.get("required_verification_gate") or "") not in VERIFICATION_GATES:
            errors.append(validation_error(f"{prefix}.required_verification_gate", "required_verification_gate is unsupported"))
        weak_layers = string_list(probe.get("missing_or_weak_layer"))
        if not weak_layers:
            errors.append(validation_error(f"{prefix}.missing_or_weak_layer", "missing_or_weak_layer is required"))
        for layer in weak_layers:
            if layer not in WEAK_LAYERS:
                errors.append(validation_error(f"{prefix}.missing_or_weak_layer", f"unsupported weak layer {layer}"))
        if decision in {"partial_drift", "out_of_coverage"} and weak_layers == ["none"]:
            errors.append(validation_error(f"{prefix}.missing_or_weak_layer", "drift probes must name a weak layer"))
        if decision in {"in_coverage", "holdout"} and not string_list(probe.get("matched_coverage_entry_ids")):
            errors.append(validation_error(f"{prefix}.matched_coverage_entry_ids", "covered probes require matched coverage entry IDs"))
        if decision == "out_of_coverage" and string_list(probe.get("matched_coverage_entry_ids")):
            errors.append(validation_error(f"{prefix}.matched_coverage_entry_ids", "out-of-coverage probes cannot declare coverage entries"))
    if not probes:
        errors.append(validation_error("drift_probe_cases", "drift_probe_cases must be non-empty"))
    required_probe_decisions = set(string_list(contract.get("required_probe_decisions")))
    if required_probe_decisions != set(DECISIONS):
        errors.append(validation_error("decision_contract.required_probe_decisions", "required probe decisions must cover every Phase 191 decision"))
    missing_decisions = sorted(required_probe_decisions - decision_set)
    if missing_decisions:
        errors.append(validation_error("drift_probe_cases.required_decisions", "missing probe decisions: " + ", ".join(missing_decisions)))
    return errors


def validate_sources(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    paths: dict[str, Path],
) -> list[dict[str, str]]:
    errors = validate_policy(policy)
    source_kinds = dict_value(policy.get("source_kinds"))
    for key, path in paths.items():
        if not path.is_file():
            errors.append(validation_error(f"sources.{key}.missing", f"source file is missing: {path}"))
            continue
        expected_kind = str(source_kinds.get(key) or "")
        actual_kind = sources.get(key, {}).get("kind")
        if expected_kind and actual_kind != expected_kind:
            errors.append(validation_error(f"sources.{key}.kind", f"{key} kind must be {expected_kind}"))

    catalog = sources.get("catalog", {})
    coverage = sources.get("skill_coverage", {})
    governance = sources.get("corpus_governance", {})
    prompt_pack = sources.get("prompt_pack", {})
    case_ids = set(catalog_case_ids(catalog))
    if int(policy.get("expected_catalog_case_count") or 0) != len(case_ids):
        errors.append(validation_error("catalog.expected_case_count", "expected catalog case count must match current catalog"))
    coverage_entries = object_list(coverage.get("entries"))
    if int(policy.get("expected_coverage_entry_count") or 0) != len(coverage_entries):
        errors.append(validation_error("coverage.expected_entry_count", "expected coverage entry count must match current registry"))
    duplicates = duplicate_route_rules(coverage)
    if duplicates:
        errors.append(validation_error("coverage.duplicate_route_rules", "duplicate route rules: " + ", ".join(duplicates)))
    expected_role_counts = dict_value(policy.get("expected_corpus_role_counts"))
    roles = role_sets(governance)
    for role in ROLE_KEYS:
        expected_count = expected_role_counts.get(role)
        if expected_count is not None and int(expected_count) != len(roles[role]):
            errors.append(validation_error(f"corpus_roles.{role}", f"{role} count must match current governance policy"))
    assigned_ids = set().union(*roles.values()) if roles else set()
    unknown_role_ids = sorted(assigned_ids - case_ids)
    if unknown_role_ids:
        errors.append(validation_error("corpus_roles.unknown_case_ids", "unknown role case IDs: " + ", ".join(unknown_role_ids)))
    unknown_pack_ids = sorted(prompt_pack_case_ids(prompt_pack) - case_ids)
    if unknown_pack_ids:
        errors.append(validation_error("prompt_pack.unknown_case_ids", "unknown prompt pack case IDs: " + ", ".join(unknown_pack_ids)))
    expected_tiers = string_list(policy.get("expected_prompt_pack_tiers"))
    if expected_tiers and prompt_pack_tiers(prompt_pack) != expected_tiers:
        errors.append(validation_error("prompt_pack.tiers", "prompt pack tiers must match the Phase 191 contract"))
    coverage_by_id = coverage_by_entry_id(coverage)
    for probe in object_list(policy.get("drift_probe_cases")):
        for entry_id in string_list(probe.get("matched_coverage_entry_ids")):
            if entry_id not in coverage_by_id:
                errors.append(validation_error(f"drift_probe_cases.{probe.get('prompt_id')}.coverage", f"unknown coverage entry {entry_id}"))
    for entry in coverage_entries:
        if not string_list(entry.get("validation_suites")):
            errors.append(validation_error(f"coverage.{entry.get('id')}.validation_suites", "coverage entry must declare validation suites"))
        if not docs_exist(config_root, entry):
            errors.append(validation_error(f"coverage.{entry.get('id')}.docs_examples", "coverage entry docs examples must exist"))
    return errors


def classify_catalog_case(
    *,
    config_root: Path,
    case: dict[str, Any],
    coverage_lookup: dict[str, dict[str, Any]],
    roles: dict[str, set[str]],
    relationships: dict[str, dict[str, list[str]]],
    prompt_pack_ids: set[str],
    artifact_paths: list[str],
    coverage_version_or_commit: str,
    timestamp: str,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    route_rule = str(case.get("expected_rule") or "")
    expected_workflow = str(case.get("expected_workflow") or "")
    entry = coverage_lookup.get(route_rule)
    corpus_roles = roles_for_case(case_id, roles)
    relationship = relationships.get(case_id, {})
    target_for_families = sorted(set(string_list(relationship.get("target_for_families"))))
    holdout_for_families = sorted(set(string_list(relationship.get("holdout_for_families"))))
    overlapping_families = sorted(set(target_for_families) & set(holdout_for_families))
    holdout_independence_status = (
        "invalid_same_family_overlap"
        if overlapping_families
        else "cross_family_dual_role_allowed"
        if target_for_families and holdout_for_families
        else "independent_holdout"
        if holdout_for_families
        else "not_holdout"
    )
    weak_layers = ["none"]
    decision = "in_coverage"
    confidence = "high"
    matched_workflow = str(entry.get("selected_workflow") or "") if entry else ""
    matched_skill = string_list(entry.get("skill_ids")) if entry else []
    prompt_family = str(entry.get("prompt_family") or "unknown") if entry else "unknown"
    required_gate = "live_gateway_anythingllm" if case_id in prompt_pack_ids or "target" in corpus_roles or "holdout" in corpus_roles else "static_registry"
    recommended = "keep in governed regression; rerun live proof when this prompt or coverage entry changes"
    reasoning = "catalog prompt maps to an implemented coverage entry with matching workflow"

    if not entry:
        decision = "out_of_coverage"
        confidence = "high"
        weak_layers = ["router", "skill", "test_coverage"]
        required_gate = "new_skill_tool_proposal"
        recommended = "create a bounded skill/tool proposal or mark the prompt unsupported before adding it to field testing"
        reasoning = "catalog prompt expected rule has no coverage registry entry"
    elif str(entry.get("status") or "") != "implemented":
        decision = "partial_drift"
        confidence = "high"
        weak_layers = ["skill", "test_coverage", "runtime_proof"]
        required_gate = "new_skill_tool_proposal"
        recommended = "complete the planned coverage entry before using this prompt in founder testing"
        reasoning = "coverage entry exists but is not implemented"
    elif matched_workflow != expected_workflow:
        decision = "partial_drift"
        confidence = "high"
        weak_layers = ["workflow", "router"]
        required_gate = "workflow_repair"
        recommended = "repair the router or prompt governance expectation before live field testing"
        reasoning = "coverage entry workflow does not match the catalog expectation"
    elif not docs_exist(config_root, entry):
        decision = "partial_drift"
        confidence = "high"
        weak_layers = ["docs", "prompt_governance"]
        required_gate = "prompt_governance_update"
        recommended = "restore docs examples before promoting or testing this prompt family"
        reasoning = "coverage entry is implemented but its documentation references are stale"
    elif overlapping_families:
        decision = "partial_drift"
        confidence = "high"
        weak_layers = ["prompt_governance"]
        required_gate = "prompt_governance_update"
        recommended = "repair corpus governance so a prompt is not target and holdout for the same family"
        reasoning = "prompt is both target and holdout for the same governed family"
    elif "holdout" in corpus_roles:
        decision = "holdout"
        recommended = "keep as holdout; do not promote related targets without blind-baseline and local-stack proof"
        if holdout_independence_status == "cross_family_dual_role_allowed":
            reasoning = "catalog prompt is a holdout for one governed family and a target for a different governed family"
        else:
            reasoning = "catalog prompt is covered and explicitly assigned a holdout role"

    return {
        "prompt_id": case_id,
        "prompt_text": str(case.get("prompt") or ""),
        "prompt_family": prompt_family,
        "decision": decision,
        "confidence": confidence,
        "expected_intent": str(case.get("baseline_target") or ""),
        "expected_workflow": expected_workflow,
        "matched_workflow": matched_workflow,
        "expected_route_rule": route_rule,
        "matched_skill": matched_skill,
        "matched_router_path": route_rule if entry else "",
        "corpus_roles": corpus_roles,
        "target_for_families": target_for_families,
        "holdout_for_families": holdout_for_families,
        "holdout_independence_status": holdout_independence_status,
        "target_root": str(case.get("target_root") or ""),
        "missing_or_weak_layer": weak_layers,
        "evidence_artifacts_checked": artifact_paths,
        "reasoning_summary": reasoning,
        "required_verification_gate": required_gate,
        "required_verification_gates": [required_gate],
        "recommended_next_action": recommended,
        "coverage_version_or_commit": coverage_version_or_commit,
        "timestamp": timestamp,
    }


def build_probe_record(
    *,
    probe: dict[str, Any],
    coverage_entries: dict[str, dict[str, Any]],
    artifact_paths: list[str],
    coverage_version_or_commit: str,
    timestamp: str,
) -> dict[str, Any]:
    matched_entries = [coverage_entries[entry_id] for entry_id in string_list(probe.get("matched_coverage_entry_ids")) if entry_id in coverage_entries]
    skills: list[str] = []
    for entry in matched_entries:
        for skill in string_list(entry.get("skill_ids")):
            if skill not in skills:
                skills.append(skill)
    return {
        "prompt_id": str(probe.get("prompt_id") or ""),
        "prompt_text": str(probe.get("prompt_text") or ""),
        "prompt_family": str(probe.get("prompt_family") or ""),
        "decision": str(probe.get("expected_decision") or ""),
        "confidence": str(probe.get("confidence") or "medium"),
        "expected_intent": str(probe.get("expected_intent") or ""),
        "expected_workflow": str(probe.get("expected_workflow") or ""),
        "matched_workflow": str(probe.get("expected_workflow") or (matched_entries[0].get("selected_workflow") if matched_entries else "")),
        "expected_route_rule": str(probe.get("expected_route_rule") or ""),
        "matched_skill": skills,
        "matched_router_path": str(probe.get("expected_route_rule") or (matched_entries[0].get("route_rule") if matched_entries else "")),
        "corpus_roles": [],
        "target_root": "",
        "missing_or_weak_layer": string_list(probe.get("missing_or_weak_layer")),
        "evidence_artifacts_checked": artifact_paths,
        "reasoning_summary": "drift probe uses the governed Phase 191 contextless audit decision contract",
        "required_verification_gate": str(probe.get("required_verification_gate") or ""),
        "required_verification_gates": [str(probe.get("required_verification_gate") or "")],
        "recommended_next_action": str(probe.get("recommended_next_action") or ""),
        "coverage_version_or_commit": coverage_version_or_commit,
        "timestamp": timestamp,
    }


def active_blocking_drift(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("source") == "catalog" and record.get("decision") in {"partial_drift", "out_of_coverage"}
    ]


def validate_records(policy: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for record in records:
        record_id = str(record.get("prompt_id") or "<unknown>")
        for field in REQUIRED_REPORT_FIELDS:
            if field not in record:
                errors.append(validation_error(f"records.{record_id}.{field}", f"record missing required field {field}"))
        decision = str(record.get("decision") or "")
        if decision not in DECISIONS:
            errors.append(validation_error(f"records.{record_id}.decision", f"unsupported decision {decision}"))
        for layer in string_list(record.get("missing_or_weak_layer")):
            if layer not in WEAK_LAYERS:
                errors.append(validation_error(f"records.{record_id}.missing_or_weak_layer", f"unsupported weak layer {layer}"))
        if str(record.get("required_verification_gate") or "") not in VERIFICATION_GATES:
            errors.append(validation_error(f"records.{record_id}.required_verification_gate", "unsupported required verification gate"))
    allowed = int(policy.get("allowed_active_catalog_blocking_drift_count") or 0)
    blocking = active_blocking_drift(records)
    if len(blocking) > allowed:
        errors.append(
            validation_error(
                "records.active_catalog_blocking_drift",
                f"active catalog blocking drift count {len(blocking)} exceeds allowed count {allowed}",
            )
        )
    return errors


def build_prompt_family_drift_detection_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    paths: dict[str, Path],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    timestamp = utc_timestamp()
    artifacts = source_artifacts(sources, paths)
    artifact_paths = evidence_artifact_paths(artifacts)
    coverage_sha = coverage_version(artifacts)
    catalog = sources.get("catalog", {})
    coverage = sources.get("skill_coverage", {})
    governance = sources.get("corpus_governance", {})
    prompt_pack = sources.get("prompt_pack", {})
    coverage_lookup = coverage_by_route_rule(coverage)
    coverage_entries = coverage_by_entry_id(coverage)
    roles = role_sets(governance)
    relationships = corpus_family_relationships(governance)
    pack_ids = prompt_pack_case_ids(prompt_pack)

    records: list[dict[str, Any]] = []
    for case in sorted(object_list(catalog.get("cases")), key=lambda item: str(item.get("case_id") or "")):
        record = classify_catalog_case(
            config_root=config_root,
            case=case,
            coverage_lookup=coverage_lookup,
            roles=roles,
            relationships=relationships,
            prompt_pack_ids=pack_ids,
            artifact_paths=artifact_paths,
            coverage_version_or_commit=coverage_sha,
            timestamp=timestamp,
        )
        record["source"] = "catalog"
        records.append(record)
    for probe in object_list(policy.get("drift_probe_cases")):
        record = build_probe_record(
            probe=probe,
            coverage_entries=coverage_entries,
            artifact_paths=artifact_paths,
            coverage_version_or_commit=coverage_sha,
            timestamp=timestamp,
        )
        record["source"] = "drift_probe"
        records.append(record)

    errors = validate_sources(config_root=config_root, policy=policy, sources=sources, paths=paths)
    errors.extend(validate_records(policy, records))
    decision_counts = dict(sorted(Counter(str(record.get("decision") or "") for record in records).items()))
    decision_counts_by_source = {
        source: dict(
            sorted(
                Counter(
                    str(record.get("decision") or "")
                    for record in records
                    if str(record.get("source") or "") == source
                ).items()
            )
        )
        for source in ("catalog", "drift_probe")
    }
    weak_layer_counts = dict(sorted(Counter(layer for record in records for layer in string_list(record.get("missing_or_weak_layer"))).items()))
    gate_counts = dict(sorted(Counter(str(record.get("required_verification_gate") or "") for record in records).items()))
    catalog_records = [record for record in records if record.get("source") == "catalog"]
    probe_records = [record for record in records if record.get("source") == "drift_probe"]
    blocking = active_blocking_drift(records)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": PromptFamilyDriftDetectionStatus.FAILED.value if errors else PromptFamilyDriftDetectionStatus.PASSED.value,
        "generated_at": timestamp,
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_artifacts": artifacts,
        "summary": {
            "catalog_case_count": len(catalog_records),
            "probe_case_count": len(probe_records),
            "total_record_count": len(records),
            "decision_counts": decision_counts,
            "decision_counts_by_source": decision_counts_by_source,
            "weak_layer_counts": weak_layer_counts,
            "verification_gate_counts": gate_counts,
            "active_catalog_blocking_drift_count": len(blocking),
            "live_runtime_required_count": gate_counts.get("live_gateway_anythingllm", 0),
            "validation_error_count": len(errors),
            "next_action": "work Phase 192 next" if not errors else "repair prompt-family drift findings before adding prompt families",
        },
        "records": records,
        "validation_errors": errors,
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    stable.pop("markdown_path", None)
    for record in object_list(stable.get("records")):
        record.pop("timestamp", None)
    return stable


def validate_prompt_family_drift_detection_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    paths: dict[str, Path],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_prompt_family_drift_detection_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        paths=paths,
        policy_path=policy_path,
    )
    if stable_report(report) != stable_report(expected):
        return ["report must match rebuilt prompt-family drift detection report"]
    return []


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Prompt Family Drift Detection",
        "",
        f"- Status: {report['status']}",
        f"- Catalog cases: {report['summary']['catalog_case_count']}",
        f"- Drift probes: {report['summary']['probe_case_count']}",
        f"- Active catalog blocking drift: {report['summary']['active_catalog_blocking_drift_count']}",
        f"- Live runtime required records: {report['summary']['live_runtime_required_count']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Decisions",
        "",
    ]
    for decision, count in dict_value(report["summary"].get("decision_counts")).items():
        lines.append(f"- {decision}: {count}")
    lines.extend(["", "## Drift Probes", ""])
    for record in object_list(report.get("records")):
        if record.get("source") == "drift_probe":
            lines.append(f"- `{record.get('prompt_id')}`: {record.get('decision')} - {record.get('recommended_next_action')}")
    lines.extend(["", "## Catalog Coverage", ""])
    for decision in DECISIONS:
        decision_records = [
            record
            for record in object_list(report.get("records"))
            if record.get("source") == "catalog" and record.get("decision") == decision
        ]
        if not decision_records:
            continue
        lines.extend(["", f"### {decision}", ""])
        for record in decision_records:
            roles_text = ",".join(string_list(record.get("corpus_roles"))) or "none"
            target_families = ",".join(string_list(record.get("target_for_families"))) or "none"
            holdout_families = ",".join(string_list(record.get("holdout_for_families"))) or "none"
            lines.append(
                f"- `{record.get('prompt_id')}` `{record.get('prompt_family')}` roles={roles_text} "
                f"target_for={target_families} holdout_for={holdout_families} "
                f"gate={record.get('required_verification_gate')} next={record.get('recommended_next_action')}"
            )
    if report.get("validation_errors"):
        lines.extend(["", "## Validation Errors", ""])
        for error in object_list(report.get("validation_errors")):
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_prompt_family_drift_detection(config: PromptFamilyDriftDetectionConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    paths = source_paths(config_root, policy)
    sources = {key: read_json_object(path) for key, path in paths.items() if path.is_file()}
    report = build_prompt_family_drift_detection_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        paths=paths,
        policy_path=policy_path,
    )
    validation_errors = validate_prompt_family_drift_detection_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        paths=paths,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = PromptFamilyDriftDetectionStatus.FAILED.value
        report["validation_errors"] = object_list(report.get("validation_errors")) + [
            validation_error(f"report.{index}", error) for index, error in enumerate(validation_errors)
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["next_action"] = "repair prompt-family drift findings before adding prompt families"
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_markdown(markdown_path, report)
        report["markdown_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
