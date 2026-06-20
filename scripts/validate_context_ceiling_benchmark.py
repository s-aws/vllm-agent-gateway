#!/usr/bin/env python3
"""Validate Phase 318 raw context ceiling benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.context_ceiling_benchmark import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    ContextCeilingBenchmarkConfig,
    run_context_ceiling_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/context-ceiling-benchmark/phase318-validation.json",
    )
    parser.add_argument("--model-base-url", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--no-live", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_context_ceiling_benchmark(
        ContextCeilingBenchmarkConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            run_live=not args.no_live,
            model_base_url=args.model_base_url,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("CONTEXT CEILING BENCHMARK REPORT " + str(args.output_path))
    print("CONTEXT CEILING BENCHMARK SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("CONTEXT CEILING BENCHMARK ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("CONTEXT CEILING BENCHMARK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
