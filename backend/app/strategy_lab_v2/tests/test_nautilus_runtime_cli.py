from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.strategy_lab_v2 import nautilus_runtime_cli
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ProductClass
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusCashDefinition,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
    build_nautilus_engine_input,
)
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventRecord, NautilusEventTape
from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    _SOURCE,
    _invocation_batch,
    _manifest,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import build_nautilus_runtime_bundle


def _runtime_bundle():
    first_event = NautilusEventRecord(
        "prices",
        "adapter-event-1",
        "EURUSD.SIM",
        "quote",
        1,
        1,
        {
            "bid": Decimal("1.1000"),
            "ask": Decimal("1.1002"),
            "bid_size": Decimal("100000"),
            "ask_size": Decimal("100000"),
        },
    )
    second_event = NautilusEventRecord(
        "prices",
        "adapter-event-2",
        "EURUSD.SIM",
        "quote",
        2,
        2,
        {
            "bid": Decimal("1.1001"),
            "ask": Decimal("1.1003"),
            "bid_size": Decimal("100000"),
            "ask_size": Decimal("100000"),
        },
    )
    event_tape = NautilusEventTape(content_digest("source-tape"), (first_event, second_event))
    instrument = NautilusInstrumentDefinition(
        "EURUSD.SIM",
        "EURUSD",
        "SIM",
        ProductClass.FX,
        "USD",
        5,
        0,
        Decimal("0.00001"),
        Decimal("1"),
        base_currency="EUR",
        bar_type="EURUSD.SIM-1-MINUTE-MID-INTERNAL",
    )
    venue = NautilusVenueDefinition(
        "SIM",
        "netting",
        "cash",
        (NautilusCashDefinition("USD", Decimal("100000")),),
        "USD",
    )
    manifest = _manifest()
    engine_input = build_nautilus_engine_input(
        trial_id="trial-1",
        attempt_id="attempt-1",
        data_snapshot_fingerprint=content_digest("snapshot"),
        event_tape=event_tape,
        instruments=(instrument,),
        venue=venue,
        strategy_source_digest=content_digest(_SOURCE),
        strategy_manifest_fingerprint=manifest.fingerprint,
        entrypoint="strategy.main:Strategy",
        parameters={"window": 20},
        random_seed=17,
    )
    return build_nautilus_runtime_bundle(engine_input, _invocation_batch())


def test_runtime_bundle_binds_cli_digest_to_the_readonly_wire_bytes() -> None:
    first = _runtime_bundle()
    second = _runtime_bundle()

    assert first == second
    assert first.input_bundle_digest == content_digest(json.loads(first.wire_bytes))
    assert first.input_bundle_digest.startswith("sha256:")
    assert first.attempt_id == "attempt-1"


def test_cli_runs_only_digest_attempt_snapshot_and_version_bound_bundle(
    tmp_path, monkeypatch
) -> None:
    bundle = _runtime_bundle()
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    input_path.write_bytes(bundle.wire_bytes)
    output_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)
    calls = []

    def fake_run(engine_input, *, serialized_strategy_invocation_batch):
        calls.append((engine_input, serialized_strategy_invocation_batch))
        return {"engine_version": "2.0.0rc5", "authoritative": False, "fills": 2}

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=len(bundle.wire_bytes),
        )
        == 0
    )
    assert len(calls) == 1
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == {"engine_version": "2.0.0rc5", "authoritative": False, "fills": 2}


@pytest.mark.parametrize(
    ("environment_attempt", "snapshot", "version", "message"),
    [
        ("attempt-other", content_digest("snapshot"), "2.0.0rc5", "attempt differs"),
        ("attempt-1", content_digest("different snapshot"), "2.0.0rc5", "snapshot differs"),
        ("attempt-1", content_digest("snapshot"), "2.0.0", "package version differs"),
    ],
)
def test_cli_rejects_bundle_identity_drift_before_result_write(
    tmp_path, monkeypatch, environment_attempt, snapshot, version, message
) -> None:
    bundle = _runtime_bundle()
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    input_path.write_bytes(bundle.wire_bytes)
    output_path.write_text("unchanged", encoding="utf-8")
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", environment_attempt)

    with pytest.raises(ValueError, match=message):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version=version,
            expected_snapshot_fingerprint=snapshot,
            max_input_bytes=len(bundle.wire_bytes),
        )
    assert output_path.read_text(encoding="utf-8") == "unchanged"


def test_cli_rejects_duplicate_fields_and_memory_limit_overflow(tmp_path, monkeypatch) -> None:
    bundle = _runtime_bundle()
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    input_path.write_bytes(b'{"schema":"x","schema":"y"}')
    output_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)

    with pytest.raises(ValueError, match="duplicate object fields"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1024,
        )

    input_path.write_bytes(bundle.wire_bytes)
    with pytest.raises(ValueError, match="exceeds its memory-derived limit"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=len(bundle.wire_bytes) - 1,
        )
