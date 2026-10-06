from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.strategy_lab_v2 import nautilus_runtime_cli
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
    FX_BASE_NOTIONAL_RISK_MODEL,
    OPTION_DELTA_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusAssetClass,
    NautilusCashDefinition,
    NautilusFixedPerFillFeeModelDefinition,
    NautilusInstrumentDefinition,
    NautilusOptionKind,
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
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)
from strategy_runtime import InvocationContextStreamSource, deserialize_invocation_batch


def _runtime_bundle(
    *,
    context_stream_store: LocalArtifactStore | None = None,
    native_event_stream_store: LocalArtifactStore | None = None,
    component_context_stream: bool = False,
    fee_model: NautilusFixedPerFillFeeModelDefinition | None = None,
    instrument_definition: NautilusInstrumentDefinition | None = None,
    session_calendar: SessionCalendarSnapshot | None = None,
    session_periods_per_year: int | None = None,
):
    instrument = instrument_definition or NautilusInstrumentDefinition(
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
    first_event = NautilusEventRecord(
        "prices",
        "adapter-event-1",
        instrument.instrument_id,
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
        instrument.instrument_id,
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
    venue = NautilusVenueDefinition(
        instrument.venue_id,
        "netting",
        "margin"
        if instrument.product_class in {ProductClass.FUTURE, ProductClass.OPTION}
        else "cash",
        (NautilusCashDefinition("USD", Decimal("100000")),),
        "USD",
        fee_model,
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
            shared_risk_policy=SharedRiskPolicy(
                risk_models=(
                    {
                        ProductClass.FX: FX_BASE_NOTIONAL_RISK_MODEL,
                        ProductClass.FUTURE: FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
                        ProductClass.OPTION: OPTION_DELTA_NOTIONAL_RISK_MODEL,
                    }[instrument.product_class],
                )
            ),
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
        session_calendar=session_calendar,
        session_periods_per_year=session_periods_per_year,
    )


def _one_session_calendar() -> SessionCalendarSnapshot:
    label = date(2026, 9, 1)
    session = TradingSession(
        "XNYS:2026-09-01",
        label,
        (
            SessionSegment(
                datetime(2026, 9, 1, 14, 30, tzinfo=UTC),
                datetime(2026, 9, 1, 21, 0, tzinfo=UTC),
            ),
        ),
    )
    return SessionCalendarSnapshot(
        calendar_id="XNYS",
        definition_version="XNYS-session-wire-test-v1",
        timezone_name="America/New_York",
        timezone_database_version="test-tzdb-v1",
        coverage_start=label,
        coverage_end=label,
        days=(CalendarDay(label, CalendarDayStatus.TRADING, session),),
        source_evidence_digest=content_digest("session-wire-test-calendar"),
    )


def test_v5_cli_bundle_verifies_and_passes_frozen_session_calendar(tmp_path, monkeypatch) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    calendar = _one_session_calendar()
    bundle = _runtime_bundle(
        context_stream_store=store,
        session_calendar=calendar,
        session_periods_per_year=252,
    )
    assert bundle.context_stream is not None
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
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")
    observed = []

    def fake_run(engine_input, *, session_calendar, **kwargs):
        observed.append(session_calendar)
        return {"engine_version": "2.0.0rc6", "authoritative": False}

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1_000_000,
            context_stream_path=str(store.path_for(bundle.context_stream.artifact.storage_key)),
            invocation_result_stream_path=str(result_stream_path),
            max_result_bytes=1024,
            account_equity_trace_path=str(equity_trace_path),
            max_account_equity_trace_bytes=1024,
        )
        == 0
    )
    assert observed == [calendar]


def test_runtime_bundle_binds_cli_digest_to_the_readonly_wire_bytes() -> None:
    first = _runtime_bundle()
    second = _runtime_bundle()

    assert first == second
    assert first.input_bundle_digest == content_digest(json.loads(first.wire_bytes))
    assert first.input_bundle_digest.startswith("sha256:")
    assert first.attempt_id == "attempt-1"


def test_runtime_bundle_serializes_signed_fixed_per_fill_fee_model() -> None:
    bundle = _runtime_bundle(
        fee_model=NautilusFixedPerFillFeeModelDefinition(Decimal("-0.25"), "USD")
    )
    payload = json.loads(bundle.wire_bytes)

    assert payload["engine_input"]["venue"]["fee_model"] == {
        "kind": "fixed_per_fill",
        "amount": "-0.25",
        "currency": "USD",
    }
    assert bundle.input_bundle_digest != _runtime_bundle().input_bundle_digest


@pytest.mark.parametrize("product_class", (ProductClass.FUTURE, ProductClass.OPTION))
def test_runtime_bundle_serializes_complete_listed_derivative_metadata(product_class):
    option = product_class is ProductClass.OPTION
    instrument = NautilusInstrumentDefinition(
        "CLZ26.NYMEX" if not option else "CLZ26C080.NYMEX",
        "CLZ26" if not option else "CLZ26C080",
        "NYMEX",
        product_class,
        "USD",
        2,
        0,
        Decimal("0.01"),
        Decimal("1"),
        multiplier=Decimal("1000" if not option else "100"),
        min_quantity=Decimal("1"),
        activation_ns=1_767_225_600_000_000_000,
        expiration_ns=1_800_748_800_000_000_000,
        asset_class=NautilusAssetClass.COMMODITY,
        underlying="CL",
        option_kind=NautilusOptionKind.CALL if option else None,
        strike_price=Decimal("80") if option else None,
        margin_init=Decimal("0.12"),
        margin_maint=Decimal("0.11"),
    )

    payload = json.loads(_runtime_bundle(instrument_definition=instrument).wire_bytes)
    engine_input = payload["engine_input"]
    wire_instrument = engine_input["instruments"][0]

    assert engine_input["input_version"] == "strategy-lab.nautilus-engine-input.v7"
    assert wire_instrument["product_class"] == product_class.value
    assert wire_instrument["asset_class"] == "COMMODITY"
    assert wire_instrument["underlying"] == "CL"
    assert wire_instrument["option_kind"] == ("CALL" if option else None)
    assert wire_instrument["strike_price"] == ("80" if option else None)
    assert wire_instrument["margin_init"] == "0.12"
    assert wire_instrument["margin_maint"] == "0.11"


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
        return {"engine_version": "2.0.0rc6", "authoritative": False, "fills": 2}

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=len(bundle.wire_bytes),
        )
        == 0
    )
    assert len(calls) == 1
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == {"engine_version": "2.0.0rc6", "authoritative": False, "fills": 2}


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
            "engine_version": "2.0.0rc6",
            "authoritative": False,
            "strategy_invocation_result_stream": {"content_digest": "placeholder"},
        }

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
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
            "engine_version": "2.0.0rc6",
            "authoritative": False,
            "strategy_invocation_result_stream": {"content_digest": "placeholder"},
        }

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")
    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
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
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")

    with pytest.raises(ValueError, match="byte length differs"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
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
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")

    with pytest.raises(ValueError, match="byte length differs"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
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
        ("attempt-other", content_digest("snapshot"), "2.0.0rc6", "attempt differs"),
        ("attempt-1", content_digest("different snapshot"), "2.0.0rc6", "snapshot differs"),
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
            expected_version="2.0.0rc6",
            expected_snapshot_fingerprint=content_digest("snapshot"),
            max_input_bytes=1024,
        )

    input_path.write_bytes(bundle.wire_bytes)
    with pytest.raises(ValueError, match="exceeds its memory-derived limit"):
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
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
        return {"engine_version": "2.0.0rc6", "authoritative": False}

    monkeypatch.setattr(nautilus_runtime_cli, "run_native_backtest", fake_run)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")

    assert (
        nautilus_runtime_cli.run_bundle(
            str(input_path),
            str(output_path),
            expected_version="2.0.0rc6",
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


def test_forward_runtime_verifies_mounts_before_building_and_serving_session(
    monkeypatch,
) -> None:
    import io

    from app.strategy_lab_v2 import nautilus_runtime_ipc
    from app.strategy_lab_v2.nautilus_forward_wire import NautilusForwardJsonWireCodec

    bootstrap = object()
    bundle = {"engine_input": {"attempt_id": "attempt-1"}}
    context_bytes = b"verified-context"
    native_bytes = b"verified-native-history"
    builder_calls = []
    serve_calls = []
    checkpoint_fingerprint = "sha256:" + "e" * 64

    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_verify_forward_startup",
        lambda **kwargs: (bootstrap, bundle),
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_context_stream_reference",
        lambda _bundle: ("sha256:" + "a" * 64, len(context_bytes), 1, None),
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_native_event_stream_reference",
        lambda _bundle: ("sha256:" + "b" * 64, len(native_bytes), "sha256:" + "c" * 64, "v1", 1),
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_open_verified_context_stream",
        lambda *_args, **_kwargs: io.BytesIO(context_bytes),
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_open_verified_native_event_stream",
        lambda *_args, **_kwargs: io.BytesIO(native_bytes),
    )

    class FakeSession:
        instance_id = "instance-1"
        runtime_session_fingerprint = "sha256:" + "d" * 64
        base_checkpoint_fingerprint = checkpoint_fingerprint

        def close(self) -> None:
            pass

    def build_factory(received_bootstrap, received_bundle, open_contexts, open_native_events):
        def read_verified_pair():
            with open_contexts() as contexts, open_native_events() as native_events:
                return contexts.read(), native_events.read()

        first_pair = read_verified_pair()
        replay_pair = read_verified_pair()
        builder_calls.append((received_bootstrap, received_bundle, first_pair, replay_pair))
        return lambda _instance_id: FakeSession()

    def serve(_input, _output, handler):
        codec = NautilusForwardJsonWireCodec()
        serve_calls.append(
            handler.open(
                codec.open_payload(
                    instance_id="instance-1",
                    checkpoint_fingerprint=checkpoint_fingerprint,
                )
            )
        )
        serve_calls.append(handler.close({}))
        return 0

    monkeypatch.setattr(nautilus_runtime_ipc, "serve_nautilus_runtime_ipc", serve)
    assert (
        nautilus_runtime_cli.serve_forward_runtime(
            bootstrap_path="/inputs/bootstrap.json",
            bootstrap_fingerprint="sha256:" + "1" * 64,
            input_path="/inputs/bundle.json",
            context_stream_path="/inputs/contexts.ndjson",
            native_event_stream_path="/inputs/native-events.ndjson",
            expected_version="2.0.0rc6",
            instance_id="instance-1",
            snapshot_fingerprint="sha256:" + "2" * 64,
            max_input_bytes=1024,
            session_factory_builder=build_factory,
            input_stream=io.BytesIO(),
            output_stream=io.BytesIO(),
        )
        == 0
    )
    assert builder_calls == [
        (bootstrap, bundle, (context_bytes, native_bytes), (context_bytes, native_bytes))
    ]
    assert len(serve_calls) == 2


def test_main_dispatches_fixed_forward_mode_to_native_session_builder(monkeypatch) -> None:
    import io
    from types import SimpleNamespace

    from app.strategy_lab_v2 import nautilus_forward_native_runtime

    builder = object()
    calls = []
    monkeypatch.setattr(
        nautilus_forward_native_runtime,
        "create_native_forward_session_factory_builder",
        lambda: builder,
    )

    def serve_forward_runtime(**kwargs):
        calls.append(kwargs)
        return 23

    monkeypatch.setattr(nautilus_runtime_cli, "serve_forward_runtime", serve_forward_runtime)
    monkeypatch.setattr(nautilus_runtime_cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO()))
    monkeypatch.setattr(nautilus_runtime_cli.sys, "stdout", SimpleNamespace(buffer=io.BytesIO()))
    assert (
        nautilus_runtime_cli.main(
            [
                "--serve-forward",
                "--input",
                "/inputs/bundle",
                "--output",
                "/outputs/result",
                "--expected-version",
                "2.0.0rc6",
                "--snapshot-fingerprint",
                "sha256:" + "1" * 64,
                "--max-input-bytes",
                "4096",
                "--context-stream",
                "/inputs/contexts",
                "--native-event-stream",
                "/inputs/native-events",
                "--bootstrap",
                "/inputs/bootstrap",
                "--bootstrap-fingerprint",
                "sha256:" + "2" * 64,
                "--instance-id",
                "instance-1",
            ]
        )
        == 23
    )
    assert len(calls) == 1
    assert calls[0]["session_factory_builder"] is builder
    assert calls[0]["bootstrap_path"] == "/inputs/bootstrap"
    assert calls[0]["instance_id"] == "instance-1"


def test_open_verified_context_stream_checks_digest_and_rewinds(tmp_path) -> None:
    import hashlib

    payload = b"immutable-context-input"
    context_path = tmp_path / "contexts.ndjson"
    context_path.write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()

    with nautilus_runtime_cli._open_verified_context_stream(
        str(context_path),
        expected_digest=digest,
        byte_length=len(payload),
        max_bytes=len(payload),
    ) as stream:
        assert stream.tell() == 0
        assert stream.read() == payload

    with pytest.raises(ValueError, match="digest differs"):
        nautilus_runtime_cli._open_verified_context_stream(
            str(context_path),
            expected_digest="sha256:" + "0" * 64,
            byte_length=len(payload),
            max_bytes=len(payload),
        )


def test_probe_does_not_eagerly_import_forward_only_runtime_modules(monkeypatch, capsys) -> None:
    import builtins

    forward_modules = {
        "app.strategy_lab_v2.nautilus_forward_bootstrap",
        "app.strategy_lab_v2.nautilus_forward_runtime_server",
        "app.strategy_lab_v2.nautilus_forward_wire",
        "app.strategy_lab_v2.nautilus_runtime_ipc",
    }
    original_import = builtins.__import__

    def reject_forward_imports(name, *args, **kwargs):
        if name in forward_modules:
            raise AssertionError(f"probe mode imported forward-only module {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_forward_imports)
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "probe_nautilus_runtime",
        lambda *, expected_version: {"engine_version": expected_version},
    )

    assert nautilus_runtime_cli.main(["--probe", "--expected-version", "2.0.0rc6"]) == 0
    assert capsys.readouterr().out == '{"engine_version":"2.0.0rc6"}\n'
