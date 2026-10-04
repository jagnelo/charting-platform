"""Run the serialized strategy protocol through the isolated Nautilus engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import deque
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from app.strategy_lab_v2 import nautilus_runtime_adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    FUTURE_CONTRACT_NOTIONAL_RISK_MODEL,
    FX_BASE_NOTIONAL_RISK_MODEL,
    AdjustmentMode,
    EvaluationWindow,
    EventGranularity,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    SharedRiskPolicy,
    StrategyVersion,
    TargetConflictPolicy,
)
from app.strategy_lab_v2.nautilus_equity_trace import (
    NautilusAccountEquityTraceReference,
    verify_nautilus_account_equity_trace_file,
)
from app.strategy_lab_v2.nautilus_native_event_stream import (
    serialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_native_reports import (
    NautilusNativeReportsReference,
    iter_nautilus_native_report_records,
)
from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_to_wire
from app.strategy_lab_v2.nautilus_rebalance_schedule import (
    NautilusRebalanceScheduleAudit,
    RebalanceExecutionStatus,
)
from app.strategy_lab_v2.nautilus_rebalance_wire import rebalance_execution_plan_to_wire
from app.strategy_lab_v2.nautilus_runtime_adapter import (
    NAUTILUS_CATALOG_INPUT_CHUNK_SIZE,
    NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE,
    run_native_backtest,
)
from app.strategy_lab_v2.nautilus_runtime_cli import main as runtime_cli_main
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
    NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
)
from app.strategy_lab_v2.nautilus_strategy_bridge import NAUTILUS_COMPONENT_ORDER_TAG_PREFIX
from app.strategy_lab_v2.rebalance import (
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceExecutionPlan,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    StrategyContext,
    StrategyDataDependency,
    StrategySdkManifest,
)
from strategy_runtime import (
    MAX_INVOCATION_CONTEXT_STREAM_BYTES,
    MAX_INVOCATION_RESULT_STREAM_BYTES,
    InvocationContextStreamSource,
    deserialize_invocation_batch,
    deserialize_invocation_result_stream,
    serialize_component_invocation_context_stream,
    serialize_invocation_batch,
    serialize_invocation_context_stream,
)

_EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
_EVENT_TIME_NS = 1_704_205_800_000_000_000


def _datetime_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


_SOURCE = """
class Strategy:
    def on_event(self, context):
        return []
"""

_TARGET_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [TargetPositionIntent("AAPL.SIM", Decimal("0.5"))]
"""

_FUTURE_TARGET_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [TargetPositionIntent("CLZ26.SIM", Decimal("0.4"))]
"""

_RAW_ORDER_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [OrderIntent(
            instrument_id="AAPL.SIM",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )]
"""

_FUTURE_ORDER_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [OrderIntent(
            instrument_id="CLZ26.SIM",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )]
"""

_POSITION_CYCLE_SOURCE = """
class Strategy:
    def __init__(self):
        self.step = 0

    def on_event(self, context):
        sides = (OrderSide.BUY, OrderSide.SELL, OrderSide.BUY, OrderSide.SELL)
        if self.step >= len(sides):
            return []
        side = sides[self.step]
        self.step += 1
        return [OrderIntent(
            instrument_id="AAPL.SIM",
            side=side,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )]
"""


def _payload() -> dict[str, object]:
    manifest = _manifest()
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-adapter-probe",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="component-1",
                strategy_fingerprint=manifest.strategy.fingerprint,
                instrument_ids=("EURUSD.SIM",),
                capital_weight=Decimal("1"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(risk_models=(FX_BASE_NOTIONAL_RISK_MODEL,)),
    )
    return {
        "trial_id": "trial-adapter-probe",
        "attempt_id": "attempt-adapter-probe",
        "data_snapshot_fingerprint": content_digest("adapter-probe-snapshot"),
        "event_tape": {
            "source_tape_fingerprint": content_digest("adapter-probe-tape"),
            "adapter_version": "strategy-lab.nautilus-event-adapter.v1",
            "events": [
                {
                    "dependency_id": "prices",
                    "event_id": "adapter-event-1",
                    "instrument_id": "EURUSD.SIM",
                    "event_type": "quote",
                    "event_time_ns": _EVENT_TIME_NS,
                    "sequence": 1,
                    "values": {
                        "bid": "1.1000",
                        "ask": "1.1002",
                        "bid_size": "100000",
                        "ask_size": "100000",
                    },
                },
                {
                    "dependency_id": "prices",
                    "event_id": "adapter-event-2",
                    "instrument_id": "EURUSD.SIM",
                    "event_type": "quote",
                    "event_time_ns": _EVENT_TIME_NS,
                    "sequence": 2,
                    "values": {
                        "bid": "1.1001",
                        "ask": "1.1003",
                        "bid_size": "100000",
                        "ask_size": "100000",
                    },
                },
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
                "price_increment": "0.00001",
                "size_increment": "1",
                "multiplier": "1",
                "min_quantity": None,
                "max_quantity": None,
                "activation_ns": None,
                "expiration_ns": None,
                "bar_type": "EURUSD.SIM-1-MINUTE-MID-INTERNAL",
                "asset_class": None,
                "underlying": None,
                "option_kind": None,
                "strike_price": None,
                "margin_init": None,
                "margin_maint": None,
            }
        ],
        "venue": {
            "venue_id": "SIM",
            "oms_type": "netting",
            "account_type": "margin",
            "base_currency": "USD",
            "cash": [{"currency": "USD", "amount": "100000"}],
            "fee_model": None,
        },
        "portfolio": portfolio_composition_to_wire(portfolio),
        "strategy_source_digest": content_digest(_SOURCE),
        "strategy_manifest_fingerprint": manifest.fingerprint,
        "entrypoint": "strategy.main:Strategy",
        "parameters": {"window": 20},
        "random_seed": 17,
        "evaluation_window": None,
        "rebalance_plan": None,
        "strategy_bindings": [
            {
                "component_id": "component-1",
                "strategy_fingerprint": manifest.strategy.fingerprint,
                "strategy_source_digest": content_digest(_SOURCE),
                "strategy_manifest_fingerprint": manifest.fingerprint,
                "entrypoint": "strategy.main:Strategy",
                "parameters_digest": content_digest({"window": 20}),
                "max_intents_per_event": 100,
            }
        ],
        "input_version": "strategy-lab.nautilus-engine-input.v7",
    }


def _manifest() -> StrategySdkManifest:
    requirement = CapabilityRequirement(
        instrument_id="EURUSD.SIM",
        product_class=ProductClass.FX,
        event_granularity=EventGranularity.QUOTE,
        event_type="quote",
        timeframe="tick",
        start=_EVENT_TIME - timedelta(days=1),
        end=_EVENT_TIME + timedelta(days=1),
        adjustment=AdjustmentMode.RAW,
        session="24x7",
        feed="consolidated",
        execution_model="market",
        account_model="margin",
        corporate_action_semantics="raw-unadjusted-v1",
    )
    return StrategySdkManifest(
        StrategyVersion("strategy-adapter-probe", "v1", "2.0", content_digest(_SOURCE)),
        (
            StrategyDataDependency(
                "prices",
                requirement,
                ("bid", "ask", "bid_size", "ask_size"),
                lookback_periods=2,
            ),
        ),
    )


def _invocation_batch() -> str:
    manifest = _manifest()
    first = MarketEvent(
        "prices",
        "adapter-event-1",
        "EURUSD.SIM",
        _EVENT_TIME,
        1,
        {
            "bid": "1.1000",
            "ask": "1.1002",
            "bid_size": "100000",
            "ask_size": "100000",
        },
    )
    second = MarketEvent(
        "prices",
        "adapter-event-2",
        "EURUSD.SIM",
        _EVENT_TIME,
        2,
        {
            "bid": "1.1001",
            "ask": "1.1003",
            "bid_size": "100000",
            "ask_size": "100000",
        },
    )
    contexts = (
        StrategyContext(
            _EVENT_TIME,
            2,
            17,
            {"window": 20},
            {"prices": (first, second)},
        ),
    )
    return serialize_invocation_batch(
        source=_SOURCE,
        manifest=manifest,
        contexts=contexts,
        entrypoint="strategy.main:Strategy",
    )


def run_target_allocation_probe() -> dict[str, Any]:
    """Exercise target allocation through the pinned native callback adapter."""

    return _run_native_execution_probe(target_position=True)


def run_order_risk_probe() -> dict[str, Any]:
    """Exercise raw SDK orders through platform risk before native submission."""

    return _run_native_execution_probe(target_position=False)


def run_futures_margin_probe() -> dict[str, Any]:
    """Exercise a listed futures order through the native margin admission gate."""

    return _run_native_execution_probe(target_position=False, futures_margin_probe=True)


def run_futures_target_allocation_probe() -> dict[str, Any]:
    """Exercise a futures target through allocation and native margin admission."""

    return _run_native_execution_probe(target_position=True, futures_margin_probe=True)


def run_native_reports_schema_probe() -> dict[str, Any]:
    """Inspect real RC report fields through the streamed artifact boundary."""

    return _run_native_execution_probe(
        target_position=False,
        include_native_report_diagnostics=True,
    )


def run_native_component_cycle_pnl_probe(
    *, commission_amount: Decimal | None = None
) -> dict[str, Any]:
    """Verify RC position snapshots, fill identities, component tags, and P&L."""

    return _run_native_execution_probe(
        target_position=False,
        include_native_report_diagnostics=True,
        position_cycle_reopen=True,
        fee_model_definition=(
            None
            if commission_amount is None
            else {
                "kind": "fixed_per_fill",
                "amount": str(commission_amount),
                "currency": "USD",
            }
        ),
    )


def run_native_signed_fee_reconciliation_probe() -> dict[str, Any]:
    """Verify positive commissions and negative rebates inside native account P&L."""

    positive_fee = run_native_component_cycle_pnl_probe(commission_amount=Decimal("1.00"))
    rebate = run_native_component_cycle_pnl_probe(commission_amount=Decimal("-1.00"))
    return {
        "authoritative": False,
        "positive_fee": positive_fee,
        "rebate": rebate,
    }


def run_rebalance_schedule_probe() -> dict[str, Any]:
    """Exercise open, close, and fail-on-misfire callbacks inside RC5."""

    cases = {
        "session_open": _run_native_execution_probe(
            target_position=True,
            rebalance_trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        ),
        "session_close": _run_native_execution_probe(
            target_position=True,
            rebalance_trigger=RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS,
        ),
        "multi_component_shared_account": _run_native_execution_probe(
            target_position=True,
            rebalance_trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            multi_component_rebalance=True,
        ),
        "component_priority_contention": _run_native_execution_probe(
            target_position=True,
            rebalance_trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            multi_component_priority=True,
            include_native_report_diagnostics=True,
        ),
        "shared_risk_rejection": _run_native_execution_probe(
            target_position=True,
            rebalance_trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            shared_risk_rejection=True,
        ),
        "fail_on_misfire": _run_native_execution_probe(
            target_position=True,
            rebalance_misfire_only=True,
        ),
    }
    return {"authoritative": False, **cases}


def _run_native_execution_probe(
    *,
    target_position: bool,
    include_native_report_diagnostics: bool = False,
    position_cycle_reopen: bool = False,
    rebalance_trigger: RebalanceTrigger | None = None,
    rebalance_misfire_only: bool = False,
    multi_component_rebalance: bool = False,
    multi_component_priority: bool = False,
    shared_risk_rejection: bool = False,
    fee_model_definition: Mapping[str, Any] | None = None,
    futures_margin_probe: bool = False,
) -> dict[str, Any]:
    component_scenario_count = sum(
        (multi_component_rebalance, multi_component_priority, shared_risk_rejection)
    )
    if component_scenario_count > 1:
        raise ValueError("native component probe scenarios are mutually exclusive")
    if position_cycle_reopen and (
        target_position
        or not include_native_report_diagnostics
        or component_scenario_count
        or rebalance_trigger is not None
        or rebalance_misfire_only
    ):
        raise ValueError("native position-cycle probe options are inconsistent")
    if fee_model_definition is not None and not position_cycle_reopen:
        raise ValueError("native fee-model probe requires the reopened-position report path")
    if rebalance_trigger is not None and rebalance_misfire_only:
        raise ValueError("rebalance trigger and misfire-only modes cannot be combined")
    if (rebalance_trigger is not None or rebalance_misfire_only) and not target_position:
        raise ValueError("rebalance probes require target-position intents")
    if component_scenario_count and (
        rebalance_trigger is not RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS
        or rebalance_misfire_only
        or not target_position
    ):
        raise ValueError("component probes require an open-boundary target rebalance")
    if futures_margin_probe and (
        include_native_report_diagnostics
        or position_cycle_reopen
        or component_scenario_count
        or rebalance_trigger is not None
        or rebalance_misfire_only
        or shared_risk_rejection
        or fee_model_definition is not None
    ):
        raise ValueError("futures margin probe options are inconsistent")
    instrument_id = "CLZ26.SIM" if futures_margin_probe else "AAPL.SIM"
    strategy_source = (
        _POSITION_CYCLE_SOURCE
        if position_cycle_reopen
        else _FUTURE_TARGET_SOURCE
        if futures_margin_probe and target_position
        else _FUTURE_ORDER_SOURCE
        if futures_margin_probe
        else _TARGET_SOURCE
        if target_position
        else _RAW_ORDER_SOURCE
    )
    later_time = _EVENT_TIME + timedelta(seconds=1)
    if position_cycle_reopen:
        cycle_quotes = (
            ("99.99", "100.01"),
            ("100.00", "100.02"),
            ("101.99", "102.01"),
            ("103.99", "104.01"),
            ("105.99", "106.01"),
        )
        events = tuple(
            MarketEvent(
                "prices",
                f"position-cycle-event-{index}",
                instrument_id,
                _EVENT_TIME + timedelta(seconds=max(index - 2, 0)),
                index,
                {"bid": bid, "ask": ask, "bid_size": "1000", "ask_size": "1000"},
            )
            for index, (bid, ask) in enumerate(cycle_quotes, start=1)
        )
    elif futures_margin_probe and target_position:
        events = (
            MarketEvent(
                "prices",
                "future-target-event-1",
                instrument_id,
                _EVENT_TIME,
                1,
                {"bid": "19.99", "ask": "20.01", "bid_size": "100", "ask_size": "100"},
            ),
            MarketEvent(
                "prices",
                "future-target-event-2",
                instrument_id,
                _EVENT_TIME,
                2,
                {"bid": "20.00", "ask": "20.02", "bid_size": "100", "ask_size": "100"},
            ),
            MarketEvent(
                "prices",
                "future-target-event-3",
                instrument_id,
                later_time,
                3,
                {"bid": "20.01", "ask": "20.03", "bid_size": "100", "ask_size": "100"},
            ),
        )
    elif futures_margin_probe:
        events = (
            MarketEvent(
                "prices",
                "future-event-1",
                instrument_id,
                _EVENT_TIME,
                1,
                {"bid": "79.99", "ask": "80.01", "bid_size": "100", "ask_size": "100"},
            ),
            MarketEvent(
                "prices",
                "future-event-2",
                instrument_id,
                _EVENT_TIME,
                2,
                {"bid": "80.00", "ask": "80.02", "bid_size": "100", "ask_size": "100"},
            ),
            MarketEvent(
                "prices",
                "future-event-3",
                instrument_id,
                later_time,
                3,
                {"bid": "80.01", "ask": "80.03", "bid_size": "100", "ask_size": "100"},
            ),
        )
    else:
        events = (
            MarketEvent(
                "prices",
                "target-event-1",
                instrument_id,
                _EVENT_TIME,
                1,
                {"bid": "99.99", "ask": "100.01", "bid_size": "1000", "ask_size": "1000"},
            ),
            MarketEvent(
                "prices",
                "target-event-2",
                instrument_id,
                _EVENT_TIME,
                2,
                {"bid": "100.00", "ask": "100.02", "bid_size": "1000", "ask_size": "1000"},
            ),
            MarketEvent(
                "prices",
                "target-event-3",
                instrument_id,
                later_time,
                3,
                {"bid": "100.01", "ask": "100.03", "bid_size": "1000", "ask_size": "1000"},
            ),
        )
    if rebalance_trigger is RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS:
        events = (
            *events,
            MarketEvent(
                "prices",
                "target-event-4",
                instrument_id,
                later_time + timedelta(seconds=1),
                4,
                {"bid": "100.02", "ask": "100.04", "bid_size": "1000", "ask_size": "1000"},
            ),
        )
    requirement = CapabilityRequirement(
        instrument_id=instrument_id,
        product_class=ProductClass.FUTURE if futures_margin_probe else ProductClass.EQUITY,
        event_granularity=EventGranularity.QUOTE,
        event_type="quote",
        timeframe="tick",
        start=_EVENT_TIME - timedelta(days=1),
        end=later_time + timedelta(days=1),
        adjustment=AdjustmentMode.RAW,
        session="regular",
        feed="consolidated",
        execution_model="market",
        account_model="margin" if futures_margin_probe else "cash",
        corporate_action_semantics="raw-unadjusted-v1",
    )
    data_dependencies = (
        StrategyDataDependency("prices", requirement, ("bid", "ask", "bid_size", "ask_size"), 1),
    )

    def component_manifest(component_id: str, source: str) -> StrategySdkManifest:
        version_prefix = "strategy-target-probe" if target_position else "strategy-raw-order-probe"
        return StrategySdkManifest(
            StrategyVersion(
                f"{version_prefix}-{component_id}",
                "v1",
                "2.0",
                content_digest(source),
            ),
            data_dependencies,
        )

    calendar_fingerprint = content_digest("nautilus-adapter-probe-calendar")
    rebalance_policy = None
    rebalance_plan = None
    if rebalance_trigger is not None or rebalance_misfire_only:
        trigger = rebalance_trigger or RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS
        rebalance_policy = CalendarRebalancePolicy(
            calendar_id="adapter-probe-calendar",
            calendar_fingerprint=calendar_fingerprint,
            cadence=RebalanceCadence.EACH_SESSION,
            trigger=trigger,
            misfire_policy=RebalanceMisfirePolicy.FAIL_RUN,
        )
        scheduled_time = later_time + timedelta(seconds=1) if rebalance_misfire_only else later_time
        occurrence = ScheduledRebalance(
            occurrence_id=content_digest(
                {
                    "policy": rebalance_policy.fingerprint,
                    "event_time": scheduled_time,
                    "session": scheduled_time.date(),
                }
            ),
            policy_fingerprint=rebalance_policy.fingerprint,
            calendar_fingerprint=calendar_fingerprint,
            session_id=f"probe-session-{scheduled_time.date().isoformat()}",
            session_label=scheduled_time.date(),
            event_time=scheduled_time,
            trigger=trigger,
            cadence_period=f"session:{scheduled_time.date().isoformat()}",
            misfire_policy=rebalance_policy.misfire_policy,
        )
        rebalance_plan = RebalanceExecutionPlan(
            policy_fingerprint=rebalance_policy.fingerprint,
            calendar_fingerprint=calendar_fingerprint,
            occurrences=(occurrence,),
        )
    component_ids = ("core", "satellite") if component_scenario_count else ("core",)
    component_sources = {component_id: strategy_source for component_id in component_ids}
    if multi_component_priority:
        component_sources = {
            "core": _TARGET_SOURCE.replace('Decimal("0.5")', 'Decimal("0.8")'),
            "satellite": _TARGET_SOURCE.replace('Decimal("0.5")', 'Decimal("0.2")'),
        }
    strategy_source = component_sources[component_ids[0]]
    component_manifests = {
        component_id: component_manifest(component_id, component_sources[component_id])
        for component_id in component_ids
    }
    manifest = component_manifests[component_ids[0]]
    component_priorities = {
        "core": 1 if multi_component_priority else 0,
        "satellite": 7 if multi_component_priority else 1,
    }
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-target-probe",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=tuple(
            PortfolioComponent(
                component_id,
                component_manifests[component_id].strategy.fingerprint,
                (instrument_id,),
                Decimal("0.5") if component_scenario_count else Decimal("1"),
                priority=component_priorities[component_id],
            )
            for component_id in component_ids
        ),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=(
                Decimal("0.25") if shared_risk_rejection else Decimal("1.0")
            ),
            risk_models=(
                FUTURE_CONTRACT_NOTIONAL_RISK_MODEL
                if futures_margin_probe
                else CASH_EQUITY_NOTIONAL_RISK_MODEL,
            ),
            target_conflict_policy=(
                TargetConflictPolicy.SUM_COMPONENT_TARGETS
                if multi_component_rebalance or shared_risk_rejection
                else TargetConflictPolicy.HIGHEST_PRIORITY
                if multi_component_priority
                else TargetConflictPolicy.REJECT
            ),
        ),
        rebalance_policy=rebalance_policy,
    )
    event_records = [
        {
            "dependency_id": event.dependency_id,
            "event_id": event.event_id,
            "instrument_id": event.instrument_id,
            "event_type": "quote",
            "event_time_ns": int(event.event_time.timestamp()) * 1_000_000_000,
            "sequence": event.sequence,
            "values": dict(event.values),
        }
        for event in events
    ]
    payload: dict[str, object] = {
        "trial_id": "trial-target-probe",
        "attempt_id": "attempt-target-probe",
        "data_snapshot_fingerprint": content_digest("target-probe-snapshot"),
        "event_tape": {
            "source_tape_fingerprint": content_digest(event_records),
            "adapter_version": "strategy-lab.nautilus-event-adapter.v1",
            "events": event_records,
        },
        "instruments": [
            {
                "instrument_id": instrument_id,
                "raw_symbol": "CLZ26" if futures_margin_probe else "AAPL",
                "venue_id": "SIM",
                "product_class": "future" if futures_margin_probe else "equity",
                "base_currency": None,
                "quote_currency": "USD",
                "price_precision": 2,
                "size_precision": 0,
                "price_increment": "0.01",
                "size_increment": "1",
                "multiplier": "1000" if futures_margin_probe else "1",
                "min_quantity": "1",
                "max_quantity": None,
                "activation_ns": (
                    _datetime_ns(_EVENT_TIME - timedelta(days=365))
                    if futures_margin_probe
                    else None
                ),
                "expiration_ns": (
                    _datetime_ns(_EVENT_TIME + timedelta(days=365))
                    if futures_margin_probe
                    else None
                ),
                "bar_type": None,
                "asset_class": "COMMODITY" if futures_margin_probe else None,
                "underlying": "CL" if futures_margin_probe else None,
                "option_kind": None,
                "strike_price": None,
                "margin_init": "0.12" if futures_margin_probe else None,
                "margin_maint": "0.11" if futures_margin_probe else None,
            }
        ],
        "venue": {
            "venue_id": "SIM",
            "oms_type": "netting",
            "account_type": "margin" if futures_margin_probe else "cash",
            "base_currency": "USD",
            "cash": [{"currency": "USD", "amount": "100000"}],
            "fee_model": fee_model_definition,
        },
        "portfolio": portfolio_composition_to_wire(portfolio),
        "strategy_source_digest": manifest.strategy.source_digest,
        "strategy_manifest_fingerprint": manifest.fingerprint,
        "entrypoint": "strategy.main:Strategy",
        "parameters": {},
        "random_seed": 11,
        "evaluation_window": None,
        "rebalance_plan": rebalance_execution_plan_to_wire(rebalance_plan),
        "strategy_bindings": [
            {
                "component_id": component_id,
                "strategy_fingerprint": component_manifests[component_id].strategy.fingerprint,
                "strategy_source_digest": component_manifests[component_id].strategy.source_digest,
                "strategy_manifest_fingerprint": component_manifests[component_id].fingerprint,
                "entrypoint": "strategy.main:Strategy",
                "parameters_digest": content_digest({}),
                "max_intents_per_event": 100,
            }
            for component_id in component_ids
        ],
        "input_version": "strategy-lab.nautilus-engine-input.v7",
    }
    invocation_contexts = tuple(
        StrategyContext(
            event.event_time,
            event.sequence,
            11,
            {},
            # The manifest declares one prior event plus the current event.
            {"prices": events[max(index - 1, 0) : index + 1]},
        )
        for index, event in enumerate(events)
        if index > 0
    )
    batch = serialize_invocation_batch(
        source=strategy_source,
        manifest=manifest,
        contexts=invocation_contexts,
        entrypoint="strategy.main:Strategy",
    )
    component_context_stream: BytesIO | None = None
    component_counts: Mapping[str, int] | None = None
    native_event_stream: BytesIO | None = None
    native_event_stream_digest: str | None = None
    if component_scenario_count:
        component_context_stream = BytesIO()
        component_counts = serialize_component_invocation_context_stream(
            component_context_stream,
            components=tuple(
                InvocationContextStreamSource(
                    component_id,
                    component_sources[component_id],
                    component_manifests[component_id],
                    invocation_contexts,
                    "strategy.main:Strategy",
                )
                for component_id in component_ids
            ),
        )
        event_tape = payload["event_tape"]
        if not isinstance(event_tape, dict):
            raise RuntimeError("multi-component native event tape is invalid")
        native_event_stream = BytesIO()
        event_summary = serialize_nautilus_native_event_stream(
            native_event_stream,
            event_records,
            source_tape_fingerprint=str(event_tape["source_tape_fingerprint"]),
            adapter_version=str(event_tape["adapter_version"]),
            expected_event_count=len(event_records),
        )
        native_event_stream_digest = event_summary.content_digest
        payload["event_tape"] = {
            "source_tape_fingerprint": event_summary.source_tape_fingerprint,
            "adapter_version": event_summary.adapter_version,
            "event_count": event_summary.event_count,
        }

    def execute_native_backtest(
        *,
        account_equity_trace_path: Path | None = None,
        native_reports_path: Path | None = None,
    ) -> dict[str, Any]:
        if component_scenario_count:
            assert component_context_stream is not None
            assert component_counts is not None
            assert native_event_stream is not None
            assert native_event_stream_digest is not None
            return run_native_backtest(
                payload,
                invocation_context_stream=component_context_stream,
                native_event_stream=native_event_stream,
                native_event_stream_digest=native_event_stream_digest,
                expected_context_count=sum(component_counts.values()),
                expected_component_context_counts=component_counts,
                account_equity_trace_path=account_equity_trace_path,
                native_reports_path=native_reports_path,
            )
        return run_native_backtest(
            payload,
            serialized_strategy_invocation_batch=batch,
            account_equity_trace_path=account_equity_trace_path,
            native_reports_path=native_reports_path,
        )

    if shared_risk_rejection:
        try:
            execute_native_backtest()
        except Exception as error:
            if "native order batch breaches shared portfolio risk" not in str(error):
                raise RuntimeError(
                    "native component risk rejection did not fail at the shared risk gate"
                ) from error
            return {
                "risk_rejected": True,
                "risk_gate": "shared_portfolio",
                "submission_prevented": True,
                "total_orders": 0,
                "total_positions": 0,
                "authoritative": False,
            }
        raise RuntimeError("native shared-risk probe submitted an over-limit component batch")

    native_report_diagnostics = None
    native_report_records: dict[str, list[Mapping[str, Any]]] = {}
    component_order_tag = None
    component_fill_attribution: dict[str, str] | None = None
    if include_native_report_diagnostics:
        scoring_start_ns = event_records[0].get("event_time_ns")
        scoring_end_ns = event_records[-1].get("event_time_ns")
        if (
            not isinstance(scoring_start_ns, int)
            or isinstance(scoring_start_ns, bool)
            or not isinstance(scoring_end_ns, int)
            or isinstance(scoring_end_ns, bool)
        ):
            raise RuntimeError("native report diagnostic tape timestamps are invalid")
        evaluation_window = EvaluationWindow(
            start=_EVENT_TIME,
            end=events[-1].event_time + timedelta(microseconds=1),
            purpose="native-report-schema-probe",
        )
        window_wire = {
            "fingerprint": evaluation_window.fingerprint,
            "purpose": evaluation_window.purpose,
            "warmup_start_ns": None,
            "start_ns": _datetime_ns(evaluation_window.start),
            "end_ns": _datetime_ns(evaluation_window.end),
        }
        window_start_ns = window_wire.get("start_ns")
        window_end_ns = window_wire.get("end_ns")
        if (
            not isinstance(window_start_ns, int)
            or isinstance(window_start_ns, bool)
            or not isinstance(window_end_ns, int)
            or isinstance(window_end_ns, bool)
        ):
            raise RuntimeError("native report diagnostic evaluation bounds are invalid")
        if window_start_ns > scoring_start_ns or window_end_ns <= scoring_end_ns:
            raise RuntimeError("native report diagnostic window does not cover its event tape")
        payload["evaluation_window"] = window_wire
        with tempfile.TemporaryDirectory(prefix="strategy-lab-native-report-probe-") as root:
            equity_path = Path(root) / "account-equity.parquet"
            reports_path = Path(root) / "native-reports.parquet"
            result = execute_native_backtest(
                account_equity_trace_path=equity_path,
                native_reports_path=reports_path,
            )
            equity_reference = NautilusAccountEquityTraceReference.from_wire(
                result.get("account_equity_trace")
            )
            verify_nautilus_account_equity_trace_file(
                equity_reference,
                equity_path,
                expected_events=tuple(
                    {"index": index, "event": event} for index, event in enumerate(event_records)
                ),
            )
            reports_reference = NautilusNativeReportsReference.from_wire(
                result.get("native_execution_reports")
            )
            report_samples: dict[str, dict[str, Any]] = {}
            for kind, _, record in iter_nautilus_native_report_records(
                reports_reference,
                reports_path,
            ):
                if position_cycle_reopen:
                    native_report_records.setdefault(kind, []).append(record)
                sample = report_samples.setdefault(
                    kind,
                    {"columns": sorted(record), "sample_record": record},
                )
                if tuple(sample["columns"]) != tuple(sorted(record)):
                    raise RuntimeError(f"native {kind} report changed columns between rows")
            if multi_component_priority:
                order_sample = report_samples.get("orders", {}).get("sample_record")
                fill_sample = report_samples.get("fills", {}).get("sample_record")
                tags = order_sample.get("tags") if isinstance(order_sample, dict) else None
                component_order_tag = f"{NAUTILUS_COMPONENT_ORDER_TAG_PREFIX}satellite"
                if not isinstance(tags, list) or component_order_tag not in tags:
                    raise RuntimeError(
                        "native order report did not retain the selected component attribution"
                    )
                if (
                    not isinstance(order_sample, dict)
                    or not isinstance(fill_sample, dict)
                    or reports_reference.row_counts
                    != (
                        ("account", 2),
                        ("fills", 1),
                        ("orders", 1),
                        ("positions", 1),
                    )
                    or order_sample.get("status") != "FILLED"
                    or not isinstance(order_sample.get("venue_order_id"), str)
                    or fill_sample.get("venue_order_id") != order_sample["venue_order_id"]
                    or not isinstance(fill_sample.get("instrument_id"), str)
                    or not isinstance(fill_sample.get("last_qty"), str)
                    or not isinstance(fill_sample.get("last_px"), str)
                    or not isinstance(fill_sample.get("commission"), str)
                    or not isinstance(fill_sample.get("currency"), str)
                ):
                    raise RuntimeError(
                        "native component fill did not reconcile through its tagged order"
                    )
                component_fill_attribution = {
                    "component_id": "satellite",
                    "venue_order_id": str(fill_sample["venue_order_id"]),
                    "instrument_id": fill_sample["instrument_id"],
                    "quantity": fill_sample["last_qty"],
                    "execution_price": fill_sample["last_px"],
                    "commission": fill_sample["commission"],
                    "currency": fill_sample["currency"],
                }
            native_report_diagnostics = {
                "evaluation_window_fingerprint": equity_reference.evaluation_window_fingerprint,
                "row_counts": dict(reports_reference.row_counts),
                "samples": report_samples,
                "verified_equity_observations": equity_reference.observation_count,
            }
            if position_cycle_reopen:
                return _component_cycle_pnl_evidence(native_report_records, result)
    else:
        result = execute_native_backtest()
    summary = result.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("target allocation probe has no native account summary")
    balance_text = summary.get("account.SIM.balance.USD.total")
    if not isinstance(balance_text, str):
        raise RuntimeError("native target allocation summary has no formatted USD balance")
    balance_parts = balance_text.split()
    if len(balance_parts) != 2 or balance_parts[1] != "USD":
        raise RuntimeError("native target allocation summary balance is not denominated in USD")
    remaining_cash = Decimal(balance_parts[0])
    if futures_margin_probe:
        if (
            result.get("authoritative") is not False
            or result.get("total_orders") != 1
            or result.get("total_positions") != 1
        ):
            raise RuntimeError("native futures margin gate did not admit its funded contract")
        return {
            "instrument_id": instrument_id,
            "product_class": "future",
            "intent_kind": "target_position" if target_position else "order",
            "native_account_type": "MARGIN",
            "native_margin_gate": "approved",
            "initial_margin_rate": "0.12",
            "maintenance_margin_rate": "0.11",
            "total_orders": result["total_orders"],
            "total_positions": result["total_positions"],
            "account_balance": str(remaining_cash),
            "account_currency": "USD",
            "authoritative": False,
        }
    if rebalance_plan is not None:
        audit = NautilusRebalanceScheduleAudit.from_wire(
            result.get("rebalance_schedule_audit"),
            attempt_id="attempt-target-probe",
            plan=rebalance_plan,
        )
        if len(audit.outcomes) != 1:
            raise RuntimeError("native rebalance probe did not audit its complete frozen plan")
        outcome = audit.outcomes[0]
        expected_status = (
            RebalanceExecutionStatus.FAILED_MISFIRE
            if rebalance_misfire_only
            else RebalanceExecutionStatus.ORDERS_SUBMITTED
        )
        expected_orders = 0 if rebalance_misfire_only else 2 if multi_component_rebalance else 1
        expected_positions = 0 if rebalance_misfire_only else 1
        if (
            outcome.execution_status is not expected_status
            or outcome.submitted_order_count != expected_orders
            or result.get("total_orders") != expected_orders
            or result.get("total_positions") != expected_positions
            or result.get("authoritative") is not False
        ):
            raise RuntimeError("native rebalance callback, audit, and account state disagree")
        if multi_component_rebalance and not Decimal("40000") < remaining_cash < Decimal("60000"):
            raise RuntimeError("native multi-component targets did not share the account budget")
        if multi_component_priority and not Decimal("88000") < remaining_cash < Decimal("92000"):
            raise RuntimeError("native priority policy did not select the higher-priority target")
        rebalance_result = {
            "audit_fingerprint": audit.fingerprint,
            "execution_status": outcome.execution_status.value,
            "submitted_order_count": outcome.submitted_order_count,
            "total_orders": result["total_orders"],
            "total_positions": result["total_positions"],
            **({"remaining_cash": str(remaining_cash)} if multi_component_rebalance else {}),
            "authoritative": False,
        }
        if multi_component_priority:
            if not isinstance(component_order_tag, str) or component_fill_attribution is None:
                raise RuntimeError("native component priority probe omitted order attribution")
            rebalance_result["remaining_cash"] = str(remaining_cash)
            rebalance_result["component_order_tag"] = component_order_tag
            rebalance_result["component_fill_attribution"] = component_fill_attribution
        return rebalance_result
    if target_position:
        if (
            result.get("authoritative") is not False
            or result.get("total_orders") != 1
            or result.get("total_positions") != 1
            or not Decimal("45000") < remaining_cash < Decimal("55000")
        ):
            raise RuntimeError(
                "native target allocation did not reconcile order, position, and cash"
            )
        probe_result = {
            "instrument_id": instrument_id,
            "requested_target_fraction": "0.5",
            "total_orders": result["total_orders"],
            "total_positions": result["total_positions"],
            "initial_cash": "100000",
            "remaining_cash": str(remaining_cash),
            "observed_deployment": str(Decimal("100000") - remaining_cash),
            "account_base_currency": "USD",
            "authoritative": False,
        }
        if native_report_diagnostics is not None:
            probe_result["native_report_diagnostics"] = native_report_diagnostics
        return probe_result
    if (
        result.get("authoritative") is not False
        or result.get("total_orders") != 1
        or result.get("total_positions") != 1
        or not Decimal("89000") < remaining_cash < Decimal("91000")
    ):
        raise RuntimeError("native raw-order risk probe did not reconcile order and account")
    probe_result = {
        "instrument_id": instrument_id,
        "requested_order_quantity": "100",
        "estimated_signed_base_notional": "10001",
        "total_orders": result["total_orders"],
        "total_positions": result["total_positions"],
        "initial_cash": "100000",
        "remaining_cash": str(remaining_cash),
        "observed_deployment": str(Decimal("100000") - remaining_cash),
        "account_base_currency": "USD",
        "authoritative": False,
    }
    if native_report_diagnostics is not None:
        probe_result["native_report_diagnostics"] = native_report_diagnostics
    return probe_result


def _component_cycle_pnl_evidence(
    reports: Mapping[str, list[Mapping[str, Any]]],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    orders = reports.get("orders", [])
    fills = reports.get("fills", [])
    positions = reports.get("positions", [])
    accounts = reports.get("account", [])
    if (
        result.get("authoritative") is not False
        or result.get("total_orders") != 4
        or len(orders) != 4
        or len(fills) != 4
        or len(positions) != 2
        or not accounts
    ):
        raise RuntimeError("native reopened-position probe did not emit two complete cycles")

    component_tag = f"{NAUTILUS_COMPONENT_ORDER_TAG_PREFIX}core"
    orders_by_client_id: dict[str, Mapping[str, Any]] = {}
    for order in orders:
        client_order_id = order.get("client_order_id")
        tags = order.get("tags")
        if (
            not isinstance(client_order_id, str)
            or not client_order_id
            or client_order_id in orders_by_client_id
            or not isinstance(tags, list | tuple)
            or tags.count(component_tag) != 1
        ):
            raise RuntimeError("native cycle orders lack unique component-tagged identities")
        orders_by_client_id[client_order_id] = order

    fills_by_trade_id: dict[str, Mapping[str, Any]] = {}
    fill_position_ids: set[str] = set()
    total_costs = Decimal(0)
    total_rebates = Decimal(0)
    for fill in fills:
        trade_id = fill.get("trade_id")
        client_order_id = fill.get("client_order_id")
        position_id = fill.get("position_id")
        commission = fill.get("commission")
        if (
            not isinstance(trade_id, str)
            or not trade_id
            or trade_id in fills_by_trade_id
            or client_order_id not in orders_by_client_id
            or not isinstance(position_id, str)
            or not position_id
        ):
            raise RuntimeError("native fill reports lack unique trade/order/position identities")
        fills_by_trade_id[trade_id] = fill
        fill_position_ids.add(position_id)
        if not isinstance(commission, str):
            raise RuntimeError("native fill commission report is missing")
        commission_parts = commission.split()
        if len(commission_parts) != 2 or commission_parts[1] != "USD":
            raise RuntimeError("native cycle commission is not explicitly denominated in USD")
        try:
            commission_amount = Decimal(commission_parts[0])
        except ArithmeticError as error:
            raise RuntimeError("native cycle commission is not an exact decimal") from error
        if not commission_amount.is_finite():
            raise RuntimeError("native cycle commission is not finite")
        if commission_amount >= 0:
            total_costs += commission_amount
        else:
            total_rebates += commission_amount.copy_abs()
    if set(orders_by_client_id) != {fill.get("client_order_id") for fill in fills}:
        raise RuntimeError("native cycle order and fill identities do not reconcile")

    position_net = Decimal(0)
    attributed_trade_ids: set[str] = set()
    archived_snapshot_count = 0
    archived_identity_mismatch = False
    for position in positions:
        position_id = position.get("position_id")
        trade_ids = position.get("trade_ids")
        events = position.get("events")
        is_snapshot = position.get("is_snapshot")
        if (
            not isinstance(position_id, str)
            or not position_id
            or not isinstance(trade_ids, list | tuple)
            or not trade_ids
            or not isinstance(events, list | tuple)
            or not events
            or not isinstance(is_snapshot, bool)
            or position.get("ts_closed") is None
        ):
            raise RuntimeError("native closed position report lacks cycle identity or closure")
        trade_ids_tuple = tuple(trade_ids)
        event_trade_ids: list[str] = []
        event_order_ids: set[str] = set()
        for event in events:
            if not isinstance(event, Mapping) or event.get("type") != "OrderFilled":
                raise RuntimeError("native closed position contains an unsupported retained event")
            event_trade_id = event.get("trade_id")
            event_client_order_id = event.get("client_order_id")
            if (
                not isinstance(event_trade_id, str)
                or event_trade_id not in fills_by_trade_id
                or not isinstance(event_client_order_id, str)
                or not event_client_order_id
            ):
                raise RuntimeError("native retained fill event cannot join to execution reports")
            event_trade_ids.append(event_trade_id)
            event_order_ids.add(event_client_order_id)
        if (
            any(not isinstance(item, str) or not item for item in trade_ids_tuple)
            or len(trade_ids_tuple) != len(set(trade_ids_tuple))
            or set(trade_ids_tuple) != set(event_trade_ids)
            or not set(trade_ids_tuple).issubset(fills_by_trade_id)
            or len(event_trade_ids) != len(set(event_trade_ids))
            or event_order_ids
            != {fills_by_trade_id[item].get("client_order_id") for item in trade_ids_tuple}
            or attributed_trade_ids.intersection(trade_ids_tuple)
        ):
            raise RuntimeError("native position trade IDs do not reconcile uniquely to fills")
        cycle_component_ids = {
            "core"
            for trade_id in trade_ids_tuple
            if fills_by_trade_id[trade_id].get("client_order_id") in orders_by_client_id
            and component_tag
            in orders_by_client_id[str(fills_by_trade_id[trade_id].get("client_order_id"))].get(
                "tags", []
            )
        }
        if cycle_component_ids != {"core"}:
            raise RuntimeError("native closed position is not uniquely owned by the core component")
        realized_pnl = position.get("realized_pnl")
        if not isinstance(realized_pnl, str):
            raise RuntimeError("native closed position realized P&L is missing")
        pnl_parts = realized_pnl.split()
        if len(pnl_parts) != 2 or pnl_parts[1] != "USD":
            raise RuntimeError("native position realized P&L is not in account base currency")
        try:
            position_net += Decimal(pnl_parts[0])
        except ArithmeticError as error:
            raise RuntimeError("native position realized P&L is not an exact decimal") from error
        attributed_trade_ids.update(trade_ids_tuple)
        if is_snapshot:
            archived_snapshot_count += 1
            archived_identity_mismatch = archived_identity_mismatch or (
                position_id not in fill_position_ids
            )

    if (
        attributed_trade_ids != set(fills_by_trade_id)
        or archived_snapshot_count < 1
        or not archived_identity_mismatch
    ):
        raise RuntimeError("native archived cycles do not cover the full fill report exactly")

    account = accounts[-1]
    if account.get("currency") != "USD" or account.get("base_currency") != "USD":
        raise RuntimeError("native final account report is not denominated in USD")
    summary = result.get("summary")
    summary_balance = (
        summary.get("account.SIM.balance.USD.total") if isinstance(summary, Mapping) else None
    )
    if not isinstance(summary_balance, str):
        raise RuntimeError("native cycle result has no USD account balance summary")
    try:
        account_balance = Decimal(str(account["total"]).split()[0])
        summary_balance_amount = Decimal(summary_balance.split()[0])
    except (ArithmeticError, KeyError, IndexError) as error:
        raise RuntimeError("native account balance is not an exact decimal") from error
    if account_balance != summary_balance_amount or not account_balance.is_finite():
        raise RuntimeError("native account report differs from the final engine account balance")
    account_net = account_balance - Decimal("100000")
    portfolio_gross = account_net + total_costs - total_rebates
    component_gross = position_net + total_costs - total_rebates
    if position_net != account_net or component_gross != portfolio_gross:
        raise RuntimeError("native component P&L does not exactly reconcile to account P&L")
    return {
        "authoritative": False,
        "archived_snapshot_cycles": archived_snapshot_count,
        "base_currency": "USD",
        "closed_position_cycles": len(positions),
        "component_gross_pnl": str(component_gross),
        "component_id": "core",
        "component_net_pnl": str(position_net),
        "component_order_count": len(orders_by_client_id),
        "exact_account_reconciliation": True,
        "fill_count": len(fills_by_trade_id),
        "native_trade_id_join_count": len(attributed_trade_ids),
        "portfolio_gross_pnl": str(portfolio_gross),
        "portfolio_net_pnl": str(account_net),
        "reported_cost_deductions": str(total_costs),
        "reported_rebates": str(total_rebates),
        "snapshot_index_differs_from_fill_position_id": archived_identity_mismatch,
        "total_orders": result["total_orders"],
    }


def run_context_stream_cli_probe(
    *,
    event_count: int = 2,
    replay_chunk_size: int | None = None,
) -> dict[str, Any]:
    """Exercise the strict stream/catalog CLI path against the native engine."""

    serialized_batch = _invocation_batch()
    source, manifest, _contexts, entrypoint, max_intents = deserialize_invocation_batch(
        serialized_batch
    )
    if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 2:
        raise ValueError("event_count must be an integer of at least two")
    if replay_chunk_size is not None and (
        not isinstance(replay_chunk_size, int)
        or isinstance(replay_chunk_size, bool)
        or replay_chunk_size < 1
    ):
        raise ValueError("replay_chunk_size must be a positive integer")
    source_engine_input = _payload()
    source_event_tape = source_engine_input["event_tape"]
    if not isinstance(source_event_tape, dict):
        raise RuntimeError("adapter probe event tape is invalid")
    source_events: list[dict[str, Any]] = [
        {
            "dependency_id": "prices",
            "event_id": f"adapter-event-{index + 1}",
            "instrument_id": "EURUSD.SIM",
            "event_type": "quote",
            "event_time_ns": _EVENT_TIME_NS + max(0, index - 1) * 1_000_000_000,
            "sequence": index + 1,
            "values": {
                "bid": f"1.{1000 + index % 100:04d}",
                "ask": f"1.{1002 + index % 100:04d}",
                "bid_size": "100000",
                "ask_size": "100000",
            },
        }
        for index in range(event_count)
    ]
    source_event_tape["events"] = source_events
    source_event_tape["source_tape_fingerprint"] = content_digest(source_events)

    def contexts() -> Iterator[StrategyContext]:
        history: deque[MarketEvent] = deque(maxlen=3)
        position = 0
        while position < len(source_events):
            group_time_ns = source_events[position]["event_time_ns"]
            group_time = _EVENT_TIME + timedelta(
                seconds=(group_time_ns - _EVENT_TIME_NS) // 1_000_000_000
            )
            group: list[MarketEvent] = []
            while (
                position < len(source_events)
                and source_events[position]["event_time_ns"] == group_time_ns
            ):
                event = source_events[position]
                group.append(
                    MarketEvent(
                        event["dependency_id"],
                        event["event_id"],
                        event["instrument_id"],
                        group_time,
                        event["sequence"],
                        event["values"],
                    )
                )
                position += 1
            history.extend(group)
            yield StrategyContext(
                group_time,
                max(event.sequence for event in group),
                17,
                {"window": 20},
                {"prices": tuple(history)},
            )

    context_iter = contexts()
    context_wire = BytesIO()
    context_count = serialize_invocation_context_stream(
        context_wire,
        source=source,
        manifest=manifest,
        contexts=context_iter,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents,
    )
    context_bytes = context_wire.getvalue()
    context_digest = f"sha256:{hashlib.sha256(context_bytes).hexdigest()}"
    native_event_wire = BytesIO()
    native_event_summary = serialize_nautilus_native_event_stream(
        native_event_wire,
        source_events,
        source_tape_fingerprint=source_event_tape["source_tape_fingerprint"],
        adapter_version=source_event_tape["adapter_version"],
        expected_event_count=len(source_events),
    )
    native_event_bytes = native_event_wire.getvalue()
    native_event_digest = native_event_summary.content_digest
    engine_input = dict(source_engine_input)
    event_tape = dict(source_event_tape)
    event_tape.pop("events")
    event_tape["event_count"] = native_event_summary.event_count
    engine_input["event_tape"] = event_tape
    bundle = {
        "schema": NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
        "engine_input": engine_input,
        "strategy_context_stream": {
            "artifact": {
                "content_digest": context_digest,
                "byte_length": len(context_bytes),
                "media_type": NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
                "schema_version": NAUTILUS_CONTEXT_STREAM_SCHEMA,
                "storage_key": context_digest,
                "retention_class": "pinned_input",
            },
            "context_count": context_count,
        },
        "native_event_stream": {
            "artifact": {
                "content_digest": native_event_digest,
                "byte_length": len(native_event_bytes),
                "media_type": NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
                "schema_version": NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
                "storage_key": native_event_digest,
                "retention_class": "pinned_input",
            },
            "source_tape_fingerprint": source_event_tape["source_tape_fingerprint"],
            "adapter_version": source_event_tape["adapter_version"],
            "event_count": native_event_summary.event_count,
        },
    }
    previous = {
        name: os.environ.get(name)
        for name in (
            "STRATEGY_INPUT_BUNDLE_DIGEST",
            "STRATEGY_ATTEMPT_ID",
            "STRATEGY_CONTEXT_STREAM_DIGEST",
            "STRATEGY_NATIVE_EVENT_STREAM_DIGEST",
        )
    }
    previous_replay_chunk_size = NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE
    try:
        if replay_chunk_size is not None:
            nautilus_runtime_adapter.NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE = replay_chunk_size
        with tempfile.TemporaryDirectory(prefix="strategy-lab-context-probe-") as directory:
            root = Path(directory)
            bundle_path = root / "bundle.json"
            context_path = root / "contexts.ndjson"
            native_event_path = root / "native-events.ndjson"
            result_stream_path = root / "invocations.ndjson"
            output_path = root / "result.json"
            bundle_path.write_text(
                json.dumps(bundle, allow_nan=False, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            context_path.write_bytes(context_bytes)
            native_event_path.write_bytes(native_event_bytes)
            result_stream_path.touch()
            output_path.touch()
            os.environ["STRATEGY_INPUT_BUNDLE_DIGEST"] = content_digest(bundle)
            os.environ["STRATEGY_ATTEMPT_ID"] = "attempt-adapter-probe"
            os.environ["STRATEGY_CONTEXT_STREAM_DIGEST"] = context_digest
            os.environ["STRATEGY_NATIVE_EVENT_STREAM_DIGEST"] = native_event_digest
            runtime_cli_main(
                [
                    "--input",
                    str(bundle_path),
                    "--output",
                    str(output_path),
                    "--expected-version",
                    "2.0.0rc5",
                    "--snapshot-fingerprint",
                    content_digest("adapter-probe-snapshot"),
                    "--max-input-bytes",
                    str(MAX_INVOCATION_CONTEXT_STREAM_BYTES),
                    "--context-stream",
                    str(context_path),
                    "--native-event-stream",
                    str(native_event_path),
                    "--invocation-results",
                    str(result_stream_path),
                    "--max-result-bytes",
                    str(MAX_INVOCATION_RESULT_STREAM_BYTES),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            result_stream_bytes = result_stream_path.read_bytes()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        nautilus_runtime_adapter.NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE = previous_replay_chunk_size
    if (
        result.get("strategy_invocation_input_protocol") != "context-stream"
        or result.get("authoritative") is not False
        or result.get("input_event_count") != event_count
        or result.get("total_orders") != 0
        or result.get("total_positions") != 0
        or result.get("native_data_source") != "parquet_catalog_chunks"
        or result.get("catalog_input_chunk_size") != NAUTILUS_CATALOG_INPUT_CHUNK_SIZE
        or result.get("catalog_replay_chunk_size")
        != (replay_chunk_size or previous_replay_chunk_size)
    ):
        raise RuntimeError("native catalog-stream CLI probe did not produce expected evidence")
    stream_receipt = result.get("strategy_invocation_result_stream")
    if not isinstance(stream_receipt, dict):
        raise RuntimeError("native context-stream CLI probe did not stream invocation results")
    if (
        stream_receipt.get("byte_length") != len(result_stream_bytes)
        or stream_receipt.get("content_digest")
        != f"sha256:{hashlib.sha256(result_stream_bytes).hexdigest()}"
    ):
        raise RuntimeError("native invocation result stream receipt differs from its bytes")
    decoded_results = tuple(
        deserialize_invocation_result_stream(
            BytesIO(result_stream_bytes),
            expected_result_count=stream_receipt.get("result_count"),
        )
    )
    if len(decoded_results) != context_count or not stream_receipt.get("all_succeeded"):
        raise RuntimeError("native invocation result stream is empty or contains failures")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    probe_group = parser.add_mutually_exclusive_group()
    probe_group.add_argument(
        "--context-stream-cli",
        action="store_true",
        help="exercise the runtime bundle and verified context-sidecar CLI path",
    )
    probe_group.add_argument(
        "--catalog-chunk-cli",
        action="store_true",
        help="cross the native-input writer boundary and multiple BacktestNode replay chunks",
    )
    probe_group.add_argument(
        "--native-report-schema",
        action="store_true",
        help="verify actual RC report schemas and OOS artifacts through the native report writer",
    )
    probe_group.add_argument(
        "--futures-margin",
        action="store_true",
        help="exercise a raw listed-futures order through native margin admission",
    )
    probe_group.add_argument(
        "--futures-target-margin",
        action="store_true",
        help="exercise a listed-futures target through allocation and native margin admission",
    )
    args = parser.parse_args(argv)
    if args.native_report_schema:
        result = run_native_reports_schema_probe()
    elif args.futures_margin:
        result = run_futures_margin_probe()
    elif args.futures_target_margin:
        result = run_futures_target_allocation_probe()
    elif args.context_stream_cli:
        result = run_context_stream_cli_probe()
    elif args.catalog_chunk_cli:
        result = run_context_stream_cli_probe(
            event_count=NAUTILUS_CATALOG_INPUT_CHUNK_SIZE + 5,
            replay_chunk_size=1_000,
        )
    else:
        result = run_native_backtest(
            _payload(),
            serialized_strategy_invocation_batch=_invocation_batch(),
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = [
    "main",
    "run_context_stream_cli_probe",
    "run_futures_margin_probe",
    "run_futures_target_allocation_probe",
    "run_native_reports_schema_probe",
]
