from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.clone_safe_model_capability_routing import (
    DEFAULT_POLICY_PATH,
    build_clone_safe_model_capability_routing_report,
    read_json_object,
    validate_clone_safe_model_capability_routing_report,
    validate_policy,
    validate_routing_and_profile,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict[str, Any]:
    return read_json_object(POLICY_PATH)


def test_phase235_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase235_static_project_report_passes_without_live_clean_handoff_requirement() -> None:
    report = build_clone_safe_model_capability_routing_report(
        config_root=REPO_ROOT,
        policy=policy(),
        policy_path=POLICY_PATH,
        require_clean_handoff_report=False,
    )

    assert report["status"] == "passed"
    assert report["decision"] == "clone_safe_routing_ready"
    assert report["summary"]["profile_path_uses_runtime_state"] is False


def test_phase235_rejects_runtime_state_profile_path() -> None:
    current_policy = policy()
    routing = {
        "kind": "model_capability_routing_policy",
        "enforcement_mode": "fail_closed",
        "default_profile_id": "localhost-8000-phase100-current",
        "profiles": [
            {
                "profile_id": "localhost-8000-phase100-current",
                "profile_path": "runtime-state/model-capability-profiles/phase100-current-profile.json",
            }
        ],
    }
    profile = {
        "kind": "model_capability_profile",
        "clone_safe": True,
        "status": "warning",
        "task_policy": {
            key: {"status": value}
            for key, value in current_policy["required_task_policies"].items()
        },
    }

    errors = validate_routing_and_profile(current_policy, routing, profile, REPO_ROOT / "runtime-state/model-capability-profiles/phase100-current-profile.json")

    assert "routing.profile_path.runtime_state" in {item["id"] for item in errors}
    assert "routing.profile_path.prefix" in {item["id"] for item in errors}


def test_phase235_requires_clean_handoff_when_configured(tmp_path: Path) -> None:
    current_policy = copy.deepcopy(policy())
    current_policy["clean_handoff_report_path"] = str(tmp_path / "missing.json")

    report = build_clone_safe_model_capability_routing_report(
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
        require_clean_handoff_report=True,
    )

    assert report["status"] == "failed"
    assert "clean_handoff.load" in {item["id"] for item in report["validation_errors"]}


def test_phase235_rejects_hidden_summary_edit() -> None:
    current_policy = policy()
    report = build_clone_safe_model_capability_routing_report(
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
        require_clean_handoff_report=False,
    )
    edited = copy.deepcopy(report)
    edited["summary"]["profile_clone_safe"] = False

    errors = validate_clone_safe_model_capability_routing_report(
        edited,
        config_root=REPO_ROOT,
        policy=current_policy,
        policy_path=POLICY_PATH,
        require_clean_handoff_report=False,
    )

    assert errors == ["report must match rebuilt clone-safe routing report"]
