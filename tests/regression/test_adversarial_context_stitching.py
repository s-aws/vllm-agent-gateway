from __future__ import annotations

import copy
from pathlib import Path

import vllm_agent_gateway.acceptance.adversarial_context_stitching as phase278
from vllm_agent_gateway.acceptance.adversarial_context_stitching import (
    DEFAULT_POLICY_PATH,
    AdversarialContextStitchingConfig,
    AdversarialContextStitchingStatus,
    FixtureMode,
    build_corpus,
    expected_answer,
    prompt_for_corpus,
    read_json_object,
    score_answer,
    validate_adversarial_context_stitching,
    validate_policy,
    write_json,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
    latest_user_message_text,
)
from vllm_agent_gateway.controllers.workflow_router.plan import (
    SUPPLIED_CORPUS_QA_STATUS,
    is_supplied_corpus_qa_request,
    workflow_kind_for_request,
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
    policy_path = root / "policy.json"
    write_json(policy_path, value)
    return root, policy_path


def test_phase278_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase278_fixture_gate_passes(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)

    report = validate_adversarial_context_stitching(
        AdversarialContextStitchingConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase278/report.json",
            markdown_output_path="runtime-state/phase278/report.md",
            fixture_dir="runtime-state/phase278/fixture",
        )
    )

    assert report["status"] == AdversarialContextStitchingStatus.PASSED.value
    assert report["summary"]["fixture_mode_count"] == 3
    assert report["summary"]["expected_answer_hard_failure_count"] == 0
    assert Path(report["summary"]["standard_prompt_path"]).is_file()


def test_phase278_scores_expected_answer() -> None:
    score = score_answer(expected_answer())

    assert score["status"] == AdversarialContextStitchingStatus.PASSED.value
    assert score["score"] == score["max_score"]


def test_phase278_rejects_wrong_launch_date() -> None:
    answer = expected_answer().replace("Correct production launch date: December 3, 2026.", "Correct production launch date: November 15, 2026.")

    score = score_answer(answer)

    assert score["status"] == AdversarialContextStitchingStatus.FAILED.value
    assert any(item["outcome"] == "launch_date" and item["hard_failure"] for item in score["checks"])


def test_phase278_rejects_allowed_eu_rollout() -> None:
    answer = expected_answer().replace("The EU may not proceed.", "The EU may proceed.")

    score = score_answer(answer)

    assert score["status"] == AdversarialContextStitchingStatus.FAILED.value
    assert any(item["outcome"] in {"regions", "eu_rollout"} and item["hard_failure"] for item in score["checks"])


def test_phase278_rejects_lost_boundary_value() -> None:
    answer = expected_answer().replace("ORCHID-17", "ORCHID")

    score = score_answer(answer)

    assert score["status"] == AdversarialContextStitchingStatus.FAILED.value
    assert any(item["outcome"] == "kill_switch" and item["hard_failure"] for item in score["checks"])


def test_phase278_rejects_wrong_sentinel_order() -> None:
    answer = expected_answer().replace("ALPHA-19, BRAVO-27, CHARLIE-08, DELTA-66.", "ALPHA-19, CHARLIE-08, BRAVO-27, DELTA-66.")

    score = score_answer(answer)

    assert score["status"] == AdversarialContextStitchingStatus.FAILED.value
    assert any(item["outcome"] == "sentinel_order" and item["hard_failure"] for item in score["checks"])


def test_phase278_rejects_answer_file_failure(tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)
    bad_answer = tmp_path / "bad-answer.txt"
    bad_answer.write_text(expected_answer().replace("$224,400", "$244,400"), encoding="utf-8")

    report = validate_adversarial_context_stitching(
        AdversarialContextStitchingConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase278/report.json",
            markdown_output_path="runtime-state/phase278/report.md",
            fixture_dir="runtime-state/phase278/fixture",
            answer_file=bad_answer,
        )
    )

    assert report["status"] == AdversarialContextStitchingStatus.FAILED.value
    assert any(item["source"] == "answer_file" for item in report["errors"])


def test_phase278_live_gateway_uses_standard_prompt(monkeypatch, tmp_path: Path) -> None:
    root, policy_path = temp_config(tmp_path)

    def fake_gateway_answer(config: phase278.AdversarialContextStitchingConfig, prompt: str) -> tuple[int, dict, str]:
        assert "SECTION 01 -- PROJECT BASELINE" in prompt
        assert "Based only on the supplied corpus" in prompt
        return 200, {"choices": [{"message": {"content": expected_answer()}}]}, expected_answer()

    monkeypatch.setattr(phase278, "gateway_answer", fake_gateway_answer)

    report = validate_adversarial_context_stitching(
        AdversarialContextStitchingConfig(
            config_root=root,
            policy_path=policy_path,
            output_path="runtime-state/phase278/report.json",
            markdown_output_path="runtime-state/phase278/report.md",
            fixture_dir="runtime-state/phase278/fixture",
            live_gateway=True,
        )
    )

    assert report["status"] == AdversarialContextStitchingStatus.PASSED.value
    assert report["summary"]["live_gateway_hard_failure_count"] == 0


def test_phase279_router_detects_supplied_corpus_qa() -> None:
    prompt = prompt_for_corpus(build_corpus(policy(), FixtureMode.STANDARD)["corpus"])

    workflow_id, status_reason, evidence = workflow_kind_for_request(prompt)

    assert workflow_id is None
    assert status_reason == "supplied_corpus_qa"
    assert is_supplied_corpus_qa_request(prompt) is True
    assert any(item.get("rule") == "supplied_corpus_qa_terms" for item in evidence)


def test_phase279_supplied_corpus_qa_preserves_full_natural_message() -> None:
    prompt = prompt_for_corpus(build_corpus(policy(), FixtureMode.STANDARD)["corpus"])
    payload = {"messages": [{"role": "user", "content": prompt}]}

    message = latest_user_message_text(payload)

    assert "SECTION 10 -- DPA STATUS" in message
    assert "Based only on the supplied corpus" in message
    assert len(message) == len(prompt.strip())


def test_phase279_workflow_router_chat_answers_supplied_corpus_without_target(tmp_path: Path) -> None:
    target_root = tmp_path / "allowed-placeholder"
    target_root.mkdir()
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target_root,),
        port=0,
    )
    prompt = prompt_for_corpus(build_corpus(policy(), FixtureMode.STANDARD)["corpus"])

    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt}],
            "budgets": {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        config,
    )

    content = body["choices"][0]["message"]["content"]
    summary = body["agentic_controller_response"]["summary"]
    assert summary["route_status"] == SUPPLIED_CORPUS_QA_STATUS
    assert summary["selected_workflow"] is None
    assert "missing_target_root_for_coding_request" not in content
    assert score_answer(summary["answer"])["status"] == AdversarialContextStitchingStatus.PASSED.value
    assert score_answer(content)["status"] == AdversarialContextStitchingStatus.PASSED.value
    artifacts = body["agentic_controller_response"]["artifacts"]
    assert Path(artifacts["supplied_corpus_qa_answer"]).is_file()
    assert Path(artifacts["supplied_corpus_qa_extraction"]).is_file()


def test_phase278_policy_rejects_missing_randomized_mode() -> None:
    mutated = copy.deepcopy(policy())
    mutated["fixture_modes"] = ["standard", "zero_overlap"]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.fixture_modes" for item in errors)
