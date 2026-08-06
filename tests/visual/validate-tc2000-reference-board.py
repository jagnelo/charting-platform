#!/usr/bin/env python3
"""Validate that a generated TC2000 reference board contains every local media card."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} BOARD_HTML")
    board = Path(sys.argv[1]).expanduser().resolve()
    if not board.is_file():
        raise SystemExit(f"board does not exist: {board}")
    html = board.read_text(encoding="utf-8")
    images = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', html)
    missing: list[str] = []
    for source in images:
        if source.startswith("file://"):
            path = Path(source[7:])
            if not path.is_file():
                missing.append(str(path))
    if missing:
        print(f"missing local board sources: {len(missing)}", file=sys.stderr)
        for path in missing[:20]:
            print(path, file=sys.stderr)
        return 1
    print(f"validated {len(images)} board images from {board}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
