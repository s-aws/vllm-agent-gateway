#!/usr/bin/env python3
"""Run Phase 140 AnythingLLM session recovery and greeting smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.anythingllm_session_recovery import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_WORKSPACE,
    AnythingLLMSessionRecoveryConfig,
    run_anythingllm_session_recovery,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument(
        "--output-path",
        default="runtime-state/anythingllm-session-recovery/phase140/phase140-anythingllm-session-recovery-report.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_anythingllm_session_recovery(
        AnythingLLMSessionRecoveryConfig(
            config_root=Path(args.config_root),
            output_path=Path(args.output_path),
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            include_live_anythingllm=not args.skip_anythingllm,
        )
    )
    print("ANYTHINGLLM SESSION RECOVERY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("ANYTHINGLLM SESSION RECOVERY ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("ANYTHINGLLM SESSION RECOVERY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
