from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState


class TestCoverageRouter:
    def test_exposes_missing_range_without_provider_routing(self, client, auth_headers, instrument):
        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": "2026-01-02T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
                "mode": "historical",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body == {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "timeframe": "D1",
            "adjusted": True,
            "mode": "historical",
            "requested_start": "2026-01-02T00:00:00Z",
            "requested_end": "2026-01-02T00:00:00Z",
            "status": "missing",
            "covered_start": None,
            "covered_end": None,
            "bar_count": 0,
            "missing_slices": [{"start": "2026-01-02T00:00:00Z", "end": "2026-01-02T00:00:00Z"}],
            "explanation": "No local bars cover the requested range.",
            "lineage": {
                "provider_bar_count": 0,
                "derived_bar_count": 0,
                "unknown_bar_count": 0,
                "source_lineage": "unavailable",
                "source_timeframes": [],
            },
            "adjustment_provenance": {
                "mode": "split_adjusted",
                "source_kind": "unavailable",
                "factor_status": "not_observed",
                "factor_version": None,
                "contract_version": 1,
            },
            "storage_evidence": {
                "status": "not_observed",
                "provider_bar_count": 0,
                "observation_count": 0,
                "matched_observation_count": 0,
                "missing_observation_count": 0,
                "mismatched_observation_count": 0,
                "orphan_observation_count": 0,
            },
            "observed_cadence": {
                "status": "no_observation",
                "sample_count": 0,
                "median_interval_days": None,
                "min_interval_days": None,
                "max_interval_days": None,
                "semantics": "diagnostic_of_returned_bar_timestamps_only",
            },
            "provenance": "canonical_local_database",
        }

    def test_exposes_fully_covered_range_without_provider_routing(
        self, client, auth_headers, db, instrument
    ):
        session = datetime(2026, 1, 2, tzinfo=UTC)
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=session,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=Decimal("100"),
                is_adjusted=True,
            )
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": "2026-01-02T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
                "mode": "historical",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body == {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "timeframe": "D1",
            "adjusted": True,
            "mode": "historical",
            "requested_start": "2026-01-02T00:00:00Z",
            "requested_end": "2026-01-02T00:00:00Z",
            "status": "ready",
            "covered_start": "2026-01-02T00:00:00Z",
            "covered_end": "2026-01-02T00:00:00Z",
            "bar_count": 1,
            "missing_slices": [],
            "explanation": "The requested range is locally covered.",
            "lineage": {
                "provider_bar_count": 1,
                "derived_bar_count": 0,
                "unknown_bar_count": 0,
                "source_lineage": "provider_only",
                "source_timeframes": [],
            },
            "adjustment_provenance": {
                "mode": "split_adjusted",
                "source_kind": "provider_observation",
                "factor_status": "provider_native_opaque",
                "factor_version": None,
                "contract_version": 1,
            },
            "storage_evidence": {
                "status": "not_observed",
                "provider_bar_count": 0,
                "observation_count": 0,
                "matched_observation_count": 0,
                "missing_observation_count": 0,
                "mismatched_observation_count": 0,
                "orphan_observation_count": 0,
            },
            "observed_cadence": {
                "status": "single_observation",
                "sample_count": 0,
                "median_interval_days": None,
                "min_interval_days": None,
                "max_interval_days": None,
                "semantics": "diagnostic_of_returned_bar_timestamps_only",
            },
            "provenance": "canonical_local_database",
        }

    def test_returns_canonical_local_coverage_without_provider_routing(
        self, client, auth_headers, db, instrument
    ):
        start = datetime.now(UTC) - timedelta(days=1)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=start,
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    volume=Decimal("100"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=start + timedelta(days=1),
                    open=Decimal("11"),
                    high=Decimal("12"),
                    low=Decimal("10"),
                    close=Decimal("11"),
                    volume=Decimal("101"),
                    is_adjusted=True,
                ),
                InstrumentDatasetState(
                    instrument_id=instrument.id,
                    data_source_id=None,
                    dataset_type="ohlcv",
                    dataset_key="D1",
                    status=DatasetStatus.STALE,
                    coverage_start=start,
                    coverage_end=start + timedelta(days=1),
                    version=2,
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}", headers=auth_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["provenance"] == "canonical_local_database"
        assert body["local_coverage"]["D1"]["bar_count"] == 2
        assert len(body["dataset_states"]) == 1
        state = body["dataset_states"][0]
        assert state["dataset_type"] == "ohlcv"
        assert state["dataset_key"] == "D1"
        assert state["status"] == "stale"
        assert state["version"] == 2
        assert "provider" not in body

    def test_requires_auth(self, client, instrument):
        response = client.get(f"/api/v1/coverage/instruments/{instrument.symbol}")

        assert response.status_code == 401

    def test_exposes_provider_neutral_range_readiness_and_bounded_slices(
        self, client, auth_headers, db, instrument
    ):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=start,
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=start + timedelta(days=1),
                    open=Decimal("11"),
                    high=Decimal("12"),
                    low=Decimal("10"),
                    close=Decimal("11"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=start + timedelta(days=9),
                    open=Decimal("12"),
                    high=Decimal("13"),
                    low=Decimal("11"),
                    close=Decimal("12"),
                    is_adjusted=True,
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
                "mode": "historical",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "timeframe": "D1",
            "adjusted": True,
            "mode": "historical",
            "requested_start": "2026-01-01T00:00:00Z",
            "requested_end": "2026-01-10T00:00:00Z",
            "status": "partial",
            "covered_start": "2026-01-01T00:00:00Z",
            "covered_end": "2026-01-10T00:00:00Z",
            "bar_count": 3,
            "missing_slices": [{"start": "2026-01-05T00:00:00Z", "end": "2026-01-09T00:00:00Z"}],
            "explanation": "Local bars leave one or more bounded range slices unavailable.",
            "lineage": {
                "provider_bar_count": 3,
                "derived_bar_count": 0,
                "unknown_bar_count": 0,
                "source_lineage": "provider_only",
                "source_timeframes": [],
            },
            "adjustment_provenance": {
                "mode": "split_adjusted",
                "source_kind": "provider_observation",
                "factor_status": "provider_native_opaque",
                "factor_version": None,
                "contract_version": 1,
            },
            "storage_evidence": {
                "status": "not_observed",
                "provider_bar_count": 0,
                "observation_count": 0,
                "matched_observation_count": 0,
                "missing_observation_count": 0,
                "mismatched_observation_count": 0,
                "orphan_observation_count": 0,
            },
            "observed_cadence": {
                "status": "observed_cadence",
                "sample_count": 2,
                "median_interval_days": 4.5,
                "min_interval_days": 1.0,
                "max_interval_days": 8.0,
                "semantics": "diagnostic_of_returned_bar_timestamps_only",
            },
            "provenance": "canonical_local_database",
        }

    def test_rejects_reversed_coverage_ranges(self, client, auth_headers, instrument):
        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "start": "2026-01-10T00:00:00Z",
                "end": "2026-01-01T00:00:00Z",
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_coverage_range"
