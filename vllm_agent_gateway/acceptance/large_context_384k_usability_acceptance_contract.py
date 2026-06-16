"""Phase 258 384k large-context usability acceptance contract gate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_384k_usability_acceptance_contract_policy"
EXPECTED_REPORT_KIND = "large_context_384k_usability_acceptance_contract_report"
EXPECTED_PHASE = 258
EXPECTED_BACKLOG_ID = "P0-M6-258"
EXPECTED_MILESTONE_IDS = {"M2", "M4", "M6", "M8", "M14", "M16"}
TARGET_ESTIMATED_PROJECT_TOKENS = 384_000
REQUIRED_SURFACES = {"workflow_router_gateway", "anythingllm"}
REQUIRED_STRATEGIES = {"retrieval", "artifact_paging", "summarization", "refusal", "chunked_investigation"}
REQUIRED_SAFETY_TRUE_FLAGS = {
    "ignored_path_negative_controls_required",
    "private_path_negative_controls_required",
    "secret_like_negative_controls_required",
    "stale_index_rejection_required",
    "changed_ignore_policy_rejection_required",
    "changed_safety_policy_rejection_required",
}
REQUIRED_ANSWER_TRUE_FLAGS = {
    "answer_first_required",
    "chat_visible_strategy_required",
    "chat_visible_limitations_required",
    "source_refs_required_for_evidence_claims",
    "source_hash_revalidation_required",
    "blind_baseline_first_required",
    "holdout_rerun_required",
    "default_and_json_output_parity_required",
}
REQUIRED_PRECEDENCE = {
    258: {259, 260, 261, 262, 263, 264, 265, 266},
    259: {260, 261, 264, 265, 266},
    260: {261, 264, 265, 266},
    261: {262, 263, 264, 265, 266},
    262: {263, 264, 265, 266},
    263: {264, 265, 266},
    264: {265, 266},
    265: {266},
    266: set(),
}
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_384k_usability_acceptance_contract_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase258"
    / "phase258-large-context-384k-usability-acceptance-contract-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase258"
    / "phase258-large-context-384k-usability-acceptance-contract-report.md"
)
PHASE_HEADING_RE = re.compile(
    r"^### Approved Phase (?P<phase>\d+):(?P<title>.*?)\n(?P<body>.*?)(?=^### Approved Phase |\Z)",
    re.MULTILINE | re.DOTALL,
)


class LargeContext384kUsabilityAcceptanceContractStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext384kUsabilityAcceptanceContractConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH


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


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "source": source, "severity": severity}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 258"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M2, M4, M6, M8, M14, and M16"))
    if policy.get("target_estimated_project_tokens") != TARGET_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.target_estimated_project_tokens", "target must be 384000"))
    if not string_list(policy.get("contract_scope")):
        errors.append(validation_error("policy.contract_scope", "contract_scope must not be empty"))
    if set(string_list(policy.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must be workflow_router_gateway and anythingllm"))
    if set(string_list(policy.get("required_strategy_ids"))) != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.required_strategy_ids", "all required strategy ids must be present"))
    if len(string_list(policy.get("required_fixture_roots"))) < 3:
        errors.append(validation_error("policy.required_fixture_roots", "large corpus and both protected Coinbase fixtures are required"))
    if len(object_list(policy.get("required_acceptance_cases"))) < 5:
        errors.append(validation_error("policy.required_acceptance_cases", "at least five acceptance cases are required"))
    for case in object_list(policy.get("required_acceptance_cases")):
        case_id = case.get("case_id")
        strategy = case.get("required_strategy_id")
        score = case.get("minimum_score")
        if not isinstance(case_id, str) or not case_id.startswith("P258-"):
            errors.append(validation_error("policy.required_acceptance_cases.case_id", "case_id must start with P258-"))
        if strategy not in REQUIRED_STRATEGIES:
            errors.append(validation_error(f"policy.required_acceptance_cases.{case_id}.strategy", "case strategy is not a required strategy"))
        if not isinstance(score, int) or isinstance(score, bool) or score < 85:
            errors.append(validation_error(f"policy.required_acceptance_cases.{case_id}.minimum_score", "minimum_score must be >= 85"))
    answer = dict_value(policy.get("answer_contract"))
    for key in REQUIRED_ANSWER_TRUE_FLAGS:
        if answer.get(key) is not True:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be true"))
    if answer.get("artifact_only_answers_allowed") is not False:
        errors.append(validation_error("policy.answer_contract.artifact_only_answers_allowed", "artifact_only_answers_allowed must be false"))
    safety = dict_value(policy.get("safety_requirements"))
    for key in REQUIRED_SAFETY_TRUE_FLAGS:
        if safety.get(key) is not True:
            errors.append(validation_error(f"policy.safety_requirements.{key}", f"{key} must be true"))
    for key in (
        "raw_prompt_stuffing_allowed",
        "raw_384k_prompt_support_claim_allowed",
        "raw_1m_prompt_support_claim_allowed",
        "store_source_text",
        "store_rejected_content",
        "protected_fixture_mutation_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(validation_error(f"policy.safety_requirements.{key}", f"{key} must be false"))
    if safety.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.safety_requirements.source_text_retention", "source_text_retention must be metadata_only"))
    if len(string_list(policy.get("required_supporting_policies"))) < 5:
        errors.append(validation_error("policy.required_supporting_policies", "supporting policies are required"))
    if len(string_list(policy.get("required_docs"))) < 6:
        errors.append(validation_error("policy.required_docs", "required_docs must include durable docs, README, and example"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE258 LARGE CONTEXT 384K USABILITY ACCEPTANCE CONTRACT PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 258"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        markers = string_list(required_markers.get(raw_path))
        missing = [marker for marker in markers if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        results.append(result)
    return results, errors


def supporting_policy_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    for raw_path in string_list(policy.get("required_supporting_policies")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "kind": None}
        if not path.is_file():
            errors.append(validation_error(f"supporting_policies.{raw_path}.missing", "supporting policy is missing", source="supporting_policies"))
            results.append(result)
            continue
        payload = read_json_object(path)
        result["sha256"] = sha256_file(path)
        result["kind"] = payload.get("kind")
        results.append(result)
    return results, errors


def roadmap_phase_statuses(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, str | None], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    roadmap_path = config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md"
    if not roadmap_path.is_file():
        return {}, [validation_error("roadmap.missing", "docs/ACTIONABLE_WORKFLOW_ROADMAP.md is missing", source="roadmap")]
    text = roadmap_path.read_text(encoding="utf-8")
    phases = {match.group("phase"): match.group("body") for match in PHASE_HEADING_RE.finditer(text)}
    required = dict(dict_value(policy.get("required_predecessor_phase_statuses")))
    required.update(dict_value(policy.get("approved_followup_phase_statuses")))
    statuses: dict[str, str | None] = {}
    for phase, expected_status in required.items():
        body = phases.get(str(phase))
        status = None
        if body:
            status_match = re.search(r"^Status:\s*(?P<status>.+?)\s*$", body, flags=re.MULTILINE)
            status = status_match.group("status") if status_match else None
        statuses[str(phase)] = status
        status_matches = status == expected_status or (expected_status == "Approved." and status == "Complete.")
        if not status_matches:
            errors.append(
                validation_error(
                    f"roadmap.phase{phase}.status",
                    f"Phase {phase} must be {expected_status!r}, got {status!r}",
                    source="roadmap",
                )
            )
    return statuses, errors


def phase_sequence_checks(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    sequence = object_list(policy.get("required_phase_sequence"))
    entries: list[dict[str, Any]] = []
    phases = [item.get("phase") for item in sequence if isinstance(item.get("phase"), int)]
    if phases != sorted(phases):
        errors.append(validation_error("policy.required_phase_sequence.order", "required_phase_sequence must be sorted by phase"))
    if phases != list(range(258, 267)):
        errors.append(validation_error("policy.required_phase_sequence.phases", "required_phase_sequence must cover phases 258 through 266"))
    for item in sequence:
        phase = item.get("phase")
        must_precede = [value for value in item.get("must_precede", []) if isinstance(value, int)] if isinstance(item.get("must_precede"), list) else []
        entries.append({"phase": phase, "name": item.get("name"), "must_precede": must_precede})
        if isinstance(phase, int):
            missing_precedence = sorted(REQUIRED_PRECEDENCE.get(phase, set()) - set(must_precede))
            if missing_precedence:
                errors.append(
                    validation_error(
                        f"policy.required_phase_sequence.{phase}.missing_precedence",
                        f"missing must_precede phases: {missing_precedence}",
                    )
                )
            for later in must_precede:
                if later <= phase:
                    errors.append(validation_error(f"policy.required_phase_sequence.{phase}", "must_precede entries must be later phases"))
    return entries, errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 384k Usability Acceptance Contract",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Target estimated project tokens: `{summary.get('target_estimated_project_tokens')}`",
        f"- Required case count: `{summary.get('required_acceptance_case_count')}`",
        f"- Required follow-up phase count: `{summary.get('required_followup_phase_count')}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_384k_usability_acceptance_contract(
    config: LargeContext384kUsabilityAcceptanceContractConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    supporting_policies, supporting_errors = supporting_policy_checks(config_root, policy)
    phase_statuses, roadmap_errors = roadmap_phase_statuses(config_root, policy)
    sequence, sequence_errors = phase_sequence_checks(policy)
    errors = policy_errors + docs_errors + supporting_errors + roadmap_errors + sequence_errors
    status = (
        LargeContext384kUsabilityAcceptanceContractStatus.PASSED.value
        if not errors
        else LargeContext384kUsabilityAcceptanceContractStatus.FAILED.value
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "docs": docs,
        "supporting_policies": supporting_policies,
        "roadmap_phase_statuses": phase_statuses,
        "required_phase_sequence": sequence,
        "required_surfaces": string_list(policy.get("required_surfaces")),
        "required_strategy_ids": string_list(policy.get("required_strategy_ids")),
        "safety_requirements": dict_value(policy.get("safety_requirements")),
        "answer_contract": dict_value(policy.get("answer_contract")),
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "target_estimated_project_tokens": policy.get("target_estimated_project_tokens"),
            "required_acceptance_case_count": len(object_list(policy.get("required_acceptance_cases"))),
            "required_followup_phase_count": len(dict_value(policy.get("approved_followup_phase_statuses"))),
            "phase258_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
