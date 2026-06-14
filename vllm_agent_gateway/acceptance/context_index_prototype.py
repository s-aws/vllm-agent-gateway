"""Phase 217 metadata-first context index prototype gate."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "context_index_prototype_policy"
EXPECTED_REPORT_KIND = "context_index_prototype_report"
EXPECTED_INDEX_KIND = "metadata_first_context_index"
EXPECTED_PHASE = 217
EXPECTED_BACKLOG_ID = "P0-M6-217"
EXPECTED_MILESTONE_IDS = {"M6", "M16"}
DEFAULT_POLICY_PATH = Path("runtime") / "context_index_prototype_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase217" / "phase217-context-index-prototype-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase217" / "phase217-context-index-prototype-report.md"


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}
STOP_TERMS = {
    "and",
    "for",
    "from",
    "into",
    "line",
    "return",
    "the",
    "this",
    "true",
    "with",
}
REQUIRED_METADATA = {
    "schema_version",
    "phase",
    "index_schema_version",
    "target_root",
    "allowed_root_id",
    "relative_path",
    "source_path",
    "source_sha256",
    "source_size",
    "source_mtime_ns",
    "ignore_policy_fingerprint",
    "safety_policy_fingerprint",
    "language",
    "chunk_id",
    "chunk_index",
    "line_start",
    "line_end",
    "start_line",
    "end_line",
    "chunk_sha256",
    "chunk_char_count",
    "chunk_token_estimate",
    "estimated_tokens",
    "search_terms",
    "search_terms_hash",
    "context_strategy_id",
    "index_created_at",
    "freshness_status",
    "admission_decision",
    "rejection_reasons",
}
REQUIRED_NEGATIVE_CASES = {
    "P217-SAFE-001",
    "P217-SAFE-002",
    "P217-SAFE-003",
    "P217-SAFE-004",
    "P217-SAFE-005",
    "P217-SAFE-006",
    "P217-SAFE-007",
}
REQUIRED_OUT_OF_SCOPE = {
    "retrieval_backed_chat_integration",
    "embedding_model_selection",
    "vector_search",
    "artifact_paging_implementation",
    "raw_1m_context_benchmark",
    "protected_fixture_mutation",
}


@dataclass(frozen=True)
class ContextIndexPrototypeConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


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


def positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 217"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M6 and M16"))
    precondition = dict_value(policy.get("phase216_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition.get(key)).strip():
            errors.append(validation_error(f"policy.phase216_precondition.{key}", f"{key} must be a non-empty string"))
    for key in (
        "required_phase217_ready",
        "durable_index_implementation_in_scope_must_be",
        "retrieval_backed_chat_integration_in_scope_must_be",
    ):
        if not isinstance(precondition.get(key), bool):
            errors.append(validation_error(f"policy.phase216_precondition.{key}", f"{key} must be boolean"))
    if not isinstance(policy.get("phase216_policy_path"), str) or not str(policy.get("phase216_policy_path")).strip():
        errors.append(validation_error("policy.phase216_policy_path", "phase216_policy_path must be a non-empty string"))
    corpus = dict_value(policy.get("source_corpus"))
    for key in ("root", "source_text_retention"):
        if not isinstance(corpus.get(key), str) or not str(corpus.get(key)).strip():
            errors.append(validation_error(f"policy.source_corpus.{key}", f"{key} must be a non-empty string"))
    if corpus.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.source_corpus.source_text_retention", "source_text_retention must be metadata_only"))
    if not string_list(corpus.get("allowed_suffixes")):
        errors.append(validation_error("policy.source_corpus.allowed_suffixes", "allowed_suffixes must not be empty"))
    for key in ("max_files", "chunk_line_count"):
        if positive_int(corpus.get(key)) is None:
            errors.append(validation_error(f"policy.source_corpus.{key}", f"{key} must be positive integer"))
    chars_per_token = corpus.get("chars_per_token")
    if not isinstance(chars_per_token, (int, float)) or isinstance(chars_per_token, bool) or chars_per_token <= 0:
        errors.append(validation_error("policy.source_corpus.chars_per_token", "chars_per_token must be positive"))
    artifact = dict_value(policy.get("index_artifact"))
    for key in ("path", "markdown_summary_path"):
        if not isinstance(artifact.get(key), str) or not str(artifact.get(key)).strip():
            errors.append(validation_error(f"policy.index_artifact.{key}", f"{key} must be a non-empty string"))
    if artifact.get("store_source_text") is not False:
        errors.append(validation_error("policy.index_artifact.store_source_text", "store_source_text must be false"))
    if artifact.get("store_rejected_content") is not False:
        errors.append(validation_error("policy.index_artifact.store_rejected_content", "store_rejected_content must be false"))
    if positive_int(artifact.get("term_limit_per_chunk")) is None:
        errors.append(validation_error("policy.index_artifact.term_limit_per_chunk", "term_limit_per_chunk must be positive integer"))
    missing_metadata = sorted(REQUIRED_METADATA - set(string_list(policy.get("required_index_metadata"))))
    if missing_metadata:
        errors.append(validation_error("policy.required_index_metadata", f"missing index metadata: {missing_metadata}"))
    if len(object_list(policy.get("query_smoke_cases"))) < 3:
        errors.append(validation_error("policy.query_smoke_cases", "at least three query smoke cases are required"))
    for index, case in enumerate(object_list(policy.get("query_smoke_cases"))):
        for key in ("case_id", "query"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                errors.append(validation_error(f"policy.query_smoke_cases[{index}].{key}", f"{key} must be non-empty"))
        if positive_int(case.get("minimum_matches")) is None:
            errors.append(validation_error(f"policy.query_smoke_cases[{index}].minimum_matches", "minimum_matches must be positive"))
        if not string_list(case.get("required_terms")):
            errors.append(validation_error(f"policy.query_smoke_cases[{index}].required_terms", "required_terms must not be empty"))
    case_ids = {str(item.get("case_id")) for item in object_list(policy.get("negative_controls"))}
    missing_cases = sorted(REQUIRED_NEGATIVE_CASES - case_ids)
    if missing_cases:
        errors.append(validation_error("policy.negative_controls", f"missing negative controls: {missing_cases}"))
    minimums = dict_value(policy.get("minimums"))
    for key in (
        "indexed_file_count",
        "chunk_count",
        "estimated_indexed_token_count",
        "rejected_negative_control_count",
        "query_smoke_case_count",
        "max_search_term_length",
    ):
        if positive_int(minimums.get(key)) is None:
            errors.append(validation_error(f"policy.minimums.{key}", f"{key} must be positive integer"))
    missing_out_of_scope = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing_out_of_scope:
        errors.append(validation_error("policy.out_of_scope", f"missing out-of-scope boundaries: {missing_out_of_scope}"))
    if policy.get("acceptance_marker") != "PHASE217 CONTEXT INDEX PROTOTYPE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 217"))
    return errors


def load_report(
    config_root: Path,
    raw_path: object,
    *,
    source: str,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error(f"{source}.missing", f"{source} report is required", source=source)]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [
            validation_error(f"{source}.malformed", f"{source} report is malformed: {type(exc).__name__}: {exc}", source=source)
        ]


def validate_phase216_precondition(policy: dict[str, Any], phase216_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not phase216_report:
        return errors
    precondition = dict_value(policy.get("phase216_precondition"))
    summary = dict_value(phase216_report.get("summary"))
    if phase216_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase216_report.status", "Phase 216 report status must be passed", source="phase216"))
    if summary.get("phase217_ready") is not precondition.get("required_phase217_ready"):
        errors.append(validation_error("phase216_report.phase217_ready", "Phase 216 report must mark phase217_ready", source="phase216"))
    if summary.get("durable_index_implementation_in_scope") is not precondition.get("durable_index_implementation_in_scope_must_be"):
        errors.append(
            validation_error(
                "phase216_report.durable_index_implementation_in_scope",
                "Phase 216 must not put durable index implementation in scope",
                source="phase216",
            )
        )
    if summary.get("retrieval_backed_chat_integration_in_scope") is not precondition.get(
        "retrieval_backed_chat_integration_in_scope_must_be"
    ):
        errors.append(
            validation_error(
                "phase216_report.retrieval_backed_chat_integration_in_scope",
                "Phase 216 must not put retrieval-backed chat in scope",
                source="phase216",
            )
        )
    return errors


def ignore_patterns(root: Path, phase216_policy: dict[str, Any]) -> list[str]:
    patterns = string_list(dict_value(phase216_policy.get("ignore_policy")).get("policy_deny_patterns"))
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


def secret_like(path: Path, phase216_policy: dict[str, Any]) -> bool:
    if path.suffix == ".secret":
        return True
    if is_binary_file(path):
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(str(item.get("contains")) in text for item in object_list(phase216_policy.get("secret_like_patterns")))


def fingerprint_ignore_policy(root: Path, phase216_policy: dict[str, Any]) -> str:
    return sha256_text(json.dumps({"patterns": ignore_patterns(root, phase216_policy)}, sort_keys=True))


def evaluate_candidate(root: Path, raw_path: str, phase216_policy: dict[str, Any], *, metadata_mutation: str | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    path = Path(raw_path)
    if ".." in path.parts:
        reasons.append("path_traversal")
    candidate = path if path.is_absolute() else root / path
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            reasons.append("unapproved_root")
    relative_path = raw_path if path.is_absolute() else path.as_posix()
    if candidate.exists() and candidate.is_file() and not candidate.is_symlink() and "unapproved_root" not in reasons:
        relative_path = candidate.relative_to(root).as_posix()
        patterns = ignore_patterns(root, phase216_policy)
        if path_is_ignored(relative_path, patterns):
            reasons.append("ignored_path")
        if relative_path.startswith("private/"):
            reasons.append("private_path")
        if relative_path.startswith("runtime-state/"):
            reasons.append("generated_artifact")
        if is_binary_file(candidate):
            reasons.append("binary_file")
        if secret_like(candidate, phase216_policy):
            reasons.append("secret_like_content")
    if metadata_mutation == "stale_source_hash":
        reasons.append("stale_source_hash")
    decision = "reject" if reasons else "admit"
    return {"path": relative_path, "decision": decision, "rejection_reasons": sorted(set(reasons))}


def terms_for_text(text: str, *, limit: int, max_length: int) -> list[str]:
    counts: dict[str, int] = {}
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower()):
        if token in STOP_TERMS or len(token) > max_length:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _count in ranked[:limit]]


def language_for_path(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "other")


def build_chunks_for_file(
    *,
    root: Path,
    path: Path,
    phase216_policy: dict[str, Any],
    chunk_line_count: int,
    chars_per_token: float,
    term_limit: int,
    max_search_term_length: int,
) -> list[dict[str, Any]]:
    relative_path = path.relative_to(root).as_posix()
    source_sha = sha256_file(path)
    stat = path.stat()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    chunks: list[dict[str, Any]] = []
    for chunk_index, start in enumerate(range(0, len(lines), chunk_line_count)):
        chunk_lines = lines[start : start + chunk_line_count]
        chunk_text = "\n".join(chunk_lines)
        chunk_hash = sha256_text(chunk_text)
        search_terms = terms_for_text(chunk_text, limit=term_limit, max_length=max_search_term_length)
        token_estimate = math.ceil(len(chunk_text) / chars_per_token)
        chunks.append(
            {
                "schema_version": SCHEMA_VERSION,
                "index_schema_version": SCHEMA_VERSION,
                "phase": EXPECTED_PHASE,
                "target_root": str(root),
                "allowed_root_id": "phase214_generated_large_corpus",
                "relative_path": relative_path,
                "source_path": relative_path,
                "source_sha256": source_sha,
                "source_size": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
                "ignore_policy_fingerprint": fingerprint_ignore_policy(root, phase216_policy),
                "safety_policy_fingerprint": sha256_text(json.dumps(phase216_policy, sort_keys=True)),
                "language": language_for_path(path),
                "chunk_id": f"{relative_path}::chunk-{chunk_index:04d}::{chunk_hash[:16]}",
                "chunk_index": chunk_index,
                "line_start": start + 1,
                "line_end": start + len(chunk_lines),
                "start_line": start + 1,
                "end_line": start + len(chunk_lines),
                "chunk_sha256": chunk_hash,
                "chunk_char_count": len(chunk_text),
                "chunk_token_estimate": token_estimate,
                "estimated_tokens": token_estimate,
                "search_terms": search_terms,
                "search_terms_hash": sha256_text(json.dumps(search_terms, sort_keys=True)),
                "context_strategy_id": "retrieval",
                "index_created_at": utc_timestamp(),
                "freshness_status": "fresh",
                "admission_decision": "admit",
                "rejection_reasons": [],
            }
        )
    return chunks


def build_index(config_root: Path, policy: dict[str, Any], phase216_policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    corpus = dict_value(policy.get("source_corpus"))
    artifact = dict_value(policy.get("index_artifact"))
    root = resolve_path(config_root, str(corpus.get("root"))).resolve()
    errors: list[dict[str, str]] = []
    if not root.is_dir():
        return {}, [validation_error("source_corpus.root", f"source corpus root does not exist: {root}", source="index")]
    allowed_suffixes = set(string_list(corpus.get("allowed_suffixes")))
    max_files = int(corpus.get("max_files", 0))
    chunk_line_count = int(corpus.get("chunk_line_count", 80))
    chars_per_token = float(corpus.get("chars_per_token", 4.0))
    term_limit = int(artifact.get("term_limit_per_chunk", 24))
    max_search_term_length = int(dict_value(policy.get("minimums")).get("max_search_term_length", 32))
    chunks: list[dict[str, Any]] = []
    indexed_files: set[str] = set()
    rejected_candidate_count = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        candidate = evaluate_candidate(root, relative, phase216_policy)
        if candidate["decision"] != "admit":
            rejected_candidate_count += 1
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue
        if is_binary_file(path):
            rejected_candidate_count += 1
            continue
        indexed_files.add(relative)
        chunks.extend(
            build_chunks_for_file(
                root=root,
                path=path,
                phase216_policy=phase216_policy,
                chunk_line_count=chunk_line_count,
                chars_per_token=chars_per_token,
                term_limit=term_limit,
                max_search_term_length=max_search_term_length,
            )
        )
        if len(indexed_files) >= max_files:
            break
    index = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_INDEX_KIND,
        "phase": EXPECTED_PHASE,
        "generated_at": utc_timestamp(),
        "target_root": str(root),
        "source_text_retention": "metadata_only",
        "store_source_text": False,
        "store_rejected_content": False,
        "indexed_file_count": len(indexed_files),
        "chunk_count": len(chunks),
        "estimated_indexed_token_count": sum(int(item["estimated_tokens"]) for item in chunks),
        "chunks": chunks,
        "rejected_candidate_count": rejected_candidate_count,
        "index_fingerprint": sha256_text(json.dumps(chunks, sort_keys=True)),
    }
    index_path = resolve_path(config_root, str(artifact.get("path")))
    write_json(index_path, index)
    summary_path = resolve_path(config_root, str(artifact.get("markdown_summary_path")))
    write_text(
        summary_path,
        "\n".join(
            [
                "# Context Index Summary",
                "",
                f"- Indexed files: `{index['indexed_file_count']}`",
                f"- Chunks: `{index['chunk_count']}`",
                f"- Estimated indexed tokens: `{index['estimated_indexed_token_count']}`",
                f"- Source text retention: `{index['source_text_retention']}`",
            ]
        )
        + "\n",
    )
    return index, errors


def validate_index(index: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    minimums = dict_value(policy.get("minimums"))
    for key in ("indexed_file_count", "chunk_count", "estimated_indexed_token_count"):
        actual = index.get(key)
        expected = minimums.get(key)
        if not isinstance(actual, int) or not isinstance(expected, int) or actual < expected:
            errors.append(validation_error(f"index.{key}", f"{key} must be at least {expected}, got {actual}", source="index"))
    if index.get("store_source_text") is not False:
        errors.append(validation_error("index.store_source_text", "index must not store source text", source="index"))
    if index.get("store_rejected_content") is not False:
        errors.append(validation_error("index.store_rejected_content", "index must not store rejected content", source="index"))
    for item in object_list(index.get("chunks")):
        missing = REQUIRED_METADATA - set(item)
        if missing:
            errors.append(validation_error("index.chunk.metadata", f"chunk missing metadata: {sorted(missing)}", source="index"))
            break
        if "text" in item or "snippet" in item or "content" in item:
            errors.append(validation_error("index.chunk.source_text", "chunk must not contain source text fields", source="index"))
            break
        max_term_length = int(dict_value(policy.get("minimums")).get("max_search_term_length", 32))
        long_terms = [term for term in string_list(item.get("search_terms")) if len(term) > max_term_length]
        if long_terms:
            errors.append(validation_error("index.chunk.search_terms", f"search terms exceed max length: {long_terms[:3]}", source="index"))
            break
        if not isinstance(item.get("search_terms_hash"), str) or not item["search_terms_hash"]:
            errors.append(validation_error("index.chunk.search_terms_hash", "chunk must include search_terms_hash", source="index"))
            break
    return errors


def run_query_smokes(index: dict[str, Any], policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    chunks = object_list(index.get("chunks"))
    for case in object_list(policy.get("query_smoke_cases")):
        required_terms = {term.lower() for term in string_list(case.get("required_terms"))}
        matches = [
            chunk
            for chunk in chunks
            if required_terms.intersection(set(string_list(chunk.get("search_terms"))))
        ]
        top_matches = sorted(
            matches,
            key=lambda chunk: (
                -len(required_terms.intersection(set(string_list(chunk.get("search_terms"))))),
                str(chunk.get("source_path")),
                int(chunk.get("chunk_index", 0)),
            ),
        )[:10]
        result = {
            "case_id": case.get("case_id"),
            "query": case.get("query"),
            "required_terms": sorted(required_terms),
            "match_count": len(matches),
            "minimum_matches": case.get("minimum_matches"),
            "top_matches": [
                {
                    "source_path": item.get("source_path"),
                    "chunk_id": item.get("chunk_id"),
                    "chunk_sha256": item.get("chunk_sha256"),
                    "source_sha256": item.get("source_sha256"),
                    "freshness_status": item.get("freshness_status"),
                    "start_line": item.get("start_line"),
                    "end_line": item.get("end_line"),
                    "score": len(required_terms.intersection(set(string_list(item.get("search_terms"))))),
                    "matched_terms": sorted(required_terms.intersection(set(string_list(item.get("search_terms"))))),
                }
                for item in top_matches
            ],
        }
        if len(matches) < int(case.get("minimum_matches", 0)):
            errors.append(
                validation_error(
                    f"query_smoke.{case.get('case_id')}",
                    f"query smoke found {len(matches)} matches, expected at least {case.get('minimum_matches')}",
                    source="query_smoke",
                )
            )
        results.append(result)
    return results, errors


def validate_stale_controls(index: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for item in object_list(index.get("chunks"))[:20]:
        if item.get("freshness_status") != "fresh":
            errors.append(validation_error("index.freshness_status", "admitted chunks must start fresh", source="index"))
            break
        for key in (
            "source_sha256",
            "source_size",
            "source_mtime_ns",
            "ignore_policy_fingerprint",
            "safety_policy_fingerprint",
            "context_strategy_id",
            "index_schema_version",
        ):
            if item.get(key) in (None, ""):
                errors.append(validation_error(f"index.stale_control.{key}", f"{key} is required for stale rejection", source="index"))
                break
    return errors


def run_negative_controls(policy: dict[str, Any], phase216_policy: dict[str, Any], index_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for case in object_list(policy.get("negative_controls")):
        result = evaluate_candidate(
            index_root,
            str(case.get("path")),
            phase216_policy,
            metadata_mutation=case.get("metadata_mutation") if isinstance(case.get("metadata_mutation"), str) else None,
        )
        expected_decision = case.get("expected_decision")
        expected_reasons = set(string_list(case.get("expected_reasons")))
        actual_reasons = set(string_list(result.get("rejection_reasons")))
        passed = result.get("decision") == expected_decision and expected_reasons.issubset(actual_reasons)
        if not passed:
            errors.append(
                validation_error(
                    f"negative_controls.{case.get('case_id')}",
                    f"expected {expected_decision} {sorted(expected_reasons)}, got {result.get('decision')} {sorted(actual_reasons)}",
                    source="negative_controls",
                )
            )
        results.append(
            {
                "case_id": case.get("case_id"),
                "path": case.get("path"),
                "expected_decision": expected_decision,
                "actual_decision": result.get("decision"),
                "expected_reasons": sorted(expected_reasons),
                "actual_reasons": sorted(actual_reasons),
                "passed": passed,
            }
        )
    return results, errors


def validate_sanitized_artifacts(report: dict[str, Any], index: dict[str, Any]) -> list[dict[str, str]]:
    serialized = json.dumps({"report": report, "index": index}, sort_keys=True)
    errors: list[dict[str, str]] = []
    for forbidden in (
        "DUMMY_SECRET_DO_NOT_USE",
        "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE",
        "ignored generated note",
        "local runtime artifact",
    ):
        if forbidden in serialized:
            errors.append(validation_error("artifact.rejected_content_leak", f"artifact contains rejected marker {forbidden}", source="artifact"))
    if '"text":' in serialized or '"snippet":' in serialized or '"content":' in serialized:
        errors.append(validation_error("artifact.source_text_field", "index/report must not contain source text fields", source="artifact"))
    return errors


def build_report(config: ContextIndexPrototypeConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    phase216_path, phase216_report, phase216_errors = load_report(
        config_root,
        dict_value(policy.get("phase216_precondition")).get("report_path"),
        source="phase216_report",
        require_artifacts=config.require_artifacts,
    )
    phase216_precondition_errors = validate_phase216_precondition(policy, phase216_report)
    phase216_policy_path = resolve_path(config_root, str(policy.get("phase216_policy_path")))
    phase216_policy = read_json_object(phase216_policy_path) if phase216_policy_path.is_file() else {}
    index, index_errors = build_index(config_root, policy, phase216_policy) if not policy_errors else ({}, [])
    index_validation_errors = validate_index(index, policy) if index else []
    stale_control_errors = validate_stale_controls(index) if index else []
    query_results, query_errors = run_query_smokes(index, policy) if index else ([], [])
    index_root = resolve_path(config_root, str(dict_value(policy.get("source_corpus")).get("root"))).resolve()
    negative_results, negative_errors = run_negative_controls(policy, phase216_policy, index_root) if index else ([], [])
    validation_errors = (
        policy_errors
        + phase216_errors
        + phase216_precondition_errors
        + index_errors
        + index_validation_errors
        + stale_control_errors
        + query_errors
        + negative_errors
    )
    status = "passed" if not validation_errors else "failed"
    artifact = dict_value(policy.get("index_artifact"))
    index_path = resolve_path(config_root, str(artifact.get("path")))
    markdown_index_path = resolve_path(config_root, str(artifact.get("markdown_summary_path")))
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
        "phase216_report_path": str(phase216_path) if phase216_path is not None else None,
        "phase216_report_sha256": sha256_file(phase216_path) if phase216_path is not None and phase216_path.is_file() else None,
        "phase216_policy_path": str(phase216_policy_path),
        "phase216_policy_sha256": sha256_file(phase216_policy_path) if phase216_policy_path.is_file() else None,
        "index_artifact_path": str(index_path),
        "index_artifact_sha256": sha256_file(index_path) if index_path.is_file() else None,
        "index_markdown_summary_path": str(markdown_index_path),
        "query_smoke_results": query_results,
        "negative_control_results": negative_results,
        "out_of_scope": string_list(policy.get("out_of_scope")),
        "validation_errors": validation_errors,
        "summary": {
            "indexed_file_count": index.get("indexed_file_count"),
            "chunk_count": index.get("chunk_count"),
            "estimated_indexed_token_count": index.get("estimated_indexed_token_count"),
            "query_smoke_case_count": len(query_results),
            "query_smoke_passed_count": len(query_results) - len(query_errors),
            "negative_control_count": len(negative_results),
            "negative_control_passed_count": len([item for item in negative_results if item.get("passed") is True]),
            "rejected_negative_control_count": len([item for item in negative_results if item.get("actual_decision") == "reject"]),
            "source_text_retention": index.get("source_text_retention"),
            "store_source_text": index.get("store_source_text"),
            "store_rejected_content": index.get("store_rejected_content"),
            "retrieval_backed_chat_integration_in_scope": "retrieval_backed_chat_integration" not in string_list(policy.get("out_of_scope")),
            "phase218_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    leak_errors = validate_sanitized_artifacts(report, index)
    if leak_errors:
        report["validation_errors"] = validation_errors + leak_errors
        report["status"] = "failed"
        report["summary"]["phase218_ready"] = False
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Context Index Prototype",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Indexed files: `{summary.get('indexed_file_count')}`",
        f"- Chunks: `{summary.get('chunk_count')}`",
        f"- Estimated indexed tokens: `{summary.get('estimated_indexed_token_count')}`",
        f"- Query smokes: `{summary.get('query_smoke_passed_count')}/{summary.get('query_smoke_case_count')}`",
        f"- Negative controls: `{summary.get('negative_control_passed_count')}/{summary.get('negative_control_count')}`",
        f"- Source text retention: `{summary.get('source_text_retention')}`",
        f"- Store source text: `{summary.get('store_source_text')}`",
        f"- Phase 218 ready: `{summary.get('phase218_ready')}`",
        "",
        "## Query Smokes",
    ]
    for item in object_list(report.get("query_smoke_results")):
        lines.append(f"- `{item.get('case_id')}` matches `{item.get('match_count')}` for `{item.get('query')}`")
    lines.extend(["", "## Negative Controls"])
    for item in object_list(report.get("negative_control_results")):
        lines.append(f"- `{item.get('case_id')}` `{item.get('actual_decision')}` reasons `{item.get('actual_reasons')}`")
    lines.extend(
        [
            "",
            "## Phase Boundary",
            "",
            "- This prototype produces a metadata-first lexical index.",
            "- It does not connect retrieval to chat, choose embeddings, implement vector search, implement artifact paging, or prove raw 1M context.",
        ]
    )
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_context_index_prototype(config: ContextIndexPrototypeConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
