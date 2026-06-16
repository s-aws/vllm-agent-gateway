from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_context_384k_objective_rebaseline import (
    DEFAULT_POLICY_PATH,
    LargeContext384kObjectiveRebaselineConfig,
    LargeContext384kObjectiveRebaselineStatus,
    read_json_object,
    validate_large_context_384k_objective_rebaseline,
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


def write_threshold_json(path: Path, pointer: str, expected: object) -> None:
    parts = [part for part in pointer.strip("/").split("/") if part]
    payload: dict[str, object] = {}
    current = payload
    for part in parts[:-1]:
        child: dict[str, object] = {}
        current[part] = child
        current = child
    current[parts[-1]] = expected
    write_json(path, payload)


def write_roadmap(root: Path, statuses: dict[str, str] | None = None) -> None:
    statuses = statuses or {"249": "Complete.", "250": "Complete.", "251": "Complete."}
    sections = []
    sections.append("384k-token projects")
    for phase in ("249", "250", "251"):
        sections.extend(
            [
                f"### Approved Phase {phase}: Synthetic",
                "",
                f"Status: {statuses[phase]}",
                "",
            ]
        )
    write_doc(root / "docs" / "ACTIONABLE_WORKFLOW_ROADMAP.md", sections)


def temp_config(tmp_path: Path, *, threshold_override: int | None = None, phase251_status: str = "Complete.") -> tuple[Path, Path]:
    root = tmp_path / "config"
    policy_value = copy.deepcopy(policy())
    for raw_path in policy_value["required_docs"]:
        if raw_path == "docs/ACTIONABLE_WORKFLOW_ROADMAP.md":
            continue
        write_doc(root / raw_path, policy_value["required_doc_markers"].get(raw_path, []))
    write_roadmap(root, statuses={"249": "Complete.", "250": "Complete.", "251": phase251_status})
    for item in policy_value["required_thresholds"]:
        expected = threshold_override if threshold_override is not None and item["path"].endswith("large_corpus_context_budget_inventory_policy.json") else item["expected"]
        write_threshold_json(root / item["path"], item["json_pointer"], expected)
    policy_path = root / "policy.json"
    write_json(policy_path, policy_value)
    return root, policy_path


def test_phase251_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase251_synthetic_config_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_large_context_384k_objective_rebaseline(
        LargeContext384kObjectiveRebaselineConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase251/report.json",
            markdown_output_path="runtime-state/phase251/report.md",
        )
    )

    assert report["status"] == LargeContext384kObjectiveRebaselineStatus.PASSED.value
    assert report["summary"]["target_estimated_project_tokens"] == 384_000
    assert report["errors"] == []


def test_phase251_blocks_threshold_drift(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, threshold_override=1_000_000)
    report = validate_large_context_384k_objective_rebaseline(
        LargeContext384kObjectiveRebaselineConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase251/report.json",
            markdown_output_path="runtime-state/phase251/report.md",
        )
    )

    assert report["status"] == LargeContext384kObjectiveRebaselineStatus.FAILED.value
    assert any(item["source"] == "thresholds" for item in report["errors"])


def test_phase251_blocks_incomplete_roadmap_phase(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path, phase251_status="Approved.")
    report = validate_large_context_384k_objective_rebaseline(
        LargeContext384kObjectiveRebaselineConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase251/report.json",
            markdown_output_path="runtime-state/phase251/report.md",
        )
    )

    assert report["status"] == LargeContext384kObjectiveRebaselineStatus.FAILED.value
    assert any(item["id"] == "roadmap.phase251.status" for item in report["errors"])
