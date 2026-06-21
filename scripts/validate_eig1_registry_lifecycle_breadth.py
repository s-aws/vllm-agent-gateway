#!/usr/bin/env python3
"""Validate EIG-1 registry lifecycle breadth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig1_registry_lifecycle_breadth import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIG1RegistryLifecycleBreadthConfig,
    run_eig1_registry_lifecycle_breadth,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig1_registry_lifecycle_breadth(
        EIG1RegistryLifecycleBreadthConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG1 REGISTRY LIFECYCLE BREADTH REPORT {report['report_path']}")
    print(
        "EIG1 REGISTRY LIFECYCLE BREADTH SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "connector_count": report.get("summary", {}).get("connector_count"),
                "scenario_count": report.get("summary", {}).get("scenario_count"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "future_gap_documented": report.get("summary", {}).get("future_gap_documented"),
                "phase296_ready": report.get("summary", {}).get("phase296_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG1 REGISTRY LIFECYCLE BREADTH FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG1 REGISTRY LIFECYCLE BREADTH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
