#!/usr/bin/env python3
"""Validate Phase 320 clone-safe context strategy router replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.context_strategy_router_clone_replay import (  # noqa: E402
    ContextStrategyRouterCloneReplayConfig,
    run_context_strategy_router_clone_replay,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    config = ContextStrategyRouterCloneReplayConfig(
        config_root=config_root,
        policy_path=Path(args.policy_path) if args.policy_path else ContextStrategyRouterCloneReplayConfig.policy_path,
        output_path=Path(args.output_path) if args.output_path else ContextStrategyRouterCloneReplayConfig.output_path,
        markdown_output_path=Path(args.markdown_output_path)
        if args.markdown_output_path
        else ContextStrategyRouterCloneReplayConfig.markdown_output_path,
    )
    report = run_context_strategy_router_clone_replay(config)
    print("CONTEXT STRATEGY ROUTER CLONE REPLAY REPORT", config.output_path)
    print("CONTEXT STRATEGY ROUTER CLONE REPLAY SUMMARY", json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report.get("status") == "passed":
        print("CONTEXT STRATEGY ROUTER CLONE REPLAY PASS")
        return 0
    print("CONTEXT STRATEGY ROUTER CLONE REPLAY FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
