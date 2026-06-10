#!/usr/bin/env python3
"""Validate Phase 142 baseline corpus promotion rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.baseline_corpus_promotion_rules import (  # noqa: E402
    DEFAULT_RULES_PATH,
    BaselineCorpusPromotionRulesConfig,
    run_promotion_rules_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--rules-path", default=str(DEFAULT_RULES_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/baseline-corpus-promotion-rules/phase142/phase142-baseline-corpus-promotion-rules-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_promotion_rules_gate(
        BaselineCorpusPromotionRulesConfig(
            config_root=Path(args.config_root),
            rules_path=Path(args.rules_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("BASELINE CORPUS PROMOTION RULES " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("BASELINE CORPUS PROMOTION RULES ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("BASELINE CORPUS PROMOTION RULES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
