from __future__ import annotations

import copy
from pathlib import Path

import vllm_agent_gateway.acceptance.large_context_500k_fixture_index_readiness as phase271
from vllm_agent_gateway.acceptance.large_context_500k_fixture_index_readiness import (
    DEFAULT_POLICY_PATH,
    LargeContext500kFixtureIndexReadinessConfig,
    LargeContext500kFixtureIndexReadinessStatus,
    read_json_object,
    validate_large_context_500k_fixture_index_readiness,
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


def temp_config(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "config"
    value = copy.deepcopy(policy())
    for raw_path in value["required_docs"]:
        write_doc(root / raw_path, value["required_doc_markers"].get(raw_path, []))
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def phase270_report(*, ready: bool = True) -> dict:
    return {
        "status": "passed" if ready else "failed",
        "summary": {
            "phase270_ready": ready,
            "stable_estimated_project_tokens": 384_000,
            "candidate_estimated_project_tokens": 500_000,
        },
    }


def phase259_report(*, corpus_tokens: int = 500_000, indexed_tokens: int = 500_000) -> dict:
    return {
        "status": "passed",
        "summary": {
            "phase260_ready": True,
            "target_estimated_project_tokens": 384_000,
            "corpus_estimated_token_count": corpus_tokens,
            "estimated_indexed_token_count": indexed_tokens,
            "indexed_file_count": 241,
            "chunk_count": 457,
        },
        "composed_report_summaries": {
            "phase214": {
                "estimated_token_count": corpus_tokens,
                "phase215_ready": True,
                "raw_1m_prompt_support_proven": False,
            },
            "phase217": {
                "estimated_indexed_token_count": indexed_tokens,
                "indexed_file_count": 241,
                "chunk_count": 457,
                "source_text_retention": "metadata_only",
                "store_source_text": False,
                "store_rejected_content": False,
            },
        },
    }


def test_phase271_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase271_synthetic_reports_pass(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase271, "run_phase270", lambda config_root: phase270_report())
    monkeypatch.setattr(phase271, "run_phase259", lambda config_root, *, bootstrap_composed_gates: phase259_report())

    report = validate_large_context_500k_fixture_index_readiness(
        LargeContext500kFixtureIndexReadinessConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase271/report.json",
            markdown_output_path="runtime-state/phase271/report.md",
            bootstrap_composed_gates=False,
        )
    )

    assert report["status"] == LargeContext500kFixtureIndexReadinessStatus.PASSED.value
    assert report["summary"]["candidate_estimated_project_tokens"] == 500_000
    assert report["summary"]["phase272_ready"] is True


def test_phase271_rejects_under_target_index(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase271, "run_phase270", lambda config_root: phase270_report())
    monkeypatch.setattr(
        phase271,
        "run_phase259",
        lambda config_root, *, bootstrap_composed_gates: phase259_report(indexed_tokens=499_999),
    )

    report = validate_large_context_500k_fixture_index_readiness(
        LargeContext500kFixtureIndexReadinessConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase271/report.json",
            markdown_output_path="runtime-state/phase271/report.md",
            bootstrap_composed_gates=False,
        )
    )

    assert report["status"] == LargeContext500kFixtureIndexReadinessStatus.FAILED.value
    assert any(item["id"] == "phase217.estimated_indexed_token_count" for item in report["errors"])


def test_phase271_rejects_under_target_corpus(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase271, "run_phase270", lambda config_root: phase270_report())
    monkeypatch.setattr(
        phase271,
        "run_phase259",
        lambda config_root, *, bootstrap_composed_gates: phase259_report(corpus_tokens=499_999),
    )

    report = validate_large_context_500k_fixture_index_readiness(
        LargeContext500kFixtureIndexReadinessConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase271/report.json",
            markdown_output_path="runtime-state/phase271/report.md",
            bootstrap_composed_gates=False,
        )
    )

    assert report["status"] == LargeContext500kFixtureIndexReadinessStatus.FAILED.value
    assert any(item["id"] == "phase214.estimated_token_count" for item in report["errors"])


def test_phase271_rejects_failed_phase270(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase271, "run_phase270", lambda config_root: phase270_report(ready=False))
    monkeypatch.setattr(phase271, "run_phase259", lambda config_root, *, bootstrap_composed_gates: phase259_report())

    report = validate_large_context_500k_fixture_index_readiness(
        LargeContext500kFixtureIndexReadinessConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase271/report.json",
            markdown_output_path="runtime-state/phase271/report.md",
            bootstrap_composed_gates=False,
        )
    )

    assert report["status"] == LargeContext500kFixtureIndexReadinessStatus.FAILED.value
    assert any(item["source"] == "phase270" for item in report["errors"])
