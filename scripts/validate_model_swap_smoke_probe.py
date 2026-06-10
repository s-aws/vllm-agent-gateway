#!/usr/bin/env python3
"""Run the Phase 154 model-swap smoke probe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.model_swap_smoke_probe import (  # noqa: E402
    DEFAULT_CURRENT_MODEL_POLICY_PATH,
    DEFAULT_POLICY_PATH,
    ModelSwapSmokeProbeConfig,
    run_model_swap_smoke_probe,
)
from vllm_agent_gateway.acceptance.v1 import DEFAULT_MODEL_BASE_URL  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--current-model-policy-path", default=str(DEFAULT_CURRENT_MODEL_POLICY_PATH))
    parser.add_argument("--candidate-model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--output-path",
        default="runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json",
    )
    parser.add_argument(
        "--markdown-output-path",
        default="runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.md",
    )
    parser.add_argument("--compatibility-output-path", default=None)
    parser.add_argument("--compatibility-markdown-output-path", default=None)
    parser.add_argument("--no-require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_model_swap_smoke_probe(
        ModelSwapSmokeProbeConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            current_model_policy_path=Path(args.current_model_policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            candidate_model_base_url=args.candidate_model_base_url,
            timeout_seconds=args.timeout_seconds,
            compatibility_output_path=Path(args.compatibility_output_path)
            if args.compatibility_output_path
            else None,
            compatibility_markdown_output_path=Path(args.compatibility_markdown_output_path)
            if args.compatibility_markdown_output_path
            else None,
            require_artifacts=not args.no_require_artifacts,
        )
    )
    print(f"MODEL SWAP SMOKE PROBE REPORT {report['report_path']}")
    print(
        "MODEL SWAP SMOKE PROBE SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != "passed":
        print("MODEL SWAP SMOKE PROBE ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("MODEL SWAP SMOKE PROBE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
