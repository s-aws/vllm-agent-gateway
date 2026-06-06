"""Skill batch admission validation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.skills.evals import (
    ALLOWED_LIVE_SUITES,
    MANUAL_ARTIFACT_IDS,
    SKILL_EVALS_PATH,
    live_mapping_for_case,
    skill_output_artifacts,
    workflow_result_artifacts,
)
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    eval_catalog_ids,
    existing_skill_ids_and_route_keys,
    semantic_intent_conflicts,
    read_json_object,
    registry_ids,
    validate_doc_refs,
    validate_eval_case_item,
    validate_skill_item,
    validate_skill_registry_manifest,
)


DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-batches"
REQUIRED_BATCH_FIELDS = {
    "schema_version",
    "kind",
    "id",
    "description",
    "doc_refs",
    "skills",
    "eval_cases",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path, batch_id: str) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"{batch_id}-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_batch_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillRegistryError(f"Missing skill batch manifest: {path}", code="missing_skill_batch") from exc
    except json.JSONDecodeError as exc:
        raise SkillRegistryError(f"Invalid skill batch manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillRegistryError("Skill batch manifest must contain a JSON object.")
    return value


def batch_id_from_manifest(manifest: dict[str, Any]) -> str:
    batch_id = manifest.get("id")
    if isinstance(batch_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", batch_id):
        return batch_id
    return "skill-batch"


def validate_batch_header(manifest: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_BATCH_FIELDS - set(manifest))
    if missing:
        raise SkillRegistryError(f"Skill batch manifest is missing field(s): {', '.join(missing)}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SkillRegistryError("Skill batch manifest schema_version must be 1.")
    if manifest.get("kind") != "skill_batch_manifest":
        raise SkillRegistryError("Skill batch manifest kind must be skill_batch_manifest.")
    batch_id = manifest["id"]
    if not isinstance(batch_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", batch_id):
        raise SkillRegistryError("Skill batch manifest id is invalid.")
    description = manifest["description"]
    if not isinstance(description, str) or len(description.strip()) < 20:
        raise SkillRegistryError("Skill batch manifest description must be a descriptive string.")
    skills = manifest["skills"]
    if not isinstance(skills, list) or not skills:
        raise SkillRegistryError("Skill batch manifest skills must be a non-empty list.")
    eval_cases = manifest["eval_cases"]
    if not isinstance(eval_cases, list) or not eval_cases:
        raise SkillRegistryError("Skill batch manifest eval_cases must be a non-empty list.")
    return {
        "id": batch_id,
        "description": description,
        "skills": skills,
        "eval_cases": eval_cases,
    }


def validate_batch_eval_cases(
    raw_eval_cases: list[Any],
    *,
    workflow_ids: set[str],
    existing_eval_case_ids: set[str],
) -> dict[str, dict[str, Any]]:
    eval_cases: dict[str, dict[str, Any]] = {}
    for raw_case in raw_eval_cases:
        eval_case = validate_eval_case_item(raw_case, workflow_ids=workflow_ids)
        eval_case_id = eval_case["id"]
        if eval_case_id in existing_eval_case_ids:
            raise SkillRegistryError(f"Skill batch eval case already exists: {eval_case_id}")
        if eval_case_id in eval_cases:
            raise SkillRegistryError(f"Duplicate skill batch eval case id: {eval_case_id}")
        live_suite = eval_case["live_suite"]
        if live_suite not in ALLOWED_LIVE_SUITES:
            raise SkillRegistryError(f"Skill batch eval case {eval_case_id} has unsupported live_suite.")
        eval_cases[eval_case_id] = eval_case
    return eval_cases


def validate_batch_skill_items(
    raw_skills: list[Any],
    *,
    config_root: Path,
    workflow_ids: set[str],
    tool_ids: set[str],
    eval_fixture_ids: set[str],
    existing_eval_case_ids: set[str],
    batch_eval_cases: dict[str, dict[str, Any]],
    existing_skill_ids: set[str],
    existing_route_keys: set[str],
) -> dict[str, dict[str, Any]]:
    skills: dict[str, dict[str, Any]] = {}
    route_keys: dict[str, str] = {}
    allowed_eval_case_ids = existing_eval_case_ids | set(batch_eval_cases)
    for raw_skill in raw_skills:
        skill = validate_skill_item(
            raw_skill,
            config_root=config_root,
            workflow_ids=workflow_ids,
            tool_ids=tool_ids,
            eval_fixture_ids=eval_fixture_ids,
            eval_case_ids=allowed_eval_case_ids,
        )
        skill_id = skill["id"]
        if skill_id in existing_skill_ids:
            raise SkillRegistryError(f"Skill batch skill id already exists: {skill_id}")
        if skill_id in skills:
            raise SkillRegistryError(f"Duplicate skill batch skill id: {skill_id}")
        if skill["eval_status"] != "draft":
            raise SkillRegistryError(f"Skill batch skill {skill_id} must use eval_status=draft.")
        route_key = skill["capability_contract"]["route_key"]
        if route_key in existing_route_keys:
            raise SkillRegistryError(f"Skill batch route_key already exists: {route_key}")
        if route_key in route_keys:
            raise SkillRegistryError(f"Duplicate skill batch route_key: {route_key}")
        route_keys[route_key] = skill_id
        referenced_batch_cases = set(skill["capability_contract"]["eval_case_ids"]) & set(batch_eval_cases)
        if not referenced_batch_cases:
            raise SkillRegistryError(f"Skill batch skill {skill_id} must reference at least one batch eval case.")
        for eval_case_id in referenced_batch_cases:
            eval_case = batch_eval_cases[eval_case_id]
            if eval_case["expected_workflow"] not in skill["workflows"]:
                raise SkillRegistryError(f"Skill batch skill {skill_id} does not list eval workflow {eval_case['expected_workflow']}.")
            if eval_case["mutation_policy"] != skill["capability_contract"]["mutation_policy"]:
                raise SkillRegistryError(f"Skill batch skill {skill_id} mutation policy must match eval case {eval_case_id}.")
        skills[skill_id] = skill
    return skills


def validate_expected_artifacts(
    eval_cases: dict[str, dict[str, Any]],
    *,
    known_artifacts: set[str],
) -> None:
    for eval_case in eval_cases.values():
        unknown = sorted(set(eval_case["expected_artifacts"]) - known_artifacts)
        if unknown:
            raise SkillRegistryError(
                f"Skill batch eval case {eval_case['id']} references unknown expected_artifacts: {', '.join(unknown)}"
            )


def skill_batch_entries(
    skills: dict[str, dict[str, Any]],
    eval_cases: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    referenced_eval_cases: set[str] = set()
    for skill in skills.values():
        contract = skill["capability_contract"]
        batch_eval_case_ids = [case_id for case_id in contract["eval_case_ids"] if case_id in eval_cases]
        referenced_eval_cases.update(batch_eval_case_ids)
        entries.append(
            {
                "skill_id": skill["id"],
                "route_key": contract["route_key"],
                "eval_case_ids": batch_eval_case_ids,
                "workflows": skill["workflows"],
                "output_artifacts": contract["output_artifacts"],
                "approval_boundary": contract["approval_boundary"],
                "mutation_policy": contract["mutation_policy"],
                "live_mappings": [live_mapping_for_case(eval_cases[case_id]) for case_id in batch_eval_case_ids],
                "status": "ready",
            }
        )
    unreferenced = sorted(set(eval_cases) - referenced_eval_cases)
    if unreferenced:
        raise SkillRegistryError(f"Skill batch eval case(s) are not referenced by any batch skill: {', '.join(unreferenced)}")
    return entries


def validate_skill_batch_manifest(manifest: dict[str, Any], config_root: Path) -> dict[str, Any]:
    config_root = config_root.resolve()
    header = validate_batch_header(manifest)
    registry = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    workflow_ids = registry_ids(config_root / "runtime" / "workflows.json", "workflows")
    tool_ids = registry_ids(config_root / "runtime" / "tools.json", "tools")
    workflows_manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow registry")
    eval_fixture_ids, existing_eval_case_ids = eval_catalog_ids(
        config_root / SKILL_EVALS_PATH,
        workflow_ids=workflow_ids,
    )
    existing_skill_ids, existing_route_keys = existing_skill_ids_and_route_keys(registry)
    doc_refs = validate_doc_refs(config_root, manifest["doc_refs"])
    eval_cases = validate_batch_eval_cases(
        header["eval_cases"],
        workflow_ids=workflow_ids,
        existing_eval_case_ids=existing_eval_case_ids,
    )
    skills = validate_batch_skill_items(
        header["skills"],
        config_root=config_root,
        workflow_ids=workflow_ids,
        tool_ids=tool_ids,
        eval_fixture_ids=eval_fixture_ids,
        existing_eval_case_ids=existing_eval_case_ids,
        batch_eval_cases=eval_cases,
        existing_skill_ids=existing_skill_ids,
        existing_route_keys=existing_route_keys,
    )
    try:
        existing_validated_skills = validate_skill_registry_manifest(registry, config_root)
    except SkillRegistryError:
        existing_validated_skills = {}
    semantic_conflicts = semantic_intent_conflicts(
        {**existing_validated_skills, **skills},
        proposed_skill_ids=set(skills),
    )
    if semantic_conflicts:
        first = semantic_conflicts[0]
        raise SkillRegistryError(
            "Skill batch has overlapping semantic intent; do not admit "
            f"{first['skill_ids'][0]} and {first['skill_ids'][1]}."
        )
    current_registry = {skill_id: skill for skill_id, skill in skills.items()}
    known_artifacts = (
        workflow_result_artifacts(workflows_manifest)
        | skill_output_artifacts(current_registry)
        | MANUAL_ARTIFACT_IDS
    )
    validate_expected_artifacts(eval_cases, known_artifacts=known_artifacts)
    entries = skill_batch_entries(skills, eval_cases)
    return {
        "status": "ready",
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_batch_validation",
        "batch_id": header["id"],
        "description": header["description"],
        "doc_refs": doc_refs,
        "summary": {
            "skill_count": len(skills),
            "eval_case_count": len(eval_cases),
            "route_key_count": len(entries),
            "live_suite_counts": live_suite_counts(eval_cases),
        },
        "entries": entries,
        "eval_cases": list(eval_cases.values()),
        "runtime_behavior_changed": False,
        "next_action": "review_then_append_batch_skills_and_eval_cases",
    }


def live_suite_counts(eval_cases: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for eval_case in eval_cases.values():
        live_suite = eval_case["live_suite"]
        counts[live_suite] = counts.get(live_suite, 0) + 1
    return counts


def build_skill_batch_report(
    config_root: Path,
    batch_path: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    manifest_path = batch_path if batch_path.is_absolute() else config_root / batch_path
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_batch_validation_report",
        "status": "failed",
        "config_root": str(config_root),
        "batch_path": str(manifest_path.resolve()),
        "batch_id": "skill-batch",
        "summary": {
            "skill_count": 0,
            "eval_case_count": 0,
            "route_key_count": 0,
            "live_suite_counts": {},
        },
        "entries": [],
        "eval_cases": [],
        "errors": [],
    }
    try:
        manifest = read_batch_manifest(manifest_path)
        report["batch_id"] = batch_id_from_manifest(manifest)
        validation = validate_skill_batch_manifest(manifest, config_root)
        report.update(validation)
        report["status"] = "passed"
    except (SkillRegistryError, OSError) as exc:
        report["errors"].append(str(exc))
    path = output_path or default_report_path(config_root, str(report["batch_id"]))
    write_json(path, report)
    report["report_path"] = str(path.resolve())
    write_json(path, report)
    return report
