#!/usr/bin/env python3
"""Validate the Phase 296 EIG-1/EIG-2 breadth closeout packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_breadth_closeout import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGBreadthCloseoutConfig,
    run_eig_breadth_closeout,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default="runtime-state/eig-breadth-closeout/phase296-validation.json")
    parser.add_argument("--workflow-router-gateway-base-url", default=None)
    parser.add_argument("--live-runtime", action="store_true")
    parser.add_argument("--include-anythingllm", action="store_true")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--anythingllm-workspace", default="my-workspace")
    parser.add_argument("--anythingllm-api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_breadth_closeout(
        EIGBreadthCloseoutConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            run_live_runtime=args.live_runtime,
            include_anythingllm=args.include_anythingllm,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            anythingllm_workspace=args.anythingllm_workspace,
            anythingllm_api_key_env=args.anythingllm_api_key_env,
            controller_base_url=args.controller_base_url,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("EIG BREADTH CLOSEOUT REPORT " + str(args.output_path))
    print("EIG BREADTH CLOSEOUT SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("EIG BREADTH CLOSEOUT ERRORS " + json.dumps(report["validation_errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG BREADTH CLOSEOUT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
