from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.model_swap_smoke_probe import (
    DEFAULT_POLICY_PATH,
    ModelSwapSmokeProbeConfig,
    build_decision,
    read_json_object,
    run_model_swap_smoke_probe,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH
EXPECTED_MODEL_ID = "Qwen3-Coder-30B-A3B-Instruct"


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def config(tmp_path: Path, *, current_policy_path: Path | None = None) -> ModelSwapSmokeProbeConfig:
    return ModelSwapSmokeProbeConfig(
        config_root=REPO_ROOT,
        current_model_policy_path=current_policy_path or Path("runtime/current_model_compatibility_matrix_policy.json"),
        output_path=tmp_path / "model-swap-smoke.json",
        markdown_output_path=tmp_path / "model-swap-smoke.md",
        compatibility_output_path=tmp_path / "compatibility.json",
        compatibility_markdown_output_path=tmp_path / "compatibility.md",
    )


def model_probe(model_ids: list[str] | None = None, *, status: str = "passed") -> dict[str, Any]:
    return {
        "status": status,
        "url": "http://127.0.0.1:8000/v1/models",
        "http_status": 200 if status == "passed" else 503,
        "model_ids": model_ids if model_ids is not None else [EXPECTED_MODEL_ID],
        "raw_kind": "list",
    }


def generation_probe(*, status: str = "passed") -> dict[str, Any]:
    return {
        "status": status,
        "model_id": EXPECTED_MODEL_ID,
        "content_sample": "SMOKE_OK" if status == "passed" else "",
        "content_length": 8 if status == "passed" else 0,
    }


def health_results(*, controller_status: str = "passed") -> list[dict[str, Any]]:
    return [
        {"name": "model", "status": "passed", "port": 8000},
        {"name": "llm_gateway", "status": "passed", "port": 8300},
        {"name": "workflow_router_gateway", "status": "passed", "port": 8500},
        {"name": "controller", "status": controller_status, "port": 8400},
    ]


def compatibility_report(*, status: str = "passed") -> dict[str, Any]:
    return {
        "kind": "current_model_compatibility_matrix_report",
        "status": status,
        "report_path": "/tmp/compatibility.json",
        "markdown_report_path": "/tmp/compatibility.md",
        "summary": {"model_profile_status": "warning"},
        "blockers": [] if status == "passed" else [{"code": "model_probe_mismatch"}],
        "errors": [] if status == "passed" else ["compatibility failed"],
    }


def run_with_mocks(
    tmp_path: Path,
    *,
    model_ids: list[str] | None = None,
    model_status: str = "passed",
    generation_status: str = "passed",
    controller_status: str = "passed",
    compatibility_status: str = "passed",
    current_policy_path: Path | None = None,
) -> dict[str, Any]:
    return run_model_swap_smoke_probe(
        config(tmp_path, current_policy_path=current_policy_path),
        model_probe_reader=lambda _base_url, _timeout: model_probe(model_ids, status=model_status),
        generation_probe_runner=lambda _base_url, _model_id, _timeout, _max_tokens: generation_probe(
            status=generation_status
        ),
        health_reader=lambda _timeout: health_results(controller_status=controller_status),
        compatibility_runner=lambda _config: compatibility_report(status=compatibility_status),
    )


def test_model_swap_smoke_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_model_swap_smoke_passes_for_expected_current_model(tmp_path: Path) -> None:
    report = run_with_mocks(tmp_path)

    assert report["status"] == "passed"
    assert report["summary"]["decision"] == "current_model_ready"
    assert report["summary"]["full_drift_gate_required"] is False
    assert report["decision"]["actual_model_ids"] == [EXPECTED_MODEL_ID]
    assert (tmp_path / "model-swap-smoke.md").exists()


def test_model_swap_smoke_detects_swapped_model_and_requires_drift_without_failing_probe(tmp_path: Path) -> None:
    report = run_with_mocks(tmp_path, model_ids=["Different-Local-Model"])

    assert report["status"] == "passed"
    assert report["summary"]["decision"] == "model_swap_requires_drift"
    assert report["summary"]["full_drift_gate_required"] is True
    assert report["decision"]["model_portability_gate_required"] is True
    assert "validate_fresh_local_model_drift.py" in report["decision"]["next_gate"]


def test_model_swap_smoke_fails_when_model_metadata_is_unavailable(tmp_path: Path) -> None:
    report = run_with_mocks(tmp_path, model_ids=[], model_status="failed")

    assert report["status"] == "failed"
    assert report["summary"]["decision"] == "fix_model_backend"
    assert report["errors"]


def test_model_swap_smoke_fails_when_harness_health_fails(tmp_path: Path) -> None:
    report = run_with_mocks(tmp_path, controller_status="failed")

    assert report["status"] == "failed"
    assert report["summary"]["decision"] == "fix_harness"
    assert report["summary"]["harness_health_passed"] is False


def test_model_swap_smoke_fails_when_generation_fails(tmp_path: Path) -> None:
    report = run_with_mocks(tmp_path, generation_status="failed")

    assert report["status"] == "failed"
    assert report["summary"]["decision"] == "fix_model_generation"
    assert report["summary"]["generation_probe_passed"] is False


def test_model_swap_smoke_fails_when_compatibility_artifacts_fail(tmp_path: Path) -> None:
    report = run_with_mocks(tmp_path, compatibility_status="failed")

    assert report["status"] == "failed"
    assert report["summary"]["decision"] == "refresh_current_model_evidence"
    assert report["summary"]["compatibility_artifacts_passed"] is False


def test_model_swap_smoke_fails_when_current_policy_has_no_expected_model_ids(tmp_path: Path) -> None:
    current_policy = read_json_object(REPO_ROOT / "runtime" / "current_model_compatibility_matrix_policy.json")
    current_policy["current_model"]["expected_model_ids"] = []
    current_policy_path = tmp_path / "current-model-policy.json"
    current_policy_path.write_text(json.dumps(current_policy), encoding="utf-8")

    report = run_with_mocks(tmp_path, current_policy_path=current_policy_path)

    assert report["status"] == "failed"
    assert "current_model_policy expected_model_ids must be non-empty" in report["errors"]


def test_model_swap_policy_rejects_automatic_model_selection_change() -> None:
    broken = copy.deepcopy(policy())
    broken["must_not"] = ["mutate model capability profile", "change runtime routing"]

    assert any("automatic model selection" in error for error in validate_policy(broken))


def test_build_decision_requires_exact_model_id_match_for_no_drift() -> None:
    decision = build_decision(
        expected_ids=[EXPECTED_MODEL_ID],
        model_probe=model_probe([EXPECTED_MODEL_ID, "extra-model"]),
        generation_probe=generation_probe(),
        health_results=health_results(),
        compatibility_report=compatibility_report(),
    )

    assert decision["decision"] == "model_swap_requires_drift"
    assert decision["full_drift_gate_required"] is True
