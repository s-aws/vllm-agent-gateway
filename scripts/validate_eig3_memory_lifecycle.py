#!/usr/bin/env python3
"""Validate EIG-3 governed memory lifecycle fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig3_memory_lifecycle import (  # noqa: E402
    DEFAULT_MEMORY_FIXTURE_PATH,
    EIG3MemoryLifecycleConfig,
    run_eig3_memory_lifecycle_validation,
)
from vllm_agent_gateway.acceptance.eig3_sensitive_data import DEFAULT_FIXTURE_PATH  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--memory-fixtures", default=str(DEFAULT_MEMORY_FIXTURE_PATH))
    parser.add_argument("--sensitive-fixtures", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig3_memory_lifecycle_validation(
        EIG3MemoryLifecycleConfig(
            config_root=Path(args.config_root),
            memory_fixture_path=Path(args.memory_fixtures),
            sensitive_fixture_path=Path(args.sensitive_fixtures),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG3 MEMORY LIFECYCLE REPORT {report['report_path']}")
    print(
        "EIG3 MEMORY LIFECYCLE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "record_count": report.get("summary", {}).get("record_count"),
                "allowed_record_count": report.get("summary", {}).get("allowed_record_count"),
                "denied_record_count": report.get("summary", {}).get("denied_record_count"),
                "failed_record_count": report.get("summary", {}).get("failed_record_count"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "phase301_ready": report.get("summary", {}).get("phase301_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG3 MEMORY LIFECYCLE FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG3 MEMORY LIFECYCLE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
