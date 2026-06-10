#!/usr/bin/env python3
"""Classify Phase 134 founder smoke results into governed feedback decisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.founder_smoke_feedback import (  # noqa: E402
    DEFAULT_SMOKE_REPORT_PATH,
    FounderSmokeFeedbackConfig,
    run_founder_smoke_feedback_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--smoke-report-path", default=str(DEFAULT_SMOKE_REPORT_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/founder-smoke-feedback/phase135/phase135-founder-smoke-feedback.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_founder_smoke_feedback_gate(
        FounderSmokeFeedbackConfig(
            config_root=Path(args.config_root),
            smoke_report_path=Path(args.smoke_report_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("FOUNDER SMOKE FEEDBACK " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("FOUNDER SMOKE FEEDBACK ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("FOUNDER SMOKE FEEDBACK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
