#!/usr/bin/env python3
"""Validate the Phase 310 EIG PR merge-readiness packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_pr_merge_readiness import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGPrMergeReadinessConfig,
    run_eig_pr_merge_readiness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default="runtime-state/eig-pr-merge-readiness/phase310-validation.json")
    parser.add_argument("--skip-github", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_pr_merge_readiness(
        EIGPrMergeReadinessConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            skip_github=args.skip_github,
        )
    )
    print("EIG PR MERGE READINESS REPORT " + str(args.output_path))
    print("EIG PR MERGE READINESS SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("EIG PR MERGE READINESS ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("EIG PR MERGE READINESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
