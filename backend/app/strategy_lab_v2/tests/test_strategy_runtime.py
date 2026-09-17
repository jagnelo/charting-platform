from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    StrategyContext,
    StrategyDataDependency,
    StrategySdkManifest,
    TargetPositionIntent,
    build_strategy_context,
)
from strategy_runtime import InvocationStatus, StrategyInvocationSession, run_strategy_event

NOW = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


def _manifest(source: str) -> StrategySdkManifest:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=NOW - timedelta(days=10),
        end=NOW + timedelta(days=10),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="XNYS.regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash",
        corporate_action_semantics="split-adjusted-v1",
    )
    return StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest(source)),
        (StrategyDataDependency("daily-bars", requirement, ("close",)),),
    )


def _context(manifest: StrategySdkManifest) -> StrategyContext:
    return build_strategy_context(
        manifest,
        event_time=NOW,
        event_sequence=1,
        random_seed=17,
        parameters={"threshold": Decimal("1.5")},
        market_events={
            "daily-bars": (
                MarketEvent(
                    "daily-bars",
                    "bar-1",
                    "US.AAPL",
                    NOW,
                    1,
                    {"close": Decimal("190")},
                ),
            )
        },
    )


def test_runtime_invokes_source_with_only_typed_sdk_and_validates_output() -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return [TargetPositionIntent('US.AAPL', Decimal('0.5'))]
"""
    manifest = _manifest(source)
    result = run_strategy_event(
        source,
        manifest=manifest,
        context=_context(manifest),
        entrypoint="strategy.main:Strategy",
    )

    assert result.status is InvocationStatus.SUCCEEDED
    assert result.accepted
    assert len(result.intents) == 1
    intent = result.intents[0]
    assert isinstance(intent, TargetPositionIntent)
    assert intent.instrument_id == "US.AAPL"
    assert intent.target_fraction == Decimal("0.5")
    assert result.error_digest is None
    assert result.fingerprint.startswith("sha256:")


def test_runtime_rejects_source_identity_and_static_escape_surfaces() -> None:
    source = "import os\n\nclass Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    rejected = run_strategy_event(
        source,
        manifest=manifest,
        context=_context(manifest),
        entrypoint="strategy.main:Strategy",
    )
    assert rejected.status is InvocationStatus.REJECTED
    assert any(item.startswith("source:forbidden_import") for item in rejected.rejection_reasons)

    other_source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    mismatch = run_strategy_event(
        other_source,
        manifest=manifest,
        context=_context(manifest),
        entrypoint="strategy.main:Strategy",
    )
    assert mismatch.status is InvocationStatus.REJECTED
    assert mismatch.rejection_reasons == ("source_digest_mismatch",)


def test_runtime_returns_hashed_failure_for_entrypoint_or_strategy_output_errors() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    missing = run_strategy_event(
        source,
        manifest=manifest,
        context=_context(manifest),
        entrypoint="strategy.main:Missing",
    )
    assert missing.status is InvocationStatus.FAILED
    assert missing.error_digest is not None
    assert missing.rejection_reasons == ()

    bad_source = """
class Strategy:
    def on_event(self, context):
        return [TargetPositionIntent('US.MSFT', Decimal('0.5'))]
"""
    bad_manifest = _manifest(bad_source)
    bad_output = run_strategy_event(
        bad_source,
        manifest=bad_manifest,
        context=_context(bad_manifest),
        entrypoint="strategy.main:Strategy",
    )
    assert bad_output.status is InvocationStatus.FAILED
    assert bad_output.error_digest is not None
    assert "MSFT" not in str(bad_output.error_digest)


def test_runtime_restricts_imports_even_when_called_without_a_container() -> None:
    source = """
from os import environ

class Strategy:
    def on_event(self, context):
        return []
"""
    manifest = _manifest(source)
    result = run_strategy_event(
        source,
        manifest=manifest,
        context=_context(manifest),
        entrypoint="strategy.main:Strategy",
    )
    assert result.status is InvocationStatus.REJECTED
    assert any("forbidden_import" in item for item in result.rejection_reasons)


def test_stateful_runtime_session_preserves_strategy_instance_across_events() -> None:
    source = """
class Strategy:
    def __init__(self):
        self.count = 0

    def on_event(self, context):
        self.count += 1
        return [TargetPositionIntent('US.AAPL', Decimal(self.count) / Decimal(10))]
"""
    manifest = _manifest(source)
    first = _context(manifest)
    second_event = MarketEvent(
        "daily-bars",
        "bar-2",
        "US.AAPL",
        NOW + timedelta(days=1),
        2,
        {"close": Decimal("191")},
    )
    second = build_strategy_context(
        manifest,
        event_time=NOW + timedelta(days=1),
        event_sequence=2,
        random_seed=17,
        parameters={"threshold": Decimal("1.5")},
        market_events={"daily-bars": (second_event,)},
    )
    session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint="strategy.main:Strategy",
    )
    assert session.ready
    first_result = session.invoke(first)
    second_result = session.invoke(second)
    assert first_result.status is InvocationStatus.SUCCEEDED
    assert second_result.status is InvocationStatus.SUCCEEDED
    assert isinstance(first_result.intents[0], TargetPositionIntent)
    assert isinstance(second_result.intents[0], TargetPositionIntent)
    assert first_result.intents[0].target_fraction == Decimal("0.1")
    assert second_result.intents[0].target_fraction == Decimal("0.2")


def test_stateful_runtime_session_rejects_context_drift_without_advancing_state() -> None:
    source = """
class Strategy:
    def __init__(self):
        self.count = 0

    def on_event(self, context):
        self.count += 1
        return [TargetPositionIntent('US.AAPL', Decimal(self.count) / Decimal(10))]
"""
    manifest = _manifest(source)
    first = _context(manifest)
    session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint="strategy.main:Strategy",
    )
    assert session.invoke(first).status is InvocationStatus.SUCCEEDED
    changed_parameters = replace(
        first,
        event_time=NOW + timedelta(days=1),
        event_sequence=2,
        parameters={"threshold": Decimal("9")},
    )
    rejected = session.invoke(changed_parameters)
    assert rejected.status is InvocationStatus.REJECTED
    assert rejected.rejection_reasons == ("context_parameters_changed",)
    repeated = session.invoke(first)
    assert repeated.status is InvocationStatus.REJECTED
    assert repeated.rejection_reasons == ("context_not_monotonic",)
