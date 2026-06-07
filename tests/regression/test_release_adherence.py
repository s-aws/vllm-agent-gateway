from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.model_capability_profile import CapabilityStatus
from vllm_agent_gateway.acceptance.release_adherence import (
    FindingSeverity,
    REQUIRED_V1_1_SUITE_IDS,
    ReleaseAdherenceConfig,
    ReleaseAdherenceFailureClass,
    classify_message,
    run_release_adherence,
)


def write_report(path: Path, report: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    report["report_path"] = str(path.resolve())
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def passing_acceptance_report(path: Path, *, include_durations: bool = True) -> dict:
    suite_runs = [{"id": suite_id, "status": "passed", "returncode": 0} for suite_id in sorted(REQUIRED_V1_1_SUITE_IDS)]
    if include_durations:
        for index, item in enumerate(suite_runs, start=1):
            item["duration_seconds"] = float(index)
    return write_report(
        path,
        {
            "kind": "v1_acceptance_report",
            "status": "passed",
            "profile": "v1.1-release-candidate",
            "target_roots": ["/mnt/c/coinbase_testing_repo_frozen_tmp", "/mnt/c/coinbase_testing_repo_frozen_tmp.github"],
            "health": [
                {"name": name, "status": "passed", "http_status": 200}
                for name in (
                    "model",
                    "llm_gateway",
                    "workflow_router_gateway",
                    "controller",
                    "reviewer_code",
                    "tester_code",
                    "architect_default",
                    "dispatcher_default",
                    "implementer_default",
                    "researcher_default",
                    "documenter_default",
                )
            ],
            "suite_runs": suite_runs,
            "json_output": [
                {"target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp"},
                {"target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github"},
            ],
            "feedback": [
                {"target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp"},
                {"target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github"},
            ],
            "fixture_state": {
                "/mnt/c/coinbase_testing_repo_frozen_tmp": {"git_status": None},
                "/mnt/c/coinbase_testing_repo_frozen_tmp.github": {"git_status": {"clean": False, "line_count": 411}},
            },
            "model_portability": {
                "status": "passed",
                "candidate_model_probe": {"status": "passed", "model_ids": ["qwen-local"]},
            },
            "errors": [],
        },
    )


def passing_ui_report(path: Path) -> dict:
    return write_report(
        path,
        {
            "kind": "anythingllm_ui_e2e_report",
            "status": "passed",
            "fixture_unchanged": True,
            "ui": {
                "cases": [
                    {
                        "case_id": "L1-001",
                        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
                        "status": "passed",
                        "semantic_status": "passed",
                    },
                    {
                        "case_id": "L1-002",
                        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
                        "status": "passed",
                        "semantic_status": "passed",
                    },
                    {
                        "case_id": "L1-001",
                        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                        "status": "passed",
                        "semantic_status": "passed",
                    },
                    {
                        "case_id": "L1-002",
                        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                        "status": "passed",
                        "semantic_status": "passed",
                    },
                ]
            },
            "errors": [],
        },
    )


def passing_portability_report(path: Path, acceptance_path: Path) -> dict:
    return write_report(
        path,
        {
            "kind": "model_portability_report",
            "status": "passed",
            "candidate": {"candidate_id": "current-localhost-model"},
            "candidate_model_probe": {"status": "passed", "model_ids": ["qwen-local"]},
            "acceptance_report_path": str(acceptance_path),
            "classification_summary": {"harness": 0, "classifier": 0, "prompt": 0, "model_quality": 0, "unknown": 0},
            "classified_failures": [],
        },
    )


def warning_profile(path: Path, markdown_path: Path, *, latency_status: str = "proven") -> dict:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("# profile\n", encoding="utf-8")
    return write_report(
        path,
        {
            "kind": "model_capability_profile",
            "status": "warning",
            "markdown_report_path": str(markdown_path.resolve()),
            "capabilities": {
                "route_stability": {"status": "proven"},
                "output_contract_reliability": {"status": "proven"},
                "semantic_answer_quality": {"status": "proven"},
                "latency": {"status": latency_status},
                "timeout_behavior": {"status": "proven"},
                "safe_apply_readiness": {"status": "partially_proven"},
            },
            "task_policy": {
                "read_only_l1": {"status": "approved"},
                "l2_read_only": {"status": "approved"},
                "real_apply": {"status": "not_approved"},
            },
        },
    )


def test_release_adherence_passes_with_warning_justified_by_real_apply_boundary(tmp_path: Path) -> None:
    output_path = tmp_path / "release-adherence.json"

    def acceptance_runner(config):
        assert config.profile.value == "v1.1-release-candidate"
        return passing_acceptance_report(config.output_path)

    def ui_runner(config):
        return passing_ui_report(config.output_path)

    def portability_runner(config):
        assert config.skip_live_acceptance is True
        return passing_portability_report(config.output_path, config.acceptance_report_path)

    def profile_runner(config):
        return warning_profile(config.output_path, config.markdown_output_path)

    report = run_release_adherence(
        ReleaseAdherenceConfig(config_root=tmp_path, output_path=output_path),
        acceptance_runner=acceptance_runner,
        ui_runner=ui_runner,
        portability_runner=portability_runner,
        profile_runner=profile_runner,
    )

    assert report["status"] == "passed"
    assert report["readiness_status"] == "releasable"
    assert report["summary"]["acceptance"]["model_ids"] == ["qwen-local"]
    assert report["summary"]["latency"]["latency_measured"] is True
    assert report["summary"]["finding_counts"]["by_severity"][FindingSeverity.BLOCKER.value] == 0
    assert report["summary"]["finding_counts"]["by_severity"][FindingSeverity.WARNING.value] == 1
    assert "safe apply is intentionally partial" in report["summary"]["model_capability_profile"]["warning_justification"]
    assert report["summary"]["acceptance"]["health_count"] == 11
    assert report["summary"]["ui"]["case_count"] == 4
    assert output_path.exists()
    assert Path(report["markdown_report_path"]).exists()
    assert "unchanged during run, not pristine" in Path(report["markdown_report_path"]).read_text(encoding="utf-8")


def test_release_adherence_blocks_failed_ui_semantic_case(tmp_path: Path) -> None:
    output_path = tmp_path / "release-adherence.json"

    def ui_runner(config):
        report = passing_ui_report(config.output_path)
        report["status"] = "failed"
        report["errors"] = ["AnythingLLM browser UI validation failed"]
        report["ui"]["cases"][0]["status"] = "failed"
        report["ui"]["cases"][0]["semantic_status"] = "failed"
        report["ui"]["cases"][0]["missing_required_markers"] = ["Beginning point:"]
        return write_report(config.output_path, report)

    report = run_release_adherence(
        ReleaseAdherenceConfig(config_root=tmp_path, output_path=output_path),
        acceptance_runner=lambda config: passing_acceptance_report(config.output_path),
        ui_runner=ui_runner,
        portability_runner=lambda config: passing_portability_report(config.output_path, config.acceptance_report_path),
        profile_runner=lambda config: warning_profile(config.output_path, config.markdown_output_path),
    )

    assert report["status"] == "failed"
    assert report["readiness_status"] == "blocked"
    assert any(item["classification"] == ReleaseAdherenceFailureClass.SEMANTIC_QUALITY.value for item in report["findings"])


def test_release_adherence_blocks_unknown_latency_profile(tmp_path: Path) -> None:
    report = run_release_adherence(
        ReleaseAdherenceConfig(config_root=tmp_path, output_path=tmp_path / "release-adherence.json"),
        acceptance_runner=lambda config: passing_acceptance_report(config.output_path, include_durations=False),
        ui_runner=lambda config: passing_ui_report(config.output_path),
        portability_runner=lambda config: passing_portability_report(config.output_path, config.acceptance_report_path),
        profile_runner=lambda config: warning_profile(
            config.output_path,
            config.markdown_output_path,
            latency_status=CapabilityStatus.UNKNOWN.value,
        ),
    )

    assert report["status"] == "failed"
    assert any(item["source"] == "model_capability_profile.latency" for item in report["findings"])
    assert any(item["classification"] == ReleaseAdherenceFailureClass.LATENCY.value for item in report["findings"])


def test_release_adherence_blocks_partial_profile_warning_not_caused_by_real_apply_only(tmp_path: Path) -> None:
    def profile_runner(config):
        report = warning_profile(config.output_path, config.markdown_output_path)
        report["capabilities"]["route_stability"]["status"] = "partially_proven"
        return write_report(config.output_path, report)

    report = run_release_adherence(
        ReleaseAdherenceConfig(config_root=tmp_path, output_path=tmp_path / "release-adherence.json"),
        acceptance_runner=lambda config: passing_acceptance_report(config.output_path),
        ui_runner=lambda config: passing_ui_report(config.output_path),
        portability_runner=lambda config: passing_portability_report(config.output_path, config.acceptance_report_path),
        profile_runner=profile_runner,
    )

    assert report["status"] == "failed"
    warning = next(item for item in report["findings"] if item["source"] == "model_capability_profile.warning")
    assert warning["severity"] == FindingSeverity.BLOCKER.value


def test_release_adherence_blocks_missing_required_acceptance_evidence(tmp_path: Path) -> None:
    def acceptance_runner(config):
        report = passing_acceptance_report(config.output_path)
        report["suite_runs"] = [item for item in report["suite_runs"] if item["id"] != "run_observability"]
        return write_report(config.output_path, report)

    report = run_release_adherence(
        ReleaseAdherenceConfig(config_root=tmp_path, output_path=tmp_path / "release-adherence.json"),
        acceptance_runner=acceptance_runner,
        ui_runner=lambda config: passing_ui_report(config.output_path),
        portability_runner=lambda config: passing_portability_report(config.output_path, config.acceptance_report_path),
        profile_runner=lambda config: warning_profile(config.output_path, config.markdown_output_path),
    )

    assert report["status"] == "failed"
    assert any(item["source"] == "v1_acceptance.required_suites" for item in report["findings"])


def test_release_adherence_blocks_model_probe_failure_from_portability_report(tmp_path: Path) -> None:
    def portability_runner(config):
        report = passing_portability_report(config.output_path, config.acceptance_report_path)
        report["status"] = "failed"
        report["candidate_model_probe"] = {"status": "failed", "error": "connection refused", "model_ids": []}
        return write_report(config.output_path, report)

    report = run_release_adherence(
        ReleaseAdherenceConfig(config_root=tmp_path, output_path=tmp_path / "release-adherence.json"),
        acceptance_runner=lambda config: passing_acceptance_report(config.output_path),
        ui_runner=lambda config: passing_ui_report(config.output_path),
        portability_runner=portability_runner,
        profile_runner=lambda config: warning_profile(config.output_path, config.markdown_output_path),
    )

    assert report["status"] == "failed"
    assert any(item["source"] == "model_portability.candidate_model_probe" for item in report["findings"])


def test_release_adherence_classifies_common_failure_terms() -> None:
    assert classify_message("selected_workflow was wrong")[0] == ReleaseAdherenceFailureClass.ROUTE
    assert classify_message("missing_semantic_markers in UI")[0] == ReleaseAdherenceFailureClass.SEMANTIC_QUALITY
    assert classify_message("protected fixture state changed")[0] == ReleaseAdherenceFailureClass.FIXTURE_MUTATION
