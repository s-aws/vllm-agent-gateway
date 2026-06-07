from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.capability_gap_backlog import validate_backlog


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKLOG_PATH = REPO_ROOT / "runtime" / "natural_language_capability_gap_backlog.json"


def load_backlog() -> dict:
    return json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))


def failed_errors(backlog: dict) -> list[str]:
    check = validate_backlog(backlog, backlog_path=BACKLOG_PATH)[0]
    return check["details"]["errors"]


def test_project_capability_gap_backlog_passes_contract() -> None:
    check = validate_backlog(load_backlog(), backlog_path=BACKLOG_PATH)[0]

    assert check["status"] == "passed"
    assert check["details"]["entry_count"] == 30
    assert check["details"]["classification_counts"]["defer"] >= 1


def test_capability_gap_backlog_rejects_accepted_broad_refactor() -> None:
    backlog = load_backlog()
    mutated = copy.deepcopy(backlog)
    entry = next(item for item in mutated["entries"] if item["id"] == "P93-027")
    entry["classification"] = "new_workflow"
    entry["expected_workflow"] = "refactor_everything.plan"
    entry["expected_skills"] = ["implementation-packet-designer"]
    entry["expected_tools"] = ["git_grep", "read_file"]
    entry["expected_artifacts"] = ["implementation_workflow_report"]
    entry["eval_gate"] = "unsafe_refactor_eval"
    entry["validation_tier"] = "gateway_anythingllm"
    entry["acceptance_markers"] = ["Refactor:"]
    entry["mutation_policy"] = "approval_gated_draft_only"

    errors = failed_errors(mutated)

    assert any("broad refactor wording must be classified as defer" in error for error in errors)


def test_capability_gap_backlog_rejects_manual_skill_injection_language() -> None:
    backlog = load_backlog()
    mutated = copy.deepcopy(backlog)
    mutated["entries"][0]["prompt"] = "Paste this SKILL.md and then review this patch."

    errors = failed_errors(mutated)

    assert any("must not rely on manual skill injection" in error for error in errors)


def test_capability_gap_backlog_rejects_missing_eval_gate_for_accepted_entry() -> None:
    backlog = load_backlog()
    mutated = copy.deepcopy(backlog)
    del mutated["entries"][0]["eval_gate"]

    errors = failed_errors(mutated)

    assert any("eval_gate must be a non-empty string" in error for error in errors)


def test_capability_gap_backlog_rejects_unbounded_prompt_count() -> None:
    backlog = load_backlog()
    mutated = copy.deepcopy(backlog)
    mutated["entries"] = mutated["entries"][:24]

    errors = failed_errors(mutated)

    assert any("entries must contain 25 through 50 prompt families" in error for error in errors)
