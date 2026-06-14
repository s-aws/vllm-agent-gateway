#!/usr/bin/env python3
"""Validate Phase 235 clone-safe model capability routing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.clone_safe_model_capability_routing import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    CloneSafeModelCapabilityRoutingConfig,
    run_clone_safe_model_capability_routing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--allow-missing-clean-handoff-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_clone_safe_model_capability_routing(
        CloneSafeModelCapabilityRoutingConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            require_clean_handoff_report=not args.allow_missing_clean_handoff_report,
        )
    )
    print("PHASE235 CLONE SAFE MODEL CAPABILITY ROUTING SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("PHASE235 CLONE SAFE MODEL CAPABILITY ROUTING ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("PHASE235 CLONE SAFE MODEL CAPABILITY ROUTING PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
