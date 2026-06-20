#!/usr/bin/env python3
"""Validate EIG-3 synthetic sensitive-data fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig3_sensitive_data import (  # noqa: E402
    DEFAULT_FIXTURE_PATH,
    EIG3SensitiveDataConfig,
    run_eig3_sensitive_data_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig3_sensitive_data_validation(
        EIG3SensitiveDataConfig(
            config_root=Path(args.config_root),
            fixture_path=Path(args.fixtures),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG3 SENSITIVE DATA REPORT {report['report_path']}")
    print(
        "EIG3 SENSITIVE DATA SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "fixture_count": report.get("summary", {}).get("fixture_count"),
                "archetype_count": report.get("summary", {}).get("archetype_count"),
                "failed_fixture_count": report.get("summary", {}).get("failed_fixture_count"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "phase299_ready": report.get("summary", {}).get("phase299_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG3 SENSITIVE DATA FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG3 SENSITIVE DATA PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
