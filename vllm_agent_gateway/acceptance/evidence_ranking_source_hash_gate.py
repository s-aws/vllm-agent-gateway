"""Evidence ranking and source-hash gate for Phase 207."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.code_investigation.plan import (
    evidence_file_records,
    evidence_relevance,
    source_refs_from_records,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "evidence_ranking_source_hash_gate_policy"
EXPECTED_REPORT_KIND = "evidence_ranking_source_hash_gate_report"
EXPECTED_PHASE = 207
EXPECTED_BACKLOG_ID = "P0-M4-207"
EXPECTED_MILESTONE_ID = "M4"
DEFAULT_POLICY_PATH = Path("runtime") / "evidence_ranking_source_hash_gate_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase207" / "phase207-evidence-ranking-source-hash-gate-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase207" / "phase207-evidence-ranking-source-hash-gate-report.md"
TIER_ORDER = {"direct": 0, "strong": 1, "supporting": 2, "weak": 3, "irrelevant": 4}


class EvidenceSourceHashStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class EvidenceRankingSourceHashGateConfig:
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


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def source_line_text(path: Path, line_number: int) -> str | None:
    if line_number < 1:
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_number > len(lines):
        return None
    return lines[line_number - 1]


def validate_source_reports(config_root: Path, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    phase206_path = resolve_path(config_root, str(policy.get("phase206_audit_pack_report_path", "")))
    phase182_path = resolve_path(config_root, str(policy.get("phase182_evidence_ranking_report_path", "")))
    for label, path in (("phase206", phase206_path), ("phase182", phase182_path)):
        if not path.is_file():
            errors.append(f"{label} source report missing at {path}")
            continue
        report = read_json_object(path)
        if report.get("status") != "passed":
            errors.append(f"{label} source report status must be passed")
        if label == "phase206":
            if report.get("phase") != 206:
                errors.append("phase206 source report phase must be 206")
            if dict_value(report.get("summary")).get("phase207_ready") is not True:
                errors.append("phase206 source report must have summary.phase207_ready=true")
        if label == "phase182":
            if report.get("phase") != "182":
                errors.append("phase182 source report phase must be '182'")
            if report.get("live") is not True:
                errors.append("phase182 source report must be live")
            live_case_count = int_value(report.get("live_case_count"))
            live_passed_case_count = int_value(report.get("live_passed_case_count"))
            minimum_live_case_count = int_value(policy.get("phase182_minimum_live_case_count"), 4)
            if live_case_count < minimum_live_case_count:
                errors.append("phase182 source report live_case_count below policy.phase182_minimum_live_case_count")
            if live_case_count != live_passed_case_count:
                errors.append("phase182 source report live_case_count must equal live_passed_case_count")
            live_cases = object_list(report.get("live_cases"))
            if len(live_cases) != live_case_count:
                errors.append("phase182 source report live_cases length must equal live_case_count")
            for live_case in live_cases:
                if live_case.get("status") != "passed":
                    errors.append("phase182 source report live_cases must all be passed")
                if object_list(live_case.get("errors")) or string_list(live_case.get("errors")):
                    errors.append("phase182 source report live_cases must not contain errors")
            live_roots = {str(item.get("target_root")) for item in live_cases if isinstance(item.get("target_root"), str)}
            for required_root in string_list(policy.get("phase182_required_target_roots")):
                if required_root not in live_roots:
                    errors.append(f"phase182 source report missing live target_root {required_root}")
        if isinstance(report.get("errors"), list) and report.get("errors"):
            errors.append(f"{label} source report must not contain errors")
    return errors


def phase206_audit_case_map(config_root: Path, policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    report = read_json_object(resolve_path(config_root, str(policy.get("phase206_audit_pack_report_path", ""))))
    return {
        str(item.get("case_id")): item
        for item in object_list(report.get("audit_cases"))
        if isinstance(item.get("case_id"), str)
    }


def audit_case_alignment_errors(case: dict[str, Any], audit_case: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or "<missing>")
    if case.get("category") != audit_case.get("category"):
        errors.append(f"case {case_id} category must match Phase 206 audit case category")
    if policy.get("target_root") != audit_case.get("target_root"):
        errors.append(f"case {case_id} target_root must match Phase 206 audit case target_root")
    baseline = dict_value(audit_case.get("blind_baseline"))
    tier_definitions = dict_value(baseline.get("evidence_tier_definitions"))
    missing_tiers = {"direct", "strong", "supporting", "weak"} - set(tier_definitions)
    if missing_tiers:
        errors.append(f"case {case_id} Phase 206 blind baseline missing tier definitions: {sorted(missing_tiers)}")
    evidence_text = " ".join(
        string_list(baseline.get("ideal_answer_shape"))
        + string_list(baseline.get("must_have_evidence"))
        + string_list(baseline.get("red_flags"))
    ).lower()
    if "line" not in evidence_text:
        errors.append(f"case {case_id} Phase 206 blind baseline must require line-level evidence")
    if "path" not in evidence_text and "file" not in evidence_text:
        errors.append(f"case {case_id} Phase 206 blind baseline must require file/path evidence")
    required_terms = string_list(case.get("phase206_required_terms"))
    if not required_terms:
        errors.append(f"case {case_id} phase206_required_terms must be non-empty")
    phase206_text = " ".join(
        [
            str(audit_case.get("prompt") or ""),
            *string_list(baseline.get("ideal_answer_shape")),
            *string_list(baseline.get("must_have_evidence")),
            *string_list(baseline.get("red_flags")),
        ]
    ).lower()
    phase207_text = " ".join(
        [
            *string_list(case.get("direct_paths")),
            *string_list(case.get("supporting_paths")),
            *[
                str(match.get("query") or "")
                for match in object_list(case.get("matches"))
                if isinstance(match.get("query"), str)
            ],
        ]
    ).lower()
    for term in required_terms:
        lowered = term.lower()
        if lowered not in phase206_text:
            errors.append(f"case {case_id} phase206_required_terms term {term!r} missing from Phase 206 baseline")
        if lowered not in phase207_text:
            errors.append(f"case {case_id} phase206_required_terms term {term!r} missing from Phase 207 evidence")
    return errors


def validate_policy(policy: dict[str, Any], *, config_root: Path) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 207")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    required_tiers = set(string_list(policy.get("required_evidence_tiers")))
    if required_tiers != {"direct", "strong", "supporting", "weak"}:
        errors.append("policy.required_evidence_tiers must be direct, strong, supporting, and weak")
    cases = object_list(policy.get("cases"))
    if len(cases) < int_value(policy.get("minimum_case_count"), 4):
        errors.append("policy.cases below policy.minimum_case_count")
    target_root = policy.get("target_root")
    if not isinstance(target_root, str) or not Path(target_root).is_dir():
        errors.append("policy.target_root must be an existing directory")
    errors.extend(validate_source_reports(config_root, policy))
    try:
        audit_cases = phase206_audit_case_map(config_root, policy)
    except Exception as exc:  # noqa: BLE001
        audit_cases = {}
        errors.append(f"phase206 audit case lookup failed: {type(exc).__name__}: {exc}")
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id") or "<missing>")
        if case_id in seen:
            errors.append(f"case {case_id} duplicates an earlier case_id")
        seen.add(case_id)
        audit_case = audit_cases.get(str(case.get("audit_case_id") or ""))
        if audit_case is None:
            errors.append(f"case {case_id} audit_case_id must exist in Phase 206 report")
        else:
            errors.extend(audit_case_alignment_errors(case, audit_case, policy))
        if not string_list(case.get("expected_top_tiers")):
            errors.append(f"case {case_id} expected_top_tiers must be non-empty")
        if not string_list(case.get("direct_paths")):
            errors.append(f"case {case_id} direct_paths must be non-empty")
        if not object_list(case.get("matches")):
            errors.append(f"case {case_id} matches must be non-empty")
        for path_key in ("direct_paths", "supporting_paths"):
            for rel_path in string_list(case.get(path_key)):
                if isinstance(target_root, str) and not (Path(target_root) / rel_path).is_file():
                    errors.append(f"case {case_id} {path_key} missing source file {rel_path}")
    negative_controls = object_list(policy.get("negative_controls"))
    if len(negative_controls) < int_value(policy.get("minimum_negative_control_count"), 2):
        errors.append("policy.negative_controls below policy.minimum_negative_control_count")
    seen_controls: set[str] = set()
    for control in negative_controls:
        control_id = str(control.get("control_id") or "<missing>")
        if control_id in seen_controls:
            errors.append(f"negative control {control_id} duplicates an earlier control_id")
        seen_controls.add(control_id)
        if not isinstance(control.get("reason"), str) or not control["reason"].strip():
            errors.append(f"negative control {control_id} reason must be non-empty")
        if not string_list(control.get("direct_paths")):
            errors.append(f"negative control {control_id} direct_paths must be non-empty")
        if not object_list(control.get("matches")):
            errors.append(f"negative control {control_id} matches must be non-empty")
        for path_key in ("direct_paths", "supporting_paths"):
            for rel_path in string_list(control.get(path_key)):
                if isinstance(target_root, str) and not (Path(target_root) / rel_path).is_file():
                    errors.append(f"negative control {control_id} {path_key} missing source file {rel_path}")
        for hint in object_list(control.get("hints")):
            hint_path = hint.get("path")
            if not isinstance(hint_path, str) or not hint_path:
                errors.append(f"negative control {control_id} hint missing path")
            elif isinstance(target_root, str) and not (Path(target_root) / hint_path).is_file():
                errors.append(f"negative control {control_id} hint missing source file {hint_path}")
    return errors


def source_proofs_for_refs(target_root: Path, refs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    proofs: list[dict[str, Any]] = []
    errors: list[str] = []
    for ref in refs:
        rel_path = ref.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            errors.append("source ref missing path")
            continue
        path = target_root / rel_path
        proof: dict[str, Any] = {
            "path": rel_path,
            "line": ref.get("line") if isinstance(ref.get("line"), int) else None,
            "query": ref.get("query") if isinstance(ref.get("query"), str) else None,
            "relevance": dict_value(ref.get("relevance")),
            "exists": path.is_file(),
        }
        if path.is_file():
            proof["sha256"] = file_sha256(path)
            line_number = proof["line"]
            query = proof["query"]
            if not isinstance(line_number, int) or line_number < 1:
                errors.append(f"source ref {rel_path} requires a positive line number")
            elif not isinstance(query, str) or not query.strip():
                errors.append(f"source ref {rel_path}:{line_number} requires a non-empty query")
            else:
                line_text = source_line_text(path, line_number)
                proof["line_exists"] = line_text is not None
                if line_text is None:
                    errors.append(f"source ref {rel_path}:{line_number} line does not exist")
                else:
                    proof["line_text"] = line_text.strip()
                    proof["line_sha256"] = text_sha256(line_text)
                    proof["line_contains_query"] = query.lower() in line_text.lower()
                    if proof["line_contains_query"] is not True:
                        errors.append(f"source ref {rel_path}:{line_number} does not contain query {query!r}")
        proofs.append(proof)
        if not proof["exists"]:
            errors.append(f"source ref {rel_path} does not exist")
        if not is_sha256(proof.get("sha256")):
            errors.append(f"source ref {rel_path} missing sha256")
        if proof.get("line_sha256") is not None and not is_sha256(proof.get("line_sha256")):
            errors.append(f"source ref {rel_path}:{proof.get('line')} missing line_sha256")
    return proofs, errors


def tier_rank(tier: str) -> int:
    return TIER_ORDER.get(tier, 99)


def top_evidence_errors(case: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or "<missing>")
    if not records:
        return [f"case {case_id} produced no evidence records"]
    top = records[0]
    top_tier = str(dict_value(top.get("relevance")).get("tier") or "")
    if top_tier not in string_list(case.get("expected_top_tiers")):
        errors.append(f"case {case_id} top evidence tier {top_tier!r} not in expected_top_tiers")
    direct_paths = set(string_list(case.get("direct_paths")))
    if str(top.get("path")) not in direct_paths:
        errors.append(f"case {case_id} top evidence path {top.get('path')!r} is not a direct path")
    ranks = [tier_rank(str(dict_value(record.get("relevance")).get("tier") or "")) for record in records]
    if ranks != sorted(ranks):
        errors.append(f"case {case_id} evidence tiers are not ordered strongest to weakest")
    return errors


def case_report(policy: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    target_root = Path(str(policy.get("target_root")))
    paths = string_list(case.get("direct_paths")) + string_list(case.get("supporting_paths"))
    records = evidence_file_records(paths, object_list(case.get("hints")), object_list(case.get("matches")))
    refs = source_refs_from_records(records)
    source_proofs, proof_errors = source_proofs_for_refs(target_root, refs)
    errors = top_evidence_errors(case, records) + proof_errors
    top = records[0] if records else {}
    return {
        "case_id": case.get("case_id"),
        "audit_case_id": case.get("audit_case_id"),
        "category": case.get("category"),
        "status": EvidenceSourceHashStatus.PASSED.value if not errors else EvidenceSourceHashStatus.FAILED.value,
        "top_path": top.get("path"),
        "top_relevance": top.get("relevance") if isinstance(top.get("relevance"), dict) else evidence_relevance(top),
        "evidence_records": records,
        "source_refs": refs,
        "source_proofs": source_proofs,
        "source_hash_count": len([item for item in source_proofs if is_sha256(item.get("sha256"))]),
        "errors": errors,
    }


def negative_control_report(policy: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    control_case = dict(control)
    control_case["case_id"] = control.get("control_id")
    control_case["expected_top_tiers"] = ["direct", "strong"]
    report = case_report(policy, control_case)
    errors = string_list(report.get("errors"))
    direct_paths = set(string_list(control.get("direct_paths")))
    supporting_paths = set(string_list(control.get("supporting_paths")))
    direct_scores = [
        int_value(dict_value(record.get("relevance")).get("score"))
        for record in object_list(report.get("evidence_records"))
        if str(record.get("path")) in direct_paths
    ]
    supporting_scores = [
        int_value(dict_value(record.get("relevance")).get("score"))
        for record in object_list(report.get("evidence_records"))
        if str(record.get("path")) in supporting_paths
    ]
    if not direct_scores:
        errors.append(f"negative control {control.get('control_id')} produced no direct evidence record")
    if supporting_scores and direct_scores and max(supporting_scores) >= max(direct_scores):
        errors.append(f"negative control {control.get('control_id')} supporting or hinted evidence outranked direct evidence")
    report["control_id"] = control.get("control_id")
    report["reason"] = control.get("reason")
    report["status"] = EvidenceSourceHashStatus.PASSED.value if not errors else EvidenceSourceHashStatus.FAILED.value
    report["errors"] = errors
    return report


def build_summary(
    policy: dict[str, Any],
    case_reports: list[dict[str, Any]],
    negative_control_reports: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    failed = [item for item in case_reports if item.get("status") != EvidenceSourceHashStatus.PASSED.value]
    failed_negative_controls = [
        item for item in negative_control_reports if item.get("status") != EvidenceSourceHashStatus.PASSED.value
    ]
    hash_count = sum(int_value(item.get("source_hash_count")) for item in case_reports)
    return {
        "case_count": len(case_reports),
        "passed_case_count": len(case_reports) - len(failed),
        "failed_case_count": len(failed),
        "negative_control_count": len(negative_control_reports),
        "passed_negative_control_count": len(negative_control_reports) - len(failed_negative_controls),
        "failed_negative_control_count": len(failed_negative_controls),
        "source_hash_count": hash_count,
        "minimum_source_hash_count": policy.get("minimum_source_hash_count"),
        "error_count": len(errors),
        "phase208_ready": (
            not errors
            and not failed
            and not failed_negative_controls
            and len(negative_control_reports) >= int_value(policy.get("minimum_negative_control_count"), 2)
            and hash_count >= int_value(policy.get("minimum_source_hash_count"), 4)
        ),
    }


def validate_evidence_ranking_source_hash_gate(config: EvidenceRankingSourceHashGateConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    errors: list[str] = []
    case_reports: list[dict[str, Any]] = []
    negative_control_reports: list[dict[str, Any]] = []
    policy: dict[str, Any] = {}
    try:
        policy = read_json_object(policy_path)
        errors.extend(validate_policy(policy, config_root=config_root))
        if not errors:
            case_reports = [case_report(policy, case) for case in object_list(policy.get("cases"))]
            negative_control_reports = [
                negative_control_report(policy, control) for control in object_list(policy.get("negative_controls"))
            ]
            errors.extend(
                error
                for item in case_reports
                for error in string_list(item.get("errors"))
                if item.get("status") != EvidenceSourceHashStatus.PASSED.value
            )
            errors.extend(
                error
                for item in negative_control_reports
                for error in string_list(item.get("errors"))
                if item.get("status") != EvidenceSourceHashStatus.PASSED.value
            )
            hash_count = sum(int_value(item.get("source_hash_count")) for item in case_reports)
            if hash_count < int_value(policy.get("minimum_source_hash_count"), 4):
                errors.append("source_hash_count below policy.minimum_source_hash_count")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"load failed: {type(exc).__name__}: {exc}")
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": EvidenceSourceHashStatus.PASSED.value if not errors else EvidenceSourceHashStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path),
        "summary": build_summary(policy, case_reports, negative_control_reports, errors),
        "cases": case_reports,
        "negative_controls": negative_control_reports,
        "errors": errors,
    }
    write_json(output_path, report)
    write_text(markdown_output_path, markdown_report(report))
    report["report_path"] = str(output_path.resolve())
    report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    return report


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Evidence Ranking Source Hash Gate",
        "",
        f"- Status: {report.get('status')}",
        f"- Cases: {summary.get('passed_case_count')} passed / {summary.get('case_count')} total",
        f"- Negative controls: {summary.get('passed_negative_control_count')} passed / {summary.get('negative_control_count')} total",
        f"- Source hashes: {summary.get('source_hash_count')}",
        f"- Phase 208 ready: {summary.get('phase208_ready')}",
        "",
        "## Cases",
        "",
        "| Case | Category | Status | Top Path | Top Tier | Hashes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in object_list(report.get("cases")):
        relevance = dict_value(item.get("top_relevance"))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("case_id")),
                    str(item.get("category")),
                    str(item.get("status")),
                    str(item.get("top_path")),
                    str(relevance.get("tier")),
                    str(item.get("source_hash_count")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Negative Controls",
            "",
            "| Control | Status | Top Path | Top Tier | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in object_list(report.get("negative_controls")):
        relevance = dict_value(item.get("top_relevance"))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("control_id")),
                    str(item.get("status")),
                    str(item.get("top_path")),
                    str(relevance.get("tier")),
                    str(item.get("reason")),
                ]
            )
            + " |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in string_list(report.get("errors")):
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"
