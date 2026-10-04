from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]
import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    PortfolioComponent,
    PortfolioComposition,
)
from app.strategy_lab_v2.metrics import METRIC_DEFINITION_VERSION
from app.strategy_lab_v2.nautilus_equity_trace import (
    NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
    NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
    NautilusAccountEquityTraceReference,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsWriter
from app.strategy_lab_v2.nautilus_result_metrics import (
    build_nautilus_oos_equity_metric_set,
    build_nautilus_oos_metric_set,
)


def _portfolio_composition() -> PortfolioComposition:
    return PortfolioComposition(
        portfolio_id="portfolio-1",
        version_id="portfolio-version-1",
        initial_capital=Decimal("1000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="alpha",
                strategy_fingerprint=content_digest("strategy-alpha"),
                instrument_ids=("AAPL.SIM",),
                capital_weight=Decimal("0.5"),
            ),
            PortfolioComponent(
                component_id="beta",
                strategy_fingerprint=content_digest("strategy-beta"),
                instrument_ids=("AAPL.SIM",),
                capital_weight=Decimal("0.5"),
            ),
        ),
    )


def _reference(
    *,
    windowed: bool = True,
    portfolio: PortfolioComposition | None = None,
) -> NautilusAccountEquityTraceReference:
    artifact_digest = content_digest("account-equity-trace")
    artifact = ArtifactManifest(
        content_digest=artifact_digest,
        byte_length=128,
        media_type=NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
        schema_version=NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
        storage_key=artifact_digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    return NautilusAccountEquityTraceReference(
        artifact=artifact,
        trial_id=content_digest("trial"),
        attempt_id="attempt-1",
        portfolio_fingerprint=(
            content_digest("portfolio") if portfolio is None else portfolio.fingerprint
        ),
        snapshot_fingerprint=content_digest("snapshot"),
        source_tape_fingerprint=content_digest("source-tape"),
        evaluation_window_fingerprint=(content_digest("evaluation-window") if windowed else None),
        scoring_start_ns=100 if windowed else None,
        scoring_end_ns=200 if windowed else None,
        base_currency="USD",
        initial_capital=Decimal("1000"),
        observation_count=3,
    )


def _metric_set_for_positions(tmp_path, positions: list[dict[str, object]]):
    equity_reference = _reference()
    reports_path = tmp_path / "position-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD"}]),
            "fills": pd.DataFrame(columns=["ts_event", "commission"]),
            "orders": pd.DataFrame(columns=["ts_init"]),
            "positions": pd.DataFrame(positions),
        }
    )
    reports_reference = writer.finish()
    return build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1020"), Decimal("1010")),
        reports_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )


def test_build_nautilus_oos_equity_metric_set_binds_trial_attempt_and_trace() -> None:
    reference = _reference()
    metric_set = build_nautilus_oos_equity_metric_set(
        reference,
        (Decimal("1200"), Decimal("1300"), Decimal("1260")),
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metric_set.trial_id == reference.trial_id
    assert metric_set.attempt_id == reference.attempt_id
    assert metric_set.definition_version == METRIC_DEFINITION_VERSION
    assert metrics["total_pnl"].value == Decimal("60")
    assert metrics["total_return"].value == Decimal("0.05")
    assert metrics["total_return"].evidence_references[0].digest == (
        reference.artifact.content_digest
    )
    assert metrics["annualized_return"].value is None


def test_build_nautilus_oos_equity_metric_set_rejects_non_oos_receipts() -> None:
    reference = _reference(windowed=False)

    with pytest.raises(ValueError, match="require an OOS evaluation window"):
        build_nautilus_oos_equity_metric_set(
            reference,
            (Decimal("1200"), Decimal("1300"), Decimal("1260")),
            created_at=datetime(2026, 10, 4, tzinfo=UTC),
        )


def test_build_nautilus_oos_metric_set_filters_and_binds_native_reports(tmp_path) -> None:
    equity_reference = _reference()
    reports_path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD", "total": "1,000.00"}]),
            "fills": pd.DataFrame(
                [
                    {"ts_event": 99, "commission": "1.00 USD"},
                    {"ts_event": 100, "commission": "1.25 USD"},
                    {"ts_event": 199, "commission": None},
                    {"ts_event": 200, "commission": "4.00 USD"},
                ]
            ),
            "orders": pd.DataFrame([{"ts_init": 100}, {"ts_init": 200}]),
            "positions": pd.DataFrame(
                [
                    {
                        "ts_opened": 150,
                        "ts_closed": 190,
                        "realized_pnl": "12.50 USD",
                    },
                    {"ts_opened": 50, "ts_closed": None, "realized_pnl": None},
                ]
            ),
        }
    )
    report_reference = writer.finish()

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1020"), Decimal("1010")),
        report_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_fill_count"].value == Decimal(2)
    assert metrics["oos_order_submission_count"].value == Decimal(1)
    assert metrics["oos_position_records_opened_count"].value == Decimal(1)
    assert metrics["oos_position_records_closed_count"].value == Decimal(1)
    assert metrics["oos_commission_reported_fill_count"].value == Decimal(1)
    assert metrics["oos_commission_unreported_fill_count"].value == Decimal(1)
    assert metrics["oos_commission_reporting_coverage"].value == Decimal("0.5")
    assert metrics["oos_reported_commission:USD"].value == Decimal("1.25")
    assert metrics["oos_reported_realized_position_pnl:USD"].value == Decimal("12.50")
    assert metrics["oos_realized_position_win_count"].value == Decimal(1)
    assert metrics["oos_realized_position_loss_count"].value == Decimal(0)
    assert metrics["oos_realized_position_win_rate"].value == Decimal(1)
    assert metrics["oos_realized_position_break_even_rate"].value == Decimal(0)
    assert metrics["oos_reported_commission:USD"].evidence_references[0].digest == (
        report_reference.artifact.content_digest
    )
    assert (
        metric_set.metric_set_id
        != build_nautilus_oos_equity_metric_set(
            equity_reference,
            (Decimal("1000"), Decimal("1020"), Decimal("1010")),
            created_at=datetime(2026, 10, 4, tzinfo=UTC),
        ).metric_set_id
    )


def test_build_nautilus_oos_metric_set_reconciles_native_component_pnl_and_costs(tmp_path) -> None:
    portfolio = _portfolio_composition()
    equity_reference = _reference(portfolio=portfolio)
    reports_path = tmp_path / "component-native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": portfolio.fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD", "total": "1,060.00"}]),
            "orders": pd.DataFrame(
                [
                    {"tags": ["strategy-lab-v2:component:alpha"]},
                    {"tags": ["strategy-lab-v2:component:alpha"]},
                ],
                index=pd.Index(["buy-1", "sell-1"], name="client_order_id"),
            ),
            "fills": pd.DataFrame(
                [
                    {
                        "position_id": "position-1",
                        "trade_id": "trade-1",
                        "commission": "1.50 USD",
                        "ts_event": 110,
                    },
                    {
                        "position_id": "position-1",
                        "trade_id": "trade-2",
                        "commission": "-0.50 USD",
                        "ts_event": 150,
                    },
                ],
                index=pd.Index(["buy-1", "sell-1"], name="client_order_id"),
            ),
            "positions": pd.DataFrame(
                [
                    {
                        "events": [
                            {
                                "client_order_id": "buy-1",
                                "trade_id": "trade-1",
                                "type": "OrderFilled",
                            },
                            {
                                "client_order_id": "sell-1",
                                "trade_id": "trade-2",
                                "type": "OrderFilled",
                            },
                        ],
                        "trade_ids": ["trade-1", "trade-2"],
                        "ts_opened": 105,
                        "ts_closed": 151,
                        "realized_pnl": "28.00 USD",
                    }
                ],
                # Archived cycles use generated report IDs, distinct from
                # the fill's original position_id; trade IDs prove the join.
                index=pd.Index(["position-1.snapshot-1"], name="position_id"),
            ),
        }
    )
    reports_reference = writer.finish()

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1030"), Decimal("1060")),
        reports_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
        portfolio=portfolio,
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["portfolio_attributed_net_pnl"].value == Decimal("60")
    assert metrics["portfolio_attributed_gross_pnl"].value == Decimal("61")
    assert metrics["component_net_pnl:alpha"].value == Decimal("28.00")
    assert metrics["component_gross_pnl:alpha"].value == Decimal("29.00")
    assert metrics["component_net_pnl:beta"].value == Decimal(0)
    assert metrics["component_net_pnl:__unallocated__"].value == Decimal("32.00")
    assert metrics["component_gross_pnl:__unallocated__"].value == Decimal("32.00")


def test_component_pnl_is_unavailable_when_native_fee_currency_needs_fx(tmp_path) -> None:
    portfolio = _portfolio_composition()
    equity_reference = _reference(portfolio=portfolio)
    reports_path = tmp_path / "foreign-fee-native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": portfolio.fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD", "total": "1,010.00"}]),
            "orders": pd.DataFrame(
                [{"tags": ["strategy-lab-v2:component:alpha"]}],
                index=pd.Index(["order-1"], name="client_order_id"),
            ),
            "fills": pd.DataFrame(
                [{"position_id": "position-1", "commission": "1.00 EUR", "ts_event": 110}],
                index=pd.Index(["order-1"], name="client_order_id"),
            ),
            "positions": pd.DataFrame(columns=["client_order_ids", "ts_opened", "ts_closed"]),
        }
    )
    reports_reference = writer.finish()

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1010"), Decimal("1010")),
        reports_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
        portfolio=portfolio,
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["component_net_pnl:alpha"].value is None
    assert "no FX conversion is inferred" in (metrics["component_net_pnl:alpha"].null_reason or "")


def test_native_realized_position_quality_is_currency_safe_and_oos_scoped(tmp_path) -> None:
    metric_set = _metric_set_for_positions(
        tmp_path,
        [
            {"ts_opened": 105, "ts_closed": 110, "realized_pnl": "2 USD"},
            {"ts_opened": 115, "ts_closed": 120, "realized_pnl": "-3 EUR"},
            {"ts_opened": 125, "ts_closed": 130, "realized_pnl": "0 USD"},
            {"ts_opened": 99, "ts_closed": 200, "realized_pnl": "9 USD"},
        ],
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_position_records_closed_count"].value == Decimal(3)
    assert metrics["oos_realized_position_win_count"].value == Decimal(1)
    assert metrics["oos_realized_position_loss_count"].value == Decimal(1)
    assert metrics["oos_realized_position_break_even_count"].value == Decimal(1)
    third = Decimal("0.3333333333333333333333333333333333")
    assert metrics["oos_realized_position_win_rate"].value == third
    assert metrics["oos_realized_position_loss_rate"].value == third
    assert metrics["oos_realized_position_break_even_rate"].value == third
    assert metrics["oos_realized_position_win_rate"].unit == "fraction"
    assert metrics["oos_realized_position_win_rate"].sample_size == 3
    assert metrics["oos_realized_position_profit_factor:USD"].value is None
    assert metrics["oos_realized_position_profit_factor:USD"].null_reason == (
        "no losing OOS-closed positions in USD"
    )
    assert metrics["oos_realized_position_mean_pnl:USD"].value == Decimal(1)
    assert metrics["oos_realized_position_mean_win_pnl:USD"].value == Decimal(2)
    assert metrics["oos_realized_position_mean_loss_pnl:USD"].value is None
    assert metrics["oos_realized_position_mean_loss_pnl:USD"].null_reason == (
        "no losing OOS-closed positions in USD"
    )
    assert metrics["oos_realized_position_win_loss_ratio:USD"].value is None
    assert metric_set.definition_version == "strategy-lab.metrics.v11"
    assert (
        metrics["oos_realized_position_profit_factor:USD"].calculation_definition.parameters[
            "decimal_precision"
        ]
        == 34
    )
    assert (
        metrics["oos_realized_position_profit_factor:USD"].calculation_definition.parameters[
            "decimal_rounding"
        ]
        == "ROUND_HALF_EVEN"
    )
    assert (
        metrics["oos_realized_position_win_rate"].calculation_definition.parameters[
            "currency_aggregation"
        ]
        == "sign_only; native currencies are not summed"
    )


def test_native_realized_position_distribution_and_profit_factor_are_currency_scoped(
    tmp_path,
) -> None:
    metric_set = _metric_set_for_positions(
        tmp_path,
        [
            {"ts_opened": 105, "ts_closed": 110, "realized_pnl": "20 USD"},
            {"ts_opened": 115, "ts_closed": 120, "realized_pnl": "-5 USD"},
            {"ts_opened": 125, "ts_closed": 130, "realized_pnl": "4 EUR"},
            {"ts_opened": 135, "ts_closed": 140, "realized_pnl": "-8 EUR"},
            {"ts_opened": 145, "ts_closed": 150, "realized_pnl": "0 EUR"},
        ],
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_realized_position_win_count:USD"].value == Decimal(1)
    assert metrics["oos_realized_position_loss_count:USD"].value == Decimal(1)
    assert metrics["oos_realized_position_win_rate:USD"].value == Decimal("0.5")
    assert metrics["oos_realized_position_gross_winning_pnl:USD"].value == Decimal(20)
    assert metrics["oos_realized_position_gross_losing_pnl_magnitude:USD"].value == Decimal(5)
    assert metrics["oos_realized_position_profit_factor:USD"].value == Decimal(4)
    assert metrics["oos_realized_position_mean_pnl:USD"].value == Decimal("7.5")
    assert metrics["oos_realized_position_mean_win_pnl:USD"].value == Decimal(20)
    assert metrics["oos_realized_position_mean_loss_pnl:USD"].value == Decimal(-5)
    assert metrics["oos_realized_position_win_loss_ratio:USD"].value == Decimal(4)
    assert metrics["oos_realized_position_pnl_quantile_p05:USD"].value == Decimal(-5)
    assert metrics["oos_realized_position_pnl_quantile_p25:USD"].value == Decimal(-5)
    assert metrics["oos_realized_position_pnl_quantile_p50:USD"].value == Decimal(-5)
    assert metrics["oos_realized_position_pnl_quantile_p75:USD"].value == Decimal(20)
    assert metrics["oos_realized_position_pnl_quantile_p95:USD"].value == Decimal(20)
    assert metrics["oos_realized_position_win_count:EUR"].value == Decimal(1)
    assert metrics["oos_realized_position_loss_count:EUR"].value == Decimal(1)
    assert metrics["oos_realized_position_break_even_count:EUR"].value == Decimal(1)
    assert metrics["oos_realized_position_win_rate:EUR"].value == Decimal(
        "0.3333333333333333333333333333333333"
    )
    assert metrics["oos_realized_position_profit_factor:EUR"].value == Decimal("0.5")
    assert metrics["oos_realized_position_mean_pnl:EUR"].value == Decimal(
        "-1.333333333333333333333333333333333"
    )
    assert metrics["oos_realized_position_mean_win_pnl:EUR"].value == Decimal(4)
    assert metrics["oos_realized_position_mean_loss_pnl:EUR"].value == Decimal(-8)
    assert metrics["oos_realized_position_win_loss_ratio:EUR"].value == Decimal("0.5")
    assert metrics["oos_realized_position_pnl_quantile_p05:EUR"].value == Decimal(-8)
    assert metrics["oos_realized_position_pnl_quantile_p25:EUR"].value == Decimal(-8)
    assert metrics["oos_realized_position_pnl_quantile_p50:EUR"].value == Decimal(0)
    assert metrics["oos_realized_position_pnl_quantile_p75:EUR"].value == Decimal(4)
    assert metrics["oos_realized_position_pnl_quantile_p95:EUR"].value == Decimal(4)
    assert metrics["oos_realized_position_profit_factor:USD"].unit == "ratio"
    assert metrics["oos_realized_position_profit_factor:USD"].sample_size == 2
    assert metrics["oos_realized_position_mean_pnl:USD"].sample_size == 2
    assert metrics["oos_realized_position_mean_win_pnl:USD"].sample_size == 1
    assert metrics["oos_realized_position_mean_loss_pnl:USD"].sample_size == 1
    assert metrics["oos_realized_position_pnl_quantile_p95:USD"].sample_size == 2
    assert (
        metrics["oos_realized_position_profit_factor:EUR"].calculation_definition.parameters[
            "currency_aggregation"
        ]
        == "within_currency_only; no FX conversion"
    )
    assert (
        metrics["oos_realized_position_win_loss_ratio:USD"].calculation_definition.formula_id
        == "strategy-lab.metrics/oos_realized_position_win_loss_ratio"
    )


def test_native_oos_position_holding_duration_uses_full_lifecycle_and_explicit_median(
    tmp_path,
) -> None:
    metric_set = _metric_set_for_positions(
        tmp_path,
        [
            {"ts_opened": 105, "ts_closed": 110, "realized_pnl": "1 USD"},
            {"ts_opened": 114, "ts_closed": 120, "realized_pnl": "2 USD"},
            {"ts_opened": 121, "ts_closed": 130, "realized_pnl": "3 USD"},
            # Closing in OOS includes the complete lifecycle even when opening
            # precedes the scoring window.
            {"ts_opened": 99, "ts_closed": 140, "realized_pnl": "4 USD"},
            # A position closing exactly at the OOS end is excluded even though
            # its full lifecycle begins before the scoring window.
            {"ts_opened": 99, "ts_closed": 200, "realized_pnl": "4 USD"},
        ],
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_position_holding_duration_reported_count"].value == Decimal(4)
    assert metrics["oos_position_holding_duration_coverage"].value == Decimal(1)
    assert metrics["oos_position_mean_holding_duration_seconds"].value == Decimal("0.00000001525")
    assert metrics["oos_position_median_holding_duration_seconds"].value == Decimal("0.0000000075")
    mean = metrics["oos_position_mean_holding_duration_seconds"]
    assert mean.unit == "seconds"
    assert mean.sample_size == 4
    assert mean.calculation_definition.parameters["duration_basis"] == (
        "full_position_lifecycle_elapsed_time"
    )
    assert mean.calculation_definition.parameters["timestamp_unit"] == "unix_nanoseconds"


def test_native_oos_position_holding_duration_withholds_incomplete_open_times(tmp_path) -> None:
    metric_set = _metric_set_for_positions(
        tmp_path,
        [
            {"ts_opened": 105, "ts_closed": 110, "realized_pnl": "1 USD"},
            {"ts_opened": None, "ts_closed": 120, "realized_pnl": "2 USD"},
            # Null close times are live positions, not malformed closed rows.
            {"ts_opened": 190, "ts_closed": None, "realized_pnl": None},
        ],
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_position_records_closed_count"].value == Decimal(2)
    assert metrics["oos_position_holding_duration_reported_count"].value == Decimal(1)
    assert metrics["oos_position_holding_duration_coverage"].value == Decimal("0.5")
    for name in (
        "oos_position_mean_holding_duration_seconds",
        "oos_position_median_holding_duration_seconds",
    ):
        assert metrics[name].value is None
        assert metrics[name].sample_size == 1
        assert metrics[name].null_reason == (
            "native positions report lacks ts_opened for one or more OOS-closed positions"
        )


def test_native_oos_position_holding_duration_rejects_reversed_timestamps(tmp_path) -> None:
    with pytest.raises(ValueError, match="ts_opened must not follow ts_closed"):
        _metric_set_for_positions(
            tmp_path,
            [{"ts_opened": 121, "ts_closed": 120, "realized_pnl": "1 USD"}],
        )


def test_native_realized_position_quality_fails_closed_on_missing_pnl(tmp_path) -> None:
    metric_set = _metric_set_for_positions(
        tmp_path,
        [
            {"ts_opened": 105, "ts_closed": 110, "realized_pnl": "2 USD"},
            {"ts_opened": 115, "ts_closed": 120, "realized_pnl": None},
        ],
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_realized_position_win_count"].value is None
    assert metrics["oos_realized_position_win_rate"].value is None
    assert "missing" in (metrics["oos_realized_position_win_rate"].null_reason or "")
    assert metrics["oos_realized_pnl_reported_position_count"].value == Decimal(1)
    assert metrics["oos_realized_pnl_unreported_position_count"].value == Decimal(1)
    assert metrics["oos_realized_position_profit_factor:USD"].value is None
    assert "missing" in (metrics["oos_realized_position_profit_factor:USD"].null_reason or "")
    assert metrics["oos_realized_position_mean_pnl:USD"].value is None
    assert "missing" in (metrics["oos_realized_position_mean_pnl:USD"].null_reason or "")
    assert metrics["oos_realized_position_pnl_quantile_p95:USD"].value is None
    assert "missing" in (metrics["oos_realized_position_pnl_quantile_p95:USD"].null_reason or "")


def test_build_nautilus_oos_metric_set_rejects_report_scope_mismatch(tmp_path) -> None:
    equity_reference = _reference()
    writer = NautilusNativeReportsWriter(
        tmp_path / "native-reports.parquet",
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": content_digest("different-snapshot"),
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD"}]),
            "fills": pd.DataFrame(columns=["ts_event", "commission"]),
            "orders": pd.DataFrame(columns=["ts_init"]),
            "positions": pd.DataFrame(columns=["ts_opened", "ts_closed"]),
        }
    )
    report_reference = writer.finish()

    with pytest.raises(ValueError, match="do not share one OOS scope"):
        build_nautilus_oos_metric_set(
            equity_reference,
            (Decimal("1000"), Decimal("1020"), Decimal("1010")),
            report_reference,
            tmp_path / "native-reports.parquet",
            created_at=datetime(2026, 10, 4, tzinfo=UTC),
        )


def test_build_nautilus_oos_metric_set_marks_incomplete_timestamps_unavailable(tmp_path) -> None:
    equity_reference = _reference()
    reports_path = tmp_path / "native-reports.parquet"
    writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input={
            "trial_id": equity_reference.trial_id,
            "attempt_id": equity_reference.attempt_id,
            "data_snapshot_fingerprint": equity_reference.snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": equity_reference.source_tape_fingerprint,
            },
            "evaluation_window": {
                "fingerprint": equity_reference.evaluation_window_fingerprint,
                "start_ns": equity_reference.scoring_start_ns,
                "end_ns": equity_reference.scoring_end_ns,
            },
        },
        portfolio={"fingerprint": equity_reference.portfolio_fingerprint},
    )
    writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD"}]),
            "fills": pd.DataFrame(
                [
                    {"ts_event": 100, "commission": "1.00 USD"},
                    {"commission": "2.00 USD"},
                ]
            ),
            "orders": pd.DataFrame(columns=["ts_init"]),
            "positions": pd.DataFrame(columns=["ts_opened", "ts_closed"]),
        }
    )
    reports_reference = writer.finish()

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        (Decimal("1000"), Decimal("1020"), Decimal("1010")),
        reports_reference,
        reports_path,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    metrics = {item.name: item for item in metric_set.values}

    assert metrics["oos_fill_count"].value is None
    assert "timestamp" in (metrics["oos_fill_count"].null_reason or "")
    assert metrics["oos_commission_reported_fill_count"].value is None
    assert metrics["oos_commission_reporting_coverage"].value is None
    assert "timestamp" in (metrics["oos_commission_reporting_coverage"].null_reason or "")
