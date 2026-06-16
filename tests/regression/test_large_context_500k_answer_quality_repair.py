from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_context_500k_answer_quality_repair import (
    DEFAULT_POLICY_PATH,
    LargeContext500kAnswerQualityRepairConfig,
    LargeContext500kAnswerQualityRepairStatus,
    read_json_object,
    validate_large_context_500k_answer_quality_repair,
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


def phase273_report(*, findings: int = 0, ready: bool = True) -> dict:
    return {
        "status": "passed" if ready else "failed",
        "summary": {
            "phase274_ready": ready,
            "critical_or_high_finding_count": findings,
            "error_count": 0 if ready else 1,
            "response_count": 18,
            "gateway_response_count": 9,
            "anythingllm_response_count": 9,
        },
    }


def temp_config(tmp_path: Path, *, write_phase273: bool = True, findings: int = 0, ready: bool = True) -> tuple[Path, Path]:
    root = tmp_path / "config"
    value = copy.deepcopy(policy())
    value["phase273_live_acceptance"]["report_path"] = "runtime-state/phase273/report.json"
    for raw_path in value["required_docs"]:
        write_doc(root / raw_path, value["required_doc_markers"].get(raw_path, []))
    if write_phase273:
        write_json(root / value["phase273_live_acceptance"]["report_path"], phase273_report(findings=findings, ready=ready))
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def test_phase274_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase274_no_repair_required_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_large_context_500k_answer_quality_repair(
        LargeContext500kAnswerQualityRepairConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase274/report.json",
            markdown_output_path="runtime-state/phase274/report.md",
        )
    )

    assert report["status"] == LargeContext500kAnswerQualityRepairStatus.PASSED.value
    assert report["decision"] == "no_repair_required"
    assert report["summary"]["phase275_ready"] is True


def test_phase274_rejects_missing_phase273_report(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, write_phase273=False)
    report = validate_large_context_500k_answer_quality_repair(
        LargeContext500kAnswerQualityRepairConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase274/report.json",
            markdown_output_path="runtime-state/phase274/report.md",
        )
    )

    assert report["status"] == LargeContext500kAnswerQualityRepairStatus.FAILED.value
    assert any(item["id"] == "phase273.report_missing" for item in report["errors"])


def test_phase274_rejects_critical_or_high_findings(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, findings=1)
    report = validate_large_context_500k_answer_quality_repair(
        LargeContext500kAnswerQualityRepairConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase274/report.json",
            markdown_output_path="runtime-state/phase274/report.md",
        )
    )

    assert report["status"] == LargeContext500kAnswerQualityRepairStatus.FAILED.value
    assert any(item["id"] == "phase273.critical_or_high_finding_count" for item in report["errors"])


def test_phase274_rejects_failed_phase273(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, ready=False)
    report = validate_large_context_500k_answer_quality_repair(
        LargeContext500kAnswerQualityRepairConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase274/report.json",
            markdown_output_path="runtime-state/phase274/report.md",
        )
    )

    assert report["status"] == LargeContext500kAnswerQualityRepairStatus.FAILED.value
    assert any(item["source"] == "phase273" for item in report["errors"])
