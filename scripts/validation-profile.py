#!/usr/bin/env python3
"""Print the minimum local validation profile for changed paths."""

from __future__ import annotations

import argparse
import json

from validation_profile import classify_paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    print(
        json.dumps(
            {"profile": classify_paths(args.paths), "paths": args.paths}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
