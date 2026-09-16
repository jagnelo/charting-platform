"""Pure portfolio target allocation and shared-account risk checks.

This layer resolves component target-position intents into portfolio weights. It
does not synthesize fills or translate targets into engine orders; the eventual
engine adapter remains responsible for using authoritative instrument economics.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    SUPPORTED_PRODUCT_RISK_MODELS,
    PortfolioComponent,
    PortfolioComposition,
    ProductRiskModel,
    SharedRiskPolicy,
    TargetConflictPolicy,
)
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.sdk import OrderIntent, StrategyIntent, TargetPositionIntent

ALLOCATION_DEFINITION_VERSION = (
    f"strategy-lab.allocation.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ComponentPositionExposure:
    """Signed base-notional exposure under the snapshot's instrument risk model."""

    component_id: str
    instrument_id: str
    signed_base_risk_exposure: Decimal

    def __post_init__(self) -> None:
        if not self.component_id.strip() or not self.instrument_id.strip():
            raise ValueError("position exposure component and instrument ids must not be empty")
        if (
            not isinstance(self.signed_base_risk_exposure, Decimal)
            or not self.signed_base_risk_exposure.is_finite()
        ):
            raise ValueError("signed_base_risk_exposure must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class InstrumentRiskBinding:
    instrument_id: str
    risk_model: ProductRiskModel

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        if not isinstance(self.risk_model, ProductRiskModel):
            raise TypeError("risk_model must be a ProductRiskModel")


@dataclass(frozen=True, slots=True)
class PortfolioExposureSnapshot:
    """One event-aligned account valuation used as the allocation risk baseline.

    `valuation_evidence_digest` is an opaque engine-adapter assertion in this
    engine-neutral package. The adapter must verify its source values, FX and
    instrument semantics before constructing this snapshot.
    """

    portfolio_fingerprint: str
    run_attempt_id: str
    event_time: datetime
    event_sequence: int
    account_equity: Decimal
    account_cash_balance: Decimal
    base_currency: str
    valuation_evidence_digest: str
    positions: tuple[ComponentPositionExposure, ...] = ()
    instrument_risk_models: tuple[InstrumentRiskBinding, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        require_sha256_digest(
            self.valuation_evidence_digest, field_name="valuation_evidence_digest"
        )
        _aware(self.event_time, "event_time")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        if (
            not isinstance(self.account_equity, Decimal)
            or not self.account_equity.is_finite()
            or self.account_equity <= 0
        ):
            raise ValueError("account_equity must be a finite positive Decimal")
        if (
            not isinstance(self.account_cash_balance, Decimal)
            or not self.account_cash_balance.is_finite()
        ):
            raise ValueError("account_cash_balance must be a finite Decimal")
        if (
            not isinstance(self.base_currency, str)
            or len(self.base_currency) != 3
            or not self.base_currency.isascii()
            or not self.base_currency.isalpha()
        ):
            raise ValueError("base_currency must be a three-letter code")
        positions = tuple(self.positions)
        risk_models = tuple(self.instrument_risk_models)
        if any(not isinstance(item, ComponentPositionExposure) for item in positions):
            raise TypeError("positions must contain ComponentPositionExposure values")
        if any(not isinstance(item, InstrumentRiskBinding) for item in risk_models):
            raise TypeError("instrument_risk_models must contain InstrumentRiskBinding values")
        keys = [(item.component_id, item.instrument_id) for item in positions]
        if len(keys) != len(set(keys)):
            raise ValueError("position exposures must be unique per component and instrument")
        risk_instruments = [item.instrument_id for item in risk_models]
        if len(risk_instruments) != len(set(risk_instruments)):
            raise ValueError("instrument risk models must be unique per instrument")
        object.__setattr__(self, "base_currency", self.base_currency.upper())
        object.__setattr__(
            self,
            "positions",
            tuple(sorted(positions, key=lambda item: (item.component_id, item.instrument_id))),
        )
        object.__setattr__(
            self,
            "instrument_risk_models",
            tuple(sorted(risk_models, key=lambda item: item.instrument_id)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ComponentTargetRequest:
    """Target weight relative to the component's current share of account equity."""

    component_id: str
    instrument_id: str
    target_fraction_of_component_budget: Decimal
    event_time: datetime
    event_sequence: int

    def __post_init__(self) -> None:
        if not self.component_id.strip() or not self.instrument_id.strip():
            raise ValueError("target request component and instrument ids must not be empty")
        if (
            not isinstance(self.target_fraction_of_component_budget, Decimal)
            or not self.target_fraction_of_component_budget.is_finite()
        ):
            raise ValueError("target fraction must be a finite Decimal")
        _aware(self.event_time, "event_time")
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")


class AllocationRejectionCode(StrEnum):
    LOWER_PRIORITY = "lower_priority"
    TARGET_CONFLICT = "target_conflict"
    PRIORITY_TIE = "priority_tie"


class RiskBreach(StrEnum):
    GROSS_EXPOSURE = "gross_exposure"
    NET_EXPOSURE = "net_exposure"
    INSTRUMENT_CONCENTRATION = "instrument_concentration"
    COMPONENT_CONCENTRATION = "component_concentration"
    COMPONENT_LEVERAGE = "component_leverage"
    OPEN_INSTRUMENT_COUNT = "open_instrument_count"
    SHORT_POSITION = "short_position"


@dataclass(frozen=True, slots=True)
class TargetRejection:
    component_id: str
    instrument_id: str
    code: AllocationRejectionCode


@dataclass(frozen=True, slots=True)
class ComponentTargetExposure:
    component_id: str
    instrument_id: str
    target_fraction_of_equity: Decimal


@dataclass(frozen=True, slots=True)
class InstrumentTargetExposure:
    instrument_id: str
    target_fraction_of_equity: Decimal
    target_signed_base_notional: Decimal


@dataclass(frozen=True, slots=True)
class AllocationDecision:
    """Deterministic target set plus an explicit all-or-nothing risk gate.

    `proposed_*` fields are diagnostic only when `risk_limits_satisfied` is false.
    Passing these notional limits is not permission to execute; a product-aware
    engine adapter must perform its own final validation.
    """

    definition_version: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    policy_fingerprint: str
    event_time: datetime
    event_sequence: int
    risk_limits_satisfied: bool
    proposed_component_exposures: tuple[ComponentTargetExposure, ...]
    proposed_instrument_targets: tuple[InstrumentTargetExposure, ...]
    risk_approved_instrument_targets: tuple[InstrumentTargetExposure, ...]
    rejected_targets: tuple[TargetRejection, ...]
    risk_breaches: tuple[RiskBreach, ...]
    gross_exposure_fraction: Decimal
    net_exposure_fraction: Decimal
    max_instrument_gross_exposure_fraction: Decimal
    max_component_gross_exposure_fraction: Decimal
    open_instrument_count: int

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def component_targets_from_intents(
    portfolio: PortfolioComposition,
    intents_by_component: Mapping[str, Iterable[StrategyIntent]],
    *,
    event_time: datetime,
    event_sequence: int,
) -> tuple[ComponentTargetRequest, ...]:
    """Normalize supported target-position outputs; fail closed on raw orders.

    An OrderIntent quantity cannot be converted to shared-account exposure here:
    instrument multiplier, currency conversion, lot rules, and nonlinear product
    risk models must come from the later engine/instrument adapter.
    """

    _aware(event_time, "event_time")
    if (
        not isinstance(event_sequence, int)
        or isinstance(event_sequence, bool)
        or event_sequence < 0
    ):
        raise ValueError("event_sequence must be a non-negative integer")
    components = {item.component_id: item for item in portfolio.components}
    requests: list[ComponentTargetRequest] = []
    for component_id in sorted(intents_by_component):
        component = components.get(component_id)
        if component is None:
            raise ValueError(f"unknown portfolio component {component_id!r}")
        instrument_scope = set(component.instrument_ids)
        for intent in intents_by_component[component_id]:
            if isinstance(intent, OrderIntent):
                raise ValueError(
                    "raw OrderIntent sizing requires engine-native instrument economics "
                    "and is not supported by the engine-neutral allocator"
                )
            if not isinstance(intent, TargetPositionIntent):
                raise TypeError("allocation accepts only typed strategy intents")
            if intent.instrument_id not in instrument_scope:
                raise ValueError(
                    f"component {component_id!r} emitted undeclared instrument "
                    f"{intent.instrument_id!r}"
                )
            requests.append(
                ComponentTargetRequest(
                    component_id=component_id,
                    instrument_id=intent.instrument_id,
                    target_fraction_of_component_budget=intent.target_fraction,
                    event_time=event_time,
                    event_sequence=event_sequence,
                )
            )
    keys = [(item.component_id, item.instrument_id) for item in requests]
    if len(keys) != len(set(keys)):
        raise ValueError("a component may target each instrument only once per event")
    return tuple(sorted(requests, key=lambda item: (item.instrument_id, item.component_id)))


@deterministic_decimal_math
def allocate_component_targets(
    portfolio: PortfolioComposition,
    exposure_snapshot: PortfolioExposureSnapshot,
    requests: Iterable[ComponentTargetRequest],
) -> AllocationDecision:
    """Resolve same-event targets and enforce gross/net/concentration limits.

    Target fractions are multiplied by the component's capital weight and current
    account equity. Existing component-attributed positions are preserved unless
    a target for that component/instrument replaces them. Gross limits count each
    component exposure before account-level netting. Any shared-risk breach gates
    the entire candidate batch; no implicit pro-rata scaling is performed.
    """

    policy = portfolio.shared_risk_policy
    if not isinstance(policy, SharedRiskPolicy):
        raise TypeError("portfolio must contain a typed SharedRiskPolicy")
    if exposure_snapshot.portfolio_fingerprint != portfolio.fingerprint:
        raise ValueError("exposure snapshot does not belong to this portfolio version")
    if exposure_snapshot.base_currency != portfolio.base_currency:
        raise ValueError("exposure snapshot base currency does not match the portfolio")

    components = {item.component_id: item for item in portfolio.components}
    allowed_risk_models = {item.product_class: item for item in policy.risk_models}
    snapshot_risk_models = {
        item.instrument_id: item.risk_model for item in exposure_snapshot.instrument_risk_models
    }
    current: dict[tuple[str, str], Decimal] = {}
    for position in exposure_snapshot.positions:
        component = components.get(position.component_id)
        if component is None:
            raise ValueError(f"unknown position component {position.component_id!r}")
        if position.instrument_id not in component.instrument_ids:
            raise ValueError(
                f"component {position.component_id!r} holds undeclared instrument "
                f"{position.instrument_id!r}"
            )
        exposure_fraction = position.signed_base_risk_exposure / exposure_snapshot.account_equity
        if exposure_fraction != 0:
            current[(position.component_id, position.instrument_id)] = exposure_fraction

    request_list = tuple(requests)
    if any(not isinstance(item, ComponentTargetRequest) for item in request_list):
        raise TypeError("requests must contain ComponentTargetRequest values")
    if any(
        item.event_time != exposure_snapshot.event_time
        or item.event_sequence != exposure_snapshot.event_sequence
        for item in request_list
    ):
        raise ValueError("all target requests must match the exposure snapshot event")

    by_instrument: dict[str, list[ComponentTargetRequest]] = defaultdict(list)
    request_keys: set[tuple[str, str]] = set()
    for request in request_list:
        component = components.get(request.component_id)
        if component is None:
            raise ValueError(f"unknown target component {request.component_id!r}")
        if request.instrument_id not in component.instrument_ids:
            raise ValueError(
                f"component {request.component_id!r} targets undeclared instrument "
                f"{request.instrument_id!r}"
            )
        key = (request.component_id, request.instrument_id)
        if key in request_keys:
            raise ValueError("a component may target each instrument only once per event")
        request_keys.add(key)
        by_instrument[request.instrument_id].append(request)

    required_instruments = {
        instrument_id for _, instrument_id in current
    } | {request.instrument_id for request in request_list}
    for instrument_id in sorted(required_instruments):
        risk_model = snapshot_risk_models.get(instrument_id)
        if risk_model is None:
            raise ValueError(f"instrument {instrument_id!r} has no risk-model evidence")
        if risk_model not in SUPPORTED_PRODUCT_RISK_MODELS:
            raise ValueError(
                f"instrument {instrument_id!r} uses an unsupported product risk model"
            )
        if allowed_risk_models.get(risk_model.product_class) != risk_model:
            raise ValueError(
                f"instrument {instrument_id!r} risk model is not allowed by the portfolio policy"
            )

    rejected: list[TargetRejection] = []
    resolved: dict[tuple[str, str], Decimal] = dict(current)
    selected_target_keys: set[tuple[str, str]] = set()
    for instrument_id in sorted(by_instrument):
        instrument_requests = sorted(by_instrument[instrument_id], key=lambda item: item.component_id)
        if len(instrument_requests) > 1 and policy.target_conflict_policy is TargetConflictPolicy.REJECT:
            rejected.extend(
                TargetRejection(item.component_id, instrument_id, AllocationRejectionCode.TARGET_CONFLICT)
                for item in instrument_requests
            )
            continue
        if (
            len(instrument_requests) > 1
            and policy.target_conflict_policy is TargetConflictPolicy.HIGHEST_PRIORITY
        ):
            highest_priority = max(components[item.component_id].priority for item in instrument_requests)
            winners = [
                item
                for item in instrument_requests
                if components[item.component_id].priority == highest_priority
            ]
            if len(winners) != 1:
                rejected.extend(
                    TargetRejection(item.component_id, instrument_id, AllocationRejectionCode.PRIORITY_TIE)
                    for item in instrument_requests
                )
                continue
            selected = winners
            rejected.extend(
                TargetRejection(item.component_id, instrument_id, AllocationRejectionCode.LOWER_PRIORITY)
                for item in instrument_requests
                if item is not winners[0]
            )
        else:
            selected = instrument_requests

        for request in selected:
            component = components[request.component_id]
            resolved[(request.component_id, instrument_id)] = (
                component.capital_weight
                * request.target_fraction_of_component_budget
            )
            selected_target_keys.add((request.component_id, instrument_id))

    policy_breaches = _risk_breaches(resolved, policy, components)
    component_exposures = tuple(
        ComponentTargetExposure(component_id, instrument_id, fraction)
        for (component_id, instrument_id), fraction in sorted(resolved.items())
        if fraction != 0 or (component_id, instrument_id) in selected_target_keys
    )
    instrument_fractions: dict[str, Decimal] = defaultdict(Decimal)
    instrument_gross: dict[str, Decimal] = defaultdict(Decimal)
    component_gross: dict[str, Decimal] = defaultdict(Decimal)
    explicitly_targeted_instruments = {
        instrument_id for _, instrument_id in selected_target_keys
    }
    for exposure in component_exposures:
        instrument_fractions[exposure.instrument_id] += exposure.target_fraction_of_equity
        instrument_gross[exposure.instrument_id] += abs(exposure.target_fraction_of_equity)
        component_gross[exposure.component_id] += abs(exposure.target_fraction_of_equity)
    proposed_targets = tuple(
        InstrumentTargetExposure(
            instrument_id=instrument_id,
            target_fraction_of_equity=fraction,
            target_signed_base_notional=fraction * exposure_snapshot.account_equity,
        )
        for instrument_id, fraction in sorted(instrument_fractions.items())
        if instrument_gross[instrument_id] > 0
        or instrument_id in explicitly_targeted_instruments
    )
    gross_fraction = sum((abs(value) for value in resolved.values()), Decimal(0))
    net_fraction = sum(resolved.values(), Decimal(0))
    max_instrument = max(instrument_gross.values(), default=Decimal(0))
    max_component = max(component_gross.values(), default=Decimal(0))
    risk_limits_satisfied = not policy_breaches
    return AllocationDecision(
        definition_version=ALLOCATION_DEFINITION_VERSION,
        portfolio_fingerprint=portfolio.fingerprint,
        exposure_snapshot_fingerprint=exposure_snapshot.fingerprint,
        policy_fingerprint=policy.fingerprint,
        event_time=exposure_snapshot.event_time,
        event_sequence=exposure_snapshot.event_sequence,
        risk_limits_satisfied=risk_limits_satisfied,
        proposed_component_exposures=component_exposures,
        proposed_instrument_targets=proposed_targets,
        risk_approved_instrument_targets=proposed_targets if risk_limits_satisfied else (),
        rejected_targets=tuple(
            sorted(rejected, key=lambda item: (item.instrument_id, item.component_id, item.code.value))
        ),
        risk_breaches=policy_breaches,
        gross_exposure_fraction=gross_fraction,
        net_exposure_fraction=net_fraction,
        max_instrument_gross_exposure_fraction=max_instrument,
        max_component_gross_exposure_fraction=max_component,
        open_instrument_count=sum(value > 0 for value in instrument_gross.values()),
    )


def _risk_breaches(
    exposures: Mapping[tuple[str, str], Decimal],
    policy: SharedRiskPolicy,
    components: Mapping[str, PortfolioComponent],
) -> tuple[RiskBreach, ...]:
    gross = sum((abs(value) for value in exposures.values()), Decimal(0))
    net = sum(exposures.values(), Decimal(0))
    instrument_gross: dict[str, Decimal] = defaultdict(Decimal)
    component_gross: dict[str, Decimal] = defaultdict(Decimal)
    for (component_id, instrument_id), value in exposures.items():
        if value == 0:
            continue
        instrument_gross[instrument_id] += abs(value)
        component_gross[component_id] += abs(value)

    breaches: list[RiskBreach] = []
    if gross > policy.max_gross_exposure_fraction:
        breaches.append(RiskBreach.GROSS_EXPOSURE)
    if abs(net) > policy.max_net_exposure_fraction:
        breaches.append(RiskBreach.NET_EXPOSURE)
    if any(value > policy.max_instrument_gross_exposure_fraction for value in instrument_gross.values()):
        breaches.append(RiskBreach.INSTRUMENT_CONCENTRATION)
    if any(value > policy.max_component_gross_exposure_fraction for value in component_gross.values()):
        breaches.append(RiskBreach.COMPONENT_CONCENTRATION)
    if any(
        value > components[component_id].capital_weight * policy.max_component_leverage
        for component_id, value in component_gross.items()
    ):
        breaches.append(RiskBreach.COMPONENT_LEVERAGE)
    if (
        policy.max_open_instruments is not None
        and len(instrument_gross) > policy.max_open_instruments
    ):
        breaches.append(RiskBreach.OPEN_INSTRUMENT_COUNT)
    if not policy.allow_short_positions and any(value < 0 for value in exposures.values()):
        breaches.append(RiskBreach.SHORT_POSITION)
    return tuple(breaches)
