#!/usr/bin/env python3
"""Validate Phase 216 corpus and index safety governance."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.corpus_index_safety_governance import (  # noqa: E402
    CorpusIndexSafetyGovernanceConfig,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    run_corpus_index_safety_governance,
)


def main() -> int:
    report = run_corpus_index_safety_governance(
        CorpusIndexSafetyGovernanceConfig(
            config_root=REPO_ROOT,
            policy_path=DEFAULT_POLICY_PATH,
            output_path=DEFAULT_OUTPUT_PATH,
        )
    )
    print("PHASE216 CORPUS INDEX SAFETY GOVERNANCE SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") != "passed":
        print(
            "PHASE216 CORPUS INDEX SAFETY GOVERNANCE FAILURES "
            + json.dumps(report.get("validation_errors", []), sort_keys=True)
        )
        return 1
    print("PHASE216 CORPUS INDEX SAFETY GOVERNANCE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
