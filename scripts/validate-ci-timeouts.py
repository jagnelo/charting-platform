#!/usr/bin/env python3
"""Validate the CI timeout contract for the timeout-hardening workstream."""

from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    for timeout in (30, 15, 45, 180):
        assert f"timeout-minutes: {timeout}" in text
    assert text.count("timeout-minutes:") == 5  # includes the existing 5m stack-start bound
    assert "run: make validate-integration" in text
    print("CI timeout and exhaustive-command contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
