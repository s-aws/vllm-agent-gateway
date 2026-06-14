#!/usr/bin/env python3
"""Validate Phase 240 remote-clone non-Coinbase generalization replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.remote_clone_non_coinbase_generalization_replay import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    RemoteCloneGeneralizationReplayConfig,
    RemoteCloneGeneralizationStatus,
    run_remote_clone_non_coinbase_generalization_replay,
)
from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument(
        "--output-path",
        default=(
            "runtime-state/remote-clone-non-coinbase-generalization-replay/phase240/"
            "phase240-remote-clone-non-coinbase-generalization-replay-report.json"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_remote_clone_non_coinbase_generalization_replay(
        RemoteCloneGeneralizationReplayConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            policy_path=Path(args.policy_path),
            include_gateway=not args.skip_gateway,
            include_anythingllm=not args.skip_anythingllm,
            model_base_url=args.model_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(
        "REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY "
        + json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "summary": report["summary"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != RemoteCloneGeneralizationStatus.PASSED.value:
        print("REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True))
        return 1
    print("REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
