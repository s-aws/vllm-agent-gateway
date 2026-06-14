#!/usr/bin/env python3
"""Validate Phase 233 contextless handoff dry run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.contextless_handoff_dry_run import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    ContextlessHandoffDryRunConfig,
    run_contextless_handoff_dry_run,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_contextless_handoff_dry_run(
        ContextlessHandoffDryRunConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
        )
    )
    print("PHASE233 CONTEXTLESS HANDOFF DRY RUN SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("PHASE233 CONTEXTLESS HANDOFF DRY RUN ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("PHASE233 CONTEXTLESS HANDOFF DRY RUN PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
