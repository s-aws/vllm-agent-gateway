#!/usr/bin/env python3
"""Validate the Phase 307 EIG baseline-candidate intake packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_baseline_candidate_intake import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGBaselineCandidateIntakeConfig,
    run_eig_baseline_candidate_intake,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/eig-baseline-candidate-intake/phase307-validation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_baseline_candidate_intake(
        EIGBaselineCandidateIntakeConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
        )
    )
    print("EIG BASELINE CANDIDATE INTAKE REPORT " + str(args.output_path))
    print("EIG BASELINE CANDIDATE INTAKE SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("EIG BASELINE CANDIDATE INTAKE ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("EIG BASELINE CANDIDATE INTAKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
