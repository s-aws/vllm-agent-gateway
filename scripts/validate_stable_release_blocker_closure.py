#!/usr/bin/env python3
"""Validate Phase 131 stable release blocker closure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.stable_release_blocker_closure import (  # noqa: E402
    DEFAULT_FOUNDER_FEEDBACK_CASES_PATH,
    DEFAULT_FOUNDER_FEEDBACK_REPORT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_PROMPT_TIGHTENING_REPORT_PATH,
    StableReleaseBlockerClosureConfig,
    run_stable_release_blocker_closure_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--prompt-tightening-report-path", default=str(DEFAULT_PROMPT_TIGHTENING_REPORT_PATH))
    parser.add_argument("--founder-feedback-report-path", default=str(DEFAULT_FOUNDER_FEEDBACK_REPORT_PATH))
    parser.add_argument("--founder-feedback-cases-path", default=str(DEFAULT_FOUNDER_FEEDBACK_CASES_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_stable_release_blocker_closure_gate(
        StableReleaseBlockerClosureConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            prompt_tightening_report_path=Path(args.prompt_tightening_report_path),
            founder_feedback_report_path=Path(args.founder_feedback_report_path),
            founder_feedback_cases_path=Path(args.founder_feedback_cases_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("STABLE RELEASE BLOCKER CLOSURE " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("STABLE RELEASE BLOCKER CLOSURE ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("STABLE RELEASE BLOCKER CLOSURE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
