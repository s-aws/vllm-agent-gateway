#!/usr/bin/env python3
"""Validate Phase 245 release-candidate runtime health restoration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.release_candidate_runtime_health_restoration import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    ReleaseCandidateRuntimeHealthRestorationConfig,
    RuntimeHealthRestorationDecision,
    validate_release_candidate_runtime_health_restoration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument(
        "--anythingllm-workflow-router-base-url",
        default=None,
        help=(
            "Expected GenericOpenAiBasePath in AnythingLLM. "
            "Defaults to --workflow-router-gateway-base-url when omitted."
        ),
    )
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--health-timeout-seconds", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_release_candidate_runtime_health_restoration(
        ReleaseCandidateRuntimeHealthRestorationConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_workflow_router_base_url=args.anythingllm_workflow_router_base_url,
            workspace=args.workspace,
            model=args.model,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            health_timeout_seconds=args.health_timeout_seconds,
        )
    )
    summary = {
        "status": report["status"],
        "decision": report["decision"],
        "runtime_health_blocker_count": report["summary"]["runtime_health_blocker_count"],
        "blocker_count": report["summary"]["blocker_count"],
        "phase246_ready": report["summary"]["phase246_ready"],
    }
    print("PHASE245 RELEASE CANDIDATE RUNTIME HEALTH RESTORATION SUMMARY " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if report["decision"] != RuntimeHealthRestorationDecision.RESTORED.value:
        return 1
    print("PHASE245 RELEASE CANDIDATE RUNTIME HEALTH RESTORATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
