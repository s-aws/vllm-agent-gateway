#!/usr/bin/env python3
"""Validate Phase 316 EIG baseline-candidate holdout proof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig_baseline_candidate_holdout_proof import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    EIGBaselineCandidateHoldoutProofConfig,
    run_eig_baseline_candidate_holdout_proof,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/eig-baseline-candidate-holdout-proof/phase316-validation.json",
    )
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--anythingllm-workspace", default="my-workspace")
    parser.add_argument("--anythingllm-api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--controller-base-url", default="http://127.0.0.1:8400")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig_baseline_candidate_holdout_proof(
        EIGBaselineCandidateHoldoutProofConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            anythingllm_workspace=args.anythingllm_workspace,
            anythingllm_api_key_env=args.anythingllm_api_key_env,
            controller_base_url=args.controller_base_url,
            timeout_seconds=args.timeout_seconds,
            run_live=not args.no_live,
            include_anythingllm=not args.skip_anythingllm,
        )
    )
    print("EIG BASELINE CANDIDATE HOLDOUT PROOF REPORT " + str(args.output_path))
    print("EIG BASELINE CANDIDATE HOLDOUT PROOF SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("EIG BASELINE CANDIDATE HOLDOUT PROOF ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("EIG BASELINE CANDIDATE HOLDOUT PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
