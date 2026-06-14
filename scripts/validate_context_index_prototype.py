#!/usr/bin/env python3
"""Validate Phase 217 metadata-first context index prototype."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.context_index_prototype import (  # noqa: E402
    ContextIndexPrototypeConfig,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    run_context_index_prototype,
)


def main() -> int:
    report = run_context_index_prototype(
        ContextIndexPrototypeConfig(
            config_root=REPO_ROOT,
            policy_path=DEFAULT_POLICY_PATH,
            output_path=DEFAULT_OUTPUT_PATH,
        )
    )
    print("PHASE217 CONTEXT INDEX PROTOTYPE SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") != "passed":
        print("PHASE217 CONTEXT INDEX PROTOTYPE FAILURES " + json.dumps(report.get("validation_errors", []), sort_keys=True))
        return 1
    print("PHASE217 CONTEXT INDEX PROTOTYPE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
