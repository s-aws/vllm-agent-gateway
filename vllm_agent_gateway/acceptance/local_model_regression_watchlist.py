"""Governance for the Phase 139 local-model regression watchlist."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_WATCHLIST_KIND = "local_model_regression_watchlist"
EXPECTED_REPORT_KIND = "local_model_regression_watchlist_report"
EXPECTED_PHASE = 139
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_WATCHLIST_PATH = Path("runtime") / "local_model_regression_watchlist.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "local-model-regression-watchlist" / "phase139"
FORBIDDEN_TAGS = {"draft-only", "apply-proof", "disposable-copy"}
FORBIDDEN_WORKFLOWS = {"refactor.single_path"}
ALLOWED_SEVERITIES = {"blocker", "advisory"}
ALLOWED_REPAIR_OWNERS = {
    "AnythingLLM configuration",
    "context gathering",
    "deterministic formatter",
    "documentation",
    "model capability",
    "routing",
    "safety boundary",
    "skill/tool selection",
    "test coverage",
}
DETERMINISTIC_SYMPTOM_TERMS = {
    "artifact",
    "dirty",
    "evidence",
    "finding",
    "gate",
    "marker",
    "mutation",
    "route",
    "run id",
    "score",
    "selected_workflow",
    "stale hash",
    "status",
    "unsafe",
    "workflow",
}
REQUIRED_GATE_IDS = {
    "chat_transcript_quality",
    "founder_feedback_loop",
    "founder_field_prompt_eval",
    "founder_test_prompt_pack",
    "fresh_local_model_drift",
    "prompt_tightening_recommendations",
    "skill_tool_coverage_gap",
    "stable_chat_quality_release",
}
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}


class LocalModelRegressionWatchlistStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LocalModelRegressionWatchlistConfig:
    config_root: Path
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"local-model-regression-watchlist-{utc_timestamp()}.json"


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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def tier_case_ids(pack: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(tier.get("tier")): string_list(tier.get("case_ids"))
        for tier in object_list(pack.get("tiers"))
        if isinstance(tier.get("tier"), str)
    }


def ordered_pack_case_ids(pack: dict[str, Any]) -> list[str]:
    return [case_id for ids in tier_case_ids(pack).values() for case_id in ids]


def catalog_cases(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(case.get("case_id")): case
        for case in object_list(catalog.get("cases"))
        if isinstance(case.get("case_id"), str)
    }


def gate_entries_by_id(watchlist: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(gate.get("gate_id")): gate
        for gate in object_list(watchlist.get("gate_catalog"))
        if isinstance(gate.get("gate_id"), str) and gate.get("gate_id")
    }


def item_case_ids(item: dict[str, Any]) -> list[str]:
    return string_list(item.get("case_ids"))


def prompt_pack_catalog_path(config_root: Path, prompt_pack: dict[str, Any]) -> Path:
    path_value = prompt_pack.get("catalog_path") if isinstance(prompt_pack.get("catalog_path"), str) else ""
    return resolve_path(config_root, path_value) if path_value else Path()


def deterministic_symptoms(symptoms: list[str]) -> bool:
    for symptom in symptoms:
        lowered = symptom.lower()
        if not any(term in lowered for term in DETERMINISTIC_SYMPTOM_TERMS):
            return False
    return True


def gate_artifact_errors(
    *,
    gates_by_id: dict[str, dict[str, Any]],
    config_root: Path,
    require_artifacts: bool,
) -> list[str]:
    errors: list[str] = []
    for gate_id, gate in sorted(gates_by_id.items()):
        artifact_path_value = gate.get("artifact_path")
        if not isinstance(artifact_path_value, str) or not artifact_path_value.strip():
            errors.append(f"gate_catalog[{gate_id}].artifact_path is required")
            continue
        artifact_path = resolve_path(config_root, artifact_path_value)
        if not artifact_path.is_file():
            if require_artifacts:
                errors.append(f"gate_catalog[{gate_id}].artifact_path does not exist: {artifact_path_value}")
            continue
        try:
            artifact = read_json_object(artifact_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"gate_catalog[{gate_id}].artifact_path is not a readable JSON object: {type(exc).__name__}")
            continue
        status = artifact.get("status")
        if isinstance(status, str) and status != "passed":
            errors.append(f"gate_catalog[{gate_id}] artifact status must be passed")
        quality_status = artifact.get("quality_status")
        if quality_status == "blocker":
            errors.append(f"gate_catalog[{gate_id}] artifact quality_status is blocker")
        summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
        for key in ("blocker_count", "blocker_finding_count", "failed_smoke_case_count", "error_count"):
            value = summary.get(key)
            if isinstance(value, int) and value > 0:
                errors.append(f"gate_catalog[{gate_id}] artifact summary.{key} must be 0")
        if artifact.get("readiness") == "blocked":
            errors.append(f"gate_catalog[{gate_id}] artifact readiness is blocked")
    return errors


def validate_item_against_case(
    item: dict[str, Any],
    *,
    case: dict[str, Any],
    expected_tier: str,
    gates_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    watch_id = str(item.get("watch_id") or "<missing>")
    prefix = f"watchlist.items[{watch_id}]"
    case_id = str(case.get("case_id"))
    if item_case_ids(item) != [case_id]:
        errors.append(f"{prefix}.case_ids must contain exactly {case_id}")
    if item.get("tier") != expected_tier:
        errors.append(f"{prefix}.tier must match founder prompt pack tier {expected_tier}")
    if expected_tier == "smoke" and item.get("severity") != "blocker":
        errors.append(f"{prefix}.severity must be blocker for smoke cases")
    if expected_tier == "expanded_read_only" and item.get("severity") == "blocker":
        errors.append(f"{prefix}.severity must be lower than smoke severity for expanded_read_only cases")
    if string_list(item.get("expected_workflows")) != [case.get("expected_workflow")]:
        errors.append(f"{prefix}.expected_workflows must match prompt catalog expected_workflow")
    if string_list(item.get("expected_rules")) != [case.get("expected_rule")]:
        errors.append(f"{prefix}.expected_rules must match prompt catalog expected_rule")
    if string_list(item.get("target_roots")) != [case.get("target_root")]:
        errors.append(f"{prefix}.target_roots must match prompt catalog target_root")
    if string_list(item.get("required_markers")) != string_list(case.get("expected_markers")):
        errors.append(f"{prefix}.required_markers must match prompt catalog expected_markers")
    if string_list(item.get("forbidden_markers")) != string_list(case.get("forbidden_markers")):
        errors.append(f"{prefix}.forbidden_markers must match prompt catalog forbidden_markers")
    if item.get("severity") not in ALLOWED_SEVERITIES:
        errors.append(f"{prefix}.severity must be blocker or advisory")
    if item.get("repair_owner") not in ALLOWED_REPAIR_OWNERS:
        errors.append(f"{prefix}.repair_owner is not an allowed Priority 0 owner")
    for field in ("founder_impact", "prompt_family", "repair_path", "risk_statement"):
        if not isinstance(item.get(field), str) or len(str(item.get(field)).strip()) < 10:
            errors.append(f"{prefix}.{field} is required")
    if not isinstance(item.get("risk_class"), str) or not item["risk_class"].strip():
        errors.append(f"{prefix}.risk_class is required")
    if not isinstance(item.get("risk_statement"), str) or len(item["risk_statement"].strip()) < 50:
        errors.append(f"{prefix}.risk_statement must be concrete")
    symptoms = string_list(item.get("expected_symptoms"))
    if len(symptoms) < 2:
        errors.append(f"{prefix}.expected_symptoms must include at least two deterministic symptoms")
    elif not deterministic_symptoms(symptoms):
        errors.append(f"{prefix}.expected_symptoms must use deterministic marker, gate, route, score, hash, or finding checks")
    blocker_conditions = string_list(item.get("blocker_conditions"))
    if len(blocker_conditions) < 2:
        errors.append(f"{prefix}.blocker_conditions must include at least two conditions")
    elif not deterministic_symptoms(blocker_conditions):
        errors.append(f"{prefix}.blocker_conditions must use deterministic checks")
    related_gates = string_list(item.get("related_gates"))
    if len(related_gates) < 3:
        errors.append(f"{prefix}.related_gates must include at least three existing gates")
    unknown_gates = sorted(set(related_gates) - set(gates_by_id))
    if unknown_gates:
        errors.append(f"{prefix}.related_gates references unknown gate(s): " + ", ".join(unknown_gates))
    tags = set(string_list(case.get("tags")))
    forbidden_tags = sorted(tags & FORBIDDEN_TAGS)
    if forbidden_tags:
        errors.append(f"{prefix} prompt catalog case has forbidden tag(s): " + ", ".join(forbidden_tags))
    if case.get("expected_workflow") in FORBIDDEN_WORKFLOWS:
        errors.append(f"{prefix} prompt catalog case uses forbidden workflow {case.get('expected_workflow')}")
    return errors


def validate_watchlist(
    watchlist: dict[str, Any],
    *,
    prompt_pack: dict[str, Any],
    prompt_catalog: dict[str, Any],
    config_root: Path,
    require_artifacts: bool = False,
) -> list[str]:
    errors: list[str] = []
    if watchlist.get("schema_version") != SCHEMA_VERSION:
        errors.append("watchlist.schema_version must be 1")
    if watchlist.get("kind") != EXPECTED_WATCHLIST_KIND:
        errors.append(f"watchlist.kind must be {EXPECTED_WATCHLIST_KIND}")
    if watchlist.get("phase") != EXPECTED_PHASE:
        errors.append("watchlist.phase must be 139")
    if watchlist.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"watchlist.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    prompt_pack_path_value = watchlist.get("prompt_pack_path")
    if not isinstance(prompt_pack_path_value, str) or not resolve_path(config_root, prompt_pack_path_value).is_file():
        errors.append("watchlist.prompt_pack_path must reference an existing prompt pack")
    if prompt_pack.get("kind") != "founder_test_prompt_pack":
        errors.append("prompt_pack.kind must be founder_test_prompt_pack")
    if prompt_catalog.get("kind") != "prompt_catalog":
        errors.append("prompt_catalog.kind must be prompt_catalog")

    tiers = tier_case_ids(prompt_pack)
    pack_case_ids = ordered_pack_case_ids(prompt_pack)
    if not tiers.get("smoke"):
        errors.append("prompt_pack smoke tier is required")
    if not tiers.get("expanded_read_only"):
        errors.append("prompt_pack expanded_read_only tier is required")
    if duplicate_values(pack_case_ids):
        errors.append("prompt_pack contains duplicate case IDs")
    cases_by_id = catalog_cases(prompt_catalog)
    unknown_pack_cases = sorted(set(pack_case_ids) - set(cases_by_id))
    if unknown_pack_cases:
        errors.append("prompt_pack references unknown catalog cases: " + ", ".join(unknown_pack_cases))
    workflows = {str(cases_by_id[case_id].get("expected_workflow")) for case_id in pack_case_ids if case_id in cases_by_id}
    for workflow in ("code_investigation.plan", "code_context.lookup", "task.decompose"):
        if workflow not in workflows:
            errors.append(f"watchlist prompt pack must cover workflow {workflow}")
    target_roots = {str(cases_by_id[case_id].get("target_root")) for case_id in pack_case_ids if case_id in cases_by_id}
    missing_roots = sorted(REQUIRED_TARGET_ROOTS - target_roots)
    if missing_roots:
        errors.append("watchlist prompt pack missing required target roots: " + ", ".join(missing_roots))

    gates_by_id = gate_entries_by_id(watchlist)
    if set(gates_by_id) != REQUIRED_GATE_IDS:
        errors.append("watchlist.gate_catalog must exactly cover required Phase 139 gate IDs")
    for gate_id, gate in gates_by_id.items():
        if gate.get("status") != "implemented":
            errors.append(f"gate_catalog[{gate_id}].status must be implemented")
        if not isinstance(gate.get("phase"), int):
            errors.append(f"gate_catalog[{gate_id}].phase must be an integer")
    errors.extend(gate_artifact_errors(gates_by_id=gates_by_id, config_root=config_root, require_artifacts=require_artifacts))

    items = object_list(watchlist.get("items"))
    if len(items) != len(pack_case_ids):
        errors.append("watchlist.items must contain exactly one item for each prompt pack case")
    watch_ids = [str(item.get("watch_id")) for item in items if isinstance(item.get("watch_id"), str)]
    if len(watch_ids) != len(items):
        errors.append("each watchlist item must include watch_id")
    duplicates = duplicate_values(watch_ids)
    if duplicates:
        errors.append("watchlist.items must not contain duplicate watch_id values: " + ", ".join(duplicates))
    assigned_case_ids = [case_id for item in items for case_id in item_case_ids(item)]
    missing_case_ids = sorted(set(pack_case_ids) - set(assigned_case_ids))
    orphan_case_ids = sorted(set(assigned_case_ids) - set(pack_case_ids))
    duplicated_case_ids = duplicate_values(assigned_case_ids)
    if missing_case_ids:
        errors.append("watchlist missing prompt pack case(s): " + ", ".join(missing_case_ids))
    if orphan_case_ids:
        errors.append("watchlist contains orphan case(s): " + ", ".join(orphan_case_ids))
    if duplicated_case_ids:
        errors.append("watchlist duplicates prompt pack case(s): " + ", ".join(duplicated_case_ids))

    tier_by_case = {case_id: tier for tier, case_ids in tiers.items() for case_id in case_ids}
    for item in items:
        ids = item_case_ids(item)
        if len(ids) != 1 or ids[0] not in cases_by_id:
            continue
        errors.extend(
            validate_item_against_case(
                item,
                case=cases_by_id[ids[0]],
                expected_tier=tier_by_case.get(ids[0], ""),
                gates_by_id=gates_by_id,
            )
        )
    return errors


def source_refs(
    *,
    watchlist_path: Path | None,
    prompt_pack_path: Path | None,
    prompt_catalog_path: Path | None,
) -> dict[str, dict[str, str | None]]:
    return {
        "watchlist": {
            "path": str(watchlist_path or DEFAULT_WATCHLIST_PATH),
            "sha256": artifact_hash(watchlist_path),
        },
        "prompt_pack": {
            "path": str(prompt_pack_path or ""),
            "sha256": artifact_hash(prompt_pack_path),
        },
        "prompt_catalog": {
            "path": str(prompt_catalog_path or ""),
            "sha256": artifact_hash(prompt_catalog_path),
        },
    }


def gate_artifact_refs(
    *,
    gates_by_id: dict[str, dict[str, Any]],
    config_root: Path,
) -> dict[str, dict[str, str | None]]:
    refs: dict[str, dict[str, str | None]] = {}
    for gate_id, gate in sorted(gates_by_id.items()):
        path_value = gate.get("artifact_path") if isinstance(gate.get("artifact_path"), str) else ""
        path = resolve_path(config_root, path_value) if path_value else Path()
        refs[gate_id] = {"path": path_value, "sha256": artifact_hash(path)}
    return refs


def build_local_model_regression_watchlist_report(
    *,
    config_root: Path,
    watchlist: dict[str, Any],
    prompt_pack: dict[str, Any],
    prompt_catalog: dict[str, Any],
    watchlist_path: Path | None = None,
    prompt_pack_path: Path | None = None,
    prompt_catalog_path: Path | None = None,
    require_artifacts: bool = False,
) -> dict[str, Any]:
    errors = validate_watchlist(
        watchlist,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        config_root=config_root,
        require_artifacts=require_artifacts,
    )
    items = object_list(watchlist.get("items"))
    tiers = tier_case_ids(prompt_pack)
    case_coverage = {
        case_id: [str(item.get("watch_id")) for item in items if item_case_ids(item) == [case_id]]
        for case_id in ordered_pack_case_ids(prompt_pack)
    }
    owner_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    for item in items:
        owner = str(item.get("repair_owner") or "unknown")
        severity = str(item.get("severity") or "unknown")
        tier = str(item.get("tier") or "unknown")
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": LocalModelRegressionWatchlistStatus.PASSED.value
        if not errors
        else LocalModelRegressionWatchlistStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "sources": source_refs(
            watchlist_path=watchlist_path,
            prompt_pack_path=prompt_pack_path,
            prompt_catalog_path=prompt_catalog_path,
        ),
        "gate_artifacts": gate_artifact_refs(gates_by_id=gate_entries_by_id(watchlist), config_root=config_root),
        "summary": {
            "watch_item_count": len(items),
            "gate_count": len(object_list(watchlist.get("gate_catalog"))),
            "prompt_pack_case_count": len(ordered_pack_case_ids(prompt_pack)),
            "covered_prompt_pack_case_count": sum(1 for values in case_coverage.values() if values),
            "smoke_case_count": len(tiers.get("smoke", [])),
            "expanded_read_only_case_count": len(tiers.get("expanded_read_only", [])),
            "blocker_watch_count": severity_counts.get("blocker", 0),
            "advisory_watch_count": severity_counts.get("advisory", 0),
            "repair_owner_count": len(owner_counts),
            "error_count": len(errors),
        },
        "case_coverage": case_coverage,
        "repair_owner_counts": dict(sorted(owner_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
        "tier_counts": dict(sorted(tier_counts.items())),
        "errors": errors,
    }


def validate_local_model_regression_watchlist_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    watchlist: dict[str, Any],
    prompt_pack: dict[str, Any],
    prompt_catalog: dict[str, Any],
    watchlist_path: Path | None = None,
    prompt_pack_path: Path | None = None,
    prompt_catalog_path: Path | None = None,
    require_artifacts: bool = False,
) -> list[str]:
    expected = build_local_model_regression_watchlist_report(
        config_root=config_root,
        watchlist=watchlist,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        watchlist_path=watchlist_path,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
        require_artifacts=require_artifacts,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "sources",
        "gate_artifacts",
        "summary",
        "case_coverage",
        "repair_owner_counts",
        "severity_counts",
        "tier_counts",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt local model regression watchlist report")
    return errors


def run_local_model_regression_watchlist_gate(config: LocalModelRegressionWatchlistConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    watchlist_path = resolve_path(config_root, config.watchlist_path)
    watchlist = read_json_object(watchlist_path) if watchlist_path.is_file() else {}
    prompt_pack_path_value = watchlist.get("prompt_pack_path") if isinstance(watchlist.get("prompt_pack_path"), str) else ""
    prompt_pack_path = resolve_path(config_root, prompt_pack_path_value) if prompt_pack_path_value else Path()
    prompt_pack = read_json_object(prompt_pack_path) if prompt_pack_path.is_file() else {}
    prompt_catalog_path = prompt_pack_catalog_path(config_root, prompt_pack)
    prompt_catalog = read_json_object(prompt_catalog_path) if prompt_catalog_path.is_file() else {}
    missing_errors = []
    for label, path in (
        ("watchlist", watchlist_path),
        ("prompt pack", prompt_pack_path),
        ("prompt catalog", prompt_catalog_path),
    ):
        if config.require_artifacts and not path.is_file():
            missing_errors.append(f"required {label} artifact is missing: {path}")
    report = build_local_model_regression_watchlist_report(
        config_root=config_root,
        watchlist=watchlist,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        watchlist_path=watchlist_path,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
        require_artifacts=config.require_artifacts,
    )
    validation_errors = validate_local_model_regression_watchlist_report(
        report,
        config_root=config_root,
        watchlist=watchlist,
        prompt_pack=prompt_pack,
        prompt_catalog=prompt_catalog,
        watchlist_path=watchlist_path,
        prompt_pack_path=prompt_pack_path,
        prompt_catalog_path=prompt_catalog_path,
        require_artifacts=config.require_artifacts,
    )
    if missing_errors or validation_errors:
        report["status"] = LocalModelRegressionWatchlistStatus.FAILED.value
        report["errors"] = missing_errors + validation_errors
        report["summary"]["error_count"] = len(report["errors"])
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
