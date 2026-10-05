"""Exact isolated Nautilus v2 release-candidate runtime declarations.

The application backend intentionally keeps the legacy Nautilus 1.x dependency
in its own environment.  This module gives an adapter a typed, immutable
declaration for the current v2 RC compatibility runtime without importing
Nautilus, discovering packages, or starting a process.  The adapter must still
provide content digests for the source checkout and runtime image after it has
resolved/builds those artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_RELEASE_PIN_VERSION,
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    NAUTILUS_V2_RC_WHEEL_SHA256,
    ConformanceCheck,
    EngineReleaseChannel,
    NautilusReleasePin,
)
from app.strategy_lab_v2.nautilus_event_adapter import NautilusForwardEventParityReceipt


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _decimal(value: Any, field_name: str) -> Decimal:
    """Parse one finite fixture decimal, accepting Nautilus money display text."""

    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise TypeError(f"{field_name} must be a decimal-compatible scalar")
    try:
        parsed = Decimal(str(value).split()[0])
    except (InvalidOperation, IndexError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _decimal_strings(value: Any, field_name: str) -> tuple[Decimal, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    return tuple(_decimal(item, field_name) for item in value)


def _money_strings(value: Any, field_name: str, currency: str) -> tuple[Decimal, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    amounts: list[Decimal] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be native money report strings")
        parts = item.split()
        if len(parts) != 2 or parts[1] != currency:
            raise ValueError(f"{field_name} entries must use the expected {currency} currency")
        amounts.append(_decimal(parts[0], field_name))
    return tuple(amounts)


def _require_native_accounting_run(run: Any) -> None:
    if not isinstance(run, Mapping):
        raise ValueError("native accounting fixture must be a mapping")
    instrument_count = run.get("instrument_count")
    if (
        not isinstance(instrument_count, int)
        or isinstance(instrument_count, bool)
        or instrument_count < 1
    ):
        raise ValueError("native accounting fixture must identify its instrument count")
    if (
        run.get("total_orders") != instrument_count
        or run.get("total_positions") != instrument_count
        or _decimal(run.get("orders_total"), "orders_total") != instrument_count
        or _decimal(run.get("positions_total"), "positions_total") != instrument_count
    ):
        raise ValueError("native orders and positions must reconcile per instrument")

    reports = run.get("native_reports")
    report_fields = {
        "commission_total",
        "commissions",
        "expected_commission_per_fill",
        "expected_quantity_per_instrument",
        "expected_quantity_total",
        "execution_prices",
        "fee_currency",
        "fill_instrument_ids",
        "fill_quantities",
        "filled_quantity",
        "fills_report_rows",
        "initial_account_total",
        "best_ask",
        "orders_report_rows",
        "price_increment",
        "total_fills",
    }
    if not isinstance(reports, Mapping) or set(reports) != report_fields:
        raise ValueError("native fill/cost fixture must include exact native report evidence")

    total_fills = reports["total_fills"]
    fill_quantities = _decimal_strings(reports["fill_quantities"], "fill_quantities")
    execution_prices = _decimal_strings(reports["execution_prices"], "execution_prices")
    commissions = _money_strings(reports["commissions"], "commissions", reports["fee_currency"])
    instrument_ids = reports["fill_instrument_ids"]
    if (
        not isinstance(total_fills, int)
        or isinstance(total_fills, bool)
        or total_fills != instrument_count
        or reports["fills_report_rows"] != total_fills
        or len(fill_quantities) != total_fills
        or len(execution_prices) != total_fills
        or len(commissions) != total_fills
        or not isinstance(instrument_ids, list)
        or len(instrument_ids) != total_fills
        or len(set(instrument_ids)) != instrument_count
        or reports["orders_report_rows"] != run["total_orders"]
    ):
        raise ValueError("native order and fill report rows do not reconcile")

    expected_per_instrument = _decimal(
        reports["expected_quantity_per_instrument"], "expected_quantity_per_instrument"
    )
    expected_total_quantity = _decimal(
        reports["expected_quantity_total"], "expected_quantity_total"
    )
    filled_quantity = _decimal(reports["filled_quantity"], "filled_quantity")
    if (
        expected_per_instrument <= 0
        or expected_total_quantity != expected_per_instrument * instrument_count
        or filled_quantity != expected_total_quantity
        or sum(fill_quantities, Decimal(0)) != filled_quantity
        or any(quantity != expected_per_instrument for quantity in fill_quantities)
    ):
        raise ValueError("native fill report quantity does not reconcile per instrument")

    best_ask = _decimal(reports["best_ask"], "best_ask")
    price_increment = _decimal(reports["price_increment"], "price_increment")
    if price_increment <= 0 or any(
        execution_price != best_ask + price_increment for execution_price in execution_prices
    ):
        raise ValueError("native fill report did not apply the configured one-tick slippage")

    expected_commission = _decimal(
        reports["expected_commission_per_fill"], "expected_commission_per_fill"
    )
    commission_total = _decimal(reports["commission_total"], "commission_total")
    if (
        expected_commission <= 0
        or any(commission != expected_commission for commission in commissions)
        or sum(commissions, Decimal(0)) != commission_total
    ):
        raise ValueError("native fee report does not match the configured fixed fee")

    initial_account_total = _decimal(reports["initial_account_total"], "initial_account_total")
    account_total = _decimal(run.get("account_total"), "account_total")
    expected_account_total = (
        initial_account_total
        - sum(
            (quantity * price for quantity, price in zip(fill_quantities, execution_prices)),
            Decimal(0),
        )
        - commission_total
    )
    if account_total != expected_account_total:
        raise ValueError("native account report does not reconcile fills and commissions")


def _require_target_allocation_probe(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "instrument_id",
        "requested_target_fraction",
        "total_orders",
        "total_positions",
        "initial_cash",
        "remaining_cash",
        "observed_deployment",
        "account_base_currency",
        "authoritative",
    }:
        raise ValueError("native target-allocation probe fields are invalid")
    initial_cash = _decimal(value["initial_cash"], "target probe initial_cash")
    remaining_cash = _decimal(value["remaining_cash"], "target probe remaining_cash")
    observed_deployment = _decimal(value["observed_deployment"], "target probe observed_deployment")
    if (
        value["instrument_id"] != "AAPL.SIM"
        or value["requested_target_fraction"] != "0.5"
        or value["account_base_currency"] != "USD"
        or value["total_orders"] != 1
        or value["total_positions"] != 1
        or value["authoritative"] is not False
        or initial_cash != Decimal("100000")
        or not Decimal("45000") < remaining_cash < Decimal("55000")
        or observed_deployment != initial_cash - remaining_cash
    ):
        raise ValueError("native target allocation order and account state do not reconcile")


def _require_raw_order_risk_probe(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "instrument_id",
        "requested_order_quantity",
        "estimated_signed_base_notional",
        "total_orders",
        "total_positions",
        "initial_cash",
        "remaining_cash",
        "observed_deployment",
        "account_base_currency",
        "authoritative",
    }:
        raise ValueError("native raw-order risk probe fields are invalid")
    initial_cash = _decimal(value["initial_cash"], "raw-order probe initial_cash")
    remaining_cash = _decimal(value["remaining_cash"], "raw-order probe remaining_cash")
    deployment = _decimal(value["observed_deployment"], "raw-order probe deployment")
    if (
        value["instrument_id"] != "AAPL.SIM"
        or value["requested_order_quantity"] != "100"
        or _decimal(value["estimated_signed_base_notional"], "raw-order estimated notional")
        != Decimal("10001")
        or value["account_base_currency"] != "USD"
        or value["total_orders"] != 1
        or value["total_positions"] != 1
        or value["authoritative"] is not False
        or initial_cash != Decimal("100000")
        or not Decimal("89000") < remaining_cash < Decimal("91000")
        or deployment != initial_cash - remaining_cash
    ):
        raise ValueError("native raw-order risk submission and account state do not reconcile")


def _require_native_component_pnl_probe(value: Any) -> None:
    fields = {
        "authoritative",
        "archived_snapshot_cycles",
        "base_currency",
        "closed_position_cycles",
        "component_gross_pnl",
        "component_id",
        "component_net_pnl",
        "component_order_count",
        "exact_account_reconciliation",
        "fill_count",
        "native_trade_id_join_count",
        "portfolio_gross_pnl",
        "portfolio_net_pnl",
        "reported_cost_deductions",
        "reported_rebates",
        "snapshot_index_differs_from_fill_position_id",
        "total_orders",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("native component P&L probe fields are invalid")
    count_fields = (
        "archived_snapshot_cycles",
        "closed_position_cycles",
        "component_order_count",
        "fill_count",
        "native_trade_id_join_count",
        "total_orders",
    )
    if any(
        not isinstance(value[name], int) or isinstance(value[name], bool) for name in count_fields
    ):
        raise ValueError("native component P&L identity counts must be integers")
    component_net = _decimal(value["component_net_pnl"], "component_net_pnl")
    component_gross = _decimal(value["component_gross_pnl"], "component_gross_pnl")
    portfolio_net = _decimal(value["portfolio_net_pnl"], "portfolio_net_pnl")
    portfolio_gross = _decimal(value["portfolio_gross_pnl"], "portfolio_gross_pnl")
    cost_deductions = _decimal(value["reported_cost_deductions"], "reported_cost_deductions")
    rebates = _decimal(value["reported_rebates"], "reported_rebates")
    if (
        value["authoritative"] is not False
        or value["component_id"] != "core"
        or value["base_currency"] != "USD"
        or value["exact_account_reconciliation"] is not True
        or value["snapshot_index_differs_from_fill_position_id"] is not True
        or value["archived_snapshot_cycles"] < 1
        or value["closed_position_cycles"] != 2
        or value["component_order_count"] != 4
        or value["fill_count"] != 4
        or value["native_trade_id_join_count"] != 4
        or value["total_orders"] != 4
        or cost_deductions < 0
        or rebates < 0
        or component_net != portfolio_net
        or component_gross != portfolio_gross
        or component_gross != component_net + cost_deductions - rebates
        or portfolio_gross != portfolio_net + cost_deductions - rebates
    ):
        raise ValueError("native archived-cycle component P&L does not reconcile to account")


def _require_native_signed_fee_reconciliation(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"authoritative", "positive_fee", "rebate"}
        or value["authoritative"] is not False
    ):
        raise ValueError("native signed fee reconciliation fields are invalid")
    positive_fee = value["positive_fee"]
    rebate = value["rebate"]
    _require_native_component_pnl_probe(positive_fee)
    _require_native_component_pnl_probe(rebate)
    positive_costs = _decimal(positive_fee["reported_cost_deductions"], "positive_fee.costs")
    positive_rebates = _decimal(positive_fee["reported_rebates"], "positive_fee.rebates")
    rebate_costs = _decimal(rebate["reported_cost_deductions"], "rebate.costs")
    rebate_amount = _decimal(rebate["reported_rebates"], "rebate.rebates")
    positive_gross = _decimal(positive_fee["portfolio_gross_pnl"], "positive_fee.gross")
    rebate_gross = _decimal(rebate["portfolio_gross_pnl"], "rebate.gross")
    positive_net = _decimal(positive_fee["portfolio_net_pnl"], "positive_fee.net")
    rebate_net = _decimal(rebate["portfolio_net_pnl"], "rebate.net")
    if (
        positive_costs <= 0
        or positive_rebates != 0
        or rebate_costs != 0
        or rebate_amount <= 0
        or positive_gross != rebate_gross
        or positive_net != positive_gross - positive_costs
        or rebate_net != rebate_gross + rebate_amount
    ):
        raise ValueError("native signed fee effects do not reconcile to gross/net account P&L")


def _require_forward_streaming_session(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {"equal", "first", "second"}:
        raise ValueError("forward streaming session evidence fields are invalid")
    first = value["first"]
    second = value["second"]
    if value["equal"] is not True or first != second:
        raise ValueError("forward streaming session replay was not deterministic")
    expected_fields = {
        "account_total",
        "authoritative",
        "batch_count",
        "batch_event_counts",
        "fill_count",
        "order_count",
        "position_count",
        "strategy_submitted_instrument_count",
    }
    for run in (first, second):
        if not isinstance(run, Mapping) or set(run) != expected_fields:
            raise ValueError("forward streaming run fields are invalid")
        account_total = _decimal(run["account_total"], "forward stream account total")
        if (
            run["authoritative"] is not False
            or run["batch_count"] != 2
            or run["batch_event_counts"] != [1, 1]
            or run["fill_count"] != 1
            or run["order_count"] != 1
            or run["position_count"] != 1
            or run["strategy_submitted_instrument_count"] != 1
            or account_total <= 0
        ):
            raise ValueError("forward streaming batches did not preserve native state")


def _require_rebalance_schedule_probe(value: Any) -> None:
    cases = {
        "session_open",
        "session_close",
        "multi_component_shared_account",
        "component_priority_contention",
        "shared_risk_rejection",
        "fail_on_misfire",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != {"authoritative", *cases}
        or value["authoritative"] is not False
    ):
        raise ValueError("native rebalance schedule probe fields are invalid")
    expected = {
        "session_open": ("orders_submitted", 1, 1, 1),
        "session_close": ("orders_submitted", 1, 1, 1),
        "multi_component_shared_account": ("orders_submitted", 2, 2, 1),
        "component_priority_contention": ("orders_submitted", 1, 1, 1),
        "fail_on_misfire": ("failed_misfire", 0, 0, 0),
    }
    for case_name, (status, count, orders, positions) in expected.items():
        case = value[case_name]
        expected_fields = {
            "audit_fingerprint",
            "execution_status",
            "submitted_order_count",
            "total_orders",
            "total_positions",
            "authoritative",
        }
        if case_name == "multi_component_shared_account":
            expected_fields.add("remaining_cash")
        if case_name == "component_priority_contention":
            expected_fields.update(
                {"remaining_cash", "component_order_tag", "component_fill_attribution"}
            )
        if not isinstance(case, Mapping) or set(case) != expected_fields:
            raise ValueError(f"native {case_name} schedule evidence fields are invalid")
        require_sha256_digest(
            case["audit_fingerprint"],
            field_name=f"{case_name}.audit_fingerprint",
        )
        if (
            case["execution_status"] != status
            or case["submitted_order_count"] != count
            or case["total_orders"] != orders
            or case["total_positions"] != positions
            or case["authoritative"] is not False
        ):
            raise ValueError(f"native {case_name} schedule callbacks did not reconcile")
        if case_name == "multi_component_shared_account":
            remaining_cash = _decimal(case["remaining_cash"], "remaining_cash")
            if not Decimal("40000") < remaining_cash < Decimal("60000"):
                raise ValueError("native multi-component targets did not share the account budget")
        if case_name == "component_priority_contention":
            remaining_cash = _decimal(case["remaining_cash"], "remaining_cash")
            if (
                not Decimal("88000") < remaining_cash < Decimal("92000")
                or case["component_order_tag"] != "strategy-lab-v2:component:satellite"
            ):
                raise ValueError("native priority selection or component attribution differs")
            fill = case["component_fill_attribution"]
            if not isinstance(fill, Mapping) or set(fill) != {
                "component_id",
                "venue_order_id",
                "instrument_id",
                "quantity",
                "execution_price",
                "commission",
                "currency",
            }:
                raise ValueError("native component fill attribution fields are invalid")
            quantity = _decimal(fill["quantity"], "component fill quantity")
            execution_price = _decimal(fill["execution_price"], "component fill execution price")
            commission = fill["commission"]
            if (
                fill["component_id"] != "satellite"
                or not isinstance(fill["venue_order_id"], str)
                or not fill["venue_order_id"].strip()
                or not isinstance(fill["instrument_id"], str)
                or not fill["instrument_id"].strip()
                or quantity <= 0
                or execution_price <= 0
                or not isinstance(commission, str)
                or len(commission.split()) != 2
                or commission.split()[1] != fill["currency"]
                or fill["currency"] != "USD"
                or _decimal(commission, "component fill commission") < 0
            ):
                raise ValueError("native component fill attribution does not reconcile")

    risk_rejection = value["shared_risk_rejection"]
    if not isinstance(risk_rejection, Mapping) or set(risk_rejection) != {
        "risk_rejected",
        "risk_gate",
        "submission_prevented",
        "total_orders",
        "total_positions",
        "authoritative",
    }:
        raise ValueError("native shared-risk rejection evidence fields are invalid")
    if (
        risk_rejection["risk_rejected"] is not True
        or risk_rejection["risk_gate"] != "shared_portfolio"
        or risk_rejection["submission_prevented"] is not True
        or risk_rejection["total_orders"] != 0
        or risk_rejection["total_positions"] != 0
        or risk_rejection["authoritative"] is not False
    ):
        raise ValueError("native shared-risk gate did not prevent over-limit orders")


@dataclass(frozen=True, slots=True)
class NautilusRcCompatibilityRuntime:
    """One exact v2 RC runtime boundary.

    The package/tag are deliberately not caller-selectable: changing either
    value creates a different release track and requires a new reviewed
    contract. The exact package-wheel digest is pinned alongside source/image
    digests supplied by the image/build adapter.
    """

    source_digest: str
    runtime_image_digest: str
    python_version: str
    rust_version: str
    wheel_digest: str = NAUTILUS_V2_RC_WHEEL_SHA256
    legacy_runtime_isolated: bool = True
    contract_version: str = NAUTILUS_RELEASE_PIN_VERSION

    def __post_init__(self) -> None:
        require_sha256_digest(self.source_digest, field_name="source_digest")
        require_sha256_digest(self.runtime_image_digest, field_name="runtime_image_digest")
        require_sha256_digest(self.wheel_digest, field_name="wheel_digest")
        if self.wheel_digest != NAUTILUS_V2_RC_WHEEL_SHA256:
            raise ValueError("the exact Nautilus RC5 wheel digest cannot be overridden")
        for name in ("python_version", "rust_version", "contract_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.legacy_runtime_isolated, bool):
            raise TypeError("legacy_runtime_isolated must be a boolean")
        if not self.legacy_runtime_isolated:
            raise ValueError("the v2 RC runtime must be isolated from the legacy runtime")

    @property
    def package_version(self) -> str:
        return NAUTILUS_V2_RC_PACKAGE_VERSION

    @property
    def release_tag(self) -> str:
        return NAUTILUS_V2_RC_RELEASE_TAG

    @property
    def release_channel(self) -> EngineReleaseChannel:
        return EngineReleaseChannel.RELEASE_CANDIDATE

    @property
    def authoritative(self) -> bool:
        """A runtime pin declaration alone does not authorize any output."""

        return False

    @property
    def release_pin(self) -> NautilusReleasePin:
        """Build the exact release identity consumed by conformance evidence."""

        return NautilusReleasePin(
            package_version=self.package_version,
            release_tag=self.release_tag,
            source_digest=self.source_digest,
            wheel_digest=self.wheel_digest,
            runtime_image_digest=self.runtime_image_digest,
            python_version=self.python_version,
            rust_version=self.rust_version,
            legacy_runtime_isolated=self.legacy_runtime_isolated,
            contract_version=self.contract_version,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusRuntimeProbeEvidence:
    """Typed, non-authoritative receipt emitted by the isolated image probe."""

    runtime_fingerprint: str
    runtime_image_digest: str
    package_version: str
    python_version: str
    platform: str
    implementation: str
    engine_lifecycle: str

    def __post_init__(self) -> None:
        for name in ("runtime_fingerprint", "runtime_image_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "package_version",
            "python_version",
            "platform",
            "implementation",
        ):
            _nonempty(getattr(self, name), name)
        if self.package_version != NAUTILUS_V2_RC_PACKAGE_VERSION:
            raise ValueError("probe evidence must target the exact v2 RC package")
        if self.engine_lifecycle != "passed":
            raise ValueError("probe evidence requires a passed engine lifecycle")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        runtime: NautilusRcCompatibilityRuntime,
    ) -> NautilusRuntimeProbeEvidence:
        """Parse one strict probe JSON object against its declared runtime."""

        if not isinstance(payload, Mapping):
            raise TypeError("probe payload must be a mapping")
        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        required = {
            "engine_lifecycle",
            "implementation",
            "nautilus_package_version",
            "platform",
            "python_version",
        }
        if set(payload) != required:
            raise ValueError("probe payload fields must match the exact runtime schema")
        values = {key: payload[key] for key in required}
        if any(not isinstance(value, str) for value in values.values()):
            raise TypeError("probe payload fields must be strings")
        if values["nautilus_package_version"] != runtime.package_version:
            raise ValueError("probe package version does not match the declared runtime")
        if values["python_version"] != runtime.python_version:
            raise ValueError("probe Python version does not match the declared runtime")
        return cls(
            runtime_fingerprint=runtime.fingerprint,
            runtime_image_digest=runtime.runtime_image_digest,
            package_version=values["nautilus_package_version"],
            python_version=values["python_version"],
            platform=values["platform"],
            implementation=values["implementation"],
            engine_lifecycle=values["engine_lifecycle"],
        )

    @property
    def authoritative(self) -> bool:
        """RC probe output can never authorize published or live results."""

        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def _require_forward_event_tape_parity(value: Any) -> bool:
    """Validate exact-image callback parity, retaining legacy partial receipts."""

    if value == "deferred_authoritative_fixture":
        return False
    fields = {
        "authoritative",
        "event_count",
        "event_types",
        "expected_wire_digest",
        "forward_tape_fingerprint",
        "instance_id",
        "mismatches",
        "observed_event_count",
        "observed_wire_digest",
        "passed",
        "receipt_fingerprint",
        "unexpected_callback_count",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("forward event-tape parity fields are invalid")
    for name in (
        "expected_wire_digest",
        "forward_tape_fingerprint",
        "observed_wire_digest",
        "receipt_fingerprint",
    ):
        require_sha256_digest(value[name], field_name=f"forward parity {name}")
    if value["event_types"] != ["ohlcv", "quote", "trade"]:
        raise ValueError("forward event-tape parity must exercise every native event type")
    if (
        value["authoritative"] is not False
        or value["passed"] is not True
        or value["event_count"] != 3
        or value["observed_event_count"] != 3
        or value["unexpected_callback_count"] != 0
        or value["expected_wire_digest"] != value["observed_wire_digest"]
        or value["mismatches"] != []
    ):
        raise ValueError("forward event-tape parity did not exactly match Nautilus callbacks")
    try:
        receipt = NautilusForwardEventParityReceipt(
            instance_id=value["instance_id"],
            forward_tape_fingerprint=value["forward_tape_fingerprint"],
            expected_event_count=value["event_count"],
            observed_event_count=value["observed_event_count"],
            expected_wire_digest=value["expected_wire_digest"],
            observed_wire_digest=value["observed_wire_digest"],
            mismatches=tuple(value["mismatches"]),
            passed=value["passed"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("forward event-tape parity receipt is invalid") from error
    if receipt.fingerprint != value["receipt_fingerprint"]:
        raise ValueError("forward event-tape parity receipt fingerprint is invalid")
    return True


def _require_native_forward_session(value: Any) -> None:
    """Require exact-image warm-up, staged-delivery, idempotency, and replay proof."""

    fields = {
        "account_event_fingerprint",
        "authoritative",
        "non_empty_prefix_runtime_reconstruction",
        "reconstructed_account_event_fingerprint",
        "passed",
        "result_fingerprint",
        "runtime_session_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("native forward session fixture fields are invalid")
    for name in (
        "account_event_fingerprint",
        "reconstructed_account_event_fingerprint",
        "result_fingerprint",
        "runtime_session_fingerprint",
    ):
        require_sha256_digest(value[name], field_name=f"native forward session {name}")
    if (
        value["authoritative"] is not False
        or value["passed"] is not True
        or value["non_empty_prefix_runtime_reconstruction"] is not True
    ):
        raise ValueError("native forward session fixture did not pass as a non-authoritative probe")


@dataclass(frozen=True, slots=True)
class NautilusRcFixtureReceipt:
    """Partial real-engine fixture receipt for the non-authoritative RC track."""

    runtime_fingerprint: str
    runtime_image_digest: str
    fixture_digest: str
    passed_checks: frozenset[ConformanceCheck]
    deferred_checks: frozenset[ConformanceCheck]

    def __post_init__(self) -> None:
        for name in ("runtime_fingerprint", "runtime_image_digest", "fixture_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        passed = frozenset(self.passed_checks)
        deferred = frozenset(self.deferred_checks)
        if any(not isinstance(check, ConformanceCheck) for check in passed | deferred):
            raise TypeError("fixture checks must contain ConformanceCheck values")
        if passed & deferred:
            raise ValueError("passed and deferred fixture checks must be disjoint")
        if passed | deferred != frozenset(ConformanceCheck):
            raise ValueError("fixture receipt must account for every conformance check")
        object.__setattr__(self, "passed_checks", passed)
        object.__setattr__(self, "deferred_checks", deferred)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        runtime: NautilusRcCompatibilityRuntime,
    ) -> NautilusRcFixtureReceipt:
        """Parse the real image fixture output without granting authority."""

        if not isinstance(payload, Mapping):
            raise TypeError("fixture payload must be a mapping")
        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        required = {
            "authoritative",
            "deterministic_replay",
            "engine_lifecycle",
            "forward_event_tape_parity",
            "forward_native_session",
            "forward_streaming_session",
            "multi_instrument_accounting",
            "native_component_pnl_attribution",
            "native_order_fill_cost",
            "native_signed_fee_reconciliation",
            "portfolio_rebalance_schedule",
        }
        if set(payload) != required:
            raise ValueError("fixture payload fields must match the exact receipt schema")
        if payload["authoritative"] is not False:
            raise ValueError("release-candidate fixture receipts cannot be authoritative")
        if payload["engine_lifecycle"] != "passed":
            raise ValueError("fixture engine lifecycle must pass")
        replay = payload["deterministic_replay"]
        multi = payload["multi_instrument_accounting"]
        native = payload["native_order_fill_cost"]
        if not isinstance(replay, Mapping) or replay.get("equal") is not True:
            raise ValueError("deterministic replay fixture did not match")
        if not isinstance(multi, Mapping) or multi.get("instrument_count", 0) < 2:
            raise ValueError("multi-instrument fixture did not cover two instruments")
        _require_native_accounting_run(multi)
        _require_native_accounting_run(native)
        _require_target_allocation_probe(native.get("target_allocation_probe"))
        _require_raw_order_risk_probe(native.get("raw_order_risk_probe"))
        _require_native_component_pnl_probe(payload["native_component_pnl_attribution"])
        _require_native_signed_fee_reconciliation(payload["native_signed_fee_reconciliation"])
        _require_native_forward_session(payload["forward_native_session"])
        _require_forward_streaming_session(payload["forward_streaming_session"])
        _require_rebalance_schedule_probe(payload["portfolio_rebalance_schedule"])
        forward_parity_passed = _require_forward_event_tape_parity(
            payload["forward_event_tape_parity"]
        )
        if multi["instrument_count"] < 2 or native["instrument_count"] != 1:
            raise ValueError("single- and multi-instrument fixtures must be distinct")
        passed_checks = {
            ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING,
            ConformanceCheck.NATIVE_ORDER_FILL_COST,
            ConformanceCheck.DETERMINISTIC_REPLAY,
            ConformanceCheck.ENGINE_LIFECYCLE,
        }
        if forward_parity_passed:
            passed_checks.add(ConformanceCheck.FORWARD_EVENT_TAPE_PARITY)
        return cls(
            runtime_fingerprint=runtime.fingerprint,
            runtime_image_digest=runtime.runtime_image_digest,
            fixture_digest=content_digest(payload),
            passed_checks=frozenset(passed_checks),
            deferred_checks=(
                frozenset()
                if forward_parity_passed
                else frozenset({ConformanceCheck.FORWARD_EVENT_TAPE_PARITY})
            ),
        )

    @property
    def compatible(self) -> bool:
        """Partial RC fixtures are compatible but not complete conformance."""

        return True

    @property
    def authoritative(self) -> bool:
        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


__all__ = [
    "NautilusRcCompatibilityRuntime",
    "NautilusRuntimeProbeEvidence",
    "NautilusRcFixtureReceipt",
]
