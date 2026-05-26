#!/usr/bin/env python3
"""Run the documenter orchestrator CLI."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_CONFIG_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_CONFIG_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_CONFIG_ROOT))

from vllm_agent_gateway.documenter.orchestrator import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
