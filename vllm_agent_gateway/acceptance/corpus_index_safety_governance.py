"""Phase 216 corpus and index safety governance gate."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "corpus_index_safety_governance_policy"
EXPECTED_REPORT_KIND = "corpus_index_safety_governance_report"
EXPECTED_PHASE = 216
EXPECTED_BACKLOG_ID = "P0-M16-216"
EXPECTED_MILESTONE_IDS = {"M16"}
DEFAULT_POLICY_PATH = Path("runtime") / "corpus_index_safety_governance_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase216" / "phase216-corpus-index-safety-governance-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase216" / "phase216-corpus-index-safety-governance-report.md"


class RootStatus(str, Enum):
    APPROVED = "approved"
    UNAPPROVED = "unapproved"
    TRAVERSAL = "traversal"
    SYMLINK_ESCAPE = "symlink_escape"


class AdmissionDecision(str, Enum):
    ADMIT = "admit"
    REJECT = "reject"


class RejectionReason(str, Enum):
    UNAPPROVED_ROOT = "unapproved_root"
    PATH_TRAVERSAL = "path_traversal"
    SYMLINK_ESCAPE = "symlink_escape"
    IGNORED_PATH = "ignored_path"
    PRIVATE_PATH = "private_path"
    BINARY_FILE = "binary_file"
    SECRET_LIKE_CONTENT = "secret_like_content"
    GENERATED_ARTIFACT = "generated_artifact"
    STALE_SOURCE_HASH = "stale_source_hash"
    CHANGED_IGNORE_POLICY_HASH = "changed_ignore_policy_hash"
    CHANGED_SAFETY_POLICY_HASH = "changed_safety_policy_hash"
    CHANGED_CONTEXT_STRATEGY_ID = "changed_context_strategy_id"


class RetentionMode(str, Enum):
    METADATA_ONLY = "metadata_only"
    REJECTED_NO_CONTENT = "rejected_no_content"


REQUIRED_RULES = {
    "reject_unapproved_roots",
    "reject_path_traversal",
    "reject_symlink_escape",
    "reject_ignored_paths",
    "reject_private_paths",
    "reject_binary_text_content",
    "reject_secret_like_content",
    "reject_generated_runtime_artifacts",
    "reject_stale_source_hashes",
    "reject_changed_ignore_policy_hash",
    "reject_changed_safety_policy_hash",
    "reject_changed_context_strategy_id",
    "preserve_source_hashes_for_admitted_sources",
    "redact_secret_like_metadata",
    "no_rejected_content_in_chat_visible_output",
    "no_rejected_content_in_durable_artifacts",
    "no_durable_index_before_phase217",
    "no_retrieval_backed_chat_before_phase218",
}
REQUIRED_IGNORE_SOURCES = {".gitignore", ".cgcignore", "policy_deny_patterns"}
REQUIRED_MANIFEST_FIELDS = {
    "manifest_schema_version",
    "target_root",
    "allowed_root_id",
    "ignore_policy_fingerprint",
    "source_path",
    "source_sha256",
    "chunk_id",
    "chunk_sha256",
    "model_id",
    "context_strategy_id",
    "created_at",
    "source_mtime_ns",
    "source_size",
    "freshness_status",
    "admission_decision",
    "rejection_reasons",
}
REQUIRED_NEGATIVE_CASES = {
    "P216-SAFE-001",
    "P216-SAFE-002",
    "P216-SAFE-003",
    "P216-SAFE-004",
    "P216-SAFE-005",
    "P216-SAFE-006",
    "P216-SAFE-007",
    "P216-SAFE-008",
    "P216-SAFE-009",
    "P216-SAFE-010",
    "P216-SAFE-011",
    "P216-SAFE-012",
    "P216-SAFE-013",
}
REQUIRED_OUT_OF_SCOPE = {
    "durable_index_implementation",
    "embedding_model_selection",
    "retrieval_backed_chat_integration",
    "artifact_paging_implementation",
    "raw_1m_context_benchmark",
    "protected_fixture_mutation",
}


@dataclass(frozen=True)
class CorpusIndexSafetyGovernanceConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True
    generate_fixture: bool = True


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 216"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M16"))
    precondition = dict_value(policy.get("phase215_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition.get(key)).strip():
            errors.append(validation_error(f"policy.phase215_precondition.{key}", f"{key} must be a non-empty string"))
    for key in (
        "required_phase216_ready",
        "retrieval_index_implementation_in_scope_must_be",
        "retrieval_backed_chat_integration_in_scope_must_be",
    ):
        if not isinstance(precondition.get(key), bool):
            errors.append(validation_error(f"policy.phase215_precondition.{key}", f"{key} must be boolean"))
    fixture = dict_value(policy.get("negative_control_fixture"))
    for key in ("root", "profile", "secret_fixture_value"):
        if not isinstance(fixture.get(key), str) or not str(fixture.get(key)).strip():
            errors.append(validation_error(f"policy.negative_control_fixture.{key}", f"{key} must be a non-empty string"))
    if not string_list(fixture.get("allowed_source_paths")):
        errors.append(validation_error("policy.negative_control_fixture.allowed_source_paths", "allowed_source_paths must not be empty"))
    if not string_list(fixture.get("stale_source_paths")):
        errors.append(validation_error("policy.negative_control_fixture.stale_source_paths", "stale_source_paths must not be empty"))
    root_policy = dict_value(policy.get("root_policy"))
    if not string_list(root_policy.get("allowed_roots")):
        errors.append(validation_error("policy.root_policy.allowed_roots", "allowed_roots must not be empty"))
    if not string_list(root_policy.get("denied_root_values")):
        errors.append(validation_error("policy.root_policy.denied_root_values", "denied_root_values must not be empty"))
    if not isinstance(root_policy.get("unapproved_root_negative_control"), str):
        errors.append(
            validation_error("policy.root_policy.unapproved_root_negative_control", "unapproved root negative control must be a string")
        )
    ignore_policy = dict_value(policy.get("ignore_policy"))
    if set(string_list(ignore_policy.get("required_ignore_sources"))) != REQUIRED_IGNORE_SOURCES:
        errors.append(validation_error("policy.ignore_policy.required_ignore_sources", "required ignore sources must match policy"))
    if not string_list(ignore_policy.get("policy_deny_patterns")):
        errors.append(validation_error("policy.ignore_policy.policy_deny_patterns", "policy_deny_patterns must not be empty"))
    if ignore_policy.get("must_apply_before_candidate_admission") is not True:
        errors.append(
            validation_error(
                "policy.ignore_policy.must_apply_before_candidate_admission",
                "ignore policy must apply before candidate admission",
            )
        )
    missing_rules = sorted(REQUIRED_RULES - set(string_list(policy.get("safety_rules"))))
    if missing_rules:
        errors.append(validation_error("policy.safety_rules", f"missing safety rules: {missing_rules}"))
    if not object_list(policy.get("secret_like_patterns")):
        errors.append(validation_error("policy.secret_like_patterns", "secret_like_patterns must not be empty"))
    for index, item in enumerate(object_list(policy.get("secret_like_patterns"))):
        for key in ("pattern_id", "contains", "redaction"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(validation_error(f"policy.secret_like_patterns[{index}].{key}", f"{key} must be non-empty"))
    missing_manifest = sorted(REQUIRED_MANIFEST_FIELDS - set(string_list(policy.get("index_manifest_requirements"))))
    if missing_manifest:
        errors.append(validation_error("policy.index_manifest_requirements", f"missing manifest fields: {missing_manifest}"))
    retention = dict_value(policy.get("retention_policy"))
    if retention.get("source_text_copy_allowed") is not False:
        errors.append(validation_error("policy.retention_policy.source_text_copy_allowed", "source_text_copy_allowed must be false"))
    if retention.get("chat_visible_rejected_content_allowed") is not False:
        errors.append(validation_error("policy.retention_policy.chat_visible_rejected_content_allowed", "chat leakage must be false"))
    if retention.get("artifact_rejected_content_allowed") is not False:
        errors.append(validation_error("policy.retention_policy.artifact_rejected_content_allowed", "artifact leakage must be false"))
    if retention.get("delete_index_on_source_removal") is not True:
        errors.append(validation_error("policy.retention_policy.delete_index_on_source_removal", "source removal must delete/invalidate index"))
    if retention.get("stale_index_status") != "rejected_until_refreshed":
        errors.append(validation_error("policy.retention_policy.stale_index_status", "stale index status must reject until refreshed"))
    if retention.get("max_reported_excerpt_chars") != 0:
        errors.append(validation_error("policy.retention_policy.max_reported_excerpt_chars", "reports must not include source excerpts"))
    case_ids = {str(item.get("case_id")) for item in object_list(policy.get("negative_controls"))}
    missing_cases = sorted(REQUIRED_NEGATIVE_CASES - case_ids)
    if missing_cases:
        errors.append(validation_error("policy.negative_controls", f"missing negative controls: {missing_cases}"))
    for case in object_list(policy.get("negative_controls")):
        if case.get("expected_decision") not in {item.value for item in AdmissionDecision}:
            errors.append(validation_error(f"policy.negative_controls.{case.get('case_id')}", "expected_decision is invalid"))
        if case.get("expected_decision") == AdmissionDecision.REJECT.value and not string_list(case.get("expected_reasons")):
            errors.append(validation_error(f"policy.negative_controls.{case.get('case_id')}.expected_reasons", "reject cases need reasons"))
    missing_out_of_scope = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing_out_of_scope:
        errors.append(validation_error("policy.out_of_scope", f"missing out-of-scope boundaries: {missing_out_of_scope}"))
    if policy.get("acceptance_marker") != "PHASE216 CORPUS INDEX SAFETY GOVERNANCE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 216"))
    return errors


def load_phase215_report(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    precondition = dict_value(policy.get("phase215_precondition"))
    raw_path = precondition.get("report_path")
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error("phase215_report.missing", "Phase 215 report is required", source="phase215")]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [
            validation_error(
                "phase215_report.malformed",
                f"Phase 215 report is malformed: {type(exc).__name__}: {exc}",
                source="phase215",
            )
        ]


def validate_phase215_precondition(policy: dict[str, Any], phase215_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not phase215_report:
        return errors
    precondition = dict_value(policy.get("phase215_precondition"))
    summary = dict_value(phase215_report.get("summary"))
    if phase215_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase215_report.status", "Phase 215 report status must be passed", source="phase215"))
    if summary.get("phase216_ready") is not precondition.get("required_phase216_ready"):
        errors.append(validation_error("phase215_report.phase216_ready", "Phase 215 report must mark phase216_ready", source="phase215"))
    if summary.get("retrieval_index_implementation_in_scope") is not precondition.get(
        "retrieval_index_implementation_in_scope_must_be"
    ):
        errors.append(
            validation_error(
                "phase215_report.retrieval_index_implementation_in_scope",
                "Phase 215 must not put retrieval index implementation in scope",
                source="phase215",
            )
        )
    if summary.get("retrieval_backed_chat_integration_in_scope") is not precondition.get(
        "retrieval_backed_chat_integration_in_scope_must_be"
    ):
        errors.append(
            validation_error(
                "phase215_report.retrieval_backed_chat_integration_in_scope",
                "Phase 215 must not put retrieval-backed chat in scope",
                source="phase215",
            )
        )
    return errors


def generate_negative_control_fixture(config_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    fixture = dict_value(policy.get("negative_control_fixture"))
    root = resolve_path(config_root, str(fixture.get("root"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    write_text(root / ".gitignore", "ignored/\nruntime-state/\n*.bin\n*.secret\n")
    write_text(root / ".cgcignore", "private/\n*.secret\n")
    write_text(root / "src" / "public_service.py", "def public_service():\n    return 'public evidence only'\n")
    write_text(root / "docs" / "public_notes.md", "# Public Notes\n\nThis file is safe for metadata-only indexing.\n")
    write_text(root / "ignored" / "hidden_service.py", "def hidden():\n    return 'ignored content'\n")
    write_text(root / "private" / "operator_notes.md", "private notes must never be indexed\n")
    write_text(root / "config" / "credential.secret", f"SECRET={fixture.get('secret_fixture_value')}\n")
    write_text(root / "runtime-state" / "generated-artifact.json", json.dumps({"artifact": "generated"}))
    write_text(root / "src" / "stale_source.py", "def stale_source():\n    return 'changed after manifest'\n")
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "blob.bin").write_bytes(bytes(range(64)) * 2)
    escape_target = root.parent / "phase216-escaped-secret.txt"
    write_text(escape_target, "outside root\n")
    link = root / "links" / "escaped-secret.txt"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(escape_target)
        symlink_created = True
    except OSError:
        symlink_created = False
        write_text(link, "symlink unavailable fallback\n")
    return {
        "root": str(root),
        "symlink_created": symlink_created,
        "escape_target": str(escape_target),
    }


def ignore_patterns(root: Path, policy: dict[str, Any]) -> list[str]:
    patterns = string_list(dict_value(policy.get("ignore_policy")).get("policy_deny_patterns"))
    for name in (".gitignore", ".cgcignore"):
        path = root / name
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return sorted(set(patterns))


def path_is_ignored(relative_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        normalized = pattern.strip("/")
        if pattern.endswith("/") and (relative_path == normalized or relative_path.startswith(normalized + "/")):
            return True
        if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(Path(relative_path).name, pattern):
            return True
        if normalized and (relative_path == normalized or relative_path.startswith(normalized + "/")):
            return True
    return False


def is_binary_file(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:2048]
    except OSError:
        return False
    if b"\0" in chunk:
        return True
    if not chunk:
        return False
    textish = sum(1 for byte in chunk if byte in b"\n\r\t" or 32 <= byte <= 126)
    return textish / len(chunk) < 0.75


def contains_secret_like_content(path: Path, policy: dict[str, Any]) -> bool:
    if is_binary_file(path):
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(str(item.get("contains")) in text for item in object_list(policy.get("secret_like_patterns")))


def fingerprint_ignore_policy(root: Path, policy: dict[str, Any]) -> str:
    payload = {
        "patterns": ignore_patterns(root, policy),
        "sources": string_list(dict_value(policy.get("ignore_policy")).get("required_ignore_sources")),
    }
    return sha256_text(json.dumps(payload, sort_keys=True))


def metadata_for_candidate(root: Path, relative_path: str, policy: dict[str, Any]) -> dict[str, Any]:
    path = root / relative_path
    stat = path.stat() if path.exists() and not path.is_symlink() else None
    source_hash = sha256_file(path) if path.is_file() and not path.is_symlink() else None
    chunk_seed = f"{relative_path}:{source_hash or 'none'}"
    return {
        "manifest_schema_version": SCHEMA_VERSION,
        "target_root": str(root),
        "allowed_root_id": "phase216_negative_control_fixture",
        "ignore_policy_fingerprint": fingerprint_ignore_policy(root, policy),
        "safety_policy_fingerprint": sha256_text(json.dumps(policy, sort_keys=True)),
        "source_path": relative_path,
        "source_sha256": source_hash,
        "chunk_id": f"chunk:{sha256_text(chunk_seed)[:16]}",
        "chunk_sha256": sha256_text(chunk_seed),
        "model_id": "Qwen3-Coder-30B-A3B-Instruct",
        "context_strategy_id": "retrieval",
        "created_at": utc_timestamp(),
        "source_mtime_ns": stat.st_mtime_ns if stat else None,
        "source_size": stat.st_size if stat else None,
        "freshness_status": "fresh",
        "retention_mode": RetentionMode.METADATA_ONLY.value,
    }


def candidate_path(root: Path, raw_path: str) -> tuple[Path, str, list[str]]:
    if ".." in Path(raw_path).parts:
        return root / raw_path, raw_path, [RejectionReason.PATH_TRAVERSAL.value]
    path = Path(raw_path)
    if path.is_absolute():
        return path, raw_path, []
    return root / path, raw_path, []


def evaluate_candidate(
    *,
    root: Path,
    raw_path: str,
    policy: dict[str, Any],
    metadata_mutation: str | None = None,
) -> dict[str, Any]:
    path, relative_path, reasons = candidate_path(root, raw_path)
    if path.is_absolute():
        try:
            resolved_candidate = path.resolve(strict=False)
        except OSError:
            resolved_candidate = path
        if resolved_candidate != root and root not in resolved_candidate.parents:
            reasons.append(RejectionReason.UNAPPROVED_ROOT.value)
    if path.is_symlink():
        try:
            resolved = path.resolve(strict=True)
            if root not in resolved.parents and resolved != root:
                reasons.append(RejectionReason.SYMLINK_ESCAPE.value)
        except OSError:
            reasons.append(RejectionReason.SYMLINK_ESCAPE.value)
    exists = path.exists()
    if exists and path.is_file() and not path.is_symlink():
        relative_for_policy = path.relative_to(root).as_posix() if root in path.resolve().parents or path.resolve() == root else relative_path
        patterns = ignore_patterns(root, policy)
        if path_is_ignored(relative_for_policy, patterns):
            reasons.append(RejectionReason.IGNORED_PATH.value)
        if relative_for_policy.startswith("private/"):
            reasons.append(RejectionReason.PRIVATE_PATH.value)
        if relative_for_policy.startswith("runtime-state/"):
            reasons.append(RejectionReason.GENERATED_ARTIFACT.value)
        if is_binary_file(path):
            reasons.append(RejectionReason.BINARY_FILE.value)
        if contains_secret_like_content(path, policy):
            reasons.append(RejectionReason.SECRET_LIKE_CONTENT.value)
    metadata = metadata_for_candidate(root, relative_path, policy) if exists and not path.is_symlink() and path.is_file() else {}
    if relative_path in string_list(dict_value(policy.get("negative_control_fixture")).get("stale_source_paths")):
        reasons.append(RejectionReason.STALE_SOURCE_HASH.value)
        if metadata:
            metadata["freshness_status"] = "stale"
    if metadata_mutation == RejectionReason.CHANGED_IGNORE_POLICY_HASH.value:
        reasons.append(RejectionReason.CHANGED_IGNORE_POLICY_HASH.value)
        metadata["ignore_policy_fingerprint"] = "changed"
    if metadata_mutation == RejectionReason.CHANGED_SAFETY_POLICY_HASH.value:
        reasons.append(RejectionReason.CHANGED_SAFETY_POLICY_HASH.value)
        metadata["safety_policy_fingerprint"] = "changed"
    if metadata_mutation == RejectionReason.CHANGED_CONTEXT_STRATEGY_ID.value:
        reasons.append(RejectionReason.CHANGED_CONTEXT_STRATEGY_ID.value)
        metadata["context_strategy_id"] = "changed_strategy"
    deduped_reasons = sorted(set(reasons))
    decision = AdmissionDecision.REJECT.value if deduped_reasons else AdmissionDecision.ADMIT.value
    metadata["admission_decision"] = decision
    metadata["rejection_reasons"] = deduped_reasons
    if decision == AdmissionDecision.REJECT.value:
        metadata["retention_mode"] = RetentionMode.REJECTED_NO_CONTENT.value
    return {
        "path": relative_path,
        "exists": exists,
        "decision": decision,
        "rejection_reasons": deduped_reasons,
        "metadata": metadata,
        "contains_source_excerpt": False,
    }


def run_negative_controls(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    fixture = dict_value(policy.get("negative_control_fixture"))
    root = resolve_path(config_root, str(fixture.get("root"))).resolve()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for case in object_list(policy.get("negative_controls")):
        raw_path = str(case.get("path"))
        metadata_mutation = case.get("metadata_mutation") if isinstance(case.get("metadata_mutation"), str) else None
        result = evaluate_candidate(root=root, raw_path=raw_path, policy=policy, metadata_mutation=metadata_mutation)
        expected_decision = case.get("expected_decision")
        expected_reasons = set(string_list(case.get("expected_reasons")))
        actual_reasons = set(result.get("rejection_reasons", []))
        case_result = {
            "case_id": case.get("case_id"),
            "path": raw_path,
            "expected_decision": expected_decision,
            "actual_decision": result.get("decision"),
            "expected_reasons": sorted(expected_reasons),
            "actual_reasons": sorted(actual_reasons),
            "passed": result.get("decision") == expected_decision and expected_reasons.issubset(actual_reasons),
            "metadata": result.get("metadata"),
            "contains_source_excerpt": result.get("contains_source_excerpt"),
        }
        if not case_result["passed"]:
            errors.append(
                validation_error(
                    f"negative_controls.{case.get('case_id')}",
                    f"expected {expected_decision} {sorted(expected_reasons)}, got {result.get('decision')} {sorted(actual_reasons)}",
                    source="negative_controls",
                )
            )
        if result.get("contains_source_excerpt") is True:
            errors.append(
                validation_error(
                    f"negative_controls.{case.get('case_id')}.source_excerpt",
                    "negative-control result must not contain source excerpts",
                    source="negative_controls",
                )
            )
        results.append(case_result)
    return results, errors


def validate_sanitized_report(report: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    serialized = json.dumps(report, sort_keys=True)
    errors: list[dict[str, str]] = []
    for pattern in object_list(policy.get("secret_like_patterns")):
        raw_value = pattern.get("contains")
        if isinstance(raw_value, str) and raw_value and raw_value in serialized:
            errors.append(validation_error("report.secret_like_leak", f"report contains secret-like pattern {pattern.get('pattern_id')}", source="report"))
    for forbidden in ("ignored content", "private notes must never be indexed", "outside root"):
        if forbidden in serialized:
            errors.append(validation_error("report.rejected_content_leak", f"report contains rejected content marker {forbidden!r}", source="report"))
    return errors


def build_report(config: CorpusIndexSafetyGovernanceConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    phase215_path, phase215_report, phase215_errors = load_phase215_report(
        config_root,
        policy,
        require_artifacts=config.require_artifacts,
    )
    precondition_errors = validate_phase215_precondition(policy, phase215_report)
    fixture_info = generate_negative_control_fixture(config_root, policy) if config.generate_fixture else {}
    negative_results, negative_errors = run_negative_controls(config_root, policy) if not policy_errors else ([], [])
    validation_errors = policy_errors + phase215_errors + precondition_errors + negative_errors
    status = "passed" if not validation_errors else "failed"
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
        "output_path": str(output_path),
        "phase215_report_path": str(phase215_path) if phase215_path is not None else None,
        "phase215_report_sha256": sha256_file(phase215_path) if phase215_path is not None and phase215_path.is_file() else None,
        "fixture_generation": fixture_info,
        "root_policy": dict_value(policy.get("root_policy")),
        "ignore_policy": dict_value(policy.get("ignore_policy")),
        "safety_rules": string_list(policy.get("safety_rules")),
        "index_manifest_requirements": string_list(policy.get("index_manifest_requirements")),
        "retention_policy": dict_value(policy.get("retention_policy")),
        "negative_control_results": negative_results,
        "out_of_scope": string_list(policy.get("out_of_scope")),
        "validation_errors": validation_errors,
        "summary": {
            "negative_control_count": len(negative_results),
            "negative_control_passed_count": len([item for item in negative_results if item.get("passed") is True]),
            "admitted_count": len([item for item in negative_results if item.get("actual_decision") == AdmissionDecision.ADMIT.value]),
            "rejected_count": len([item for item in negative_results if item.get("actual_decision") == AdmissionDecision.REJECT.value]),
            "safety_rule_count": len(string_list(policy.get("safety_rules"))),
            "manifest_requirement_count": len(string_list(policy.get("index_manifest_requirements"))),
            "retention_source_text_copy_allowed": dict_value(policy.get("retention_policy")).get("source_text_copy_allowed"),
            "chat_visible_rejected_content_allowed": dict_value(policy.get("retention_policy")).get(
                "chat_visible_rejected_content_allowed"
            ),
            "artifact_rejected_content_allowed": dict_value(policy.get("retention_policy")).get(
                "artifact_rejected_content_allowed"
            ),
            "durable_index_implementation_in_scope": "durable_index_implementation" not in string_list(policy.get("out_of_scope")),
            "retrieval_backed_chat_integration_in_scope": "retrieval_backed_chat_integration"
            not in string_list(policy.get("out_of_scope")),
            "phase217_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    leak_errors = validate_sanitized_report(report, policy)
    if leak_errors:
        report["validation_errors"] = validation_errors + leak_errors
        report["status"] = "failed"
        report["summary"]["phase217_ready"] = False
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Corpus Index Safety Governance",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Negative controls: `{summary.get('negative_control_passed_count')}/{summary.get('negative_control_count')}`",
        f"- Admitted candidates: `{summary.get('admitted_count')}`",
        f"- Rejected candidates: `{summary.get('rejected_count')}`",
        f"- Safety rules: `{summary.get('safety_rule_count')}`",
        f"- Manifest requirements: `{summary.get('manifest_requirement_count')}`",
        f"- Durable index implementation in scope: `{summary.get('durable_index_implementation_in_scope')}`",
        f"- Retrieval-backed chat integration in scope: `{summary.get('retrieval_backed_chat_integration_in_scope')}`",
        f"- Phase 217 ready: `{summary.get('phase217_ready')}`",
        "",
        "## Negative Controls",
    ]
    for item in object_list(report.get("negative_control_results")):
        lines.append(
            f"- `{item.get('case_id')}` `{item.get('actual_decision')}` "
            f"expected `{item.get('expected_decision')}` reasons `{item.get('actual_reasons')}`"
        )
    lines.extend(
        [
            "",
            "## Phase Boundary",
            "",
            "- This phase validates safety governance only.",
            "- It does not implement a durable index, choose embeddings, connect retrieval to chat, implement artifact paging, or prove raw 1M-token context.",
            "- Rejected source text, private content, ignored content, secret-like values, and stale content must not appear in this report.",
        ]
    )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_corpus_index_safety_governance(config: CorpusIndexSafetyGovernanceConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
