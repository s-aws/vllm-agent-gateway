#!/usr/bin/env python3
"""Validate connector eval release gate proof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.connector_eval_release_gate import (  # noqa: E402
    ConnectorEvalReleaseGateError,
    run_connector_eval_release_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate connector eval release gate proof.")
    parser.add_argument("--config-root", default=".", help="Repository/config root.")
    parser.add_argument("--packet-path", default=None, help="Connector release packet JSON path. Defaults to sample packet.")
    parser.add_argument(
        "--output-path",
        default="runtime-state/connector-eval-release-gate/phase283/phase283-connector-eval-release-gate-report.json",
        help="Output report path.",
    )
    args = parser.parse_args()

    try:
        report = run_connector_eval_release_gate(
            config_root=Path(args.config_root).resolve(),
            packet_path=Path(args.packet_path).resolve() if args.packet_path else None,
            output_path=Path(args.output_path).resolve(),
        )
    except ConnectorEvalReleaseGateError as exc:
        print(f"CONNECTOR EVAL RELEASE GATE FAIL: {exc}", file=sys.stderr)
        return 1
    print("CONNECTOR EVAL RELEASE GATE PASS " + json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
