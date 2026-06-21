#!/usr/bin/env python3
"""Validate the EIG-3 masking/refusal output-surface policy matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig3_output_surface_policy import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIG3OutputSurfacePolicyConfig,
    run_eig3_output_surface_policy_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--fixtures", default=None)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig3_output_surface_policy_validation(
        EIG3OutputSurfacePolicyConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy),
            fixture_path=Path(args.fixtures) if args.fixtures else None,
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG3 OUTPUT SURFACE POLICY REPORT {report['report_path']}")
    print(
        "EIG3 OUTPUT SURFACE POLICY SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "fixture_count": report.get("summary", {}).get("fixture_count"),
                "surface_count": report.get("summary", {}).get("surface_count"),
                "failed_fixture_count": report.get("summary", {}).get("failed_fixture_count"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "phase300_ready": report.get("summary", {}).get("phase300_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG3 OUTPUT SURFACE POLICY FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG3 OUTPUT SURFACE POLICY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
