"""Priority 0 blind-baseline corpus governance validation."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_CORPUS_PATH = Path("runtime") / "baseline_corpus.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "baseline-corpus"
REQUIRED_ROUTES = {"gateway", "anythingllm"}
REQUIRED_COINBASE_TARGETS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}
EXPECTED_PHASES = {116, 117, 118, 119}
EXPECTED_BACKLOG_IDS = {"P0-BB-001", "P0-BB-002", "P0-BB-003", "P0-BB-004"}
EXPECTED_BASELINE_COLLECTION_ORDER = "blind_baseline_before_local_model_output"
MINIMUM_SCORE = 85


class CorpusEntryStatus(str, Enum):
    STABLE = "stable"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class RepairStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    ACCEPTED_AND_RERUN = "accepted_and_rerun"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BaselineCorpusConfig:
    config_root: Path
    corpus_path: Path = DEFAULT_CORPUS_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"baseline-corpus-{utc_timestamp()}.json"


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


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def artifact_hash_errors(
    *,
    config_root: Path,
    prefix: str,
    path_value: object,
    hash_value: object,
    required: bool,
) -> list[str]:
    if not isinstance(path_value, str) or not path_value.strip():
        return [f"{prefix}.path is required"]
    if not isinstance(hash_value, str) or len(hash_value) != 64:
        return [f"{prefix}.sha256 must be a 64-character hash"]
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        return [f"{prefix}.path does not exist: {path_value}"] if required else []
    actual = sha256_file(path)
    if actual != hash_value:
        return [f"{prefix}.sha256 is stale for {path_value}"]
    return []


def case_ids_from_prompt_cases(prompt_cases: dict[str, Any]) -> set[str]:
    return {
        str(item.get("case_id"))
        for item in object_list(prompt_cases.get("cases"))
        if isinstance(item.get("case_id"), str) and item.get("case_id")
    }


def case_id_list_from_prompt_cases(prompt_cases: dict[str, Any]) -> list[str]:
    return [
        str(item.get("case_id"))
        for item in object_list(prompt_cases.get("cases"))
        if isinstance(item.get("case_id"), str) and item.get("case_id")
    ]


def case_ids_from_baselines(baselines: dict[str, Any]) -> set[str]:
    return {
        str(item.get("case_id"))
        for item in object_list(baselines.get("baselines"))
        if isinstance(item.get("case_id"), str) and item.get("case_id")
    }


def case_id_list_from_baselines(baselines: dict[str, Any]) -> list[str]:
    return [
        str(item.get("case_id"))
        for item in object_list(baselines.get("baselines"))
        if isinstance(item.get("case_id"), str) and item.get("case_id")
    ]


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def holdout_count(prompt_cases: dict[str, Any]) -> int:
    return sum(1 for item in object_list(prompt_cases.get("cases")) if item.get("holdout") is True)


def validate_baseline_record_content(baselines: dict[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []
    top_level_rubric = isinstance(baselines.get("scoring_rubric_100"), dict)
    for item in object_list(baselines.get("baselines")):
        case_prefix = f"{prefix}.blind_baselines[{item.get('case_id')}]"
        if not isinstance(item.get("ideal_answer_shape"), str) or not item["ideal_answer_shape"].strip():
            errors.append(f"{case_prefix}.ideal_answer_shape is required")
        if not (string_list(item.get("must_have_facts")) or string_list(item.get("must_have_topics"))):
            errors.append(f"{case_prefix} must define must_have_facts or must_have_topics")
        if not (string_list(item.get("evidence_expectations")) or string_list(item.get("must_have_topics"))):
            errors.append(f"{case_prefix} must define evidence_expectations or must_have_topics")
        if not string_list(item.get("safety_boundaries")):
            errors.append(f"{case_prefix}.safety_boundaries is required")
        if not string_list(item.get("likely_local_model_failure_modes")):
            errors.append(f"{case_prefix}.likely_local_model_failure_modes is required")
        if not isinstance(item.get("prompt_tightening_suggestion"), str) or not item["prompt_tightening_suggestion"].strip():
            errors.append(f"{case_prefix}.prompt_tightening_suggestion is required")
        if not (top_level_rubric or isinstance(item.get("scoring_rubric_100"), dict)):
            errors.append(f"{case_prefix}.scoring_rubric_100 is required at baseline or catalog level")
    return errors


def validate_prompt_and_baseline_sources(
    entry: dict[str, Any],
    *,
    config_root: Path,
    prefix: str,
) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None]:
    errors: list[str] = []
    prompt_ref = entry.get("prompt_cases") if isinstance(entry.get("prompt_cases"), dict) else {}
    baseline_ref = entry.get("blind_baselines") if isinstance(entry.get("blind_baselines"), dict) else {}
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix=f"{prefix}.prompt_cases",
            path_value=prompt_ref.get("path"),
            hash_value=prompt_ref.get("sha256"),
            required=True,
        )
    )
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix=f"{prefix}.blind_baselines",
            path_value=baseline_ref.get("path"),
            hash_value=baseline_ref.get("sha256"),
            required=True,
        )
    )
    if errors:
        return errors, None, None
    prompt_cases = read_json_object(resolve_path(config_root, str(prompt_ref["path"])))
    baselines = read_json_object(resolve_path(config_root, str(baseline_ref["path"])))
    expected_case_count = entry.get("expected_case_count")
    if not isinstance(expected_case_count, int) or expected_case_count <= 0:
        errors.append(f"{prefix}.expected_case_count must be a positive integer")
    elif len(object_list(prompt_cases.get("cases"))) != expected_case_count:
        errors.append(f"{prefix}.expected_case_count does not match prompt case count")
    expected_holdout_count = entry.get("expected_holdout_count")
    if not isinstance(expected_holdout_count, int) or expected_holdout_count < 1:
        errors.append(f"{prefix}.expected_holdout_count must be at least 1")
    elif holdout_count(prompt_cases) < expected_holdout_count:
        errors.append(f"{prefix}.prompt_cases has fewer holdouts than expected")
    prompt_case_ids = case_ids_from_prompt_cases(prompt_cases)
    baseline_case_ids = case_ids_from_baselines(baselines)
    duplicate_prompt_ids = duplicate_values(case_id_list_from_prompt_cases(prompt_cases))
    if duplicate_prompt_ids:
        errors.append(f"{prefix}.prompt_cases contains duplicate case IDs: " + ", ".join(duplicate_prompt_ids))
    duplicate_baseline_ids = duplicate_values(case_id_list_from_baselines(baselines))
    if duplicate_baseline_ids:
        errors.append(f"{prefix}.blind_baselines contains duplicate case IDs: " + ", ".join(duplicate_baseline_ids))
    if prompt_case_ids != baseline_case_ids:
        errors.append(f"{prefix}.blind_baselines case IDs do not match prompt cases")
    baseline_policy = baselines.get("baseline_policy") if isinstance(baselines.get("baseline_policy"), dict) else {}
    if baseline_policy.get("blind_agent_context") != "contextless":
        errors.append(f"{prefix}.blind_baselines.baseline_policy must be contextless")
    if baseline_policy.get("local_model_output_seen") is not False:
        errors.append(f"{prefix}.blind_baselines.baseline_policy must record local_model_output_seen=false")
    if baseline_policy.get("source_mutation_allowed") is not False:
        errors.append(f"{prefix}.blind_baselines.baseline_policy must record source_mutation_allowed=false")
    errors.extend(validate_baseline_record_content(baselines, prefix=prefix))
    return errors, prompt_cases, baselines


def validate_local_eval_summary(
    entry: dict[str, Any],
    *,
    config_root: Path,
    prefix: str,
    require_artifacts: bool,
    expected_case_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    local_eval = entry.get("local_eval") if isinstance(entry.get("local_eval"), dict) else {}
    if not local_eval:
        return [f"{prefix}.local_eval is required"]
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix=f"{prefix}.local_eval",
            path_value=local_eval.get("path"),
            hash_value=local_eval.get("sha256"),
            required=require_artifacts,
        )
    )
    if local_eval.get("status") != "captured":
        errors.append(f"{prefix}.local_eval.status must be captured")
    expected_case_count = entry.get("expected_case_count")
    if local_eval.get("case_count") != expected_case_count:
        errors.append(f"{prefix}.local_eval.case_count must match expected_case_count")
    routes = set(string_list(local_eval.get("routes")))
    missing_routes = sorted(REQUIRED_ROUTES - routes)
    if missing_routes:
        errors.append(f"{prefix}.local_eval.routes missing required route(s): " + ", ".join(missing_routes))
    target_roots = set(string_list(local_eval.get("target_roots")))
    missing_targets = sorted(REQUIRED_COINBASE_TARGETS - target_roots)
    if missing_targets:
        errors.append(f"{prefix}.local_eval.target_roots missing required target(s): " + ", ".join(missing_targets))
    mutation_proof = local_eval.get("mutation_proof") if isinstance(local_eval.get("mutation_proof"), dict) else {}
    if mutation_proof.get("runtime_changed_files") != []:
        errors.append(f"{prefix}.local_eval.mutation_proof.runtime_changed_files must be []")
    if mutation_proof.get("target_changed_files") != {}:
        errors.append(f"{prefix}.local_eval.mutation_proof.target_changed_files must be {{}}")
    if mutation_proof.get("target_git_changed") not in ({}, None):
        errors.append(f"{prefix}.local_eval.mutation_proof.target_git_changed must be empty when present")
    if errors:
        return errors
    path_value = local_eval.get("path")
    if isinstance(path_value, str) and resolve_path(config_root, path_value).is_file():
        artifact = read_json_object(resolve_path(config_root, path_value))
        cases = object_list(artifact.get("checks", {}).get("cases") if isinstance(artifact.get("checks"), dict) else [])
        if len(cases) != expected_case_count:
            errors.append(f"{prefix}.local_eval artifact case count does not match expected_case_count")
        artifact_case_ids = {str(case.get("case_id")) for case in cases if isinstance(case.get("case_id"), str)}
        if expected_case_ids is not None and artifact_case_ids != expected_case_ids:
            errors.append(f"{prefix}.local_eval artifact case IDs do not match prompt cases")
        for case in cases:
            responses = case.get("responses") if isinstance(case.get("responses"), dict) else {}
            missing = sorted(REQUIRED_ROUTES - set(responses))
            if missing:
                errors.append(f"{prefix}.local_eval artifact case {case.get('case_id')} missing route(s): " + ", ".join(missing))
            for route in REQUIRED_ROUTES:
                route_response = responses.get(route)
                if isinstance(route_response, dict) and route_response.get("status") not in {None, "captured"}:
                    errors.append(f"{prefix}.local_eval artifact case {case.get('case_id')} route {route} not captured")
        if artifact.get("runtime_changed_files") != []:
            errors.append(f"{prefix}.local_eval artifact runtime_changed_files must be []")
        if artifact.get("target_changed_files") != {}:
            errors.append(f"{prefix}.local_eval artifact target_changed_files must be {{}}")
        if artifact.get("target_git_changed") not in ({}, None):
            errors.append(f"{prefix}.local_eval artifact target_git_changed must be empty when present")
    return errors


def validate_comparison_summary(
    entry: dict[str, Any],
    *,
    config_root: Path,
    prefix: str,
    require_artifacts: bool,
    expected_case_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    comparison = entry.get("comparison") if isinstance(entry.get("comparison"), dict) else {}
    if not comparison:
        return [f"{prefix}.comparison is required"]
    errors.extend(
        artifact_hash_errors(
            config_root=config_root,
            prefix=f"{prefix}.comparison",
            path_value=comparison.get("path"),
            hash_value=comparison.get("sha256"),
            required=require_artifacts,
        )
    )
    expected_response_count = entry.get("expected_response_count")
    if comparison.get("status") != "passed":
        errors.append(f"{prefix}.comparison.status must be passed")
    if comparison.get("response_count") != expected_response_count:
        errors.append(f"{prefix}.comparison.response_count must match expected_response_count")
    if comparison.get("passed_response_count") != comparison.get("response_count"):
        errors.append(f"{prefix}.comparison.passed_response_count must equal response_count")
    if not isinstance(comparison.get("minimum_route_score"), int) or comparison["minimum_route_score"] < MINIMUM_SCORE:
        errors.append(f"{prefix}.comparison.minimum_route_score must be >= {MINIMUM_SCORE}")
    if comparison.get("critical_finding_count") != 0:
        errors.append(f"{prefix}.comparison.critical_finding_count must be 0")
    if comparison.get("high_finding_count") != 0:
        errors.append(f"{prefix}.comparison.high_finding_count must be 0")
    if comparison.get("recommended_next_repairs") != []:
        errors.append(f"{prefix}.comparison.recommended_next_repairs must be [] for stable entries")
    if comparison.get("gap_categories") not in ({}, None):
        errors.append(f"{prefix}.comparison.gap_categories must be empty for stable entries")
    inputs = comparison.get("inputs") if isinstance(comparison.get("inputs"), dict) else {}
    prompt_ref = entry.get("prompt_cases") if isinstance(entry.get("prompt_cases"), dict) else {}
    baseline_ref = entry.get("blind_baselines") if isinstance(entry.get("blind_baselines"), dict) else {}
    local_eval = entry.get("local_eval") if isinstance(entry.get("local_eval"), dict) else {}
    for input_key, source_ref, source_field in (
        ("prompt_cases_sha256", prompt_ref, "prompt_cases"),
        ("blind_baselines_sha256", baseline_ref, "blind_baselines"),
        ("local_eval_sha256", local_eval, "local_eval"),
    ):
        if inputs.get(input_key) != source_ref.get("sha256"):
            errors.append(f"{prefix}.comparison.inputs.{input_key} must match {source_field}.sha256")
    if errors:
        return errors
    path_value = comparison.get("path")
    if isinstance(path_value, str) and resolve_path(config_root, path_value).is_file():
        artifact = read_json_object(resolve_path(config_root, path_value))
        if artifact.get("status") != comparison.get("status"):
            errors.append(f"{prefix}.comparison artifact status does not match summary")
        artifact_cases = object_list(artifact.get("cases"))
        artifact_case_ids = {str(case.get("case_id")) for case in artifact_cases if isinstance(case.get("case_id"), str)}
        if expected_case_ids is not None and artifact_case_ids != expected_case_ids:
            errors.append(f"{prefix}.comparison artifact case IDs do not match prompt cases")
        for field in ("response_count", "passed_response_count", "critical_finding_count", "high_finding_count"):
            if artifact.get(field) != comparison.get(field):
                errors.append(f"{prefix}.comparison artifact {field} does not match summary")
        min_score: int | None = None
        for case in artifact_cases:
            for route in object_list(case.get("routes")):
                if route.get("pass") is not True:
                    errors.append(f"{prefix}.comparison artifact route did not pass for {case.get('case_id')}")
                score = route.get("score")
                if not isinstance(score, int):
                    errors.append(f"{prefix}.comparison artifact route score is missing for {case.get('case_id')}")
                elif score < MINIMUM_SCORE:
                    errors.append(f"{prefix}.comparison artifact route score below {MINIMUM_SCORE} for {case.get('case_id')}")
                elif min_score is None or score < min_score:
                    min_score = score
                for finding in object_list(route.get("unresolved_findings")):
                    if finding.get("severity") in {"critical", "high"}:
                        errors.append(f"{prefix}.comparison artifact has unresolved critical/high finding")
        if min_score is not None and min_score != comparison.get("minimum_route_score"):
            errors.append(f"{prefix}.comparison.minimum_route_score does not match artifact route scores")
    return errors


def validate_repair_status(entry: dict[str, Any], *, prefix: str) -> list[str]:
    repair = entry.get("repair_status") if isinstance(entry.get("repair_status"), dict) else {}
    if not repair:
        return [f"{prefix}.repair_status is required"]
    status = repair.get("status")
    if status not in {item.value for item in RepairStatus}:
        return [f"{prefix}.repair_status.status must be supported"]
    errors: list[str] = []
    if repair.get("stale") is not False:
        errors.append(f"{prefix}.repair_status.stale must be false")
    comparison = entry.get("comparison") if isinstance(entry.get("comparison"), dict) else {}
    recommended_repairs = comparison.get("recommended_next_repairs")
    if recommended_repairs and status == RepairStatus.NOT_REQUIRED.value:
        errors.append(f"{prefix}.repair_status cannot be not_required when comparison recommends repairs")
    if status == RepairStatus.ACCEPTED_AND_RERUN.value and repair.get("holdout_rerun_status") != "passed":
        errors.append(f"{prefix}.repair_status.holdout_rerun_status must be passed after accepted repairs")
    return errors


def validate_source_order(entry: dict[str, Any], *, prefix: str) -> list[str]:
    source_order = entry.get("source_order") if isinstance(entry.get("source_order"), dict) else {}
    if not source_order:
        return [f"{prefix}.source_order is required"]
    errors: list[str] = []
    if source_order.get("blind_baseline_collected_before_local_output") is not True:
        errors.append(f"{prefix}.source_order.blind_baseline_collected_before_local_output must be true")
    if source_order.get("local_model_output_seen_by_blind_agent") is not False:
        errors.append(f"{prefix}.source_order.local_model_output_seen_by_blind_agent must be false")
    return errors


def validate_corpus_entry(
    entry: dict[str, Any],
    index: int,
    *,
    config_root: Path,
    require_artifacts: bool,
) -> list[str]:
    prefix = f"entries[{entry.get('entry_id') or index}]"
    errors: list[str] = []
    if entry.get("status") not in {item.value for item in CorpusEntryStatus}:
        errors.append(f"{prefix}.status must be supported")
    if entry.get("phase") not in {116, 117, 118, 119}:
        errors.append(f"{prefix}.phase must be one of the governed Priority 0 phases")
    if not isinstance(entry.get("priority_backlog_id"), str) or not entry["priority_backlog_id"].startswith("P0-BB-"):
        errors.append(f"{prefix}.priority_backlog_id must be a P0-BB id")
    expected_response_count = entry.get("expected_response_count")
    if not isinstance(expected_response_count, int) or expected_response_count <= 0:
        errors.append(f"{prefix}.expected_response_count must be a positive integer")
    expected_case_count = entry.get("expected_case_count")
    if isinstance(expected_case_count, int) and isinstance(expected_response_count, int):
        expected_by_routes = expected_case_count * len(REQUIRED_ROUTES)
        if expected_response_count != expected_by_routes:
            errors.append(f"{prefix}.expected_response_count must equal expected_case_count * required route count")
    source_errors, prompt_cases, _baselines = validate_prompt_and_baseline_sources(entry, config_root=config_root, prefix=prefix)
    errors.extend(source_errors)
    expected_case_ids = case_ids_from_prompt_cases(prompt_cases) if prompt_cases is not None else None
    errors.extend(validate_source_order(entry, prefix=prefix))
    errors.extend(
        validate_local_eval_summary(
            entry,
            config_root=config_root,
            prefix=prefix,
            require_artifacts=require_artifacts,
            expected_case_ids=expected_case_ids,
        )
    )
    errors.extend(
        validate_comparison_summary(
            entry,
            config_root=config_root,
            prefix=prefix,
            require_artifacts=require_artifacts,
            expected_case_ids=expected_case_ids,
        )
    )
    errors.extend(validate_repair_status(entry, prefix=prefix))
    return errors


def validate_baseline_corpus(
    corpus: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool = False,
) -> list[str]:
    errors: list[str] = []
    if corpus.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if corpus.get("kind") != "priority0_baseline_corpus":
        errors.append("kind must be priority0_baseline_corpus")
    policy = corpus.get("governance_policy") if isinstance(corpus.get("governance_policy"), dict) else {}
    if policy.get("baseline_collection_order") != EXPECTED_BASELINE_COLLECTION_ORDER:
        errors.append(f"governance_policy.baseline_collection_order must be {EXPECTED_BASELINE_COLLECTION_ORDER}")
    if set(string_list(policy.get("required_routes"))) != REQUIRED_ROUTES:
        errors.append("governance_policy.required_routes must be gateway and anythingllm")
    if set(string_list(policy.get("required_target_roots"))) != REQUIRED_COINBASE_TARGETS:
        errors.append("governance_policy.required_target_roots must be both frozen Coinbase fixtures")
    if policy.get("minimum_score") != MINIMUM_SCORE:
        errors.append(f"governance_policy.minimum_score must be {MINIMUM_SCORE}")
    if policy.get("critical_findings_allowed") != 0 or policy.get("high_findings_allowed") != 0:
        errors.append("governance_policy critical/high findings allowed must be 0")
    if policy.get("repair_rerun_required") is not True:
        errors.append("governance_policy.repair_rerun_required must be true")
    if policy.get("source_mutation_allowed") is not False:
        errors.append("governance_policy.source_mutation_allowed must be false")
    if policy.get("stale_source_hashes_allowed") is not False:
        errors.append("governance_policy.stale_source_hashes_allowed must be false")
    entries = object_list(corpus.get("entries"))
    if not entries:
        errors.append("entries must contain at least one governed baseline record")
        return errors
    entry_ids = [str(item.get("entry_id")) for item in entries if isinstance(item.get("entry_id"), str)]
    if len(entry_ids) != len(set(entry_ids)):
        errors.append("entries contain duplicate entry_id values")
    phases = [item.get("phase") for item in entries]
    if len(phases) != len(set(phases)):
        errors.append("entries contain duplicate phase values")
    if set(phases) != EXPECTED_PHASES:
        errors.append("entries must exactly cover phases 116, 117, 118, and 119")
    backlog_ids = [str(item.get("priority_backlog_id")) for item in entries if isinstance(item.get("priority_backlog_id"), str)]
    if len(backlog_ids) != len(set(backlog_ids)):
        errors.append("entries contain duplicate priority_backlog_id values")
    if set(backlog_ids) != EXPECTED_BACKLOG_IDS:
        errors.append("entries must exactly cover P0-BB-001 through P0-BB-004")
    for index, entry in enumerate(entries):
        errors.extend(validate_corpus_entry(entry, index, config_root=config_root, require_artifacts=require_artifacts))
    return errors


def run_baseline_corpus_governance(config: BaselineCorpusConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    corpus_path = resolve_path(config_root, config.corpus_path)
    corpus = read_json_object(corpus_path)
    errors = validate_baseline_corpus(corpus, config_root=config_root, require_artifacts=config.require_artifacts)
    entries = object_list(corpus.get("entries"))
    summary = {
        "entry_count": len(entries),
        "stable_entry_count": sum(1 for entry in entries if entry.get("status") == CorpusEntryStatus.STABLE.value),
        "error_count": len(errors),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "baseline_corpus_governance_report",
        "status": "passed" if not errors else "failed",
        "corpus_path": str(corpus_path),
        "require_artifacts": config.require_artifacts,
        "summary": summary,
        "errors": errors,
        "entries": [
            {
                "entry_id": entry.get("entry_id"),
                "phase": entry.get("phase"),
                "priority_backlog_id": entry.get("priority_backlog_id"),
                "status": entry.get("status"),
                "comparison_status": (entry.get("comparison") if isinstance(entry.get("comparison"), dict) else {}).get("status"),
            }
            for entry in entries
        ],
    }
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
