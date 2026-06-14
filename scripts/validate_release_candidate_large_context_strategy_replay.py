#!/usr/bin/env python3
"""Validate Phase 241 release-candidate large-context strategy replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)
from vllm_agent_gateway.acceptance.release_candidate_large_context_strategy_replay import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    ReleaseCandidateLargeContextReplayStatus,
    ReleaseCandidateLargeContextStrategyReplayConfig,
    run_release_candidate_large_context_strategy_replay,
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
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument(
        "--output-path",
        default=(
            "runtime-state/release-candidate-large-context-strategy-replay/phase241/"
            "phase241-release-candidate-large-context-strategy-replay-report.json"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_release_candidate_large_context_strategy_replay(
        ReleaseCandidateLargeContextStrategyReplayConfig(
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
        "RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY "
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
    if report["status"] != ReleaseCandidateLargeContextReplayStatus.PASSED.value:
        print("RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True))
        return 1
    print("RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
