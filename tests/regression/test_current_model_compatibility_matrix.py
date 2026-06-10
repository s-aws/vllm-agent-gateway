from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.current_model_compatibility_matrix import (
    DEFAULT_POLICY_PATH,
    CurrentModelCompatibilityMatrixConfig,
    build_current_model_compatibility_matrix_report,
    load_sources,
    read_json_object,
    run_current_model_compatibility_matrix,
    validate_current_model_compatibility_matrix_report,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_sources() -> dict[str, tuple[Path | None, dict[str, Any] | None]]:
    sources, errors = load_sources(config_root=REPO_ROOT, policy=policy(), require_artifacts=True)
    assert errors == []
    return sources


def clone_sources() -> dict[str, tuple[Path | None, dict[str, Any] | None]]:
    return {
        source_id: (path, copy.deepcopy(payload))
        for source_id, (path, payload) in loaded_sources().items()
    }


def build_report(
    sources: dict[str, tuple[Path | None, dict[str, Any] | None]] | None = None,
) -> dict[str, Any]:
    return build_current_model_compatibility_matrix_report(
        policy=policy(),
        sources=sources or loaded_sources(),
        policy_path=POLICY_PATH,
    )


def blocker_codes(report: dict[str, Any]) -> set[str]:
    return {item["code"] for item in report["blockers"]}


def test_current_model_compatibility_matrix_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_current_model_compatibility_matrix_current_artifacts_pass(tmp_path: Path) -> None:
    output_path = tmp_path / "matrix.json"
    markdown_path = tmp_path / "matrix.md"

    report = run_current_model_compatibility_matrix(
        CurrentModelCompatibilityMatrixConfig(
            config_root=REPO_ROOT,
            output_path=output_path,
            markdown_output_path=markdown_path,
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["l1_prompt_family_count"] >= 20
    assert report["summary"]["l2_prompt_family_count"] >= 10
    assert report["summary"]["supported_prompt_family_count"] == report["summary"]["prompt_family_count"]
    assert report["summary"]["governed_output_format_count"] == 2
    assert report["summary"]["anythingllm_compatibility_status"] == "supported"
    assert report["summary"]["known_failure_mode_count"] == 14
    assert report["summary"]["model_profile_status"] == "warning"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Current-Model Compatibility Matrix")


def test_current_model_compatibility_matrix_rejects_missing_required_artifact() -> None:
    sources = clone_sources()
    sources["model_capability_profile"] = (None, None)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "missing_required_artifact" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_failed_model_profile() -> None:
    sources = clone_sources()
    path, profile = sources["model_capability_profile"]
    assert profile is not None
    profile["status"] = "failed"
    sources["model_capability_profile"] = (path, profile)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "source_status_not_allowed" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_model_probe_mismatch() -> None:
    sources = clone_sources()
    path, profile = sources["model_capability_profile"]
    assert profile is not None
    profile["candidate_model_probe"]["model_ids"] = ["unexpected-model"]  # type: ignore[index]
    sources["model_capability_profile"] = (path, profile)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "model_probe_mismatch" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_real_apply_approval() -> None:
    sources = clone_sources()
    path, profile = sources["model_capability_profile"]
    assert profile is not None
    profile["task_policy"]["real_apply"]["status"] = "approved"  # type: ignore[index]
    sources["model_capability_profile"] = (path, profile)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "task_policy_mismatch" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_missing_l2_prompt_support() -> None:
    sources = clone_sources()
    path, coverage = sources["prompt_skill_coverage"]
    assert coverage is not None
    coverage["entries"] = [entry for entry in coverage["entries"] if entry.get("level") != "L2"]  # type: ignore[index]
    sources["prompt_skill_coverage"] = (path, coverage)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "missing_supported_l2" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_failed_output_format_gate() -> None:
    sources = clone_sources()
    path, natural = sources["natural_output_format_preference"]
    assert natural is not None
    natural["status"] = "failed"
    sources["natural_output_format_preference"] = (path, natural)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "source_status_not_allowed" in blocker_codes(report)
    assert "output_format_not_supported" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_missing_anythingllm_evidence() -> None:
    sources = clone_sources()
    path, drift = sources["fresh_local_model_drift"]
    assert drift is not None
    drift["summary"]["required_routes"] = ["gateway"]  # type: ignore[index]
    sources["fresh_local_model_drift"] = (path, drift)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "anythingllm_not_supported" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_scorecard_blocker() -> None:
    sources = clone_sources()
    path, scorecard = sources["contextless_audit_scorecard"]
    assert scorecard is not None
    scorecard["status"] = "failed"
    scorecard["summary"]["hard_blocker_count"] = 1  # type: ignore[index]
    sources["contextless_audit_scorecard"] = (path, scorecard)

    report = build_report(sources)

    assert report["status"] == "failed"
    assert "source_status_not_allowed" in blocker_codes(report)
    assert "anythingllm_not_supported" in blocker_codes(report)


def test_current_model_compatibility_matrix_rejects_hidden_summary_edit() -> None:
    sources = loaded_sources()
    report = build_current_model_compatibility_matrix_report(
        policy=policy(),
        sources=sources,
        policy_path=POLICY_PATH,
    )
    report["summary"]["supported_prompt_family_count"] = 0

    errors = validate_current_model_compatibility_matrix_report(
        report,
        policy=policy(),
        sources=sources,
        policy_path=POLICY_PATH,
    )

    assert "report.summary must match rebuilt current-model compatibility matrix" in errors


def test_current_model_compatibility_matrix_policy_rejects_governed_format_as_not_governed() -> None:
    bad_policy = copy.deepcopy(policy())
    bad_policy["not_governed_output_formats"].append("json")

    errors = validate_policy(bad_policy)

    assert "not_governed_output_formats must not include governed formats" in errors
