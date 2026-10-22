from datetime import UTC, datetime

from app.schemas.strategy import (
    StrategyCoverageBenchmarkOut,
    StrategyCoverageInstrumentOut,
    StrategyCoveragePreviewOut,
    StrategyCoverageUniverseOut,
    StrategyDefinitionSummaryOut,
    StrategyRunBatchOut,
    StrategyRunOut,
    StrategyVersionOut,
)


def test_strategy_response_schemas_serialize_timestamps_as_canonical_utc_z():
    naive = datetime(2026, 9, 12, 14, 30)
    aware = datetime(2026, 9, 12, 16, 30, tzinfo=UTC)

    version = StrategyVersionOut(
        id=1,
        strategy_id=2,
        version_number=1,
        definition_snapshot={},
        parameter_schema={},
        default_parameters={},
        universe_config={},
        benchmark_config={},
        execution_model={},
        notes=None,
        is_current=True,
        created_at=naive,
        updated_at=aware,
    )
    run = StrategyRunOut(
        id=3,
        strategy_id=2,
        strategy_version_id=1,
        requested_by_user_id=4,
        test_mode="backtest",
        status="completed",
        timeframe="D1",
        started_at=naive,
        completed_at=aware,
        date_from=naive,
        date_to=aware,
        parameter_values={},
        universe_config={},
        benchmark_config={},
        execution_assumptions={},
        engine_run_ref=None,
        result_summary={},
        artifact_manifest={},
        warning_log=[],
        error_log=None,
        created_at=naive,
        updated_at=aware,
    )
    batch = StrategyRunBatchOut(
        id=5,
        strategy_id=2,
        strategy_version_id=1,
        requested_by_user_id=4,
        label="baseline",
        test_mode="backtest",
        status="completed",
        parameter_dimensions=[],
        parameter_grid=[],
        summary={},
        created_at=naive,
        updated_at=aware,
    )
    summary = StrategyDefinitionSummaryOut(
        id=2,
        user_id=4,
        name="Breakout",
        description=None,
        source_type="custom",
        definition_type="rules",
        is_active=True,
        tags=[],
        metadata_json={},
        versions=[version],
        run_batches=[batch],
        runs=[run],
        created_at=naive,
        updated_at=aware,
    )
    instrument = StrategyCoverageInstrumentOut(
        instrument_id=7,
        symbol="SPY",
        available_from=naive,
        available_to=aware,
        requested_first_bar_at=naive,
        requested_last_bar_at=aware,
        total_bars=2,
        requested_bars=2,
        requested_status="full",
    )
    universe = StrategyCoverageUniverseOut(
        preview_mode="canonical",
        instrument_count=1,
        instruments_with_data=1,
        instruments_with_requested_data=1,
        instruments_with_full_requested_coverage=1,
        instruments_with_partial_requested_coverage=0,
        instruments_without_requested_coverage=0,
        total_bars=2,
        requested_first_bar_at=naive,
        requested_last_bar_at=aware,
        any_coverage_from=naive,
        any_coverage_to=aware,
        collective_coverage_from=naive,
        collective_coverage_to=aware,
        requested_fits_collective_range=True,
        instruments=[instrument],
    )
    benchmark = StrategyCoverageBenchmarkOut(
        symbol="SPY",
        requested_status="full",
        available_from=naive,
        available_to=aware,
        requested_first_bar_at=naive,
        requested_last_bar_at=aware,
        total_bars=2,
        requested_bars=2,
        requested_fits_range=True,
    )
    preview = StrategyCoveragePreviewOut(
        timeframe="D1",
        requested_date_from=naive,
        requested_date_to=aware,
        universe=universe,
        benchmark=benchmark,
    )

    assert version.model_dump(mode="json")["created_at"] == "2026-09-12T14:30:00Z"
    run_payload = run.model_dump(mode="json")
    assert run_payload["started_at"] == "2026-09-12T14:30:00Z"
    assert run_payload["completed_at"] == "2026-09-12T16:30:00Z"
    assert run_payload["date_to"] == "2026-09-12T16:30:00Z"
    assert batch.model_dump(mode="json")["updated_at"] == "2026-09-12T16:30:00Z"
    summary_payload = summary.model_dump(mode="json")
    assert summary_payload["created_at"] == "2026-09-12T14:30:00Z"
    assert summary_payload["runs"][0]["updated_at"] == "2026-09-12T16:30:00Z"
    assert instrument.model_dump(mode="json")["available_from"] == "2026-09-12T14:30:00Z"
    universe_payload = universe.model_dump(mode="json")
    assert universe_payload["collective_coverage_to"] == "2026-09-12T16:30:00Z"
    assert universe_payload["instruments"][0]["requested_last_bar_at"] == ("2026-09-12T16:30:00Z")
    assert benchmark.model_dump(mode="json")["requested_first_bar_at"] == ("2026-09-12T14:30:00Z")
    assert preview.model_dump(mode="json")["requested_date_to"] == "2026-09-12T16:30:00Z"
