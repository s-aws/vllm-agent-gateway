#!/usr/bin/env python3
"""Validate the Phase 303 EIG-3 breadth closeout packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig3_breadth_closeout import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIG3BreadthCloseoutConfig,
    run_eig3_breadth_closeout,
)
from vllm_agent_gateway.acceptance.v1 import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default="runtime-state/eig3-breadth-closeout/phase303-validation.json")
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--no-live-runtime", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig3_breadth_closeout(
        EIG3BreadthCloseoutConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            run_live_runtime=not args.no_live_runtime,
            include_anythingllm=not args.skip_anythingllm,
        )
    )
    print("EIG3 BREADTH CLOSEOUT REPORT " + str(args.output_path))
    print("EIG3 BREADTH CLOSEOUT SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("EIG3 BREADTH CLOSEOUT ERRORS " + json.dumps(report["validation_errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG3 BREADTH CLOSEOUT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
