"""Strict wire codec for the immutable portfolio allocation input."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from enum import Enum
from typing import Any

from app.strategy_lab_v2.contracts import (
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    SharedRiskPolicy,
    TargetConflictPolicy,
)


def portfolio_composition_to_wire(portfolio: PortfolioComposition) -> dict[str, Any]:
    """Serialize all allocation/risk fields and bind them to the domain fingerprint."""

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if portfolio.rebalance_policy is not None:
        raise ValueError("calendar rebalancing is not represented by the current engine input")
    result = _wire_value(asdict(portfolio))
    assert isinstance(result, dict)
    result["fingerprint"] = portfolio.fingerprint
    return result


def portfolio_composition_from_wire(value: object) -> PortfolioComposition:
    """Validate and reconstruct the exact allocation policy supplied to the worker."""

    if not isinstance(value, dict) or set(value) != {
        "portfolio_id",
        "version_id",
        "initial_capital",
        "base_currency",
        "components",
        "rebalance_policy",
        "shared_risk_policy",
        "fingerprint",
    }:
        raise ValueError("portfolio execution policy fields are invalid")
    if value["rebalance_policy"] is not None:
        raise ValueError("calendar rebalancing is not represented by the current engine input")
    components_wire = value["components"]
    if not isinstance(components_wire, list):
        raise ValueError("portfolio components must be a list")
    components: list[PortfolioComponent] = []
    for item in components_wire:
        if not isinstance(item, dict) or set(item) != {
            "component_id",
            "strategy_fingerprint",
            "instrument_ids",
            "capital_weight",
            "priority",
        }:
            raise ValueError("portfolio component fields are invalid")
        instrument_ids = item["instrument_ids"]
        if not isinstance(instrument_ids, list) or any(
            not isinstance(instrument_id, str) for instrument_id in instrument_ids
        ):
            raise ValueError("portfolio component instrument ids are invalid")
        priority = item["priority"]
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("portfolio component priority is invalid")
        components.append(
            PortfolioComponent(
                component_id=_text(item["component_id"], "component_id"),
                strategy_fingerprint=_text(item["strategy_fingerprint"], "strategy_fingerprint"),
                instrument_ids=tuple(instrument_ids),
                capital_weight=_decimal(item["capital_weight"], "capital_weight"),
                priority=priority,
            )
        )
    policy_wire = value["shared_risk_policy"]
    if not isinstance(policy_wire, dict) or set(policy_wire) != {
        "max_gross_exposure_fraction",
        "max_net_exposure_fraction",
        "max_instrument_gross_exposure_fraction",
        "max_component_gross_exposure_fraction",
        "max_component_leverage",
        "max_open_instruments",
        "allow_short_positions",
        "target_conflict_policy",
        "risk_models",
        "definition_version",
    }:
        raise ValueError("shared risk policy fields are invalid")
    models_wire = policy_wire["risk_models"]
    if not isinstance(models_wire, list):
        raise ValueError("portfolio risk models must be a list")
    models: list[ProductRiskModel] = []
    for item in models_wire:
        if not isinstance(item, dict) or set(item) != {
            "product_class",
            "exposure_measure",
            "definition_digest",
        }:
            raise ValueError("portfolio risk model fields are invalid")
        models.append(
            ProductRiskModel(
                product_class=ProductClass(_text(item["product_class"], "product_class")),
                exposure_measure=RiskExposureMeasure(
                    _text(item["exposure_measure"], "exposure_measure")
                ),
                definition_digest=_text(item["definition_digest"], "definition_digest"),
            )
        )
    max_open = policy_wire["max_open_instruments"]
    if max_open is not None and (not isinstance(max_open, int) or isinstance(max_open, bool)):
        raise ValueError("shared risk max_open_instruments is invalid")
    allow_short = policy_wire["allow_short_positions"]
    if not isinstance(allow_short, bool):
        raise ValueError("shared risk allow_short_positions is invalid")
    portfolio = PortfolioComposition(
        portfolio_id=_text(value["portfolio_id"], "portfolio_id"),
        version_id=_text(value["version_id"], "version_id"),
        initial_capital=_decimal(value["initial_capital"], "initial_capital"),
        base_currency=_text(value["base_currency"], "base_currency"),
        components=tuple(components),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=_decimal(
                policy_wire["max_gross_exposure_fraction"], "max_gross_exposure_fraction"
            ),
            max_net_exposure_fraction=_decimal(
                policy_wire["max_net_exposure_fraction"], "max_net_exposure_fraction"
            ),
            max_instrument_gross_exposure_fraction=_decimal(
                policy_wire["max_instrument_gross_exposure_fraction"],
                "max_instrument_gross_exposure_fraction",
            ),
            max_component_gross_exposure_fraction=_decimal(
                policy_wire["max_component_gross_exposure_fraction"],
                "max_component_gross_exposure_fraction",
            ),
            max_component_leverage=_decimal(
                policy_wire["max_component_leverage"], "max_component_leverage"
            ),
            max_open_instruments=max_open,
            allow_short_positions=allow_short,
            target_conflict_policy=TargetConflictPolicy(
                _text(policy_wire["target_conflict_policy"], "target_conflict_policy")
            ),
            risk_models=tuple(models),
            definition_version=_text(policy_wire["definition_version"], "definition_version"),
        ),
    )
    if value["fingerprint"] != portfolio.fingerprint:
        raise ValueError("portfolio execution policy fingerprint is invalid")
    return portfolio


def _wire_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("portfolio decimals must be finite")
        return str(value)
    if isinstance(value, Enum):
        return _wire_value(value.value)
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("portfolio mappings require string keys")
        return {key: _wire_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_wire_value(item) for item in value]
    if value is None or isinstance(value, str | bool | int):
        return value
    raise ValueError(f"unsupported portfolio wire type {type(value).__name__}")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be encoded as text")
    try:
        parsed = Decimal(value)
    except Exception as error:
        raise ValueError(f"{field_name} is not a valid decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


__all__ = ["portfolio_composition_from_wire", "portfolio_composition_to_wire"]
