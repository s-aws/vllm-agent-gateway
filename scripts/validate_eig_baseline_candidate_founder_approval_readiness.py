#!/usr/bin/env python3
"""Validate Phase 317 EIG founder-approval readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_baseline_candidate_founder_approval_readiness import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGBaselineCandidateFounderApprovalReadinessConfig,
    run_eig_baseline_candidate_founder_approval_readiness,
)


def optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/eig-baseline-candidate-founder-approval-readiness/phase317-validation.json",
    )
    parser.add_argument("--blind-baseline-report-path", default=None)
    parser.add_argument("--local-comparison-report-path", default=None)
    parser.add_argument("--route-mutation-report-path", default=None)
    parser.add_argument("--holdout-report-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_baseline_candidate_founder_approval_readiness(
        EIGBaselineCandidateFounderApprovalReadinessConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            blind_baseline_report_path=optional_path(args.blind_baseline_report_path),
            local_comparison_report_path=optional_path(args.local_comparison_report_path),
            route_mutation_report_path=optional_path(args.route_mutation_report_path),
            holdout_report_path=optional_path(args.holdout_report_path),
        )
    )
    print("EIG BASELINE CANDIDATE FOUNDER APPROVAL READINESS REPORT " + str(args.output_path))
    print("EIG BASELINE CANDIDATE FOUNDER APPROVAL READINESS SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("EIG BASELINE CANDIDATE FOUNDER APPROVAL READINESS ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("EIG BASELINE CANDIDATE FOUNDER APPROVAL READINESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
