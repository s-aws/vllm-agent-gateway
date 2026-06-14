#!/usr/bin/env python3
"""Validate Phase 234 clean-clone or clean-snapshot release handoff proof."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.clean_clone_release_handoff import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_SNAPSHOT_ROOT,
    CleanCloneReleaseHandoffConfig,
    SourceMode,
    run_clean_clone_release_handoff,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--snapshot-root", default=str(DEFAULT_SNAPSHOT_ROOT))
    parser.add_argument("--source-mode", choices=[item.value for item in SourceMode], default=SourceMode.CLEAN_SNAPSHOT.value)
    parser.add_argument("--prepare-snapshot", action="store_true")
    parser.add_argument("--run-commands", action="store_true")
    parser.add_argument("--run-live-minimal", action="store_true")
    parser.add_argument("--managed-state-root", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_clean_clone_release_handoff(
        CleanCloneReleaseHandoffConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            snapshot_root=Path(args.snapshot_root),
            source_mode=SourceMode(args.source_mode),
            prepare_snapshot=args.prepare_snapshot,
            run_commands=args.run_commands,
            run_live_minimal=args.run_live_minimal,
            managed_state_root=Path(args.managed_state_root) if args.managed_state_root else None,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("PHASE234 CLEAN CLONE RELEASE HANDOFF SUMMARY " + json.dumps(report["summary"], sort_keys=True))
    if report["status"] != "passed":
        print("PHASE234 CLEAN CLONE RELEASE HANDOFF ERRORS " + json.dumps(report["validation_errors"], sort_keys=True))
        return 1
    print("PHASE234 CLEAN CLONE RELEASE HANDOFF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
