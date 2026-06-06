from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import vllm_agent_gateway.acceptance.onboarding as onboarding
from vllm_agent_gateway.acceptance.onboarding import (
    OnboardingValidationConfig,
    validate_external_tester_onboarding,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_current_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / "runtime" / "external_tester_onboarding.json").read_text(encoding="utf-8"))


def test_external_tester_onboarding_pack_passes_current_contract(tmp_path: Path) -> None:
    report = validate_external_tester_onboarding(
        OnboardingValidationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "onboarding.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["failed_check_ids"] == []
    assert report["summary"]["case_count"] == 5
    assert report["summary"]["live_status"] == "skipped"
    assert Path(report["report_path"]).exists()


def test_external_tester_onboarding_rejects_deferred_advanced_prompt(tmp_path: Path) -> None:
    pack = load_current_pack()
    cases = pack["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    first["prompt"] = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, refactor the stealth lookup. "
        "Read only."
    )
    pack_path = write_json(tmp_path / "external_tester_onboarding.json", pack)

    report = validate_external_tester_onboarding(
        OnboardingValidationConfig(
            config_root=REPO_ROOT,
            pack_path=pack_path,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "failed"
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["case.ONB-001.contract"]["status"] == "failed"
    assert any("deferred or mutation-capable" in item for item in by_id["case.ONB-001.contract"]["details"]["errors"])


def test_external_tester_onboarding_live_mock_records_feedback(tmp_path: Path, monkeypatch) -> None:
    def fake_fixture_state(target_roots: tuple[str, ...]) -> dict[str, dict[str, object]]:
        return {target_root: {"hashes": {"core/stealth_order_manager.py": "same"}, "git_status": ""} for target_root in target_roots}

    def fake_json_request(
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: int,
    ) -> tuple[int, dict[str, Any]]:
        del headers, timeout_seconds
        if url.endswith("/api/ping"):
            return 200, {"online": True}
        if url.endswith("/api/v1/workspaces"):
            return 200, {"workspaces": [{"slug": "my-workspace"}]}
        if url.endswith("/api/v1/workspace/my-workspace/chat"):
            message = str((payload or {}).get("message") or "")
            if message.startswith("Record feedback for run workflow-router-"):
                return 200, {
                    "textResponse": (
                        "workflow_feedback.record completed\n"
                        "run_id: workflow-feedback-20260606T000000000000Z\n"
                        "target_run_id: workflow-router-20260606T000000000000Z\n"
                        "linked_run_found: true\n"
                        "feedback_record: /tmp/feedback-record.json"
                    )
                }
            return 200, {
                "textResponse": (
                    "I completed workflow_router.plan.\n"
                    "workflow_router.plan completed\n"
                    "run_id: workflow-router-20260606T000000000000Z\n"
                    "Result:\n"
                    "- Selected workflow: code_investigation.plan\n"
                    "Skill Selection:\n"
                    "Answer:\n"
                    "StealthOrderManager.find_stealth_order_by_placed_order_id\n"
                    "Inputs:\n"
                    "placed_order_id\n"
                    "Outputs:\n"
                    "Side effects:\n"
                    "Related tests:\n"
                    "Artifacts:\n"
                    "- downstream_code_explanation: /tmp/code-explanation.json"
                )
            }
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(onboarding, "fixture_state", fake_fixture_state)
    monkeypatch.setattr(onboarding, "json_request", fake_json_request)

    report = validate_external_tester_onboarding(
        OnboardingValidationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "live.json",
            live_anythingllm=True,
            include_feedback=True,
            case_ids=("ONB-001",),
        ),
        api_key="test-key",
    )

    assert report["status"] == "passed"
    assert report["summary"]["live_status"] == "passed"
    assert report["summary"]["live_case_count"] == 1
    assert report["summary"]["feedback_count"] == 1
    live_case = report["live"]["cases"][0]
    assert live_case["run_id"] == "workflow-router-20260606T000000000000Z"
    assert live_case["feedback_run_id"] == "workflow-feedback-20260606T000000000000Z"
