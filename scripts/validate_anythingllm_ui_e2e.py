#!/usr/bin/env python3
"""Validate the browser-rendered AnythingLLM Desktop UI path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.anythingllm_ui_e2e import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    AnythingLLMUiE2EConfig,
    AnythingLLMUiE2EStatus,
    run_anythingllm_ui_e2e,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--ui-dist-root", default=None)
    parser.add_argument("--app-asar-path", default=None)
    parser.add_argument("--extract-root", default=None)
    parser.add_argument("--refresh-extract", action="store_true")
    parser.add_argument("--npx-command", default=None)
    parser.add_argument("--browser-channel", default="")
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--static-port", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_anythingllm_ui_e2e(
        AnythingLLMUiE2EConfig(
            config_root=Path(args.config_root),
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            target_roots=tuple(args.target_roots or DEFAULT_TARGET_ROOTS),
            output_path=Path(args.output_path) if args.output_path else None,
            ui_dist_root=Path(args.ui_dist_root) if args.ui_dist_root else None,
            app_asar_path=Path(args.app_asar_path) if args.app_asar_path else None,
            extract_root=Path(args.extract_root) if args.extract_root else None,
            refresh_extract=args.refresh_extract,
            npx_command=args.npx_command,
            browser_channel=args.browser_channel,
            timeout_seconds=args.timeout_seconds,
            static_port=args.static_port,
        )
    )
    print(f"ANYTHINGLLM UI E2E REPORT {report['report_path']}")
    print(
        "ANYTHINGLLM UI E2E SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "workspace": report["config"]["workspace"],
                "target_roots": report["config"]["target_roots"],
                "case_count": len(report.get("ui", {}).get("cases", [])),
                "fixture_unchanged": report.get("fixture_unchanged"),
                "error_count": len(report.get("errors", [])),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != AnythingLLMUiE2EStatus.PASSED.value:
        print("ANYTHINGLLM UI E2E FAILURES " + json.dumps(report.get("errors", []), ensure_ascii=True))
        return 1
    print("ANYTHINGLLM UI E2E PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
