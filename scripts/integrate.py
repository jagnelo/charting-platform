#!/usr/bin/env python3
"""Compatibility entry point for the persistent staging integration workflow."""

from __future__ import annotations

import argparse

import staging


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("branch")
    parser.add_argument("--publish", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--remediate-degraded", action="store_true")
    args = parser.parse_args()
    staging.integrate([args.branch], remediate=args.remediate_degraded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
