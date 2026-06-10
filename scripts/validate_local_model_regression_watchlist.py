#!/usr/bin/env python3
"""Validate the Phase 139 local-model regression watchlist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.local_model_regression_watchlist import (  # noqa: E402
    DEFAULT_WATCHLIST_PATH,
    LocalModelRegressionWatchlistConfig,
    run_local_model_regression_watchlist_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--watchlist-path", default=str(DEFAULT_WATCHLIST_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/local-model-regression-watchlist/phase139/phase139-local-model-regression-watchlist-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_local_model_regression_watchlist_gate(
        LocalModelRegressionWatchlistConfig(
            config_root=Path(args.config_root),
            watchlist_path=Path(args.watchlist_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("LOCAL MODEL REGRESSION WATCHLIST " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("LOCAL MODEL REGRESSION WATCHLIST ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("LOCAL MODEL REGRESSION WATCHLIST PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
