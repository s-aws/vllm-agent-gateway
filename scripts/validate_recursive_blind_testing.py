#!/usr/bin/env python3
"""Validate bounded recursive blind-testing policy and optional reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.recursive_blind_testing import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    RecursiveBlindTestingValidationConfig,
    validate_recursive_blind_testing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--report", default=None, help="Optional recursive_blind_testing_report to validate.")
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_recursive_blind_testing(
        RecursiveBlindTestingValidationConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            report_path=Path(args.report) if args.report else None,
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"RECURSIVE BLIND TESTING REPORT {report['report_path']}")
    print(
        "RECURSIVE BLIND TESTING SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "policy_path": report.get("policy_path"),
                "validated_report_path": report.get("validated_report_path"),
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "policy_validated": report.get("summary", {}).get("policy_validated"),
                "report_validated": report.get("summary", {}).get("report_validated"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("RECURSIVE BLIND TESTING FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("RECURSIVE BLIND TESTING PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
