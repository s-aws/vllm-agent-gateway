#!/usr/bin/env python3
"""Validate Phase 272 500k stale-index rejection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.large_context_500k_stale_index_rejection import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    LargeContext500kStaleIndexRejectionConfig,
    LargeContext500kStaleIndexRejectionStatus,
    validate_large_context_500k_stale_index_rejection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--skip-phase271-precondition", action="store_true")
    parser.add_argument("--skip-phase260-delegate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_large_context_500k_stale_index_rejection(
        LargeContext500kStaleIndexRejectionConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            validate_phase271_precondition=not args.skip_phase271_precondition,
            validate_phase260_delegate=not args.skip_phase260_delegate,
        )
    )
    print(
        "PHASE272 LARGE CONTEXT 500K STALE INDEX REJECTION SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != LargeContext500kStaleIndexRejectionStatus.PASSED.value:
        print("PHASE272 LARGE CONTEXT 500K STALE INDEX REJECTION FAIL")
        print("PHASE272 ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE272 LARGE CONTEXT 500K STALE INDEX REJECTION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
