from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import BinaryIO

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_store import ArtifactStoreCorruptionError, LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.authenticated_event_tape import AuthenticatedFrozenEventTapeResolver
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
    FrozenEventTapeStreamResolution,
    FrozenSeriesRow,
    iter_verified_event_tape_stream,
)
from app.strategy_lab_v2.nautilus_event_adapter import (
    iter_materialized_nautilus_event_records,
    materialize_nautilus_event_tape,
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

    result = FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()).resolve_materialized(
        snapshot, manifest
    )

    assert result.tape.snapshot_fingerprint == snapshot.fingerprint
    assert result.binding.dependency_event_counts == (("daily-bars", 2),)
    assert result.source_artifact_digests == (series.content_digest,)
    assert [event.values for event in result.tape.events] == [{"close": 100}, {"close": 101}]
    assert all(event.event_id.startswith("sha256:") for event in result.tape.events)


def test_streaming_resolution_preserves_tape_identity_without_retaining_events(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs(fields=("close",))
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)
    resolver = FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder())

    materialized = resolver.resolve_materialized(snapshot, manifest)
    streamed = resolver.resolve(snapshot, manifest)

    assert isinstance(streamed, FrozenEventTapeStreamResolution)
    assert not hasattr(streamed, "tape")
    assert streamed.tape_fingerprint == materialized.tape.fingerprint
    assert streamed.binding == materialized.binding
    assert streamed.event_count == materialized.tape.event_count
    assert tuple(iter_verified_event_tape_stream(streamed, store)) == materialized.tape.events
    assert store.path_for(streamed.artifact.storage_key).read_bytes().count(b"\n") == 2


def test_streaming_tape_can_feed_the_nautilus_event_adapter_incrementally(tmp_path) -> None:
    fields = ("open", "high", "low", "close", "volume")
    snapshot, manifest, series, payload = _inputs(fields=fields)
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    class NativeBarDecoder:
        def iter_rows(self, series: DataSeriesManifest, source: BinaryIO):
            del source
            for sequence in range(series.row_count):
                price = 100 + sequence
                yield FrozenSeriesRow(
                    f"bar-{sequence}",
                    BASE + timedelta(days=sequence),
                    sequence,
                    {
                        "open": price,
                        "high": price + 1,
                        "low": price - 1,
                        "close": price,
                        "volume": 1000 + sequence,
                    },
                )

    resolver = FrozenEventTapeArtifactResolver(store, NativeBarDecoder())
    materialized = resolver.resolve_materialized(snapshot, manifest)
    streamed = resolver.resolve(snapshot, manifest)
    expected = materialize_nautilus_event_tape(materialized.tape, snapshot, manifest)
    actual = tuple(iter_materialized_nautilus_event_records(streamed, snapshot, manifest, store))

    assert actual == expected.events


def test_streaming_resolution_rejects_duplicate_event_identity(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    class DuplicateSourceIdsDecoder:
        def iter_rows(self, series: DataSeriesManifest, source: BinaryIO):
            del source
            yield FrozenSeriesRow("same", BASE, 0, {"close": 100})
            yield FrozenSeriesRow("same", BASE + timedelta(days=1), 1, {"close": 101})

    resolver = FrozenEventTapeArtifactResolver(store, DuplicateSourceIdsDecoder())
    with pytest.raises(ValueError, match="event ids must be unique"):
        resolver.resolve_streaming(snapshot, manifest)


def test_streaming_resolution_handles_long_histories_incrementally(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs(row_count=4096)
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    class GeneratedHistoryDecoder:
        def iter_rows(self, series: DataSeriesManifest, source: BinaryIO):
            del source
            for sequence in range(series.row_count):
                yield FrozenSeriesRow(
                    f"bar-{sequence}",
                    BASE,
                    sequence,
                    {"close": Decimal(sequence)},
                )

    resolver = FrozenEventTapeArtifactResolver(store, GeneratedHistoryDecoder())
    streamed = resolver.resolve_streaming(snapshot, manifest)
    events = iter_verified_event_tape_stream(streamed, store)

    first = next(iter(events))
    assert first.sequence == 0
    assert first.values["close"] == Decimal(0)
    count = 1 + sum(1 for _event in events)
    assert count == 4096
    assert streamed.event_count == 4096


def test_streaming_resolution_enforces_a_temporary_disk_budget(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs(row_count=2048)
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)

    class LargeRowsDecoder:
        def iter_rows(self, series: DataSeriesManifest, source: BinaryIO):
            del source
            for sequence in range(series.row_count):
                yield FrozenSeriesRow(
                    f"bar-{sequence}",
                    BASE,
                    sequence,
                    {"close": "x" * 2048},
                )

    resolver = FrozenEventTapeArtifactResolver(store, LargeRowsDecoder())
    with pytest.raises(ValueError, match="sort spool exceeds its configured disk bound"):
        resolver.resolve_streaming(
            snapshot,
            manifest,
            max_event_bytes=4096,
            max_spool_bytes=1_048_576,
        )


def test_streaming_resolution_bounds_each_event_and_verifies_the_output_artifact(tmp_path) -> None:
    snapshot, manifest, series, payload = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)
    resolver = FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder())

    with pytest.raises(ValueError, match="row exceeds its configured bound"):
        resolver.resolve_streaming(snapshot, manifest, max_event_bytes=8)

    streamed = resolver.resolve_streaming(snapshot, manifest)
    target = store.path_for(streamed.artifact.storage_key)
    target.chmod(0o644)
    target.write_bytes(b"{}\n")
    with pytest.raises(ArtifactStoreCorruptionError, match="wrong digest"):
        tuple(iter_verified_event_tape_stream(streamed, store))


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


@pytest.mark.anyio
async def test_authenticated_tape_resolver_loads_owner_snapshot_and_verifies_artifacts(
    tmp_path,
) -> None:
    snapshot, manifest, series, payload = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")
    _publish(store, series, payload)
    offload_calls = []

    async def inline_offloader(function, *args):
        offload_calls.append(function)
        return function(*args)

    class Reader:
        async def get_domain_contracts_by_fingerprint(
            self, *, principal, resource_type, fingerprints
        ):
            assert principal == "owner-1"
            assert resource_type is ApiResourceType.SNAPSHOT
            assert fingerprints == (snapshot.fingerprint,)
            return {snapshot.fingerprint: snapshot}

    resolver = AuthenticatedFrozenEventTapeResolver(
        Reader(),
        FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()),
        principal="owner-1",
        offloader=inline_offloader,
    )

    result = await resolver.resolve(snapshot.fingerprint, manifest)

    assert result.snapshot_fingerprint == snapshot.fingerprint
    assert result.manifest_fingerprint == manifest.fingerprint
    assert result.event_count == 2
    assert result.source_artifact_digests == (series.content_digest,)
    assert len(offload_calls) == 1


@pytest.mark.anyio
async def test_authenticated_tape_resolver_fails_closed_when_owner_snapshot_is_missing(
    tmp_path,
) -> None:
    snapshot, manifest, _series, _payload = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")

    class Reader:
        async def get_domain_contracts_by_fingerprint(
            self, *, principal, resource_type, fingerprints
        ):
            assert principal == "other-owner"
            assert resource_type is ApiResourceType.SNAPSHOT
            return {}

    resolver = AuthenticatedFrozenEventTapeResolver(
        Reader(),
        FrozenEventTapeArtifactResolver(store, JsonSeriesDecoder()),
        principal="other-owner",
    )

    with pytest.raises(ValueError, match="owner-scoped frozen snapshot is unavailable"):
        await resolver.resolve(snapshot.fingerprint, manifest)


@pytest.mark.anyio
async def test_authenticated_tape_resolver_rejects_fingerprint_aliases(tmp_path) -> None:
    snapshot, manifest, _series, _payload = _inputs()
    requested_fingerprint = content_digest("different-snapshot")

    class Reader:
        async def get_domain_contracts_by_fingerprint(
            self, *, principal, resource_type, fingerprints
        ):
            return {requested_fingerprint: snapshot}

    resolver = AuthenticatedFrozenEventTapeResolver(
        Reader(),
        FrozenEventTapeArtifactResolver(
            LocalArtifactStore(tmp_path / "artifacts"), JsonSeriesDecoder()
        ),
        principal="owner-1",
    )

    with pytest.raises(ValueError, match="fingerprint does not match its key"):
        await resolver.resolve(requested_fingerprint, manifest)
