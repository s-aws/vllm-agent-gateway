#!/usr/bin/env python3
"""Validate the Phase 312 EIG baseline-candidate blind baselines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_baseline_candidate_blind_baselines import (  # noqa: E402
    DEFAULT_BASELINE_PATH,
    EIGBaselineCandidateBlindBaselineConfig,
    run_eig_baseline_candidate_blind_baselines,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--baseline-path", default=str(DEFAULT_BASELINE_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/eig-baseline-candidate-blind-baselines/phase312-validation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_baseline_candidate_blind_baselines(
        EIGBaselineCandidateBlindBaselineConfig(
            config_root=Path(args.config_root),
            baseline_path=Path(args.baseline_path),
            output_path=Path(args.output_path),
        )
    )
    print("EIG BASELINE CANDIDATE BLIND BASELINES REPORT " + str(args.output_path))
    print("EIG BASELINE CANDIDATE BLIND BASELINES SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("EIG BASELINE CANDIDATE BLIND BASELINES ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("EIG BASELINE CANDIDATE BLIND BASELINES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
