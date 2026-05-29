#!/usr/bin/env python3
"""Run explicit documenter controller-service examples."""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_CONTROLLER_URL = "http://127.0.0.1:8400"
DOCUMENT_REVIEW_PATH = "/v1/controller/documenter/reviews"
HARNESS_PATH = "/v1/controller/harness/chat/completions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a documenter controller-service example request.")
    parser.add_argument("--controller-url", default=DEFAULT_CONTROLLER_URL)
    parser.add_argument("--target-root", default=".", help="Repository to review.")
    parser.add_argument(
        "--case",
        choices=["seed", "tracked", "all", "harness"],
        default="seed",
        help="Example request shape to send.",
    )
    parser.add_argument(
        "--seed-doc",
        "--seed",
        "--doc",
        dest="seed_doc",
        default=None,
        help="Seed document. Defaults to README.md for seed/harness examples.",
    )
    parser.add_argument("--live", action="store_true", help="Call the documenter role endpoint instead of dry-run mode.")
    parser.add_argument("--async-run", action="store_true", help="Create an async controller run and poll it.")
    parser.add_argument("--max-chunks", type=int, default=1, help="Bounded demo max_chunks budget.")
    parser.add_argument("--parallelism", type=int, default=1, help="Bounded concurrent chunk review budget.")
    parser.add_argument("--chunk-token-limit", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    parser.add_argument("--poll-timeout", type=float, default=60.0, help="Async polling timeout in seconds.")
    parser.add_argument("--output", default=None, help="Optional file path for the JSON response.")
    parser.add_argument("--print-request", action="store_true", help="Print the request JSON before sending it.")
    return parser.parse_args()


def request_path(path: str, query: str) -> str:
    return f"{path}?{query}" if query else path


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    url = urlsplit(base_url)
    if url.scheme not in {"http", ""}:
        raise ValueError("Only http controller URLs are supported.")
    host = url.hostname or "127.0.0.1"
    port = url.port or 80
    base_path = request_path(url.path.rstrip("/") + path, url.query)
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    connection.request("POST", base_path, body=body, headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    connection.close()
    return response.status, json.loads(data)


def get_json(base_url: str, path: str, timeout: float) -> tuple[int, dict[str, Any]]:
    url = urlsplit(base_url)
    if url.scheme not in {"http", ""}:
        raise ValueError("Only http controller URLs are supported.")
    host = url.hostname or "127.0.0.1"
    port = url.port or 80
    base_path = request_path(url.path.rstrip("/") + path, url.query)
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    connection.request("GET", base_path)
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    connection.close()
    return response.status, json.loads(data)


def documenter_request(args: argparse.Namespace) -> dict[str, Any]:
    target_root = str(Path(args.target_root).resolve())
    request: dict[str, Any] = {
        "workflow": "documenter.review",
        "target_root": target_root,
        "mode": "full",
        "chunk_token_limit": args.chunk_token_limit,
        "budgets": {"max_chunks": args.max_chunks, "parallelism": args.parallelism},
    }
    if not args.live:
        request["dry_run"] = True
    if args.async_run:
        request["async"] = True
    if args.case in {"seed", "harness"}:
        request.update({"seed_doc": args.seed_doc or "README.md", "document_scope": "tracked", "review_scope": "seed"})
    elif args.case == "tracked":
        request.update({"document_scope": "tracked", "review_scope": "manifest"})
        if args.seed_doc:
            request["seed_doc"] = args.seed_doc
    elif args.case == "all":
        request.update({"document_scope": "all", "review_scope": "manifest"})
        if args.seed_doc:
            request["seed_doc"] = args.seed_doc
    return request


def harness_request(controller_request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "agentic-controller",
        "agentic_controller_request": controller_request,
    }


def poll_run(base_url: str, run_id: str, timeout: float) -> tuple[int, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_status = 0
    last_body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, body = get_json(base_url, f"/v1/controller/runs/{run_id}", timeout=min(10.0, timeout))
        last_status = status
        last_body = body
        if status == 200 and body.get("status") in {"completed", "failed", "canceled", "paused"}:
            return status, body
        time.sleep(0.25)
    return last_status, last_body


def write_optional_output(path: str | None, response: dict[str, Any]) -> None:
    if path is None:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(response, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    controller_request = documenter_request(args)
    path = DOCUMENT_REVIEW_PATH
    payload = controller_request
    if args.case == "harness":
        path = HARNESS_PATH
        payload = harness_request(controller_request)
    if args.print_request:
        print(json.dumps(payload, ensure_ascii=True, indent=2))

    status, response = post_json(args.controller_url, path, payload, args.timeout)
    if args.async_run and status == 202 and isinstance(response.get("run_id"), str):
        status, response = poll_run(args.controller_url, response["run_id"], args.poll_timeout)

    write_optional_output(args.output, response)
    print(json.dumps(response, ensure_ascii=True, indent=2))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
