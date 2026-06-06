#!/usr/bin/env python3
"""Validate governed prompt catalog fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.prompt_catalogs import (  # noqa: E402
    DEFAULT_FOUNDER_FIELD_CATALOG,
    PromptCatalogError,
    load_prompt_catalog,
    prompt_cases_from_catalog,
    resolve_catalog_path,
    validate_prompt_catalog,
)


DEFAULT_REPORT_DIR = Path("runtime-state") / "prompt-catalogs"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path, catalog_id: str) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"{catalog_id}-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_report(config_root: Path, catalog_path: Path | None = None) -> dict[str, Any]:
    resolved_path = resolve_catalog_path(config_root, catalog_path)
    try:
        catalog = load_prompt_catalog(config_root, catalog_path)
        problems = validate_prompt_catalog(catalog)
        cases = () if problems else prompt_cases_from_catalog(catalog)
    except PromptCatalogError as exc:
        catalog = {}
        problems = [str(exc)]
        cases = ()
    refined_count = sum(1 for case in cases if case.refined_prompt)
    tag_counts: dict[str, int] = {}
    for case in cases:
        for tag in case.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return {
        "schema_version": 1,
        "kind": "prompt_catalog_validation",
        "status": "passed" if not problems else "failed",
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "catalog_path": str(resolved_path),
        "catalog_id": catalog.get("catalog_id", ""),
        "catalog_version": catalog.get("version", ""),
        "summary": {
            "case_count": len(cases),
            "refined_prompt_count": refined_count,
            "tag_counts": tag_counts,
            "problem_count": len(problems),
        },
        "case_ids": [case.case_id for case in cases],
        "problems": problems,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--catalog-path", default=str(DEFAULT_FOUNDER_FIELD_CATALOG))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    catalog_path = Path(args.catalog_path) if args.catalog_path else None
    report = build_report(config_root, catalog_path)
    output_path = (
        Path(args.output_path)
        if args.output_path
        else default_report_path(config_root, report.get("catalog_id") or "prompt-catalog")
    )
    write_json(output_path, report)
    print(f"PROMPT CATALOG REPORT {output_path.resolve()}")
    print("PROMPT CATALOG SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PROMPT CATALOG FAILURES " + json.dumps(report["problems"], ensure_ascii=True, sort_keys=True))
        return 1
    print("PROMPT CATALOG PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
