#!/usr/bin/env python3
"""Validate the Phase 110 semi-well-defined prompt generalization suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.semi_well_defined_prompts import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CATALOG_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    LiveClient,
    SemiWellDefinedConfig,
    validate_semi_well_defined_prompts,
)


def parse_clients(values: list[str] | None) -> tuple[LiveClient, ...]:
    if not values:
        return (LiveClient.GATEWAY, LiveClient.ANYTHINGLLM)
    clients: list[LiveClient] = []
    for value in values:
        normalized = value.strip().lower()
        try:
            clients.append(LiveClient(normalized))
        except ValueError as exc:
            raise SystemExit(f"Unsupported client {value!r}; use gateway or anythingllm") from exc
    return tuple(dict.fromkeys(clients))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--policy-path", default="runtime/recursive_blind_testing_policy.json")
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--client", action="append", choices=[client.value for client in LiveClient])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--markdown-output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_semi_well_defined_prompts(
        SemiWellDefinedConfig(
            config_root=Path(args.config_root),
            catalog_path=Path(args.catalog_path),
            manifest_path=Path(args.manifest_path),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path) if args.output_path else None,
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            workflow_router_gateway_base_url=args.workflow_router_gateway_base_url,
            anythingllm_api_base_url=args.anythingllm_api_base_url,
            workspace=args.workspace,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            case_ids=tuple(args.case_ids or ()),
            clients=parse_clients(args.client),
            live=args.live,
        )
    )
    print(f"SEMI WELL DEFINED PROMPT REPORT {Path(args.output_path).resolve() if args.output_path else 'see runtime-state'}")
    print("SEMI WELL DEFINED PROMPT SUMMARY " + json.dumps(report.get("summary", {}), ensure_ascii=True, sort_keys=True))
    if report.get("status") != "passed":
        print("SEMI WELL DEFINED PROMPT FAILURES " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("SEMI WELL DEFINED PROMPT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
