#!/usr/bin/env python3
"""Guard the primary workstation's uPlot-only numerical renderer contract.

Static SVG icons and the chart drawing canvas are intentionally allowed. The
primary workstation must not reintroduce dynamic SVG geometry for numerical
series; excluded legacy options surfaces are outside this contract.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    ROOT / "frontend/src/components/workstation",
    ROOT / "frontend/src/components/strategy",
    ROOT / "frontend/src/components/common/Sparkline.vue",
    ROOT / "frontend/src/components/dashboard/DashboardHeatMapWidget.vue",
)

FORBIDDEN_PATTERNS = (
    (re.compile(r"<polyline\b", re.IGNORECASE), "SVG polyline geometry"),
    (re.compile(r"<polygon\b", re.IGNORECASE), "SVG polygon geometry"),
    (re.compile(r"<path\b[^>]*(?::d|v-bind:d)\s*=", re.IGNORECASE), "bound SVG path geometry"),
    (re.compile(r"<(?:line|path)\b[^>]*(?::(?:x1|x2|y1|y2)|v-bind:(?:x1|x2|y1|y2))\s*=", re.IGNORECASE), "bound SVG line geometry"),
    (re.compile(r"\b(?:pointsToSvg|sparkPoints)\b"), "SVG numerical point helper"),
)


def source_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.vue")))
    return files


def main() -> int:
    violations: list[str] = []
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        for pattern, description in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line}: {description}")

    if violations:
        print("uPlot numerical renderer contract violated:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1

    print(f"uPlot numerical renderer contract valid: {len(source_files())} primary source files audited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
