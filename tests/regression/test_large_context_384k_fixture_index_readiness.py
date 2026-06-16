from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_context_384k_fixture_index_readiness import (
    DEFAULT_POLICY_PATH,
    LargeContext384kFixtureIndexReadinessConfig,
    LargeContext384kFixtureIndexReadinessStatus,
    read_json_object,
    validate_large_context_384k_fixture_index_readiness,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, markers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(markers) + "\n", encoding="utf-8")


def phase214_report(tokens: int = 384_000) -> dict:
    return {
        "kind": "large_corpus_context_budget_inventory_report",
        "status": "passed",
        "summary": {
            "estimated_token_count": tokens,
            "phase215_ready": True,
            "raw_1m_prompt_support_proven": False,
            "validation_error_count": 0,
        },
    }


def phase216_report() -> dict:
    return {
        "kind": "corpus_index_safety_governance_report",
        "status": "passed",
        "summary": {
            "negative_control_count": 13,
            "negative_control_passed_count": 13,
            "phase217_ready": True,
            "retention_source_text_copy_allowed": False,
            "artifact_rejected_content_allowed": False,
            "chat_visible_rejected_content_allowed": False,
            "validation_error_count": 0,
        },
    }


def phase217_report(tokens: int = 384_000) -> dict:
    return {
        "kind": "context_index_prototype_report",
        "status": "passed",
        "index_artifact_path": "",
        "summary": {
            "indexed_file_count": 220,
            "chunk_count": 220,
            "estimated_indexed_token_count": tokens,
            "query_smoke_case_count": 3,
            "query_smoke_passed_count": 3,
            "negative_control_count": 7,
            "negative_control_passed_count": 7,
            "phase218_ready": True,
            "source_text_retention": "metadata_only",
            "store_source_text": False,
            "store_rejected_content": False,
            "validation_error_count": 0,
        },
    }


def temp_config(tmp_path: Path, *, indexed_tokens: int = 384_000) -> tuple[Path, Path]:
    root = tmp_path / "config"
    value = copy.deepcopy(policy())
    for raw_path in value["required_docs"]:
        write_doc(root / raw_path, value["required_doc_markers"].get(raw_path, []))
    for fixture in ("coinbase-a", "coinbase-b"):
        fixture_root = root / fixture
        fixture_root.mkdir(parents=True)
        (fixture_root / "README.md").write_text(f"# {fixture}\n", encoding="utf-8")
    value["protected_fixture_roots"] = ["coinbase-a", "coinbase-b"]
    gates = value["composed_gates"]
    phase214_path = root / gates["large_corpus_inventory"]["report_path"]
    phase216_path = root / gates["corpus_index_safety"]["report_path"]
    phase217_path = root / gates["context_index"]["report_path"]
    index_path = root / "runtime-state" / "phase217" / "phase217-context-index.json"
    write_json(index_path, {"kind": "metadata_first_context_index"})
    p217 = phase217_report(indexed_tokens)
    p217["index_artifact_path"] = str(index_path)
    write_json(phase214_path, phase214_report())
    write_json(phase216_path, phase216_report())
    write_json(phase217_path, p217)
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def test_phase259_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase259_synthetic_reports_pass(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_large_context_384k_fixture_index_readiness(
        LargeContext384kFixtureIndexReadinessConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase259/report.json",
            markdown_output_path="runtime-state/phase259/report.md",
            bootstrap_composed_gates=False,
            validate_phase258_precondition=False,
        )
    )

    assert report["status"] == LargeContext384kFixtureIndexReadinessStatus.PASSED.value
    assert report["summary"]["estimated_indexed_token_count"] == 384_000
    assert report["summary"]["phase260_ready"] is True


def test_phase259_rejects_under_target_index(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, indexed_tokens=383_999)
    report = validate_large_context_384k_fixture_index_readiness(
        LargeContext384kFixtureIndexReadinessConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase259/report.json",
            markdown_output_path="runtime-state/phase259/report.md",
            bootstrap_composed_gates=False,
            validate_phase258_precondition=False,
        )
    )

    assert report["status"] == LargeContext384kFixtureIndexReadinessStatus.FAILED.value
    assert any(item["id"] == "phase217.estimated_indexed_token_count" for item in report["errors"])


def test_phase259_policy_requires_metadata_only() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_index_safety"]["store_source_text"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_index_safety.store_source_text" for item in errors)
