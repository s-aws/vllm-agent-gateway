"""Fresh local-model drift gate validation for Priority 0 stable corpus."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import validate_baseline_corpus


SCHEMA_VERSION = 1
DEFAULT_CATALOG_PATH = Path("runtime") / "fresh_local_model_drift_cases.json"
DEFAULT_BASELINE_CORPUS_PATH = Path("runtime") / "baseline_corpus.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "fresh-local-model-drift" / "phase127"
EXPECTED_OUTPUT_ROOT = "runtime-state/fresh-local-model-drift/phase127"
EXPECTED_FAMILY_IDS = {
    "phase116_code_quality",
    "phase117_defect_diagnosis",
    "phase118_engineering_judgment",
    "phase119_delivery_mentorship",
}
REQUIRED_ROUTES = {"gateway", "anythingllm"}
REQUIRED_COINBASE_TARGETS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}
MINIMUM_ROUTE_SCORE = 85


class FreshLocalModelDriftStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class DriftSeverity(str, Enum):
    NONE = "none"
    WATCH = "watch"
    FAILED = "failed"


@dataclass(frozen=True)
class FreshLocalModelDriftConfig:
    config_root: Path
    catalog_path: Path = DEFAULT_CATALOG_PATH
    baseline_corpus_path: Path = DEFAULT_BASELINE_CORPUS_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"fresh-local-model-drift-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def is_under_path(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def stable_baseline_entries(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry["entry_id"]): entry
        for entry in object_list(corpus.get("entries"))
        if entry.get("status") == "stable" and isinstance(entry.get("entry_id"), str)
    }


def prompt_case_lookup(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json_object(path)
    return {
        str(item["case_id"]): item
        for item in object_list(payload.get("cases"))
        if isinstance(item.get("case_id"), str)
    }


def baseline_case_ids(path: Path) -> set[str]:
    payload = read_json_object(path)
    return {str(item["case_id"]) for item in object_list(payload.get("baselines")) if isinstance(item.get("case_id"), str)}


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def selected_case_ids(local_eval: dict[str, Any]) -> list[str]:
    return [str(item.get("case_id")) for item in object_list(dict_value(local_eval.get("checks")).get("cases"))]


def selected_target_roots_from_cases(cases: dict[str, dict[str, Any]], case_ids: list[str]) -> set[str]:
    return {
        str(cases[case_id].get("target_root"))
        for case_id in case_ids
        if case_id in cases and isinstance(cases[case_id].get("target_root"), str)
    }


def routes_for_comparison_case(case: dict[str, Any]) -> set[str]:
    return {str(item.get("route")) for item in object_list(case.get("routes")) if isinstance(item.get("route"), str)}


def minimum_route_score(comparison: dict[str, Any]) -> int | None:
    scores: list[int] = []
    for case in object_list(comparison.get("cases")):
        for route in object_list(case.get("routes")):
            score = route.get("score")
            if isinstance(score, int):
                scores.append(score)
    return min(scores) if scores else None


def comparison_case_ids(comparison: dict[str, Any]) -> list[str]:
    return [str(item.get("case_id")) for item in object_list(comparison.get("cases"))]


def normalize_mutation_value(value: object) -> object:
    if value in (None, [], {}):
        return value
    return value


def family_prefix(family: dict[str, Any]) -> str:
    return f"catalog.families[{family.get('family_id')}]"


def family_output_root(config_root: Path, catalog: dict[str, Any]) -> Path:
    output_root = str(catalog.get("output_root") or EXPECTED_OUTPUT_ROOT)
    return resolve_path(config_root, output_root)


def validate_catalog_paths_against_baseline(
    *,
    family: dict[str, Any],
    baseline_entry: dict[str, Any],
    config_root: Path,
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    prompt_ref = dict_value(baseline_entry.get("prompt_cases"))
    baseline_ref = dict_value(baseline_entry.get("blind_baselines"))
    if family.get("cases_path") != prompt_ref.get("path"):
        errors.append(f"{prefix}.cases_path must match baseline corpus prompt_cases.path")
    if family.get("baselines_path") != baseline_ref.get("path"):
        errors.append(f"{prefix}.baselines_path must match baseline corpus blind_baselines.path")

    cases_path = resolve_path(config_root, str(family.get("cases_path") or ""))
    baselines_path = resolve_path(config_root, str(family.get("baselines_path") or ""))
    if cases_path.is_file() and prompt_ref.get("sha256") != sha256_file(cases_path):
        errors.append(f"{prefix}.cases_path hash is stale against baseline corpus")
    if baselines_path.is_file() and baseline_ref.get("sha256") != sha256_file(baselines_path):
        errors.append(f"{prefix}.baselines_path hash is stale against baseline corpus")
    return errors


def validate_fresh_local_model_drift_catalog(
    catalog: dict[str, Any],
    *,
    config_root: Path,
    baseline_corpus: dict[str, Any] | None = None,
    require_baseline_artifacts: bool = False,
) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append("catalog.schema_version must be 1")
    if catalog.get("kind") != "fresh_local_model_drift_case_catalog":
        errors.append("catalog.kind must be fresh_local_model_drift_case_catalog")
    if catalog.get("phase") != 127:
        errors.append("catalog.phase must be 127")
    if catalog.get("priority_backlog_id") != "P0-BB-012":
        errors.append("catalog.priority_backlog_id must be P0-BB-012")
    if set(string_list(catalog.get("required_routes"))) != REQUIRED_ROUTES:
        errors.append("catalog.required_routes must be gateway and anythingllm")

    output_root_value = catalog.get("output_root")
    if output_root_value != EXPECTED_OUTPUT_ROOT:
        errors.append(f"catalog.output_root must be {EXPECTED_OUTPUT_ROOT}")
    output_root = family_output_root(config_root, catalog)

    baseline_entries: dict[str, dict[str, Any]] = {}
    if baseline_corpus:
        baseline_errors = validate_baseline_corpus(
            baseline_corpus,
            config_root=config_root,
            require_artifacts=require_baseline_artifacts,
        )
        errors.extend(f"baseline_corpus: {error}" for error in baseline_errors)
        baseline_entries = stable_baseline_entries(baseline_corpus)

    families = object_list(catalog.get("families"))
    family_ids = [str(item.get("family_id")) for item in families if isinstance(item.get("family_id"), str)]
    if set(family_ids) != EXPECTED_FAMILY_IDS:
        errors.append("catalog.families must exactly cover stable Phase 116-119 family IDs")
    if duplicate_values(family_ids):
        errors.append("catalog.families must not contain duplicate family IDs")

    for family in families:
        family_id = str(family.get("family_id"))
        prefix = family_prefix(family)
        baseline_entry = baseline_entries.get(family_id)
        if baseline_entry:
            if family.get("priority_backlog_id") != baseline_entry.get("priority_backlog_id"):
                errors.append(f"{prefix}.priority_backlog_id must match baseline corpus")
            errors.extend(
                validate_catalog_paths_against_baseline(
                    family=family,
                    baseline_entry=baseline_entry,
                    config_root=config_root,
                    prefix=prefix,
                )
            )
        elif baseline_entries:
            errors.append(f"{prefix}.family_id is not a stable baseline corpus entry")

        for key in ("run_script", "compare_script", "cases_path", "baselines_path"):
            value = family.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{key} is required")
            elif not resolve_path(config_root, value).is_file():
                errors.append(f"{prefix}.{key} does not exist: {value}")

        for key in ("fresh_local_eval_path", "fresh_comparison_path"):
            value = family.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{key} is required")
                continue
            resolved = resolve_path(config_root, value)
            if not is_under_path(resolved, output_root):
                errors.append(f"{prefix}.{key} must live under {EXPECTED_OUTPUT_ROOT}")
            if baseline_entry:
                old_ref_key = "local_eval" if key == "fresh_local_eval_path" else "comparison"
                old_path = dict_value(baseline_entry.get(old_ref_key)).get("path")
                if value == old_path:
                    errors.append(f"{prefix}.{key} must not overwrite accepted baseline corpus artifacts")

        case_ids = string_list(family.get("case_ids"))
        duplicates = duplicate_values(case_ids)
        if duplicates:
            errors.append(f"{prefix}.case_ids must not contain duplicates: {', '.join(duplicates)}")
        if len(case_ids) < len(REQUIRED_COINBASE_TARGETS):
            errors.append(f"{prefix}.case_ids must include at least one case per frozen Coinbase target")
        expected_response_count = family.get("expected_response_count")
        if not isinstance(expected_response_count, int) or expected_response_count != len(case_ids) * len(REQUIRED_ROUTES):
            errors.append(f"{prefix}.expected_response_count must equal case_ids * required_routes")

        cases_path = family.get("cases_path")
        baselines_path = family.get("baselines_path")
        if isinstance(cases_path, str) and resolve_path(config_root, cases_path).is_file():
            available = prompt_case_lookup(resolve_path(config_root, cases_path))
            missing = sorted(set(case_ids) - set(available))
            if missing:
                errors.append(f"{prefix}.case_ids missing from governed prompt cases: {', '.join(missing)}")
            roots = selected_target_roots_from_cases(available, case_ids)
            if roots != REQUIRED_COINBASE_TARGETS:
                errors.append(f"{prefix}.case_ids must cover exactly both frozen Coinbase target roots")
        if isinstance(baselines_path, str) and resolve_path(config_root, baselines_path).is_file():
            baseline_ids = baseline_case_ids(resolve_path(config_root, baselines_path))
            missing = sorted(set(case_ids) - baseline_ids)
            if missing:
                errors.append(f"{prefix}.case_ids missing from blind baselines: {', '.join(missing)}")
    return errors


def command_result_errors(command: dict[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []
    if command.get("returncode") != 0:
        errors.append(f"{prefix}.returncode must be 0")
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv:
        errors.append(f"{prefix}.argv is required")
    if not isinstance(command.get("duration_seconds"), (int, float)):
        errors.append(f"{prefix}.duration_seconds is required")
    return errors


def prior_comparison_errors(prior: dict[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []
    if prior.get("status") != FreshLocalModelDriftStatus.PASSED.value:
        errors.append(f"{prefix}.status must be passed")
    if prior.get("critical_finding_count") != 0:
        errors.append(f"{prefix}.critical_finding_count must be 0")
    if prior.get("high_finding_count") != 0:
        errors.append(f"{prefix}.high_finding_count must be 0")
    if dict_value(prior.get("gap_categories")):
        errors.append(f"{prefix}.gap_categories must be empty")
    return errors


def comparison_errors(
    comparison: dict[str, Any],
    *,
    prefix: str,
    expected_case_ids: list[str],
    expected_response_count: int,
    prior_comparison: dict[str, Any],
) -> tuple[list[str], int | None, DriftSeverity]:
    errors: list[str] = []
    if comparison.get("status") != FreshLocalModelDriftStatus.PASSED.value:
        errors.append(f"{prefix}.status must be passed")
    if comparison.get("response_count") != expected_response_count:
        errors.append(f"{prefix}.response_count must equal selected case count * required routes")
    if comparison.get("passed_response_count") != expected_response_count:
        errors.append(f"{prefix}.passed_response_count must equal response_count")
    if comparison.get("critical_finding_count") != 0:
        errors.append(f"{prefix}.critical_finding_count must be 0")
    if comparison.get("high_finding_count") != 0:
        errors.append(f"{prefix}.high_finding_count must be 0")
    if dict_value(comparison.get("gap_categories")):
        errors.append(f"{prefix}.gap_categories must be empty")
    if comparison.get("recommended_next_repairs") not in ([], None):
        errors.append(f"{prefix}.recommended_next_repairs must be empty")

    if comparison_case_ids(comparison) != expected_case_ids:
        errors.append(f"{prefix}.cases must match selected catalog case IDs in order")
    for case in object_list(comparison.get("cases")):
        case_prefix = f"{prefix}.cases[{case.get('case_id')}]"
        routes = routes_for_comparison_case(case)
        if routes != REQUIRED_ROUTES:
            errors.append(f"{case_prefix}.routes must exactly include gateway and anythingllm")
        for route in object_list(case.get("routes")):
            route_prefix = f"{case_prefix}.routes[{route.get('route')}]"
            if route.get("pass") is not True:
                errors.append(f"{route_prefix}.pass must be true")
            score = route.get("score")
            if not isinstance(score, int) or score < MINIMUM_ROUTE_SCORE:
                errors.append(f"{route_prefix}.score must be at least {MINIMUM_ROUTE_SCORE}")
            if object_list(route.get("unresolved_findings")):
                errors.append(f"{route_prefix}.unresolved_findings must be empty")

    min_score = minimum_route_score(comparison)
    prior_min = prior_comparison.get("minimum_route_score")
    if min_score is None:
        errors.append(f"{prefix}.minimum_route_score could not be derived")
        return errors, min_score, DriftSeverity.FAILED
    if not isinstance(prior_min, int):
        errors.append(f"{prefix}.prior.minimum_route_score is required")
        return errors, min_score, DriftSeverity.FAILED
    if min_score < prior_min:
        errors.append(f"{prefix}.minimum_route_score regressed below prior accepted result")
        return errors, min_score, DriftSeverity.WATCH
    return errors, min_score, DriftSeverity.NONE


def local_eval_errors(
    local_eval: dict[str, Any],
    *,
    prefix: str,
    expected_case_ids: list[str],
    expected_case_targets: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    if local_eval.get("status") != "captured":
        errors.append(f"{prefix}.status must be captured")
    if local_eval.get("case_count") != len(expected_case_ids):
        errors.append(f"{prefix}.case_count must match catalog case_ids")
    if selected_case_ids(local_eval) != expected_case_ids:
        errors.append(f"{prefix}.checks.cases must match catalog case_ids in order")
    target_roots = set(string_list(local_eval.get("target_roots")))
    if target_roots != REQUIRED_COINBASE_TARGETS:
        errors.append(f"{prefix}.target_roots must exactly cover both frozen Coinbase target roots")

    for case in object_list(dict_value(local_eval.get("checks")).get("cases")):
        case_id = str(case.get("case_id"))
        case_prefix = f"{prefix}.checks.cases[{case_id}]"
        if case.get("target_root") != expected_case_targets.get(case_id):
            errors.append(f"{case_prefix}.target_root must match governed prompt case")
        responses = case.get("responses") if isinstance(case.get("responses"), dict) else {}
        if set(str(route) for route in responses) != REQUIRED_ROUTES:
            errors.append(f"{case_prefix}.responses must exactly include gateway and anythingllm")
        for route, response in responses.items():
            response_prefix = f"{case_prefix}.responses[{route}]"
            if not isinstance(response, dict):
                errors.append(f"{response_prefix} must be an object")
                continue
            if response.get("status") != "captured":
                errors.append(f"{response_prefix}.status must be captured")
            if response.get("http_status") != 200:
                errors.append(f"{response_prefix}.http_status must be 200")
            if not isinstance(response.get("text"), str) or not response["text"].strip():
                errors.append(f"{response_prefix}.text must be non-empty")

    if normalize_mutation_value(local_eval.get("runtime_changed_files")) not in ([], None):
        errors.append(f"{prefix}.runtime_changed_files must be empty")
    if normalize_mutation_value(local_eval.get("target_changed_files")) not in ({}, None):
        errors.append(f"{prefix}.target_changed_files must be empty")
    if normalize_mutation_value(local_eval.get("target_git_changed")) not in ({}, None):
        errors.append(f"{prefix}.target_git_changed must be empty")
    return errors


def source_hashes_for_family(config_root: Path, family: dict[str, Any]) -> dict[str, str | None]:
    cases_path = resolve_path(config_root, str(family.get("cases_path") or ""))
    baselines_path = resolve_path(config_root, str(family.get("baselines_path") or ""))
    return {
        "prompt_cases_sha256": artifact_hash(cases_path),
        "blind_baselines_sha256": artifact_hash(baselines_path),
    }


def expected_case_targets_for_family(config_root: Path, family: dict[str, Any]) -> dict[str, str]:
    cases = prompt_case_lookup(resolve_path(config_root, str(family.get("cases_path") or "")))
    return {
        case_id: str(cases[case_id].get("target_root"))
        for case_id in string_list(family.get("case_ids"))
        if case_id in cases and isinstance(cases[case_id].get("target_root"), str)
    }


def validate_fresh_local_model_drift_report(
    report: dict[str, Any],
    *,
    catalog: dict[str, Any],
    baseline_corpus: dict[str, Any],
    config_root: Path,
    require_artifacts: bool = False,
) -> list[str]:
    errors = validate_fresh_local_model_drift_catalog(
        catalog,
        config_root=config_root,
        baseline_corpus=baseline_corpus,
        require_baseline_artifacts=require_artifacts,
    )
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != "fresh_local_model_drift_report":
        errors.append("report.kind must be fresh_local_model_drift_report")
    if report.get("phase") != 127:
        errors.append("report.phase must be 127")
    if report.get("priority_backlog_id") != "P0-BB-012":
        errors.append("report.priority_backlog_id must be P0-BB-012")

    baseline_entries = stable_baseline_entries(baseline_corpus)
    family_results = {
        str(item.get("family_id")): item
        for item in object_list(report.get("families"))
        if isinstance(item.get("family_id"), str)
    }
    catalog_families = {
        str(item.get("family_id")): item
        for item in object_list(catalog.get("families"))
        if isinstance(item.get("family_id"), str)
    }
    if set(family_results) != set(catalog_families):
        errors.append("report.families must exactly match catalog families")

    total_response_count = 0
    total_passed_count = 0
    failed_family_count = 0
    derived_min_scores: dict[str, int] = {}
    drift_severities: dict[str, DriftSeverity] = {}

    for family_id, family in catalog_families.items():
        prefix = f"report.families[{family_id}]"
        result = family_results.get(family_id)
        if not isinstance(result, dict):
            continue
        family_error_count_before = len(errors)
        baseline_entry = baseline_entries.get(family_id, {})
        prior_comparison = dict_value(baseline_entry.get("comparison"))
        expected_response_count = int(family.get("expected_response_count", 0))
        expected_case_ids = string_list(family.get("case_ids"))
        expected_case_targets = expected_case_targets_for_family(config_root, family)
        expected_source_hashes = source_hashes_for_family(config_root, family)

        if result.get("case_ids") != expected_case_ids:
            errors.append(f"{prefix}.case_ids must match catalog")
        if set(string_list(result.get("target_roots"))) != REQUIRED_COINBASE_TARGETS:
            errors.append(f"{prefix}.target_roots must cover both frozen Coinbase roots")
        if dict_value(result.get("source_hashes")) != expected_source_hashes:
            errors.append(f"{prefix}.source_hashes must match current governed source files")
        commands = result.get("commands") if isinstance(result.get("commands"), dict) else {}
        errors.extend(command_result_errors(dict_value(commands.get("local_eval")), prefix=f"{prefix}.commands.local_eval"))
        errors.extend(command_result_errors(dict_value(commands.get("comparison")), prefix=f"{prefix}.commands.comparison"))

        comparison_path_value = result.get("fresh_comparison_path")
        local_eval_path_value = result.get("fresh_local_eval_path")
        if comparison_path_value != family.get("fresh_comparison_path"):
            errors.append(f"{prefix}.fresh_comparison_path must match catalog")
        if local_eval_path_value != family.get("fresh_local_eval_path"):
            errors.append(f"{prefix}.fresh_local_eval_path must match catalog")

        comparison_path = resolve_path(config_root, str(comparison_path_value or ""))
        local_eval_path = resolve_path(config_root, str(local_eval_path_value or ""))
        if require_artifacts:
            if not comparison_path.is_file():
                errors.append(f"{prefix}.fresh_comparison_path does not exist")
            if not local_eval_path.is_file():
                errors.append(f"{prefix}.fresh_local_eval_path does not exist")

        comparison = read_json_object(comparison_path) if comparison_path.is_file() else dict_value(result.get("comparison"))
        local_eval = read_json_object(local_eval_path) if local_eval_path.is_file() else dict_value(result.get("local_eval_summary"))
        errors.extend(prior_comparison_errors(prior_comparison, prefix=f"{prefix}.prior_comparison"))

        comparison_error_list, min_score, drift_severity = comparison_errors(
            comparison,
            prefix=f"{prefix}.comparison",
            expected_case_ids=expected_case_ids,
            expected_response_count=expected_response_count,
            prior_comparison=prior_comparison,
        )
        errors.extend(comparison_error_list)
        drift_severities[family_id] = drift_severity
        if isinstance(min_score, int):
            derived_min_scores[family_id] = min_score

        errors.extend(
            local_eval_errors(
                local_eval,
                prefix=f"{prefix}.local_eval",
                expected_case_ids=expected_case_ids,
                expected_case_targets=expected_case_targets,
            )
        )

        comparison_hash = artifact_hash(comparison_path)
        local_eval_hash = artifact_hash(local_eval_path)
        if result.get("fresh_comparison_sha256") != comparison_hash:
            errors.append(f"{prefix}.fresh_comparison_sha256 is stale or missing")
        if result.get("fresh_local_eval_sha256") != local_eval_hash:
            errors.append(f"{prefix}.fresh_local_eval_sha256 is stale or missing")
        if comparison_hash and comparison_hash == dict_value(prior_comparison).get("sha256"):
            errors.append(f"{prefix}.fresh_comparison_sha256 must not match accepted baseline comparison hash")
        if local_eval_hash and local_eval_hash == dict_value(baseline_entry.get("local_eval")).get("sha256"):
            errors.append(f"{prefix}.fresh_local_eval_sha256 must not match accepted baseline eval hash")

        if result.get("minimum_route_score") != min_score:
            errors.append(f"{prefix}.minimum_route_score must match derived comparison minimum")
        if result.get("drift_severity") != drift_severity.value:
            errors.append(f"{prefix}.drift_severity must match derived drift severity")
        expected_family_status = (
            FreshLocalModelDriftStatus.PASSED.value
            if len(errors) == family_error_count_before
            else FreshLocalModelDriftStatus.FAILED.value
        )
        if result.get("status") != expected_family_status:
            errors.append(f"{prefix}.status must reflect family proof errors")

        total_response_count += int(comparison.get("response_count") or 0)
        total_passed_count += int(comparison.get("passed_response_count") or 0)
        if result.get("status") != FreshLocalModelDriftStatus.PASSED.value:
            failed_family_count += 1

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("family_count") != len(catalog_families):
        errors.append("summary.family_count must match catalog")
    if summary.get("selected_case_count") != sum(len(string_list(family.get("case_ids"))) for family in catalog_families.values()):
        errors.append("summary.selected_case_count must equal selected catalog cases")
    if summary.get("response_count") != total_response_count:
        errors.append("summary.response_count must match fresh comparisons")
    if summary.get("passed_response_count") != total_passed_count:
        errors.append("summary.passed_response_count must match fresh comparisons")
    if summary.get("failed_family_count") != failed_family_count:
        errors.append("summary.failed_family_count must match family results")
    if summary.get("critical_finding_count") != 0:
        errors.append("summary.critical_finding_count must be 0")
    if summary.get("high_finding_count") != 0:
        errors.append("summary.high_finding_count must be 0")
    if dict_value(summary.get("gap_categories")):
        errors.append("summary.gap_categories must be empty")
    if set(string_list(summary.get("required_routes"))) != REQUIRED_ROUTES:
        errors.append("summary.required_routes must include gateway and anythingllm")
    if set(string_list(summary.get("target_roots"))) != REQUIRED_COINBASE_TARGETS:
        errors.append("summary.target_roots must include both frozen Coinbase roots")
    if summary.get("minimum_route_scores") != derived_min_scores:
        errors.append("summary.minimum_route_scores must match derived family scores")

    expected_drift_status = (
        "no_drift_detected"
        if drift_severities and all(severity == DriftSeverity.NONE for severity in drift_severities.values())
        else "drift_detected"
    )
    if summary.get("drift_status") != expected_drift_status:
        errors.append("summary.drift_status must match family drift severities")

    expected_status = FreshLocalModelDriftStatus.PASSED.value if not errors else FreshLocalModelDriftStatus.FAILED.value
    if report.get("status") != expected_status:
        errors.append(f"report.status must be {expected_status}")
    return errors


def run_fresh_local_model_drift_validation(config: FreshLocalModelDriftConfig) -> dict[str, Any]:
    config_root = config.config_root
    catalog = read_json_object(resolve_path(config_root, config.catalog_path))
    baseline_corpus = read_json_object(resolve_path(config_root, config.baseline_corpus_path))
    errors = validate_fresh_local_model_drift_catalog(
        catalog,
        config_root=config_root,
        baseline_corpus=baseline_corpus,
        require_baseline_artifacts=config.require_artifacts,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "fresh_local_model_drift_validation_report",
        "phase": 127,
        "priority_backlog_id": "P0-BB-012",
        "status": FreshLocalModelDriftStatus.PASSED.value if not errors else FreshLocalModelDriftStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "catalog_path": str(config.catalog_path),
        "baseline_corpus_path": str(config.baseline_corpus_path),
        "summary": {
            "family_count": len(object_list(catalog.get("families"))),
            "error_count": len(errors),
        },
        "errors": errors,
    }
    write_json(config.output_path or default_report_path(config_root), report)
    return report
