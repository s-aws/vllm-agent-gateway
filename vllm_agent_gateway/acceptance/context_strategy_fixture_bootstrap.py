"""Disposable large-context fixture bootstrap for strategy router validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    build_chunks_for_file,
    read_json_object,
    write_json,
)


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
            (
                "order replay pipeline risk gate audit summary context retrieval source evidence "
                "chunk boundary token budget fixture navigation confidence limitation generated "
                "corpus deterministic proof"
            )
            for _index in range(30)
        ]
    )
    files[0].parent.mkdir(parents=True, exist_ok=True)
    files[0].write_text(
        "PIPELINE_STAGE = 'risk_gate_audit_summary'\n\ndef replay_stage(event):\n    return event\n" + body,
        encoding="utf-8",
    )
    files[1].write_text("def replay_lookup(event):\n    return {'audit_summary': event}\n" + body, encoding="utf-8")
    files[2].parent.mkdir(parents=True, exist_ok=True)
    files[2].write_text("def test_order_replay_risk_gate_audit_summary():\n    assert True\n" + body, encoding="utf-8")
    files[3].parent.mkdir(parents=True, exist_ok=True)
    files[3].write_text("# Generated Service Architecture\n\n" + body, encoding="utf-8")
    files[4].parent.mkdir(parents=True, exist_ok=True)
    files[4].write_text(
        '{"scenario": "order replay pipeline risk gate audit summary generated service architecture"}\n' + body,
        encoding="utf-8",
    )
    (root / "private").mkdir()
    (root / "private" / "operator.secret").write_text("PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE\n", encoding="utf-8")
    return files


def make_context_strategy_fixture_policy(config_root: Path, output_root: Path) -> dict[str, Any]:
    corpus_root = output_root / "small-large-corpus"
    files = make_small_large_context_fixture(corpus_root)
    safety_policy = read_json_object(config_root / "runtime" / "corpus_index_safety_governance_policy.json")
    phase216_policy_path = output_root / "phase216-policy.json"
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
    index_path = output_root / "context-index.json"
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
    context_policy_path = output_root / "context-index-policy.json"
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
    return {
        "target_root": corpus_root,
        "context_index_policy_path": context_policy_path,
        "index_path": index_path,
        "phase216_policy_path": phase216_policy_path,
        "indexed_file_count": len(files),
        "chunk_count": len(chunks),
        "estimated_indexed_token_count": sum(int(item["estimated_tokens"]) for item in chunks),
    }
