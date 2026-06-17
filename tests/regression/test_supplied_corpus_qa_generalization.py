from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.acceptance.supplied_corpus_qa_generalization import (
    PHASE280_CASES,
    SuppliedCorpusQaGeneralizationConfig,
    prompt_for_case,
    score_case_answer,
    validate_supplied_corpus_qa_generalization,
)
from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, handle_workflow_router_chat_completion
from vllm_agent_gateway.controllers.supplied_corpus_qa import answer_supplied_corpus_qa
from vllm_agent_gateway.controllers.workflow_router.plan import SUPPLIED_CORPUS_QA_STATUS


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_PATHS = (
    REPO_ROOT / "vllm_agent_gateway" / "controllers" / "supplied_corpus_qa.py",
    REPO_ROOT / "vllm_agent_gateway" / "controllers" / "workflow_router" / "plan.py",
)


def assert_case_answer(case: dict[str, object], answer: str) -> None:
    score = score_case_answer(case, answer)
    assert score["status"] == "passed", score


def test_phase280_supplied_corpus_qa_generic_engine_passes_unseen_fixtures() -> None:
    for case in PHASE280_CASES:
        answer, details = answer_supplied_corpus_qa(prompt_for_case(case))

        assert details["extraction_status"] == "complete", case["id"]
        assert details["question_count"] == len(case["questions"])  # type: ignore[arg-type]
        assert_case_answer(case, answer)


def test_phase280_workflow_router_chat_uses_same_route_for_unseen_fixtures(tmp_path: Path) -> None:
    target_root = tmp_path / "allowed-placeholder"
    target_root.mkdir()
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target_root,),
        port=0,
    )

    for case in PHASE280_CASES:
        body = handle_workflow_router_chat_completion(
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": prompt_for_case(case)}],
                "budgets": {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            },
            config,
        )

        content = body["choices"][0]["message"]["content"]
        summary = body["agentic_controller_response"]["summary"]
        assert summary["route_status"] == SUPPLIED_CORPUS_QA_STATUS
        assert summary["selected_workflow"] is None
        assert "supplied_corpus_qa_answer" in body["agentic_controller_response"]["artifacts"]
        assert_case_answer(case, content)


def test_phase280_generic_answer_path_has_no_phase278_fixture_literals() -> None:
    implementation_text = "\n".join(path.read_text(encoding="utf-8") for path in IMPLEMENTATION_PATHS)

    for forbidden in ("Meridian Gate", "ORCHID", "Payments API", "DPA"):
        assert forbidden not in implementation_text


def test_phase280_acceptance_report_passes_static_and_direct_router(tmp_path: Path) -> None:
    report = validate_supplied_corpus_qa_generalization(
        SuppliedCorpusQaGeneralizationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            artifact_dir=tmp_path / "artifacts",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 5
    assert report["summary"]["direct_engine_status"] == "passed"
    assert report["summary"]["direct_router_status"] == "passed"
    assert report["summary"]["no_target_coding_guard_status"] == "passed"
