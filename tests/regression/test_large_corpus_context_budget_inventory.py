from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.large_corpus_context_budget_inventory import (
    DEFAULT_POLICY_PATH,
    LargeCorpusContextBudgetInventoryConfig,
    inventory_corpus,
    read_json_object,
    run_large_corpus_context_budget_inventory,
    validate_policy,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def small_policy(tmp_path: Path) -> dict:
    mutated = copy.deepcopy(policy())
    start_script = tmp_path / "start-agent-prompt-proxies.sh"
    host_notes = tmp_path / "VLLM_AGENT_HOST.md"
    start_script.write_text(
        "\n".join(
            [
                'MODEL_LIMIT="${MODEL_LIMIT:-1000}"',
                'TARGET_INPUT_LIMIT="${TARGET_INPUT_LIMIT:-500}"',
                'SAFETY_BUFFER="${SAFETY_BUFFER:-100}"',
                'DEFAULT_MAX_OUTPUT="${DEFAULT_MAX_OUTPUT:-200}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    host_notes.write_text(
        "\n".join(
            [
                "Qwen3-Coder-30B-A3B-Instruct",
                "--max-model-len 1000",
                "MODEL_LIMIT=1000",
                "TARGET_INPUT_LIMIT=500",
                "DEFAULT_MAX_OUTPUT=200",
                "",
            ]
        ),
        encoding="utf-8",
    )
    mutated["generated_fixture"]["root"] = str(tmp_path / "large-corpus")
    mutated["generated_fixture"]["module_count"] = 2
    mutated["generated_fixture"]["doc_count"] = 2
    mutated["generated_fixture"]["test_count"] = 2
    mutated["generated_fixture"]["config_count"] = 1
    mutated["generated_fixture"]["json_case_count"] = 1
    mutated["generated_fixture"]["filler_lines_per_file"] = 4
    mutated["generated_fixture"]["line_width"] = 96
    mutated["inventory_minimums"]["file_count"] = 10
    mutated["inventory_minimums"]["estimated_token_count"] = 500
    mutated["inventory_minimums"]["language_count"] = 5
    mutated["inventory_minimums"]["binary_path_count"] = 2
    mutated["inventory_minimums"]["ignored_path_count"] = 3
    mutated["context_budget_sources"]["vllm_host_notes"] = str(host_notes)
    mutated["context_budget_sources"]["gateway_start_script"] = str(start_script)
    mutated["context_budget_sources"]["expected_model_limit"] = 1000
    mutated["context_budget_sources"]["expected_target_input_limit"] = 500
    mutated["context_budget_sources"]["expected_default_max_output"] = 200
    mutated["context_budget_sources"]["runtime_probe_required"] = False
    return mutated


def test_phase214_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase214_inventory_report_passes_with_small_fixture(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, small_policy(tmp_path))

    report = run_large_corpus_context_budget_inventory(
        LargeCorpusContextBudgetInventoryConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["file_count"] >= 10
    assert report["summary"]["estimated_token_count"] >= 500
    assert report["summary"]["phase215_ready"] is True
    assert report["summary"]["raw_1m_prompt_support_proven"] is False
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# Large-Corpus Context Budget Inventory")


def test_phase214_policy_rejects_missing_raw_context_boundary() -> None:
    mutated = copy.deepcopy(policy())
    mutated["required_claim_boundaries"] = [
        item for item in mutated["required_claim_boundaries"] if item != "raw_1m_token_prompt_support_not_claimed"
    ]

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.required_claim_boundaries" for item in errors)


def test_phase214_inventory_counts_ignored_and_binary_paths(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    (root / "src").mkdir(parents=True)
    (root / "ignored").mkdir()
    (root / "assets").mkdir()
    (root / ".gitignore").write_text("ignored/\n*.bin\n", encoding="utf-8")
    (root / "src" / "service.py").write_text("def service():\n    return 'ok'\n", encoding="utf-8")
    (root / "ignored" / "note.txt").write_text("ignored\n", encoding="utf-8")
    (root / "assets" / "blob.bin").write_bytes(b"\x00\x01\x02\x03")

    inventory = inventory_corpus(root, chars_per_token=4.0)

    assert inventory["file_count"] == 4
    assert inventory["ignored_path_count"] == 2
    assert inventory["binary_path_count"] == 1
    assert inventory["role_counts"]["ignored"] == 2
    assert inventory["role_counts"]["source"] == 1


def test_phase214_report_rejects_corpus_below_token_budget(tmp_path: Path) -> None:
    mutated = small_policy(tmp_path)
    mutated["inventory_minimums"]["estimated_token_count"] = 10_000_000
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, mutated)

    report = run_large_corpus_context_budget_inventory(
        LargeCorpusContextBudgetInventoryConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "summary.estimated_token_count" for item in report["validation_errors"])
