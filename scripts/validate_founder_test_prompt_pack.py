#!/usr/bin/env python3
"""Validate the Phase 137 founder test prompt pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.founder_test_prompt_pack import (  # noqa: E402
    DEFAULT_PACK_PATH,
    FounderTestPromptPackConfig,
    run_prompt_pack_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--pack-path", default=str(DEFAULT_PACK_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/founder-test-prompt-pack/phase137/phase137-founder-test-prompt-pack.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_prompt_pack_gate(
        FounderTestPromptPackConfig(
            config_root=Path(args.config_root),
            pack_path=Path(args.pack_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("FOUNDER TEST PROMPT PACK " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("FOUNDER TEST PROMPT PACK ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("FOUNDER TEST PROMPT PACK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
