#!/usr/bin/env python3
"""Validate Phase 227 founder-feedback loop rebaseline artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.founder_feedback_loop_rebaseline import (  # noqa: E402
    DEFAULT_CASES_PATH,
    DEFAULT_LIVE_REPORT_PATH,
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    FounderFeedbackLoopRebaselineConfig,
    validate_founder_feedback_loop_rebaseline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--live-report-path", default=str(DEFAULT_LIVE_REPORT_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--require-live-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_founder_feedback_loop_rebaseline(
        FounderFeedbackLoopRebaselineConfig(
            config_root=Path(args.config_root),
            cases_path=Path(args.cases_path),
            live_report_path=Path(args.live_report_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            require_live_report=args.require_live_report,
        )
    )
    print("PHASE227 FOUNDER FEEDBACK REBASELINE SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE227 FOUNDER FEEDBACK REBASELINE FAIL")
        return 1
    print("PHASE227 FOUNDER FEEDBACK REBASELINE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
