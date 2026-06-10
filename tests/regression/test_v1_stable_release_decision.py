from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1_stable_release_decision import (
    DEFAULT_POLICY_PATH,
    V1StableReleaseDecisionConfig,
    build_v1_stable_release_decision_report,
    load_sources,
    read_json_object,
    run_v1_stable_release_decision,
    validate_policy,
    validate_v1_stable_release_decision_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def loaded_sources() -> dict[str, tuple[Path | None, dict[str, Any]]]:
    sources, errors = load_sources(REPO_ROOT, policy(), require_artifacts=True)
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
    return build_v1_stable_release_decision_report(
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
    return validate_v1_stable_release_decision_report(
        report,
        config_root=REPO_ROOT,
        policy=policy_payload or policy(),
        sources=sources or loaded_sources(),
        load_errors=load_errors or [],
        policy_path=POLICY_PATH,
    )


def blocker_sources(report: dict[str, Any]) -> set[str]:
    return {str(item.get("source")) for item in report["release_blockers"]}


def test_v1_stable_release_decision_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_v1_stable_release_decision_passes(tmp_path: Path) -> None:
    report = run_v1_stable_release_decision(
        V1StableReleaseDecisionConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "decision.json",
            markdown_output_path=tmp_path / "decision.md",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] == "release_for_founder_testing"
    assert report["summary"]["release_blocker_count"] == 0
    assert "not_advanced_broad_refactor_orchestration" in report["release_limitations"]
    assert (tmp_path / "decision.md").exists()


def test_v1_stable_release_decision_blocks_unready_review() -> None:
    sources = cloned_sources()
    path, review = sources["v1_product_readiness_review"]
    review["recommendation"] = "no_go"
    review["status"] = "failed"
    sources["v1_product_readiness_review"] = (path, review)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert "v1_product_readiness_review" in blocker_sources(report)


def test_v1_stable_release_decision_blocks_model_swap_drift_requirement() -> None:
    sources = cloned_sources()
    path, model_swap = sources["model_swap_smoke_probe"]
    model_swap["decision"]["decision"] = "model_swap_requires_drift"
    sources["model_swap_smoke_probe"] = (path, model_swap)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert report["decision"] == "blocked"
    assert "model_swap_smoke_probe" in blocker_sources(report)


def test_v1_stable_release_decision_blocks_missing_source() -> None:
    sources = cloned_sources()
    sources["stable_proof"] = (Path("missing.json"), {})
    report = build_report(sources=sources, load_errors=["required report is missing: stable proof"])

    assert report["status"] == "failed"
    assert "input_loading" in blocker_sources(report)
    assert "stable_proof" in blocker_sources(report)


def test_v1_stable_release_decision_policy_rejects_missing_limitation() -> None:
    broken = copy.deepcopy(policy())
    broken["release_limitations"] = [
        item for item in broken["release_limitations"] if item != "not_automatic_model_selection"
    ]

    assert "policy.release_limitations must match the governed release limitations" in validate_policy(broken)
    report = build_report(policy_payload=broken)
    assert report["status"] == "failed"
    assert "not_automatic_model_selection" not in report["release_limitations"]


def test_v1_stable_release_decision_policy_rejects_missing_scope() -> None:
    broken = copy.deepcopy(policy())
    broken["release_scope"] = [
        item for item in broken["release_scope"] if item != "anythingllm_workflow_router_path"
    ]

    assert "policy.release_scope must match the governed release scope" in validate_policy(broken)
    report = build_report(policy_payload=broken)

    assert report["status"] == "failed"
    assert "anythingllm_workflow_router_path" not in report["release_scope"]


def test_v1_stable_release_decision_policy_requires_rollback_path() -> None:
    broken = copy.deepcopy(policy())
    broken["rollback_path"] = ""

    assert "policy.rollback_path must be a non-empty string" in validate_policy(broken)
    report = build_report(policy_payload=broken)

    assert report["status"] == "failed"
    assert report["rollback_path"] == ""


def test_v1_stable_release_decision_policy_requires_next_roadmap_batch() -> None:
    broken = copy.deepcopy(policy())
    broken["next_roadmap_batch"] = ""

    assert "policy.next_roadmap_batch must be a non-empty string" in validate_policy(broken)
    report = build_report(policy_payload=broken)

    assert report["status"] == "failed"
    assert report["next_roadmap_batch"] == ""


def test_v1_stable_release_decision_blocks_missing_final_marker() -> None:
    broken = copy.deepcopy(policy())
    broken["required_final_markers"].append("marker-that-does-not-exist")

    report = build_report(policy_payload=broken)

    assert report["status"] == "failed"
    assert "final_decision" in blocker_sources(report)


def test_v1_stable_release_decision_rejects_hidden_summary_edit() -> None:
    report = build_report()
    report["summary"]["release_blocker_count"] = 100

    assert "report must match rebuilt V1 stable release decision" in validate_report(report)


def test_v1_stable_release_decision_evidence_links_all_required_sources() -> None:
    report = build_report()

    assert set(report["source_refs"]) == {
        "model_swap_smoke_probe",
        "release_notes",
        "stable_chat_quality_release",
        "stable_proof",
        "stable_release_reset_rehearsal",
        "v1_product_readiness_review",
    }
    assert report["summary"]["evidence_link_count"] == 6


def test_v1_stable_release_decision_includes_release_closeout_fields() -> None:
    report = build_report()

    assert "stable reset rehearsal" in report["rollback_path"]
    assert "No approved incomplete phase remains" in report["next_roadmap_batch"]
    assert "rollback_path=" in report["decision_text"]
    assert "next_roadmap_batch=" in report["decision_text"]
