"""Phase 260 stale-index rejection gate for 384k usability."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    build_chunks_for_file,
    read_json_object,
    write_json,
)
from vllm_agent_gateway.controllers.large_context.context_strategy import select_context_strategy
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    RetrievalBackedChatAnswerRequest,
    invoke_retrieval_backed_chat_answer,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_384k_stale_index_rejection_policy"
EXPECTED_REPORT_KIND = "large_context_384k_stale_index_rejection_report"
EXPECTED_PHASE = 260
EXPECTED_BACKLOG_ID = "P0-M6-260"
EXPECTED_MILESTONE_IDS = {"M6", "M8", "M16"}
TARGET_ESTIMATED_PROJECT_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_384k_stale_index_rejection_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase260"
    / "phase260-large-context-384k-stale-index-rejection-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase260"
    / "phase260-large-context-384k-stale-index-rejection-report.md"
)


class LargeContext384kStaleIndexRejectionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext384kStaleIndexRejectionConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    validate_phase259_precondition: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    text = str(value)
    if os.name == "nt" and len(text) > 7 and text.startswith("/mnt/") and text[5].isalpha() and text[6] == "/":
        return Path(f"{text[5].upper()}:/{text[7:]}")
    path = Path(value)
    return path if path.is_absolute() else config_root / path


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
        errors.append(validation_error("policy.phase", "phase must be 260"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6, M8, and M16"))
    if policy.get("target_estimated_project_tokens") != TARGET_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.target_estimated_project_tokens", "target must be 384000"))
    if len(object_list(policy.get("required_cases"))) < 6:
        errors.append(validation_error("policy.required_cases", "six stale/unsafe rejection cases are required"))
    properties = dict_value(policy.get("required_fail_closed_properties"))
    for key in (
        "artifact_only_answers_allowed",
        "raw_prompt_stuffing_allowed",
        "store_source_text",
        "store_rejected_content",
        "serve_stale_evidence_allowed",
        "serve_ignored_or_secret_like_evidence_allowed",
    ):
        if properties.get(key) is not False:
            errors.append(validation_error(f"policy.required_fail_closed_properties.{key}", f"{key} must be false"))
    if properties.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.required_fail_closed_properties.source_text_retention", "source_text_retention must be metadata_only"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE260 LARGE CONTEXT 384K STALE INDEX REJECTION PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 260"))
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
        missing = [marker for marker in string_list(required_markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        results.append(result)
    return results, errors


def phase259_precondition_errors(config_root: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    precondition = dict_value(policy.get("phase259_precondition"))
    report_path = config_root / "runtime-state" / "phase259" / "phase259-large-context-384k-fixture-index-readiness-report.json"
    if not report_path.is_file():
        return [validation_error("phase259.report_missing", "Phase 259 readiness report is missing", source="phase259")]
    report = read_json_object(report_path)
    if report.get("status") != precondition.get("required_status"):
        return [validation_error("phase259.status", "Phase 259 readiness report must pass", source="phase259")]
    if dict_value(report.get("summary")).get("phase260_ready") is not True:
        return [validation_error("phase259.phase260_ready", "Phase 259 must mark phase260_ready=true", source="phase259")]
    return []


def phase216_policy(config_root: Path) -> dict[str, Any]:
    return read_json_object(config_root / "runtime" / "corpus_index_safety_governance_policy.json")


def make_disposable_index(config_root: Path, case_root: Path) -> tuple[Path, Path, Path]:
    target_root = case_root / "fixture"
    target_root.mkdir(parents=True, exist_ok=True)
    write_text(target_root / ".gitignore", "ignored/\nruntime-state/\n*.bin\n*.secret\n")
    write_text(target_root / ".cgcignore", "private/\n*.secret\n")
    files = [
        target_root / "src" / "order_replay" / "module_0000.py",
        target_root / "src" / "order_replay" / "module_0001.py",
        target_root / "tests" / "test_order_replay.py",
        target_root / "docs" / "architecture.md",
    ]
    body = "\n".join(
        [
            "order replay pipeline risk gate audit summary context retrieval source evidence token budget generated service"
            for _ in range(24)
        ]
    )
    write_text(files[0], "def replay_stage(event):\n    return event\n" + body)
    write_text(files[1], "def audit_summary(event):\n    return {'audit_summary': event}\n" + body)
    write_text(files[2], "def test_risk_gate_audit_summary():\n    assert True\n" + body)
    write_text(files[3], "# Generated Service Architecture\n\n" + body)
    write_text(target_root / "private" / "operator.secret", "PHASE260_DUMMY_SECRET_DO_NOT_EXPOSE\n")
    safety_policy = phase216_policy(config_root)
    safety_policy_path = case_root / "phase216-policy.json"
    write_json(safety_policy_path, safety_policy)
    chunks: list[dict[str, Any]] = []
    for path in files:
        chunks.extend(
            build_chunks_for_file(
                root=target_root,
                path=path,
                phase216_policy=safety_policy,
                chunk_line_count=80,
                chars_per_token=4.0,
                term_limit=24,
                max_search_term_length=32,
            )
        )
    index_path = case_root / "context-index.json"
    write_json(
        index_path,
        {
            "schema_version": 1,
            "kind": "metadata_first_context_index",
            "phase": 217,
            "target_root": str(target_root),
            "source_text_retention": "metadata_only",
            "store_source_text": False,
            "store_rejected_content": False,
            "indexed_file_count": len(files),
            "chunk_count": len(chunks),
            "estimated_indexed_token_count": sum(int(item["estimated_tokens"]) for item in chunks),
            "chunks": chunks,
        },
    )
    context_policy_path = case_root / "context-index-policy.json"
    write_json(
        context_policy_path,
        {
            "schema_version": 1,
            "kind": "context_index_prototype_policy",
            "phase": 217,
            "phase216_policy_path": str(safety_policy_path),
            "source_corpus": {"root": str(target_root)},
            "index_artifact": {"path": str(index_path)},
        },
    )
    return target_root, context_policy_path, index_path


def route_prompt() -> str:
    return "In the large corpus fixture, find evidence for how risk gate decisions flow into audit summaries."


def mutate_case(case_root: Path, target_root: Path, context_policy_path: Path, index_path: Path, mutation: str) -> None:
    if mutation == "stale_source_hash":
        index = read_json_object(index_path)
        index["chunks"][0]["source_sha256"] = "0" * 64
        write_json(index_path, index)
        return
    if mutation == "changed_ignore_policy_hash":
        write_text(target_root / ".gitignore", "ignored/\nruntime-state/\n*.bin\n*.secret\nnew-deny/\n")
        return
    if mutation == "changed_safety_policy_hash":
        context_policy = read_json_object(context_policy_path)
        safety_policy_path = Path(context_policy["phase216_policy_path"])
        safety_policy = read_json_object(safety_policy_path)
        safety_policy["secret_like_patterns"].append({"contains": "NEW_SENTINEL"})
        write_json(safety_policy_path, safety_policy)
        return
    if mutation == "source_missing":
        (target_root / "src" / "order_replay" / "module_0000.py").unlink()


def run_router_case(config_root: Path, case_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    target_root, context_policy_path, index_path = make_disposable_index(config_root, case_root)
    mutate_case(case_root, target_root, context_policy_path, index_path, str(case.get("mutation")))
    decision = select_context_strategy(
        config_root=config_root,
        target_root=target_root,
        user_request=route_prompt(),
        route_evidence=[{"source": "router_rule", "rule": "large_context_read_only_terms"}],
        selected_workflow="code_investigation.plan",
        request_context={"context_index_policy_path": str(context_policy_path)},
    )
    passed = (
        decision.get("status") == case.get("expected_status")
        and decision.get("reason") == case.get("expected_reason")
        and decision.get("source_freshness_status") == "stale"
    )
    return {"case_id": case.get("case_id"), "surface": "context_strategy_router", "passed": passed, "decision": decision}


def run_retrieval_case(config_root: Path, case_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    target_root, context_policy_path, index_path = make_disposable_index(config_root, case_root)
    mutation = str(case.get("mutation"))
    mutate_case(case_root, target_root, context_policy_path, index_path, mutation)
    prompt = (
        "Find private operator secret evidence in the ignored large corpus directory."
        if mutation == "unsafe_evidence_request"
        else route_prompt()
    )
    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=config_root,
            target_root=target_root,
            output_root=case_root / "out",
            user_request=prompt,
            context_index_policy_path=context_policy_path,
        )
    )
    report = result.report
    errors = object_list(report.get("validation_errors")) if isinstance(report, dict) else []
    passed = (
        isinstance(report, dict)
        and report.get("status") == case.get("expected_status")
        and any(item.get("id") == case.get("expected_error_id") for item in errors)
        and not object_list(report.get("evidence_refs"))
    )
    return {"case_id": case.get("case_id"), "surface": "retrieval_answer", "passed": passed, "report_summary": dict_value(report.get("summary")) if isinstance(report, dict) else {}, "validation_errors": errors}


def run_cases(config_root: Path, policy: dict[str, Any], output_path: Path) -> list[dict[str, Any]]:
    case_base = output_path.parent / f"phase260-disposable-{utc_timestamp()}"
    case_base.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for case in object_list(policy.get("required_cases")):
        case_root = case_base / str(case.get("case_id"))
        if case.get("surface") == "context_strategy_router":
            results.append(run_router_case(config_root, case_root, case))
        elif case.get("surface") == "retrieval_answer":
            results.append(run_retrieval_case(config_root, case_root, case))
        else:
            results.append({"case_id": case.get("case_id"), "surface": case.get("surface"), "passed": False})
    return results


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 384k Stale-Index Rejection",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Case count: `{summary.get('case_count')}`",
        f"- Passed case count: `{summary.get('passed_case_count')}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_384k_stale_index_rejection(config: LargeContext384kStaleIndexRejectionConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    precondition_errors = phase259_precondition_errors(config_root, policy) if config.validate_phase259_precondition else []
    case_results = run_cases(config_root, policy, output_path) if not policy_errors else []
    case_errors = [
        validation_error(f"cases.{item.get('case_id')}", "stale-index rejection case failed", source="cases")
        for item in case_results
        if item.get("passed") is not True
    ]
    errors = policy_errors + docs_errors + precondition_errors + case_errors
    status = LargeContext384kStaleIndexRejectionStatus.PASSED.value if not errors else LargeContext384kStaleIndexRejectionStatus.FAILED.value
    passed_count = sum(1 for item in case_results if item.get("passed") is True)
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
        "case_results": case_results,
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "target_estimated_project_tokens": policy.get("target_estimated_project_tokens"),
            "case_count": len(case_results),
            "passed_case_count": passed_count,
            "router_case_count": sum(1 for item in case_results if item.get("surface") == "context_strategy_router"),
            "retrieval_case_count": sum(1 for item in case_results if item.get("surface") == "retrieval_answer"),
            "phase261_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
