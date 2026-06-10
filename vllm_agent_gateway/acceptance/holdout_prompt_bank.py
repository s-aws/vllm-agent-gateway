"""Priority 0 holdout prompt bank validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    DEFAULT_CORPUS_PATH,
    REQUIRED_COINBASE_TARGETS,
    REQUIRED_ROUTES,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)


SCHEMA_VERSION = 1
DEFAULT_HOLDOUT_BANK_PATH = Path("runtime") / "holdout_prompt_bank.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "holdout-prompt-bank"
DEFAULT_MINIMUM_SCORE = 85


class HoldoutPromptBankStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class HoldoutPromptBankConfig:
    config_root: Path
    corpus_path: Path = DEFAULT_CORPUS_PATH
    bank_path: Path = DEFAULT_HOLDOUT_BANK_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"holdout-prompt-bank-{utc_timestamp()}.json"


def stable_corpus_entries_by_id(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("entry_id")): entry
        for entry in object_list(corpus.get("entries"))
        if entry.get("status") == "stable" and isinstance(entry.get("entry_id"), str) and entry.get("entry_id")
    }


def bank_entries_by_id(bank: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("entry_id")): entry
        for entry in object_list(bank.get("entries"))
        if isinstance(entry.get("entry_id"), str) and entry.get("entry_id")
    }


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def case_ids_from_prompt_cases(prompt_cases: dict[str, Any], *, holdout_only: bool = False) -> list[str]:
    return [
        str(item.get("case_id"))
        for item in object_list(prompt_cases.get("cases"))
        if isinstance(item.get("case_id"), str) and item.get("case_id") and (not holdout_only or item.get("holdout") is True)
    ]


def case_ids_from_baselines(baselines: dict[str, Any]) -> list[str]:
    return [
        str(item.get("case_id"))
        for item in object_list(baselines.get("baselines"))
        if isinstance(item.get("case_id"), str) and item.get("case_id")
    ]


def cases_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("case_id")): item
        for item in items
        if isinstance(item.get("case_id"), str) and item.get("case_id")
    }


def path_ref_errors(
    *,
    config_root: Path,
    prefix: str,
    ref: object,
    expected_ref: object,
    require_artifacts: bool,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(ref, dict):
        return [f"{prefix} is required"]
    if not isinstance(expected_ref, dict):
        return [f"{prefix} has no matching baseline corpus ref"]
    path_value = ref.get("path")
    hash_value = ref.get("sha256")
    if path_value != expected_ref.get("path"):
        errors.append(f"{prefix}.path must match baseline corpus")
    if hash_value != expected_ref.get("sha256"):
        errors.append(f"{prefix}.sha256 must match baseline corpus")
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"{prefix}.path is required")
    if not isinstance(hash_value, str) or len(hash_value) != 64:
        errors.append(f"{prefix}.sha256 must be a 64-character hash")
    if errors:
        return errors
    path = resolve_path(config_root, str(path_value))
    if not path.is_file():
        if require_artifacts or str(path_value).startswith("runtime/"):
            errors.append(f"{prefix}.path does not exist: {path_value}")
        return errors
    if sha256_file(path) != hash_value:
        errors.append(f"{prefix}.sha256 is stale for {path_value}")
    return errors


def validate_bank_shape(bank: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if bank.get("schema_version") != SCHEMA_VERSION:
        errors.append("holdout bank schema_version must be 1")
    if bank.get("kind") != "priority0_holdout_prompt_bank":
        errors.append("holdout bank kind must be priority0_holdout_prompt_bank")
    policy = bank.get("policy") if isinstance(bank.get("policy"), dict) else {}
    if policy.get("minimum_holdouts_per_entry") != 2:
        errors.append("policy.minimum_holdouts_per_entry must be 2")
    if set(string_list(policy.get("required_routes"))) != REQUIRED_ROUTES:
        errors.append("policy.required_routes must include gateway and anythingllm")
    if policy.get("minimum_route_score") != DEFAULT_MINIMUM_SCORE:
        errors.append("policy.minimum_route_score must be 85")
    if policy.get("comparison_status_required") != "passed":
        errors.append("policy.comparison_status_required must be passed")
    if policy.get("critical_findings_allowed") != 0:
        errors.append("policy.critical_findings_allowed must be 0")
    if policy.get("high_findings_allowed") != 0:
        errors.append("policy.high_findings_allowed must be 0")
    if set(string_list(policy.get("frozen_target_roots_for_reporting"))) != REQUIRED_COINBASE_TARGETS:
        errors.append("policy.frozen_target_roots_for_reporting must match frozen Coinbase target roots")
    if policy.get("allow_justified_missing_frozen_holdouts") is not True:
        errors.append("policy.allow_justified_missing_frozen_holdouts must be true")
    if policy.get("source_mutation_allowed") is not False:
        errors.append("policy.source_mutation_allowed must be false")
    if policy.get("holdout_rerun_required_after_repair") is not True:
        errors.append("policy.holdout_rerun_required_after_repair must be true")

    bank_entry_ids = set(bank_entries_by_id(bank))
    stable_entry_ids = set(stable_corpus_entries_by_id(corpus))
    if bank_entry_ids != stable_entry_ids:
        errors.append("holdout bank entries must exactly match stable baseline corpus entry IDs")
    return errors


def validate_prompt_and_baseline_holdouts(
    *,
    bank_entry: dict[str, Any],
    corpus_entry: dict[str, Any],
    prompt_cases: dict[str, Any],
    baselines: dict[str, Any],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    holdout_case_ids = string_list(bank_entry.get("holdout_case_ids"))
    if len(holdout_case_ids) != corpus_entry.get("expected_holdout_count"):
        errors.append(f"{prefix}.holdout_case_ids must match expected_holdout_count")
    duplicates = duplicate_values(holdout_case_ids)
    if duplicates:
        errors.append(f"{prefix}.holdout_case_ids contains duplicate IDs: " + ", ".join(duplicates))
    actual_holdout_ids = case_ids_from_prompt_cases(prompt_cases, holdout_only=True)
    if set(holdout_case_ids) != set(actual_holdout_ids):
        errors.append(f"{prefix}.holdout_case_ids must exactly match prompt cases marked holdout=true")
    baseline_ids = set(case_ids_from_baselines(baselines))
    missing_baselines = sorted(set(holdout_case_ids) - baseline_ids)
    if missing_baselines:
        errors.append(f"{prefix}.blind_baselines missing holdout case IDs: " + ", ".join(missing_baselines))

    prompt_case_map = cases_by_id(object_list(prompt_cases.get("cases")))
    holdout_target_roots = set(string_list(bank_entry.get("holdout_target_roots")))
    actual_target_roots = {
        str(prompt_case_map[case_id].get("target_root"))
        for case_id in holdout_case_ids
        if case_id in prompt_case_map and isinstance(prompt_case_map[case_id].get("target_root"), str)
    }
    if holdout_target_roots != actual_target_roots:
        errors.append(f"{prefix}.holdout_target_roots must match prompt case target roots")
    target_coverage = bank_entry.get("target_coverage") if isinstance(bank_entry.get("target_coverage"), dict) else {}
    covered_target_roots = set(string_list(target_coverage.get("covered_target_roots")))
    if covered_target_roots != actual_target_roots:
        errors.append(f"{prefix}.target_coverage.covered_target_roots must match holdout target roots")
    missing_frozen_target_roots = set(string_list(target_coverage.get("missing_frozen_target_roots")))
    actual_missing_frozen_target_roots = REQUIRED_COINBASE_TARGETS - actual_target_roots
    if missing_frozen_target_roots != actual_missing_frozen_target_roots:
        errors.append(f"{prefix}.target_coverage.missing_frozen_target_roots must match uncovered frozen targets")
    if missing_frozen_target_roots and (
        not isinstance(target_coverage.get("justification"), str) or not target_coverage["justification"].strip()
    ):
        errors.append(f"{prefix}.target_coverage.justification is required when frozen holdouts are absent")
    for case_id in holdout_case_ids:
        prompt_case = prompt_case_map.get(case_id)
        if not prompt_case:
            errors.append(f"{prefix}.prompt_cases missing holdout case {case_id}")
            continue
        if not isinstance(prompt_case.get("prompt"), str) or not prompt_case["prompt"].strip():
            errors.append(f"{prefix}.prompt_cases[{case_id}].prompt is required")
    baseline_map = cases_by_id(object_list(baselines.get("baselines")))
    for case_id in holdout_case_ids:
        baseline = baseline_map.get(case_id)
        if not baseline:
            continue
        if not string_list(baseline.get("safety_boundaries")):
            errors.append(f"{prefix}.blind_baselines[{case_id}].safety_boundaries is required")
        if not (
            string_list(baseline.get("must_have_facts"))
            or string_list(baseline.get("must_have_topics"))
        ):
            errors.append(f"{prefix}.blind_baselines[{case_id}] must define must_have_facts or must_have_topics")
    return errors


def validate_local_eval_holdouts(
    *,
    artifact: dict[str, Any],
    holdout_case_ids: list[str],
    prefix: str,
) -> tuple[list[str], dict[tuple[str, str], str]]:
    errors: list[str] = []
    selected_workflows: dict[tuple[str, str], str] = {}
    if artifact.get("runtime_changed_files") != []:
        errors.append(f"{prefix}.local_eval.runtime_changed_files must be []")
    if artifact.get("target_changed_files") != {}:
        errors.append(f"{prefix}.local_eval.target_changed_files must be {{}}")
    if artifact.get("target_git_changed") not in ({}, None):
        errors.append(f"{prefix}.local_eval.target_git_changed must be empty when present")
    cases = cases_by_id(object_list(artifact.get("checks", {}).get("cases") if isinstance(artifact.get("checks"), dict) else []))
    missing_cases = sorted(set(holdout_case_ids) - set(cases))
    if missing_cases:
        errors.append(f"{prefix}.local_eval missing holdout case IDs: " + ", ".join(missing_cases))
    for case_id in holdout_case_ids:
        case = cases.get(case_id)
        if not case:
            continue
        if case.get("holdout") is not True:
            errors.append(f"{prefix}.local_eval case {case_id} must record holdout=true")
        responses = case.get("responses") if isinstance(case.get("responses"), dict) else {}
        response_routes = set(responses)
        missing_routes = sorted(REQUIRED_ROUTES - response_routes)
        if missing_routes:
            errors.append(f"{prefix}.local_eval case {case_id} missing route(s): " + ", ".join(missing_routes))
        extra_routes = sorted(response_routes - REQUIRED_ROUTES)
        if extra_routes:
            errors.append(f"{prefix}.local_eval case {case_id} has unexpected route(s): " + ", ".join(extra_routes))
        for route in sorted(REQUIRED_ROUTES):
            response = responses.get(route)
            route_prefix = f"{prefix}.local_eval case {case_id}.{route}"
            if not isinstance(response, dict):
                continue
            if response.get("status") != "captured":
                errors.append(f"{route_prefix}.status must be captured")
            if response.get("http_status") != 200:
                errors.append(f"{route_prefix}.http_status must be 200")
            if not isinstance(response.get("text"), str) or not response["text"].strip():
                errors.append(f"{route_prefix}.text is required")
            elif "source mutation:" not in response["text"].lower():
                errors.append(f"{route_prefix}.text must include source mutation boundary")
            route_summary = response.get("route_summary") if isinstance(response.get("route_summary"), dict) else {}
            if not isinstance(route_summary.get("run_id"), str) or not route_summary["run_id"].strip():
                errors.append(f"{route_prefix}.route_summary.run_id is required")
            if not isinstance(route_summary.get("selected_workflow"), str) or not route_summary["selected_workflow"].strip():
                errors.append(f"{route_prefix}.route_summary.selected_workflow is required")
            else:
                selected_workflows[(case_id, route)] = str(route_summary["selected_workflow"])
    return errors, selected_workflows


def validate_comparison_holdouts(
    *,
    artifact: dict[str, Any],
    holdout_case_ids: list[str],
    local_eval_selected_workflows: dict[tuple[str, str], str],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    if artifact.get("status") != "passed":
        errors.append(f"{prefix}.comparison.status must be passed")
    if artifact.get("critical_finding_count") != 0:
        errors.append(f"{prefix}.comparison.critical_finding_count must be 0")
    if artifact.get("high_finding_count") != 0:
        errors.append(f"{prefix}.comparison.high_finding_count must be 0")
    if artifact.get("recommended_next_repairs") != []:
        errors.append(f"{prefix}.comparison.recommended_next_repairs must be []")
    cases = cases_by_id(object_list(artifact.get("cases")))
    missing_cases = sorted(set(holdout_case_ids) - set(cases))
    if missing_cases:
        errors.append(f"{prefix}.comparison missing holdout case IDs: " + ", ".join(missing_cases))
    for case_id in holdout_case_ids:
        case = cases.get(case_id)
        if not case:
            continue
        if case.get("holdout") is not True:
            errors.append(f"{prefix}.comparison case {case_id} must record holdout=true")
        routes = {
            str(route_result.get("route")): route_result
            for route_result in object_list(case.get("routes"))
            if isinstance(route_result.get("route"), str) and route_result.get("route")
        }
        route_names = set(routes)
        missing_routes = sorted(REQUIRED_ROUTES - route_names)
        if missing_routes:
            errors.append(f"{prefix}.comparison case {case_id} missing route(s): " + ", ".join(missing_routes))
        extra_routes = sorted(route_names - REQUIRED_ROUTES)
        if extra_routes:
            errors.append(f"{prefix}.comparison case {case_id} has unexpected route(s): " + ", ".join(extra_routes))
        for route in sorted(REQUIRED_ROUTES):
            route_result = routes.get(route)
            if not route_result:
                continue
            route_prefix = f"{prefix}.comparison case {case_id}.{route}"
            if route_result.get("pass") is not True:
                errors.append(f"{route_prefix}.pass must be true")
            score = route_result.get("score")
            if not isinstance(score, int) or score < DEFAULT_MINIMUM_SCORE:
                errors.append(f"{route_prefix}.score must be >= {DEFAULT_MINIMUM_SCORE}")
            if route_result.get("unresolved_findings") != []:
                errors.append(f"{route_prefix}.unresolved_findings must be []")
            if "read_only_boundary_present" in route_result and route_result.get("read_only_boundary_present") is not True:
                errors.append(f"{route_prefix}.read_only_boundary_present must be true")
            if not isinstance(route_result.get("selected_workflow"), str) or not route_result["selected_workflow"].strip():
                errors.append(f"{route_prefix}.selected_workflow is required")
            else:
                expected_workflow = local_eval_selected_workflows.get((case_id, route))
                if expected_workflow and route_result["selected_workflow"] != expected_workflow:
                    errors.append(f"{route_prefix}.selected_workflow must match local_eval route_summary.selected_workflow")
    return errors


def validate_holdout_entry(
    *,
    config_root: Path,
    bank_entry: dict[str, Any],
    corpus_entry: dict[str, Any],
    require_artifacts: bool,
) -> tuple[list[str], dict[str, Any]]:
    entry_id = str(bank_entry.get("entry_id"))
    prefix = f"entries[{entry_id}]"
    errors: list[str] = []
    if bank_entry.get("priority_backlog_id") != corpus_entry.get("priority_backlog_id"):
        errors.append(f"{prefix}.priority_backlog_id must match baseline corpus")
    if bank_entry.get("prompt_family") != corpus_entry.get("prompt_family"):
        errors.append(f"{prefix}.prompt_family must match baseline corpus")

    proof_refs = bank_entry.get("proof_refs") if isinstance(bank_entry.get("proof_refs"), dict) else {}
    errors.extend(
        path_ref_errors(
            config_root=config_root,
            prefix=f"{prefix}.proof_refs.prompt_cases",
            ref=proof_refs.get("prompt_cases"),
            expected_ref=corpus_entry.get("prompt_cases"),
            require_artifacts=True,
        )
    )
    errors.extend(
        path_ref_errors(
            config_root=config_root,
            prefix=f"{prefix}.proof_refs.blind_baselines",
            ref=proof_refs.get("blind_baselines"),
            expected_ref=corpus_entry.get("blind_baselines"),
            require_artifacts=True,
        )
    )
    errors.extend(
        path_ref_errors(
            config_root=config_root,
            prefix=f"{prefix}.proof_refs.local_eval",
            ref=proof_refs.get("local_eval"),
            expected_ref=corpus_entry.get("local_eval"),
            require_artifacts=require_artifacts,
        )
    )
    errors.extend(
        path_ref_errors(
            config_root=config_root,
            prefix=f"{prefix}.proof_refs.comparison",
            ref=proof_refs.get("comparison"),
            expected_ref=corpus_entry.get("comparison"),
            require_artifacts=require_artifacts,
        )
    )
    if errors:
        return errors, {
            "entry_id": entry_id,
            "holdout_case_ids": string_list(bank_entry.get("holdout_case_ids")),
            "holdout_response_count": 0,
        }

    prompt_ref = proof_refs["prompt_cases"]
    baseline_ref = proof_refs["blind_baselines"]
    prompt_cases = read_json_object(resolve_path(config_root, str(prompt_ref["path"])))
    baselines = read_json_object(resolve_path(config_root, str(baseline_ref["path"])))
    holdout_case_ids = string_list(bank_entry.get("holdout_case_ids"))
    errors.extend(
        validate_prompt_and_baseline_holdouts(
            bank_entry=bank_entry,
            corpus_entry=corpus_entry,
            prompt_cases=prompt_cases,
            baselines=baselines,
            prefix=prefix,
        )
    )

    local_eval_selected_workflows: dict[tuple[str, str], str] = {}
    local_eval_path = resolve_path(config_root, str(proof_refs["local_eval"]["path"]))
    if local_eval_path.is_file():
        local_eval_errors, local_eval_selected_workflows = validate_local_eval_holdouts(
            artifact=read_json_object(local_eval_path),
            holdout_case_ids=holdout_case_ids,
            prefix=prefix,
        )
        errors.extend(local_eval_errors)
    comparison_path = resolve_path(config_root, str(proof_refs["comparison"]["path"]))
    if comparison_path.is_file():
        errors.extend(
            validate_comparison_holdouts(
                artifact=read_json_object(comparison_path),
                holdout_case_ids=holdout_case_ids,
                local_eval_selected_workflows=local_eval_selected_workflows,
                prefix=prefix,
            )
        )
    proof_hashes = {
        name: {
            "path": proof_refs[name]["path"],
            "expected_sha256": proof_refs[name]["sha256"],
            "actual_sha256": sha256_file(resolve_path(config_root, str(proof_refs[name]["path"])))
            if resolve_path(config_root, str(proof_refs[name]["path"])).is_file()
            else None,
        }
        for name in ("prompt_cases", "blind_baselines", "local_eval", "comparison")
    }
    return errors, {
        "entry_id": entry_id,
        "priority_backlog_id": bank_entry.get("priority_backlog_id"),
        "prompt_family": bank_entry.get("prompt_family"),
        "holdout_case_ids": holdout_case_ids,
        "holdout_case_count": len(holdout_case_ids),
        "holdout_response_count": len(holdout_case_ids) * len(REQUIRED_ROUTES),
        "target_coverage": bank_entry.get("target_coverage") if isinstance(bank_entry.get("target_coverage"), dict) else {},
        "proof_hashes": proof_hashes,
        "error_count": len(errors),
    }


def validate_holdout_prompt_bank(
    bank: dict[str, Any],
    corpus: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool = False,
) -> tuple[list[str], list[dict[str, Any]]]:
    errors = validate_bank_shape(bank, corpus)
    checked_entries: list[dict[str, Any]] = []
    if errors:
        return errors, checked_entries
    corpus_by_id = stable_corpus_entries_by_id(corpus)
    for entry_id, bank_entry in sorted(bank_entries_by_id(bank).items()):
        entry_errors, summary = validate_holdout_entry(
            config_root=config_root,
            bank_entry=bank_entry,
            corpus_entry=corpus_by_id[entry_id],
            require_artifacts=require_artifacts,
        )
        errors.extend(entry_errors)
        checked_entries.append(summary)
    return errors, checked_entries


def run_holdout_prompt_bank_validation(config: HoldoutPromptBankConfig) -> dict[str, Any]:
    config_root = config.config_root
    corpus = read_json_object(resolve_path(config_root, config.corpus_path))
    bank = read_json_object(resolve_path(config_root, config.bank_path))
    errors, checked_entries = validate_holdout_prompt_bank(
        bank,
        corpus,
        config_root=config_root,
        require_artifacts=config.require_artifacts,
    )
    status = HoldoutPromptBankStatus.PASSED if not errors else HoldoutPromptBankStatus.FAILED
    report: dict[str, Any] = {
        "kind": "holdout_prompt_bank_report",
        "schema_version": SCHEMA_VERSION,
        "status": status.value,
        "generated_at": utc_timestamp(),
        "require_artifacts": config.require_artifacts,
        "bank_path": str(config.bank_path),
        "corpus_path": str(config.corpus_path),
        "summary": {
            "entry_count": len(checked_entries),
            "holdout_case_count": sum(int(entry.get("holdout_case_count", 0)) for entry in checked_entries),
            "holdout_response_count": sum(int(entry.get("holdout_response_count", 0)) for entry in checked_entries),
            "error_count": len(errors),
        },
        "entries": checked_entries,
        "errors": errors,
    }
    write_json(config.output_path or default_report_path(config_root), report)
    return report
