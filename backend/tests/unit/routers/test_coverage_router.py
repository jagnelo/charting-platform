from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState


class TestCoverageRouter:
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
                    extra_data={
                        "bar_count": 2,
                        "adjusted": True,
                        "adjustment": "split_adjusted",
                        "source_kind": "provider_observation",
                        "provider_source_id": 1,
                        "adjustment_provenance": {
                            "mode": "split_adjusted",
                            "source_kind": "provider_observation",
                            "factor_status": "provider_native_opaque",
                            "factor_version": None,
                            "contract_version": 1,
                        },
                    },
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
        assert state["extra_data"]["adjustment"] == "split_adjusted"
        assert state["extra_data"]["source_kind"] == "provider_observation"
        assert state["extra_data"]["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "provider_observation",
            "factor_status": "provider_native_opaque",
            "factor_version": None,
            "contract_version": 1,
        }
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
        assert body["status"] == "partial"
        assert body["bar_count"] == 3
        assert body["missing_slices"] == [
            {"start": "2026-01-05T00:00:00Z", "end": "2026-01-09T00:00:00Z"}
        ]
        assert body["provenance"] == "canonical_local_database"
        assert body["lineage"] == {
            "provider_bar_count": 3,
            "derived_bar_count": 0,
            "unknown_bar_count": 0,
            "source_lineage": "provider_only",
            "source_timeframes": [],
        }
        assert body["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "provider_observation",
            "factor_status": "provider_native_opaque",
            "factor_version": None,
            "contract_version": 1,
        }
        assert body["observed_cadence"] == {
            "status": "observed_cadence",
            "sample_count": 2,
            "median_interval_days": 4.5,
            "min_interval_days": 1.0,
            "max_interval_days": 8.0,
            "semantics": "diagnostic_of_returned_bar_timestamps_only",
        }
        assert "provider" not in body

    def test_range_coverage_exposes_verified_adjustment_factor_version(
        self, client, auth_headers, db, instrument
    ):
        from app.models.data_source import DataSource
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import DatasetStatus, InstrumentDatasetState

        source = DataSource(name="coverage-factor-provider")
        db.add(source)
        db.flush()
        start = datetime(2026, 1, 2, tzinfo=UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=source.id,
                    timeframe=Timeframe.D1,
                    ts=start,
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    is_adjusted=True,
                ),
                InstrumentDatasetState(
                    instrument_id=instrument.id,
                    data_source_id=source.id,
                    dataset_type="ohlcv",
                    dataset_key="D1:adj",
                    status=DatasetStatus.FRESH,
                    observed_at=start,
                    fetched_at=start,
                    coverage_start=start,
                    coverage_end=start,
                    version=1,
                    extra_data={
                        "adjustment_provenance": {
                            "mode": "split_adjusted",
                            "source_kind": "provider_observation",
                            "factor_status": "rebuildable_split_factors",
                            "factor_version": "afv1-test-version",
                            "factor_observation_count": 2,
                            "factor_rebuildable_observation_count": 2,
                            "factor_opaque_observation_count": 0,
                            "factor_kinds": ["split_ratio"],
                            "contract_version": 1,
                        }
                    },
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": start.isoformat(),
                "end": start.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "provider_observation",
            "factor_status": "rebuildable_split_factors",
            "factor_version": "afv1-test-version",
            "factor_observation_count": 2,
            "factor_rebuildable_observation_count": 2,
            "factor_opaque_observation_count": 0,
            "factor_kinds": ["split_ratio"],
            "contract_version": 1,
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

    def test_range_coverage_normalizes_offset_aware_request_boundaries(
        self, client, auth_headers, db, instrument
    ):
        start = datetime(2026, 1, 2, tzinfo=UTC)
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=start,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                is_adjusted=True,
            )
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                # These are the same instants as 2026-01-02T00:00:00Z and
                # 2026-01-03T00:00:00Z, expressed with a non-UTC offset.
                "start": "2026-01-02T02:00:00+02:00",
                "end": "2026-01-03T02:00:00+02:00",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["requested_start"] == "2026-01-02T00:00:00Z"
        assert body["requested_end"] == "2026-01-03T00:00:00Z"
        assert body["covered_start"] == "2026-01-02T00:00:00Z"
        assert body["bar_count"] == 1

    def test_range_coverage_exposes_derived_factor_version(
        self, client, auth_headers, db, instrument
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import DatasetStatus, InstrumentDatasetState

        start = datetime(2026, 2, 2, tzinfo=UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.W1,
                    ts=start,
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    is_adjusted=True,
                    is_derived=True,
                    source_timeframe="D1",
                ),
                InstrumentDatasetState(
                    instrument_id=instrument.id,
                    data_source_id=None,
                    dataset_type="ohlcv",
                    dataset_key="W1:adj",
                    status=DatasetStatus.FRESH,
                    observed_at=start,
                    fetched_at=start,
                    coverage_start=start,
                    coverage_end=start,
                    version=1,
                    extra_data={
                        "adjustment_provenance": {
                            "mode": "split_adjusted",
                            "source_kind": "derived_from_canonical_d1",
                            "factor_status": "inherited_from_canonical_d1",
                            "factor_version": "afv1-derived-version",
                            "contract_version": 1,
                        }
                    },
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "W1",
                "start": start.isoformat(),
                "end": start.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "derived_from_canonical_d1",
            "factor_status": "inherited_from_canonical_d1",
            "factor_version": "afv1-derived-version",
            "contract_version": 1,
        }

    def test_range_coverage_prefers_lineage_specific_state_over_generic_state(
        self, client, auth_headers, db, instrument
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import DatasetStatus, InstrumentDatasetState

        start = datetime(2026, 2, 3, tzinfo=UTC)
        provenance = {
            "mode": "split_adjusted",
            "source_kind": "local_split_ratio",
            "factor_status": "rebuildable_split_factors",
            "factor_version": "afv1-local-specific",
            "contract_version": 1,
        }
        generic_provenance = {
            **provenance,
            "factor_version": "afv1-generic-fallback",
        }
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
                    is_derived=True,
                    derivation_method="local_split_ratio",
                    source_timeframe="D1",
                ),
                InstrumentDatasetState(
                    instrument_id=instrument.id,
                    data_source_id=None,
                    dataset_type="ohlcv",
                    dataset_key="D1:adj",
                    status=DatasetStatus.FRESH,
                    observed_at=start,
                    fetched_at=start,
                    coverage_start=start,
                    coverage_end=start,
                    version=1,
                    extra_data={"adjustment_provenance": generic_provenance},
                ),
                InstrumentDatasetState(
                    instrument_id=instrument.id,
                    data_source_id=None,
                    dataset_type="ohlcv",
                    dataset_key="D1:adj:local_split_ratio",
                    status=DatasetStatus.FRESH,
                    observed_at=start,
                    fetched_at=start,
                    coverage_start=start,
                    coverage_end=start,
                    version=2,
                    extra_data={"adjustment_provenance": provenance},
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": start.isoformat(),
                "end": start.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["adjustment_provenance"]["factor_version"] == ("afv1-local-specific")

    def test_range_coverage_does_not_project_future_factor_state(
        self, client, auth_headers, db, instrument
    ):
        from app.models.data_source import DataSource

        source = DataSource(name="coverage-future-factor-provider")
        db.add(source)
        db.flush()
        start = datetime(2026, 1, 2, tzinfo=UTC)
        cutoff = start + timedelta(days=1)
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=start,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                is_adjusted=True,
            )
        )
        db.add(
            InstrumentDatasetState(
                instrument_id=instrument.id,
                data_source_id=source.id,
                dataset_type="ohlcv",
                dataset_key="D1:adj",
                status=DatasetStatus.FRESH,
                observed_at=start,
                fetched_at=cutoff + timedelta(days=1),
                coverage_start=start,
                coverage_end=cutoff + timedelta(days=1),
                version=1,
                extra_data={
                    "adjustment_provenance": {
                        "mode": "split_adjusted",
                        "source_kind": "provider_observation",
                        "factor_status": "rebuildable_split_factors",
                        "factor_version": "future-factor-version",
                    }
                },
            )
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": start.isoformat(),
                "end": cutoff.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "provider_observation",
            "factor_status": "provider_native_opaque",
            "factor_version": None,
            "contract_version": 1,
        }

    def test_range_coverage_exposes_provider_factor_derived_version(
        self, client, auth_headers, db, instrument
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import DatasetStatus, InstrumentDatasetState

        start = datetime(2026, 2, 2, tzinfo=UTC)
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
                    is_derived=True,
                    derivation_method="provider_adjustment_factor",
                    source_timeframe="D1",
                ),
                InstrumentDatasetState(
                    instrument_id=instrument.id,
                    data_source_id=None,
                    dataset_type="ohlcv",
                    dataset_key="D1:adj:provider_adjustment_factor",
                    status=DatasetStatus.FRESH,
                    observed_at=start,
                    fetched_at=start,
                    coverage_start=start,
                    coverage_end=start,
                    version=1,
                    extra_data={
                        "adjustment_provenance": {
                            "mode": "provider_adjusted",
                            "source_kind": "provider_adjustment_factor",
                            "factor_status": "rebuildable_provider_factors",
                            "factor_version": "afv1-provider-derived-version",
                            "contract_version": 1,
                        }
                    },
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "D1",
                "start": start.isoformat(),
                "end": start.isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "provider_adjustment_factor",
            "factor_status": "rebuildable_provider_factors",
            "factor_version": "afv1-provider-derived-version",
            "contract_version": 1,
        }

    def test_range_readiness_reports_mixed_provider_and_derived_lineage(
        self, client, auth_headers, db, instrument
    ):
        start = datetime(2026, 2, 2, tzinfo=UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.W1,
                    ts=start,
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    is_adjusted=True,
                    is_derived=False,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.W1,
                    ts=start + timedelta(days=7),
                    open=Decimal("11"),
                    high=Decimal("12"),
                    low=Decimal("10"),
                    close=Decimal("11"),
                    is_adjusted=True,
                    is_derived=True,
                    source_timeframe="D1",
                ),
            ]
        )
        db.flush()

        response = client.get(
            f"/api/v1/coverage/instruments/{instrument.symbol}/ohlcv",
            params={
                "timeframe": "W1",
                "start": "2026-02-02T00:00:00Z",
                "end": "2026-02-09T00:00:00Z",
                "mode": "historical",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["lineage"] == {
            "provider_bar_count": 1,
            "derived_bar_count": 1,
            "unknown_bar_count": 0,
            "source_lineage": "provider_and_derived",
            "source_timeframes": ["D1"],
        }
        assert body["adjustment_provenance"] == {
            "mode": "split_adjusted",
            "source_kind": "mixed_provider_and_derived",
            "factor_status": "mixed_provider_native_opaque_and_inherited_from_canonical_d1",
            "factor_version": None,
            "contract_version": 1,
        }
