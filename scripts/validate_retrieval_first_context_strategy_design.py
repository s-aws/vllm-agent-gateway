#!/usr/bin/env python3
"""Validate Phase 215 retrieval-first context strategy design."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.retrieval_first_context_strategy_design import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    RetrievalFirstContextStrategyDesignConfig,
    run_retrieval_first_context_strategy_design,
)


def main() -> int:
    report = run_retrieval_first_context_strategy_design(
        RetrievalFirstContextStrategyDesignConfig(
            config_root=REPO_ROOT,
            policy_path=DEFAULT_POLICY_PATH,
            output_path=DEFAULT_OUTPUT_PATH,
        )
    )
    print("PHASE215 RETRIEVAL FIRST CONTEXT STRATEGY DESIGN SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") != "passed":
        print(
            "PHASE215 RETRIEVAL FIRST CONTEXT STRATEGY DESIGN FAILURES "
            + json.dumps(report.get("validation_errors", []), sort_keys=True)
        )
        return 1
    print("PHASE215 RETRIEVAL FIRST CONTEXT STRATEGY DESIGN PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
