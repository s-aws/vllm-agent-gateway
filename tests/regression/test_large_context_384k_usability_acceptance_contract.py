from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_context_384k_usability_acceptance_contract import (
    DEFAULT_POLICY_PATH,
    LargeContext384kUsabilityAcceptanceContractConfig,
    LargeContext384kUsabilityAcceptanceContractStatus,
    read_json_object,
    validate_large_context_384k_usability_acceptance_contract,
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


def write_roadmap(root: Path, statuses: dict[str, str] | None = None) -> None:
    expected = {str(phase): "Complete." for phase in range(251, 259)}
    expected.update({str(phase): "Approved." for phase in range(259, 267)})
    if statuses:
        expected.update(statuses)
    titles = {
        258: "Large-Context 384k Usability Acceptance Contract",
        259: "384k Fixture And Index Readiness Proof",
        260: "384k Stale-Index Rejection Hardening",
        261: "Live 384k Acceptance Validator",
        262: "Targeted 384k Answer-Quality Repair",
        263: "Founder 384k Getting-Started Integration",
        264: "Clean-Clone 384k Usability Replay",
        265: "384k Release-Candidate Decision Gate",
        266: "Stable 384k Handoff Refresh",
    }
    sections: list[str] = []
    for phase in range(251, 267):
        sections.extend(
            [
                f"### Approved Phase {phase}: {titles.get(phase, 'Synthetic')}",
                "",
                f"Status: {expected[str(phase)]}",
                "",
            ]
        )
    write_doc(root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", sections)


def temp_config(tmp_path: Path, *, overrides: dict[str, str] | None = None) -> tuple[Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        write_doc(root / raw_path, policy_value["required_doc_markers"].get(raw_path, []))
    write_roadmap(root, overrides)
    for raw_path in policy_value["required_supporting_policies"]:
        write_json(root / raw_path, {"kind": Path(raw_path).stem})
    policy_path = root / "policy.json"
    write_json(policy_path, policy_value)
    return root, policy_path


def test_phase258_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase258_synthetic_config_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_large_context_384k_usability_acceptance_contract(
        LargeContext384kUsabilityAcceptanceContractConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase258/report.json",
            markdown_output_path="runtime-state/phase258/report.md",
        )
    )

    assert report["status"] == LargeContext384kUsabilityAcceptanceContractStatus.PASSED.value
    assert report["summary"]["target_estimated_project_tokens"] == 384_000
    assert report["summary"]["required_followup_phase_count"] == 8
    assert report["errors"] == []


def test_phase258_requires_stale_index_rejection() -> None:
    mutated = copy.deepcopy(policy())
    mutated["safety_requirements"]["stale_index_rejection_required"] = False

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.safety_requirements.stale_index_rejection_required" for item in errors)


def test_phase258_blocks_live_acceptance_before_stale_rejection() -> None:
    mutated = copy.deepcopy(policy())
    phase260 = mutated["required_phase_sequence"][2]
    assert phase260["phase"] == 260
    phase260["must_precede"] = [264, 265, 266]

    from vllm_agent_gateway.acceptance.large_context_384k_usability_acceptance_contract import phase_sequence_checks

    _, errors = phase_sequence_checks(mutated)

    assert any(item["id"] == "policy.required_phase_sequence.260.missing_precedence" for item in errors)


def test_phase258_rejects_unapproved_followup_status(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, overrides={"261": "Proposed."})
    report = validate_large_context_384k_usability_acceptance_contract(
        LargeContext384kUsabilityAcceptanceContractConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase258/report.json",
            markdown_output_path="runtime-state/phase258/report.md",
        )
    )

    assert report["status"] == LargeContext384kUsabilityAcceptanceContractStatus.FAILED.value
    assert any(item["id"] == "roadmap.phase261.status" for item in report["errors"])
