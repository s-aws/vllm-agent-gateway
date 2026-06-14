from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)
from vllm_agent_gateway.controllers.large_context.chunked_investigation import (
    ChunkedInvestigationRequest,
    invoke_chunked_investigation,
)
from vllm_agent_gateway.controllers.workflow_router.plan import WorkflowRouterPlanRequest, invoke_workflow_router_plan
from tests.regression.test_retrieval_backed_chat_answer_gate import make_context_index_policy


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_chunked_executor_produces_phase222_artifacts_without_source_text(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    result = invoke_chunked_investigation(
        ChunkedInvestigationRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "out",
            user_request=(
                "In the large corpus fixture, trace the end-to-end cross-file flow across the whole corpus "
                "from risk gate to audit summary."
            ),
            context_index_policy_path=context_policy_path,
        )
    )

    report = result.report
    assert isinstance(report, dict)
    assert report["kind"] == "chunked_investigation_report"
    assert report["strategy"] == "chunked_investigation"
    assert report["status"] == "answered"
    assert report["summary"]["phase222_contract_satisfied"] is True
    assert report["summary"]["chunked_completed_stage_count"] >= 2
    assert report["summary"]["chunked_evidence_count"] >= 3
    assert report["plan"]["kind"] == "chunked_investigation_plan"
    assert report["final_answer"]["answer_first"] is True
    assert report["final_answer"]["flow_narrative"]
    assert len(report["final_answer"]["flow_narrative"]) >= 4
    assert len(report["final_answer"]["evidence_table"]) >= 3
    assert len(report["final_answer"]["not_proven_by_selected_evidence"]) >= 3
    answer = report["final_answer"]["answer"]
    for marker in (
        "Scope and limits:",
        "Evidence table:",
        "Flow narrative:",
        "Not proven by selected evidence:",
        "source_hash:",
        "chunk_hash:",
        "freshness:",
        "Entry point:",
        "Decision/output path:",
        "Verification surface:",
        "bounded cross-file trace",
    ):
        assert marker in answer
    assert report["final_answer"]["claim_map"]
    assert report["final_answer"]["raw_prompt_stuffing"] is False
    assert all(ref.get("source_sha256") and ref.get("chunk_sha256") for ref in report["evidence"])
    source_paths = [ref["source_path"] for ref in report["evidence"]]
    assert len(set(source_paths)) == len(source_paths)
    verification_refs = [ref for ref in report["evidence"] if ref["retrieval_stage_id"] == "verification_surfaces"]
    assert verification_refs
    assert verification_refs[0]["source_type"] in {"test", "doc", "case", "config"}
    assert result.artifact_paths["chunked_investigation_report"].endswith("chunked-investigation-report.json")
    assert result.artifact_paths["chunk_final_answer"].endswith("chunk-final-answer.json")

    serialized = json.dumps(report, sort_keys=True)
    assert '"source_text"' not in serialized
    assert '"snippet"' not in serialized
    assert "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE" not in serialized


def test_workflow_router_invokes_chunked_executor_when_strategy_selected(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "router",
            user_request=(
                "In the large corpus fixture, trace the end-to-end cross-file flow across the whole corpus "
                "from risk gate to audit summary."
            ),
            mode="execute_read_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            context={"context_index_policy_path": str(context_policy_path)},
        )
    )

    summary = result.report["summary"]
    decision = result.report["decision"]
    assert summary["selected_context_strategy"] == "chunked_investigation"
    assert summary["context_strategy_execution_path"] == "large_context.chunked_investigation"
    assert summary["downstream_workflow"] == "large_context.chunked_investigation"
    assert summary["chunked_status"] == "answered"
    assert summary["chunked_stage_count"] == 3
    assert summary["chunked_evidence_count"] >= 3
    assert summary["phase222_contract_satisfied"] is True
    assert decision["large_context_chunked_investigation"]["workflow"] == "large_context.chunked_investigation"
    assert "downstream_chunked_investigation_report" in result.artifact_paths


def test_chat_adapter_returns_answer_first_for_chunked_investigation(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    config = ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "chat",
        allowed_target_roots=(REPO_ROOT, target_root),
    )

    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"In {target_root}, trace the end-to-end cross-file flow across the whole corpus "
                        "from risk gate to audit summary."
                    ),
                }
            ],
            "context": {"context_index_policy_path": str(context_policy_path)},
        },
        config,
    )

    content = body["choices"][0]["message"]["content"]
    summary = body["agentic_controller_response"]["summary"]
    assert content.startswith("Answer:\n")
    assert "Chunked investigation result" in content
    assert "Scope and limits:" in content
    assert "Evidence table:" in content
    assert "Flow narrative:" in content
    assert "Not proven by selected evidence:" in content
    assert "chunked_stage_count" in content
    assert summary["selected_context_strategy"] == "chunked_investigation"
    assert summary["chunked_status"] == "answered"
    assert summary["phase222_contract_satisfied"] is True


def test_small_repo_prompt_does_not_invoke_chunked_executor(tmp_path: Path) -> None:
    target_root = tmp_path / "small-repo"
    target_root.mkdir()
    (target_root / "README.md").write_text("# Small repo\n\nNo large corpus here.\n", encoding="utf-8")

    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "router",
            user_request=f"In {target_root}, explain what README.md is for. Read only.",
            mode="execute_read_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        )
    )

    summary = result.report["summary"]
    decision = result.report["decision"]
    assert summary["selected_context_strategy"] == "direct_context"
    assert summary["downstream_workflow"] != "large_context.chunked_investigation"
    assert "large_context_chunked_investigation" not in decision
