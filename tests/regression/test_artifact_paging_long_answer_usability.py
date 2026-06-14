from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.artifact_paging_long_answer_usability import (
    DEFAULT_POLICY_PATH,
    ArtifactPagingLongAnswerUsabilityConfig,
    read_json_object,
    run_artifact_paging_long_answer_usability,
    validate_policy,
    write_json,
)
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    RetrievalBackedChatAnswerRequest,
    invoke_retrieval_backed_chat_answer,
)
from tests.regression.test_retrieval_backed_chat_answer_gate import make_context_index_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def test_phase219_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase219_policy_rejects_artifact_only_output() -> None:
    mutated = copy.deepcopy(policy())
    mutated["answer_contract"]["artifact_only_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.answer_contract.artifact_only_allowed" for item in errors)


def test_retrieval_answer_creates_metadata_only_pages(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "out",
            user_request="In the large corpus fixture, identify the most relevant modules for the order replay pipeline.",
            context_index_policy_path=context_policy_path,
            max_evidence_refs=2,
            max_artifact_evidence_refs=5,
            artifact_page_size=2,
        )
    )

    report = result.report
    assert isinstance(report, dict)
    pages = report["artifact_pages"]
    assert report["summary"]["retrieval_evidence_count"] == 2
    assert pages["page_count"] >= 3
    assert pages["artifact_source_ref_count"] == 5
    assert pages["chat_refs_trace_to_pages"] is True
    assert pages["store_source_text"] is False
    assert "Paged evidence:" in report["answer"]
    for page in pages["pages"]:
        assert page["page_id"].startswith("retrieval-evidence-page-")
        assert page["continuation_hint"]
        for ref in page["source_refs"]:
            assert "source_text" not in ref
            assert "snippet" not in ref
            assert ref["source_sha256"]
            assert ref["chunk_sha256"]


def test_phase219_report_passes_with_project_artifacts(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["phase218_precondition"]["report_path"] = "runtime-state/phase218/phase218-retrieval-backed-chat-answer-gate-report.json"
    policy_path = tmp_path / "phase219-policy.json"
    write_json(policy_path, mutated)

    report = run_artifact_paging_long_answer_usability(
        ArtifactPagingLongAnswerUsabilityConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["direct_passed_count"] == 2
    assert report["summary"]["format_a_passed_count"] == 2
    assert report["summary"]["json_passed_count"] == 2
    assert report["summary"]["phase220_ready"] is True
