from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import (
    DEFAULT_POLICY_PATH,
    ContextIndexPrototypeConfig,
    read_json_object,
    run_context_index_prototype,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def phase216_report() -> dict:
    return {
        "schema_version": 1,
        "kind": "corpus_index_safety_governance_report",
        "phase": 216,
        "status": "passed",
        "summary": {
            "phase217_ready": True,
            "durable_index_implementation_in_scope": False,
            "retrieval_backed_chat_integration_in_scope": False,
        },
    }


def phase216_policy() -> dict:
    return read_json_object(REPO_ROOT / "runtime" / "corpus_index_safety_governance_policy.json")


def make_small_corpus(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("ignored/\nruntime-state/\n*.bin\n*.secret\n", encoding="utf-8")
    (root / ".cgcignore").write_text("private/\n*.secret\n", encoding="utf-8")
    for index in range(4):
        path = root / "src" / "order_replay" / f"module_{index:04d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "def replay():",
                    "    risk_gate = 'enabled'",
                    "    audit_summary = 'required'",
                    "    # risk gate audit summary",
                    "    return 'order replay pipeline generated design architecture'",
                    "",
                ]
                * 20
            ),
            encoding="utf-8",
        )
    (root / "ignored").mkdir()
    (root / "ignored" / "ignored_notes.txt").write_text("ignored generated note\n", encoding="utf-8")
    (root / "private").mkdir()
    (root / "private" / "operator.secret").write_text("DUMMY_SECRET_DO_NOT_USE\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "binary_blob.bin").write_bytes(b"\x00\x01\x02")
    (root / "runtime-state").mkdir()
    (root / "runtime-state" / "local_artifact.txt").write_text("local runtime artifact\n", encoding="utf-8")


def small_policy(tmp_path: Path) -> dict:
    mutated = copy.deepcopy(policy())
    corpus_root = tmp_path / "large-corpus"
    make_small_corpus(corpus_root)
    phase216_report_path = tmp_path / "phase216-report.json"
    phase216_policy_path = tmp_path / "phase216-policy.json"
    write_json(phase216_report_path, phase216_report())
    write_json(phase216_policy_path, phase216_policy())
    mutated["phase216_precondition"]["report_path"] = str(phase216_report_path)
    mutated["phase216_policy_path"] = str(phase216_policy_path)
    mutated["source_corpus"]["root"] = str(corpus_root)
    mutated["source_corpus"]["max_files"] = 4
    mutated["source_corpus"]["chunk_line_count"] = 20
    mutated["index_artifact"]["path"] = str(tmp_path / "index.json")
    mutated["index_artifact"]["markdown_summary_path"] = str(tmp_path / "index.md")
    mutated["minimums"]["indexed_file_count"] = 4
    mutated["minimums"]["chunk_count"] = 4
    mutated["minimums"]["estimated_indexed_token_count"] = 100
    for case in mutated["query_smoke_cases"]:
        case["minimum_matches"] = 1
    return mutated


def run_with_policy(tmp_path: Path, value: dict) -> dict:
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, value)
    return run_context_index_prototype(
        ContextIndexPrototypeConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )


def test_phase217_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase217_report_passes_with_small_corpus(tmp_path: Path) -> None:
    report = run_with_policy(tmp_path, small_policy(tmp_path))

    assert report["status"] == "passed"
    assert report["summary"]["indexed_file_count"] == 4
    assert report["summary"]["chunk_count"] >= 4
    assert report["summary"]["source_text_retention"] == "metadata_only"
    assert report["summary"]["store_source_text"] is False
    assert report["summary"]["phase218_ready"] is True
    index_text = (tmp_path / "index.json").read_text(encoding="utf-8")
    assert "DUMMY_SECRET_DO_NOT_USE" not in index_text
    assert "ignored generated note" not in index_text
    assert '"snippet"' not in index_text
    assert '"content"' not in index_text


def test_phase217_policy_rejects_source_text_storage() -> None:
    mutated = copy.deepcopy(policy())
    mutated["index_artifact"]["store_source_text"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.index_artifact.store_source_text" for item in errors)


def test_phase217_policy_rejects_missing_metadata() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_index_metadata"] = [
        item for item in mutated["required_index_metadata"] if item != "search_terms_hash"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_index_metadata" for item in errors)


def test_phase217_report_rejects_phase216_index_scope(tmp_path: Path) -> None:
    mutated = small_policy(tmp_path)
    report_path = Path(mutated["phase216_precondition"]["report_path"])
    scoped = phase216_report()
    scoped["summary"]["durable_index_implementation_in_scope"] = True
    write_json(report_path, scoped)

    report = run_with_policy(tmp_path, mutated)

    assert report["status"] == "failed"
    assert any(item["id"] == "phase216_report.durable_index_implementation_in_scope" for item in report["validation_errors"])


def test_phase217_policy_rejects_missing_negative_control() -> None:
    mutated = copy.deepcopy(policy())
    mutated["negative_controls"] = [
        item for item in mutated["negative_controls"] if item.get("case_id") != "P217-SAFE-007"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.negative_controls" for item in errors)
