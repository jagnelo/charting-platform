from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    FX_BASE_NOTIONAL_RISK_MODEL,
    EvaluationWindow,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusCashDefinition,
    NautilusComponentStrategyBinding,
    NautilusEngineInput,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
    build_nautilus_engine_input,
    component_strategy_binding_to_wire,
    component_strategy_bindings_from_wire,
    evaluation_window_to_wire,
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


def _multi_portfolio() -> PortfolioComposition:
    return PortfolioComposition(
        portfolio_id="portfolio-multi",
        version_id="portfolio-multi-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="alpha",
                strategy_fingerprint=content_digest("strategy-alpha"),
                instrument_ids=("EURUSD.SIM",),
                capital_weight=Decimal("0.5"),
            ),
            PortfolioComponent(
                component_id="beta",
                strategy_fingerprint=content_digest("strategy-beta"),
                instrument_ids=("EURUSD.SIM",),
                capital_weight=Decimal("0.5"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(risk_models=(FX_BASE_NOTIONAL_RISK_MODEL,)),
    )


def _binding(
    component_id: str,
    strategy: str,
    source: str,
    params: dict[str, object],
) -> NautilusComponentStrategyBinding:
    return NautilusComponentStrategyBinding(
        component_id=component_id,
        strategy_fingerprint=content_digest(strategy),
        strategy_source_digest=content_digest(source),
        strategy_manifest_fingerprint=content_digest(f"manifest-{strategy}"),
        entrypoint="strategy.main:Strategy",
        parameters_digest=content_digest(params),
        max_intents_per_event=50,
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
    assert tuple(binding.component_id for binding in engine_input.strategy_bindings) == (
        "component-1",
    )
    assert engine_input.input_version == "strategy-lab.nautilus-engine-input.v4"
    assert engine_input.fingerprint.startswith("sha256:")


def test_evaluation_window_wire_preserves_identity_and_half_open_bounds() -> None:
    from datetime import UTC, datetime, timedelta

    start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    window = EvaluationWindow(
        start=start + timedelta(hours=1),
        end=start + timedelta(hours=3),
        purpose="out_of_sample",
        warmup_start=start,
    )

    wire = evaluation_window_to_wire(window)

    assert wire == {
        "fingerprint": window.fingerprint,
        "purpose": "out_of_sample",
        "warmup_start_ns": 1_704_205_800_000_000_000,
        "start_ns": 1_704_209_400_000_000_000,
        "end_ns": 1_704_216_600_000_000_000,
    }


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


def test_engine_input_authenticates_every_portfolio_strategy_binding() -> None:
    alpha = _binding("alpha", "strategy-alpha", "source-alpha", {"window": 10})
    beta = _binding("beta", "strategy-beta", "source-beta", {"fast": 3})
    engine_input = build_nautilus_engine_input(
        trial_id="trial-multi",
        attempt_id="attempt-multi",
        data_snapshot_fingerprint=content_digest("snapshot-multi"),
        event_tape=_tape(),
        instruments=(_instrument(),),
        venue=_venue(),
        portfolio=_multi_portfolio(),
        strategy_source_digest=alpha.strategy_source_digest,
        strategy_manifest_fingerprint=alpha.strategy_manifest_fingerprint,
        entrypoint=alpha.entrypoint,
        parameters={"window": 10},
        random_seed=17,
        strategy_bindings=(beta, alpha),
    )

    assert tuple(binding.component_id for binding in engine_input.strategy_bindings) == (
        "alpha",
        "beta",
    )
    assert engine_input.strategy_bindings[1] == beta
    assert component_strategy_bindings_from_wire(
        [component_strategy_binding_to_wire(beta), component_strategy_binding_to_wire(alpha)]
    ) == (alpha, beta)


def test_engine_input_rejects_incomplete_or_misbound_multi_strategy_sets() -> None:
    alpha = _binding("alpha", "strategy-alpha", "source-alpha", {"window": 10})
    common: dict[str, Any] = dict(
        trial_id="trial-multi",
        attempt_id="attempt-multi",
        data_snapshot_fingerprint=content_digest("snapshot-multi"),
        event_tape=_tape(),
        instruments=(_instrument(),),
        venue=_venue(),
        portfolio=_multi_portfolio(),
        strategy_source_digest=alpha.strategy_source_digest,
        strategy_manifest_fingerprint=alpha.strategy_manifest_fingerprint,
        entrypoint=alpha.entrypoint,
        parameters={"window": 10},
        random_seed=17,
    )

    with pytest.raises(ValueError, match="requires explicit component strategy bindings"):
        build_nautilus_engine_input(**common)
    with pytest.raises(ValueError, match="cover the complete portfolio"):
        build_nautilus_engine_input(strategy_bindings=(alpha,), **common)
    wrong_beta = _binding("beta", "wrong-strategy", "source-beta", {"fast": 3})
    with pytest.raises(ValueError, match="differs from portfolio identity"):
        build_nautilus_engine_input(strategy_bindings=(alpha, wrong_beta), **common)


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
