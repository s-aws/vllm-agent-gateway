#!/usr/bin/env python3
"""Run streaming documenter modes for large single-document inputs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from vllm_agent_gateway.controllers.documenter.streaming import (  # noqa: E402
    DEFAULT_CHUNK_BYTES,
    DEFAULT_CLASSIFICATION_LABELS,
    DEFAULT_MAX_MODEL_RECORDS,
    DEFAULT_MAX_OUTLINE_ENTRIES,
    DEFAULT_MAX_QUERY_MATCHES,
    DEFAULT_MAX_SUMMARIES,
    DEFAULT_MAX_SUMMARY_DEPTH,
    DEFAULT_MODEL,
    DEFAULT_MODEL_OUTPUT_TOKENS,
    DEFAULT_READ_BLOCK_BYTES,
    MODE_REGISTRY,
    StreamingDocumenterError,
    StreamingDocumenterInvocationRequest,
    invoke_streaming_documenter,
)


DEFAULT_OUTPUT_DIR = ".agentic_reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded streaming documenter modes.")
    parser.add_argument("--target-root", "--repo-root", dest="target_root", default=".")
    parser.add_argument("--doc", required=True, help="Document path inside --target-root.")
    parser.add_argument("--mode", choices=sorted(MODE_REGISTRY), default="context_presence")
    parser.add_argument(
        "--query",
        default=None,
        help="Literal query string. Required for context_presence; optional for token_count query-match output.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Artifact directory. Relative paths are resolved from the current working directory.",
    )
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    parser.add_argument("--read-block-bytes", type=int, default=DEFAULT_READ_BLOCK_BYTES)
    parser.add_argument("--max-bytes", type=int, default=None, help="Stop after reviewing this many file bytes.")
    parser.add_argument("--max-chunks", type=int, default=None, help="Stop after reviewing this many chunks.")
    parser.add_argument(
        "--max-outline-entries",
        type=int,
        default=DEFAULT_MAX_OUTLINE_ENTRIES,
        help="Maximum heading entries retained by outline-capable modes.",
    )
    parser.add_argument(
        "--max-query-matches",
        type=int,
        default=DEFAULT_MAX_QUERY_MATCHES,
        help="Maximum query match records retained by query-capable modes.",
    )
    parser.add_argument(
        "--max-elapsed-seconds",
        type=float,
        default=None,
        help="Stop after this many elapsed seconds.",
    )
    parser.add_argument(
        "--stop-after-chunks",
        type=int,
        default=None,
        help="Pause after N chunks. Intended for resume smoke testing.",
    )
    parser.add_argument("--resume", default=None, help="Resume from a streaming-state JSON artifact.")
    parser.add_argument(
        "--resume-allow-arg-changes",
        action="store_true",
        help="Allow resume even when compatible controller arguments changed.",
    )
    parser.add_argument(
        "--role-base-url",
        default=None,
        help="OpenAI-compatible role endpoint base URL. Required for model-assisted modes.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AGENTIC_GATEWAY_MODEL", DEFAULT_MODEL),
        help="Model name for model-assisted modes.",
    )
    parser.add_argument("--timeout", type=int, default=600, help="HTTP timeout for model-assisted calls.")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MODEL_OUTPUT_TOKENS,
        help="Maximum output tokens requested per model-assisted chunk.",
    )
    parser.add_argument(
        "--max-model-records",
        type=int,
        default=DEFAULT_MAX_MODEL_RECORDS,
        help="Maximum retained facts/classifications/risks across model-assisted chunks.",
    )
    parser.add_argument(
        "--classification-label",
        action="append",
        default=None,
        help="Allowed classify label. May be repeated. Defaults to the built-in document labels.",
    )
    parser.add_argument(
        "--max-summaries",
        type=int,
        default=DEFAULT_MAX_SUMMARIES,
        help="Maximum summaries per recursive summarize merge packet.",
    )
    parser.add_argument(
        "--max-summary-depth",
        type=int,
        default=DEFAULT_MAX_SUMMARY_DEPTH,
        help="Maximum recursive summarize merge depth.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = invoke_streaming_documenter(StreamingDocumenterInvocationRequest.from_namespace(args))
    print(f"Wrote {result.artifact_paths['streaming_report']}")
    print(f"Wrote {result.artifact_paths['streaming_state']}")
    if result.summary_text:
        print(result.summary_text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StreamingDocumenterError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
