from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.release_candidate_ship_handoff import (
    ReleaseCandidateShipHandoffConfig,
    ReleaseCandidateShipHandoffStatus,
    validate_policy,
    validate_release_candidate_ship_handoff,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "release_candidate_ship_handoff_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_doc(path: Path, markers: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(markers or [])
    path.write_text(body + "\n", encoding="utf-8")


def release_proof(policy_value: dict) -> dict:
    expected = policy_value["expected_release_proof"]
    return {
        "schema_version": 1,
        "kind": expected["kind"],
        "status": expected["status"],
        "profile": expected["profile"],
        "proof_kind": expected["proof_kind"],
        "source_phase": expected["source_phase"],
        "source_report": policy_value["decision_source"]["phase244_decision_report"],
        "retention_reason": "runtime-state is local-only; stable validation needs committed metadata.",
        "known_boundary": "Advanced broad refactor orchestration remains deferred. Raw 1M-token prompt serving is not claimed.",
        "ship_decision": "ship",
        "decision_source": {
            "branch": expected["decision_source_branch"],
            "clone_path": expected["decision_source_clone_path"],
            "commit": expected["decision_source_commit"],
            "phase244_summary": {
                "decision": expected["phase244_decision"],
                "runtime_health_blocker_count": expected["phase244_runtime_health_blocker_count"],
                "machine_report_count": expected["phase244_machine_report_count"],
            },
        },
        "runtime_restoration": {
            "decision": expected["phase245_decision"],
            "gateway_run_id": expected["phase245_gateway_run_id"],
            "anythingllm_run_id": expected["phase245_anythingllm_run_id"],
        },
        "final_regression": {
            "command": "python3 -m pytest tests/regression/ -v",
            "result": expected["final_regression_result_contains"] + ", 4 skipped, 23 deselected",
        },
    }


def release_channels(policy_value: dict) -> dict:
    return {
        "schema_version": 1,
        "kind": "release_channel_manifest",
        "channels": [
            {"id": "dev", "status": "active"},
            {"id": "release-candidate", "status": "active"},
            {
                "id": "stable",
                "status": "active",
                "stable_readiness": {
                    **policy_value["expected_stable_readiness"],
                    "known_boundary": "Stable covers release-candidate ship proof. Advanced broad refactor orchestration remains deferred. Raw 1M-token prompt serving is not claimed.",
                },
            },
        ],
    }


def write_roadmap(root: Path, *, complete: bool = True) -> None:
    write_doc(
        root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md",
        [
            "### Approved Phase 247: Release-Candidate Ship Handoff",
            "",
            "Status: Complete." if complete else "Status: Approved.",
        ],
    )


def write_required_docs(root: Path, policy_value: dict, *, missing_marker_doc: str | None = None) -> None:
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        markers = list(policy_value["docs_required_markers"].get(raw_path, []))
        if raw_path == missing_marker_doc and markers:
            markers = markers[1:]
        markers.extend(policy_value["global_known_limit_markers"])
        write_doc(root / raw_path, markers)


def temp_config(
    tmp_path: Path,
    *,
    missing_release_proof: bool = False,
    stale_channel: bool = False,
    missing_marker_doc: str | None = None,
    incomplete_roadmap: bool = False,
) -> tuple[Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    write_roadmap(root, complete=not incomplete_roadmap)
    write_required_docs(root, policy_value, missing_marker_doc=missing_marker_doc)
    if not missing_release_proof:
        write_json(root / policy_value["required_release_proof"], release_proof(policy_value))
    channels = release_channels(policy_value)
    if stale_channel:
        channels["channels"][2]["stable_readiness"]["activated_by"] = "old_phase"
    write_json(root / policy_value["required_release_channel_manifest"], channels)
    policy_path = root / "policy.json"
    write_json(policy_path, policy_value)
    return root, policy_path


def test_phase247_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase247_synthetic_handoff_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_release_candidate_ship_handoff(
        ReleaseCandidateShipHandoffConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase247/report.json",
            markdown_output_path="runtime-state/phase247/report.md",
        )
    )

    assert report["status"] == ReleaseCandidateShipHandoffStatus.PASSED.value
    assert report["summary"]["ship_handoff_ready"] is True
    assert report["errors"] == []


def test_phase247_blocks_missing_release_proof(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, missing_release_proof=True)
    report = validate_release_candidate_ship_handoff(
        ReleaseCandidateShipHandoffConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase247/report.json",
            markdown_output_path="runtime-state/phase247/report.md",
        )
    )

    assert report["status"] == ReleaseCandidateShipHandoffStatus.FAILED.value
    assert any(item["id"] == "release_proof.missing" for item in report["errors"])


def test_phase247_blocks_stale_stable_channel(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, stale_channel=True)
    report = validate_release_candidate_ship_handoff(
        ReleaseCandidateShipHandoffConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase247/report.json",
            markdown_output_path="runtime-state/phase247/report.md",
        )
    )

    assert report["status"] == ReleaseCandidateShipHandoffStatus.FAILED.value
    assert any(item["id"] == "release_channel.stable_readiness.activated_by" for item in report["errors"])


def test_phase247_blocks_missing_doc_marker(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, missing_marker_doc="README.release-candidate-ship-handoff.md")
    report = validate_release_candidate_ship_handoff(
        ReleaseCandidateShipHandoffConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase247/report.json",
            markdown_output_path="runtime-state/phase247/report.md",
        )
    )

    assert report["status"] == ReleaseCandidateShipHandoffStatus.FAILED.value
    assert any(item["source"] == "docs" for item in report["errors"])


def test_phase247_blocks_incomplete_roadmap(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, incomplete_roadmap=True)
    report = validate_release_candidate_ship_handoff(
        ReleaseCandidateShipHandoffConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase247/report.json",
            markdown_output_path="runtime-state/phase247/report.md",
        )
    )

    assert report["status"] == ReleaseCandidateShipHandoffStatus.FAILED.value
    assert any(item["id"] == "roadmap.phase247.status" for item in report["errors"])


def test_phase247_project_gate_passes() -> None:
    report = validate_release_candidate_ship_handoff(
        ReleaseCandidateShipHandoffConfig(
            config_root=REPO_ROOT,
            output_path="runtime-state/phase247/project-report.json",
            markdown_output_path="runtime-state/phase247/project-report.md",
        )
    )

    assert report["status"] == ReleaseCandidateShipHandoffStatus.PASSED.value
