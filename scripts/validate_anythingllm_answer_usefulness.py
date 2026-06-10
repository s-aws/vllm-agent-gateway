#!/usr/bin/env python3
"""Validate that governed AnythingLLM responses are useful directly in chat."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.anythingllm_answer_usefulness import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    DEFAULT_CORPUS_PATH,
    AnythingLLMAnswerUsefulnessConfig,
    run_anythingllm_answer_usefulness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--corpus-path", default=str(DEFAULT_CORPUS_PATH))
    parser.add_argument("--contract-path", default=str(DEFAULT_CONTRACT_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/anythingllm-answer-usefulness/anythingllm-answer-usefulness-report.json",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_anythingllm_answer_usefulness(
        AnythingLLMAnswerUsefulnessConfig(
            config_root=Path(args.config_root),
            corpus_path=Path(args.corpus_path),
            contract_path=Path(args.contract_path),
            output_path=Path(args.output_path),
            require_artifacts=args.require_artifacts,
        )
    )
    print("ANYTHINGLLM ANSWER USEFULNESS " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("ANYTHINGLLM ANSWER USEFULNESS ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("ANYTHINGLLM ANSWER USEFULNESS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
