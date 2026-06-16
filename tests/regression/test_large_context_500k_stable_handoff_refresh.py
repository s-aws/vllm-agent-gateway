from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance import large_context_500k_stable_handoff_refresh as phase277
from vllm_agent_gateway.acceptance.large_context_500k_stable_handoff_refresh import (
    DEFAULT_POLICY_PATH,
    LargeContext500kStableHandoffRefreshConfig,
    read_json_object,
    validate_large_context_500k_stable_handoff_refresh,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        text
        or "\n".join(
            [
                "500k-token project usability",
                "governed context strategy",
                "raw 500k prompt serving is not claimed",
                "384k-token project usability baseline remains preserved",
                "PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH PASS",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_roadmap(config_root: Path, *, incomplete_phase: int | None = None) -> None:
    lines = []
    for phase in range(270, 277):
        lines.extend(
            [
                f"### Approved Phase {phase}: Synthetic Phase {phase}",
                "",
                "Status: Approved." if phase == incomplete_phase else "Status: Complete.",
                "",
            ]
        )
    write_doc(config_root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", "\n".join(lines))


def known_boundary() -> str:
    return (
        "Stable covers 500k-token project usability through governed context strategy. "
        "The 384k-token project usability baseline remains preserved. "
        "Advanced broad refactor orchestration remains deferred. "
        "Raw 500k prompt serving is not claimed. "
        "Raw 1M-token prompt serving is not claimed."
    )


def metadata_500k(**overrides: object) -> dict:
    data = {
        "decision": "ship",
        "decision_phase": 276,
        "decision_report": "runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json",
        "clean_clone_replay_phase": 275,
        "clean_clone_source_commit": "9dc768f0303ef2a57bad897beeffd3d537346dc2",
        "candidate_estimated_project_tokens": 500000,
        "previous_stable_estimated_project_tokens": 384000,
        "raw_prompt_stuffing_allowed": False,
        "raw_500k_prompt_serving_claimed": False,
        "governed_context_strategy_only": True,
        "phase277_ready": True,
    }
    data.update(overrides)
    return data


def metadata_384k() -> dict:
    return {
        "decision": "ship",
        "decision_phase": 265,
        "target_estimated_project_tokens": 384000,
        "phase266_ready": True,
        "post_384k_expansion_status": "superseded_by_500k_stable_handoff",
    }


def phase276_report(**summary_overrides: object) -> dict:
    summary = {
        "blocker_count": 0,
        "runtime_health_blocker_count": 0,
        "phase275_status": "passed",
        "phase275_decision": "phase275_clean_clone_500k_candidate_ready",
        "candidate_estimated_project_tokens": 500000,
        "stable_estimated_project_tokens": 384000,
        "phase273_response_count": 18,
        "phase273_gateway_response_count": 9,
        "phase273_anythingllm_response_count": 9,
        "phase273_critical_or_high_finding_count": 0,
        "phase273_json_default_parity_status": "passed",
        "raw_prompt_stuffing_allowed": False,
        "phase277_ready": True,
    }
    summary.update(summary_overrides)
    return {
        "kind": "large_context_500k_candidate_decision_gate_report",
        "status": "passed",
        "decision": "ship",
        "summary": summary,
        "blockers": [],
    }


def release_channels() -> dict:
    return {
        "schema_version": 1,
        "kind": "release_channel_manifest",
        "channels": [
            {
                "id": "stable",
                "status": "active",
                "stable_readiness": {
                    "known_boundary": known_boundary(),
                    "refreshed_at": "2026-06-16",
                    "refreshed_by": "phase277_stable_500k_handoff_refresh",
                    "refreshed_from_report": "runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json",
                    "large_context_384k_release_candidate": metadata_384k(),
                    "large_context_500k_project_usability": metadata_500k(),
                },
            }
        ],
    }


def stable_proof() -> dict:
    return {
        "kind": "v1_acceptance_report",
        "status": "passed",
        "known_boundary": known_boundary(),
        "stable_refresh": {
            "phase": 277,
            "refreshed_by": "phase277_stable_500k_handoff_refresh",
        },
        "large_context_384k_release_candidate": metadata_384k(),
        "large_context_500k_project_usability": metadata_500k(),
    }


def config_root(
    tmp_path: Path,
    *,
    incomplete_phase: int | None = None,
    missing_phase276: bool = False,
    phase276_summary_overrides: dict[str, object] | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    write_roadmap(root, incomplete_phase=incomplete_phase)
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        write_doc(root / raw_path)
    phase276_path = root / "runtime-state" / "phase276" / "phase276-report.json"
    if not missing_phase276:
        phase277.write_json(phase276_path, phase276_report(**(phase276_summary_overrides or {})))
    release_value = release_channels()
    proof_value = stable_proof()
    if metadata_overrides:
        release_value["channels"][0]["stable_readiness"]["large_context_500k_project_usability"].update(metadata_overrides)
        proof_value["large_context_500k_project_usability"].update(metadata_overrides)
    release_path = root / policy_value["required_release_channel_manifest"]
    proof_path = root / policy_value["required_stable_proof"]
    phase277.write_json(release_path, release_value)
    phase277.write_json(proof_path, proof_value)
    policy_path = root / "policy.json"
    phase277.write_json(policy_path, policy_value)
    return root, policy_path, phase276_path


def test_phase277_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase277_synthetic_passes_when_metadata_and_phase276_ship(tmp_path: Path) -> None:
    root, policy_path, phase276_path = config_root(tmp_path)

    report = validate_large_context_500k_stable_handoff_refresh(
        LargeContext500kStableHandoffRefreshConfig(
            config_root=root,
            policy_path=policy_path,
            phase276_report_path=phase276_path,
            output_path="runtime-state/phase277/report.json",
            markdown_output_path="runtime-state/phase277/report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["decision"] == "stable_500k_handoff_refreshed"
    assert report["summary"]["phase278_ready"] is True
    assert report["blockers"] == []


def test_phase277_rejects_missing_phase276_report(tmp_path: Path) -> None:
    root, policy_path, phase276_path = config_root(tmp_path, missing_phase276=True)

    report = validate_large_context_500k_stable_handoff_refresh(
        LargeContext500kStableHandoffRefreshConfig(
            config_root=root,
            policy_path=policy_path,
            phase276_report_path=phase276_path,
            output_path="runtime-state/phase277/report.json",
            markdown_output_path="runtime-state/phase277/report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "phase276.missing" for item in report["blockers"])


def test_phase277_rejects_non_ship_phase276(tmp_path: Path) -> None:
    root, policy_path, phase276_path = config_root(tmp_path)
    payload = phase276_report()
    payload["decision"] = "hold"
    phase277.write_json(phase276_path, payload)

    report = validate_large_context_500k_stable_handoff_refresh(
        LargeContext500kStableHandoffRefreshConfig(
            config_root=root,
            policy_path=policy_path,
            phase276_report_path=phase276_path,
            output_path="runtime-state/phase277/report.json",
            markdown_output_path="runtime-state/phase277/report.md",
        )
    )

    assert any(item["id"] == "phase276.decision" for item in report["blockers"])


def test_phase277_rejects_raw_500k_prompt_claim(tmp_path: Path) -> None:
    root, policy_path, phase276_path = config_root(
        tmp_path,
        metadata_overrides={"raw_500k_prompt_serving_claimed": True},
    )

    report = validate_large_context_500k_stable_handoff_refresh(
        LargeContext500kStableHandoffRefreshConfig(
            config_root=root,
            policy_path=policy_path,
            phase276_report_path=phase276_path,
            output_path="runtime-state/phase277/report.json",
            markdown_output_path="runtime-state/phase277/report.md",
        )
    )

    assert any("raw_500k_prompt_serving_claimed" in item["id"] for item in report["blockers"])


def test_phase277_rejects_incomplete_required_phase(tmp_path: Path) -> None:
    root, policy_path, phase276_path = config_root(tmp_path, incomplete_phase=276)

    report = validate_large_context_500k_stable_handoff_refresh(
        LargeContext500kStableHandoffRefreshConfig(
            config_root=root,
            policy_path=policy_path,
            phase276_report_path=phase276_path,
            output_path="runtime-state/phase277/report.json",
            markdown_output_path="runtime-state/phase277/report.md",
        )
    )

    assert any(item["id"] == "phase.276.status" for item in report["blockers"])
