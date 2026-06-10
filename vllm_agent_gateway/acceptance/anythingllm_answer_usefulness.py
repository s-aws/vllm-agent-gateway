"""Priority 0 AnythingLLM answer-usefulness validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_CORPUS_PATH = Path("runtime") / "baseline_corpus.json"
DEFAULT_CONTRACT_PATH = Path("runtime") / "anythingllm_answer_usefulness_contract.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "anythingllm-answer-usefulness"


class AnythingLLMAnswerUsefulnessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class AnythingLLMAnswerUsefulnessConfig:
    config_root: Path
    corpus_path: Path = DEFAULT_CORPUS_PATH
    contract_path: Path = DEFAULT_CONTRACT_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"anythingllm-answer-usefulness-{utc_timestamp()}.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def contains_marker(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def marker_index(text: str, marker: str) -> int:
    return text.lower().find(marker.lower())


def non_empty_line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def contract_entries_by_id(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("entry_id")): entry
        for entry in object_list(contract.get("entries"))
        if isinstance(entry.get("entry_id"), str) and entry.get("entry_id")
    }


def stable_corpus_entries_by_id(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("entry_id")): entry
        for entry in object_list(corpus.get("entries"))
        if entry.get("status") == "stable" and isinstance(entry.get("entry_id"), str) and entry.get("entry_id")
    }


def validate_contract_shape(contract: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append("contract.schema_version must be 1")
    if contract.get("kind") != "priority0_anythingllm_answer_usefulness_contract":
        errors.append("contract.kind must be priority0_anythingllm_answer_usefulness_contract")
    minimum_text_chars = contract.get("minimum_text_chars")
    if not isinstance(minimum_text_chars, int) or minimum_text_chars < 800:
        errors.append("contract.minimum_text_chars must be at least 800")
    minimum_line_count = contract.get("minimum_line_count")
    if not isinstance(minimum_line_count, int) or minimum_line_count < 12:
        errors.append("contract.minimum_line_count must be at least 12")
    minimum_pre_artifact_line_count = contract.get("minimum_pre_artifact_line_count")
    if not isinstance(minimum_pre_artifact_line_count, int) or minimum_pre_artifact_line_count < 8:
        errors.append("contract.minimum_pre_artifact_line_count must be at least 8")
    minimum_answer_section_chars = contract.get("minimum_answer_section_chars")
    if not isinstance(minimum_answer_section_chars, int) or minimum_answer_section_chars < 300:
        errors.append("contract.minimum_answer_section_chars must be at least 300")
    minimum_answer_section_line_count = contract.get("minimum_answer_section_line_count")
    if not isinstance(minimum_answer_section_line_count, int) or minimum_answer_section_line_count < 4:
        errors.append("contract.minimum_answer_section_line_count must be at least 4")
    maximum_pre_answer_line_count = contract.get("maximum_pre_answer_line_count")
    if not isinstance(maximum_pre_answer_line_count, int) or maximum_pre_answer_line_count < 20:
        errors.append("contract.maximum_pre_answer_line_count must be at least 20")
    if not isinstance(contract.get("artifact_section_marker"), str) or not contract["artifact_section_marker"].strip():
        errors.append("contract.artifact_section_marker is required")
    if not string_list(contract.get("required_global_markers")):
        errors.append("contract.required_global_markers is required")
    if not string_list(contract.get("required_safety_markers")):
        errors.append("contract.required_safety_markers is required")

    contract_entry_ids = set(contract_entries_by_id(contract))
    stable_entry_ids = set(stable_corpus_entries_by_id(corpus))
    if contract_entry_ids != stable_entry_ids:
        errors.append("contract.entries must exactly match stable baseline corpus entry IDs")

    for entry_id, entry in contract_entries_by_id(contract).items():
        prefix = f"contract.entries[{entry_id}]"
        if not isinstance(entry.get("priority_backlog_id"), str) or not entry["priority_backlog_id"].strip():
            errors.append(f"{prefix}.priority_backlog_id is required")
        if not (string_list(entry.get("required_answer_markers")) or string_list(entry.get("accepted_answer_section_markers"))):
            errors.append(f"{prefix} must define required_answer_markers or accepted_answer_section_markers")
        if not string_list(entry.get("useful_detail_markers")):
            errors.append(f"{prefix}.useful_detail_markers is required")
        minimum_useful_detail_markers = entry.get("minimum_useful_detail_markers")
        if not isinstance(minimum_useful_detail_markers, int) or minimum_useful_detail_markers < 1:
            errors.append(f"{prefix}.minimum_useful_detail_markers must be at least 1")
        elif minimum_useful_detail_markers > len(string_list(entry.get("useful_detail_markers"))):
            errors.append(f"{prefix}.minimum_useful_detail_markers cannot exceed useful_detail_markers count")
    return errors


def validate_response_text(
    text: str,
    *,
    contract: dict[str, Any],
    entry_contract: dict[str, Any],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    minimum_text_chars = int(contract.get("minimum_text_chars", 0))
    minimum_line_count = int(contract.get("minimum_line_count", 0))
    minimum_pre_artifact_line_count = int(contract.get("minimum_pre_artifact_line_count", 0))
    minimum_answer_section_chars = int(contract.get("minimum_answer_section_chars", 0))
    minimum_answer_section_line_count = int(contract.get("minimum_answer_section_line_count", 0))
    maximum_pre_answer_line_count = int(contract.get("maximum_pre_answer_line_count", 0))
    artifact_section_marker = str(contract.get("artifact_section_marker", "Artifacts:"))

    if len(text) < minimum_text_chars:
        errors.append(f"{prefix}.text is shorter than minimum_text_chars")
    if non_empty_line_count(text) < minimum_line_count:
        errors.append(f"{prefix}.text has fewer non-empty lines than minimum_line_count")
    for marker in string_list(contract.get("required_global_markers")):
        if not contains_marker(text, marker):
            errors.append(f"{prefix}.text missing global marker {marker}")
    for marker in string_list(contract.get("required_safety_markers")):
        if not contains_marker(text, marker):
            errors.append(f"{prefix}.text missing safety marker {marker}")

    artifact_index = marker_index(text, artifact_section_marker)
    if artifact_index < 0:
        errors.append(f"{prefix}.text missing artifact section marker {artifact_section_marker}")
        pre_artifact_text = text
    else:
        pre_artifact_text = text[:artifact_index]
        if non_empty_line_count(pre_artifact_text) < minimum_pre_artifact_line_count:
            errors.append(f"{prefix}.text has too little answer content before artifacts")

    accepted_answer_section_markers = string_list(entry_contract.get("accepted_answer_section_markers"))
    required_answer_markers = string_list(entry_contract.get("required_answer_markers"))
    answer_section_markers = accepted_answer_section_markers or required_answer_markers
    answer_section_indexes = [marker_index(text, marker) for marker in answer_section_markers if marker_index(text, marker) >= 0]
    if not answer_section_indexes:
        errors.append(f"{prefix}.text missing accepted answer section marker")
        answer_section_text = ""
    elif artifact_index >= 0 and min(answer_section_indexes) > artifact_index:
        errors.append(f"{prefix}.text answer section appears after artifacts")
        answer_section_text = ""
    else:
        answer_index = min(answer_section_indexes)
        answer_section_text = text[answer_index:artifact_index] if artifact_index >= 0 else text[answer_index:]
        pre_answer_line_count = non_empty_line_count(text[:answer_index])
        if maximum_pre_answer_line_count and pre_answer_line_count > maximum_pre_answer_line_count:
            errors.append(
                f"{prefix}.text has {pre_answer_line_count} non-empty line(s) before answer section, "
                f"maximum is {maximum_pre_answer_line_count}"
            )
        if len(answer_section_text) < minimum_answer_section_chars:
            errors.append(f"{prefix}.answer_section is shorter than minimum_answer_section_chars")
        if non_empty_line_count(answer_section_text) < minimum_answer_section_line_count:
            errors.append(f"{prefix}.answer_section has fewer lines than minimum_answer_section_line_count")

    for marker in required_answer_markers:
        marker_position = marker_index(text, marker)
        if marker_position < 0:
            errors.append(f"{prefix}.text missing answer marker {marker}")
        elif artifact_index >= 0 and marker_position > artifact_index:
            errors.append(f"{prefix}.text answer marker {marker} appears after artifacts")

    useful_detail_markers = string_list(entry_contract.get("useful_detail_markers"))
    useful_detail_hits = [marker for marker in useful_detail_markers if contains_marker(answer_section_text, marker)]
    minimum_useful_detail_markers = int(entry_contract.get("minimum_useful_detail_markers", 0))
    if len(useful_detail_hits) < minimum_useful_detail_markers:
        errors.append(
            f"{prefix}.text has {len(useful_detail_hits)} useful detail marker(s), "
            f"expected at least {minimum_useful_detail_markers}"
        )
    return errors


def validate_anythingllm_response(
    response: dict[str, Any],
    *,
    contract: dict[str, Any],
    entry_contract: dict[str, Any],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    if response.get("status") != "captured":
        errors.append(f"{prefix}.status must be captured")
    if response.get("http_status") != 200:
        errors.append(f"{prefix}.http_status must be 200")
    text = response.get("text")
    if not isinstance(text, str) or not text.strip():
        return errors + [f"{prefix}.text is required"]
    route_summary = response.get("route_summary") if isinstance(response.get("route_summary"), dict) else {}
    run_id = route_summary.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append(f"{prefix}.route_summary.run_id is required")
    elif run_id not in text:
        errors.append(f"{prefix}.text must include route_summary.run_id")
    if not isinstance(route_summary.get("selected_workflow"), str) or not route_summary["selected_workflow"].strip():
        errors.append(f"{prefix}.route_summary.selected_workflow is required")
    errors.extend(validate_response_text(text, contract=contract, entry_contract=entry_contract, prefix=prefix))
    return errors


def validate_local_eval_artifact(
    *,
    config_root: Path,
    corpus_entry: dict[str, Any],
    contract: dict[str, Any],
    entry_contract: dict[str, Any],
    prefix: str,
    require_artifacts: bool,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    checked_cases = 0
    local_eval = corpus_entry.get("local_eval") if isinstance(corpus_entry.get("local_eval"), dict) else {}
    path_value = local_eval.get("path")
    hash_value = local_eval.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        return [f"{prefix}.local_eval.path is required"], {"checked_cases": checked_cases}
    if not isinstance(hash_value, str) or len(hash_value) != 64:
        return [f"{prefix}.local_eval.sha256 must be a 64-character hash"], {"checked_cases": checked_cases}
    artifact_path = resolve_path(config_root, path_value)
    if not artifact_path.is_file():
        if require_artifacts:
            errors.append(f"{prefix}.local_eval.path does not exist: {path_value}")
        return errors, {"checked_cases": checked_cases}
    actual_hash = sha256_file(artifact_path)
    if actual_hash != hash_value:
        errors.append(f"{prefix}.local_eval.sha256 is stale for {path_value}")
    artifact = read_json_object(artifact_path)
    cases = object_list(artifact.get("checks", {}).get("cases") if isinstance(artifact.get("checks"), dict) else [])
    expected_case_count = corpus_entry.get("expected_case_count")
    if not isinstance(expected_case_count, int) or expected_case_count <= 0:
        errors.append(f"{prefix}.expected_case_count must be a positive integer")
    elif len(cases) != expected_case_count:
        errors.append(f"{prefix}.local_eval artifact case count does not match expected_case_count")
    for case in cases:
        case_id = case.get("case_id", "<missing>")
        responses = case.get("responses") if isinstance(case.get("responses"), dict) else {}
        anythingllm_response = responses.get("anythingllm")
        if not isinstance(anythingllm_response, dict):
            errors.append(f"{prefix}.local_eval case {case_id} missing anythingllm response")
            continue
        checked_cases += 1
        errors.extend(
            validate_anythingllm_response(
                anythingllm_response,
                contract=contract,
                entry_contract=entry_contract,
                prefix=f"{prefix}.local_eval case {case_id}.anythingllm",
            )
        )
    return errors, {"checked_cases": checked_cases}


def validate_anythingllm_answer_usefulness(
    corpus: dict[str, Any],
    contract: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool = False,
) -> tuple[list[str], list[dict[str, Any]]]:
    errors = validate_contract_shape(contract, corpus)
    checked_entries: list[dict[str, Any]] = []
    if errors:
        return errors, checked_entries
    contract_by_id = contract_entries_by_id(contract)
    corpus_by_id = stable_corpus_entries_by_id(corpus)
    for entry_id in sorted(contract_by_id):
        corpus_entry = corpus_by_id[entry_id]
        entry_contract = contract_by_id[entry_id]
        entry_errors, summary = validate_local_eval_artifact(
            config_root=config_root,
            corpus_entry=corpus_entry,
            contract=contract,
            entry_contract=entry_contract,
            prefix=f"entries[{entry_id}]",
            require_artifacts=require_artifacts,
        )
        errors.extend(entry_errors)
        checked_entries.append(
            {
                "entry_id": entry_id,
                "priority_backlog_id": corpus_entry.get("priority_backlog_id"),
                "local_eval_path": corpus_entry.get("local_eval", {}).get("path")
                if isinstance(corpus_entry.get("local_eval"), dict)
                else None,
                "checked_cases": summary["checked_cases"],
                "expected_case_count": corpus_entry.get("expected_case_count"),
                "error_count": len(entry_errors),
            }
        )
    return errors, checked_entries


def run_anythingllm_answer_usefulness(config: AnythingLLMAnswerUsefulnessConfig) -> dict[str, Any]:
    config_root = config.config_root
    corpus = read_json_object(resolve_path(config_root, config.corpus_path))
    contract = read_json_object(resolve_path(config_root, config.contract_path))
    errors, checked_entries = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=config_root,
        require_artifacts=config.require_artifacts,
    )
    total_checked_cases = sum(int(entry["checked_cases"]) for entry in checked_entries)
    status = AnythingLLMAnswerUsefulnessStatus.PASSED if not errors else AnythingLLMAnswerUsefulnessStatus.FAILED
    report: dict[str, Any] = {
        "kind": "anythingllm_answer_usefulness_report",
        "schema_version": SCHEMA_VERSION,
        "status": status.value,
        "generated_at": utc_timestamp(),
        "require_artifacts": config.require_artifacts,
        "corpus_path": str(config.corpus_path),
        "contract_path": str(config.contract_path),
        "summary": {
            "entry_count": len(checked_entries),
            "checked_case_count": total_checked_cases,
            "error_count": len(errors),
            "minimum_text_chars": contract.get("minimum_text_chars"),
            "minimum_line_count": contract.get("minimum_line_count"),
            "minimum_pre_artifact_line_count": contract.get("minimum_pre_artifact_line_count"),
            "minimum_answer_section_chars": contract.get("minimum_answer_section_chars"),
            "minimum_answer_section_line_count": contract.get("minimum_answer_section_line_count"),
            "maximum_pre_answer_line_count": contract.get("maximum_pre_answer_line_count"),
        },
        "entries": checked_entries,
        "errors": errors,
    }
    write_json(config.output_path or default_report_path(config_root), report)
    return report
