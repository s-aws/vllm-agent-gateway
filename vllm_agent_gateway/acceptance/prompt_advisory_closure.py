"""Phase 165 prompt-advisory closure governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_field_round2 import (
    build_founder_field_round2_report,
    materialize_blind_baseline_package,
)
from vllm_agent_gateway.prompt_catalogs import load_founder_field_prompts


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "prompt_advisory_closure_policy"
EXPECTED_REPORT_KIND = "prompt_advisory_closure_report"
EXPECTED_FIELD_SOURCE_KIND = "founder_field_prompt_evaluation"
EXPECTED_FEEDBACK_KIND = "transcript_quality_feedback_intake_report"
EXPECTED_ROUND2_KIND = "founder_field_round2_report"
EXPECTED_PHASE = 165
EXPECTED_BACKLOG_ID = "P0-BB-029"
DEFAULT_POLICY_PATH = Path("runtime") / "prompt_advisory_closure_policy.json"
DEFAULT_ROUND2_POLICY_PATH = Path("runtime") / "founder_field_round2_policy.json"
DEFAULT_ROUND2_BASELINE_SOURCE_PATH = Path("runtime") / "founder_field_round2_blind_baselines.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "prompt-advisory-closure" / "phase165"
DEFAULT_REFINED_FIELD_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase165-refined-prompt-run.json"
DEFAULT_REFINED_FIELD_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase165-refined-prompt-run.md"
DEFAULT_HOLDOUT_FIELD_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase165-holdout-run.json"
DEFAULT_HOLDOUT_FIELD_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase165-holdout-run.md"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase165-prompt-advisory-closure-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase165-prompt-advisory-closure-report.md"


class PromptAdvisoryClosureStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ClosureDecision(str, Enum):
    CLOSED_REFINED_PROMPT_PROVEN = "closed_refined_prompt_proven"
    DOCUMENTED_GUIDANCE = "documented_guidance"
    PRODUCT_GAP_ESCALATION = "product_gap_escalation"


@dataclass(frozen=True)
class PromptAdvisoryClosureConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    round2_policy_path: Path = DEFAULT_ROUND2_POLICY_PATH
    round2_baseline_source_path: Path = DEFAULT_ROUND2_BASELINE_SOURCE_PATH
    refined_field_report_path: Path = DEFAULT_REFINED_FIELD_REPORT_PATH
    holdout_field_report_path: Path = DEFAULT_HOLDOUT_FIELD_REPORT_PATH
    output_path: Path = DEFAULT_REPORT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_PATH


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


def case_by_id(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(case.get("case_id")): case for case in cases if isinstance(case.get("case_id"), str)}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 165")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    advisory_ids = string_list(policy.get("required_advisory_case_ids"))
    holdout_ids = string_list(policy.get("holdout_case_ids"))
    if len(advisory_ids) != 14:
        errors.append("policy.required_advisory_case_ids must contain the 14 Phase 158 advisory cases")
    if len(advisory_ids) != len(set(advisory_ids)):
        errors.append("policy.required_advisory_case_ids must be unique")
    if not holdout_ids:
        errors.append("policy.holdout_case_ids must be non-empty")
    if set(advisory_ids) & set(holdout_ids):
        errors.append("policy.holdout_case_ids must not overlap advisory cases")
    if set(string_list(policy.get("allowed_closure_decisions"))) != {item.value for item in ClosureDecision}:
        errors.append("policy.allowed_closure_decisions must match the three governed closure decisions")
    if policy.get("required_route_surface") != "anythingllm_via_workflow_router_gateway":
        errors.append("policy.required_route_surface must require AnythingLLM via workflow-router gateway")
    for key in ("minimum_refined_score", "minimum_holdout_score"):
        if not isinstance(policy.get(key), int) or int(policy.get(key)) < 1:
            errors.append(f"policy.{key} must be a positive integer")
    if policy.get("refined_prompts_are_test_candidates_only") is not True:
        errors.append("policy.refined_prompts_are_test_candidates_only must be true")
    if policy.get("acceptance_marker") != "PHASE165 PROMPT ADVISORY CLOSURE PASS":
        errors.append("policy.acceptance_marker must be PHASE165 PROMPT ADVISORY CLOSURE PASS")
    sources = dict_value(policy.get("required_source_paths"))
    for key in ("phase158_feedback_report", "phase164_round2_report", "prompt_catalog"):
        if not isinstance(sources.get(key), str) or not sources[key].strip():
            errors.append(f"policy.required_source_paths.{key} must be a path string")
    return errors


def catalog_refinements(config_root: Path) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for case in load_founder_field_prompts(config_root):
        if case.refined_prompt:
            records[case.case_id] = {
                "prompt": case.prompt,
                "refined_prompt": case.refined_prompt,
                "prompt_risk": case.prompt_risk,
                "target_root": case.target_root,
            }
    return records


def validate_field_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    report: dict[str, Any],
    required_case_ids: list[str],
    expected_variant: str,
    source: str,
    require_pass: bool,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if report.get("kind") != EXPECTED_FIELD_SOURCE_KIND:
        errors.append({"id": f"{source}.kind", "severity": "high", "message": f"{source} kind must be {EXPECTED_FIELD_SOURCE_KIND}"})
    if require_pass and report.get("status") != "passed":
        errors.append({"id": f"{source}.status", "severity": "high", "message": f"{source} must pass"})
    if not require_pass and report.get("status") not in {"passed", "failed"}:
        errors.append({"id": f"{source}.status", "severity": "high", "message": f"{source} status must be passed or failed"})
    if dict_value(report.get("anythingllm_preflight")).get("status") != "passed":
        errors.append({"id": f"{source}.anythingllm_preflight", "severity": "high", "message": f"{source} AnythingLLM preflight must pass"})
    if object_list(report.get("errors")) or string_list(report.get("errors")):
        errors.append({"id": f"{source}.errors", "severity": "high", "message": f"{source} errors must be empty"})
    if report.get("fixture_state_before") != report.get("fixture_state_after"):
        errors.append({"id": f"{source}.fixture_state_changed", "severity": "critical", "message": f"{source} changed protected fixture state"})
    cases = object_list(report.get("cases"))
    case_ids = [str(case.get("case_id")) for case in cases]
    if set(case_ids) != set(required_case_ids):
        errors.append({"id": f"{source}.case_ids", "severity": "high", "message": f"{source} case IDs must match policy"})
    for index, case in enumerate(cases):
        prefix = f"{source}.cases[{index}]"
        if require_pass and case.get("status") != "passed":
            errors.append({"id": f"{prefix}.status", "severity": "high", "message": "case must pass"})
        if case.get("route_surface") != policy.get("required_route_surface"):
            errors.append({"id": f"{prefix}.route_surface", "severity": "high", "message": "case must prove AnythingLLM via workflow-router gateway"})
        if not isinstance(case.get("run_id"), str) or not str(case.get("run_id")).startswith("workflow-router-"):
            errors.append({"id": f"{prefix}.run_id", "severity": "high", "message": "case must include workflow-router run_id"})
        if case.get("prompt_variant") != expected_variant:
            errors.append({"id": f"{prefix}.prompt_variant", "severity": "high", "message": f"case prompt_variant must be {expected_variant}"})
        raw_path = case.get("response_artifact_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append({"id": f"{prefix}.response_artifact_path", "severity": "high", "message": "case must include response_artifact_path"})
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            errors.append({"id": f"{prefix}.response_artifact_missing", "severity": "high", "message": "response artifact must exist"})
            continue
        actual_hash = sha256_file(path)
        if case.get("response_artifact_sha256") != actual_hash:
            errors.append({"id": f"{prefix}.response_artifact_hash", "severity": "high", "message": "response artifact hash mismatch"})
        if case.get("text_sha256") != actual_hash:
            errors.append({"id": f"{prefix}.text_hash", "severity": "high", "message": "text_sha256 must match response artifact hash"})
    return errors


def scored_cases(
    *,
    config_root: Path,
    round2_policy: dict[str, Any],
    baseline_source: dict[str, Any],
    field_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    baseline = materialize_blind_baseline_package(policy=round2_policy, baseline_package=baseline_source)
    fake_readiness = {"kind": "post_restart_runtime_readiness_report", "status": "passed", "decision": "ready_after_restart"}
    fake_phase158 = {"kind": EXPECTED_FEEDBACK_KIND, "status": "passed", "accepted_findings": []}
    report = build_founder_field_round2_report(
        config_root=config_root,
        policy=round2_policy,
        baseline_package=baseline,
        field_report=field_report,
        readiness_report=fake_readiness,
        phase158_report=fake_phase158,
    )
    return case_by_id(object_list(report.get("case_evidence")))


def closure_for_case(
    *,
    policy: dict[str, Any],
    finding: dict[str, Any],
    phase164_case: dict[str, Any],
    refined_case: dict[str, Any],
    holdout_min_score: int,
    refinement: dict[str, str],
) -> dict[str, Any]:
    refined_score = int(refined_case.get("score") or 0)
    phase164_score = int(phase164_case.get("score") or 0)
    threshold = int(policy.get("minimum_refined_score") or 85)
    refined_failed = refined_case.get("status") != "passed" or refined_case.get("quality_classification") == "blocker"
    if refined_failed:
        decision = ClosureDecision.PRODUCT_GAP_ESCALATION.value
        rationale = "Refined prompt candidate produced a failed or blocker-classified live result and should feed the proposal phase, not implementation in Phase 165."
    elif refined_score >= threshold and holdout_min_score >= int(policy.get("minimum_holdout_score") or 85):
        decision = ClosureDecision.DOCUMENTED_GUIDANCE.value
        rationale = "Refined prompt candidate is proven and holdouts passed, but Phase 164 already passed; keep as documented user/operator guidance rather than a silent rewrite."
    elif refined_score >= threshold:
        decision = ClosureDecision.DOCUMENTED_GUIDANCE.value
        rationale = "Refined prompt candidate passed, but holdout proof is insufficient for closure beyond documented guidance."
    else:
        decision = ClosureDecision.PRODUCT_GAP_ESCALATION.value
        rationale = "Refined prompt candidate did not meet the minimum score and should feed the proposal phase, not implementation in Phase 165."
    if not refined_failed and phase164_score < threshold and refined_score >= threshold and holdout_min_score >= int(policy.get("minimum_holdout_score") or 85):
        decision = ClosureDecision.CLOSED_REFINED_PROMPT_PROVEN.value
        rationale = "Original advisory missed the target, refined prompt resolved the risk, and holdouts passed without regression."
    return {
        "case_id": finding.get("case_id"),
        "risk": finding.get("message"),
        "phase158_finding_id": finding.get("finding_id"),
        "phase164_score": phase164_score,
        "phase164_classification": phase164_case.get("quality_classification"),
        "refined_prompt": refinement.get("refined_prompt", ""),
        "refined_prompt_sha256": hashlib.sha256(refinement.get("refined_prompt", "").encode("utf-8")).hexdigest(),
        "refined_score": refined_score,
        "refined_classification": refined_case.get("quality_classification"),
        "refined_run_id": refined_case.get("run_id"),
        "refined_response_artifact_path": refined_case.get("response_artifact_path"),
        "refined_response_artifact_sha256": refined_case.get("response_artifact_sha256"),
        "target_root": refined_case.get("target_root"),
        "route_surface": refined_case.get("route_surface"),
        "decision": decision,
        "rationale": rationale,
        "silent_rewrite_performed": False,
        "holdout_min_score": holdout_min_score,
    }


def validation_errors_for_sources(
    *,
    config_root: Path,
    policy: dict[str, Any],
    phase158_report: dict[str, Any],
    phase164_report: dict[str, Any],
    refined_report: dict[str, Any],
    holdout_report: dict[str, Any],
    closure_records: list[dict[str, Any]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    errors.extend({"id": f"policy.{index}", "severity": "high", "message": error} for index, error in enumerate(validate_policy(policy)))
    if phase158_report.get("kind") != EXPECTED_FEEDBACK_KIND or phase158_report.get("status") != "passed":
        errors.append({"id": "phase158.source", "severity": "high", "message": "Phase 158 feedback report must pass"})
    if phase164_report.get("kind") != EXPECTED_ROUND2_KIND or phase164_report.get("status") != "passed":
        errors.append({"id": "phase164.source", "severity": "high", "message": "Phase 164 round 2 report must pass"})
    advisory_ids = string_list(policy.get("required_advisory_case_ids"))
    accepted = [
        item for item in object_list(phase158_report.get("accepted_findings"))
        if item.get("category") == "prompt_issue" and item.get("owner_path") == "prompt_catalog_review"
    ]
    accepted_ids = [str(item.get("case_id")) for item in accepted]
    if set(accepted_ids) != set(advisory_ids):
        errors.append({"id": "phase158.advisory_ids", "severity": "high", "message": "Phase 158 prompt advisory IDs must match policy"})
    phase164_cases = case_by_id(object_list(phase164_report.get("case_evidence")))
    missing_phase164 = sorted(set(advisory_ids) - set(phase164_cases))
    if missing_phase164:
        errors.append({"id": "phase164.advisory_ids", "severity": "high", "message": "Phase 164 missing advisory cases: " + ", ".join(missing_phase164)})
    errors.extend(
        validate_field_report(
            config_root=config_root,
            policy=policy,
            report=refined_report,
            required_case_ids=advisory_ids,
            expected_variant="refined",
            source="refined",
            require_pass=False,
        )
    )
    errors.extend(
        validate_field_report(
            config_root=config_root,
            policy=policy,
            report=holdout_report,
            required_case_ids=string_list(policy.get("holdout_case_ids")),
            expected_variant="original",
            source="holdout",
            require_pass=True,
        )
    )
    closure_ids = [str(item.get("case_id")) for item in closure_records]
    if set(closure_ids) != set(advisory_ids) or len(closure_ids) != len(set(closure_ids)):
        errors.append({"id": "closure.case_ids", "severity": "high", "message": "closure records must have exactly one record per advisory case"})
    allowed = set(string_list(policy.get("allowed_closure_decisions")))
    for index, record in enumerate(closure_records):
        prefix = f"closure.records[{index}]"
        if record.get("decision") not in allowed:
            errors.append({"id": f"{prefix}.decision", "severity": "high", "message": "closure decision is not allowed"})
        if record.get("silent_rewrite_performed") is not False:
            errors.append({"id": f"{prefix}.silent_rewrite", "severity": "critical", "message": "refined prompts must not be treated as silent rewrites"})
        for key in ("risk", "refined_prompt", "refined_run_id", "refined_response_artifact_path", "refined_response_artifact_sha256", "route_surface", "rationale"):
            if not isinstance(record.get(key), str) or not str(record.get(key)).strip():
                errors.append({"id": f"{prefix}.{key}", "severity": "high", "message": f"closure record missing {key}"})
    return errors


def build_prompt_advisory_closure_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    round2_policy: dict[str, Any],
    round2_baseline_source: dict[str, Any],
    phase158_report: dict[str, Any],
    phase164_report: dict[str, Any],
    refined_report: dict[str, Any],
    holdout_report: dict[str, Any],
    policy_path: Path | None = None,
    refined_report_path: Path | None = None,
    holdout_report_path: Path | None = None,
    phase158_report_path: Path | None = None,
    phase164_report_path: Path | None = None,
) -> dict[str, Any]:
    refinements = catalog_refinements(config_root)
    refined_scored = scored_cases(
        config_root=config_root,
        round2_policy=round2_policy,
        baseline_source=round2_baseline_source,
        field_report=refined_report,
    )
    holdout_scored = scored_cases(
        config_root=config_root,
        round2_policy=round2_policy,
        baseline_source=round2_baseline_source,
        field_report=holdout_report,
    )
    phase164_cases = case_by_id(object_list(phase164_report.get("case_evidence")))
    holdout_min_score = min((int(item.get("score") or 0) for item in holdout_scored.values()), default=0)
    accepted = [
        item for item in object_list(phase158_report.get("accepted_findings"))
        if item.get("category") == "prompt_issue" and item.get("owner_path") == "prompt_catalog_review"
    ]
    closure_records = [
        closure_for_case(
            policy=policy,
            finding=finding,
            phase164_case=phase164_cases.get(str(finding.get("case_id")), {}),
            refined_case=refined_scored.get(str(finding.get("case_id")), {}),
            holdout_min_score=holdout_min_score,
            refinement=refinements.get(str(finding.get("case_id")), {}),
        )
        for finding in accepted
    ]
    errors = validation_errors_for_sources(
        config_root=config_root,
        policy=policy,
        phase158_report=phase158_report,
        phase164_report=phase164_report,
        refined_report=refined_report,
        holdout_report=holdout_report,
        closure_records=closure_records,
    )
    decision_counts = {
        decision.value: sum(1 for item in closure_records if item.get("decision") == decision.value)
        for decision in ClosureDecision
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": PromptAdvisoryClosureStatus.FAILED.value if errors else PromptAdvisoryClosureStatus.PASSED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "phase158_report_path": str(phase158_report_path.resolve()) if phase158_report_path else None,
        "phase158_report_sha256": artifact_hash(phase158_report_path),
        "phase164_report_path": str(phase164_report_path.resolve()) if phase164_report_path else None,
        "phase164_report_sha256": artifact_hash(phase164_report_path),
        "refined_report_path": str(refined_report_path.resolve()) if refined_report_path else None,
        "refined_report_sha256": artifact_hash(refined_report_path),
        "holdout_report_path": str(holdout_report_path.resolve()) if holdout_report_path else None,
        "holdout_report_sha256": artifact_hash(holdout_report_path),
        "closure_records": closure_records,
        "holdout_evidence": list(holdout_scored.values()),
        "summary": {
            "closure_count": len(closure_records),
            "decision_counts": decision_counts,
            "refined_min_score": min((int(item.get("refined_score") or 0) for item in closure_records), default=0),
            "holdout_min_score": holdout_min_score,
            "product_gap_escalation_count": decision_counts[ClosureDecision.PRODUCT_GAP_ESCALATION.value],
            "phase169_required": decision_counts[ClosureDecision.PRODUCT_GAP_ESCALATION.value] > 0,
            "validation_error_count": len(errors),
            "next_action": "begin Phase 166 generic chat and vague prompt contract"
            if decision_counts[ClosureDecision.PRODUCT_GAP_ESCALATION.value] == 0
            else "route product gaps through Phase 169 proposal pass",
        },
        "validation_errors": errors,
    }


def stable_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "status",
            "policy_path",
            "policy_sha256",
            "phase158_report_path",
            "phase158_report_sha256",
            "phase164_report_path",
            "phase164_report_sha256",
            "refined_report_path",
            "refined_report_sha256",
            "holdout_report_path",
            "holdout_report_sha256",
            "closure_records",
            "holdout_evidence",
            "summary",
            "validation_errors",
        )
    }


def validate_prompt_advisory_closure_report(report: dict[str, Any], **kwargs: Any) -> list[str]:
    expected = build_prompt_advisory_closure_report(**kwargs)
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt prompt advisory closure report"]
    return []


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Prompt Advisory Closure",
        "",
        f"- Status: {report['status']}",
        f"- Closure count: {report['summary']['closure_count']}",
        f"- Decision counts: {report['summary']['decision_counts']}",
        f"- Refined min score: {report['summary']['refined_min_score']}",
        f"- Holdout min score: {report['summary']['holdout_min_score']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Closures",
        "",
        "| Case | Decision | Phase 164 Score | Refined Score | Holdout Min | Run ID | Rationale |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for record in object_list(report.get("closure_records")):
        rationale = str(record.get("rationale") or "").replace("\n", " ")
        lines.append(
            f"| {record.get('case_id')} | {record.get('decision')} | {record.get('phase164_score')} | "
            f"{record.get('refined_score')} | {record.get('holdout_min_score')} | {record.get('refined_run_id')} | {rationale[:300]} |"
        )
    if report["validation_errors"]:
        lines.extend(["", "## Validation Errors", ""])
        for error in report["validation_errors"]:
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_prompt_advisory_closure(config: PromptAdvisoryClosureConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    round2_policy_path = resolve_path(config_root, config.round2_policy_path)
    round2_baseline_source_path = resolve_path(config_root, config.round2_baseline_source_path)
    refined_field_report_path = resolve_path(config_root, config.refined_field_report_path)
    holdout_field_report_path = resolve_path(config_root, config.holdout_field_report_path)
    policy = read_json_object(policy_path)
    round2_policy = read_json_object(round2_policy_path)
    round2_baseline_source = read_json_object(round2_baseline_source_path)
    sources = dict_value(policy.get("required_source_paths"))
    phase158_report_path = resolve_path(config_root, str(sources.get("phase158_feedback_report") or ""))
    phase164_report_path = resolve_path(config_root, str(sources.get("phase164_round2_report") or ""))
    phase158_report = read_json_object(phase158_report_path)
    phase164_report = read_json_object(phase164_report_path)
    refined_report = read_json_object(refined_field_report_path)
    holdout_report = read_json_object(holdout_field_report_path)
    report = build_prompt_advisory_closure_report(
        config_root=config_root,
        policy=policy,
        round2_policy=round2_policy,
        round2_baseline_source=round2_baseline_source,
        phase158_report=phase158_report,
        phase164_report=phase164_report,
        refined_report=refined_report,
        holdout_report=holdout_report,
        policy_path=policy_path,
        refined_report_path=refined_field_report_path,
        holdout_report_path=holdout_field_report_path,
        phase158_report_path=phase158_report_path,
        phase164_report_path=phase164_report_path,
    )
    validation_errors = validate_prompt_advisory_closure_report(
        report,
        config_root=config_root,
        policy=policy,
        round2_policy=round2_policy,
        round2_baseline_source=round2_baseline_source,
        phase158_report=phase158_report,
        phase164_report=phase164_report,
        refined_report=refined_report,
        holdout_report=holdout_report,
        policy_path=policy_path,
        refined_report_path=refined_field_report_path,
        holdout_report_path=holdout_field_report_path,
        phase158_report_path=phase158_report_path,
        phase164_report_path=phase164_report_path,
    )
    if validation_errors:
        report["status"] = PromptAdvisoryClosureStatus.FAILED.value
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
