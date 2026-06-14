from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object
from vllm_agent_gateway.acceptance.large_context_usability_live_closeout import (
    DEFAULT_POLICY_PATH,
    LargeContextUsabilityLiveCloseoutConfig,
    default_markdown_output_path,
    default_output_path,
    response_score,
    validate_large_context_usability_live_closeout,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_phase221_default_paths_keep_live_and_preflight_separate() -> None:
    assert default_output_path(live=True) != default_output_path(live=False)
    assert default_markdown_output_path(live=True) != default_markdown_output_path(live=False)
    assert "preflight" in str(default_output_path(live=False))


def test_phase221_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase221_policy_rejects_missing_blind_baseline() -> None:
    mutated = copy.deepcopy(policy())
    mutated["baseline_cases"][0]["blind_baseline"] = {}

    errors = validate_policy(mutated)

    assert any(item["id"].endswith(".blind_baseline") for item in errors)


def test_phase221_preflight_passes_without_required_artifacts(tmp_path: Path) -> None:
    report = validate_large_context_usability_live_closeout(
        LargeContextUsabilityLiveCloseoutConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase221-preflight.json",
            markdown_output_path=tmp_path / "phase221-preflight.md",
            live=False,
            require_artifacts=False,
        )
    )

    assert report["status"] == "preflight_passed"
    assert report["summary"]["case_count"] == 8
    assert report["summary"]["response_count"] == 0
    assert report["summary"]["raw_prompt_stuffing_allowed"] is False


def test_phase221_response_score_rejects_wrong_strategy(tmp_path: Path) -> None:
    target_root = tmp_path / "large"
    source = target_root / "src" / "order_replay" / "module_0000.py"
    source.parent.mkdir(parents=True)
    source.write_text("risk gate audit summary\n", encoding="utf-8")
    source_sha = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    artifact_path = tmp_path / "retrieval.json"
    artifact = {
        "status": "answered",
        "prompt_budget": {"raw_prompt_stuffing": False},
        "source_text_retention": "metadata_only",
        "store_source_text": False,
        "evidence_refs": [
            {
                "source_path": "src/order_replay/module_0000.py",
                "line_start": 1,
                "line_end": 1,
                "chunk_sha256": "abc",
                "source_sha256": source_sha,
                "freshness_status": "fresh",
            }
        ],
        "artifact_pages": {"page_count": 0, "artifact_source_ref_count": 1},
    }
    write_json(artifact_path, artifact)
    case = {
        "case_id": "P221-TEST",
        "expected_strategy": "retrieval",
        "expected_execution_path": "large_context.retrieval_answer",
        "minimum_score": 85,
        "minimum_evidence_refs": 1,
        "minimum_visible_refs": 1,
        "required_terms": ["risk", "audit", "raw_prompt_stuffing"],
    }
    record = {
        "status": "completed",
        "summary": {
            "selected_context_strategy": "refusal",
            "context_strategy_execution_path": "large_context.retrieval_answer",
            "downstream_workflow": "large_context.retrieval_answer",
            "downstream_status": "completed",
            "raw_prompt_stuffing": False,
            "source_changed": False,
        },
    }
    text = (
        "Answer:\n"
        "risk audit raw_prompt_stuffing src/order_replay/module_0000.py\n"
        "selected_context_strategy: refusal\n"
        "context_strategy_rationale: test\n"
        "run_id: test\n"
    )

    result = response_score(case, text, record, artifact, target_root)

    assert result["status"] == "failed"
    assert any("selected_context_strategy" in error for error in result["errors"])


def test_phase221_response_score_passes_with_hash_proof(tmp_path: Path) -> None:
    target_root = tmp_path / "large"
    source = target_root / "src" / "order_replay" / "module_0000.py"
    source.parent.mkdir(parents=True)
    source.write_text("risk gate audit summary\n", encoding="utf-8")
    source_sha = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    artifact = {
        "status": "answered",
        "prompt_budget": {"raw_prompt_stuffing": False},
        "source_text_retention": "metadata_only",
        "store_source_text": False,
        "evidence_refs": [
            {
                "source_path": "src/order_replay/module_0000.py",
                "line_start": 1,
                "line_end": 1,
                "chunk_sha256": "abc",
                "source_sha256": source_sha,
                "freshness_status": "fresh",
            }
        ],
        "artifact_pages": {"page_count": 0, "artifact_source_ref_count": 1},
    }
    case = {
        "case_id": "P221-TEST",
        "expected_strategy": "retrieval",
        "expected_execution_path": "large_context.retrieval_answer",
        "minimum_score": 85,
        "minimum_evidence_refs": 1,
        "minimum_visible_refs": 1,
        "required_terms": ["risk", "audit", "raw_prompt_stuffing"],
    }
    record = {
        "status": "completed",
        "summary": {
            "selected_context_strategy": "retrieval",
            "context_strategy_execution_path": "large_context.retrieval_answer",
            "downstream_workflow": "large_context.retrieval_answer",
            "downstream_status": "completed",
            "raw_prompt_stuffing": False,
            "source_changed": False,
        },
    }
    text = (
        "Answer:\n"
        "risk audit raw_prompt_stuffing src/order_replay/module_0000.py\n"
        "selected_context_strategy: retrieval\n"
        "context_strategy_rationale: test\n"
        "run_id: test\n"
    )

    result = response_score(case, text, record, artifact, target_root)

    assert result["status"] == "passed"
    assert result["visible_source_refs"] == ["src/order_replay/module_0000.py"]
