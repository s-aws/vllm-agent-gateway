#!/usr/bin/env python3
"""Build and validate a stable release refresh report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.stable_release_refresh import (  # noqa: E402
    DEFAULT_MARKDOWN_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_REPORT_PATH,
    StableReleaseRefreshConfig,
    run_stable_release_refresh,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_PATH))
    parser.add_argument("--run-refresh", action="store_true")
    parser.add_argument("--execute-reset-start", action="store_true")
    parser.add_argument("--execute-recovery", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_stable_release_refresh(
        StableReleaseRefreshConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            run_refresh=args.run_refresh,
            timeout_seconds=args.timeout_seconds,
            execute_reset_start=args.execute_reset_start,
            execute_recovery=args.execute_recovery,
        )
    )
    phase = str(report.get("phase"))
    print(f"PHASE{phase} STABLE RELEASE REFRESH REPORT " + str(report.get("report_path")))
    print(f"PHASE{phase} STABLE RELEASE REFRESH SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print(f"PHASE{phase} STABLE RELEASE REFRESH ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print(f"PHASE{phase} STABLE RELEASE REFRESH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
