from __future__ import annotations

import copy
from pathlib import Path

import pytest

from vllm_agent_gateway.acceptance import large_context_384k_live_acceptance as phase261
from vllm_agent_gateway.acceptance.large_context_384k_live_acceptance import (
    DEFAULT_POLICY_PATH,
    LargeContext384kLiveAcceptanceConfig,
    LargeContext384kLiveAcceptanceStatus,
    read_json_object,
    validate_large_context_384k_live_acceptance,
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
    value["target_root"] = "target"
    value["protected_fixture_roots"] = ["fixture-a", "fixture-b"]
    for raw_path in value["required_docs"]:
        write_doc(root / raw_path, value["required_doc_markers"].get(raw_path, []))
    for relative in ("target/source.py", "fixture-a/README.md", "fixture-b/README.md"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")
    write_json(
        root / "runtime" / "large_context_usability_live_closeout_policy.json",
        {
            "baseline_cases": [
                {
                    "case_id": "P221-LC-001",
                    "category": "retrieval",
                    "prompt": "prompt",
                    "blind_baseline": {"scoring": ["score"]},
                }
            ],
            "holdout_cases": [],
        },
    )
    write_json(
        root / "runtime" / "chunked_investigation_executor_implementation_policy.json",
        {
            "chunked_prompt": "chunked prompt",
            "answer_contract": {"answer_first_required": True},
            "minimums": {"stage_count": 3},
        },
    )
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def prerequisite_reports() -> dict[str, dict]:
    return {
        "phase258": {"status": "passed", "summary": {"phase258_ready": True}},
        "phase259": {
            "status": "passed",
            "summary": {"phase260_ready": True, "estimated_indexed_token_count": 384000},
        },
        "phase260": {"status": "passed", "summary": {"phase261_ready": True}},
    }


def response(surface: str, strategy: str, case_id: str = "case") -> dict:
    return {
        "surface": surface,
        "case_id": case_id,
        "status": "passed",
        "score": 100,
        "selected_context_strategy": strategy,
        "run_id": f"{surface}-{strategy}-{case_id}",
        "errors": [],
    }


def small_repo(surface: str, root: str) -> dict:
    return {"surface": surface, "target_root": root, "status": "passed", "run_id": f"{surface}-{root}"}


def live_reports(*, include_chunked: bool = True) -> dict[str, dict]:
    phase221_responses = []
    for surface in ("gateway", "anythingllm"):
        for strategy in ("retrieval", "artifact_paging", "summarization", "refusal"):
            phase221_responses.append(response(surface, strategy, strategy))
    phase223_strategy = "chunked_investigation" if include_chunked else "retrieval"
    phase223_responses = [response(surface, phase223_strategy, "chunked") for surface in ("gateway", "anythingllm")]
    small = [small_repo(surface, root) for surface in ("gateway", "anythingllm") for root in ("a", "b")]
    return {
        "phase221": {
            "status": "passed",
            "responses": phase221_responses,
            "small_repo_regression_results": small,
            "summary": {
                "response_count": 16,
                "failed_response_count": 0,
                "small_repo_regression_count": 4,
                "failed_small_repo_regression_count": 0,
                "raw_prompt_stuffing_allowed": False,
            },
        },
        "phase223": {
            "status": "passed",
            "responses": phase223_responses,
            "small_repo_regression_results": small,
            "summary": {
                "response_count": 2,
                "failed_response_count": 0,
                "small_repo_regression_count": 4,
                "failed_small_repo_regression_count": 0,
                "raw_prompt_stuffing_allowed": False,
            },
        },
    }


def target_settings() -> dict:
    return {"status": "passed", "checks": {"generic_openai_base_path": True}, "errors": []}


def parity_pass() -> dict:
    return {"case_id": "P261-PARITY-001", "status": "passed", "errors": []}


def test_phase261_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase261_synthetic_gate_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase261, "run_precondition_reports", lambda config: prerequisite_reports())
    monkeypatch.setattr(phase261, "target_settings_result", lambda config, policy, api_key: target_settings())
    monkeypatch.setattr(phase261, "run_live_reports", lambda config, output_dir: live_reports())
    monkeypatch.setattr(phase261, "run_json_default_parity", lambda config, policy, target_root: parity_pass())

    report = validate_large_context_384k_live_acceptance(
        LargeContext384kLiveAcceptanceConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase261/report.json",
            markdown_output_path="runtime-state/phase261/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext384kLiveAcceptanceStatus.PASSED.value
    assert report["decision"] == "phase261_current_384k_live_acceptance_proof"
    assert report["summary"]["phase262_ready"] is True
    assert set(report["summary"]["strategy_ids"]) == {
        "retrieval",
        "artifact_paging",
        "summarization",
        "refusal",
        "chunked_investigation",
    }
    assert report["summary"]["json_default_parity_status"] == "passed"
    assert report["summary"]["critical_or_high_finding_count"] == 0


def test_phase261_rejects_missing_chunked_investigation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase261, "run_precondition_reports", lambda config: prerequisite_reports())
    monkeypatch.setattr(phase261, "target_settings_result", lambda config, policy, api_key: target_settings())
    monkeypatch.setattr(phase261, "run_live_reports", lambda config, output_dir: live_reports(include_chunked=False))
    monkeypatch.setattr(phase261, "run_json_default_parity", lambda config, policy, target_root: parity_pass())

    report = validate_large_context_384k_live_acceptance(
        LargeContext384kLiveAcceptanceConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase261/report.json",
            markdown_output_path="runtime-state/phase261/report.md",
            live=True,
        )
    )

    assert report["status"] == LargeContext384kLiveAcceptanceStatus.FAILED.value
    assert any(item["id"] == "live_reports.strategy_ids" for item in report["errors"])


def test_phase261_policy_rejects_post_384k_expansion() -> None:
    mutated = copy.deepcopy(policy())
    mutated["safety_requirements"]["post_384k_expansion_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.safety_requirements.post_384k_expansion_allowed" for item in errors)
