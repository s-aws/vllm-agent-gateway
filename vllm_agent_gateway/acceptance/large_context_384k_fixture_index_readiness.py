"""Phase 259 384k fixture and index readiness gate."""

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
    ContextIndexPrototypeConfig,
    run_context_index_prototype,
)
from vllm_agent_gateway.acceptance.corpus_index_safety_governance import (
    CorpusIndexSafetyGovernanceConfig,
    run_corpus_index_safety_governance,
)
from vllm_agent_gateway.acceptance.large_context_384k_usability_acceptance_contract import (
    LargeContext384kUsabilityAcceptanceContractConfig,
    validate_large_context_384k_usability_acceptance_contract,
)
from vllm_agent_gateway.acceptance.large_corpus_context_budget_inventory import (
    LargeCorpusContextBudgetInventoryConfig,
    run_large_corpus_context_budget_inventory,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_384k_fixture_index_readiness_policy"
EXPECTED_REPORT_KIND = "large_context_384k_fixture_index_readiness_report"
EXPECTED_PHASE = 259
EXPECTED_BACKLOG_ID = "P0-M6-259"
EXPECTED_MILESTONE_IDS = {"M6", "M16"}
TARGET_ESTIMATED_PROJECT_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_384k_fixture_index_readiness_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase259"
    / "phase259-large-context-384k-fixture-index-readiness-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase259"
    / "phase259-large-context-384k-fixture-index-readiness-report.md"
)


class LargeContext384kFixtureIndexReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext384kFixtureIndexReadinessConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    bootstrap_composed_gates: bool = True
    validate_phase258_precondition: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    text = str(value)
    if os.name == "nt" and len(text) > 7 and text.startswith("/mnt/") and text[5].isalpha() and text[6] == "/":
        return Path(f"{text[5].upper()}:/{text[7:]}")
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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        errors.append(validation_error("policy.phase", "phase must be 259"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6 and M16"))
    if policy.get("target_estimated_project_tokens") != TARGET_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.target_estimated_project_tokens", "target must be 384000"))
    if not dict_value(policy.get("phase258_precondition")):
        errors.append(validation_error("policy.phase258_precondition", "phase258_precondition is required"))
    gates = dict_value(policy.get("composed_gates"))
    for key in ("large_corpus_inventory", "corpus_index_safety", "context_index"):
        if not dict_value(gates.get(key)):
            errors.append(validation_error(f"policy.composed_gates.{key}", f"{key} gate is required"))
    safety = dict_value(policy.get("required_index_safety"))
    if safety.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.required_index_safety.source_text_retention", "source_text_retention must be metadata_only"))
    for key in (
        "store_source_text",
        "store_rejected_content",
        "raw_prompt_stuffing_allowed",
        "raw_384k_prompt_support_claim_allowed",
        "raw_1m_prompt_support_claim_allowed",
        "artifact_only_answers_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(validation_error(f"policy.required_index_safety.{key}", f"{key} must be false"))
    if len(string_list(policy.get("protected_fixture_roots"))) < 2:
        errors.append(validation_error("policy.protected_fixture_roots", "both protected Coinbase fixture roots are required"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE259 LARGE CONTEXT 384K FIXTURE INDEX READINESS PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 259"))
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


def tree_fingerprint(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {"root": str(root), "exists": False, "file_count": 0, "total_size": 0, "sha256": None}
    digest = hashlib.sha256()
    file_count = 0
    total_size = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative.startswith(".git/") or "/.git/" in relative:
            continue
        file_count += 1
        data = path.read_bytes()
        total_size += len(data)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return {
        "root": str(root),
        "exists": True,
        "file_count": file_count,
        "total_size": total_size,
        "sha256": digest.hexdigest(),
    }


def protected_fixture_fingerprints(config_root: Path, policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        raw_path: tree_fingerprint(resolve_path(config_root, raw_path))
        for raw_path in string_list(policy.get("protected_fixture_roots"))
    }


def run_phase258_contract(config_root: Path) -> dict[str, Any]:
    return validate_large_context_384k_usability_acceptance_contract(
        LargeContext384kUsabilityAcceptanceContractConfig(config_root=config_root)
    )


def run_composed_gates(config_root: Path) -> dict[str, dict[str, Any]]:
    phase214 = run_large_corpus_context_budget_inventory(
        LargeCorpusContextBudgetInventoryConfig(config_root=config_root)
    )
    phase216 = run_corpus_index_safety_governance(
        CorpusIndexSafetyGovernanceConfig(config_root=config_root)
    )
    phase217 = run_context_index_prototype(
        ContextIndexPrototypeConfig(config_root=config_root)
    )
    return {"phase214": phase214, "phase216": phase216, "phase217": phase217}


def load_composed_reports(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    reports: dict[str, dict[str, Any]] = {}
    gates = dict_value(policy.get("composed_gates"))
    paths = {
        "phase214": dict_value(gates.get("large_corpus_inventory")).get("report_path"),
        "phase216": dict_value(gates.get("corpus_index_safety")).get("report_path"),
        "phase217": dict_value(gates.get("context_index")).get("report_path"),
    }
    for key, raw_path in paths.items():
        if not isinstance(raw_path, str):
            errors.append(validation_error(f"{key}.report_path", "report_path must be a string", source=key))
            reports[key] = {}
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            errors.append(validation_error(f"{key}.report_missing", f"report missing: {raw_path}", source=key))
            reports[key] = {}
            continue
        reports[key] = read_json_object(path)
    return reports, errors


def validate_composed_reports(
    config_root: Path,
    policy: dict[str, Any],
    reports: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    gates = dict_value(policy.get("composed_gates"))
    phase214 = reports.get("phase214", {})
    phase216 = reports.get("phase216", {})
    phase217 = reports.get("phase217", {})
    phase214_summary = dict_value(phase214.get("summary"))
    phase216_summary = dict_value(phase216.get("summary"))
    phase217_summary = dict_value(phase217.get("summary"))
    phase214_gate = dict_value(gates.get("large_corpus_inventory"))
    phase216_gate = dict_value(gates.get("corpus_index_safety"))
    phase217_gate = dict_value(gates.get("context_index"))

    if phase214.get("status") != phase214_gate.get("required_status"):
        errors.append(validation_error("phase214.status", "Phase 214 inventory must pass", source="phase214"))
    if int(phase214_summary.get("estimated_token_count", 0)) < int(phase214_gate.get("minimum_estimated_token_count", 0)):
        errors.append(validation_error("phase214.estimated_token_count", "large corpus must meet 384k token target", source="phase214"))
    if phase214_summary.get("phase215_ready") is not phase214_gate.get("required_phase215_ready"):
        errors.append(validation_error("phase214.phase215_ready", "Phase 214 must be ready for Phase 215", source="phase214"))
    if phase214_summary.get("raw_1m_prompt_support_proven") is not False:
        errors.append(validation_error("phase214.raw_1m_prompt_support_proven", "raw 1M prompt support must remain unproven", source="phase214"))

    if phase216.get("status") != phase216_gate.get("required_status"):
        errors.append(validation_error("phase216.status", "Phase 216 safety governance must pass", source="phase216"))
    if int(phase216_summary.get("negative_control_count", 0)) < int(phase216_gate.get("minimum_negative_control_count", 0)):
        errors.append(validation_error("phase216.negative_control_count", "Phase 216 negative controls are incomplete", source="phase216"))
    if phase216_summary.get("negative_control_passed_count") != phase216_summary.get("negative_control_count"):
        errors.append(validation_error("phase216.negative_control_passed_count", "all Phase 216 negative controls must pass", source="phase216"))
    if phase216_summary.get("phase217_ready") is not phase216_gate.get("required_phase217_ready"):
        errors.append(validation_error("phase216.phase217_ready", "Phase 216 must be ready for Phase 217", source="phase216"))
    for key in ("retention_source_text_copy_allowed", "artifact_rejected_content_allowed", "chat_visible_rejected_content_allowed"):
        if phase216_summary.get(key) is not False:
            errors.append(validation_error(f"phase216.{key}", f"{key} must be false", source="phase216"))

    if phase217.get("status") != phase217_gate.get("required_status"):
        errors.append(validation_error("phase217.status", "Phase 217 context index must pass", source="phase217"))
    if int(phase217_summary.get("indexed_file_count", 0)) < int(phase217_gate.get("minimum_indexed_file_count", 0)):
        errors.append(validation_error("phase217.indexed_file_count", "indexed file count is too low", source="phase217"))
    if int(phase217_summary.get("chunk_count", 0)) < int(phase217_gate.get("minimum_chunk_count", 0)):
        errors.append(validation_error("phase217.chunk_count", "chunk count is too low", source="phase217"))
    if int(phase217_summary.get("estimated_indexed_token_count", 0)) < int(phase217_gate.get("minimum_estimated_indexed_token_count", 0)):
        errors.append(validation_error("phase217.estimated_indexed_token_count", "indexed token estimate must meet 384k target", source="phase217"))
    if phase217_summary.get("query_smoke_passed_count") != phase217_summary.get("query_smoke_case_count"):
        errors.append(validation_error("phase217.query_smoke_passed_count", "all query smokes must pass", source="phase217"))
    if phase217_summary.get("negative_control_passed_count") != phase217_summary.get("negative_control_count"):
        errors.append(validation_error("phase217.negative_control_passed_count", "all index negative controls must pass", source="phase217"))
    if phase217_summary.get("phase218_ready") is not phase217_gate.get("required_phase218_ready"):
        errors.append(validation_error("phase217.phase218_ready", "Phase 217 must be ready for Phase 218", source="phase217"))
    safety = dict_value(policy.get("required_index_safety"))
    for key in ("source_text_retention", "store_source_text", "store_rejected_content"):
        if phase217_summary.get(key) != safety.get(key):
            errors.append(validation_error(f"phase217.{key}", f"{key} must match policy", source="phase217"))
    index_path = phase217.get("index_artifact_path")
    if isinstance(index_path, str):
        artifact_path = resolve_path(config_root, index_path)
        if not artifact_path.is_file():
            errors.append(validation_error("phase217.index_artifact_path", "index artifact path must exist", source="phase217"))
    else:
        errors.append(validation_error("phase217.index_artifact_path", "index artifact path is required", source="phase217"))
    return errors


def fixture_mutation_errors(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for root, before_value in before.items():
        after_value = after.get(root, {})
        if before_value.get("exists") is not True:
            errors.append(validation_error(f"fixtures.{root}.missing", "protected fixture root is missing", source="fixtures"))
            continue
        if before_value != after_value:
            errors.append(validation_error(f"fixtures.{root}.changed", "protected fixture fingerprint changed", source="fixtures"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 384k Fixture And Index Readiness",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Corpus estimated tokens: `{summary.get('corpus_estimated_token_count')}`",
        f"- Indexed estimated tokens: `{summary.get('estimated_indexed_token_count')}`",
        f"- Indexed files: `{summary.get('indexed_file_count')}`",
        f"- Chunks: `{summary.get('chunk_count')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors if isinstance(item, dict))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_384k_fixture_index_readiness(
    config: LargeContext384kFixtureIndexReadinessConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    before_fixtures = protected_fixture_fingerprints(config_root, policy)
    phase258 = run_phase258_contract(config_root) if config.validate_phase258_precondition else {"status": "passed", "summary": {}}
    if config.bootstrap_composed_gates:
        reports = run_composed_gates(config_root)
        report_load_errors: list[dict[str, str]] = []
    else:
        reports, report_load_errors = load_composed_reports(config_root, policy)
    after_fixtures = protected_fixture_fingerprints(config_root, policy)
    fixture_errors = fixture_mutation_errors(before_fixtures, after_fixtures)
    composed_errors = validate_composed_reports(config_root, policy, reports)
    phase258_errors = []
    if phase258.get("status") != dict_value(policy.get("phase258_precondition")).get("required_status"):
        phase258_errors.append(validation_error("phase258.status", "Phase 258 acceptance contract must pass", source="phase258"))
    errors = policy_errors + docs_errors + report_load_errors + composed_errors + phase258_errors + fixture_errors

    phase214_summary = dict_value(reports.get("phase214", {}).get("summary"))
    phase216_summary = dict_value(reports.get("phase216", {}).get("summary"))
    phase217_summary = dict_value(reports.get("phase217", {}).get("summary"))
    status = (
        LargeContext384kFixtureIndexReadinessStatus.PASSED.value
        if not errors
        else LargeContext384kFixtureIndexReadinessStatus.FAILED.value
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
        "bootstrap_composed_gates": config.bootstrap_composed_gates,
        "docs": docs,
        "phase258_summary": dict_value(phase258.get("summary")),
        "composed_report_summaries": {
            "phase214": phase214_summary,
            "phase216": phase216_summary,
            "phase217": phase217_summary,
        },
        "protected_fixture_fingerprints_before": before_fixtures,
        "protected_fixture_fingerprints_after": after_fixtures,
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "target_estimated_project_tokens": policy.get("target_estimated_project_tokens"),
            "corpus_estimated_token_count": phase214_summary.get("estimated_token_count"),
            "estimated_indexed_token_count": phase217_summary.get("estimated_indexed_token_count"),
            "indexed_file_count": phase217_summary.get("indexed_file_count"),
            "chunk_count": phase217_summary.get("chunk_count"),
            "phase216_negative_control_count": phase216_summary.get("negative_control_count"),
            "phase217_negative_control_count": phase217_summary.get("negative_control_count"),
            "protected_fixture_root_count": len(before_fixtures),
            "phase260_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
