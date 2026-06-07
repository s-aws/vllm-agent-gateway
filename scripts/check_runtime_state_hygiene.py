#!/usr/bin/env python3
"""Check that local runtime-state artifacts are ignored and proof metadata is retained."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.runtime_state_hygiene import (  # noqa: E402
    DEFAULT_STABLE_PROOF_PATH,
    RuntimeStateHygieneConfig,
    validate_runtime_state_hygiene,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--stable-proof-path", default=str(DEFAULT_STABLE_PROOF_PATH))
    parser.add_argument("--command-timeout-seconds", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path) if args.output_path else None,
            stable_proof_path=Path(args.stable_proof_path),
            command_timeout_seconds=args.command_timeout_seconds,
        )
    )
    print(f"RUNTIME STATE HYGIENE REPORT {report['report_path']}")
    print(
        "RUNTIME STATE HYGIENE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "check_count": report.get("summary", {}).get("check_count"),
                "failed_check_ids": report.get("summary", {}).get("failed_check_ids"),
                "stable_proof_path": report.get("stable_proof_path"),
                "ignore_sample_paths": report.get("ignore_sample_paths"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        failures = [item for item in report.get("checks", []) if item.get("status") == "failed"]
        print("RUNTIME STATE HYGIENE FAILURES " + json.dumps(failures, ensure_ascii=True, sort_keys=True))
        return 1
    print("RUNTIME STATE HYGIENE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
