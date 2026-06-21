#!/usr/bin/env python3
"""Validate the Phase 311 EIG baseline-candidate promotion-readiness packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_baseline_candidate_promotion_readiness import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGBaselineCandidatePromotionReadinessConfig,
    run_eig_baseline_candidate_promotion_readiness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/eig-baseline-candidate-promotion-readiness/phase311-validation.json",
    )
    parser.add_argument("--skip-github", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_baseline_candidate_promotion_readiness(
        EIGBaselineCandidatePromotionReadinessConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            skip_github=args.skip_github,
        )
    )
    print("EIG BASELINE CANDIDATE PROMOTION READINESS REPORT " + str(args.output_path))
    print("EIG BASELINE CANDIDATE PROMOTION READINESS SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print(
            "EIG BASELINE CANDIDATE PROMOTION READINESS ERRORS "
            + json.dumps(report["validation_errors"], sort_keys=True)
        )
        return 1
    print("EIG BASELINE CANDIDATE PROMOTION READINESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
