#!/usr/bin/env python3
"""Validate the Phase 61 Batch D skill-scaling proposal without registry mutation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.evals import SKILL_EVALS_PATH  # noqa: E402
from vllm_agent_gateway.skills.registry import (  # noqa: E402
    SKILL_REGISTRY_PATH,
    eval_catalog_ids,
    existing_skill_ids_and_route_keys,
    read_json_object,
    registry_ids,
    semantic_intent_conflicts,
    validate_skill_registry_manifest,
)


DEFAULT_PROPOSAL_PATH = Path("docs") / "skill-scaling-batch-d.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-batches"
REQUIRED_CANDIDATE_FIELDS = {
    "id",
    "route_key",
    "prompt_family",
    "task_type",
    "natural_prompt",
    "expected_workflow",
    "expected_artifacts",
    "mutation_policy",
    "approval_boundary",
    "triggers",
    "eval_case_id",
    "source_prompt_cases",
    "rationale",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain a JSON object")
    return value


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise RuntimeError(f"{label} must be a non-empty string list")
    return value


def proposed_skill_like(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate["id"],
        "workflows": [candidate["expected_workflow"]],
        "triggers": candidate["triggers"],
        "eval_status": "draft",
        "capability_contract": {
            "route_key": candidate["route_key"],
            "task_types": [candidate["task_type"]],
            "output_artifacts": candidate["expected_artifacts"],
            "mutation_policy": candidate["mutation_policy"],
        },
    }


def raw_skill_maps(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    skills_by_id: dict[str, dict[str, Any]] = {}
    route_owner_by_key: dict[str, str] = {}
    raw_skills = registry.get("skills")
    if not isinstance(raw_skills, list):
        raise RuntimeError("runtime/skills.json skills must be a list")
    for item in raw_skills:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        skill_id = item["id"]
        skills_by_id[skill_id] = item
        contract = item.get("capability_contract")
        if isinstance(contract, dict) and isinstance(contract.get("route_key"), str):
            route_owner_by_key[contract["route_key"]] = skill_id
    return skills_by_id, route_owner_by_key


def raw_eval_cases_by_id(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / SKILL_EVALS_PATH, "skill eval catalog")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list):
        raise RuntimeError("runtime/skill_evals.json cases must be a list")
    return {
        item["id"]: item
        for item in raw_cases
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def validate_registered_candidate(candidate: dict[str, Any], skill: dict[str, Any]) -> None:
    contract = skill.get("capability_contract")
    if not isinstance(contract, dict):
        raise RuntimeError(f"registered candidate {candidate['id']} is missing capability_contract")
    checks = {
        "route_key": contract.get("route_key") == candidate["route_key"],
        "workflow": candidate["expected_workflow"] in skill.get("workflows", []),
        "task_type": candidate["task_type"] in contract.get("task_types", []),
        "output_artifacts": contract.get("output_artifacts") == candidate["expected_artifacts"],
        "mutation_policy": contract.get("mutation_policy") == candidate["mutation_policy"],
        "approval_boundary": contract.get("approval_boundary") == candidate["approval_boundary"],
        "eval_case": candidate["eval_case_id"] in contract.get("eval_case_ids", []),
        "eval_status": skill.get("eval_status") in {"draft", "validated"},
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise RuntimeError(f"registered candidate {candidate['id']} metadata mismatch: {', '.join(failed)}")


def validate_registered_eval_case(candidate: dict[str, Any], eval_case: dict[str, Any]) -> None:
    checks = {
        "prompt_family": eval_case.get("prompt_family") == candidate["prompt_family"],
        "natural_prompt": eval_case.get("natural_prompt") == candidate["natural_prompt"],
        "expected_workflow": eval_case.get("expected_workflow") == candidate["expected_workflow"],
        "expected_artifacts": eval_case.get("expected_artifacts") == candidate["expected_artifacts"],
        "mutation_policy": eval_case.get("mutation_policy") == candidate["mutation_policy"],
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise RuntimeError(f"registered eval case {candidate['eval_case_id']} metadata mismatch: {', '.join(failed)}")


def validate_candidate_shape(candidate: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise RuntimeError(f"candidate {index} must be an object")
    missing = sorted(REQUIRED_CANDIDATE_FIELDS - set(candidate))
    if missing:
        raise RuntimeError(f"candidate {index} missing field(s): {', '.join(missing)}")
    for key in ("id", "route_key", "prompt_family", "task_type", "natural_prompt", "expected_workflow", "mutation_policy", "approval_boundary", "eval_case_id", "rationale"):
        if not isinstance(candidate[key], str) or not candidate[key].strip():
            raise RuntimeError(f"candidate {index}.{key} must be a non-empty string")
    for key in ("expected_artifacts", "triggers", "source_prompt_cases"):
        string_list(candidate[key], f"candidate {index}.{key}")
    if candidate["mutation_policy"] != "no_repository_mutation":
        raise RuntimeError(f"candidate {candidate['id']} must be read-only in Batch D")
    if candidate["approval_boundary"] != "none":
        raise RuntimeError(f"candidate {candidate['id']} must not require approval-gated mutation in Batch D")
    return candidate


def build_proposal_report(config_root: Path, proposal_path: Path, *, output_path: Path | None = None) -> dict[str, Any]:
    config_root = config_root.resolve()
    proposal_path = proposal_path if proposal_path.is_absolute() else config_root / proposal_path
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "skill_batch_d_proposal_validation",
        "status": "failed",
        "config_root": str(config_root),
        "proposal_path": str(proposal_path.resolve()),
        "batch_id": "phase61-field-evidence-batch-d",
        "summary": {
            "candidate_count": 0,
            "route_key_count": 0,
            "eval_case_count": 0,
            "semantic_conflict_count": 0,
        },
        "candidates": [],
        "semantic_conflicts": [],
        "errors": [],
    }
    try:
        proposal = read_json(proposal_path, "Batch D proposal")
        if proposal.get("schema_version") != 1:
            raise RuntimeError("proposal schema_version must be 1")
        if proposal.get("kind") != "skill_batch_d_evidence_proposal":
            raise RuntimeError("proposal kind must be skill_batch_d_evidence_proposal")
        candidates = [
            validate_candidate_shape(candidate, index=index)
            for index, candidate in enumerate(proposal.get("candidates", []), start=1)
        ]
        if not candidates:
            raise RuntimeError("proposal must include candidates")

        registry = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
        workflow_ids = registry_ids(config_root / "runtime" / "workflows.json", "workflows")
        existing_skill_ids, existing_route_keys = existing_skill_ids_and_route_keys(registry)
        skills_by_id, route_owner_by_key = raw_skill_maps(registry)
        eval_cases_by_id = raw_eval_cases_by_id(config_root)
        _eval_fixture_ids, existing_eval_case_ids = eval_catalog_ids(
            config_root / SKILL_EVALS_PATH,
            workflow_ids=workflow_ids,
        )
        candidate_ids = [candidate["id"] for candidate in candidates]
        route_keys = [candidate["route_key"] for candidate in candidates]
        eval_case_ids = [candidate["eval_case_id"] for candidate in candidates]
        duplicate_candidate_ids = sorted({value for value in candidate_ids if candidate_ids.count(value) > 1})
        duplicate_route_keys = sorted({value for value in route_keys if route_keys.count(value) > 1})
        duplicate_eval_case_ids = sorted({value for value in eval_case_ids if eval_case_ids.count(value) > 1})
        if duplicate_candidate_ids:
            raise RuntimeError(f"duplicate candidate id(s): {', '.join(duplicate_candidate_ids)}")
        if duplicate_route_keys:
            raise RuntimeError(f"duplicate candidate route key(s): {', '.join(duplicate_route_keys)}")
        if duplicate_eval_case_ids:
            raise RuntimeError(f"duplicate candidate eval case id(s): {', '.join(duplicate_eval_case_ids)}")
        for candidate in candidates:
            skill = skills_by_id.get(candidate["id"])
            route_owner = route_owner_by_key.get(candidate["route_key"])
            eval_case = eval_cases_by_id.get(candidate["eval_case_id"])
            if skill:
                validate_registered_candidate(candidate, skill)
            elif candidate["id"] in existing_skill_ids:
                raise RuntimeError(f"candidate skill id already exists with unreadable metadata: {candidate['id']}")
            if route_owner and route_owner != candidate["id"]:
                raise RuntimeError(
                    f"candidate route key already exists with different owner: {candidate['route_key']} -> {route_owner}"
                )
            if not skill and candidate["route_key"] in existing_route_keys:
                raise RuntimeError(f"candidate route key already exists: {candidate['route_key']}")
            if eval_case:
                validate_registered_eval_case(candidate, eval_case)
            elif candidate["eval_case_id"] in existing_eval_case_ids:
                raise RuntimeError(f"candidate eval case id already exists with unreadable metadata: {candidate['eval_case_id']}")
        unknown_workflows = sorted({candidate["expected_workflow"] for candidate in candidates} - workflow_ids)
        if unknown_workflows:
            raise RuntimeError(f"candidate expected_workflow unknown: {', '.join(unknown_workflows)}")

        try:
            existing_validated_skills = validate_skill_registry_manifest(registry, config_root)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"current skill registry must validate before Batch D proposal validation: {exc}") from exc
        proposed_skills = {candidate["id"]: proposed_skill_like(candidate) for candidate in candidates}
        semantic_conflicts = semantic_intent_conflicts(
            {**existing_validated_skills, **proposed_skills},
            proposed_skill_ids=set(proposed_skills),
        )
        report["semantic_conflicts"] = semantic_conflicts
        if semantic_conflicts:
            raise RuntimeError("candidate semantic intent overlaps existing registry skill")

        report["candidates"] = [
            {
                "id": candidate["id"],
                "route_key": candidate["route_key"],
                "eval_case_id": candidate["eval_case_id"],
                "expected_workflow": candidate["expected_workflow"],
                "expected_artifacts": candidate["expected_artifacts"],
                "source_prompt_cases": candidate["source_prompt_cases"],
                "status": (
                    "registered_candidate_matches_proposal"
                    if candidate["id"] in skills_by_id and candidate["eval_case_id"] in eval_cases_by_id
                    else "candidate_ready_for_founder_review"
                ),
            }
            for candidate in candidates
        ]
        report["summary"] = {
            "candidate_count": len(candidates),
            "route_key_count": len(set(route_keys)),
            "eval_case_count": len(set(eval_case_ids)),
            "semantic_conflict_count": 0,
        }
        report["status"] = "passed"
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["summary"]["semantic_conflict_count"] = len(report["semantic_conflicts"])

    path = output_path or config_root / DEFAULT_REPORT_DIR / f"phase61-batch-d-proposal-{utc_timestamp()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_path"] = str(path.resolve())
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--proposal-file", default=str(DEFAULT_PROPOSAL_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_proposal_report(
        Path(args.config_root),
        Path(args.proposal_file),
        output_path=Path(args.output_path) if args.output_path else None,
    )
    print(f"SKILL BATCH D PROPOSAL REPORT {report['report_path']}")
    print("SKILL BATCH D PROPOSAL SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("SKILL BATCH D PROPOSAL FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL BATCH D PROPOSAL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
