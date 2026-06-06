#!/usr/bin/env python3
"""Generate a compact observability report for recent controller runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.run_inspector import (  # noqa: E402
    InspectorOutputFormat,
    RunObservabilityConfig,
    format_run_observability,
    observe_runs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--controller-output-root", default=None)
    parser.add_argument("--workflow", default="workflow_router.plan")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--prompt-family", default=None)
    parser.add_argument("--skill", default=None)
    parser.add_argument("--model-status", default=None)
    parser.add_argument("--target-root", default=None)
    parser.add_argument("--route-status", default=None)
    parser.add_argument("--semantic-status", default=None)
    parser.add_argument("--failure-category", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--format", choices=[item.value for item in InspectorOutputFormat], default=InspectorOutputFormat.TEXT.value)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = observe_runs(
            RunObservabilityConfig(
                config_root=Path(args.config_root),
                controller_output_root=Path(args.controller_output_root) if args.controller_output_root else None,
                workflow=args.workflow or None,
                limit=args.limit,
                prompt_family=args.prompt_family,
                skill=args.skill,
                model_status=args.model_status,
                target_root=args.target_root,
                route_status=args.route_status,
                semantic_status=args.semantic_status,
                failure_category=args.failure_category,
                output_path=Path(args.output_path) if args.output_path else None,
                output_format=InspectorOutputFormat(args.format),
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"RUN OBSERVABILITY FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if args.format == InspectorOutputFormat.JSON.value:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(format_run_observability(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
