"""Registry-scale reporting for skill library growth."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.skills.evals import SKILL_EVALS_PATH
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SkillRegistryError,
    load_skill_registry,
    read_json_object,
    semantic_intent_conflicts,
    validate_eval_case_item,
)


DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-scale"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"skill-scale-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def build_skill_scale_report(config_root: Path, *, output_path: Path | None = None) -> dict[str, Any]:
    config_root = config_root.resolve()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_scale_report",
        "status": "failed",
        "config_root": str(config_root),
        "registry_path": str((config_root / SKILL_REGISTRY_PATH).resolve()),
        "eval_catalog_path": str((config_root / SKILL_EVALS_PATH).resolve()),
        "summary": {
            "skill_count": 0,
            "eval_case_count": 0,
            "route_key_count": 0,
            "deprecated_skill_count": 0,
            "do_not_admit_count": 0,
        },
        "coverage": {
            "by_workflow": {},
            "by_output_artifact": {},
            "by_safety_level": {},
            "by_mutation_policy": {},
            "by_prompt_family": {},
            "by_route_namespace": {},
        },
        "route_key_ownership": [],
        "deprecations": [],
        "do_not_admit": [],
        "errors": [],
    }
    try:
        skills = load_skill_registry(config_root)
        eval_manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
        eval_cases_raw = eval_manifest.get("cases", [])
        if not isinstance(eval_cases_raw, list):
            raise SkillRegistryError("runtime/skill_evals.json cases must be a list.")
        eval_cases = [validate_eval_case_item(item) for item in eval_cases_raw]

        workflow_counts: Counter[str] = Counter()
        artifact_counts: Counter[str] = Counter()
        safety_counts: Counter[str] = Counter()
        mutation_counts: Counter[str] = Counter()
        namespace_counts: Counter[str] = Counter()
        prompt_counts: Counter[str] = Counter()
        route_key_ownership: list[dict[str, Any]] = []
        deprecations: list[dict[str, Any]] = []
        eval_case_to_skill_ids: dict[str, list[str]] = defaultdict(list)

        for skill in skills.values():
            contract = skill["capability_contract"]
            safety_counts[skill["safety_level"]] += 1
            mutation_counts[contract["mutation_policy"]] += 1
            namespace_counts[skill["route_namespace"]] += 1
            for workflow in skill["workflows"]:
                workflow_counts[workflow] += 1
            for artifact in contract["output_artifacts"]:
                artifact_counts[artifact] += 1
            for eval_case_id in contract["eval_case_ids"]:
                eval_case_to_skill_ids[eval_case_id].append(skill["id"])
            route_key_ownership.append(
                {
                    "skill_id": skill["id"],
                    "route_key": contract["route_key"],
                    "namespace": skill["route_namespace"],
                    "owner": skill["owner"],
                    "workflows": skill["workflows"],
                    "mutation_policy": contract["mutation_policy"],
                    "approval_boundary": contract["approval_boundary"],
                    "output_artifacts": contract["output_artifacts"],
                }
            )
            if skill.get("deprecation"):
                deprecations.append({"skill_id": skill["id"], **skill["deprecation"]})

        for eval_case in eval_cases:
            prompt_counts[eval_case["prompt_family"]] += 1

        conflicts = semantic_intent_conflicts(skills)
        do_not_admit = [
            {
                **conflict,
                "action": "do_not_admit_without_replacement_or_deprecation_plan",
            }
            for conflict in conflicts
        ]
        uncovered_eval_cases = sorted(
            eval_case["id"] for eval_case in eval_cases if eval_case["id"] not in eval_case_to_skill_ids
        )
        if uncovered_eval_cases:
            report["errors"].append(
                "Eval case(s) are not referenced by any skill: " + ", ".join(uncovered_eval_cases)
            )

        report["summary"] = {
            "skill_count": len(skills),
            "eval_case_count": len(eval_cases),
            "route_key_count": len({skill["capability_contract"]["route_key"] for skill in skills.values()}),
            "deprecated_skill_count": len(deprecations),
            "do_not_admit_count": len(do_not_admit),
        }
        report["coverage"] = {
            "by_workflow": sorted_counter(workflow_counts),
            "by_output_artifact": sorted_counter(artifact_counts),
            "by_safety_level": sorted_counter(safety_counts),
            "by_mutation_policy": sorted_counter(mutation_counts),
            "by_prompt_family": sorted_counter(prompt_counts),
            "by_route_namespace": sorted_counter(namespace_counts),
        }
        report["route_key_ownership"] = sorted(route_key_ownership, key=lambda item: item["route_key"])
        report["deprecations"] = sorted(deprecations, key=lambda item: item["skill_id"])
        report["do_not_admit"] = do_not_admit
        if do_not_admit:
            report["errors"].append("Overlapping semantic intent found; see do_not_admit.")
    except (OSError, SkillRegistryError) as exc:
        report["errors"].append(str(exc))

    report["status"] = "failed" if report["errors"] else "passed"
    path = output_path or default_report_path(config_root)
    write_json(path, report)
    report["report_path"] = str(path.resolve())
    write_json(path, report)
    return report
