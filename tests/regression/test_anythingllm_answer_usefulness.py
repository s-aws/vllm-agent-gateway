from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.anythingllm_answer_usefulness import (
    AnythingLLMAnswerUsefulnessConfig,
    run_anythingllm_answer_usefulness,
    validate_anythingllm_answer_usefulness,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "runtime" / "baseline_corpus.json"
CONTRACT_PATH = REPO_ROOT / "runtime" / "anythingllm_answer_usefulness_contract.json"


def load_project_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def load_project_contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_entry(corpus: dict[str, object]) -> dict[str, object]:
    return corpus["entries"][0]  # type: ignore[index]


def first_contract_entry(contract: dict[str, object]) -> dict[str, object]:
    return contract["entries"][0]  # type: ignore[index]


def useful_response_text(*, artifact_first: bool = False) -> str:
    answer = """I completed workflow_router.plan.
workflow_router.plan completed
run_id: workflow-router-test
warnings: 0
failures: 0

Result:
- Workflow: workflow_router.plan
- Status: completed
- Selected workflow: code_investigation.plan

Skill Selection:
- Why: Selected code_investigation.plan from router evidence.
- Route rules: l2_code_quality_review_terms

Summary:
- route_status: ready
- selected_workflow: code_investigation.plan
- source_changed: False
- confidence: medium

Code Quality Review:
- Target: core/example.py
- Status: ready
- Findings:
  - CQ-1 [medium/testability]: Example duplicated logic is supported by bounded evidence.
    Evidence: core/example.py:10; core/example.py:22
    Impact: The duplicate path can drift.
    Bounded remediation: Extract one helper after a focused regression exists.
- Rejected false positives: broad refactor is not supported by the bounded prompt.
- Source refs: core/example.py:10; core/example.py:22
- Source mutation: false
"""
    artifacts = """
Artifacts:
- route_decision: /tmp/route-decision.json
- downstream_code_quality_review: /tmp/code-quality-review.json

Run record: /v1/controller/runs/workflow-router-test
"""
    body = artifacts + "\n" + answer if artifact_first else answer + "\n" + artifacts
    return body + "\n".join(f"detail line {index}" for index in range(80))


def eval_artifact_with_text(text: str) -> dict[str, object]:
    return {
        "case_count": 1,
        "checks": {
            "cases": [
                {
                    "case_id": "CASE-001",
                    "responses": {
                        "anythingllm": {
                            "status": "captured",
                            "http_status": 200,
                            "route_summary": {
                                "run_id": "workflow-router-test",
                                "selected_workflow": "code_investigation.plan",
                            },
                            "text": text,
                        }
                    },
                }
            ]
        },
    }


def single_entry_corpus_and_contract(tmp_path: Path, text: str) -> tuple[dict[str, object], dict[str, object]]:
    corpus = load_project_corpus()
    contract = load_project_contract()
    eval_path = write_json(tmp_path / "local-eval.json", eval_artifact_with_text(text))
    entry = first_entry(corpus)
    entry["expected_case_count"] = 1
    entry["local_eval"] = {
        "path": str(eval_path),
        "sha256": sha256_file(eval_path),
        "status": "captured",
        "case_count": 1,
        "routes": ["anythingllm", "gateway"],
    }
    return corpus, contract


def test_project_anythingllm_answer_usefulness_passes_with_current_artifacts() -> None:
    report = run_anythingllm_answer_usefulness(
        AnythingLLMAnswerUsefulnessConfig(
            config_root=REPO_ROOT,
            output_path=REPO_ROOT
            / "runtime-state"
            / "anythingllm-answer-usefulness"
            / "unit-project.json",
            require_artifacts=True,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["entry_count"] == 4  # type: ignore[index]
    assert report["summary"]["checked_case_count"] == 40  # type: ignore[index]
    assert report["summary"]["error_count"] == 0  # type: ignore[index]


def test_answer_usefulness_rejects_contract_missing_stable_entry() -> None:
    corpus = load_project_corpus()
    contract = load_project_contract()
    contract["entries"] = contract["entries"][:-1]  # type: ignore[index]

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=False,
    )

    assert any("exactly match stable baseline corpus entry IDs" in error for error in errors)


def test_answer_usefulness_rejects_artifact_only_answer(tmp_path: Path) -> None:
    corpus, contract = single_entry_corpus_and_contract(
        tmp_path,
        "I completed workflow_router.plan.\nworkflow_router.plan completed\nrun_id: workflow-router-test\n"
        "Result:\nSkill Selection:\nSummary:\nArtifacts:\n- report: /tmp/report.json\nRun record: /v1/controller/runs/workflow-router-test\n",
    )

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )

    assert any("missing accepted answer section marker" in error for error in errors)
    assert any("too little answer content before artifacts" in error for error in errors)


def test_answer_usefulness_rejects_answer_after_artifacts(tmp_path: Path) -> None:
    corpus, contract = single_entry_corpus_and_contract(tmp_path, useful_response_text(artifact_first=True))

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )

    assert any("answer section appears after artifacts" in error for error in errors)


def test_answer_usefulness_rejects_missing_source_mutation_boundary(tmp_path: Path) -> None:
    text = useful_response_text().replace("- Source mutation: false\n", "")
    corpus, contract = single_entry_corpus_and_contract(tmp_path, text)

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )

    assert any("Source mutation:" in error for error in errors)


def test_answer_usefulness_rejects_truncated_response(tmp_path: Path) -> None:
    corpus, contract = single_entry_corpus_and_contract(
        tmp_path,
        "I completed workflow_router.plan.\nworkflow_router.plan completed\nrun_id: workflow-router-test\n",
    )

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )

    assert any("shorter than minimum_text_chars" in error for error in errors)
    assert any("fewer non-empty lines" in error for error in errors)


def test_answer_usefulness_rejects_missing_useful_detail_markers(tmp_path: Path) -> None:
    text = useful_response_text()
    text = text.replace("- Findings:", "- Notes:")
    text = text.replace("    Evidence:", "    Source:")
    text = text.replace("    Impact:", "    Result:")
    text = text.replace("    Bounded remediation:", "    Option:")
    text = text.replace("- Rejected false positives:", "- Rejected:")
    corpus, contract = single_entry_corpus_and_contract(tmp_path, text)

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )

    assert any("useful detail marker" in error for error in errors)


def test_answer_usefulness_rejects_stale_local_eval_hash(tmp_path: Path) -> None:
    corpus, contract = single_entry_corpus_and_contract(tmp_path, useful_response_text())
    local_eval = first_entry(corpus)["local_eval"]  # type: ignore[index]
    local_eval["sha256"] = "0" * 64  # type: ignore[index]

    errors, _checked = validate_anythingllm_answer_usefulness(
        corpus,
        contract,
        config_root=REPO_ROOT,
        require_artifacts=True,
    )

    assert any("local_eval.sha256 is stale" in error for error in errors)
