#!/usr/bin/env python3
"""Validate Phase 151 skill/tool selection explainability E2E."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.skill_tool_selection_explainability_e2e import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_POLICY_PATH,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    SkillToolSelectionExplainabilityE2EConfig,
    run_skill_tool_selection_explainability_e2e,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default=(
            "runtime-state/skill-tool-selection-explainability-e2e/phase151/"
            "phase151-skill-tool-selection-explainability-e2e-report.json"
        ),
    )
    parser.add_argument(
        "--markdown-output-path",
        default=(
            "runtime-state/skill-tool-selection-explainability-e2e/phase151/"
            "phase151-skill-tool-selection-explainability-e2e-report.md"
        ),
    )
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_skill_tool_selection_explainability_e2e(
        SkillToolSelectionExplainabilityE2EConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            include_gateway=not args.skip_gateway,
            include_anythingllm=not args.skip_anythingllm,
            model_base_url=args.model_base_url,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            controller_base_url=args.controller_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("SKILL TOOL SELECTION EXPLAINABILITY E2E SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("SKILL TOOL SELECTION EXPLAINABILITY E2E ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL TOOL SELECTION EXPLAINABILITY E2E PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

