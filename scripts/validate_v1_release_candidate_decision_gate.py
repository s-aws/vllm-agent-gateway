#!/usr/bin/env python3
"""Validate Phase 244 V1 release-candidate decision gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.v1_release_candidate_decision_gate import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    V1ReleaseCandidateDecisionGateConfig,
    validate_v1_release_candidate_decision_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--allow-missing-artifacts", action="store_true")
    parser.add_argument("--skip-live-health", action="store_true")
    parser.add_argument("--health-timeout-seconds", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_v1_release_candidate_decision_gate(
        V1ReleaseCandidateDecisionGateConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            require_artifacts=not args.allow_missing_artifacts,
            run_live_health=not args.skip_live_health,
            health_timeout_seconds=args.health_timeout_seconds,
        )
    )
    print(
        "PHASE244 V1 RELEASE CANDIDATE DECISION GATE SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "blocker_count": report["summary"]["blocker_count"],
                "runtime_health_blocker_count": report["summary"]["runtime_health_blocker_count"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    print("PHASE244 V1 RELEASE CANDIDATE DECISION GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
