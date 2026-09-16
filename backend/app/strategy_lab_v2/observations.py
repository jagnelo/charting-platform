"""Typed, provenance-bound engine result observations.

These records carry normalized base-currency values from an authoritative
engine adapter. They do not perform FX conversion, infer execution costs, or
derive component P&L from position changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.decimal_math import deterministic_decimal_math

UNALLOCATED_COMPONENT_ID = "__unallocated__"


def _currency_code(value: str, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ValueError(f"{field_name} must be a three-letter currency code")
    return value.upper()


@dataclass(frozen=True, slots=True, order=True)
class ObservationPoint:
    """A normalized engine event instant and its stable within-instant order."""

    event_time: datetime
    event_sequence: int

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))


class ExecutionCostKind(StrEnum):
    COMMISSION = "commission"
    EXCHANGE_FEE = "exchange_fee"
    TAX = "tax"
    SLIPPAGE = "slippage"
    REBATE = "rebate"
    OTHER = "other"


class CostReportStatus(StrEnum):
    """Completeness of the engine's reported fill-cost components."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ExternalCashFlowReportStatus(StrEnum):
    """Completeness of native account external-cash-flow reporting."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True, order=True)
class ExternalCashFlowBoundaryObservation:
    """Authoritative pre/post marks bracketing one external cash-flow event.

    A boundary is deliberately separate from the interval's net flow report:
    time-weighted returns need a valuation immediately before and after every
    event so the cash jump can be excluded from the linked return factors.
    ``post_flow_equity - pre_flow_equity`` must equal the reported event amount.
    The parent account interval binds the boundary to its portfolio, run,
    currency, and interior event range.
    """

    point: ObservationPoint
    pre_flow_equity: Decimal
    post_flow_equity: Decimal
    external_cash_flow: Decimal
    engine_evidence_digest: str

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        if not isinstance(self.point, ObservationPoint):
            raise TypeError("point must be an ObservationPoint")
        for name in ("pre_flow_equity", "post_flow_equity", "external_cash_flow"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.pre_flow_equity <= 0:
            raise ValueError("pre_flow_equity must be positive")
        if self.post_flow_equity < 0:
            raise ValueError("post_flow_equity must be non-negative")
        if self.external_cash_flow == 0:
            raise ValueError("external_cash_flow boundary amounts must be non-zero")
        if self.post_flow_equity - self.pre_flow_equity != self.external_cash_flow:
            raise ValueError("post_flow_equity must equal pre_flow_equity plus external_cash_flow")
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")


@dataclass(frozen=True, slots=True)
class ExecutionCostComponent:
    """One engine-reported fill cash effect in native and account currency.

    Amounts use cash-flow signs: expenses are negative and credits/rebates are
    positive. Slippage may have either sign because execution can beat its
    explicit benchmark. The adapter supplies conversion evidence for foreign
    currency amounts; this domain type does not validate that evidence.
    """

    cost_component_id: str
    kind: ExecutionCostKind
    native_currency: str
    native_cash_effect: Decimal
    base_currency: str
    base_cash_effect: Decimal
    cost_model_digest: str
    evidence_digest: str
    fx_conversion_evidence_digest: str | None = None
    benchmark_definition_digest: str | None = None

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        if not self.cost_component_id.strip():
            raise ValueError("cost_component_id must not be empty")
        if not isinstance(self.kind, ExecutionCostKind):
            raise TypeError("kind must be an ExecutionCostKind")
        native_currency = _currency_code(self.native_currency, "native_currency")
        base_currency = _currency_code(self.base_currency, "base_currency")
        for name in ("native_cash_effect", "base_cash_effect"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        require_sha256_digest(self.cost_model_digest, field_name="cost_model_digest")
        require_sha256_digest(self.evidence_digest, field_name="evidence_digest")
        if native_currency == base_currency:
            if self.native_cash_effect != self.base_cash_effect:
                raise ValueError("same-currency native and base cash effects must match")
            if self.fx_conversion_evidence_digest is not None:
                raise ValueError("same-currency cost must not declare FX conversion evidence")
        else:
            if self.fx_conversion_evidence_digest is None:
                raise ValueError("foreign-currency cost requires FX conversion evidence")
            require_sha256_digest(
                self.fx_conversion_evidence_digest,
                field_name="fx_conversion_evidence_digest",
            )
        if (
            self.native_cash_effect < 0 < self.base_cash_effect
            or self.native_cash_effect > 0 > self.base_cash_effect
        ):
            raise ValueError("currency conversion must preserve the cash-effect sign")
        if (self.native_cash_effect == 0) != (self.base_cash_effect == 0):
            raise ValueError("currency conversion must preserve zero versus non-zero cash effects")
        if self.kind is ExecutionCostKind.REBATE:
            if self.native_cash_effect < 0 or self.base_cash_effect < 0:
                raise ValueError("rebate cash effects must be non-negative")
        elif self.kind is not ExecutionCostKind.SLIPPAGE:
            if self.native_cash_effect > 0 or self.base_cash_effect > 0:
                raise ValueError("expense cash effects must be non-positive")
        if self.kind is ExecutionCostKind.SLIPPAGE:
            require_sha256_digest(
                self.benchmark_definition_digest or "",
                field_name="benchmark_definition_digest",
            )
        elif self.benchmark_definition_digest is not None:
            raise ValueError("only slippage may declare a benchmark definition")
        object.__setattr__(self, "native_currency", native_currency)
        object.__setattr__(self, "base_currency", base_currency)


@dataclass(frozen=True, slots=True)
class FillCostObservation:
    """One native engine fill with authoritative notional and reported costs."""

    portfolio_fingerprint: str
    run_attempt_id: str
    point: ObservationPoint
    fill_id: str
    component_id: str
    instrument_id: str
    traded_base_notional: Decimal
    base_currency: str
    engine_evidence_digest: str
    cost_report_status: CostReportStatus
    costs: tuple[ExecutionCostComponent, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        if not isinstance(self.point, ObservationPoint):
            raise TypeError("point must be an ObservationPoint")
        for name in ("fill_id", "component_id", "instrument_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if (
            not isinstance(self.traded_base_notional, Decimal)
            or not self.traded_base_notional.is_finite()
            or self.traded_base_notional <= 0
        ):
            raise ValueError("traded_base_notional must be a finite positive Decimal")
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")
        if not isinstance(self.cost_report_status, CostReportStatus):
            raise TypeError("cost_report_status must be a CostReportStatus")
        base_currency = _currency_code(self.base_currency, "base_currency")
        costs = tuple(self.costs)
        if any(not isinstance(item, ExecutionCostComponent) for item in costs):
            raise TypeError("costs must contain ExecutionCostComponent values")
        if any(item.base_currency != base_currency for item in costs):
            raise ValueError("fill costs must use the fill's account base currency")
        if self.cost_report_status is CostReportStatus.UNAVAILABLE and costs:
            raise ValueError("unavailable cost reports must not include cost components")
        identifiers = [item.cost_component_id for item in costs]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("cost component ids must be unique within a fill")
        object.__setattr__(self, "base_currency", base_currency)
        object.__setattr__(
            self,
            "costs",
            tuple(sorted(costs, key=lambda item: item.cost_component_id)),
        )


@dataclass(frozen=True, slots=True, order=True)
class FinancingCostObservation:
    """One engine-reported financing cash effect outside a fill report."""

    portfolio_fingerprint: str
    run_attempt_id: str
    point: ObservationPoint
    financing_event_id: str
    base_cash_effect: Decimal
    base_currency: str
    financing_model_digest: str
    engine_evidence_digest: str

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        if not isinstance(self.point, ObservationPoint):
            raise TypeError("point must be an ObservationPoint")
        if not isinstance(self.financing_event_id, str) or not self.financing_event_id.strip():
            raise ValueError("financing_event_id must not be empty")
        if not isinstance(self.base_cash_effect, Decimal) or not self.base_cash_effect.is_finite():
            raise ValueError("base_cash_effect must be a finite Decimal")
        object.__setattr__(self, "base_currency", _currency_code(self.base_currency, "base_currency"))
        require_sha256_digest(self.financing_model_digest, field_name="financing_model_digest")
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")


@dataclass(frozen=True, slots=True)
class FinancingCostReport:
    """A bounded engine financing report with explicit completeness status."""

    portfolio_fingerprint: str
    run_attempt_id: str
    start_point: ObservationPoint
    end_point: ObservationPoint
    base_currency: str
    report_status: CostReportStatus
    engine_evidence_digest: str
    observations: tuple[FinancingCostObservation, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        if not isinstance(self.start_point, ObservationPoint):
            raise TypeError("start_point must be an ObservationPoint")
        if not isinstance(self.end_point, ObservationPoint):
            raise TypeError("end_point must be an ObservationPoint")
        if self.end_point <= self.start_point:
            raise ValueError("financing report end_point must be after start_point")
        object.__setattr__(self, "base_currency", _currency_code(self.base_currency, "base_currency"))
        if not isinstance(self.report_status, CostReportStatus):
            raise TypeError("report_status must be a CostReportStatus")
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")
        observations = tuple(self.observations)
        if any(not isinstance(item, FinancingCostObservation) for item in observations):
            raise TypeError("observations must contain FinancingCostObservation values")
        if any(item.portfolio_fingerprint != self.portfolio_fingerprint for item in observations):
            raise ValueError("financing observations must use the report's portfolio version")
        if any(item.run_attempt_id != self.run_attempt_id for item in observations):
            raise ValueError("financing observations must use the report's run attempt")
        if any(item.base_currency != self.base_currency for item in observations):
            raise ValueError("financing observations must use the report's base currency")
        if any(item.point < self.start_point or item.point > self.end_point for item in observations):
            raise ValueError("financing observations must fall within the report interval")
        event_ids = [item.financing_event_id for item in observations]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("financing event ids must be unique within a report")
        if self.report_status is CostReportStatus.UNAVAILABLE and observations:
            raise ValueError("unavailable financing reports must not include observations")
        object.__setattr__(self, "observations", tuple(sorted(observations, key=lambda item: item.point)))


@dataclass(frozen=True, slots=True)
class AccountCapitalMarginObservation:
    """One engine-reported capital and margin capacity valuation.

    Requirement and capacity values are supplied by the account/product
    adapter. The metrics layer never estimates margin from notional exposure;
    capacities may therefore represent portfolio rules, broker buying power, or
    a product-specific clearing model without changing the contract.
    """

    portfolio_fingerprint: str
    run_attempt_id: str
    point: ObservationPoint
    account_equity: Decimal
    initial_margin_requirement: Decimal
    maintenance_margin_requirement: Decimal
    initial_margin_capacity: Decimal
    maintenance_margin_capacity: Decimal
    base_currency: str
    valuation_evidence_digest: str

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        if not isinstance(self.point, ObservationPoint):
            raise TypeError("point must be an ObservationPoint")
        for name in (
            "account_equity",
            "initial_margin_requirement",
            "maintenance_margin_requirement",
            "initial_margin_capacity",
            "maintenance_margin_capacity",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.account_equity <= 0:
            raise ValueError("account_equity must be positive")
        if self.initial_margin_requirement < 0 or self.maintenance_margin_requirement < 0:
            raise ValueError("margin requirements must be non-negative")
        if self.initial_margin_capacity <= 0 or self.maintenance_margin_capacity <= 0:
            raise ValueError("margin capacities must be positive")
        object.__setattr__(self, "base_currency", _currency_code(self.base_currency, "base_currency"))
        require_sha256_digest(self.valuation_evidence_digest, field_name="valuation_evidence_digest")


@dataclass(frozen=True, slots=True)
class AccountEquityIntervalObservation:
    """One engine-reported prior-mark-to-session-close account interval.

    External cash flow uses account-cash signs: deposits are positive and
    withdrawals negative. A complete report must provide an authoritative net
    amount, including explicit zero, and state whether any flow events occurred;
    this distinguishes a verified no-flow interval from offsetting flows whose
    net amount is zero. Partial reports may provide a known subtotal and positive
    occurrence evidence, while unavailable reports provide neither. Net P&L is
    trusted only for complete reports. Return calculations with external flows
    require explicit pre/post boundary valuations in the time-weighted return
    calculator.
    """

    portfolio_fingerprint: str
    run_attempt_id: str
    calendar_fingerprint: str
    session_label: date
    start_point: ObservationPoint
    end_point: ObservationPoint
    starting_equity: Decimal
    ending_equity: Decimal
    external_cash_flow: Decimal | None
    external_cash_flow_occurred: bool | None
    external_cash_flow_report_status: ExternalCashFlowReportStatus
    base_currency: str
    engine_evidence_digest: str
    external_cash_flow_boundaries: tuple[ExternalCashFlowBoundaryObservation, ...] = ()

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        require_sha256_digest(self.calendar_fingerprint, field_name="calendar_fingerprint")
        if type(self.session_label) is not date:
            raise TypeError("session_label must be a date, not a datetime")
        if not isinstance(self.start_point, ObservationPoint):
            raise TypeError("start_point must be an ObservationPoint")
        if not isinstance(self.end_point, ObservationPoint):
            raise TypeError("end_point must be an ObservationPoint")
        if self.end_point <= self.start_point:
            raise ValueError("equity interval end_point must follow start_point")
        for name in ("starting_equity", "ending_equity"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.external_cash_flow is not None and (
            not isinstance(self.external_cash_flow, Decimal)
            or not self.external_cash_flow.is_finite()
        ):
            raise ValueError("external_cash_flow must be a finite Decimal or None")
        if not isinstance(
            self.external_cash_flow_report_status, ExternalCashFlowReportStatus
        ):
            raise TypeError(
                "external_cash_flow_report_status must be an ExternalCashFlowReportStatus"
            )
        if self.external_cash_flow_occurred is not None and not isinstance(
            self.external_cash_flow_occurred, bool
        ):
            raise TypeError("external_cash_flow_occurred must be a bool or None")
        if (
            self.external_cash_flow_report_status is ExternalCashFlowReportStatus.COMPLETE
            and self.external_cash_flow is None
        ):
            raise ValueError("complete external cash-flow reports must include an amount")
        if (
            self.external_cash_flow_report_status is ExternalCashFlowReportStatus.COMPLETE
            and self.external_cash_flow_occurred is None
        ):
            raise ValueError(
                "complete external cash-flow reports must state whether flows occurred"
            )
        if (
            self.external_cash_flow is not None
            and self.external_cash_flow != 0
            and self.external_cash_flow_occurred is not True
        ):
            raise ValueError("a nonzero external cash flow requires flow-occurrence evidence")
        if (
            self.external_cash_flow_report_status is ExternalCashFlowReportStatus.PARTIAL
            and self.external_cash_flow_occurred is False
        ):
            raise ValueError("partial external cash-flow reports cannot prove that no flows occurred")
        if (
            self.external_cash_flow_report_status is ExternalCashFlowReportStatus.UNAVAILABLE
            and (self.external_cash_flow is not None or self.external_cash_flow_occurred is not None)
        ):
            raise ValueError("unavailable external cash-flow reports must not include flow evidence")
        if self.starting_equity <= 0 or self.ending_equity < 0:
            raise ValueError("starting_equity must be positive and ending_equity non-negative")
        object.__setattr__(
            self, "base_currency", _currency_code(self.base_currency, "base_currency")
        )
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")
        boundaries = tuple(self.external_cash_flow_boundaries)
        if any(not isinstance(item, ExternalCashFlowBoundaryObservation) for item in boundaries):
            raise TypeError(
                "external_cash_flow_boundaries must contain ExternalCashFlowBoundaryObservation values"
            )
        if tuple(sorted(boundaries, key=lambda item: item.point)) != boundaries:
            raise ValueError("external cash-flow boundaries must be strictly ordered")
        if len({item.point for item in boundaries}) != len(boundaries):
            raise ValueError("external cash-flow boundaries must have unique points")
        if any(
            item.point <= self.start_point or item.point >= self.end_point for item in boundaries
        ):
            raise ValueError(
                "external cash-flow boundaries must fall strictly inside the account interval"
            )
        if boundaries and self.external_cash_flow_occurred is not True:
            raise ValueError("external cash-flow boundaries require occurrence evidence")
        if boundaries and self.external_cash_flow is not None:
            boundary_total = sum(
                (item.external_cash_flow for item in boundaries),
                Decimal(0),
            )
            if boundary_total != self.external_cash_flow:
                raise ValueError(
                    "external cash-flow boundaries must reconcile the interval flow amount"
                )
        object.__setattr__(self, "external_cash_flow_boundaries", boundaries)


@dataclass(frozen=True, slots=True)
class PortfolioPnlObservation:
    """Authoritative run-level account P&L at a result event point."""

    portfolio_fingerprint: str
    run_attempt_id: str
    point: ObservationPoint
    gross_pnl: Decimal
    net_pnl: Decimal
    base_currency: str
    component_ids: tuple[str, ...]
    result_bundle_digest: str
    engine_evidence_digest: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        if not isinstance(self.point, ObservationPoint):
            raise TypeError("point must be an ObservationPoint")
        for name in ("gross_pnl", "net_pnl"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        object.__setattr__(self, "base_currency", _currency_code(self.base_currency, "base_currency"))
        component_ids = tuple(self.component_ids)
        if not component_ids or any(
            not isinstance(value, str)
            or not value.strip()
            or value == UNALLOCATED_COMPONENT_ID
            for value in component_ids
        ):
            raise ValueError("component_ids must list declared portfolio components")
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("portfolio component_ids must be unique")
        object.__setattr__(self, "component_ids", tuple(sorted(component_ids)))
        require_sha256_digest(self.result_bundle_digest, field_name="result_bundle_digest")
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")


@dataclass(frozen=True, slots=True)
class ComponentPnlObservation:
    """Engine-reported run P&L assigned to one component or unallocated residual."""

    portfolio_fingerprint: str
    run_attempt_id: str
    point: ObservationPoint
    component_id: str
    gross_pnl: Decimal
    cost_deductions: Decimal
    rebates: Decimal
    net_pnl: Decimal
    base_currency: str
    result_bundle_digest: str
    attribution_method_digest: str
    engine_evidence_digest: str

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.run_attempt_id, str) or not self.run_attempt_id.strip():
            raise ValueError("run_attempt_id must not be empty")
        if not isinstance(self.point, ObservationPoint):
            raise TypeError("point must be an ObservationPoint")
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty; use the unallocated sentinel explicitly")
        for name in ("gross_pnl", "cost_deductions", "rebates", "net_pnl"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.cost_deductions < 0 or self.rebates < 0:
            raise ValueError("cost deductions and rebates must be non-negative")
        if self.net_pnl != self.gross_pnl - self.cost_deductions + self.rebates:
            raise ValueError("net_pnl must equal gross_pnl less costs plus rebates")
        object.__setattr__(self, "base_currency", _currency_code(self.base_currency, "base_currency"))
        require_sha256_digest(self.result_bundle_digest, field_name="result_bundle_digest")
        require_sha256_digest(
            self.attribution_method_digest,
            field_name="attribution_method_digest",
        )
        require_sha256_digest(self.engine_evidence_digest, field_name="engine_evidence_digest")
