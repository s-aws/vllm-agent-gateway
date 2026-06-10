#!/usr/bin/env python3
"""Validate or execute Phase 165 prompt-advisory closure."""

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

from vllm_agent_gateway.acceptance.prompt_advisory_closure import (  # noqa: E402
    DEFAULT_HOLDOUT_FIELD_MARKDOWN_PATH,
    DEFAULT_HOLDOUT_FIELD_REPORT_PATH,
    DEFAULT_MARKDOWN_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_POLICY_PATH,
    DEFAULT_REFINED_FIELD_MARKDOWN_PATH,
    DEFAULT_REFINED_FIELD_REPORT_PATH,
    DEFAULT_REPORT_PATH,
    PromptAdvisoryClosureConfig,
    read_json_object,
    run_prompt_advisory_closure,
    string_list,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--refined-field-report-path", default=str(DEFAULT_REFINED_FIELD_REPORT_PATH))
    parser.add_argument("--refined-field-markdown-output-path", default=str(DEFAULT_REFINED_FIELD_MARKDOWN_PATH))
    parser.add_argument("--holdout-field-report-path", default=str(DEFAULT_HOLDOUT_FIELD_REPORT_PATH))
    parser.add_argument("--holdout-field-markdown-output-path", default=str(DEFAULT_HOLDOUT_FIELD_MARKDOWN_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_PATH))
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--anythingllm-api-base-url", default="http://127.0.0.1:3001")
    parser.add_argument("--workspace", default="my-workspace")
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def run_field_runner(
    *,
    args: argparse.Namespace,
    config_root: Path,
    case_ids: list[str],
    output_path: Path,
    markdown_output_path: Path,
    use_refined: bool,
) -> dict[str, object]:
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
        str(output_path),
        "--markdown-output-path",
        str(markdown_output_path),
    ]
    if use_refined:
        command.append("--use-refined-prompts")
    for case_id in case_ids:
        command.extend(["--case-id", case_id])
    result = subprocess.run(
        command,
        cwd=str(config_root),
        capture_output=True,
        text=True,
        timeout=args.timeout_seconds + 120,
        env=os.environ.copy(),
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "output_path": str(output_path),
        "markdown_output_path": str(markdown_output_path),
        "use_refined_prompts": use_refined,
    }


def resolved(config_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    policy_path = resolved(config_root, args.policy_path)
    policy = read_json_object(policy_path)
    live_runs: dict[str, object] | None = None
    if args.run_live:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        refined_path = resolved(config_root, args.refined_field_report_path)
        refined_markdown = resolved(config_root, args.refined_field_markdown_output_path)
        holdout_path = resolved(config_root, args.holdout_field_report_path)
        holdout_markdown = resolved(config_root, args.holdout_field_markdown_output_path)
        refined_run = run_field_runner(
            args=args,
            config_root=config_root,
            case_ids=string_list(policy.get("required_advisory_case_ids")),
            output_path=refined_path,
            markdown_output_path=refined_markdown,
            use_refined=True,
        )
        holdout_run = run_field_runner(
            args=args,
            config_root=config_root,
            case_ids=string_list(policy.get("holdout_case_ids")),
            output_path=holdout_path,
            markdown_output_path=holdout_markdown,
            use_refined=False,
        )
        live_runs = {"refined": refined_run, "holdout": holdout_run}
        print("PHASE165 PROMPT ADVISORY CLOSURE RUN " + json.dumps(live_runs, ensure_ascii=True, sort_keys=True))
    report = run_prompt_advisory_closure(
        PromptAdvisoryClosureConfig(
            config_root=config_root,
            policy_path=Path(args.policy_path),
            refined_field_report_path=Path(args.refined_field_report_path),
            holdout_field_report_path=Path(args.holdout_field_report_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    if live_runs is not None:
        report["live_runs"] = live_runs
        write_json(resolved(config_root, args.output_path), report)
    print(f"PHASE165 PROMPT ADVISORY CLOSURE REPORT {report['report_path']}")
    print("PHASE165 PROMPT ADVISORY CLOSURE SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE165 PROMPT ADVISORY CLOSURE ERRORS " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE165 PROMPT ADVISORY CLOSURE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
