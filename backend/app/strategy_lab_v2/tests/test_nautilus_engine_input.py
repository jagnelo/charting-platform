from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

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
    NautilusEngineInput,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
    build_nautilus_engine_input,
)
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventRecord,
    NautilusEventTape,
)


def _instrument(
    *, venue_id: str = "SIM", instrument_id: str = "EURUSD.SIM"
) -> NautilusInstrumentDefinition:
    return NautilusInstrumentDefinition(
        instrument_id=instrument_id,
        raw_symbol=instrument_id.split(".", 1)[0],
        venue_id=venue_id,
        product_class=ProductClass.FX,
        quote_currency="USD",
        base_currency="EUR",
        price_precision=5,
        size_precision=0,
        price_increment=Decimal("0.00001"),
        size_increment=Decimal("1"),
    )


def _venue(*, venue_id: str = "SIM") -> NautilusVenueDefinition:
    return NautilusVenueDefinition(
        venue_id=venue_id,
        oms_type="netting",
        account_type="cash",
        cash=(NautilusCashDefinition("USD", Decimal("100000")),),
        base_currency="USD",
    )


def _portfolio() -> PortfolioComposition:
    return PortfolioComposition(
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


def _tape(*, instrument_id: str = "EURUSD.SIM") -> NautilusEventTape:
    record = NautilusEventRecord(
        dependency_id="prices",
        event_id="event-1",
        instrument_id=instrument_id,
        event_type="quote",
        event_time_ns=1_704_067_200_000_000_000,
        sequence=1,
        values={
            "bid": Decimal("1.1"),
            "ask": Decimal("1.1002"),
            "bid_size": Decimal("100000"),
            "ask_size": Decimal("100000"),
        },
    )
    return NautilusEventTape(content_digest("source-tape"), (record,))


def _without(values: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in keys}


def test_engine_input_binds_tape_catalog_and_shared_account() -> None:
    instrument = _instrument()
    engine_input = build_nautilus_engine_input(
        trial_id="trial-1",
        attempt_id="attempt-1",
        data_snapshot_fingerprint=content_digest("snapshot"),
        event_tape=_tape(),
        instruments=(instrument,),
        venue=_venue(),
        portfolio=_portfolio(),
        strategy_source_digest=content_digest("source"),
        strategy_manifest_fingerprint=content_digest("manifest"),
        entrypoint="strategy.main:Strategy",
        parameters={"window": 20},
        random_seed=17,
    )

    assert isinstance(engine_input, NautilusEngineInput)
    assert engine_input.instruments == (instrument,)
    assert engine_input.parameters["window"] == 20
    assert engine_input.fingerprint.startswith("sha256:")


def test_engine_input_is_deterministic_and_freezes_parameters() -> None:
    kwargs: dict[str, Any] = dict(
        trial_id="trial-1",
        attempt_id="attempt-1",
        data_snapshot_fingerprint=content_digest("snapshot"),
        event_tape=_tape(),
        instruments=(_instrument(),),
        venue=_venue(),
        portfolio=_portfolio(),
        strategy_source_digest=content_digest("source"),
        strategy_manifest_fingerprint=content_digest("manifest"),
        entrypoint="strategy.main:Strategy",
        parameters={"nested": {"b": 2, "a": 1}},
        random_seed=17,
    )
    first = build_nautilus_engine_input(**kwargs)
    second = build_nautilus_engine_input(**kwargs)
    assert first == second
    assert first.fingerprint == second.fingerprint
    with pytest.raises(TypeError):
        first.parameters["new"] = 1  # type: ignore[index]


def test_engine_input_rejects_missing_or_cross_venue_instruments() -> None:
    kwargs: dict[str, Any] = dict(
        trial_id="trial-1",
        attempt_id="attempt-1",
        data_snapshot_fingerprint=content_digest("snapshot"),
        event_tape=_tape(),
        venue=_venue(),
        portfolio=_portfolio(),
        strategy_source_digest=content_digest("source"),
        strategy_manifest_fingerprint=content_digest("manifest"),
        entrypoint="strategy.main:Strategy",
        parameters={},
        random_seed=17,
    )
    with pytest.raises(ValueError, match="without a definition"):
        build_nautilus_engine_input(
            instruments=(_instrument(),),
            event_tape=_tape(instrument_id="GBPUSD.SIM"),
            **_without(kwargs, "instruments", "event_tape"),
        )
    with pytest.raises(ValueError, match="different venue"):
        build_nautilus_engine_input(instruments=(_instrument(venue_id="OTHER"),), **kwargs)


def test_engine_input_rejects_identity_and_catalog_conflicts() -> None:
    instrument = _instrument()
    kwargs = dict(
        trial_id="trial-1",
        attempt_id="attempt-1",
        data_snapshot_fingerprint=content_digest("snapshot"),
        event_tape=_tape(),
        instruments=(instrument,),
        venue=_venue(),
        portfolio=_portfolio(),
        strategy_source_digest=content_digest("source"),
        strategy_manifest_fingerprint=content_digest("manifest"),
        entrypoint="strategy.main:Strategy",
        parameters={},
        random_seed=17,
    )
    with pytest.raises(ValueError, match="unique"):
        build_nautilus_engine_input(
            instruments=(instrument, instrument),
            **_without(kwargs, "instruments"),
        )
    with pytest.raises(ValueError, match="entrypoint"):
        build_nautilus_engine_input(
            entrypoint="strategy.main",
            **_without(kwargs, "entrypoint"),
        )
    with pytest.raises(ValueError, match="source_digest"):
        build_nautilus_engine_input(
            strategy_source_digest="bad",
            **_without(kwargs, "strategy_source_digest"),
        )


def test_instrument_definition_rejects_invalid_lifecycle() -> None:
    with pytest.raises(ValueError, match="expiration_ns"):
        NautilusInstrumentDefinition(
            instrument_id="A.SIM",
            raw_symbol="A",
            venue_id="SIM",
            product_class=ProductClass.EQUITY,
            quote_currency="USD",
            price_precision=2,
            size_precision=0,
            price_increment=Decimal("0.01"),
            size_increment=Decimal("1"),
            activation_ns=10,
            expiration_ns=10,
        )
