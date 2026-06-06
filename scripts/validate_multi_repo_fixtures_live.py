#!/usr/bin/env python3
"""Validate workflow-router behavior across controlled fixture repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.fixtures.manager import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    FixtureEntry,
    fixture_entries,
    load_fixture_manifest,
)


DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "multi-repo-fixtures"


@dataclass(frozen=True)
class FixtureLiveCase:
    case_id: str
    fixture_id: str
    prompt_template: str
    expected_workflow: str
    expected_artifact: str
    expected_route_hint: str


LIVE_CASES = [
    FixtureLiveCase(
        case_id="coinbase-code-explanation",
        fixture_id="coinbase-frozen",
        prompt_template=(
            "In {target_root}, explain what find_stealth_order_by_placed_order_id does "
            "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_code_explanation",
        expected_route_hint="l1_explain_code_terms",
    ),
    FixtureLiveCase(
        case_id="coinbase-git-code-explanation",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, explain what find_stealth_order_by_placed_order_id does "
            "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_code_explanation",
        expected_route_hint="l1_explain_code_terms",
    ),
    FixtureLiveCase(
        case_id="node-cli-configuration-lookup",
        fixture_id="node-cli-generalization",
        prompt_template=(
            "In {target_root}, locate where DEFAULT_PROFILE is defined or used as a configuration setting. "
            "Read only. Include source refs and runtime effect. Return JSON."
        ),
        expected_workflow="code_investigation.plan",
        expected_artifact="downstream_configuration_lookup",
        expected_route_hint="l1_configuration_lookup_terms",
    ),
]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_request(url: str, *, payload: dict[str, Any], timeout_seconds: int) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    for key in ("textResponse", "response", "message", "text"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    raise RuntimeError("response did not include assistant text")


def json_content(body: dict[str, Any]) -> dict[str, Any]:
    text = text_response(body)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("assistant JSON content was not an object")
    return parsed


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(entry: FixtureEntry) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in entry.watched_paths:
        path = entry.source_path / relative_path
        if path.exists() and path.is_file():
            hashes[relative_path] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{entry.fixture_id} did not contain watched files")
    return hashes


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def validate_case(args: argparse.Namespace, entry: FixtureEntry, case: FixtureLiveCase) -> dict[str, Any]:
    before_hashes = watched_hashes(entry)
    before_git_status = git_status(entry.source_path)
    prompt = case.prompt_template.format(target_root=entry.source_path.as_posix())
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "output_format": "json",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"{case.case_id} returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    parsed = json_content(body)
    contract = parsed.get("chat_contract") if isinstance(parsed.get("chat_contract"), dict) else {}
    artifacts = parsed.get("artifacts") if isinstance(parsed.get("artifacts"), dict) else {}
    if parsed.get("workflow") != "workflow_router.plan":
        raise RuntimeError(f"{case.case_id} returned wrong wrapper workflow: {parsed.get('workflow')!r}")
    if contract.get("selected_workflow") != case.expected_workflow:
        raise RuntimeError(f"{case.case_id} selected wrong workflow: {contract.get('selected_workflow')!r}")
    if case.expected_artifact not in artifacts:
        raise RuntimeError(f"{case.case_id} missing expected artifact: {case.expected_artifact}")
    after_hashes = watched_hashes(entry)
    after_git_status = git_status(entry.source_path)
    if before_hashes != after_hashes:
        raise RuntimeError(f"{case.case_id} mutated watched files for {entry.fixture_id}")
    if before_git_status is not None and before_git_status != after_git_status:
        raise RuntimeError(f"{case.case_id} changed git status for {entry.fixture_id}")
    run_id = str(parsed.get("run_id") or "")
    result = {
        "case_id": case.case_id,
        "fixture_id": case.fixture_id,
        "category": entry.category,
        "target_root": entry.source_path.as_posix(),
        "run_id": run_id,
        "status": "passed",
        "selected_workflow": contract.get("selected_workflow"),
        "selected_skills": contract.get("selected_skills"),
        "selected_tools": contract.get("selected_tools"),
        "expected_artifact": case.expected_artifact,
        "artifact_keys": sorted(artifacts),
        "expected_route_hint": case.expected_route_hint,
        "source_unchanged": True,
        "git_status_unchanged": before_git_status == after_git_status,
    }
    print(f"MULTI REPO FIXTURE PASS case={case.case_id} fixture={entry.fixture_id} run_id={run_id}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    manifest = load_fixture_manifest(config_root, Path(args.manifest))
    entries = {entry.fixture_id: entry for entry in fixture_entries(config_root, manifest)}
    output_path = Path(args.output_path) if args.output_path else config_root / DEFAULT_OUTPUT_DIR / f"multi-repo-fixtures-{utc_timestamp()}.json"
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "multi_repo_fixture_live_report",
        "status": "failed",
        "created_at": utc_timestamp(),
        "cases": [],
        "errors": [],
    }
    try:
        for case in LIVE_CASES:
            entry = entries.get(case.fixture_id)
            if entry is None:
                raise RuntimeError(f"missing fixture in manifest: {case.fixture_id}")
            report["cases"].append(validate_case(args, entry, case))
        categories = {case["category"] for case in report["cases"] if isinstance(case, dict)}
        report["summary"] = {
            "case_count": len(report["cases"]),
            "fixture_count": len({case["fixture_id"] for case in report["cases"] if isinstance(case, dict)}),
            "category_count": len(categories),
            "categories": sorted(categories),
            "error_count": 0,
        }
        report["status"] = "passed"
    except Exception as exc:
        report["errors"].append(str(exc))
        report["summary"] = {
            "case_count": len(report["cases"]),
            "error_count": len(report["errors"]),
        }
        write_json(output_path, report)
        print(f"MULTI REPO FIXTURE REPORT {output_path}")
        print("MULTI REPO FIXTURE FAIL " + str(exc))
        return 1
    write_json(output_path, report)
    print(f"MULTI REPO FIXTURE REPORT {output_path}")
    print("MULTI REPO FIXTURE PASS")
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
