from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from io import BytesIO

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    FX_BASE_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_to_wire
from app.strategy_lab_v2.nautilus_runtime_adapter import (
    NautilusRuntimeDataError,
    run_native_backtest,
)


def _payload() -> dict[str, object]:
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-1",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="component-1",
                strategy_fingerprint=content_digest("strategy"),
                instrument_ids=("EURUSD.SIM",),
                capital_weight=Decimal("1"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(risk_models=(FX_BASE_NOTIONAL_RISK_MODEL,)),
    )
    return {
        "trial_id": "trial-1",
        "attempt_id": "attempt-1",
        "data_snapshot_fingerprint": content_digest("snapshot"),
        "event_tape": {
            "source_tape_fingerprint": content_digest("source-tape"),
            "adapter_version": "strategy-lab.nautilus-event-adapter.v1",
            "events": [
                {
                    "dependency_id": "prices",
                    "event_id": "event-1",
                    "instrument_id": "EURUSD.SIM",
                    "event_type": "quote",
                    "event_time_ns": 1_704_067_200_000_000_000,
                    "sequence": 1,
                    "values": {
                        "bid": Decimal("1.1000"),
                        "ask": Decimal("1.1002"),
                        "bid_size": Decimal("100000"),
                        "ask_size": Decimal("100000"),
                    },
                }
            ],
        },
        "instruments": [
            {
                "instrument_id": "EURUSD.SIM",
                "raw_symbol": "EURUSD",
                "venue_id": "SIM",
                "product_class": "fx",
                "base_currency": "EUR",
                "quote_currency": "USD",
                "price_precision": 5,
                "size_precision": 0,
                "price_increment": Decimal("0.00001"),
                "size_increment": Decimal("1"),
                "multiplier": Decimal("1"),
                "min_quantity": None,
                "max_quantity": None,
                "activation_ns": None,
                "expiration_ns": None,
                "bar_type": "EURUSD.SIM-1-MINUTE-MID-INTERNAL",
            }
        ],
        "venue": {
            "venue_id": "SIM",
            "oms_type": "netting",
            "account_type": "cash",
            "base_currency": "USD",
            "cash": [{"currency": "USD", "amount": Decimal("100000")}],
        },
        "portfolio": portfolio_composition_to_wire(portfolio),
        "strategy_source_digest": content_digest("source"),
        "strategy_manifest_fingerprint": content_digest("manifest"),
        "entrypoint": "strategy.main:Strategy",
        "parameters": {"window": 20},
        "random_seed": 17,
        "input_version": "strategy-lab.nautilus-engine-input.v2",
    }


def test_runtime_adapter_rejects_unknown_engine_input_fields_before_native_import() -> None:
    payload = _payload()
    payload["unexpected"] = True

    with pytest.raises(NautilusRuntimeDataError, match="engine input fields"):
        run_native_backtest(payload)


def test_runtime_adapter_requires_content_addressed_identities() -> None:
    payload = _payload()
    payload["data_snapshot_fingerprint"] = "not-a-digest"

    with pytest.raises(ValueError, match="data_snapshot_fingerprint"):
        run_native_backtest(payload)


def test_runtime_adapter_rejects_duplicate_event_identity() -> None:
    payload = _payload()
    tape = deepcopy(payload["event_tape"])
    assert isinstance(tape, dict)
    events = tape["events"]
    assert isinstance(events, list)
    events.append(deepcopy(events[0]))
    payload["event_tape"] = tape

    with pytest.raises(NautilusRuntimeDataError, match="event ids"):
        run_native_backtest(payload)


def test_runtime_adapter_rejects_event_without_catalog_definition() -> None:
    payload = _payload()
    tape = deepcopy(payload["event_tape"])
    assert isinstance(tape, dict)
    events = tape["events"]
    assert isinstance(events, list)
    event = deepcopy(events[0])
    assert isinstance(event, dict)
    event["instrument_id"] = "GBPUSD.SIM"
    events[0] = event
    payload["event_tape"] = tape

    with pytest.raises(NautilusRuntimeDataError, match="without a definition"):
        run_native_backtest(payload)


def test_runtime_adapter_requires_serialized_strategy_batch_before_native_import() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="serialized strategy invocation batch"):
        run_native_backtest(_payload())


def test_runtime_adapter_rejects_batch_source_mismatch_before_native_import() -> None:
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
        _invocation_batch,
    )
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
        _payload as _probe_payload,
    )

    payload = _probe_payload()
    payload["strategy_source_digest"] = content_digest("different strategy source")

    with pytest.raises(NautilusRuntimeDataError, match="strategy source digest"):
        run_native_backtest(
            payload,
            serialized_strategy_invocation_batch=_invocation_batch(),
        )


def test_runtime_adapter_rejects_stream_source_mismatch_before_native_import() -> None:
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
        _invocation_batch,
    )
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
        _payload as _probe_payload,
    )
    from strategy_runtime import (
        deserialize_invocation_batch,
        serialize_invocation_context_stream,
    )

    payload = _probe_payload()
    payload["strategy_source_digest"] = content_digest("different strategy source")
    source, manifest, contexts, entrypoint, max_intents = deserialize_invocation_batch(
        _invocation_batch()
    )
    stream = BytesIO()
    serialize_invocation_context_stream(
        stream,
        source=source,
        manifest=manifest,
        contexts=contexts,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents,
    )
    stream.seek(0)

    with pytest.raises(NautilusRuntimeDataError, match="strategy source digest"):
        run_native_backtest(
            payload,
            invocation_context_stream=stream,
            expected_context_count=1,
        )
