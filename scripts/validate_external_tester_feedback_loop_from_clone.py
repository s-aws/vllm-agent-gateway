#!/usr/bin/env python3
"""Validate Phase 243 external-tester feedback loop proof from clone."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.external_tester_feedback_loop_from_clone import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    ExternalTesterFeedbackLoopFromCloneConfig,
    validate_external_tester_feedback_loop_from_clone,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--allow-missing-live-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_external_tester_feedback_loop_from_clone(
        ExternalTesterFeedbackLoopFromCloneConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            require_live_artifacts=not args.allow_missing_live_artifacts,
        )
    )
    print(
        "PHASE243 EXTERNAL TESTER FEEDBACK LOOP FROM CLONE SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != "passed":
        print("PHASE243 EXTERNAL TESTER FEEDBACK LOOP FROM CLONE FAIL")
        print(json.dumps(report["validation_errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE243 EXTERNAL TESTER FEEDBACK LOOP FROM CLONE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
