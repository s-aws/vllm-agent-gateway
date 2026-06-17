#!/usr/bin/env python3
"""Validate Phase 278 adversarial context-stitching fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.adversarial_context_stitching import (  # noqa: E402
    DEFAULT_FIXTURE_DIR,
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    AdversarialContextStitchingConfig,
    AdversarialContextStitchingStatus,
    validate_adversarial_context_stitching,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (  # noqa: E402
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--fixture-dir", default=str(DEFAULT_FIXTURE_DIR))
    parser.add_argument("--answer-file", default=None, help="Optional captured gateway/model answer to score against the fixture.")
    parser.add_argument("--live-gateway", action="store_true", help="Send the generated standard prompt through the workflow-router gateway and score the answer.")
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_adversarial_context_stitching(
        AdversarialContextStitchingConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            fixture_dir=Path(args.fixture_dir),
            answer_file=Path(args.answer_file) if args.answer_file else None,
            live_gateway=bool(args.live_gateway),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            model_base_url=args.model_base_url,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("PHASE278 ADVERSARIAL CONTEXT STITCHING SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != AdversarialContextStitchingStatus.PASSED.value:
        print("PHASE278 ADVERSARIAL CONTEXT STITCHING FAIL")
        print("PHASE278 ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE278 ADVERSARIAL CONTEXT STITCHING PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
