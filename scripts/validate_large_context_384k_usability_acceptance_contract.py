#!/usr/bin/env python3
"""Validate Phase 258 384k large-context usability acceptance contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.large_context_384k_usability_acceptance_contract import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    LargeContext384kUsabilityAcceptanceContractConfig,
    LargeContext384kUsabilityAcceptanceContractStatus,
    validate_large_context_384k_usability_acceptance_contract,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_large_context_384k_usability_acceptance_contract(
        LargeContext384kUsabilityAcceptanceContractConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
        )
    )
    print(
        "PHASE258 LARGE CONTEXT 384K USABILITY ACCEPTANCE CONTRACT SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != LargeContext384kUsabilityAcceptanceContractStatus.PASSED.value:
        print("PHASE258 LARGE CONTEXT 384K USABILITY ACCEPTANCE CONTRACT FAIL")
        return 1
    print("PHASE258 LARGE CONTEXT 384K USABILITY ACCEPTANCE CONTRACT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
