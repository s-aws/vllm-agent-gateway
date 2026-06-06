#!/usr/bin/env python3
"""Validate project release channels and stable readiness rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.release_channels import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    ReleaseChannelId,
    ReleaseChannelValidationConfig,
    validate_release_channels,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--output-path", default=None)
    parser.add_argument(
        "--channel",
        choices=[item.value for item in ReleaseChannelId],
        default=None,
        help="Validate one channel contract after validating the manifest shape.",
    )
    parser.add_argument(
        "--release-candidate-report",
        default=None,
        help="Path to a passed v1_acceptance_report required only when stable is active.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=Path(args.config_root),
            manifest_path=Path(args.manifest),
            output_path=Path(args.output_path) if args.output_path else None,
            channel=args.channel,
            release_candidate_report_path=Path(args.release_candidate_report) if args.release_candidate_report else None,
        )
    )
    print(f"RELEASE CHANNEL REPORT {report['report_path']}")
    print(
        "RELEASE CHANNEL SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "harness_version": report.get("harness_version"),
                "channel_ids": report.get("channel_ids"),
                "selected_channel": report.get("selected_channel"),
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "warning_check_ids": report.get("summary", {}).get("warning_check_ids"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("RELEASE CHANNEL FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("RELEASE CHANNEL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
