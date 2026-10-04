from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.strategy_lab_v2 import nautilus_runtime_cli
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    FX_BASE_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    SharedRiskPolicy,
)
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
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    build_nautilus_runtime_bundle,
    materialize_nautilus_component_context_stream_artifact,
    materialize_nautilus_context_stream_artifact,
    materialize_nautilus_native_event_stream_artifact,
)
from strategy_runtime import InvocationContextStreamSource, deserialize_invocation_batch


def _runtime_bundle(
    *,
    context_stream_store: LocalArtifactStore | None = None,
    native_event_stream_store: LocalArtifactStore | None = None,
    component_context_stream: bool = False,
):
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
        portfolio=PortfolioComposition(
            portfolio_id="portfolio-1",
            version_id="portfolio-v1",
            initial_capital=Decimal("100000"),
            base_currency="USD",
            components=(
                PortfolioComponent(
                    component_id="component-1",
                    strategy_fingerprint=manifest.strategy.fingerprint,
                    instrument_ids=(instrument.instrument_id,),
                    capital_weight=Decimal("1"),
                ),
            ),
            shared_risk_policy=SharedRiskPolicy(risk_models=(FX_BASE_NOTIONAL_RISK_MODEL,)),
        ),
        strategy_source_digest=content_digest(_SOURCE),
        strategy_manifest_fingerprint=manifest.fingerprint,
        entrypoint="strategy.main:Strategy",
        parameters={"window": 20},
        random_seed=17,
    )
    invocation_batch = _invocation_batch()
    if context_stream_store is None:
        return build_nautilus_runtime_bundle(engine_input, invocation_batch)
    source, manifest, contexts, entrypoint, max_intents = deserialize_invocation_batch(
        invocation_batch
    )
    if component_context_stream:
        context_stream = materialize_nautilus_component_context_stream_artifact(
            context_stream_store,
            components=(
                InvocationContextStreamSource(
                    "component-1",
                    source,
                    manifest,
                    contexts,
                    entrypoint,
                    max_intents,
                ),
            ),
        )
    else:
        context_stream = materialize_nautilus_context_stream_artifact(
            context_stream_store,
            source=source,
            manifest=manifest,
            contexts=contexts,
            entrypoint=entrypoint,
            max_intents_per_event=max_intents,
        )
    native_event_stream = None
    if native_event_stream_store is not None:
        native_event_stream = materialize_nautilus_native_event_stream_artifact(
            native_event_stream_store,
            events=event_tape.events,
            source_tape_fingerprint=event_tape.source_tape_fingerprint,
            adapter_version=event_tape.adapter_version,
            event_count=len(event_tape.events),
        )
    return build_nautilus_runtime_bundle(
        engine_input,
        context_stream=context_stream,
        native_event_stream=native_event_stream,
    )


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


def test_cli_verifies_and_streams_context_sidecar_before_native_run(tmp_path, monkeypatch) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = _runtime_bundle(context_stream_store=store)
    assert bundle.context_stream is not None
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    result_stream_path = tmp_path / "invocations.ndjson"
    equity_trace_path = tmp_path / "account-equity.parquet"
    report_path = tmp_path / "native-reports.parquet"
    input_path.write_bytes(bundle.wire_bytes)
    output_path.touch()
    result_stream_path.touch()
    equity_trace_path.touch()
    report_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)
    monkeypatch.setenv(
        "STRATEGY_CONTEXT_STREAM_DIGEST", bundle.context_stream.artifact.content_digest
    )
    calls = []

    def fake_run(
        engine_input,
        *,
        invocation_context_stream,
        expected_context_count,
        invocation_result_stream,
        max_invocation_result_bytes,
        account_equity_trace_path,
        max_account_equity_trace_bytes,
        native_reports_path,
        max_native_reports_bytes,
    ):
        invocation_result_stream.write(b"bounded-result-stream")
        assert account_equity_trace_path == str(equity_trace_path)
        assert max_account_equity_trace_bytes == 1024
        assert native_reports_path == str(report_path)
        assert max_native_reports_bytes == 1024
        calls.append(
            (
                engine_input,
                invocation_context_stream.read(),
                expected_context_count,
                max_invocation_result_bytes,
            )
        )
        return {
            "engine_version": "2.0.0rc5",
            "authoritative": False,
            "strategy_invocation_result_stream": {"content_digest": "placeholder"},
        }

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1_000_000,
            context_stream_path=str(store.path_for(bundle.context_stream.artifact.storage_key)),
            invocation_result_stream_path=str(result_stream_path),
            max_result_bytes=1024,
            account_equity_trace_path=str(equity_trace_path),
            max_account_equity_trace_bytes=1024,
            native_reports_path=str(report_path),
            max_native_reports_bytes=1024,
        )
        == 0
    )
    assert len(calls) == 1
    assert calls[0][1] == store.read(bundle.context_stream.artifact.storage_key)
    assert calls[0][2] == bundle.context_stream.context_count
    assert calls[0][3] == 1024
    assert result_stream_path.read_bytes() == b"bounded-result-stream"


def test_cli_verifies_and_streams_native_event_sidecar_to_the_adapter(
    tmp_path,
    monkeypatch,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = _runtime_bundle(
        context_stream_store=store,
        native_event_stream_store=store,
    )
    assert bundle.context_stream is not None
    assert bundle.native_event_stream is not None
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    result_stream_path = tmp_path / "invocations.ndjson"
    equity_trace_path = tmp_path / "account-equity.parquet"
    input_path.write_bytes(bundle.wire_bytes)
    output_path.touch()
    result_stream_path.touch()
    equity_trace_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)
    monkeypatch.setenv(
        "STRATEGY_CONTEXT_STREAM_DIGEST", bundle.context_stream.artifact.content_digest
    )
    monkeypatch.setenv(
        "STRATEGY_NATIVE_EVENT_STREAM_DIGEST",
        bundle.native_event_stream.artifact.content_digest,
    )
    calls = []

    def fake_run(
        engine_input,
        *,
        invocation_context_stream,
        native_event_stream,
        native_event_stream_digest,
        expected_context_count,
        invocation_result_stream,
        max_invocation_result_bytes,
        account_equity_trace_path,
        max_account_equity_trace_bytes,
    ):
        invocation_result_stream.write(b"bounded-result-stream")
        calls.append(
            (
                engine_input,
                invocation_context_stream.read(),
                native_event_stream.read(),
                native_event_stream_digest,
                expected_context_count,
                max_invocation_result_bytes,
            )
        )
        return {
            "engine_version": "2.0.0rc5",
            "authoritative": False,
            "strategy_invocation_result_stream": {"content_digest": "placeholder"},
        }

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1_000_000,
            context_stream_path=str(store.path_for(bundle.context_stream.artifact.storage_key)),
            native_event_stream_path=str(
                store.path_for(bundle.native_event_stream.artifact.storage_key)
            ),
            invocation_result_stream_path=str(result_stream_path),
            max_result_bytes=1024,
            account_equity_trace_path=str(equity_trace_path),
            max_account_equity_trace_bytes=1024,
        )
        == 0
    )
    assert len(calls) == 1
    tape = calls[0][0]["event_tape"]
    assert set(tape) == {"source_tape_fingerprint", "adapter_version", "event_count"}
    assert tape["event_count"] == bundle.native_event_stream.event_count
    assert calls[0][1] == store.read(bundle.context_stream.artifact.storage_key)
    assert calls[0][2] == store.read(bundle.native_event_stream.artifact.storage_key)
    assert calls[0][3] == bundle.native_event_stream.artifact.content_digest
    assert result_stream_path.read_bytes() == b"bounded-result-stream"


def test_cli_rejects_native_event_sidecar_digest_drift_before_result_write(
    tmp_path,
    monkeypatch,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = _runtime_bundle(
        context_stream_store=store,
        native_event_stream_store=store,
    )
    assert bundle.native_event_stream is not None
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    event_path = tmp_path / "native-events.ndjson"
    result_stream_path = tmp_path / "invocations.ndjson"
    equity_trace_path = tmp_path / "account-equity.parquet"
    input_path.write_bytes(bundle.wire_bytes)
    event_path.write_bytes(b"drifted")
    output_path.write_text("unchanged", encoding="utf-8")
    result_stream_path.touch()
    equity_trace_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)
    monkeypatch.setenv(
        "STRATEGY_CONTEXT_STREAM_DIGEST", bundle.context_stream.artifact.content_digest
    )
    monkeypatch.setenv(
        "STRATEGY_NATIVE_EVENT_STREAM_DIGEST",
        bundle.native_event_stream.artifact.content_digest,
    )
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")

    with pytest.raises(ValueError, match="byte length differs"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1_000_000,
            context_stream_path=str(store.path_for(bundle.context_stream.artifact.storage_key)),
            native_event_stream_path=str(event_path),
            invocation_result_stream_path=str(result_stream_path),
            max_result_bytes=1024,
            account_equity_trace_path=str(equity_trace_path),
            max_account_equity_trace_bytes=1024,
        )
    assert output_path.read_text(encoding="utf-8") == "unchanged"


def test_cli_rejects_context_sidecar_digest_drift_before_result_write(
    tmp_path, monkeypatch
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = _runtime_bundle(context_stream_store=store)
    assert bundle.context_stream is not None
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    result_stream_path = tmp_path / "invocations.ndjson"
    context_path = tmp_path / "contexts.ndjson"
    equity_trace_path = tmp_path / "account-equity.parquet"
    input_path.write_bytes(bundle.wire_bytes)
    context_path.write_bytes(b"drifted")
    output_path.write_text("unchanged", encoding="utf-8")
    result_stream_path.touch()
    equity_trace_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)
    monkeypatch.setenv(
        "STRATEGY_CONTEXT_STREAM_DIGEST", bundle.context_stream.artifact.content_digest
    )
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")

    with pytest.raises(ValueError, match="byte length differs"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1_000_000,
            context_stream_path=str(context_path),
            invocation_result_stream_path=str(result_stream_path),
            max_result_bytes=1024,
            account_equity_trace_path=str(equity_trace_path),
            max_account_equity_trace_bytes=1024,
        )
    assert output_path.read_text(encoding="utf-8") == "unchanged"


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


def test_cli_streams_component_context_reference_with_counts_to_adapter(
    tmp_path, monkeypatch
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = _runtime_bundle(
        context_stream_store=store,
        native_event_stream_store=store,
        component_context_stream=True,
    )
    assert bundle.context_stream is not None
    assert bundle.context_stream.component_counts
    assert bundle.native_event_stream is not None
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    result_stream_path = tmp_path / "invocations.ndjson"
    equity_trace_path = tmp_path / "account-equity.parquet"
    input_path.write_bytes(bundle.wire_bytes)
    output_path.touch()
    result_stream_path.touch()
    equity_trace_path.touch()
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle.input_bundle_digest)
    monkeypatch.setenv("STRATEGY_ATTEMPT_ID", bundle.attempt_id)
    monkeypatch.setenv(
        "STRATEGY_CONTEXT_STREAM_DIGEST", bundle.context_stream.artifact.content_digest
    )
    monkeypatch.setenv(
        "STRATEGY_NATIVE_EVENT_STREAM_DIGEST",
        bundle.native_event_stream.artifact.content_digest,
    )
    calls = []

    def fake_run(
        engine_input,
        *,
        invocation_context_stream,
        native_event_stream,
        native_event_stream_digest,
        expected_context_count,
        expected_component_context_counts,
        invocation_result_stream,
        max_invocation_result_bytes,
        account_equity_trace_path,
        max_account_equity_trace_bytes,
    ):
        invocation_result_stream.write(b"component-results")
        calls.append(
            (
                engine_input,
                invocation_context_stream.read(),
                native_event_stream_digest,
                expected_context_count,
                expected_component_context_counts,
                max_invocation_result_bytes,
            )
        )
        return {"engine_version": "2.0.0rc5", "authoritative": False}

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")

    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc5",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1_000_000,
            context_stream_path=str(store.path_for(bundle.context_stream.artifact.storage_key)),
            native_event_stream_path=str(
                store.path_for(bundle.native_event_stream.artifact.storage_key)
            ),
            invocation_result_stream_path=str(result_stream_path),
            max_result_bytes=1024,
            account_equity_trace_path=str(equity_trace_path),
            max_account_equity_trace_bytes=1024,
        )
        == 0
    )
    assert len(calls) == 1
    assert calls[0][1] == store.read(bundle.context_stream.artifact.storage_key)
    assert calls[0][2] == bundle.native_event_stream.artifact.content_digest
    assert calls[0][3] == bundle.context_stream.context_count
    assert calls[0][4] == dict(bundle.context_stream.component_counts)
    assert calls[0][5] == 1024
    assert result_stream_path.read_bytes() == b"component-results"
