from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    DEFAULT_POLICY_PATH,
    LargeContext500kCandidateRebaselineConfig,
    LargeContext500kCandidateRebaselineStatus,
    read_json_object,
    validate_large_context_500k_candidate_rebaseline,
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
    statuses = statuses or {phase: "Complete." for phase in ("266", "267", "268", "269", "270")}
    sections = ["500k-token project usability candidate"]
    for phase in ("266", "267", "268", "269", "270"):
        sections.extend(
            [
                f"### Approved Phase {phase}: Synthetic",
                "",
                f"Status: {statuses[phase]}",
                "",
            ]
        )
    write_doc(root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", sections)


def temp_config(
    tmp_path: Path,
    *,
    phase270_status: str = "Complete.",
    forbidden_marker: str | None = None,
) -> tuple[Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        markers = list(policy_value["required_doc_markers"].get(raw_path, []))
        if forbidden_marker and raw_path == "README.md":
            markers.append(forbidden_marker)
        write_doc(root / raw_path, markers)
    write_roadmap(
        root,
        statuses={
            "266": "Complete.",
            "267": "Complete.",
            "268": "Complete.",
            "269": "Complete.",
            "270": phase270_status,
        },
    )
    policy_path = root / "policy.json"
    write_json(policy_path, policy_value)
    return root, policy_path


def test_phase270_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase270_synthetic_config_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_large_context_500k_candidate_rebaseline(
        LargeContext500kCandidateRebaselineConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase270/report.json",
            markdown_output_path="runtime-state/phase270/report.md",
        )
    )

    assert report["status"] == LargeContext500kCandidateRebaselineStatus.PASSED.value
    assert report["summary"]["stable_estimated_project_tokens"] == 384_000
    assert report["summary"]["candidate_estimated_project_tokens"] == 500_000
    assert report["errors"] == []


def test_phase270_blocks_stable_500k_claim(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, forbidden_marker="500k is the stable release target")
    report = validate_large_context_500k_candidate_rebaseline(
        LargeContext500kCandidateRebaselineConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase270/report.json",
            markdown_output_path="runtime-state/phase270/report.md",
        )
    )

    assert report["status"] == LargeContext500kCandidateRebaselineStatus.FAILED.value
    assert any(item["source"] == "docs" and item["id"].endswith(".forbidden") for item in report["errors"])


def test_phase270_blocks_incomplete_roadmap_phase(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, phase270_status="Approved.")
    report = validate_large_context_500k_candidate_rebaseline(
        LargeContext500kCandidateRebaselineConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase270/report.json",
            markdown_output_path="runtime-state/phase270/report.md",
        )
    )

    assert report["status"] == LargeContext500kCandidateRebaselineStatus.FAILED.value
    assert any(item["id"] == "roadmap.phase270.status" for item in report["errors"])
