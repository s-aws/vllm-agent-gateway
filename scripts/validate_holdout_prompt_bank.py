#!/usr/bin/env python3
"""Validate the governed Priority 0 holdout prompt bank."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.holdout_prompt_bank import (  # noqa: E402
    DEFAULT_CORPUS_PATH,
    DEFAULT_HOLDOUT_BANK_PATH,
    HoldoutPromptBankConfig,
    run_holdout_prompt_bank_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--corpus-path", default=str(DEFAULT_CORPUS_PATH))
    parser.add_argument("--bank-path", default=str(DEFAULT_HOLDOUT_BANK_PATH))
    parser.add_argument("--output-path", default="runtime-state/holdout-prompt-bank/holdout-prompt-bank-report.json")
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_holdout_prompt_bank_validation(
        HoldoutPromptBankConfig(
            config_root=Path(args.config_root),
            corpus_path=Path(args.corpus_path),
            bank_path=Path(args.bank_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("HOLDOUT PROMPT BANK " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("HOLDOUT PROMPT BANK ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("HOLDOUT PROMPT BANK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
