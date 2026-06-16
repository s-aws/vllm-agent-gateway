from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import (
    build_chunks_for_file,
    read_json_object,
    write_json,
)
from vllm_agent_gateway.acceptance.retrieval_backed_chat_answer_gate import (
    DEFAULT_POLICY_PATH,
    validate_policy,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)
from vllm_agent_gateway.controllers.large_context.retrieval_answer import (
    RetrievalBackedChatAnswerRequest,
    invoke_retrieval_backed_chat_answer,
)
from vllm_agent_gateway.controllers.workflow_router.plan import WorkflowRouterPlanRequest, invoke_workflow_router_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def phase216_policy() -> dict:
    return read_json_object(REPO_ROOT / "runtime" / "corpus_index_safety_governance_policy.json")


def make_small_large_context_fixture(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("ignored/\nruntime-state/\n*.bin\n*.secret\n", encoding="utf-8")
    (root / ".cgcignore").write_text("private/\n*.secret\n", encoding="utf-8")
    files = [
        root / "src" / "order_replay" / "module_0000.py",
        root / "src" / "order_replay" / "module_0001.py",
        root / "tests" / "test_order_replay_0000.py",
        root / "docs" / "architecture.md",
        root / "cases" / "scenario_0000.json",
    ]
    body = "\n".join(
        [
            "order replay pipeline risk gate audit summary context retrieval source evidence chunk boundary token budget fixture navigation confidence limitation generated corpus deterministic proof"
            for _index in range(30)
        ]
    )
    files[0].parent.mkdir(parents=True, exist_ok=True)
    files[0].write_text("PIPELINE_STAGE = 'risk_gate_audit_summary'\n\ndef replay_stage(event):\n    return event\n" + body, encoding="utf-8")
    files[1].write_text("def replay_lookup(event):\n    return {'audit_summary': event}\n" + body, encoding="utf-8")
    files[2].parent.mkdir(parents=True, exist_ok=True)
    files[2].write_text("def test_order_replay_risk_gate_audit_summary():\n    assert True\n" + body, encoding="utf-8")
    files[3].parent.mkdir(parents=True, exist_ok=True)
    files[3].write_text("# Generated Service Architecture\n\n" + body, encoding="utf-8")
    files[4].parent.mkdir(parents=True, exist_ok=True)
    files[4].write_text('{"scenario": "order replay pipeline risk gate audit summary generated service architecture"}\n' + body, encoding="utf-8")
    (root / "private").mkdir()
    (root / "private" / "operator.secret").write_text("PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE\n", encoding="utf-8")
    return files


def make_context_index_policy(tmp_path: Path) -> tuple[Path, Path]:
    corpus_root = tmp_path / "small-large-corpus"
    files = make_small_large_context_fixture(corpus_root)
    safety_policy = phase216_policy()
    phase216_policy_path = tmp_path / "phase216-policy.json"
    write_json(phase216_policy_path, safety_policy)
    chunks = []
    for path in files:
        chunks.extend(
            build_chunks_for_file(
                root=corpus_root,
                path=path,
                phase216_policy=safety_policy,
                chunk_line_count=80,
                chars_per_token=4.0,
                term_limit=24,
                max_search_term_length=32,
            )
        )
    index_path = tmp_path / "context-index.json"
    write_json(
        index_path,
        {
            "schema_version": 1,
            "kind": "metadata_first_context_index",
            "phase": 217,
            "target_root": str(corpus_root),
            "source_text_retention": "metadata_only",
            "store_source_text": False,
            "store_rejected_content": False,
            "indexed_file_count": len(files),
            "chunk_count": len(chunks),
            "estimated_indexed_token_count": sum(int(item["estimated_tokens"]) for item in chunks),
            "chunks": chunks,
        },
    )
    context_policy_path = tmp_path / "context-index-policy.json"
    write_json(
        context_policy_path,
        {
            "schema_version": 1,
            "kind": "context_index_prototype_policy",
            "phase": 217,
            "phase216_policy_path": str(phase216_policy_path),
            "source_corpus": {"root": str(corpus_root)},
            "index_artifact": {"path": str(index_path)},
        },
    )
    return corpus_root, context_policy_path


def test_phase218_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase218_policy_rejects_new_chat_endpoint() -> None:
    mutated = copy.deepcopy(policy())
    mutated["answer_contract"]["new_chat_endpoint_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.answer_contract.new_chat_endpoint_allowed" for item in errors)


def test_retrieval_answer_uses_metadata_index_without_source_text(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "out",
            user_request="In the large corpus fixture, identify the most relevant modules for the order replay pipeline.",
            context_index_policy_path=context_policy_path,
        )
    )

    report = result.report
    assert isinstance(report, dict)
    assert report["status"] == "answered"
    assert report["summary"]["retrieval_evidence_count"] >= 3
    serialized = json.dumps(report, sort_keys=True)
    assert '"source_text"' not in serialized
    assert '"snippet"' not in serialized
    assert "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE" not in serialized


def test_workflow_router_surfaces_retrieval_answer_with_context_override(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "router",
            user_request="In the large corpus fixture, find evidence for how risk gate decisions flow into audit summaries.",
            mode="execute_read_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            context={"context_index_policy_path": str(context_policy_path)},
        )
    )

    summary = result.report["summary"]
    decision = result.report["decision"]
    assert summary["retrieval_status"] == "answered"
    assert summary["answer"].startswith("Risk-gate-to-audit-summary evidence")
    assert decision["large_context_retrieval"]["workflow"] == "large_context.retrieval_answer"


def test_chat_adapter_returns_answer_first_for_retrieval(tmp_path: Path) -> None:
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
                    "content": f"In {target_root}, summarize the generated service architecture without reading every file.",
                }
            ],
            "context": {"context_index_policy_path": str(context_policy_path)},
        },
        config,
    )

    content = body["choices"][0]["message"]["content"]
    assert content.startswith("Answer:\n")
    assert "source" in content.lower()
    assert body["agentic_controller_response"]["summary"]["retrieval_status"] == "answered"


def test_unsafe_evidence_request_blocks_without_refs(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)

    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "unsafe",
            user_request="Find private operator secret evidence in the ignored large corpus directory.",
            context_index_policy_path=context_policy_path,
        )
    )

    report = result.report
    assert isinstance(report, dict)
    assert report["status"] == "blocked"
    assert report["evidence_refs"] == []
    assert "cannot retrieve private" in report["answer"].lower()


def test_retrieval_answer_blocks_when_policy_fingerprint_changes(tmp_path: Path) -> None:
    target_root, context_policy_path = make_context_index_policy(tmp_path)
    context_policy = read_json_object(context_policy_path)
    safety_policy_path = Path(context_policy["phase216_policy_path"])
    safety_policy = read_json_object(safety_policy_path)
    safety_policy["secret_like_patterns"].append({"contains": "NEW_SENTINEL"})
    write_json(safety_policy_path, safety_policy)

    result = invoke_retrieval_backed_chat_answer(
        RetrievalBackedChatAnswerRequest(
            config_root=REPO_ROOT,
            target_root=target_root,
            output_root=tmp_path / "changed-policy",
            user_request="In the large corpus fixture, find evidence for how risk gate decisions flow into audit summaries.",
            context_index_policy_path=context_policy_path,
        )
    )

    report = result.report
    assert isinstance(report, dict)
    assert report["status"] == "blocked"
    assert report["summary"]["route_status"] == "blocked"
    assert report["evidence_refs"] == []
    assert any(item["id"] == "index.no_fresh_evidence" for item in report["validation_errors"])
    assert any(
        "changed_safety_policy_hash" in decision.get("reasons", [])
        for decision in report["safety_decisions"]
    )
