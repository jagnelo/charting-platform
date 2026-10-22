from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
    FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
    FX_BASE_NOTIONAL_RISK_MODEL,
    OPTION_DELTA_NOTIONAL_RISK_MODEL,
    SUPPORTED_PRODUCT_RISK_MODELS,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
)
from app.strategy_lab_v2.risk_models import (
    RiskValuationReceipt,
    estimate_signed_base_notional,
    registered_risk_model,
)
from app.strategy_lab_v2.sdk import OrderSide

EVIDENCE = content_digest("risk-valuation-evidence-v1")


def _estimate(
    *,
    model=CASH_EQUITY_NOTIONAL_RISK_MODEL,
    side=OrderSide.BUY,
    quantity="2",
    mark_price="100",
    multiplier="1",
    rate="1",
    underlying: str | None = None,
    delta: str | None = None,
):
    return estimate_signed_base_notional(
        instrument_id="instrument-1",
        risk_model=model,
        side=side,
        quantity=Decimal(quantity),
        mark_price=Decimal(mark_price),
        contract_multiplier=Decimal(multiplier),
        quote_to_base_rate=Decimal(rate),
        valuation_evidence_digest=EVIDENCE,
        underlying_mark_price=None if underlying is None else Decimal(underlying),
        option_delta=None if delta is None else Decimal(delta),
    )


def test_registered_models_are_exact_content_bound_versions() -> None:
    assert tuple(SUPPORTED_PRODUCT_RISK_MODELS) == (
        CASH_EQUITY_NOTIONAL_RISK_MODEL,
        CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
        FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
        OPTION_DELTA_NOTIONAL_RISK_MODEL,
        FX_BASE_NOTIONAL_RISK_MODEL,
    )
    assert all(registered_risk_model(model) for model in SUPPORTED_PRODUCT_RISK_MODELS)
    assert not registered_risk_model(
        ProductRiskModel(
            ProductClass.OTHER,
            RiskExposureMeasure.SIGNED_BASE_NOTIONAL,
            content_digest("unregistered-model"),
        )
    )


def test_cash_equity_and_crypto_use_marked_quantity_value() -> None:
    cash = _estimate(quantity="10", mark_price="125", rate="0.8")
    crypto = _estimate(
        model=CRYPTO_SPOT_NOTIONAL_RISK_MODEL,
        quantity="2",
        mark_price="25000",
        rate="0.95",
    )

    assert cash.signed_base_notional == Decimal("1000")
    assert crypto.signed_base_notional == Decimal("47500.00")
    assert cash.risk_model == CASH_EQUITY_NOTIONAL_RISK_MODEL
    assert cash.fingerprint == _estimate(quantity="10", mark_price="125", rate="0.8").fingerprint


def test_future_and_fx_models_include_contract_and_conversion_economics() -> None:
    future = _estimate(
        model=FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
        quantity="3",
        mark_price="5000",
        multiplier="50",
        rate="0.9",
    )
    fx = _estimate(
        model=FX_BASE_NOTIONAL_RISK_MODEL,
        quantity="100000",
        mark_price="1.1",
        rate="0.9",
    )

    assert future.signed_base_notional == Decimal("675000.0")
    assert fx.signed_base_notional == Decimal("99000.0")


def test_option_model_requires_underlying_mark_and_uses_signed_delta() -> None:
    call = _estimate(
        model=OPTION_DELTA_NOTIONAL_RISK_MODEL,
        quantity="1",
        mark_price="8",
        multiplier="100",
        underlying="50",
        delta="0.5",
    )
    sold_put = _estimate(
        model=OPTION_DELTA_NOTIONAL_RISK_MODEL,
        side=OrderSide.SELL,
        quantity="1",
        mark_price="4",
        multiplier="100",
        underlying="50",
        delta="-0.4",
    )

    assert call.signed_base_notional == Decimal("2500.0")
    assert sold_put.signed_base_notional == Decimal("2000.0")
    with pytest.raises(ValueError, match="underlying_mark_price"):
        _estimate(model=OPTION_DELTA_NOTIONAL_RISK_MODEL, delta="0.5")
    with pytest.raises(ValueError, match="between -1 and 1"):
        _estimate(model=OPTION_DELTA_NOTIONAL_RISK_MODEL, underlying="50", delta="1.01")


def test_registered_models_reject_incompatible_inputs_and_unregistered_digests() -> None:
    with pytest.raises(ValueError, match="contract_multiplier=1"):
        _estimate(multiplier="2")
    with pytest.raises(ValueError, match="option-only"):
        _estimate(underlying="50", delta="0.5")
    with pytest.raises(ValueError, match="zero signed"):
        _estimate(
            model=OPTION_DELTA_NOTIONAL_RISK_MODEL,
            underlying="50",
            delta="0",
        )
    with pytest.raises(ValueError, match="registered product"):
        _estimate(
            model=ProductRiskModel(
                ProductClass.FUTURE,
                RiskExposureMeasure.SIGNED_CONTRACT_NOTIONAL,
                content_digest("different-future-model"),
            )
        )


def test_receipts_preserve_model_sign_and_decimal_context() -> None:
    baseline = _estimate(quantity="0.333", mark_price="123.4567", rate="0.91")
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = _estimate(quantity="0.333", mark_price="123.4567", rate="0.91")
    assert constrained == baseline
    with pytest.raises(ValueError, match="finite and non-zero"):
        RiskValuationReceipt(
            "instrument-1",
            CASH_EQUITY_NOTIONAL_RISK_MODEL,
            OrderSide.BUY,
            Decimal("1"),
            Decimal("0"),
            EVIDENCE,
        )
