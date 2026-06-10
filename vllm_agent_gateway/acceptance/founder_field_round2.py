"""Phase 164 founder field-test round 2 governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "founder_field_round2_policy"
EXPECTED_BASELINE_KIND = "founder_field_round2_blind_baselines"
EXPECTED_REPORT_KIND = "founder_field_round2_report"
EXPECTED_FIELD_SOURCE_KIND = "founder_field_prompt_evaluation"
EXPECTED_READINESS_KIND = "post_restart_runtime_readiness_report"
EXPECTED_FEEDBACK_KIND = "transcript_quality_feedback_intake_report"
EXPECTED_PHASE = 164
EXPECTED_BACKLOG_ID = "P0-BB-028"
DEFAULT_POLICY_PATH = Path("runtime") / "founder_field_round2_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "founder-field-round2" / "phase164"
DEFAULT_BASELINE_PATH = DEFAULT_OUTPUT_DIR / "phase164-founder-field-round2-blind-baselines.json"
DEFAULT_FIELD_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase164-founder-field-round2-run.json"
DEFAULT_FIELD_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase164-founder-field-round2-run.md"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase164-founder-field-round2-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase164-founder-field-round2-report.md"
LOCAL_OUTPUT_KEYS = {
    "_full_text",
    "body",
    "http_status",
    "initial_difference",
    "missing_markers",
    "missing_semantic_markers",
    "output_contract_status",
    "response_artifact_bytes",
    "response_artifact_path",
    "response_artifact_sha256",
    "route_surface",
    "run_id",
    "semantic_quality_status",
    "status",
    "suggested_prompt_if_missed",
    "text_sample",
    "text_sha256",
}


class FounderFieldRound2Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FounderFieldRound2QualityStatus(str, Enum):
    PASSED = "passed"
    ADVISORY = "advisory"
    FAILED = "failed"


@dataclass(frozen=True)
class FounderFieldRound2Config:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    baseline_path: Path = DEFAULT_BASELINE_PATH
    field_report_path: Path = DEFAULT_FIELD_REPORT_PATH
    output_path: Path = DEFAULT_REPORT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def prompt_sha256(prompt: object) -> str:
    return sha256_text(str(prompt or ""))


def parse_utc_sortable(value: object) -> str:
    return str(value or "")


def marker_count_score(text: str, markers: list[str], total_points: int) -> int:
    if not markers:
        return 0
    present = sum(1 for marker in markers if marker in text)
    return round(total_points * present / len(markers))


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 164")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("existing_runner_script") != "scripts/run_founder_field_prompt_eval.py":
        errors.append("policy.existing_runner_script must use the existing founder field runner")
    if policy.get("blind_baseline_source_path") != "runtime/founder_field_round2_blind_baselines.json":
        errors.append("policy.blind_baseline_source_path must point to the governed blind baseline source")
    case_ids = string_list(policy.get("required_case_ids"))
    advisory_ids = string_list(policy.get("required_advisory_case_ids"))
    control_ids = string_list(policy.get("required_control_case_ids"))
    if len(case_ids) != len(set(case_ids)):
        errors.append("policy.required_case_ids must be unique")
    min_case_count = policy.get("min_case_count")
    max_case_count = policy.get("max_case_count")
    if not isinstance(min_case_count, int) or min_case_count < 1:
        errors.append("policy.min_case_count must be a positive integer")
    if not isinstance(max_case_count, int) or max_case_count < len(case_ids):
        errors.append("policy.max_case_count must cover required_case_ids")
    if isinstance(min_case_count, int) and len(case_ids) < min_case_count:
        errors.append("policy.required_case_ids must meet min_case_count")
    if isinstance(max_case_count, int) and len(case_ids) > max_case_count:
        errors.append("policy.required_case_ids must not exceed max_case_count")
    if not set(advisory_ids).issubset(set(case_ids)):
        errors.append("policy.required_advisory_case_ids must be a subset of required_case_ids")
    if not set(control_ids).issubset(set(case_ids)):
        errors.append("policy.required_control_case_ids must be a subset of required_case_ids")
    if not advisory_ids:
        errors.append("policy.required_advisory_case_ids must be non-empty")
    if not control_ids:
        errors.append("policy.required_control_case_ids must be non-empty")
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append("policy.required_target_roots must include both frozen Coinbase fixtures")
    if set(string_list(policy.get("allowed_quality_classifications"))) != {"pass", "advisory", "blocker", "proposal_candidate"}:
        errors.append("policy.allowed_quality_classifications must be pass, advisory, blocker, and proposal_candidate")
    if string_list(policy.get("required_route_surfaces")) != ["anythingllm_via_workflow_router_gateway"]:
        errors.append("policy.required_route_surfaces must require AnythingLLM via workflow-router gateway")
    if not isinstance(policy.get("minimum_score"), int) or int(policy.get("minimum_score")) < 1:
        errors.append("policy.minimum_score must be a positive integer")
    if policy.get("acceptance_marker") != "PHASE164 FOUNDER FIELD ROUND 2 PASS":
        errors.append("policy.acceptance_marker must be PHASE164 FOUNDER FIELD ROUND 2 PASS")
    return errors


def validate_scoring_rubric(value: object) -> list[str]:
    rubric = dict_value(value)
    required = {
        "routing": 20,
        "answer_completeness": 30,
        "evidence": 20,
        "safety_boundary": 15,
        "output_contract": 15,
    }
    problems: list[str] = []
    if set(rubric) != set(required):
        problems.append("rubric keys must be routing, answer_completeness, evidence, safety_boundary, output_contract")
    for key, expected in required.items():
        if rubric.get(key) != expected:
            problems.append(f"rubric.{key} must be {expected}")
    if sum(value for value in rubric.values() if isinstance(value, int)) != 100:
        problems.append("rubric total must be 100")
    return problems


def materialize_blind_baseline_package(*, policy: dict[str, Any], baseline_package: dict[str, Any]) -> dict[str, Any]:
    """Return a mechanically hashed copy of the blind package without adding answer content."""

    required_case_ids = string_list(policy.get("required_case_ids"))
    records = object_list(baseline_package.get("cases"))
    materialized = json.loads(json.dumps(baseline_package, ensure_ascii=True))
    for record in object_list(materialized.get("cases")):
        if str(record.get("case_id")) in required_case_ids:
            record["prompt_sha256"] = prompt_sha256(record.get("prompt"))
    materialized.setdefault("summary", {})
    materialized["summary"]["case_count"] = len(records)
    materialized["summary"]["target_roots"] = sorted(
        {str(record.get("target_root")) for record in records if isinstance(record.get("target_root"), str)}
    )
    materialized["summary"]["scoring_rubric_total"] = 100
    return materialized


def validate_baseline_package(
    *,
    policy: dict[str, Any],
    baseline_package: dict[str, Any],
    field_report: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if baseline_package.get("schema_version") != SCHEMA_VERSION:
        errors.append({"id": "baseline.schema_version", "severity": "high", "message": "baseline schema_version must be 1"})
    if baseline_package.get("kind") != EXPECTED_BASELINE_KIND:
        errors.append({"id": "baseline.kind", "severity": "high", "message": f"baseline kind must be {EXPECTED_BASELINE_KIND}"})
    if baseline_package.get("phase") != EXPECTED_PHASE:
        errors.append({"id": "baseline.phase", "severity": "high", "message": "baseline phase must be 164"})
    if baseline_package.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append({"id": "baseline.priority_backlog_id", "severity": "high", "message": f"baseline priority_backlog_id must be {EXPECTED_BACKLOG_ID}"})
    if baseline_package.get("local_model_output_seen_by_blind_agent") is not False:
        errors.append({"id": "baseline.local_output_seen", "severity": "high", "message": "blind baseline must assert local_model_output_seen_by_blind_agent=false"})
    if str(baseline_package.get("baseline_source") or "").startswith("runtime/prompt_catalogs/"):
        errors.append({"id": "baseline.source", "severity": "high", "message": "blind baseline must not be generated from the prompt catalog alone"})

    required_case_ids = string_list(policy.get("required_case_ids"))
    records = object_list(baseline_package.get("cases"))
    record_ids = [str(record.get("case_id")) for record in records]
    if set(record_ids) != set(required_case_ids):
        errors.append({"id": "baseline.case_ids", "severity": "high", "message": "baseline case IDs must match policy"})
    if len(record_ids) != len(set(record_ids)):
        errors.append({"id": "baseline.duplicate_case_ids", "severity": "high", "message": "baseline case IDs must be unique"})
    required_fields = set(string_list(policy.get("required_blind_baseline_fields")))
    for index, record in enumerate(records):
        prefix = f"baseline.cases[{index}]"
        missing_fields = sorted(field for field in required_fields if not record.get(field))
        if missing_fields:
            errors.append(
                {
                    "id": f"{prefix}.missing_required_fields",
                    "severity": "high",
                    "message": "baseline missing required fields: " + ", ".join(missing_fields),
                }
            )
        leaked = sorted(key for key in LOCAL_OUTPUT_KEYS if key in record)
        if leaked:
            errors.append(
                {
                    "id": f"{prefix}.local_output_leak",
                    "severity": "high",
                    "message": "blind baseline must not include local output fields: " + ", ".join(leaked),
                }
            )
        if record.get("prompt_sha256") != prompt_sha256(record.get("prompt")):
            errors.append({"id": f"{prefix}.prompt_hash", "severity": "high", "message": "baseline prompt hash mismatch"})
        for key in ("must_have_facts", "must_have_markers", "forbidden_markers", "evidence_expectations", "safety_boundaries", "output_expectations"):
            if not string_list(record.get(key)):
                errors.append({"id": f"{prefix}.{key}", "severity": "high", "message": f"baseline {key} must be a non-empty string list"})
        if not isinstance(record.get("ideal_answer_shape"), str) or not str(record.get("ideal_answer_shape")).strip():
            errors.append({"id": f"{prefix}.ideal_answer_shape", "severity": "high", "message": "baseline ideal_answer_shape must be a non-empty string"})
        for problem in validate_scoring_rubric(record.get("scoring_rubric")):
            errors.append({"id": f"{prefix}.scoring_rubric", "severity": "high", "message": problem})
    if field_report is not None:
        baseline_at = parse_utc_sortable(baseline_package.get("generated_at"))
        field_at = parse_utc_sortable(field_report.get("created_at"))
        if baseline_at and field_at and baseline_at > field_at:
            errors.append(
                {
                    "id": "baseline.generated_after_field_run",
                    "severity": "high",
                    "message": "blind baseline must be generated before the field run",
                }
            )
    return errors


def response_artifact_text(config_root: Path, case: dict[str, Any]) -> str:
    path = resolve_path(config_root, str(case.get("response_artifact_path") or ""))
    return path.read_text(encoding="utf-8")


def response_artifact_validation_errors(config_root: Path, case: dict[str, Any], prefix: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    raw_path = case.get("response_artifact_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return [{"id": f"{prefix}.response_artifact_path", "severity": "high", "message": "field case must include full response_artifact_path"}]
    path = resolve_path(config_root, raw_path)
    if not path.is_file():
        return [{"id": f"{prefix}.response_artifact_missing", "severity": "high", "message": "field response artifact must exist"}]
    actual_hash = sha256_file(path)
    if case.get("response_artifact_sha256") != actual_hash:
        errors.append({"id": f"{prefix}.response_artifact_hash", "severity": "high", "message": "field response artifact hash mismatch"})
    if case.get("text_sha256") != actual_hash:
        errors.append({"id": f"{prefix}.text_hash", "severity": "high", "message": "field text_sha256 must match full response artifact hash"})
    text = path.read_text(encoding="utf-8")
    if not isinstance(case.get("text_sample"), str) or not text.startswith(str(case.get("text_sample"))):
        errors.append({"id": f"{prefix}.text_sample", "severity": "high", "message": "field text_sample must be a prefix of the full response artifact"})
    if not isinstance(case.get("response_artifact_bytes"), int) or int(case.get("response_artifact_bytes")) != path.stat().st_size:
        errors.append({"id": f"{prefix}.response_artifact_bytes", "severity": "high", "message": "field response_artifact_bytes must match file size"})
    return errors


def evidence_score(text: str, total_points: int) -> int:
    evidence_markers = [
        "Artifacts:",
        "Evidence",
        "Evidence files:",
        "Related tests:",
        "Recommended commands:",
        "Source refs:",
        "Verification:",
    ]
    return min(total_points, marker_count_score(text, evidence_markers, total_points))


def score_breakdown(config_root: Path, case: dict[str, Any], baseline: dict[str, Any]) -> dict[str, int]:
    try:
        text = response_artifact_text(config_root, case)
    except OSError:
        text = str(case.get("text_sample") or "")
    rubric = dict_value(baseline.get("scoring_rubric"))
    routing = 0
    if isinstance(case.get("run_id"), str) and str(case.get("run_id")).startswith("workflow-router-"):
        routing += 8
    if str(case.get("expected_workflow")) == str(baseline.get("expected_workflow")) and f"selected_workflow: {case.get('expected_workflow')}" in text:
        routing += 7
    if case.get("route_surface") == "anythingllm_via_workflow_router_gateway":
        routing += 5
    completeness = marker_count_score(text, string_list(baseline.get("must_have_markers")), int(rubric.get("answer_completeness") or 30))
    safety = int(rubric.get("safety_boundary") or 15)
    for marker in string_list(baseline.get("forbidden_markers")):
        if marker in text:
            safety = 0
            break
    output_contract = int(rubric.get("output_contract") or 15) if case.get("output_contract_status") == "passed" else 0
    return {
        "routing": min(routing, int(rubric.get("routing") or 20)),
        "answer_completeness": completeness,
        "evidence": evidence_score(text, int(rubric.get("evidence") or 20)),
        "safety_boundary": safety,
        "output_contract": output_contract,
    }


def case_score(config_root: Path, case: dict[str, Any], baseline: dict[str, Any]) -> int:
    return sum(score_breakdown(config_root, case, baseline).values())


def quality_classification(
    config_root: Path,
    case: dict[str, Any],
    baseline: dict[str, Any],
    *,
    advisory_case_ids: set[str],
    minimum_score: int,
) -> str:
    score = case_score(config_root, case, baseline)
    if score < minimum_score or case.get("status") != "passed":
        return "blocker"
    if str(case.get("case_id")) in advisory_case_ids or str(case.get("prompt_risk") or "").strip():
        return "advisory"
    return "pass"


def case_evidence(
    config_root: Path,
    case: dict[str, Any],
    baseline: dict[str, Any],
    *,
    advisory_case_ids: set[str],
    minimum_score: int,
) -> dict[str, Any]:
    breakdown = score_breakdown(config_root, case, baseline)
    score = sum(breakdown.values())
    classification = quality_classification(
        config_root,
        case,
        baseline,
        advisory_case_ids=advisory_case_ids,
        minimum_score=minimum_score,
    )
    return {
        "case_id": case.get("case_id"),
        "target_root": case.get("target_root"),
        "prompt_sha256": prompt_sha256(case.get("prompt")),
        "baseline_prompt_sha256": baseline.get("prompt_sha256"),
        "expected_workflow": case.get("expected_workflow"),
        "expected_skill_id": case.get("expected_skill_id") or "",
        "expected_artifact_key": case.get("expected_artifact_key") or "",
        "status": case.get("status"),
        "score": score,
        "score_breakdown": breakdown,
        "quality_classification": classification,
        "output_contract_status": case.get("output_contract_status"),
        "semantic_quality_status": case.get("semantic_quality_status"),
        "route_surface": case.get("route_surface"),
        "run_id": case.get("run_id"),
        "text_sha256": case.get("text_sha256"),
        "response_artifact_path": case.get("response_artifact_path"),
        "response_artifact_sha256": case.get("response_artifact_sha256"),
        "blind_baseline_comparison": {
            "ideal_answer_shape": baseline.get("ideal_answer_shape"),
            "must_have_facts": baseline.get("must_have_facts"),
            "must_have_markers": baseline.get("must_have_markers"),
            "evidence_expectations": baseline.get("evidence_expectations"),
            "safety_boundaries": baseline.get("safety_boundaries"),
            "output_expectations": baseline.get("output_expectations"),
        },
        "initial_difference": case.get("initial_difference"),
        "suggested_prompt_if_missed": case.get("suggested_prompt_if_missed") or "",
        "refined_prompt": case.get("refined_prompt") or "",
        "prompt_risk": case.get("prompt_risk") or "",
    }


def validation_errors_for_sources(
    *,
    config_root: Path,
    policy: dict[str, Any],
    baseline_package: dict[str, Any],
    field_report: dict[str, Any],
    readiness_report: dict[str, Any],
    phase158_report: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    errors.extend({"id": f"policy.{index}", "severity": "high", "message": error} for index, error in enumerate(validate_policy(policy)))
    errors.extend(validate_baseline_package(policy=policy, baseline_package=baseline_package, field_report=field_report))
    if readiness_report.get("kind") != EXPECTED_READINESS_KIND:
        errors.append({"id": "readiness.kind", "severity": "high", "message": f"readiness kind must be {EXPECTED_READINESS_KIND}"})
    if readiness_report.get("status") != "passed" or readiness_report.get("decision") != "ready_after_restart":
        errors.append({"id": "readiness.status", "severity": "high", "message": "Phase 163 readiness must pass before field round 2"})
    if phase158_report.get("kind") != EXPECTED_FEEDBACK_KIND:
        errors.append({"id": "phase158.kind", "severity": "high", "message": f"Phase 158 report kind must be {EXPECTED_FEEDBACK_KIND}"})
    if phase158_report.get("status") != "passed":
        errors.append({"id": "phase158.status", "severity": "high", "message": "Phase 158 feedback intake must pass"})
    accepted = object_list(phase158_report.get("accepted_findings"))
    phase158_advisory_ids = {
        str(item.get("case_id"))
        for item in accepted
        if item.get("category") == "prompt_issue" and item.get("owner_path") == "prompt_catalog_review"
    }
    required_advisory_ids = set(string_list(policy.get("required_advisory_case_ids")))
    missing_advisories = sorted(required_advisory_ids - phase158_advisory_ids)
    if missing_advisories:
        errors.append({"id": "phase158.advisory_case_ids", "severity": "high", "message": "Phase 158 missing advisory cases: " + ", ".join(missing_advisories)})
    if field_report.get("kind") != EXPECTED_FIELD_SOURCE_KIND:
        errors.append({"id": "field.kind", "severity": "high", "message": f"field report kind must be {EXPECTED_FIELD_SOURCE_KIND}"})
    if dict_value(field_report.get("anythingllm_preflight")).get("status") != "passed":
        errors.append({"id": "field.anythingllm_preflight", "severity": "high", "message": "AnythingLLM preflight must pass"})
    if object_list(field_report.get("errors")) or string_list(field_report.get("errors")):
        errors.append({"id": "field.errors", "severity": "high", "message": "field report errors must be empty"})
    if field_report.get("fixture_state_before") != field_report.get("fixture_state_after"):
        errors.append({"id": "field.fixture_state_changed", "severity": "critical", "message": "field round changed protected fixture state"})
    cases = object_list(field_report.get("cases"))
    case_ids = [str(case.get("case_id")) for case in cases]
    required_case_ids = string_list(policy.get("required_case_ids"))
    if set(case_ids) != set(required_case_ids):
        errors.append({"id": "field.case_ids", "severity": "high", "message": "field case IDs must match policy"})
    target_roots = {str(case.get("target_root")) for case in cases if isinstance(case.get("target_root"), str)}
    if target_roots != set(string_list(policy.get("required_target_roots"))):
        errors.append({"id": "field.target_roots", "severity": "high", "message": "field report must cover both frozen Coinbase fixtures and no other roots"})
    required_route_surfaces = set(string_list(policy.get("required_route_surfaces")))
    baseline_by_id = {str(record.get("case_id")): record for record in object_list(baseline_package.get("cases"))}
    for index, case in enumerate(cases):
        prefix = f"field.cases[{index}]"
        case_id = str(case.get("case_id"))
        baseline = baseline_by_id.get(case_id)
        if not baseline:
            errors.append({"id": f"{prefix}.missing_baseline", "severity": "high", "message": "field case missing blind baseline"})
            continue
        if prompt_sha256(case.get("prompt")) != baseline.get("prompt_sha256"):
            errors.append({"id": f"{prefix}.prompt_hash", "severity": "high", "message": "field prompt hash must match blind baseline"})
        if not isinstance(case.get("run_id"), str) or not str(case.get("run_id")).startswith("workflow-router-"):
            errors.append({"id": f"{prefix}.run_id", "severity": "high", "message": "field case must include workflow-router run_id"})
        if case.get("route_surface") not in required_route_surfaces:
            errors.append({"id": f"{prefix}.route_surface", "severity": "high", "message": "field case must prove AnythingLLM via workflow-router gateway"})
        errors.extend(response_artifact_validation_errors(config_root, case, prefix))
    return errors


def build_founder_field_round2_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    baseline_package: dict[str, Any],
    field_report: dict[str, Any],
    readiness_report: dict[str, Any],
    phase158_report: dict[str, Any],
    policy_path: Path | None = None,
    baseline_path: Path | None = None,
    field_report_path: Path | None = None,
    readiness_report_path: Path | None = None,
    phase158_report_path: Path | None = None,
) -> dict[str, Any]:
    errors = validation_errors_for_sources(
        config_root=config_root,
        policy=policy,
        baseline_package=baseline_package,
        field_report=field_report,
        readiness_report=readiness_report,
        phase158_report=phase158_report,
    )
    advisory_ids = set(string_list(policy.get("required_advisory_case_ids")))
    minimum_score = int(policy.get("minimum_score") or 85)
    baselines = {str(record.get("case_id")): record for record in object_list(baseline_package.get("cases"))}
    cases = [
        case_evidence(config_root, case, baselines.get(str(case.get("case_id")), {}), advisory_case_ids=advisory_ids, minimum_score=minimum_score)
        for case in object_list(field_report.get("cases"))
    ]
    classification_counts = {
        "pass": sum(1 for item in cases if item.get("quality_classification") == "pass"),
        "advisory": sum(1 for item in cases if item.get("quality_classification") == "advisory"),
        "blocker": sum(1 for item in cases if item.get("quality_classification") == "blocker"),
        "proposal_candidate": sum(1 for item in cases if item.get("quality_classification") == "proposal_candidate"),
    }
    if classification_counts["blocker"]:
        quality_status = FounderFieldRound2QualityStatus.FAILED.value
    elif classification_counts["advisory"] or classification_counts["proposal_candidate"]:
        quality_status = FounderFieldRound2QualityStatus.ADVISORY.value
    else:
        quality_status = FounderFieldRound2QualityStatus.PASSED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderFieldRound2Status.FAILED.value if errors else FounderFieldRound2Status.PASSED.value,
        "quality_status": quality_status,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "baseline_path": str(baseline_path.resolve()) if baseline_path else None,
        "baseline_sha256": artifact_hash(baseline_path),
        "field_report_path": str(field_report_path.resolve()) if field_report_path else None,
        "field_report_sha256": artifact_hash(field_report_path),
        "readiness_report_path": str(readiness_report_path.resolve()) if readiness_report_path else None,
        "readiness_report_sha256": artifact_hash(readiness_report_path),
        "phase158_report_path": str(phase158_report_path.resolve()) if phase158_report_path else None,
        "phase158_report_sha256": artifact_hash(phase158_report_path),
        "case_evidence": cases,
        "summary": {
            "case_count": len(cases),
            "target_roots": sorted({str(item.get("target_root")) for item in cases if item.get("target_root")}),
            "classification_counts": classification_counts,
            "min_score": min((int(item.get("score") or 0) for item in cases), default=0),
            "average_score": round(sum(int(item.get("score") or 0) for item in cases) / len(cases), 2) if cases else 0,
            "phase165_required": classification_counts["advisory"] > 0,
            "phase169_required": classification_counts["blocker"] > 0 or classification_counts["proposal_candidate"] > 0,
            "validation_error_count": len(errors),
            "next_action": "begin Phase 165 prompt-advisory closure"
            if not classification_counts["blocker"]
            else "route blockers through Phase 169 proposal pass",
        },
        "validation_errors": errors,
    }


def validate_founder_field_round2_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    baseline_package: dict[str, Any],
    field_report: dict[str, Any],
    readiness_report: dict[str, Any],
    phase158_report: dict[str, Any],
    policy_path: Path | None = None,
    baseline_path: Path | None = None,
    field_report_path: Path | None = None,
    readiness_report_path: Path | None = None,
    phase158_report_path: Path | None = None,
) -> list[str]:
    expected = build_founder_field_round2_report(
        config_root=config_root,
        policy=policy,
        baseline_package=baseline_package,
        field_report=field_report,
        readiness_report=readiness_report,
        phase158_report=phase158_report,
        policy_path=policy_path,
        baseline_path=baseline_path,
        field_report_path=field_report_path,
        readiness_report_path=readiness_report_path,
        phase158_report_path=phase158_report_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "quality_status",
        "policy_path",
        "policy_sha256",
        "baseline_path",
        "baseline_sha256",
        "field_report_path",
        "field_report_sha256",
        "readiness_report_path",
        "readiness_report_sha256",
        "phase158_report_path",
        "phase158_report_sha256",
        "case_evidence",
        "summary",
        "validation_errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append("report must match rebuilt founder field round 2 report")
            break
    return errors


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Founder Field Round 2",
        "",
        f"- Status: {report['status']}",
        f"- Quality status: {report['quality_status']}",
        f"- Case count: {report['summary']['case_count']}",
        f"- Classification counts: {report['summary']['classification_counts']}",
        f"- Minimum score: {report['summary']['min_score']}",
        f"- Average score: {report['summary']['average_score']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Cases",
        "",
        "| Case | Classification | Score | Workflow | Route | Run ID | Response Artifact | Difference |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for item in report["case_evidence"]:
        difference = str(item.get("initial_difference", "")).replace("\n", " ")
        lines.append(
            f"| {item.get('case_id')} | {item.get('quality_classification')} | {item.get('score')} | "
            f"{item.get('expected_workflow')} | {item.get('route_surface')} | {item.get('run_id')} | "
            f"{item.get('response_artifact_path')} | {difference[:300]} |"
        )
    if report["validation_errors"]:
        lines.extend(["", "## Validation Errors", ""])
        for error in report["validation_errors"]:
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_founder_field_round2(config: FounderFieldRound2Config) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    baseline_path = resolve_path(config_root, config.baseline_path)
    field_report_path = resolve_path(config_root, config.field_report_path)
    policy = read_json_object(policy_path)
    baseline_package = read_json_object(baseline_path)
    field_report = read_json_object(field_report_path)
    readiness_report_path = resolve_path(config_root, str(policy.get("post_restart_readiness_report_path") or ""))
    phase158_report_path = resolve_path(config_root, str(policy.get("phase158_feedback_report_path") or ""))
    readiness_report = read_json_object(readiness_report_path)
    phase158_report = read_json_object(phase158_report_path)
    report = build_founder_field_round2_report(
        config_root=config_root,
        policy=policy,
        baseline_package=baseline_package,
        field_report=field_report,
        readiness_report=readiness_report,
        phase158_report=phase158_report,
        policy_path=policy_path,
        baseline_path=baseline_path,
        field_report_path=field_report_path,
        readiness_report_path=readiness_report_path,
        phase158_report_path=phase158_report_path,
    )
    validation_errors = validate_founder_field_round2_report(
        report,
        config_root=config_root,
        policy=policy,
        baseline_package=baseline_package,
        field_report=field_report,
        readiness_report=readiness_report,
        phase158_report=phase158_report,
        policy_path=policy_path,
        baseline_path=baseline_path,
        field_report_path=field_report_path,
        readiness_report_path=readiness_report_path,
        phase158_report_path=phase158_report_path,
    )
    if validation_errors:
        report["status"] = FounderFieldRound2Status.FAILED.value
        report["validation_errors"] = list(report.get("validation_errors") or []) + [
            {"id": f"report.{index}", "severity": "high", "message": error} for index, error in enumerate(validation_errors)
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
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
