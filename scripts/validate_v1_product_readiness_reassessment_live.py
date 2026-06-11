#!/usr/bin/env python3
"""Build the Phase 196 live-runtime proof required by the reassessment gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase196" / "phase196-v1-product-readiness-live-proof.json"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_MODEL_ID = "Qwen3-Coder-30B-A3B-Instruct"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
RUN_ID_RE = re.compile(r"run_id=(workflow-router-\S+)")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def read_models(base_url: str, timeout_seconds: int) -> list[str]:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/models", timeout=timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))
    values = body.get("data")
    if not isinstance(values, list):
        return []
    return [str(item.get("id")) for item in values if isinstance(item, dict) and item.get("id")]


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_fingerprint(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest(path).encode("ascii"))
        digest.update(b"\0")
        file_count += 1
    return {"mode": "hash", "file_count": file_count, "sha256": digest.hexdigest()}


def fixture_fingerprint(root_value: str) -> dict[str, Any]:
    root = Path(root_value)
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", root_value, "status", "--short"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return {
            "mode": "git_status",
            "exit_code": result.returncode,
            "status": result.stdout,
            "stderr": result.stderr,
        }
    return directory_fingerprint(root)


def command_record(command: list[str], timeout_seconds: int) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def run_ids_from_stdout(record: dict[str, Any], marker: str) -> list[str]:
    stdout = str(record.get("stdout_tail") or "")
    return [match.group(1) for line in stdout.splitlines() if marker in line for match in [RUN_ID_RE.search(line)] if match]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    errors: list[dict[str, str]] = []
    before = {root: fixture_fingerprint(root) for root in target_roots}
    model_ids = read_models(args.model_base_url, args.timeout_seconds)
    if DEFAULT_MODEL_ID not in model_ids:
        errors.append({"id": "model_id.missing", "message": f"{DEFAULT_MODEL_ID} not found in {args.model_base_url}/models"})
    if not os.environ.get(args.api_key_env):
        errors.append({"id": "anythingllm.api_key_missing", "message": f"{args.api_key_env} is required"})

    commands = [
        command_record([sys.executable, "scripts/run_first_time_user_doctor.py"], args.timeout_seconds),
        command_record([sys.executable, "scripts/validate_post_restart_runtime_readiness.py"], args.timeout_seconds),
        command_record(
            [
                sys.executable,
                "scripts/validate_release_candidate_founder_trial_pack.py",
                "--require-proof-artifacts",
                "--validate-fixture-state",
            ],
            args.timeout_seconds,
        ),
        command_record(
            [
                sys.executable,
                "scripts/validate_workflow_router_chat_contract_live.py",
                "--workflow-router-gateway-base-url",
                args.workflow_router_gateway_base_url,
                "--anythingllm-api-base-url",
                args.anythingllm_api_base_url,
                "--workspace",
                args.workspace,
                "--api-key-env",
                args.api_key_env,
                *[value for root in target_roots for value in ("--target-root", root)],
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            args.timeout_seconds * 2,
        ),
    ]
    for record in commands:
        if record["returncode"] != 0:
            errors.append({"id": "command.failed", "message": " ".join(record["command"])})

    after = {root: fixture_fingerprint(root) for root in target_roots}
    fixture_errors: list[str] = []
    for root in target_roots:
        if before[root] != after[root]:
            fixture_errors.append(root)
    if fixture_errors:
        errors.append({"id": "fixture_integrity.changed", "message": ", ".join(fixture_errors)})

    chat_contract = commands[-1]
    gateway_run_ids = run_ids_from_stdout(chat_contract, "CHAT CONTRACT JSON GATEWAY PASS")
    anythingllm_run_ids = run_ids_from_stdout(chat_contract, "CHAT CONTRACT JSON ANYTHINGLLM PASS")
    if len(gateway_run_ids) < len(target_roots):
        errors.append({"id": "gateway_run_ids.missing", "message": "missing gateway run IDs"})
    if len(anythingllm_run_ids) < len(target_roots):
        errors.append({"id": "anythingllm_run_ids.missing", "message": "missing AnythingLLM run IDs"})

    report = {
        "schema_version": 1,
        "kind": "v1_product_readiness_reassessment_live_proof",
        "phase": 196,
        "priority_backlog_id": "P0-BB-060",
        "status": "failed" if errors else "passed",
        "created_at": utc_timestamp(),
        "model_id": DEFAULT_MODEL_ID,
        "model_ids": model_ids,
        "gateway_url": args.workflow_router_gateway_base_url,
        "anythingllm_target_url": args.workflow_router_gateway_base_url,
        "anythingllm_api_url": args.anythingllm_api_base_url,
        "workspace": args.workspace,
        "target_roots": target_roots,
        "run_ids": {
            "gateway": gateway_run_ids,
            "anythingllm": anythingllm_run_ids,
        },
        "output_markers": [
            "json",
            "chat_contract",
            "selected_workflow",
            "workflow-router-",
        ],
        "fixture_integrity": {
            "status": "failed" if fixture_errors else "passed",
            "before": before,
            "after": after,
        },
        "commands": commands,
        "errors": errors,
        "summary": {
            "command_count": len(commands),
            "gateway_run_id_count": len(gateway_run_ids),
            "anythingllm_run_id_count": len(anythingllm_run_ids),
            "target_root_count": len(target_roots),
            "error_count": len(errors),
        },
    }
    output_path = REPO_ROOT / args.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PHASE196 V1 PRODUCT READINESS LIVE PROOF REPORT {output_path.resolve()}")
    print("PHASE196 V1 PRODUCT READINESS LIVE PROOF SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if errors:
        print("PHASE196 V1 PRODUCT READINESS LIVE PROOF FAIL " + json.dumps(errors, ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE196 V1 PRODUCT READINESS LIVE PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
