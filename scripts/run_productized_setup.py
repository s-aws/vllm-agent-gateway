#!/usr/bin/env python3
"""Compatibility entrypoint for productized local harness setup."""

from __future__ import annotations

from manage_productized_setup import main


if __name__ == "__main__":
    raise SystemExit(main())
