from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance import release_candidate_runtime_health_restoration as gate
from vllm_agent_gateway.acceptance.release_candidate_runtime_health_restoration import (
    ReleaseCandidateRuntimeHealthRestorationConfig,
    RuntimeHealthRestorationDecision,
    validate_policy,
    validate_release_candidate_runtime_health_restoration,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "release_candidate_runtime_health_restoration_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def make_fixture(root: Path) -> None:
    (root / "core").mkdir(parents=True)
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "README.md").write_text("fixture readme\n", encoding="utf-8")
    (root / "core" / "stealth_order_manager.py").write_text("def find_stealth_order_by_placed_order_id():\n    pass\n", encoding="utf-8")
    (root / "tests" / "unit" / "test_order_id_and_followup_rules.py").write_text("def test_placeholder():\n    pass\n", encoding="utf-8")


def temp_policy(tmp_path: Path, *, one_fixture_missing: bool = False) -> tuple[Path, Path]:
    root = tmp_path / "config"
    first = tmp_path / "fixture-a"
    second = tmp_path / "fixture-b"
    make_fixture(first)
    if not one_fixture_missing:
        make_fixture(second)
    value = copy.deepcopy(policy())
    value["protected_fixture_roots"] = [str(first), str(second)]
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def fake_text() -> str:
    return "\n".join(
        [
            "workflow_router.plan completed",
            "run_id: workflow-router-20260614T000000000000Z",
            "- Selected workflow: code_investigation.plan",
            "find_stealth_order_by_placed_order_id",
            "Inputs:",
            "Outputs:",
            "Source mutation: False",
        ]
    )


def install_success_mocks(monkeypatch) -> None:
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
    monkeypatch.setattr(gate, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 200, "passed": True})

    def fake_json_request(url, *, payload=None, headers=None, timeout_seconds, method="POST"):
        if url.endswith("/api/v1/system"):
            return 200, {
                "settings": {
                    "LLMProvider": "generic-openai",
                    "LLMModel": "Qwen3-Coder-30B-A3B-Instruct",
                    "GenericOpenAiBasePath": "http://127.0.0.1:8500/v1",
                }
            }
        return 200, {"choices": [{"message": {"content": fake_text()}}]}

    monkeypatch.setattr(gate, "json_request", fake_json_request)


def test_phase245_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase245_synthetic_restored_when_health_target_chat_and_fixtures_pass(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = temp_policy(tmp_path)
    install_success_mocks(monkeypatch)

    report = validate_release_candidate_runtime_health_restoration(
        ReleaseCandidateRuntimeHealthRestorationConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase245/report.json",
        )
    )

    assert report["decision"] == RuntimeHealthRestorationDecision.RESTORED.value
    assert report["summary"]["runtime_health_blocker_count"] == 0
    assert report["summary"]["phase246_ready"] is True
    assert [case["status"] for case in report["cases"]] == ["passed", "passed"]


def test_phase245_blocks_when_runtime_health_fails(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = temp_policy(tmp_path)
    install_success_mocks(monkeypatch)
    monkeypatch.setattr(gate, "probe_url", lambda url, timeout_seconds: {"url": url, "status_code": 502, "passed": False})

    report = validate_release_candidate_runtime_health_restoration(
        ReleaseCandidateRuntimeHealthRestorationConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase245/report.json",
        )
    )

    assert report["decision"] == RuntimeHealthRestorationDecision.BLOCKED.value
    assert report["summary"]["runtime_health_blocker_count"] == len(policy()["required_runtime_health"])


def test_phase245_blocks_when_anythingllm_target_is_wrong(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = temp_policy(tmp_path)
    install_success_mocks(monkeypatch)

    def fake_json_request(url, *, payload=None, headers=None, timeout_seconds, method="POST"):
        if url.endswith("/api/v1/system"):
            return 200, {
                "settings": {
                    "LLMProvider": "generic-openai",
                    "LLMModel": "Qwen3-Coder-30B-A3B-Instruct",
                    "GenericOpenAiBasePath": "http://127.0.0.1:8300/v1",
                }
            }
        return 200, {"choices": [{"message": {"content": fake_text()}}]}

    monkeypatch.setattr(gate, "json_request", fake_json_request)
    report = validate_release_candidate_runtime_health_restoration(
        ReleaseCandidateRuntimeHealthRestorationConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase245/report.json",
        )
    )

    assert report["decision"] == RuntimeHealthRestorationDecision.BLOCKED.value
    assert any(item["id"] == "anythingllm.target_settings" for item in report["blockers"])


def test_phase245_blocks_when_minimal_chat_lacks_run_id(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = temp_policy(tmp_path)
    install_success_mocks(monkeypatch)

    def fake_json_request(url, *, payload=None, headers=None, timeout_seconds, method="POST"):
        if url.endswith("/api/v1/system"):
            return 200, {
                "settings": {
                    "LLMProvider": "generic-openai",
                    "LLMModel": "Qwen3-Coder-30B-A3B-Instruct",
                    "GenericOpenAiBasePath": "http://127.0.0.1:8500/v1",
                }
            }
        return 200, {"choices": [{"message": {"content": "workflow_router.plan completed\nInputs:\nOutputs:\nSource mutation: False"}}]}

    monkeypatch.setattr(gate, "json_request", fake_json_request)
    report = validate_release_candidate_runtime_health_restoration(
        ReleaseCandidateRuntimeHealthRestorationConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase245/report.json",
        )
    )

    assert report["decision"] == RuntimeHealthRestorationDecision.BLOCKED.value
    assert report["summary"]["passed_case_count"] == 0


def test_phase245_blocks_when_fixture_is_missing(tmp_path: Path, monkeypatch) -> None:
    root, policy_path = temp_policy(tmp_path, one_fixture_missing=True)
    install_success_mocks(monkeypatch)

    report = validate_release_candidate_runtime_health_restoration(
        ReleaseCandidateRuntimeHealthRestorationConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase245/report.json",
        )
    )

    assert report["decision"] == RuntimeHealthRestorationDecision.BLOCKED.value
    assert any(item["source"] == "fixture" for item in report["blockers"])
