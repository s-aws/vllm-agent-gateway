#!/usr/bin/env python3
"""Validate Phase 222 chunked-investigation executor contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.chunked_investigation_executor_contract import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    ChunkedInvestigationExecutorContractConfig,
    run_chunked_investigation_executor_contract,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--no-require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_chunked_investigation_executor_contract(
        ChunkedInvestigationExecutorContractConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            require_artifacts=not args.no_require_artifacts,
        )
    )
    print("PHASE222 CHUNKED INVESTIGATION EXECUTOR CONTRACT SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") != "passed":
        print(
            "PHASE222 CHUNKED INVESTIGATION EXECUTOR CONTRACT FAILURES "
            + json.dumps(report.get("validation_errors", []), sort_keys=True)
        )
        return 1
    print("PHASE222 CHUNKED INVESTIGATION EXECUTOR CONTRACT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
