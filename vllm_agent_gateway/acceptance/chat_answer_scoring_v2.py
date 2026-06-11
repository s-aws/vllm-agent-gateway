"""Phase 192 chat-answer scoring automation V2."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chat_answer_scoring_v2_policy"
EXPECTED_REPORT_KIND = "chat_answer_scoring_v2_report"
EXPECTED_PHASE = 192
EXPECTED_BACKLOG_ID = "P0-BB-056"
DEFAULT_POLICY_PATH = Path("runtime") / "chat_answer_scoring_v2_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase192" / "phase192-chat-answer-scoring-v2-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase192" / "phase192-chat-answer-scoring-v2-report.md"
DIMENSIONS = (
    "routing",
    "evidence_relevance",
    "correctness",
    "answer_completeness",
    "source_refs",
    "format_adherence",
    "safety_boundaries",
    "user_visible_usefulness",
)
BLOCKING_DIMENSIONS = (
    "routing",
    "correctness",
    "answer_completeness",
    "source_refs",
    "format_adherence",
    "safety_boundaries",
    "user_visible_usefulness",
)
REPAIR_TARGETS = (
    "none",
    "router",
    "evidence_relevance",
    "correctness",
    "answer_completeness",
    "source_refs",
    "format_contract",
    "safety_boundary",
    "user_visible_usefulness",
    "prompt_wording",
    "prompt_governance",
)
CLASSIFICATIONS = ("pass", "advisory", "fail")
SOURCE_REF_RE = re.compile(r"\b[\w./-]+\.(?:py|md|json|yaml|yml|toml|js|ts|tsx|jsx|go|rs|java|sh)(?::\d+)?\b")
SOURCE_MUTATION_MARKERS = (
    "source mutation: true",
    "source_changed: true",
    "disposable_copy_changed: true",
)


class ChatAnswerScoringV2Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ChatAnswerScoringV2Config:
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
        "blind_baseline_delta_report": str(policy.get("source_blind_baseline_delta_report_path") or ""),
        "founder_round2_report": str(policy.get("source_founder_round2_report_path") or ""),
        "drift_detection_report": str(policy.get("source_drift_detection_report_path") or ""),
    }


def source_paths(config_root: Path, policy: dict[str, Any]) -> dict[str, Path]:
    return {key: resolve_path(config_root, value) for key, value in source_path_config(policy).items()}


def source_artifacts(sources: dict[str, dict[str, Any]], paths: dict[str, Path]) -> list[dict[str, Any]]:
    return [
        {
            "source_key": key,
            "path": str(paths[key].resolve()),
            "sha256": artifact_hash(paths[key]),
            "kind": sources.get(key, {}).get("kind"),
            "status": sources.get(key, {}).get("status"),
        }
        for key in sorted(paths)
    ]


def validation_error(error_id: str, message: str, severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 192"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("acceptance_marker") != "PHASE192 CHAT ANSWER SCORING V2 PASS":
        errors.append(validation_error("policy.acceptance_marker", "policy.acceptance_marker must match Phase 192"))
    for key, value in source_path_config(policy).items():
        if not value:
            errors.append(validation_error(f"policy.source_path.{key}", f"{key} source path is required"))
    contract = dict_value(policy.get("classification_contract"))
    if string_list(contract.get("required_dimensions")) != list(DIMENSIONS):
        errors.append(validation_error("classification_contract.required_dimensions", "required dimensions must match the Phase 192 contract"))
    if string_list(contract.get("blocking_dimensions")) != list(BLOCKING_DIMENSIONS):
        errors.append(validation_error("classification_contract.blocking_dimensions", "blocking dimensions must match the Phase 192 contract"))
    if string_list(contract.get("allowed_repair_targets")) != list(REPAIR_TARGETS):
        errors.append(validation_error("classification_contract.allowed_repair_targets", "repair targets must match the Phase 192 contract"))
    if string_list(contract.get("allowed_classifications")) != list(CLASSIFICATIONS):
        errors.append(validation_error("classification_contract.allowed_classifications", "classifications must be pass, advisory, fail"))
    weights = dict_value(contract.get("score_weights"))
    if set(weights) != set(DIMENSIONS):
        errors.append(validation_error("classification_contract.score_weights", "score weights must cover every required dimension"))
    if sum(value for value in weights.values() if isinstance(value, int)) != 100:
        errors.append(validation_error("classification_contract.score_weights", "score weights must total 100"))
    if int(policy.get("minimum_case_score") or 0) < 1:
        errors.append(validation_error("policy.minimum_case_score", "minimum_case_score must be positive"))
    if int(policy.get("minimum_report_score") or 0) < 1:
        errors.append(validation_error("policy.minimum_report_score", "minimum_report_score must be positive"))
    example_classifications = {str(item.get("expected_classification") or "") for item in object_list(policy.get("scoring_examples"))}
    if example_classifications != set(CLASSIFICATIONS):
        errors.append(validation_error("scoring_examples.classifications", "scoring examples must include pass, advisory, and fail"))
    for index, example in enumerate(object_list(policy.get("scoring_examples"))):
        prefix = f"scoring_examples[{index}]"
        if str(example.get("expected_classification") or "") not in CLASSIFICATIONS:
            errors.append(validation_error(f"{prefix}.expected_classification", "expected_classification is unsupported"))
        for target in string_list(example.get("expected_repair_targets")):
            if target not in REPAIR_TARGETS:
                errors.append(validation_error(f"{prefix}.expected_repair_targets", f"unsupported repair target {target}"))
        if not str(example.get("response_text") or "").strip():
            errors.append(validation_error(f"{prefix}.response_text", "response_text is required"))
        if not dict_value(example.get("source_case")):
            errors.append(validation_error(f"{prefix}.source_case", "source_case is required"))
    return errors


def validate_sources(policy: dict[str, Any], sources: dict[str, dict[str, Any]], paths: dict[str, Path]) -> list[dict[str, str]]:
    errors = validate_policy(policy)
    source_kinds = dict_value(policy.get("source_kinds"))
    for key, path in paths.items():
        if not path.is_file():
            errors.append(validation_error(f"sources.{key}.missing", f"source file is missing: {path}"))
            continue
        expected_kind = str(source_kinds.get(key) or "")
        if expected_kind and sources.get(key, {}).get("kind") != expected_kind:
            errors.append(validation_error(f"sources.{key}.kind", f"{key} kind must be {expected_kind}"))
        if sources.get(key, {}).get("status") != "passed":
            errors.append(validation_error(f"sources.{key}.status", f"{key} source report must be passed"))
    delta_report = sources.get("blind_baseline_delta_report", {})
    drift_report = sources.get("drift_detection_report", {})
    if int(policy.get("expected_delta_count") or 0) != len(object_list(delta_report.get("deltas"))):
        errors.append(validation_error("delta.expected_count", "expected_delta_count must match the blind-baseline delta report"))
    if dict_value(drift_report.get("summary")).get("active_catalog_blocking_drift_count") != policy.get("expected_drift_active_catalog_blocking_drift_count"):
        errors.append(validation_error("drift.active_catalog_blocking_drift_count", "active catalog drift must match policy"))
    return errors


def response_text(config_root: Path, case: dict[str, Any], explicit_text: str | None = None) -> str:
    if explicit_text is not None:
        return explicit_text
    path_value = case.get("local_answer_path") or case.get("response_artifact_path")
    if not isinstance(path_value, str) or not path_value.strip():
        return ""
    path = resolve_path(config_root, path_value)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def source_refs_status(text: str) -> dict[str, Any]:
    refs = sorted(set(match.group(0) for match in SOURCE_REF_RE.finditer(text)))
    marker_present = any(marker in text for marker in ("Source refs:", "Evidence files:", "Related tests:", "Artifacts:", "Evidence:"))
    status = "passed" if refs and marker_present else "failed"
    return {"status": status, "refs": refs[:20], "ref_count": len(refs), "marker_present": marker_present}


def safety_status(case: dict[str, Any], text: str) -> dict[str, Any]:
    score = int(dict_value(case.get("score_breakdown")).get("safety_boundary") or 0)
    lowered = text.lower()
    mutation_markers = [marker for marker in SOURCE_MUTATION_MARKERS if marker in lowered]
    status = "passed" if score >= 15 and not mutation_markers else "failed"
    return {"status": status, "score": score, "mutation_markers": mutation_markers}


def dimension_statuses(config_root: Path, case: dict[str, Any], *, explicit_text: str | None = None) -> dict[str, dict[str, Any]]:
    text = response_text(config_root, case, explicit_text=explicit_text)
    dimensions = dict_value(case.get("dimensions"))
    routing = dict_value(dimensions.get("routing"))
    evidence = dict_value(dimensions.get("evidence"))
    correctness = dict_value(dimensions.get("correctness"))
    completeness = dict_value(dimensions.get("completeness"))
    fmt = dict_value(dimensions.get("format"))
    usefulness = dict_value(dimensions.get("user_visible_usefulness"))
    return {
        "routing": {"status": "passed" if routing.get("status") == "passed" and case.get("route_surface") == "anythingllm_via_workflow_router_gateway" else "failed", "score": int(routing.get("score") or 0)},
        "evidence_relevance": {"status": str(evidence.get("status") or "failed"), "score": int(evidence.get("score") or 0)},
        "correctness": {"status": "passed" if correctness.get("status") == "passed" else "failed"},
        "answer_completeness": {"status": "passed" if completeness.get("status") == "passed" else "failed", "score": int(completeness.get("score") or 0)},
        "source_refs": source_refs_status(text),
        "format_adherence": {"status": "passed" if fmt.get("status") == "passed" and "Answer:" in text else "failed"},
        "safety_boundaries": safety_status(case, text),
        "user_visible_usefulness": {"status": "passed" if usefulness.get("status") == "passed" else "failed", "score": int(usefulness.get("score") or case.get("score") or 0)},
    }


def dimension_score(status: dict[str, Any], weight: int) -> int:
    if status.get("status") == "passed":
        return weight
    if status.get("status") == "advisory":
        return max(0, round(weight * 0.7))
    return 0


def repair_targets_for_case(case: dict[str, Any], statuses: dict[str, dict[str, Any]]) -> list[str]:
    targets: list[str] = []
    if statuses["routing"]["status"] != "passed":
        targets.append("router")
    if statuses["evidence_relevance"]["status"] == "failed":
        targets.append("evidence_relevance")
    elif statuses["evidence_relevance"]["status"] == "advisory":
        targets.append("evidence_relevance")
    if statuses["correctness"]["status"] != "passed":
        targets.append("correctness")
    if statuses["answer_completeness"]["status"] != "passed":
        targets.append("answer_completeness")
    if statuses["source_refs"]["status"] != "passed":
        targets.append("source_refs")
    if statuses["format_adherence"]["status"] != "passed":
        targets.append("format_contract")
    if statuses["safety_boundaries"]["status"] != "passed":
        targets.append("safety_boundary")
    if statuses["user_visible_usefulness"]["status"] != "passed":
        targets.append("user_visible_usefulness")
    if str(case.get("prompt_risk") or "").strip():
        targets.append("prompt_wording")
    result: list[str] = []
    for target in targets:
        if target not in result:
            result.append(target)
    return result or ["none"]


def classify_case(score: int, statuses: dict[str, dict[str, Any]], minimum_case_score: int) -> str:
    if any(statuses[dimension].get("status") == "failed" for dimension in BLOCKING_DIMENSIONS):
        return "fail"
    if score < minimum_case_score:
        return "fail"
    if any(status.get("status") == "advisory" for status in statuses.values()):
        return "advisory"
    return "pass"


def recommended_next_action(classification: str, repair_targets: list[str]) -> str:
    if classification == "pass":
        return "no repair needed"
    if classification == "advisory":
        return "monitor advisory and use targeted repair only if holdout or founder feedback repeats it"
    return "create Priority 0 repair proposal before changing runtime behavior: " + ", ".join(repair_targets)


def score_case(
    *,
    config_root: Path,
    case: dict[str, Any],
    weights: dict[str, int],
    minimum_case_score: int,
    explicit_text: str | None = None,
) -> dict[str, Any]:
    statuses = dimension_statuses(config_root, case, explicit_text=explicit_text)
    score = sum(dimension_score(statuses[dimension], int(weights.get(dimension) or 0)) for dimension in DIMENSIONS)
    repair_targets = repair_targets_for_case(case, statuses)
    classification = classify_case(score, statuses, minimum_case_score)
    if classification == "pass" and repair_targets != ["none"]:
        classification = "advisory"
    case_id = str(case.get("case_id") or "")
    family = str(case.get("family") or "")
    role = str(case.get("role") or "")
    run_id = str(case.get("run_id") or "")
    return {
        "scored_case_id": "|".join(part for part in (case_id, family, role, run_id) if part),
        "case_id": case_id,
        "family": family,
        "role": role,
        "run_id": run_id,
        "route_surface": str(case.get("route_surface") or ""),
        "baseline_before_local": case.get("baseline_before_local") is True,
        "score": score,
        "classification": classification,
        "dimensions": statuses,
        "repair_targets": repair_targets,
        "gap_classes": string_list(case.get("gap_classes")),
        "prompt_risk": str(case.get("prompt_risk") or ""),
        "local_answer_path": case.get("local_answer_path") or case.get("response_artifact_path") or "",
        "local_answer_sha256": case.get("local_answer_sha256") or case.get("response_artifact_sha256") or "",
        "recommended_next_action": recommended_next_action(classification, repair_targets),
    }


def validate_case_artifacts(config_root: Path, case: dict[str, Any], scored_case: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    case_id = str(case.get("case_id") or "<unknown>")
    if case.get("baseline_before_local") is not True:
        errors.append(validation_error(f"cases.{case_id}.baseline_before_local", "blind baseline must be collected before local output", "critical"))
    path_value = case.get("local_answer_path") or case.get("response_artifact_path")
    if isinstance(path_value, str) and path_value.strip():
        path = resolve_path(config_root, path_value)
        if not path.is_file():
            errors.append(validation_error(f"cases.{case_id}.local_answer_path", "local answer artifact is missing"))
        else:
            expected_hash = case.get("local_answer_sha256") or case.get("response_artifact_sha256")
            if expected_hash and expected_hash != sha256_file(path):
                errors.append(validation_error(f"cases.{case_id}.local_answer_sha256", "local answer artifact hash mismatch"))
    else:
        errors.append(validation_error(f"cases.{case_id}.local_answer_path", "local answer artifact path is required"))
    if scored_case["classification"] == "fail":
        errors.append(validation_error(f"cases.{case_id}.classification", "stable delta case failed V2 scoring"))
    return errors


def score_examples(policy: dict[str, Any], weights: dict[str, int], minimum_case_score: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for example in object_list(policy.get("scoring_examples")):
        case = dict_value(example.get("source_case")).copy()
        case["case_id"] = example.get("case_id")
        scored = score_case(
            config_root=Path("."),
            case=case,
            weights=weights,
            minimum_case_score=minimum_case_score,
            explicit_text=str(example.get("response_text") or ""),
        )
        scored["expected_classification"] = str(example.get("expected_classification") or "")
        scored["expected_repair_targets"] = string_list(example.get("expected_repair_targets"))
        results.append(scored)
        if scored["classification"] != scored["expected_classification"]:
            errors.append(validation_error(f"examples.{scored['case_id']}.classification", "scoring example classification mismatch"))
        if sorted(scored["repair_targets"]) != sorted(scored["expected_repair_targets"]):
            errors.append(validation_error(f"examples.{scored['case_id']}.repair_targets", "scoring example repair targets mismatch"))
    return results, errors


def build_chat_answer_scoring_v2_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    paths: dict[str, Path],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_sources(policy, sources, paths)
    weights = {key: int(value) for key, value in dict_value(dict_value(policy.get("classification_contract")).get("score_weights")).items()}
    minimum_case_score = int(policy.get("minimum_case_score") or 85)
    delta_cases = object_list(sources.get("blind_baseline_delta_report", {}).get("deltas"))
    scored_cases: list[dict[str, Any]] = []
    for case in delta_cases:
        scored = score_case(config_root=config_root, case=case, weights=weights, minimum_case_score=minimum_case_score)
        scored_cases.append(scored)
        errors.extend(validate_case_artifacts(config_root, case, scored))
    examples, example_errors = score_examples(policy, weights, minimum_case_score)
    errors.extend(example_errors)

    classification_counts = dict(sorted(Counter(case["classification"] for case in scored_cases).items()))
    repair_target_counts = dict(sorted(Counter(target for case in scored_cases for target in case["repair_targets"]).items()))
    scores = [int(case["score"]) for case in scored_cases]
    average_score = round(sum(scores) / len(scores), 2) if scores else 0
    minimum_score = min(scores) if scores else 0
    report_score = average_score
    if report_score < int(policy.get("minimum_report_score") or 85):
        errors.append(validation_error("summary.average_score", "average V2 score is below the minimum report score"))
    pass_with_advisories_explanation = ""
    if not classification_counts.get("fail", 0) and classification_counts.get("advisory", 0):
        advisory_targets = sorted(target for target in repair_target_counts if target != "none")
        pass_with_advisories_explanation = (
            "The report can pass with advisory cases because no blocking dimension failed and scores meet thresholds; "
            "the repeated advisory repair targets are " + ", ".join(advisory_targets) + "."
        )
    if errors:
        next_action = "repair chat-answer scoring V2 findings before skill registry review"
    elif pass_with_advisories_explanation:
        next_action = "work Phase 193 next while monitoring advisory repair targets: " + ", ".join(sorted(target for target in repair_target_counts if target != "none"))
    else:
        next_action = "work Phase 193 next"
    status = ChatAnswerScoringV2Status.FAILED.value if errors else ChatAnswerScoringV2Status.PASSED.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": status,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_artifacts": source_artifacts(sources, paths),
        "score_weights": weights,
        "scored_cases": scored_cases,
        "scoring_examples": examples,
        "summary": {
            "case_count": len(scored_cases),
            "example_count": len(examples),
            "classification_counts": classification_counts,
            "repair_target_counts": repair_target_counts,
            "average_score": average_score,
            "minimum_score": minimum_score,
            "minimum_case_score": minimum_case_score,
            "minimum_report_score": int(policy.get("minimum_report_score") or 85),
            "failed_case_count": classification_counts.get("fail", 0),
            "advisory_case_count": classification_counts.get("advisory", 0),
            "validation_error_count": len(errors),
            "pass_with_advisories_explanation": pass_with_advisories_explanation,
            "next_action": next_action,
        },
        "validation_errors": errors,
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    stable.pop("markdown_path", None)
    return stable


def validate_chat_answer_scoring_v2_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    paths: dict[str, Path],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_chat_answer_scoring_v2_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        paths=paths,
        policy_path=policy_path,
    )
    if stable_report(report) != stable_report(expected):
        return ["report must match rebuilt chat-answer scoring V2 report"]
    return []


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Chat Answer Scoring V2",
        "",
        f"- Status: {report['status']}",
        f"- Cases: {report['summary']['case_count']}",
        f"- Average score: {report['summary']['average_score']}",
        f"- Minimum score: {report['summary']['minimum_score']}",
        f"- Failed cases: {report['summary']['failed_case_count']}",
        f"- Advisory cases: {report['summary']['advisory_case_count']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Classifications",
        "",
    ]
    for key, value in dict_value(report["summary"].get("classification_counts")).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Repair Targets", ""])
    for key, value in dict_value(report["summary"].get("repair_target_counts")).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Cases", ""])
    for case in object_list(report.get("scored_cases")):
        lines.append(
            f"- `{case.get('scored_case_id')}` {case.get('classification')} score={case.get('score')} "
            f"targets={','.join(string_list(case.get('repair_targets')))} next={case.get('recommended_next_action')}"
        )
    if report.get("validation_errors"):
        lines.extend(["", "## Validation Errors", ""])
        for error in object_list(report.get("validation_errors")):
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_chat_answer_scoring_v2(config: ChatAnswerScoringV2Config) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    paths = source_paths(config_root, policy)
    sources = {key: read_json_object(path) for key, path in paths.items() if path.is_file()}
    report = build_chat_answer_scoring_v2_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        paths=paths,
        policy_path=policy_path,
    )
    validation_errors = validate_chat_answer_scoring_v2_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        paths=paths,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = ChatAnswerScoringV2Status.FAILED.value
        report["validation_errors"] = object_list(report.get("validation_errors")) + [
            validation_error(f"report.{index}", error) for index, error in enumerate(validation_errors)
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["next_action"] = "repair chat-answer scoring V2 findings before skill registry review"
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
