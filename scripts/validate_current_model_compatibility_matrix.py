#!/usr/bin/env python3
"""Validate the Phase 150 current-model compatibility matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.current_model_compatibility_matrix import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    CurrentModelCompatibilityMatrixConfig,
    run_current_model_compatibility_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.json",
    )
    parser.add_argument(
        "--markdown-output-path",
        default="runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.md",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_current_model_compatibility_matrix(
        CurrentModelCompatibilityMatrixConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            require_artifacts=args.require_artifacts,
        )
    )
    print("CURRENT MODEL COMPATIBILITY SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("CURRENT MODEL COMPATIBILITY ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        print("CURRENT MODEL COMPATIBILITY BLOCKERS " + json.dumps(report["blockers"], ensure_ascii=True, sort_keys=True))
        return 1
    print("CURRENT MODEL COMPATIBILITY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
