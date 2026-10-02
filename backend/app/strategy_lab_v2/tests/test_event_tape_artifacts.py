from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

import pytest

from app.strategy_lab_v2.artifact_store import ArtifactStoreCorruptionError, LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
    DataSeriesManifest,
    DataSnapshot,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    FrozenSeriesRow,
)
from app.strategy_lab_v2.sdk import StrategyDataDependency, StrategySdkManifest

BASE = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


class JsonSeriesDecoder:
    """Test adapter standing in for the provider-owned Arrow decoder."""

    def iter_rows(self, series: DataSeriesManifest, source: BinaryIO):
        del series
        for row in json.load(source):
            yield FrozenSeriesRow(
                event_id=row["event_id"],
                event_time=datetime.fromisoformat(row["event_time"]),
                sequence=row["sequence"],
                values=row["values"],
            )


def _inputs(*, fields: tuple[str, ...] = ("close",), row_count: int = 2):
    rows = [
        {
            "event_id": f"bar-{sequence}",
            "event_time": (BASE + timedelta(days=sequence)).isoformat(),
            "sequence": sequence,
            "values": {"close": 100 + sequence, "volume": 1000 + sequence},
        }
        for sequence in range(2)
    ]
    payload = json.dumps(rows, separators=(",", ":")).encode()
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=BASE - timedelta(days=1),
        end=BASE + timedelta(days=4),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=BASE - timedelta(days=10),
        history_end=BASE + timedelta(days=10),
        evidence_digest=content_digest("capability-evidence"),
    )
    preflight = preflight_capabilities((requirement,), (cell,))
    series = DataSeriesManifest(
        instrument_id="US.AAPL",
        event_type="ohlcv",
        event_granularity=EventGranularity.BAR,
        timeframe="1d",
        session="regular",
        feed="consolidated",
        start=requirement.start,
        end=requirement.end,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        corporate_action_semantics="split-adjusted-v1",
        coverage_evidence_digest=content_digest("coverage-evidence"),
        content_digest=artifact_content_digest(payload),
        row_count=row_count,
    )
    snapshot = DataSnapshot(
        "snapshot-1",
        "provider-snapshot-1",
        preflight,
        (series,),
        BASE,
    )
    manifest = StrategySdkManifest(
        StrategyVersion("strategy-1", "v1", "2.0.0", content_digest("source")),
        (StrategyDataDependency("daily-bars", requirement, fields),),
    )
    return snapshot, manifest, series, payload


def _publish(store: LocalArtifactStore, series: DataSeriesManifest, payload: bytes) -> None:
    store.publish(
        ArtifactManifest(
            content_digest=series.content_digest,
            byte_length=len(payload),
            media_type="application/vnd.apache.parquet",
            schema_version="provider.market-series.v1",
            storage_key=series.content_digest,
        ),
        payload,
    )


def test_resolves_verified_series_artifact_and_projects_only_declared_fields(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs(fields=("close",))
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    result = FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()).resolve(snapshot, manifest)

    assert result.tape.snapshot_fingerprint == snapshot.fingerprint
    assert result.binding.dependency_event_counts == (("daily-bars", 2),)
    assert result.source_artifact_digests == (series.content_digest,)
    assert [event.values for event in result.tape.events] == [{"close": 100}, {"close": 101}]
    assert all(event.event_id.startswith("sha256:") for event in result.tape.events)


def test_rejects_declared_row_count_mismatch_before_binding(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs(row_count=3)
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    with pytest.raises(ValueError, match="row count differs"):
        FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()).resolve(snapshot, manifest)


def test_rejects_missing_strategy_fields(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs(fields=("close", "missing"))
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    with pytest.raises(ValueError, match="missing declared fields"):
        FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()).resolve(snapshot, manifest)


def test_rejects_decoded_rows_outside_the_frozen_series_interval(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    class OutsideSeriesDecoder:
        def iter_rows(self, series: DataSeriesManifest, source: BinaryIO):
            del source
            yield FrozenSeriesRow(
                "outside",
                series.end,
                0,
                {"close": 100},
            )
            yield FrozenSeriesRow(
                "outside-2",
                series.end + timedelta(days=1),
                1,
                {"close": 101},
            )

    with pytest.raises(ValueError, match="outside its frozen series interval"):
        FrozenEventTapeArtifactResolver(store, OutsideSeriesDecoder()).resolve(snapshot, manifest)


def test_missing_snapshot_artifact_does_not_fetch_or_fallback(tmp_path) -> None:
    snapshot, manifest, _series, _payload = _inputs()
    resolver = FrozenEventTapeArtifactResolver(
        LocalArtifactStore(tmp_path / "artifacts"), JsonSeriesDecoder()
    )

    with pytest.raises(FileNotFoundError):
        resolver.resolve(snapshot, manifest)


def test_corrupt_snapshot_artifact_fails_content_address_verification(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)
    target = store.path_for(series.content_digest)
    target.chmod(0o644)
    target.write_bytes(b"corrupted")

    with pytest.raises(ArtifactStoreCorruptionError, match="wrong digest"):
        FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()).resolve(snapshot, manifest)
