"""Runtime-local Nautilus v2 compatibility probe.

This module is copied into the isolated Nautilus runtime and executed there.
It deliberately imports Nautilus only inside the probe function, after checking
the installed distribution version, so the backend's legacy v1 environment can
never accidentally satisfy an RC probe.  The probe performs only package,
BacktestEngine construction, and disposal checks; it does not acquire data or
publish a result.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from collections.abc import Mapping
from typing import Any

from app.strategy_lab_v2.conformance import NAUTILUS_V2_RC_PACKAGE_VERSION


def probe_nautilus_runtime(
    *, expected_version: str = NAUTILUS_V2_RC_PACKAGE_VERSION
) -> Mapping[str, Any]:
    """Verify one isolated runtime and exercise its engine lifecycle."""

    if not isinstance(expected_version, str) or not expected_version.strip():
        raise ValueError("expected_version must not be empty")
    try:
        installed_version = importlib.metadata.version("nautilus-trader")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError("nautilus-trader distribution is not installed") from error
    if installed_version != expected_version:
        raise RuntimeError(
            "nautilus-trader version mismatch: "
            f"expected {expected_version}, got {installed_version}"
        )

    try:
        from nautilus_trader import __version__
        from nautilus_trader.backtest import (  # type: ignore[attr-defined]
            BacktestEngine,
            BacktestEngineConfig,
        )
        from nautilus_trader.common import LoggerConfig  # type: ignore[attr-defined]
    except ImportError as error:
        raise RuntimeError("Nautilus v2 backtest bindings are unavailable") from error
    if __version__ != expected_version:
        raise RuntimeError(
            f"Nautilus module version mismatch: expected {expected_version}, got {__version__}"
        )

    engine = None
    try:
        engine = BacktestEngine(
            BacktestEngineConfig(
                logging=LoggerConfig(bypass_logging=True),
                bypass_logging=True,
            )
        )
    finally:
        if engine is not None:
            engine.dispose()
    return {
        "engine_lifecycle": "passed",
        "nautilus_package_version": installed_version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "implementation": sys.implementation.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", default=NAUTILUS_V2_RC_PACKAGE_VERSION)
    args = parser.parse_args()
    result = probe_nautilus_runtime(expected_version=args.expected_version)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - runtime image entrypoint
    raise SystemExit(main())


__all__ = ["main", "probe_nautilus_runtime"]
