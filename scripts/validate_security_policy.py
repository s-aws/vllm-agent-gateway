#!/usr/bin/env python3
"""Validate the local harness security policy and artifact exposure rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.security_policy import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    SecurityPolicyValidationConfig,
    validate_security_policy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=None)
    parser.add_argument(
        "--skip-secret-value-scan",
        action="store_true",
        help="Skip scanning configured files for configured secret environment variable values.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_security_policy(
        SecurityPolicyValidationConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            output_path=Path(args.output_path) if args.output_path else None,
            include_secret_value_scan=not args.skip_secret_value_scan,
        )
    )
    print(f"SECURITY POLICY REPORT {report['report_path']}")
    print(
        "SECURITY POLICY SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "status_counts": report.get("summary", {}).get("status_counts"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("SECURITY POLICY FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("SECURITY POLICY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
