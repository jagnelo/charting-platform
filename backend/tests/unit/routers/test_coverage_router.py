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
