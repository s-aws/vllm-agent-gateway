from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1_product_readiness_reassessment import (
    DEFAULT_POLICY_PATH,
    V1ProductReadinessReassessmentConfig,
    build_v1_product_readiness_reassessment_report,
    load_report_inputs,
    read_json_object,
    run_v1_product_readiness_reassessment,
    validate_policy,
    validate_v1_product_readiness_reassessment_report,
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


def loaded_live_proof() -> tuple[Path | None, dict[str, Any]]:
    live_policy = policy()["required_live_runtime_proof"]
    path = REPO_ROOT / live_policy["path"]
    return path, read_json_object(path)


def build_report(
    *,
    policy_payload: dict[str, Any] | None = None,
    sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    live_proof: tuple[Path | None, dict[str, Any]] | None = None,
    load_errors: list[dict[str, str]] | None = None,
    live_proof_load_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    live_path, live_payload = live_proof or loaded_live_proof()
    return build_v1_product_readiness_reassessment_report(
        config_root=REPO_ROOT,
        policy=policy_payload or policy(),
        sources=sources or loaded_sources(),
        live_proof_path=live_path,
        live_proof=live_payload,
        load_errors=load_errors or [],
        live_proof_load_errors=live_proof_load_errors or [],
        policy_path=POLICY_PATH,
    )


def validate_report(
    report: dict[str, Any],
    *,
    policy_payload: dict[str, Any] | None = None,
    sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    live_proof: tuple[Path | None, dict[str, Any]] | None = None,
    load_errors: list[dict[str, str]] | None = None,
    live_proof_load_errors: list[dict[str, str]] | None = None,
) -> list[str]:
    live_path, live_payload = live_proof or loaded_live_proof()
    return validate_v1_product_readiness_reassessment_report(
        report,
        config_root=REPO_ROOT,
        policy=policy_payload or policy(),
        sources=sources or loaded_sources(),
        live_proof_path=live_path,
        live_proof=live_payload,
        load_errors=load_errors or [],
        live_proof_load_errors=live_proof_load_errors or [],
        policy_path=POLICY_PATH,
    )


def blocker_ids(report: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in report["release_blockers"]}


def test_v1_product_readiness_reassessment_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_project_v1_product_readiness_reassessment_passes(tmp_path: Path) -> None:
    report = run_v1_product_readiness_reassessment(
        V1ProductReadinessReassessmentConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "reassessment.json",
            markdown_output_path=tmp_path / "reassessment.md",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["recommendation"] == "release_for_broader_founder_beta"
    assert report["summary"]["release_blocker_count"] == 0
    assert report["summary"]["required_report_count"] == 9
    assert report["summary"]["phase195_prompt_case_count"] == 14
    assert "not_advanced_broad_refactor_orchestration" in report["release_limitations"]
    assert (tmp_path / "reassessment.md").exists()


def test_v1_product_readiness_reassessment_blocks_missing_required_report() -> None:
    sources = cloned_sources()
    sources["release_candidate_founder_trial_pack"] = (Path("missing.json"), {})
    report = build_report(
        sources=sources,
        load_errors=[
            {
                "id": "release_candidate_founder_trial_pack.missing",
                "source": "release_candidate_founder_trial_pack",
                "severity": "high",
                "message": "required report is missing",
            }
        ],
    )

    assert report["status"] == "failed"
    assert report["recommendation"] == "blocked_stale_or_invalid_evidence"
    assert "release_candidate_founder_trial_pack.missing" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_failed_report() -> None:
    sources = cloned_sources()
    path, phase192 = sources["chat_answer_scoring_v2"]
    phase192["status"] = "failed"
    phase192["summary"]["validation_error_count"] = 1
    sources["chat_answer_scoring_v2"] = (path, phase192)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "chat_answer_scoring_v2.status" in blocker_ids(report)
    assert "chat_answer_scoring_v2.validation_errors" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_phase195_without_fixture_state() -> None:
    sources = cloned_sources()
    path, phase195 = sources["release_candidate_founder_trial_pack"]
    phase195["fixture_state"]["validated"] = False
    sources["release_candidate_founder_trial_pack"] = (path, phase195)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "phase195.fixture_state" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_phase195_without_proof_mode() -> None:
    sources = cloned_sources()
    path, phase195 = sources["release_candidate_founder_trial_pack"]
    phase195["proof_artifact_mode"]["enabled_for_this_run"] = False
    sources["release_candidate_founder_trial_pack"] = (path, phase195)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "phase195.proof_artifact_mode" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_missing_live_proof() -> None:
    report = build_report(
        live_proof=(Path("missing-live-proof.json"), {}),
        live_proof_load_errors=[
            {
                "id": "live_runtime_proof.missing",
                "source": "live_runtime_proof",
                "severity": "high",
                "message": "required live runtime proof is missing",
            }
        ],
    )

    assert report["status"] == "failed"
    assert "live_runtime_proof.missing" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_live_proof_without_anythingllm_run_ids() -> None:
    live_path, live_payload = loaded_live_proof()
    broken = copy.deepcopy(live_payload)
    broken["run_ids"]["anythingllm"] = []

    report = build_report(live_proof=(live_path, broken))

    assert report["status"] == "failed"
    assert "live_runtime_proof.run_ids.anythingllm" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_wrong_anythingllm_target() -> None:
    live_path, live_payload = loaded_live_proof()
    broken = copy.deepcopy(live_payload)
    broken["anythingllm_target_url"] = "http://127.0.0.1:8300/v1"

    report = build_report(live_proof=(live_path, broken))

    assert report["status"] == "failed"
    assert "live_runtime_proof.anythingllm_target_url" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_phase192_failed_cases() -> None:
    sources = cloned_sources()
    path, phase192 = sources["chat_answer_scoring_v2"]
    phase192["summary"]["failed_case_count"] = 1
    sources["chat_answer_scoring_v2"] = (path, phase192)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "phase192.failed_cases" in blocker_ids(report)


def test_v1_product_readiness_reassessment_blocks_phase194_promotion_without_proof() -> None:
    sources = cloned_sources()
    path, phase194 = sources["skill_authoring_pipeline_v2"]
    phase194["summary"]["promotion_eligible"] = True
    sources["skill_authoring_pipeline_v2"] = (path, phase194)

    report = build_report(sources=sources)

    assert report["status"] == "failed"
    assert "phase194.promotion_boundary" in blocker_ids(report)


def test_v1_product_readiness_reassessment_policy_rejects_missing_limitation() -> None:
    broken = copy.deepcopy(policy())
    broken["release_limitations"] = [
        item for item in broken["release_limitations"] if item != "not_automatic_model_selection"
    ]

    errors = validate_policy(broken)

    assert any(error["id"] == "policy.release_limitations" for error in errors)


def test_v1_product_readiness_reassessment_rejects_hidden_summary_edit() -> None:
    report = build_report()
    report["summary"]["release_blocker_count"] = 99

    errors = validate_report(report)

    assert "report must match rebuilt V1 product readiness reassessment" in errors


def test_v1_product_readiness_reassessment_tracks_advisories() -> None:
    report = build_report()
    advisory_ids = {item["id"] for item in report["advisories"]}

    assert "phase192_advisory_cases" in advisory_ids
    assert "phase194_draft_only" in advisory_ids
    assert "advanced_refactor_deferred" in advisory_ids
