#!/usr/bin/env python3
"""Validate Phase 130 stable chat-quality release readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.stable_chat_quality_release import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    StableChatQualityReleaseConfig,
    run_stable_chat_quality_release_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/stable-chat-quality-release/phase130/stable-chat-quality-release-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_stable_chat_quality_release_gate(
        StableChatQualityReleaseConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("STABLE CHAT QUALITY RELEASE " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("STABLE CHAT QUALITY RELEASE ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("STABLE CHAT QUALITY RELEASE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
