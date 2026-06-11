#!/usr/bin/env python3
"""Build and validate the Phase 198 founder feedback intake and repair proposal report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.founder_feedback_intake_repair import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    FounderFeedbackIntakeRepairConfig,
    run_founder_feedback_intake_repair,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_founder_feedback_intake_repair(
        FounderFeedbackIntakeRepairConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    print(f"PHASE198 FOUNDER FEEDBACK INTAKE REPAIR REPORT {report['report_path']}")
    print("PHASE198 FOUNDER FEEDBACK INTAKE REPAIR SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE198 FOUNDER FEEDBACK INTAKE REPAIR ERRORS " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE198 FOUNDER FEEDBACK INTAKE REPAIR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
