from __future__ import annotations

import importlib.metadata

import pytest

from app.strategy_lab_v2.nautilus_runtime_probe import probe_nautilus_runtime


def test_probe_rejects_missing_or_legacy_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "version",
        lambda _name: "1.226.0",
    )
    with pytest.raises(RuntimeError, match="version mismatch"):
        probe_nautilus_runtime()


def test_probe_rejects_empty_expected_version() -> None:
    with pytest.raises(ValueError, match="expected_version"):
        probe_nautilus_runtime(expected_version="")
