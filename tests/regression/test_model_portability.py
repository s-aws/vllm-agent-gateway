from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.model_portability import (
    ModelPortabilityConfig,
    ModelPortabilityIssue,
    acceptance_failure_records,
    classification_summary,
    run_model_portability,
)


def test_model_portability_classifies_common_harness_failures() -> None:
    report = {
        "errors": [
            "RuntimeError: ANYTHINGLLM_API_KEY is required",
            "RuntimeError: health check failed: []",
            "TimeoutError: timed out waiting for body bytes",
        ],
        "suite_runs": [],
    }

    records = acceptance_failure_records(report)
    summary = classification_summary(records)

    assert len(records) == 3
    assert summary[ModelPortabilityIssue.HARNESS.value] == 3
    assert all(record["recommended_next_action"] for record in records)


def test_model_portability_classifies_classifier_prompt_and_model_quality_misses() -> None:
    report = {
        "errors": [],
        "suite_runs": [
            {
                "id": "route_suite",
                "status": "failed",
                "description": "router proof",
                "stdout_tail": "expected_workflow code_investigation.plan but selected_workflow task.decompose",
                "stderr_tail": "",
                "returncode": 1,
            },
            {
                "id": "prompt_suite",
                "status": "failed",
                "description": "field prompt proof",
                "stdout_tail": "prompt_risk ambiguous request; suggested_prompt_if_missed included",
                "stderr_tail": "",
                "returncode": 1,
            },
            {
                "id": "semantic_suite",
                "status": "failed",
                "description": "semantic proof",
                "stdout_tail": "semantic_quality_status failed with missing_semantic_markers",
                "stderr_tail": "",
                "returncode": 1,
            },
        ],
    }

    summary = classification_summary(acceptance_failure_records(report))

    assert summary[ModelPortabilityIssue.CLASSIFIER.value] == 1
    assert summary[ModelPortabilityIssue.PROMPT.value] == 1
    assert summary[ModelPortabilityIssue.MODEL_QUALITY.value] == 1


def test_model_portability_offline_report_passes_when_v1_acceptance_passes(tmp_path: Path) -> None:
    acceptance_path = tmp_path / "acceptance.json"
    output_path = tmp_path / "portability.json"
    acceptance_path.write_text(
        json.dumps(
            {
                "kind": "v1_acceptance_report",
                "status": "passed",
                "profile": "release-candidate",
                "report_path": str(acceptance_path),
                "target_roots": ["/mnt/c/coinbase_testing_repo_frozen_tmp"],
                "suite_runs": [{"id": "representative_l1", "status": "passed"}],
                "errors": [],
                "founder_field_summary": {"status": "passed", "summary": {"passed": 34, "failed": 0}, "errors": []},
                "skill_library_health": {"status": "passed"},
            }
        ),
        encoding="utf-8",
    )

    report = run_model_portability(
        ModelPortabilityConfig(
            config_root=tmp_path,
            candidate_id="offline-pass-candidate",
            output_path=output_path,
            acceptance_report_path=acceptance_path,
            skip_live_acceptance=True,
            skip_model_probe=True,
        )
    )

    assert report["status"] == "passed"
    assert report["candidate"]["candidate_id"] == "offline-pass-candidate"
    assert report["acceptance_report"]["status"] == "passed"
    assert report["classification_summary"][ModelPortabilityIssue.UNKNOWN.value] == 0
    assert output_path.exists()


def test_model_portability_offline_report_fails_with_classified_acceptance_miss(tmp_path: Path) -> None:
    acceptance_path = tmp_path / "acceptance.json"
    output_path = tmp_path / "portability.json"
    acceptance_path.write_text(
        json.dumps(
            {
                "kind": "v1_acceptance_report",
                "status": "failed",
                "profile": "release-candidate",
                "report_path": str(acceptance_path),
                "target_roots": ["/mnt/c/coinbase_testing_repo_frozen_tmp"],
                "suite_runs": [
                    {
                        "id": "founder_field_prompts",
                        "status": "failed",
                        "description": "founder prompts",
                        "stdout_tail": "semantic_quality_status failed with missing_semantic_markers",
                        "stderr_tail": "",
                        "returncode": 1,
                    }
                ],
                "errors": ["RuntimeError: acceptance suite command failed"],
                "founder_field_summary": {"status": "failed", "summary": {"passed": 33, "failed": 1}, "errors": []},
                "skill_library_health": {"status": "passed"},
            }
        ),
        encoding="utf-8",
    )

    report = run_model_portability(
        ModelPortabilityConfig(
            config_root=tmp_path,
            candidate_id="offline-fail-candidate",
            output_path=output_path,
            acceptance_report_path=acceptance_path,
            skip_live_acceptance=True,
            skip_model_probe=True,
        )
    )

    assert report["status"] == "failed"
    assert report["classification_summary"][ModelPortabilityIssue.MODEL_QUALITY.value] >= 1
    assert any(record["classification"] == ModelPortabilityIssue.MODEL_QUALITY.value for record in report["classified_failures"])
