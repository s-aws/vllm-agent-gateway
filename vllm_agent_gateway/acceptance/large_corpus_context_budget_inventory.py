"""Phase 214 large-corpus fixture and context-budget inventory gate."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_corpus_context_budget_inventory_policy"
EXPECTED_REPORT_KIND = "large_corpus_context_budget_inventory_report"
EXPECTED_PHASE = 214
EXPECTED_BACKLOG_ID = "P0-M6-214"
EXPECTED_MILESTONE_IDS = {"M6", "M7"}
DEFAULT_POLICY_PATH = Path("runtime") / "large_corpus_context_budget_inventory_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase214" / "phase214-large-corpus-context-budget-inventory-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase214" / "phase214-large-corpus-context-budget-inventory-report.md"

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".txt": "text",
    ".bin": "binary",
}


@dataclass(frozen=True)
class LargeCorpusContextBudgetInventoryConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
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


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 214"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "policy.milestone_ids must be M6 and M7"))
    fixture = dict_value(policy.get("generated_fixture"))
    for key in ("root", "profile"):
        if not isinstance(fixture.get(key), str) or not fixture[key].strip():
            errors.append(validation_error(f"policy.generated_fixture.{key}", f"{key} must be a non-empty string"))
    for key in ("module_count", "doc_count", "test_count", "config_count", "json_case_count", "filler_lines_per_file", "line_width"):
        if positive_int(fixture.get(key)) is None:
            errors.append(validation_error(f"policy.generated_fixture.{key}", f"{key} must be a positive integer"))
    minimums = dict_value(policy.get("inventory_minimums"))
    for key in (
        "file_count",
        "estimated_token_count",
        "language_count",
        "binary_path_count",
        "ignored_path_count",
        "blind_baseline_prompt_count",
    ):
        if positive_int(minimums.get(key)) is None:
            errors.append(validation_error(f"policy.inventory_minimums.{key}", f"{key} must be a positive integer"))
    token_estimation = dict_value(policy.get("token_estimation"))
    chars_per_token = token_estimation.get("chars_per_token")
    if not isinstance(chars_per_token, (int, float)) or isinstance(chars_per_token, bool) or chars_per_token <= 0:
        errors.append(validation_error("policy.token_estimation.chars_per_token", "chars_per_token must be positive"))
    budget_sources = dict_value(policy.get("context_budget_sources"))
    for key in ("vllm_host_notes", "gateway_start_script", "expected_model"):
        if not isinstance(budget_sources.get(key), str) or not budget_sources[key].strip():
            errors.append(validation_error(f"policy.context_budget_sources.{key}", f"{key} must be a non-empty string"))
    for key in ("expected_model_limit", "expected_target_input_limit", "expected_default_max_output"):
        if positive_int(budget_sources.get(key)) is None:
            errors.append(validation_error(f"policy.context_budget_sources.{key}", f"{key} must be a positive integer"))
    if not isinstance(budget_sources.get("runtime_probe_required"), bool):
        errors.append(validation_error("policy.context_budget_sources.runtime_probe_required", "runtime_probe_required must be boolean"))
    probe_urls = dict_value(budget_sources.get("runtime_probe_urls"))
    for key in ("model_models_url", "gateway_health_url", "controller_health_url", "workflow_router_models_url"):
        if not isinstance(probe_urls.get(key), str) or not probe_urls[key].startswith("http://"):
            errors.append(validation_error(f"policy.context_budget_sources.runtime_probe_urls.{key}", f"{key} must be a local http URL"))
    boundaries = set(string_list(policy.get("required_claim_boundaries")))
    for required in (
        "usable_large_corpus_investigation_not_raw_prompt_stuffing",
        "raw_1m_token_prompt_support_not_claimed",
        "retrieval_first_design_required_before_chat_integration",
        "safety_governance_required_before_durable_indexing",
        "generated_fixture_not_production_source",
    ):
        if required not in boundaries:
            errors.append(validation_error("policy.required_claim_boundaries", f"missing boundary {required}"))
    cases = object_list(policy.get("blind_baseline_prompt_cases"))
    if len(cases) < int(minimums.get("blind_baseline_prompt_count", 0) or 0):
        errors.append(validation_error("policy.blind_baseline_prompt_cases", "not enough blind-baseline prompt cases"))
    categories = {str(item.get("category")) for item in cases}
    for required in (
        "large_corpus_navigation",
        "large_corpus_evidence_lookup",
        "large_corpus_summarization",
        "large_corpus_limitations",
    ):
        if required not in categories:
            errors.append(validation_error("policy.blind_baseline_prompt_cases.categories", f"missing category {required}"))
    for index, case in enumerate(cases):
        prefix = f"policy.blind_baseline_prompt_cases[{index}]"
        for key in ("case_id", "category", "prompt"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                errors.append(validation_error(f"{prefix}.{key}", f"{key} must be a non-empty string"))
        if not string_list(case.get("ideal_answer_shape")):
            errors.append(validation_error(f"{prefix}.ideal_answer_shape", "ideal_answer_shape must not be empty"))
        if not string_list(case.get("must_have_evidence")):
            errors.append(validation_error(f"{prefix}.must_have_evidence", "must_have_evidence must not be empty"))
    if policy.get("acceptance_marker") != "PHASE214 LARGE CORPUS CONTEXT BUDGET INVENTORY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 214"))
    return errors


def deterministic_line(kind: str, index: int, line_no: int, width: int) -> str:
    base = (
        f"{kind} shard {index:04d} line {line_no:04d}: order replay pipeline risk gate audit summary "
        f"context retrieval source evidence chunk boundary token budget fixture navigation "
        f"confidence limitation generated corpus deterministic proof "
    )
    if len(base) >= width:
        return base[:width]
    return base + ("x" * (width - len(base)))


def generated_body(kind: str, index: int, *, filler_lines: int, line_width: int) -> str:
    return "\n".join(deterministic_line(kind, index, line_no, line_width) for line_no in range(filler_lines)) + "\n"


def generate_large_corpus_fixture(config_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    fixture = dict_value(policy.get("generated_fixture"))
    root = resolve_path(config_root, str(fixture.get("root")))
    filler_lines = int(fixture.get("filler_lines_per_file", 1))
    line_width = int(fixture.get("line_width", 120))
    root.mkdir(parents=True, exist_ok=True)
    write_text(
        root / ".gitignore",
        "\n".join(["ignored/", "runtime-state/", "*.bin", "*.secret", ""]) ,
    )
    write_text(root / ".cgcignore", "\n".join(["private/", "*.secret", ""]))

    written: list[str] = [".gitignore", ".cgcignore"]

    for index in range(int(fixture.get("module_count", 0))):
        path = root / "src" / "order_replay" / f"module_{index:04d}.py"
        text = (
            f'"""Generated module {index:04d} for large-corpus context inventory."""\n\n'
            f"PIPELINE_STAGE_{index:04d} = 'risk_gate_audit_summary_{index:04d}'\n\n"
            f"def replay_stage_{index:04d}(event):\n"
            f"    return {{'stage': PIPELINE_STAGE_{index:04d}, 'event': event, 'requires_evidence': True}}\n\n"
            + generated_body("python", index, filler_lines=filler_lines, line_width=line_width)
        )
        write_text(path, text)
        written.append(path.relative_to(root).as_posix())

    for index in range(int(fixture.get("doc_count", 0))):
        path = root / "docs" / "architecture" / f"design_{index:04d}.md"
        text = (
            f"# Generated Design {index:04d}\n\n"
            "This document describes the generated order replay pipeline, risk gate decisions, "
            "audit summaries, context retrieval evidence, and limitations for large-corpus testing.\n\n"
            + generated_body("markdown", index, filler_lines=filler_lines, line_width=line_width)
        )
        write_text(path, text)
        written.append(path.relative_to(root).as_posix())

    for index in range(int(fixture.get("test_count", 0))):
        path = root / "tests" / "regression" / f"test_replay_stage_{index:04d}.py"
        text = (
            f"from src.order_replay.module_{index % max(1, int(fixture.get('module_count', 1))):04d} import replay_stage_{index % max(1, int(fixture.get('module_count', 1))):04d}\n\n"
            f"def test_replay_stage_{index:04d}_emits_audit_evidence():\n"
            f"    result = replay_stage_{index % max(1, int(fixture.get('module_count', 1))):04d}({{'order_id': 'demo'}})\n"
            "    assert result['requires_evidence'] is True\n\n"
            + generated_body("test", index, filler_lines=filler_lines, line_width=line_width)
        )
        write_text(path, text)
        written.append(path.relative_to(root).as_posix())

    for index in range(int(fixture.get("config_count", 0))):
        path = root / "config" / f"strategy_{index:04d}.yaml"
        text = (
            f"strategy_id: generated-strategy-{index:04d}\n"
            "risk_gate: enabled\n"
            "audit_summary: required\n"
            "retrieval_profile: bounded\n"
            + generated_body("yaml", index, filler_lines=filler_lines, line_width=line_width)
        )
        write_text(path, text)
        written.append(path.relative_to(root).as_posix())

    for index in range(int(fixture.get("json_case_count", 0))):
        path = root / "cases" / f"scenario_{index:04d}.json"
        payload = {
            "scenario_id": f"generated-scenario-{index:04d}",
            "pipeline": "order_replay",
            "risk_gate": "enabled",
            "audit_summary": "required",
            "notes": generated_body("json", index, filler_lines=filler_lines, line_width=line_width),
        }
        write_json(path, payload)
        written.append(path.relative_to(root).as_posix())

    write_text(root / "ignored" / "ignored_notes.txt", "ignored generated note\n")
    write_text(root / "runtime-state" / "local_artifact.txt", "local runtime artifact\n")
    write_text(root / "private" / "operator.secret", "DUMMY_SECRET_DO_NOT_USE\n")
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "binary_blob.bin").write_bytes(bytes(range(256)) * 4)
    (root / "ignored" / "ignored_blob.bin").parent.mkdir(parents=True, exist_ok=True)
    (root / "ignored" / "ignored_blob.bin").write_bytes(bytes(reversed(range(256))) * 4)
    written.extend(
        [
            "ignored/ignored_notes.txt",
            "runtime-state/local_artifact.txt",
            "private/operator.secret",
            "assets/binary_blob.bin",
            "ignored/ignored_blob.bin",
        ]
    )
    manifest = {
        "kind": "generated_large_corpus_manifest",
        "schema_version": 1,
        "profile": fixture.get("profile"),
        "generated_at": utc_timestamp(),
        "file_count": len(written),
        "files": sorted(written)[:50],
    }
    write_json(root / "manifest.json", manifest)
    return {"root": str(root), "written_file_count": len(written) + 1, "manifest_path": str(root / "manifest.json")}


def ignore_patterns(root: Path) -> list[str]:
    patterns: list[str] = []
    for name in (".gitignore", ".cgcignore"):
        path = root / name
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


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


def language_for_path(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "other")


def role_for_path(relative_path: str, *, ignored: bool, binary: bool) -> str:
    if ignored:
        return "ignored"
    if binary:
        return "binary"
    if relative_path.startswith("src/"):
        return "source"
    if relative_path.startswith("docs/"):
        return "documentation"
    if relative_path.startswith("tests/"):
        return "test"
    if relative_path.startswith("config/"):
        return "configuration"
    if relative_path.startswith("cases/"):
        return "case_data"
    return "support"


def inventory_corpus(root: Path, *, chars_per_token: float) -> dict[str, Any]:
    patterns = ignore_patterns(root)
    file_count = 0
    total_bytes = 0
    char_count = 0
    ignored_paths: list[str] = []
    binary_paths: list[str] = []
    language_counts: dict[str, int] = {}
    extension_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    directories: set[str] = set()
    largest_files: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        for parent in Path(relative).parents:
            parent_value = parent.as_posix()
            if parent_value not in (".", ""):
                directories.add(parent_value)
        file_count += 1
        language = language_for_path(path)
        language_counts[language] = language_counts.get(language, 0) + 1
        extension = path.suffix.lower() or "[none]"
        extension_counts[extension] = extension_counts.get(extension, 0) + 1
        ignored = path_is_ignored(relative, patterns)
        binary = is_binary_file(path)
        role = role_for_path(relative, ignored=ignored, binary=binary)
        role_counts[role] = role_counts.get(role, 0) + 1
        if ignored:
            ignored_paths.append(relative)
        if binary:
            binary_paths.append(relative)
        size = path.stat().st_size
        total_bytes += size
        digest.update(relative.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        if not binary:
            text = path.read_text(encoding="utf-8", errors="replace")
            char_count += len(text)
        largest_files.append(
            {"path": relative, "bytes": size, "language": language, "role": role, "ignored": ignored, "binary": binary}
        )
    largest_files.sort(key=lambda item: (-int(item["bytes"]), str(item["path"])))
    return {
        "root": str(root),
        "file_count": file_count,
        "directory_count": len(directories),
        "total_bytes": total_bytes,
        "text_char_count": char_count,
        "estimated_token_count": math.ceil(char_count / chars_per_token),
        "chars_per_token": chars_per_token,
        "language_counts": dict(sorted(language_counts.items())),
        "language_count": len(language_counts),
        "extension_counts": dict(sorted(extension_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "ignored_path_count": len(ignored_paths),
        "ignored_path_samples": ignored_paths[:20],
        "binary_path_count": len(binary_paths),
        "binary_path_samples": binary_paths[:20],
        "largest_files": largest_files[:10],
        "fingerprint": digest.hexdigest(),
    }


def parse_gateway_budget(config_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    sources = dict_value(policy.get("context_budget_sources"))
    start_script = resolve_path(config_root, str(sources.get("gateway_start_script")))
    host_notes = resolve_path(config_root, str(sources.get("vllm_host_notes")))
    start_text = start_script.read_text(encoding="utf-8", errors="replace") if start_script.is_file() else ""
    host_text = host_notes.read_text(encoding="utf-8", errors="replace") if host_notes.is_file() else ""

    def shell_default(name: str) -> int | None:
        match = re.search(rf"{name}=\"?\$\{{{name}:-(\d+)\}}\"?", start_text)
        return int(match.group(1)) if match else None

    def host_value(name: str) -> int | None:
        match = re.search(rf"{name}=(\d+)", host_text)
        return int(match.group(1)) if match else None

    model_limit = shell_default("MODEL_LIMIT") or host_value("MODEL_LIMIT")
    target_input_limit = shell_default("TARGET_INPUT_LIMIT") or host_value("TARGET_INPUT_LIMIT")
    default_max_output = shell_default("DEFAULT_MAX_OUTPUT") or host_value("DEFAULT_MAX_OUTPUT")
    safety_buffer = shell_default("SAFETY_BUFFER") or host_value("SAFETY_BUFFER")
    max_model_len_match = re.search(r"--max-model-len\s+(\d+)", host_text)
    max_model_len = int(max_model_len_match.group(1)) if max_model_len_match else model_limit
    return {
        "model": sources.get("expected_model"),
        "model_limit": model_limit,
        "target_input_limit": target_input_limit,
        "default_max_output": default_max_output,
        "safety_buffer": safety_buffer,
        "host_notes_max_model_len": max_model_len,
        "vllm_host_notes": str(host_notes),
        "gateway_start_script": str(start_script),
        "raw_1m_prompt_support_proven": False,
        "budget_source_status": "parsed" if model_limit and target_input_limit and default_max_output else "incomplete",
    }


def probe_json_url(url: str, *, timeout_seconds: float = 2.0) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, headers={"Authorization": "Bearer dummy"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local runtime probe URL from policy.
            body = response.read(8192)
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            payload = {"raw_excerpt": body.decode("utf-8", errors="replace")[:500]}
        return {"url": url, "reachable": True, "payload": payload}
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {"url": url, "reachable": False, "error": f"{type(exc).__name__}: {exc}"}


def runtime_probe(policy: dict[str, Any]) -> dict[str, Any]:
    budget_sources = dict_value(policy.get("context_budget_sources"))
    probe_urls = dict_value(budget_sources.get("runtime_probe_urls"))
    probes = {
        key: probe_json_url(url)
        for key, url in probe_urls.items()
        if isinstance(key, str) and isinstance(url, str) and url.startswith("http://")
    }
    observed_models: list[str] = []
    model_payload = dict_value(dict_value(probes.get("model_models_url")).get("payload"))
    for item in object_list(model_payload.get("data")):
        model_id = item.get("id")
        if isinstance(model_id, str):
            observed_models.append(model_id)
    return {
        "required": bool(budget_sources.get("runtime_probe_required")),
        "probe_count": len(probes),
        "reachable_count": len([item for item in probes.values() if item.get("reachable") is True]),
        "observed_models": observed_models,
        "probes": probes,
    }


def evaluate_report(policy: dict[str, Any], corpus: dict[str, Any], budget: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    minimums = dict_value(policy.get("inventory_minimums"))
    checks = {
        "file_count": corpus.get("file_count"),
        "estimated_token_count": corpus.get("estimated_token_count"),
        "language_count": corpus.get("language_count"),
        "binary_path_count": corpus.get("binary_path_count"),
        "ignored_path_count": corpus.get("ignored_path_count"),
        "blind_baseline_prompt_count": len(object_list(policy.get("blind_baseline_prompt_cases"))),
    }
    for key, actual in checks.items():
        expected = minimums.get(key)
        if not isinstance(actual, int) or not isinstance(expected, int) or actual < expected:
            errors.append(validation_error(f"summary.{key}", f"{key} must be at least {expected}, got {actual}", source="report"))
    if corpus.get("estimated_token_count", 0) <= (budget.get("target_input_limit") or 0):
        errors.append(validation_error("claim_boundary.corpus_exceeds_target_input_limit", "corpus must exceed current target input limit", source="report"))
    if corpus.get("estimated_token_count", 0) <= (budget.get("model_limit") or 0):
        errors.append(validation_error("claim_boundary.corpus_exceeds_model_limit", "corpus must exceed current model limit", source="report"))
    if budget.get("raw_1m_prompt_support_proven") is not False:
        errors.append(validation_error("claim_boundary.raw_1m", "raw 1M-token prompt support must not be claimed", source="report"))
    for key, expected in dict_value(policy.get("context_budget_sources")).items():
        if key.startswith("expected_") and key != "expected_model":
            budget_key = key.replace("expected_", "")
            if budget.get(budget_key) != expected:
                errors.append(validation_error(f"context_budget.{budget_key}", f"{budget_key} must match expected value {expected}", source="report"))
    if budget.get("model") != dict_value(policy.get("context_budget_sources")).get("expected_model"):
        errors.append(validation_error("context_budget.model", "model must match expected model", source="report"))
    runtime = dict_value(budget.get("runtime_probe"))
    if runtime.get("required") is True and runtime.get("reachable_count", 0) < runtime.get("probe_count", 0):
        errors.append(validation_error("runtime_probe.reachable", "all runtime probes must be reachable when required", source="report"))
    return errors


def build_report(config: LargeCorpusContextBudgetInventoryConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    fixture_info = generate_large_corpus_fixture(config_root, policy) if config.generate_fixture else {}
    fixture_root = resolve_path(config_root, str(dict_value(policy.get("generated_fixture")).get("root")))
    chars_per_token = float(dict_value(policy.get("token_estimation")).get("chars_per_token", 4.0))
    corpus = inventory_corpus(fixture_root, chars_per_token=chars_per_token) if fixture_root.is_dir() else {"root": str(fixture_root)}
    budget = parse_gateway_budget(config_root, policy)
    budget["runtime_probe"] = runtime_probe(policy)
    report_errors = evaluate_report(policy, corpus, budget) if not policy_errors else []
    validation_errors = policy_errors + report_errors
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
        "fixture_generation": fixture_info,
        "corpus_inventory": corpus,
        "context_budget": budget,
        "claim_boundaries": string_list(policy.get("required_claim_boundaries")),
        "blind_baseline_prompt_cases": object_list(policy.get("blind_baseline_prompt_cases")),
        "validation_errors": validation_errors,
        "summary": {
            "corpus_root": corpus.get("root"),
            "file_count": corpus.get("file_count"),
            "estimated_token_count": corpus.get("estimated_token_count"),
            "directory_count": corpus.get("directory_count"),
            "language_count": corpus.get("language_count"),
            "binary_path_count": corpus.get("binary_path_count"),
            "ignored_path_count": corpus.get("ignored_path_count"),
            "blind_baseline_prompt_count": len(object_list(policy.get("blind_baseline_prompt_cases"))),
            "model_limit": budget.get("model_limit"),
            "target_input_limit": budget.get("target_input_limit"),
            "raw_1m_prompt_support_proven": False,
            "phase215_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    corpus = dict_value(report.get("corpus_inventory"))
    budget = dict_value(report.get("context_budget"))
    lines = [
        "# Large-Corpus Context Budget Inventory",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Corpus root: `{summary.get('corpus_root')}`",
        f"- Files: `{summary.get('file_count')}`",
        f"- Estimated tokens: `{summary.get('estimated_token_count')}`",
        f"- Model limit: `{summary.get('model_limit')}`",
        f"- Gateway target input limit: `{summary.get('target_input_limit')}`",
        f"- Raw 1M prompt support proven: `{summary.get('raw_1m_prompt_support_proven')}`",
        f"- Phase 215 ready: `{summary.get('phase215_ready')}`",
        "",
        "## Language Mix",
    ]
    for language, count in dict_value(corpus.get("language_counts")).items():
        lines.append(f"- `{language}`: `{count}`")
    lines.extend(
        [
            "",
            "## Context Boundary",
            "",
            "- The corpus is intentionally larger than the current gateway/model context budget.",
            "- This phase does not claim raw 1M-token prompt support.",
            "- Later phases must use retrieval, chunking, summarization, artifact paging, and safety governance before chat integration.",
            "",
            "## Budget Sources",
            "",
            f"- Model: `{budget.get('model')}`",
            f"- vLLM notes: `{budget.get('vllm_host_notes')}`",
            f"- Gateway script: `{budget.get('gateway_start_script')}`",
        ]
    )
    if object_list(report.get("validation_errors")):
        lines.extend(["", "## Validation Errors"])
        for item in object_list(report.get("validation_errors")):
            lines.append(f"- `{item.get('id')}` {item.get('message')}")
    return "\n".join(lines).rstrip() + "\n"


def run_large_corpus_context_budget_inventory(config: LargeCorpusContextBudgetInventoryConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = resolve_path(config_root, config.output_path)
    markdown_path = resolve_path(config_root, config.markdown_output_path)
    report = build_report(config)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_path, render_markdown_report(report))
    return report
