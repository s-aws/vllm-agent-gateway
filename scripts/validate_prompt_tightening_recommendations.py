#!/usr/bin/env python3
"""Validate Phase 128 prompt-tightening recommendation governance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.prompt_tightening_recommendations import (  # noqa: E402
    DEFAULT_BASELINE_CORPUS_PATH,
    DEFAULT_FRESH_DRIFT_REPORT_PATH,
    DEFAULT_POLICY_PATH,
    PromptTighteningRecommendationConfig,
    run_prompt_tightening_recommendation_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--baseline-corpus-path", default=str(DEFAULT_BASELINE_CORPUS_PATH))
    parser.add_argument("--fresh-drift-report-path", default=str(DEFAULT_FRESH_DRIFT_REPORT_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/prompt-tightening-recommendations/phase128/prompt-tightening-recommendations-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_prompt_tightening_recommendation_gate(
        PromptTighteningRecommendationConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            baseline_corpus_path=Path(args.baseline_corpus_path),
            fresh_drift_report_path=Path(args.fresh_drift_report_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("PROMPT TIGHTENING RECOMMENDATIONS " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PROMPT TIGHTENING RECOMMENDATIONS ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PROMPT TIGHTENING RECOMMENDATIONS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
