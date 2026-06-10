#!/usr/bin/env python3
"""Validate or execute the Phase 157 founder field-test round."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.founder_field_round1 import (  # noqa: E402
    DEFAULT_FIELD_MARKDOWN_PATH,
    DEFAULT_FIELD_REPORT_PATH,
    DEFAULT_MARKDOWN_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_POLICY_PATH,
    DEFAULT_REPORT_PATH,
    FounderFieldRound1Config,
    read_json_object,
    run_founder_field_round1,
    string_list,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--field-report-path", default=str(DEFAULT_FIELD_REPORT_PATH))
    parser.add_argument("--field-markdown-output-path", default=str(DEFAULT_FIELD_MARKDOWN_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_PATH))
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def run_existing_founder_field_runner(args: argparse.Namespace, policy: dict[str, object], config_root: Path) -> dict[str, object]:
    field_report_path = Path(args.field_report_path)
    if not field_report_path.is_absolute():
        field_report_path = config_root / field_report_path
    field_markdown_path = Path(args.field_markdown_output_path)
    if not field_markdown_path.is_absolute():
        field_markdown_path = config_root / field_markdown_path
    command = [
        sys.executable,
        str(config_root / "scripts" / "run_founder_field_prompt_eval.py"),
        "--config-root",
        str(config_root),
        "--anythingllm-api-base-url",
        args.anythingllm_api_base_url,
        "--workspace",
        args.workspace,
        "--api-key-env",
        args.api_key_env,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--output-path",
        str(field_report_path),
        "--markdown-output-path",
        str(field_markdown_path),
    ]
    for case_id in string_list(policy.get("required_case_ids")):
        command.extend(["--case-id", case_id])
    env = os.environ.copy()
    result = subprocess.run(
        command,
        cwd=str(config_root),
        capture_output=True,
        text=True,
        timeout=args.timeout_seconds + 120,
        env=env,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "field_report_path": str(field_report_path),
        "field_markdown_path": str(field_markdown_path),
    }


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    policy_path = Path(args.policy_path)
    resolved_policy_path = policy_path if policy_path.is_absolute() else config_root / policy_path
    policy = read_json_object(resolved_policy_path)
    live_run: dict[str, object] | None = None
    if args.run_live:
        live_run = run_existing_founder_field_runner(args, policy, config_root)
        print("PHASE157 FOUNDER FIELD RUN " + json.dumps(live_run, ensure_ascii=True, sort_keys=True))
    report = run_founder_field_round1(
        FounderFieldRound1Config(
            config_root=config_root,
            policy_path=Path(args.policy_path),
            field_report_path=Path(args.field_report_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    if live_run is not None:
        report["live_run"] = live_run
        output_path = Path(args.output_path)
        if not output_path.is_absolute():
            output_path = config_root / output_path
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PHASE157 FOUNDER FIELD ROUND REPORT {report['report_path']}")
    print("PHASE157 FOUNDER FIELD ROUND SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print(
            "PHASE157 FOUNDER FIELD ROUND ERRORS "
            + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("PHASE157 FOUNDER FIELD ROUND PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
