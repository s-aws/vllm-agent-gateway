from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_context_384k_stale_index_rejection import (
    DEFAULT_POLICY_PATH,
    LargeContext384kStaleIndexRejectionConfig,
    LargeContext384kStaleIndexRejectionStatus,
    read_json_object,
    validate_large_context_384k_stale_index_rejection,
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


def temp_config(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "config"
    value = copy.deepcopy(policy())
    for raw_path in value["required_docs"]:
        write_doc(root / raw_path, value["required_doc_markers"].get(raw_path, []))
    runtime_policy = REPO_ROOT / "runtime" / "corpus_index_safety_governance_policy.json"
    write_json(root / "runtime" / "corpus_index_safety_governance_policy.json", read_json_object(runtime_policy))
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def test_phase260_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase260_synthetic_gate_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    report = validate_large_context_384k_stale_index_rejection(
        LargeContext384kStaleIndexRejectionConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase260/report.json",
            markdown_output_path="runtime-state/phase260/report.md",
            validate_phase259_precondition=False,
        )
    )

    assert report["status"] == LargeContext384kStaleIndexRejectionStatus.PASSED.value
    assert report["summary"]["case_count"] == 6
    assert report["summary"]["passed_case_count"] == 6
    assert report["summary"]["phase261_ready"] is True


def test_phase260_policy_rejects_serving_stale_evidence() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_fail_closed_properties"]["serve_stale_evidence_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_fail_closed_properties.serve_stale_evidence_allowed" for item in errors)
