#!/usr/bin/env python3
"""Validate Phase 214 large-corpus fixture and context-budget inventory."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.large_corpus_context_budget_inventory import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    LargeCorpusContextBudgetInventoryConfig,
    run_large_corpus_context_budget_inventory,
)


def main() -> int:
    report = run_large_corpus_context_budget_inventory(
        LargeCorpusContextBudgetInventoryConfig(
            config_root=REPO_ROOT,
            policy_path=DEFAULT_POLICY_PATH,
            output_path=DEFAULT_OUTPUT_PATH,
        )
    )
    print("PHASE214 LARGE CORPUS CONTEXT BUDGET INVENTORY SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") != "passed":
        print(
            "PHASE214 LARGE CORPUS CONTEXT BUDGET INVENTORY FAILURES "
            + json.dumps(report.get("validation_errors", []), sort_keys=True)
        )
        return 1
    print("PHASE214 LARGE CORPUS CONTEXT BUDGET INVENTORY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
