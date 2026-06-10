#!/usr/bin/env python3
"""Validate Phase 138 chat transcript quality for founder smoke transcripts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.chat_transcript_quality import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    DEFAULT_TRANSCRIPT_REPORT_PATH,
    ChatTranscriptQualityConfig,
    run_chat_transcript_quality_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--transcript-report-path", default=str(DEFAULT_TRANSCRIPT_REPORT_PATH))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_chat_transcript_quality_gate(
        ChatTranscriptQualityConfig(
            config_root=Path(args.config_root),
            transcript_report_path=Path(args.transcript_report_path),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("CHAT TRANSCRIPT QUALITY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("CHAT TRANSCRIPT QUALITY ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("CHAT TRANSCRIPT QUALITY " + str(report["quality_status"]).upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
