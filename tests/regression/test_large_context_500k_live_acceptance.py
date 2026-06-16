from __future__ import annotations

import copy
from pathlib import Path

import vllm_agent_gateway.acceptance.large_context_500k_live_acceptance as phase273
from vllm_agent_gateway.acceptance.large_context_500k_live_acceptance import (
    DEFAULT_POLICY_PATH,
    LargeContext500kLiveAcceptanceConfig,
    LargeContext500kLiveAcceptanceStatus,
    read_json_object,
    validate_large_context_500k_live_acceptance,
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


def phase272_report(*, ready: bool = True) -> dict:
    return {
        "status": "passed" if ready else "failed",
        "summary": {
            "candidate_estimated_project_tokens": 500_000,
            "phase273_ready": ready,
            "phase260_case_count": 6,
            "phase260_passed_case_count": 6,
        },
    }


def phase261_report(*, ready: bool = True, include_chunked: bool = True) -> dict:
    strategies = ["retrieval", "artifact_paging", "summarization", "refusal"]
    if include_chunked:
        strategies.append("chunked_investigation")
    return {
        "status": "passed" if ready else "failed",
        "report_path": "runtime-state/phase273/phase273-phase261-report.json",
        "run_ids": {"phase221": ["gateway-retrieval"], "phase223": ["gateway-chunked"]},
        "summary": {
            "phase262_ready": ready,
            "strategy_ids": strategies,
            "response_count": 18,
            "gateway_response_count": 9,
            "anythingllm_response_count": 9,
            "target_settings_status": "passed",
            "json_default_parity_status": "passed",
            "critical_or_high_finding_count": 0,
            "raw_prompt_stuffing_allowed": False,
        },
    }


def test_phase273_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase273_synthetic_live_delegate_passes(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase273, "run_phase272", lambda config_root: phase272_report())
    monkeypatch.setattr(phase273, "run_phase261", lambda config, output_dir: phase261_report())

    report = validate_large_context_500k_live_acceptance(
        LargeContext500kLiveAcceptanceConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase273/report.json",
            markdown_output_path="runtime-state/phase273/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kLiveAcceptanceStatus.PASSED.value
    assert report["summary"]["candidate_estimated_project_tokens"] == 500_000
    assert report["summary"]["phase274_ready"] is True


def test_phase273_rejects_failed_phase272(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase273, "run_phase272", lambda config_root: phase272_report(ready=False))
    monkeypatch.setattr(phase273, "run_phase261", lambda config, output_dir: phase261_report())

    report = validate_large_context_500k_live_acceptance(
        LargeContext500kLiveAcceptanceConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase273/report.json",
            markdown_output_path="runtime-state/phase273/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kLiveAcceptanceStatus.FAILED.value
    assert any(item["source"] == "phase272" for item in report["errors"])


def test_phase273_rejects_failed_live_delegate(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase273, "run_phase272", lambda config_root: phase272_report())
    monkeypatch.setattr(phase273, "run_phase261", lambda config, output_dir: phase261_report(ready=False))

    report = validate_large_context_500k_live_acceptance(
        LargeContext500kLiveAcceptanceConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase273/report.json",
            markdown_output_path="runtime-state/phase273/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kLiveAcceptanceStatus.FAILED.value
    assert any(item["source"] == "phase261" for item in report["errors"])


def test_phase273_rejects_missing_strategy(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase273, "run_phase272", lambda config_root: phase272_report())
    monkeypatch.setattr(phase273, "run_phase261", lambda config, output_dir: phase261_report(include_chunked=False))

    report = validate_large_context_500k_live_acceptance(
        LargeContext500kLiveAcceptanceConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase273/report.json",
            markdown_output_path="runtime-state/phase273/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext500kLiveAcceptanceStatus.FAILED.value
    assert any(item["id"] == "phase261.strategy_ids" for item in report["errors"])


def test_phase273_policy_rejects_raw_500k_prompt_claim() -> None:
    mutated = copy.deepcopy(policy())
    mutated["safety_requirements"]["raw_500k_prompt_support_claim_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.safety_requirements.raw_500k_prompt_support_claim_allowed" for item in errors)
