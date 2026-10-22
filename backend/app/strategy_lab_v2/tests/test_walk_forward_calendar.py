from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, BinaryIO

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.capabilities import CapabilityCell, preflight_capabilities
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    DataSeriesManifest,
    DataSnapshot,
    ExperimentDefinition,
    PortfolioComponent,
    PortfolioComposition,
    ScientificTrial,
)
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    FrozenSeriesRow,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.tests.test_strategy_package_resolution import (
    RUNTIME_ABI,
)
from app.strategy_lab_v2.tests.test_strategy_package_resolution import (
    _fixture as package_fixture,
)
from app.strategy_lab_v2.walk_forward_calendar import AuthenticatedWalkForwardCalendarResolver

NOW = datetime(2024, 1, 1, tzinfo=UTC)


class JsonFrozenSeriesDecoder:
    def iter_rows(self, _series: DataSeriesManifest, source: BinaryIO):
        for row in json.load(source):
            yield FrozenSeriesRow(
                row["event_id"],
                datetime.fromisoformat(row["event_time"]),
                row["sequence"],
                row["values"],
            )


def _fixture(tmp_path):
    store, package, strategy, sdk_manifest, _archive = package_fixture(tmp_path)
    requirement = sdk_manifest.data_dependencies[0].requirement
    cell = CapabilityCell(
        instrument_id=requirement.instrument_id,
        product_class=requirement.product_class,
        event_granularities=frozenset({requirement.event_granularity}),
        event_types=frozenset({requirement.event_type}),
        timeframes=frozenset({requirement.timeframe}),
        adjustments=frozenset({requirement.adjustment}),
        sessions=frozenset({requirement.session}),
        feeds=frozenset({requirement.feed}),
        execution_models=frozenset({requirement.execution_model}),
        account_models=frozenset({requirement.account_model}),
        corporate_action_semantics=frozenset({requirement.corporate_action_semantics}),
        history_start=requirement.start - timedelta(days=1),
        history_end=requirement.end + timedelta(days=1),
        evidence_digest=artifact_content_digest(b"capability-evidence"),
    )
    preflight = preflight_capabilities((requirement,), (cell,))
    rows = [
        {
            "event_id": "bar-1",
            "event_time": requirement.start.isoformat(),
            "sequence": 0,
            "values": {"close": "100"},
        },
        {
            "event_id": "bar-2",
            "event_time": (requirement.start + timedelta(hours=12)).isoformat(),
            "sequence": 1,
            "values": {"close": "101"},
        },
    ]
    series_bytes = json.dumps(rows, separators=(",", ":")).encode()
    series = DataSeriesManifest(
        instrument_id=requirement.instrument_id,
        event_type=requirement.event_type,
        event_granularity=requirement.event_granularity,
        timeframe=requirement.timeframe,
        session=requirement.session,
        feed=requirement.feed,
        start=requirement.start,
        end=requirement.end,
        adjustment=requirement.adjustment,
        corporate_action_semantics=requirement.corporate_action_semantics,
        coverage_evidence_digest=cell.evidence_digest,
        content_digest=artifact_content_digest(series_bytes),
        row_count=len(rows),
    )
    snapshot = DataSnapshot(
        "calendar-snapshot",
        "provider-snapshot",
        preflight,
        (series,),
        NOW,
    )
    store.publish(
        ArtifactManifest(
            series.content_digest,
            len(series_bytes),
            "application/vnd.apache.parquet",
            "provider.market-series.v1",
            series.content_digest,
            ArtifactRetention.PINNED_INPUT,
        ),
        series_bytes,
    )
    portfolio = PortfolioComposition(
        "calendar-portfolio",
        "v1",
        Decimal("10000"),
        "USD",
        (
            PortfolioComponent(
                "component-1",
                strategy.fingerprint,
                (requirement.instrument_id,),
                Decimal("1"),
            ),
        ),
    )
    experiment = ExperimentDefinition(
        "calendar-experiment",
        portfolio.fingerprint,
        (strategy.fingerprint,),
        snapshot.fingerprint,
        snapshot.capability_contract_digest,
        7,
        "metrics-v1",
        strategy_package_fingerprints={strategy.fingerprint: package.fingerprint},
    )
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=preflight,
        parameter_set={"lookback": 20},
        seed=7,
    )
    contracts = {
        (ApiResourceType.PORTFOLIO, portfolio.fingerprint): portfolio,
        (ApiResourceType.STRATEGY, strategy.fingerprint): strategy,
        (ApiResourceType.PACKAGE, package.fingerprint): package,
    }

    class Reader:
        async def get_domain_contract_by_fingerprint(self, **kwargs: Any):
            assert kwargs["principal"].id == "owner-1"
            return contracts.get((kwargs["resource_type"], kwargs["fingerprint"]))

        async def get_domain_contracts_by_fingerprint(self, **kwargs: Any):
            assert kwargs["principal"].id == "owner-1"
            return {
                fingerprint: contracts[(kwargs["resource_type"], fingerprint)]
                for fingerprint in kwargs["fingerprints"]
                if (kwargs["resource_type"], fingerprint) in contracts
            }

    package_resolver = StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI)
    tape_resolver = FrozenEventTapeArtifactResolver(store, JsonFrozenSeriesDecoder())

    async def inline_offloader(function, *args):
        return function(*args)

    resolver = AuthenticatedWalkForwardCalendarResolver(
        Reader(),
        package_resolver,
        tape_resolver,
        offloader=inline_offloader,
    )
    return resolver, experiment, snapshot, trial, strategy, package


def test_calendar_resolver_derives_boundaries_from_owner_pinned_local_artifacts(tmp_path):
    resolver, experiment, snapshot, trial, strategy, package = _fixture(tmp_path)

    boundaries = asyncio.run(
        resolver(
            principal=SimpleNamespace(id="owner-1"),
            experiment=experiment,
            snapshot=snapshot,
            candidates=(trial,),
        )
    )

    expected_start = snapshot.series[0].start
    assert boundaries == (
        expected_start,
        expected_start + timedelta(hours=12),
        expected_start + timedelta(hours=12, microseconds=1),
    )
    assert strategy.fingerprint in experiment.strategy_package_fingerprints
    assert package.fingerprint == experiment.strategy_package_fingerprints[strategy.fingerprint]


def test_calendar_resolver_rejects_candidate_from_another_experiment(tmp_path):
    resolver, experiment, snapshot, trial, _strategy, _package = _fixture(tmp_path)
    foreign = ScientificTrial.create(
        experiment_fingerprint=artifact_content_digest(b"foreign-experiment"),
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=snapshot.preflight_report,
        parameter_set={"lookback": 20},
        seed=7,
    )

    with pytest.raises(ValueError, match="unwindowed trials from this experiment"):
        asyncio.run(
            resolver(
                principal=SimpleNamespace(id="owner-1"),
                experiment=experiment,
                snapshot=snapshot,
                candidates=(foreign,),
            )
        )
