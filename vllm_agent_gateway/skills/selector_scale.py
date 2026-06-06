"""Metadata-only selector scale and stability benchmarks."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from vllm_agent_gateway.skills.registry import (
    ROUTE_KEY_NAMESPACES,
    SCHEMA_VERSION,
    normalized_trigger_phrases,
    route_key_namespace,
    select_skills_for_workflow,
    selected_skill_capability_route_keys,
)


DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-scale"
DEFAULT_SKILL_COUNTS = (100, 1_000, 10_000)
DEFAULT_REPETITIONS = 10
DEFAULT_MAX_SELECTED = 5
DEFAULT_10000_THRESHOLD_SECONDS = 10.0

NON_STRICT_ROUTE_NAMESPACES = (
    "code",
    "config",
    "context",
    "diagnostics",
    "docs",
    "git",
    "planning",
    "test",
    "verification",
)

REPRESENTATIVE_REQUESTS = (
    {
        "id": "l1_explain_code",
        "workflow_id": "code_investigation.plan",
        "query_text": "In the repo, phase41 explain code behavior for the selected function.",
        "expected_skill_id": "phase41-target-explain-code",
        "expected_route_key": "code.phase41_explain_code",
    },
    {
        "id": "l1_pytest_fixture_lookup",
        "workflow_id": "code_context.lookup",
        "query_text": "In the repo, phase41 pytest fixture lookup for this test file.",
        "expected_skill_id": "phase41-target-pytest-fixture",
        "expected_route_key": "test.phase41_pytest_fixture",
    },
    {
        "id": "l2_failing_test_diagnosis",
        "workflow_id": "code_investigation.plan",
        "query_text": "In the repo, phase41 diagnose failing test root cause and likely fix area.",
        "expected_skill_id": "phase41-target-failing-test",
        "expected_route_key": "diagnostics.phase41_failing_test",
    },
    {
        "id": "l2_api_reference_lookup",
        "workflow_id": "code_context.lookup",
        "query_text": "In the repo, phase41 API reference lookup for a public method.",
        "expected_skill_id": "phase41-target-api-reference",
        "expected_route_key": "docs.phase41_api_reference",
    },
)

TARGET_SKILL_DEFINITIONS = (
    {
        "id": "phase41-target-explain-code",
        "route_key": "code.phase41_explain_code",
        "workflow": "code_investigation.plan",
        "trigger": "phase41 explain code behavior",
        "task_type": "phase41_explain_code_behavior",
        "output_artifact": "phase41_explain_code_summary",
        "eval_case_id": "phase41_eval_explain_code",
        "prompt_family": "phase41-l1-explain-code",
    },
    {
        "id": "phase41-target-pytest-fixture",
        "route_key": "test.phase41_pytest_fixture",
        "workflow": "code_context.lookup",
        "trigger": "phase41 pytest fixture lookup",
        "task_type": "phase41_pytest_fixture_lookup",
        "output_artifact": "phase41_pytest_fixture_summary",
        "eval_case_id": "phase41_eval_pytest_fixture",
        "prompt_family": "phase41-l1-pytest-fixture-lookup",
    },
    {
        "id": "phase41-target-failing-test",
        "route_key": "diagnostics.phase41_failing_test",
        "workflow": "code_investigation.plan",
        "trigger": "phase41 diagnose failing test root cause",
        "task_type": "phase41_failing_test_diagnosis",
        "output_artifact": "phase41_failing_test_diagnosis",
        "eval_case_id": "phase41_eval_failing_test",
        "prompt_family": "phase41-l2-failing-test-diagnosis",
    },
    {
        "id": "phase41-target-api-reference",
        "route_key": "docs.phase41_api_reference",
        "workflow": "code_context.lookup",
        "trigger": "phase41 API reference lookup",
        "task_type": "phase41_api_reference_lookup",
        "output_artifact": "phase41_api_reference_summary",
        "eval_case_id": "phase41_eval_api_reference",
        "prompt_family": "phase41-l2-api-reference-lookup",
    },
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"skill-selector-scale-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_skill(
    *,
    skill_id: str,
    route_key: str,
    workflow: str,
    trigger: str,
    task_type: str,
    output_artifact: str,
    eval_case_id: str,
) -> dict[str, Any]:
    return {
        "id": skill_id,
        "path": f".qwen/skills/{skill_id}/SKILL.md",
        "version": "0.1.0",
        "owner": "agentic_agents",
        "description": f"Phase 41 synthetic metadata-only skill for {task_type}.",
        "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
        "safety_level": "read_only_planning",
        "allowed_tools": [],
        "workflows": [workflow],
        "triggers": [trigger],
        "workflow_priorities": {workflow: 1000},
        "capability_contract": {
            "route_key": route_key,
            "task_types": [task_type],
            "input_artifacts": ["natural_user_request"],
            "output_artifacts": [output_artifact],
            "approval_boundary": "none",
            "mutation_policy": "no_repository_mutation",
            "eval_case_ids": [eval_case_id],
        },
        "problem_solving_steps": [1, 2, 4],
        "eval_status": "validated",
        "evals": {"fixtures": ["clear_request"]},
        "failure_record_refs": ["docs/SKILL_LIBRARY_SCALING_PLAN.md#phase-41-skill-selector-scale-and-stability-gate"],
    }


def build_eval_case(
    *,
    eval_case_id: str,
    prompt_family: str,
    natural_prompt: str,
    workflow: str,
    output_artifact: str,
) -> dict[str, Any]:
    return {
        "id": eval_case_id,
        "prompt_family": prompt_family,
        "natural_prompt": natural_prompt,
        "expected_workflow": workflow,
        "expected_artifacts": [output_artifact],
        "mutation_policy": "no_repository_mutation",
        "live_suite": "skill_registry_contract",
    }


def build_synthetic_catalog(skill_count: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if skill_count < len(TARGET_SKILL_DEFINITIONS):
        raise ValueError(f"skill_count must be at least {len(TARGET_SKILL_DEFINITIONS)}")

    skills: dict[str, dict[str, Any]] = {}
    eval_cases: list[dict[str, Any]] = []
    for target in TARGET_SKILL_DEFINITIONS:
        skill = build_skill(
            skill_id=target["id"],
            route_key=target["route_key"],
            workflow=target["workflow"],
            trigger=target["trigger"],
            task_type=target["task_type"],
            output_artifact=target["output_artifact"],
            eval_case_id=target["eval_case_id"],
        )
        skills[skill["id"]] = skill
        eval_cases.append(
            build_eval_case(
                eval_case_id=target["eval_case_id"],
                prompt_family=target["prompt_family"],
                natural_prompt=f"In <repo>, run {target['trigger']}.",
                workflow=target["workflow"],
                output_artifact=target["output_artifact"],
            )
        )

    for index in range(skill_count - len(skills)):
        namespace = NON_STRICT_ROUTE_NAMESPACES[index % len(NON_STRICT_ROUTE_NAMESPACES)]
        workflow = "code_investigation.plan" if index % 2 == 0 else "code_context.lookup"
        skill_id = f"phase41-synthetic-{index:05d}"
        eval_case_id = f"phase41_eval_synthetic_{index:05d}"
        task_type = f"phase41_synthetic_task_{index:05d}"
        output_artifact = f"phase41_synthetic_artifact_{index:05d}"
        trigger = f"phase41 isolated trigger {index:05d}"
        skill = build_skill(
            skill_id=skill_id,
            route_key=f"{namespace}.phase41_synthetic_{index:05d}",
            workflow=workflow,
            trigger=trigger,
            task_type=task_type,
            output_artifact=output_artifact,
            eval_case_id=eval_case_id,
        )
        skills[skill_id] = skill
        eval_cases.append(
            build_eval_case(
                eval_case_id=eval_case_id,
                prompt_family=f"phase41-synthetic-{index:05d}",
                natural_prompt=f"In <repo>, run {trigger}.",
                workflow=workflow,
                output_artifact=output_artifact,
            )
        )
    return skills, eval_cases


def sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def catalog_issue_summary(skills: dict[str, dict[str, Any]], eval_cases: list[dict[str, Any]]) -> dict[str, Any]:
    route_keys: Counter[str] = Counter()
    namespaces: Counter[str] = Counter()
    trigger_index: dict[str, list[str]] = defaultdict(list)
    task_index: dict[tuple[tuple[str, ...], str, str], list[str]] = defaultdict(list)
    output_trigger_index: dict[tuple[tuple[str, ...], str, tuple[str, ...], str], list[str]] = defaultdict(list)
    referenced_eval_cases: set[str] = set()

    errors: list[str] = []
    unsupported_namespaces: list[dict[str, str]] = []

    for skill in skills.values():
        contract = skill["capability_contract"]
        route_key = contract["route_key"]
        namespace = route_key_namespace(route_key)
        route_keys[route_key] += 1
        namespaces[namespace] += 1
        if namespace not in ROUTE_KEY_NAMESPACES:
            unsupported_namespaces.append(
                {"skill_id": skill["id"], "route_key": route_key, "namespace": namespace}
            )
        workflows = tuple(sorted(skill["workflows"]))
        mutation_policy = contract["mutation_policy"]
        for trigger in normalized_trigger_phrases(skill["triggers"]):
            trigger_index[trigger].append(skill["id"])
        for task_type in contract["task_types"]:
            task_index[(workflows, mutation_policy, task_type)].append(skill["id"])
        output_key = tuple(sorted(contract["output_artifacts"]))
        for trigger in normalized_trigger_phrases(skill["triggers"]):
            output_trigger_index[(workflows, mutation_policy, output_key, trigger)].append(skill["id"])
        referenced_eval_cases.update(contract["eval_case_ids"])

    eval_case_ids = {case["id"] for case in eval_cases}
    prompt_families = Counter(case["prompt_family"] for case in eval_cases)
    duplicate_route_keys = [
        {"route_key": route_key, "count": count}
        for route_key, count in sorted(route_keys.items())
        if count > 1
    ]
    trigger_collisions = [
        {"trigger": trigger, "skill_ids": sorted(skill_ids)}
        for trigger, skill_ids in sorted(trigger_index.items())
        if len(skill_ids) > 1
    ]
    semantic_overlaps = [
        {"kind": "task_type", "key": key[2], "skill_ids": sorted(skill_ids)}
        for key, skill_ids in sorted(task_index.items())
        if len(skill_ids) > 1
    ]
    semantic_overlaps.extend(
        {
            "kind": "output_trigger",
            "key": "|".join((*key[2], key[3])),
            "skill_ids": sorted(skill_ids),
        }
        for key, skill_ids in sorted(output_trigger_index.items())
        if len(skill_ids) > 1
    )
    duplicate_prompt_families = [
        {"prompt_family": prompt_family, "count": count}
        for prompt_family, count in sorted(prompt_families.items())
        if count > 1
    ]
    missing_eval_cases = sorted(referenced_eval_cases - eval_case_ids)
    unreferenced_eval_cases = sorted(eval_case_ids - referenced_eval_cases)

    if duplicate_route_keys:
        errors.append("duplicate_route_keys")
    if unsupported_namespaces:
        errors.append("unsupported_route_namespaces")
    if trigger_collisions:
        errors.append("trigger_collisions")
    if semantic_overlaps:
        errors.append("semantic_overlaps")
    if duplicate_prompt_families:
        errors.append("duplicate_prompt_families")
    if missing_eval_cases:
        errors.append("missing_eval_cases")
    if unreferenced_eval_cases:
        errors.append("unreferenced_eval_cases")

    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "route_namespace_saturation": sorted_counter(namespaces),
        "duplicate_route_keys": duplicate_route_keys,
        "unsupported_route_namespaces": unsupported_namespaces,
        "trigger_collisions": trigger_collisions,
        "semantic_overlaps": semantic_overlaps,
        "prompt_family_count": len(prompt_families),
        "duplicate_prompt_families": duplicate_prompt_families,
        "missing_eval_cases": missing_eval_cases,
        "unreferenced_eval_cases": unreferenced_eval_cases,
    }


def run_selection_stability(
    skills: dict[str, dict[str, Any]],
    *,
    repetitions: int,
    max_selected: int,
) -> dict[str, Any]:
    started = perf_counter()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for request in REPRESENTATIVE_REQUESTS:
        selections: list[list[str]] = []
        for _index in range(repetitions):
            selections.append(
                select_skills_for_workflow(
                    skills,
                    request["workflow_id"],
                    query_text=request["query_text"],
                    limit=max_selected,
                )
            )
        first = selections[0]
        stable = all(selection == first for selection in selections)
        route_keys = selected_skill_capability_route_keys(skills, first)
        expected_skill_id = request["expected_skill_id"]
        expected_route_key = request["expected_route_key"]
        expected_selected = expected_skill_id in first and route_keys.get(expected_skill_id) == expected_route_key
        if not stable:
            errors.append(f"{request['id']} selection was unstable")
        if not expected_selected:
            errors.append(f"{request['id']} did not select {expected_skill_id}")
        results.append(
            {
                "request_id": request["id"],
                "workflow_id": request["workflow_id"],
                "stable": stable,
                "expected_selected": expected_selected,
                "selected_skill_ids": first,
                "selected_route_keys": route_keys,
            }
        )
    elapsed_seconds = perf_counter() - started
    return {
        "status": "failed" if errors else "passed",
        "elapsed_seconds": elapsed_seconds,
        "repetitions": repetitions,
        "max_selected": max_selected,
        "representative_results": results,
        "errors": errors,
        "body_reads_during_selection": 0,
    }


def negative_fixture_mutations() -> dict[str, Callable[[dict[str, dict[str, Any]], list[dict[str, Any]]], None]]:
    def duplicate_route_key(skills: dict[str, dict[str, Any]], _eval_cases: list[dict[str, Any]]) -> None:
        skills["phase41-target-pytest-fixture"]["capability_contract"]["route_key"] = (
            skills["phase41-target-explain-code"]["capability_contract"]["route_key"]
        )

    def unsupported_namespace(skills: dict[str, dict[str, Any]], _eval_cases: list[dict[str, Any]]) -> None:
        skills["phase41-target-api-reference"]["capability_contract"]["route_key"] = "unsupported.phase41_api_reference"

    def trigger_collision(skills: dict[str, dict[str, Any]], _eval_cases: list[dict[str, Any]]) -> None:
        skills["phase41-target-api-reference"]["triggers"] = list(skills["phase41-target-explain-code"]["triggers"])

    def semantic_overlap(skills: dict[str, dict[str, Any]], _eval_cases: list[dict[str, Any]]) -> None:
        skills["phase41-target-failing-test"]["capability_contract"]["task_types"] = list(
            skills["phase41-target-explain-code"]["capability_contract"]["task_types"]
        )

    def missing_eval_case(skills: dict[str, dict[str, Any]], eval_cases: list[dict[str, Any]]) -> None:
        missing = skills["phase41-target-api-reference"]["capability_contract"]["eval_case_ids"][0]
        eval_cases[:] = [case for case in eval_cases if case["id"] != missing]

    return {
        "duplicate_route_key": duplicate_route_key,
        "unsupported_namespace": unsupported_namespace,
        "trigger_collision": trigger_collision,
        "semantic_overlap": semantic_overlap,
        "missing_eval_case": missing_eval_case,
    }


def run_negative_fixtures() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for fixture_id, mutate in negative_fixture_mutations().items():
        skills, eval_cases = build_synthetic_catalog(25)
        mutate(skills, eval_cases)
        issues = catalog_issue_summary(skills, eval_cases)
        results.append(
            {
                "id": fixture_id,
                "status": "rejected" if issues["status"] == "failed" else "not_rejected",
                "detected_errors": issues["errors"],
            }
        )
    return results


def build_skill_selector_scale_report(
    config_root: Path,
    *,
    output_path: Path | None = None,
    skill_counts: tuple[int, ...] = DEFAULT_SKILL_COUNTS,
    repetitions: int = DEFAULT_REPETITIONS,
    max_selected: int = DEFAULT_MAX_SELECTED,
    threshold_10000_seconds: float = DEFAULT_10000_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    config_root = config_root.resolve()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_selector_scale_report",
        "status": "failed",
        "config_root": str(config_root),
        "thresholds": {
            "skill_counts": list(skill_counts),
            "repetitions": repetitions,
            "max_selected": max_selected,
            "max_10000_selection_seconds": threshold_10000_seconds,
        },
        "selection_policy": {
            "input": "metadata_only",
            "loads_skill_bodies_during_selection": False,
        },
        "benchmarks": [],
        "negative_fixtures": [],
        "summary": {},
        "errors": [],
    }

    largest_elapsed = 0.0
    body_reads = 0
    for skill_count in skill_counts:
        skills, eval_cases = build_synthetic_catalog(skill_count)
        analysis = catalog_issue_summary(skills, eval_cases)
        selection = run_selection_stability(skills, repetitions=repetitions, max_selected=max_selected)
        largest_elapsed = max(largest_elapsed, selection["elapsed_seconds"])
        body_reads += selection["body_reads_during_selection"]
        benchmark = {
            "skill_count": skill_count,
            "eval_case_count": len(eval_cases),
            "catalog_analysis": analysis,
            "selection_benchmark": selection,
        }
        report["benchmarks"].append(benchmark)
        if analysis["status"] != "passed":
            report["errors"].append(f"{skill_count}-skill catalog analysis failed: {', '.join(analysis['errors'])}")
        if selection["status"] != "passed":
            report["errors"].extend(f"{skill_count}-skill {error}" for error in selection["errors"])
        if skill_count >= 10_000 and selection["elapsed_seconds"] > threshold_10000_seconds:
            report["errors"].append(
                f"10000-skill selector benchmark exceeded {threshold_10000_seconds:.3f}s: "
                f"{selection['elapsed_seconds']:.3f}s"
            )

    negative_fixtures = run_negative_fixtures()
    report["negative_fixtures"] = negative_fixtures
    not_rejected = [fixture["id"] for fixture in negative_fixtures if fixture["status"] != "rejected"]
    if not_rejected:
        report["errors"].append("Negative fixture(s) were not rejected: " + ", ".join(sorted(not_rejected)))

    largest_benchmark = max(report["benchmarks"], key=lambda item: item["skill_count"]) if report["benchmarks"] else None
    report["summary"] = {
        "largest_skill_count": largest_benchmark["skill_count"] if largest_benchmark else 0,
        "largest_selection_elapsed_seconds": (
            largest_benchmark["selection_benchmark"]["elapsed_seconds"] if largest_benchmark else 0.0
        ),
        "max_selection_elapsed_seconds": largest_elapsed,
        "body_reads_during_selection": body_reads,
        "negative_fixture_count": len(negative_fixtures),
        "negative_fixture_rejected_count": len(negative_fixtures) - len(not_rejected),
    }
    report["status"] = "failed" if report["errors"] else "passed"
    path = output_path or default_report_path(config_root)
    write_json(path, report)
    report["report_path"] = str(path.resolve())
    write_json(path, report)
    return report
