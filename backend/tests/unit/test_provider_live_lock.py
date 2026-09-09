from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "provider_live_lock.py"
_SPEC = importlib.util.spec_from_file_location("provider_live_lock", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
ProviderLiveRunAlreadyActive = _MODULE.ProviderLiveRunAlreadyActive
provider_live_run_lock = _MODULE.provider_live_run_lock


def test_provider_live_lock_writes_non_secret_metadata_and_clears_on_release(tmp_path: Path):
    lock_path = tmp_path / "provider-live.lock"

    with provider_live_run_lock(lock_path):
        metadata = lock_path.read_text()
        assert '"pid"' in metadata
        assert '"started_at"' in metadata
        assert "secret" not in metadata.lower()

    assert lock_path.read_text() == ""


def test_provider_live_lock_rejects_second_owner(tmp_path: Path):
    lock_path = tmp_path / "provider-live.lock"

    with provider_live_run_lock(lock_path):
        original_metadata = lock_path.read_text()
        with pytest.raises(ProviderLiveRunAlreadyActive):
            with provider_live_run_lock(lock_path):
                pass
        assert lock_path.read_text() == original_metadata
