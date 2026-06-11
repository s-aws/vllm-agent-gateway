#!/usr/bin/env python3
"""Validate Phase 190 unsupported-scope refusal quality."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.unsupported_scope_refusal_quality import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_POLICY_PATH,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    UnsupportedScopeRefusalQualityConfig,
    run_unsupported_scope_refusal_quality,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_unsupported_scope_refusal_quality(
        UnsupportedScopeRefusalQualityConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path) if args.output_path else None,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            timeout_seconds=args.timeout_seconds,
            run_live=args.run_live,
            include_anythingllm=not args.skip_anythingllm,
        )
    )
    print("PHASE190 UNSUPPORTED SCOPE REFUSAL QUALITY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        failed = [
            {
                "case_id": case.get("case_id"),
                "surface": case.get("surface"),
                "target_root": case.get("target_root"),
                "findings": case.get("findings"),
            }
            for case in report.get("cases", [])
            if isinstance(case, dict) and case.get("status") != "passed"
        ]
        print("PHASE190 UNSUPPORTED SCOPE REFUSAL QUALITY FAILURES " + json.dumps(failed, ensure_ascii=True, sort_keys=True))
        print("PHASE190 UNSUPPORTED SCOPE REFUSAL QUALITY ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE190 UNSUPPORTED SCOPE REFUSAL QUALITY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
