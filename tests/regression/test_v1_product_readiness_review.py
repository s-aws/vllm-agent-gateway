from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1_product_readiness_review import (
    DEFAULT_POLICY_PATH,
    V1ProductReadinessReviewConfig,
    build_v1_product_readiness_review_report,
    load_report_inputs,
    read_json_object,
    run_v1_product_readiness_review,
    validate_policy,
    validate_v1_product_readiness_review_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_sources() -> dict[str, tuple[Path | None, dict[str, Any]]]:
    sources, errors = load_report_inputs(REPO_ROOT, policy(), require_artifacts=True)
    assert errors == []
    return sources


def cloned_sources() -> dict[str, tuple[Path | None, dict[str, Any]]]:
    return {
        source_id: (path, copy.deepcopy(payload))
        for source_id, (path, payload) in loaded_sources().items()
    }


def build_report(
    *,
    policy_payload: dict[str, Any] | None = None,
    sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    load_errors: list[str] | None = None,
) -> dict[str, Any]:
    return build_v1_product_readiness_review_report(
        config_root=REPO_ROOT,
        policy=policy_payload or policy(),
        sources=sources or loaded_sources(),
        load_errors=load_errors or [],
        policy_path=POLICY_PATH,
    )


def validate_report(
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    load_errors: list[str] | None = None,
) -> list[str]:
    return validate_v1_product_readiness_review_report(
        report,
        config_root=REPO_ROOT,
        policy=policy_payload or policy(),
        sources=sources or loaded_sources(),
        load_errors=load_errors or [],
        policy_path=POLICY_PATH,
    )


def blocker_sources(report: dict[str, Any]) -> set[str]:
    return {str(item.get("source")) for item in report["release_blockers"]}


def test_v1_product_readiness_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_v1_product_readiness_review_passes(tmp_path: Path) -> None:
    report = run_v1_product_readiness_review(
        V1ProductReadinessReviewConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "review.json",
            markdown_output_path=tmp_path / "review.md",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["recommendation"] == "go_for_founder_testing"
    assert report["summary"]["release_blocker_count"] == 0
    assert report["summary"]["model_swap_decision"] == "current_model_ready"
    assert "advanced_broad_refactor_orchestration" in report["unsupported_workflows"]
    assert (tmp_path / "review.md").exists()


def test_v1_product_readiness_blocks_missing_required_report() -> None:
    sources = cloned_sources()
    sources["stable_release_reset_rehearsal"] = (Path("missing.json"), {})
    report = build_report(sources=sources, load_errors=["required report is missing: reset"])

    assert report["status"] == "failed"
    assert report["recommendation"] == "no_go"
    assert "stable_release_reset_rehearsal" in blocker_sources(report)
    assert "input_loading" in blocker_sources(report)


def test_v1_product_readiness_blocks_model_swap_requires_drift() -> None:
    sources = cloned_sources()
    path, model_swap = sources["model_swap_smoke_probe"]
    model_swap["decision"]["decision"] = "model_swap_requires_drift"
    model_swap["decision"]["full_drift_gate_required"] = True
    sources["model_swap_smoke_probe"] = (path, model_swap)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert report["recommendation"] == "no_go"
    assert "model_swap_smoke_probe" in blocker_sources(report)


def test_v1_product_readiness_blocks_unready_stable_release() -> None:
    sources = cloned_sources()
    path, stable = sources["stable_chat_quality_release"]
    stable["readiness"] = "blocked"
    stable["status"] = "failed"
    stable["summary"]["blocker_count"] = 1
    sources["stable_chat_quality_release"] = (path, stable)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert report["recommendation"] == "no_go"
    assert "stable_chat_quality_release" in blocker_sources(report)


def test_v1_product_readiness_policy_rejects_missing_unsupported_boundary() -> None:
    broken = copy.deepcopy(policy())
    broken["unsupported_workflows"] = [
        item for item in broken["unsupported_workflows"] if item != "automatic_model_selection"
    ]

    assert any("unsupported_workflows" in error for error in validate_policy(broken))


def test_v1_product_readiness_rejects_hidden_summary_edit() -> None:
    report = build_report()
    report["summary"]["release_blocker_count"] = 99

    errors = validate_report(report)

    assert "report must match rebuilt V1 product readiness review" in errors


def test_v1_product_readiness_blocks_missing_release_note_marker() -> None:
    broken = copy.deepcopy(policy())
    broken["required_evidence_markers"].append("marker-that-does-not-exist")

    report = build_report(policy_payload=broken)

    assert report["status"] == "failed"
    assert "release_notes" in blocker_sources(report)


def test_v1_product_readiness_tracks_monitored_risks() -> None:
    report = build_report()
    risk_ids = {item["id"] for item in report["monitored_risks"]}

    assert "fixture_scope_limited" in risk_ids
    assert "advanced_refactor_deferred" in risk_ids
    assert report["summary"]["monitored_risk_count"] >= 2
