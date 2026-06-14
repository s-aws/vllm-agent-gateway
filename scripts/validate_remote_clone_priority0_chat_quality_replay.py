#!/usr/bin/env python3
"""Validate Phase 239 remote-clone Priority 0 chat-quality replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.remote_clone_priority0_chat_quality_replay import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_POLICY_PATH,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    RemoteClonePriority0ReplayConfig,
    RemoteClonePriority0ReplayStatus,
    run_remote_clone_priority0_chat_quality_replay,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument(
        "--output-path",
        default=(
            "runtime-state/remote-clone-priority0-chat-quality-replay/phase239/"
            "phase239-remote-clone-priority0-chat-quality-replay-report.json"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_remote_clone_priority0_chat_quality_replay(
        RemoteClonePriority0ReplayConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            policy_path=Path(args.policy_path),
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print(
        "REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY "
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
    if report["status"] != RemoteClonePriority0ReplayStatus.PASSED.value:
        print("REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True))
        return 1
    print("REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
