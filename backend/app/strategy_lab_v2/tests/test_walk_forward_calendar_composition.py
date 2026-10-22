from __future__ import annotations

from pathlib import Path

import pytest

from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeArtifactResolver
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import JsonFrozenSeriesDecoder
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import RUNTIME_ABI
from app.strategy_lab_v2.walk_forward_calendar import AuthenticatedWalkForwardCalendarResolver
from app.strategy_lab_v2.walk_forward_calendar_composition import (
    create_walk_forward_calendar_resolver,
)


@pytest.fixture
def persistence() -> PostgresStrategyLabV2Persistence:
    return PostgresStrategyLabV2Persistence.build(lambda: object())


def test_production_composition_uses_owner_reader_and_one_verified_store(
    persistence: PostgresStrategyLabV2Persistence,
    tmp_path: Path,
) -> None:
    resolver = create_walk_forward_calendar_resolver(
        persistence,
        tmp_path / "artifacts",
        runtime_abi=RUNTIME_ABI,
        series_decoder=JsonFrozenSeriesDecoder(),
    )

    assert isinstance(resolver, AuthenticatedWalkForwardCalendarResolver)
    assert resolver._reader is persistence.resources
    assert isinstance(resolver._package_resolver, StrategyPackageArtifactResolver)
    assert isinstance(resolver._event_tape_resolver, FrozenEventTapeArtifactResolver)
    assert resolver._package_resolver.store is resolver._event_tape_resolver.artifact_store
    assert resolver._package_resolver.store.root == (tmp_path / "artifacts").resolve()


@pytest.mark.parametrize(
    ("artifact_root", "runtime_abi", "decoder", "error"),
    [
        (Path("relative"), RUNTIME_ABI, JsonFrozenSeriesDecoder(), ValueError),
        (Path("/tmp/artifacts"), " ", JsonFrozenSeriesDecoder(), ValueError),
        (Path("/tmp/artifacts"), RUNTIME_ABI, object(), TypeError),
    ],
)
def test_production_composition_rejects_invalid_host_inputs(
    persistence: PostgresStrategyLabV2Persistence,
    artifact_root: Path,
    runtime_abi: str,
    decoder: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        create_walk_forward_calendar_resolver(
            persistence,
            artifact_root,
            runtime_abi=runtime_abi,
            series_decoder=decoder,  # type: ignore[arg-type]
        )
