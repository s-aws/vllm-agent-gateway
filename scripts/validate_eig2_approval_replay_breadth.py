#!/usr/bin/env python3
"""Validate EIG-2 approval replay breadth fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig2_approval_replay_breadth import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIG2ApprovalReplayBreadthConfig,
    run_eig2_approval_replay_breadth_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig2_approval_replay_breadth_validation(
        EIG2ApprovalReplayBreadthConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG2 APPROVAL REPLAY BREADTH REPORT {report['report_path']}")
    print(
        "EIG2 APPROVAL REPLAY BREADTH SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "approval_replay_case_count": report.get("summary", {}).get("approval_replay_case_count"),
                "all_required_scenarios_passed": report.get("summary", {}).get("all_required_scenarios_passed"),
                "audit_validation_passed": report.get("summary", {}).get("audit_validation_passed"),
                "scope_change_denied": report.get("summary", {}).get("scope_change_denied"),
                "non_dry_run_write_denied": report.get("summary", {}).get("non_dry_run_write_denied"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "phase295_ready": report.get("summary", {}).get("phase295_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG2 APPROVAL REPLAY BREADTH FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG2 APPROVAL REPLAY BREADTH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
