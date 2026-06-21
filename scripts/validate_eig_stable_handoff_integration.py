#!/usr/bin/env python3
"""Validate the Phase 304 EIG stable handoff integration packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_stable_handoff_integration import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGStableHandoffIntegrationConfig,
    run_eig_stable_handoff_integration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/eig-stable-handoff-integration/phase304-validation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_stable_handoff_integration(
        EIGStableHandoffIntegrationConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
        )
    )
    print("EIG STABLE HANDOFF INTEGRATION REPORT " + str(args.output_path))
    print(
        "EIG STABLE HANDOFF INTEGRATION SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != "passed":
        print(
            "EIG STABLE HANDOFF INTEGRATION ERRORS "
            + json.dumps(report["validation_errors"], ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("EIG STABLE HANDOFF INTEGRATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
