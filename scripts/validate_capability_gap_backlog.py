#!/usr/bin/env python3
"""Validate the Phase 93 natural-language capability gap backlog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.capability_gap_backlog import (  # noqa: E402
    DEFAULT_BACKLOG_PATH,
    CapabilityGapBacklogValidationConfig,
    validate_capability_gap_backlog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--backlog", default=str(DEFAULT_BACKLOG_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_capability_gap_backlog(
        CapabilityGapBacklogValidationConfig(
            config_root=Path(args.config_root),
            backlog_path=Path(args.backlog),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"CAPABILITY GAP BACKLOG REPORT {report['report_path']}")
    print(
        "CAPABILITY GAP BACKLOG SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "backlog_path": report.get("backlog_path"),
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "backlog_validated": report.get("summary", {}).get("backlog_validated"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("CAPABILITY GAP BACKLOG FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("CAPABILITY GAP BACKLOG PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
