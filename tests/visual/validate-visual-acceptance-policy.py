#!/usr/bin/env python3
"""Guard the deterministic visual acceptance policy.

The Playwright visual suite is intentionally explicit at every screenshot call
so a future test cannot silently inherit a looser default.  The manifest is the
single source for the numeric policy; this guard checks that the source tests
continue to apply it and that every gap state retains a local interim oracle.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests/visual/references/tc2000-v25/manifest.yaml"
VISUAL_SPEC = ROOT / "frontend/tests/e2e/tc2000_visual.spec.ts"
EXPECTED_RATIO = 0.005
EXPECTED_GEOMETRY_PX = 1
EXPECTED_DELTA_E2000 = 2


def _screenshot_blocks(source: str) -> list[str]:
    """Return balanced-ish assertion blocks without requiring a TS parser."""

    starts = [match.start() for match in re.finditer(r"toHaveScreenshot\s*\(", source)]
    blocks: list[str] = []
    for start in starts:
        depth = 0
        in_string: str | None = None
        escaped = False
        end = None
        for index in range(start, len(source)):
            char = source[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = None
                continue
            if char in {"'", '"', "`"}:
                in_string = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise ValueError("unterminated toHaveScreenshot assertion")
        blocks.append(source[start:end])
    return blocks


def main() -> int:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    policy = (manifest.get("reference_policy") or {}).get("visual_thresholds") or {}
    errors: list[str] = []

    expected_policy = {
        "max_diff_pixel_ratio": EXPECTED_RATIO,
        "geometry_tolerance_css_px": EXPECTED_GEOMETRY_PX,
        "solid_color_delta_e2000": EXPECTED_DELTA_E2000,
    }
    for key, expected in expected_policy.items():
        actual = policy.get(key)
        if actual != expected:
            errors.append(f"manifest visual_thresholds.{key}={actual!r}, expected {expected!r}")

    source = VISUAL_SPEC.read_text(encoding="utf-8")
    try:
        blocks = _screenshot_blocks(source)
    except ValueError as exc:
        errors.append(str(exc))
        blocks = []
    if not blocks:
        errors.append("visual spec contains no toHaveScreenshot assertions")

    expected_ratio_text = f"maxDiffPixelRatio: {EXPECTED_RATIO}"
    for number, block in enumerate(blocks, start=1):
        if expected_ratio_text not in block:
            errors.append(f"screenshot assertion {number} does not enforce {expected_ratio_text}")
        for required in ("animations: 'disabled'", "caret: 'hide'", "scale: 'css'"):
            if required not in block:
                errors.append(f"screenshot assertion {number} is missing {required}")

    for surface in manifest.get("surfaces", []):
        for entry in surface.get("state_entries", []):
            if entry.get("state") != "required_missing":
                continue
            if not str(entry.get("interim_oracle") or "").strip():
                errors.append(f"{surface.get('id')}/{entry.get('id')} has no interim oracle")
            baselines = entry.get("local_baselines")
            if not isinstance(baselines, list) or len(baselines) < 4:
                errors.append(f"{surface.get('id')}/{entry.get('id')} has fewer than four local baselines")

    if errors:
        print("visual acceptance policy violations:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1

    print(f"visual acceptance policy valid: {len(blocks)} screenshot assertions; thresholds 0.5% / 1px / ΔE2000 2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
