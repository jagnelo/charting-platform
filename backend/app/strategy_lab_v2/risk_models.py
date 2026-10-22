"""Registered product-risk valuation formulas for pre-trade exposure estimates.

These formulas are deliberately small and explicit.  They consume adapter-
verified instrument economics and return a signed base-notional estimate for
shared-account risk checks; they do not model margin, liquidity, settlement,
greeks beyond the declared option delta, or engine fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    OPTION_DELTA_NOTIONAL_RISK_MODEL,
    SUPPORTED_PRODUCT_RISK_MODELS,
    ProductRiskModel,
)
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.sdk import OrderSide

RISK_VALUATION_DEFINITION_VERSION = (
    f"strategy-lab.risk-valuation.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _positive(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


@dataclass(frozen=True, slots=True)
class RiskValuationReceipt:
    """Digest-bound output of one registered product-risk formula."""

    instrument_id: str
    risk_model: ProductRiskModel
    side: OrderSide
    quantity: Decimal
    signed_base_notional: Decimal
    valuation_evidence_digest: str
    definition_version: str = RISK_VALUATION_DEFINITION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if self.risk_model not in SUPPORTED_PRODUCT_RISK_MODELS:
            raise ValueError("risk_model is not a registered product risk model")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide")
        _positive(self.quantity, "quantity")
        if (
            not isinstance(self.signed_base_notional, Decimal)
            or not self.signed_base_notional.is_finite()
            or self.signed_base_notional == 0
        ):
            raise ValueError("signed_base_notional must be finite and non-zero")
        require_sha256_digest(
            self.valuation_evidence_digest,
            field_name="valuation_evidence_digest",
        )
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError("definition_version must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@deterministic_decimal_math
def estimate_signed_base_notional(
    *,
    instrument_id: str,
    risk_model: ProductRiskModel,
    side: OrderSide,
    quantity: Decimal,
    mark_price: Decimal,
    contract_multiplier: Decimal,
    quote_to_base_rate: Decimal,
    valuation_evidence_digest: str,
    underlying_mark_price: Decimal | None = None,
    option_delta: Decimal | None = None,
) -> RiskValuationReceipt:
    """Apply one registered model to adapter-verified order economics.

    Cash equities and crypto use marked quantity value.  Futures use contract
    notional.  Options use underlying marked notional multiplied by the
    supplied signed delta.  FX uses the pair's marked notional converted to the
    portfolio base currency.  All values remain estimates until the native
    engine reports authoritative orders and fills.
    """

    if not isinstance(instrument_id, str) or not instrument_id.strip():
        raise ValueError("instrument_id must not be empty")
    if risk_model not in SUPPORTED_PRODUCT_RISK_MODELS:
        raise ValueError("risk_model is not a registered product risk model")
    if not isinstance(side, OrderSide):
        raise TypeError("side must be an OrderSide")
    _positive(quantity, "quantity")
    _positive(mark_price, "mark_price")
    _positive(contract_multiplier, "contract_multiplier")
    _positive(quote_to_base_rate, "quote_to_base_rate")
    require_sha256_digest(valuation_evidence_digest, field_name="valuation_evidence_digest")

    if risk_model == CASH_EQUITY_NOTIONAL_RISK_MODEL and contract_multiplier != Decimal(1):
        raise ValueError("cash-equity risk valuation requires contract_multiplier=1")
    if risk_model == OPTION_DELTA_NOTIONAL_RISK_MODEL:
        if underlying_mark_price is None:
            raise ValueError("option risk valuation requires underlying_mark_price")
        _positive(underlying_mark_price, "underlying_mark_price")
        if (
            not isinstance(option_delta, Decimal)
            or not option_delta.is_finite()
            or option_delta < Decimal(-1)
            or option_delta > Decimal(1)
        ):
            raise ValueError("option_delta must be a finite Decimal between -1 and 1")
        price_basis = underlying_mark_price
        delta = option_delta
    else:
        if underlying_mark_price is not None or option_delta is not None:
            raise ValueError("option-only valuation inputs are not valid for this risk model")
        price_basis = mark_price
        delta = Decimal(1)

    signed_quantity = quantity if side is OrderSide.BUY else -quantity
    signed_notional = (
        signed_quantity
        * price_basis
        * contract_multiplier
        * quote_to_base_rate
        * delta
    )
    if signed_notional == 0:
        raise ValueError("risk valuation produced a zero signed base notional")
    return RiskValuationReceipt(
        instrument_id=instrument_id,
        risk_model=risk_model,
        side=side,
        quantity=quantity,
        signed_base_notional=signed_notional,
        valuation_evidence_digest=valuation_evidence_digest,
    )


def registered_risk_model(risk_model: ProductRiskModel) -> bool:
    """Return whether the exact versioned model is supported by this package."""

    return risk_model in SUPPORTED_PRODUCT_RISK_MODELS
