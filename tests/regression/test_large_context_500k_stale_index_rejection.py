from __future__ import annotations

import copy
from pathlib import Path

import vllm_agent_gateway.acceptance.large_context_500k_stale_index_rejection as phase272
from vllm_agent_gateway.acceptance.large_context_500k_stale_index_rejection import (
    DEFAULT_POLICY_PATH,
    LargeContext500kStaleIndexRejectionConfig,
    LargeContext500kStaleIndexRejectionStatus,
    read_json_object,
    validate_large_context_500k_stale_index_rejection,
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


def phase271_report(*, ready: bool = True) -> dict:
    return {
        "status": "passed" if ready else "failed",
        "summary": {
            "candidate_estimated_project_tokens": 500_000,
            "phase272_ready": ready,
        },
    }


def phase260_report(*, ready: bool = True, passed_case_count: int = 6) -> dict:
    return {
        "status": "passed" if ready else "failed",
        "summary": {
            "target_estimated_project_tokens": 384_000,
            "case_count": 6,
            "passed_case_count": passed_case_count,
            "phase261_ready": ready,
        },
        "case_results": [
            {"case_id": f"P260-STALENESS-{index:03d}", "passed": index <= passed_case_count}
            for index in range(1, 7)
        ],
    }


def test_phase272_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase272_synthetic_reports_pass(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase272, "run_phase271", lambda config_root: phase271_report())
    monkeypatch.setattr(phase272, "run_phase260", lambda config_root: phase260_report())

    report = validate_large_context_500k_stale_index_rejection(
        LargeContext500kStaleIndexRejectionConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase272/report.json",
            markdown_output_path="runtime-state/phase272/report.md",
        )
    )

    assert report["status"] == LargeContext500kStaleIndexRejectionStatus.PASSED.value
    assert report["summary"]["candidate_estimated_project_tokens"] == 500_000
    assert report["summary"]["phase273_ready"] is True


def test_phase272_rejects_failed_phase271(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase272, "run_phase271", lambda config_root: phase271_report(ready=False))
    monkeypatch.setattr(phase272, "run_phase260", lambda config_root: phase260_report())

    report = validate_large_context_500k_stale_index_rejection(
        LargeContext500kStaleIndexRejectionConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase272/report.json",
            markdown_output_path="runtime-state/phase272/report.md",
        )
    )

    assert report["status"] == LargeContext500kStaleIndexRejectionStatus.FAILED.value
    assert any(item["source"] == "phase271" for item in report["errors"])


def test_phase272_rejects_failed_stale_index_delegate(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase272, "run_phase271", lambda config_root: phase271_report())
    monkeypatch.setattr(phase272, "run_phase260", lambda config_root: phase260_report(ready=False))

    report = validate_large_context_500k_stale_index_rejection(
        LargeContext500kStaleIndexRejectionConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase272/report.json",
            markdown_output_path="runtime-state/phase272/report.md",
        )
    )

    assert report["status"] == LargeContext500kStaleIndexRejectionStatus.FAILED.value
    assert any(item["source"] == "phase260" for item in report["errors"])


def test_phase272_rejects_partial_case_pass(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    monkeypatch.setattr(phase272, "run_phase271", lambda config_root: phase271_report())
    monkeypatch.setattr(phase272, "run_phase260", lambda config_root: phase260_report(passed_case_count=5))

    report = validate_large_context_500k_stale_index_rejection(
        LargeContext500kStaleIndexRejectionConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase272/report.json",
            markdown_output_path="runtime-state/phase272/report.md",
        )
    )

    assert report["status"] == LargeContext500kStaleIndexRejectionStatus.FAILED.value
    assert any(item["id"] == "phase260.passed_case_count" for item in report["errors"])
