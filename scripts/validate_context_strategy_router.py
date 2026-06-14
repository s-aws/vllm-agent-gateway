#!/usr/bin/env python3
"""Validate Phase 220 context strategy router."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.context_strategy_router import (  # noqa: E402
    ContextStrategyRouterConfig,
    run_context_strategy_router,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    parser.add_argument("--no-require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    config = ContextStrategyRouterConfig(
        config_root=config_root,
        policy_path=Path(args.policy_path) if args.policy_path else ContextStrategyRouterConfig.policy_path,
        output_path=Path(args.output_path) if args.output_path else ContextStrategyRouterConfig.output_path,
        markdown_output_path=Path(args.markdown_output_path)
        if args.markdown_output_path
        else ContextStrategyRouterConfig.markdown_output_path,
        require_artifacts=not args.no_require_artifacts,
    )
    report = run_context_strategy_router(config)
    print(json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
