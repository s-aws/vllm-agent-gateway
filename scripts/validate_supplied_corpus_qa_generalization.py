#!/usr/bin/env python3
"""Validate Phase 280 supplied-corpus QA generalization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.supplied_corpus_qa_generalization import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    SuppliedCorpusQaGeneralizationConfig,
    validate_supplied_corpus_qa_generalization,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--live-gateway", action="store_true", help="Run all unseen fixtures through the live workflow-router gateway.")
    parser.add_argument("--anythingllm", action="store_true", help="Run all unseen fixtures through the AnythingLLM workspace API.")
    parser.add_argument("--workflow-router-gateway-base-url", default="http://127.0.0.1:8500/v1")
    parser.add_argument("--model-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_supplied_corpus_qa_generalization(
        SuppliedCorpusQaGeneralizationConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
            artifact_dir=Path(args.artifact_dir),
            include_live_gateway=bool(args.live_gateway),
            include_anythingllm=bool(args.anythingllm),
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            model_base_url=args.model_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
        )
    )
    print("PHASE280 SUPPLIED CORPUS QA SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE280 SUPPLIED CORPUS QA FAIL")
        print("PHASE280 ERRORS " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE280 SUPPLIED CORPUS QA PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

