#!/usr/bin/env python3
"""Validate Phase 119 delivery-mentorship prompt cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.task_decomposition_quality import (  # noqa: E402
    DEFAULT_PHASE119_CASE_CATALOG,
    load_json_object,
    validate_phase119_case_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--catalog-path", default=str(DEFAULT_PHASE119_CASE_CATALOG))
    parser.add_argument("--output-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    catalog_path = Path(args.catalog_path)
    if not catalog_path.is_absolute():
        catalog_path = config_root / catalog_path
    report = validate_phase119_case_catalog(load_json_object(catalog_path))
    report["catalog_path"] = str(catalog_path)
    if args.output_path:
        output_path = Path(args.output_path)
        if not output_path.is_absolute():
            output_path = config_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PHASE119 DELIVERY MENTORSHIP CASES " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
