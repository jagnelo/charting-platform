"""Owner-authenticated walk-forward calendar derivation from frozen inputs."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, cast

from starlette.concurrency import run_in_threadpool

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.contracts import (
    DataSnapshot,
    ExperimentDefinition,
    PortfolioComposition,
    ScientificTrial,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    verified_observation_boundaries,
)
from app.strategy_lab_v2.nautilus_trial_materializer import build_frozen_tape_manifest
from app.strategy_lab_v2.sdk import StrategySdkManifest


class WalkForwardCalendarDomainReader(Protocol):
    """Owner-scoped domain reads needed to resolve package and portfolio pins."""

    async def get_domain_contract_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprint: str,
    ) -> Any: ...

    async def get_domain_contracts_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprints: Sequence[str],
    ) -> Mapping[str, Any]: ...


class ResolvedPackage(Protocol):
    manifest: StrategySdkManifest
    package_fingerprint: str
    strategy_fingerprint: str


class PackageManifestResolver(Protocol):
    store: LocalArtifactStore

    def resolve(
        self,
        package: StrategyPackage,
        strategy: StrategyVersion,
    ) -> ResolvedPackage: ...


Offloader = Callable[..., Any]


async def _offload(function: Callable[..., Any], *args: Any) -> Any:
    return await run_in_threadpool(function, *args)


class AuthenticatedWalkForwardCalendarResolver:
    """Resolve exact strategy package pins and decode their frozen data tape.

    Resource reads remain owner-scoped. Package archives are loaded through
    ``StrategyPackageArtifactResolver``; the union SDK manifest is then used by
    ``FrozenEventTapeArtifactResolver`` to verify and decode the snapshot's
    content-addressed source series. Calendar extraction runs off the API event
    loop and returns only event-time batches verified against the resulting
    tape fingerprint.
    """

    def __init__(
        self,
        reader: WalkForwardCalendarDomainReader,
        package_resolver: PackageManifestResolver,
        event_tape_resolver: FrozenEventTapeArtifactResolver,
        *,
        offloader: Offloader | None = None,
    ) -> None:
        if not callable(getattr(reader, "get_domain_contract_by_fingerprint", None)):
            raise TypeError("reader must provide owner-scoped domain fingerprint reads")
        if not callable(getattr(reader, "get_domain_contracts_by_fingerprint", None)):
            raise TypeError("reader must provide owner-scoped batch domain reads")
        if not callable(getattr(package_resolver, "resolve", None)):
            raise TypeError("package_resolver must provide resolve(package, strategy)")
        if not isinstance(event_tape_resolver, FrozenEventTapeArtifactResolver):
            raise TypeError("event_tape_resolver must use FrozenEventTapeArtifactResolver")
        if package_resolver.store is not event_tape_resolver.artifact_store:
            raise ValueError("package and frozen-series resolvers must share one artifact store")
        if offloader is not None and not callable(offloader):
            raise TypeError("offloader must be callable")
        self._reader = reader
        self._package_resolver = package_resolver
        self._event_tape_resolver = event_tape_resolver
        self._offloader = cast(Offloader, _offload) if offloader is None else offloader

    async def __call__(
        self,
        *,
        principal: Any,
        experiment: ExperimentDefinition,
        snapshot: DataSnapshot,
        candidates: Sequence[ScientificTrial],
    ) -> tuple[datetime, ...]:
        """Return verified UTC boundaries for the exact owner-bound experiment."""

        if not isinstance(experiment, ExperimentDefinition):
            raise TypeError("experiment must be an ExperimentDefinition")
        if not isinstance(snapshot, DataSnapshot):
            raise TypeError("snapshot must be a DataSnapshot")
        if (
            snapshot.fingerprint != experiment.snapshot_fingerprint
            or snapshot.capability_contract_digest != experiment.capability_contract_digest
        ):
            raise ValueError("calendar snapshot differs from its experiment binding")
        candidate_values = tuple(candidates)
        if not candidate_values or any(
            not isinstance(candidate, ScientificTrial) for candidate in candidate_values
        ):
            raise TypeError("candidates must contain ScientificTrial values")
        if len({candidate.trial_id for candidate in candidate_values}) != len(candidate_values):
            raise ValueError("calendar candidates must have unique trial identities")
        if any(
            candidate.experiment_fingerprint != experiment.fingerprint
            or candidate.snapshot_fingerprint != snapshot.fingerprint
            or candidate.preflight_fingerprint != snapshot.preflight_report.fingerprint
            or candidate.evaluation_window is not None
            for candidate in candidate_values
        ):
            raise ValueError("calendar candidates must be unwindowed trials from this experiment")

        portfolio = await self._reader.get_domain_contract_by_fingerprint(
            principal=principal,
            resource_type=ApiResourceType.PORTFOLIO,
            fingerprint=experiment.portfolio_fingerprint,
        )
        if not isinstance(portfolio, PortfolioComposition):
            raise ValueError("walk-forward portfolio is unavailable to this owner")
        if portfolio.fingerprint != experiment.portfolio_fingerprint:
            raise ValueError("walk-forward portfolio identity differs from its experiment pin")
        strategy_fingerprints = tuple(
            sorted({component.strategy_fingerprint for component in portfolio.components})
        )
        if strategy_fingerprints != experiment.strategy_fingerprints:
            raise ValueError("walk-forward portfolio strategies differ from experiment pins")
        package_pins = experiment.strategy_package_fingerprints
        if set(package_pins) != set(strategy_fingerprints):
            raise ValueError("walk-forward experiment does not pin every strategy package")

        strategies = await self._reader.get_domain_contracts_by_fingerprint(
            principal=principal,
            resource_type=ApiResourceType.STRATEGY,
            fingerprints=strategy_fingerprints,
        )
        packages = await self._reader.get_domain_contracts_by_fingerprint(
            principal=principal,
            resource_type=ApiResourceType.PACKAGE,
            fingerprints=tuple(package_pins.values()),
        )
        if set(strategies) != set(strategy_fingerprints):
            raise ValueError("one or more walk-forward strategies are unavailable to this owner")
        if set(packages) != set(package_pins.values()):
            raise ValueError(
                "one or more pinned walk-forward packages are unavailable to this owner"
            )

        typed_strategies: list[StrategyVersion] = []
        typed_packages: list[StrategyPackage] = []
        for strategy_fingerprint in strategy_fingerprints:
            strategy = strategies[strategy_fingerprint]
            package_fingerprint = package_pins[strategy_fingerprint]
            package = packages[package_fingerprint]
            if (
                not isinstance(strategy, StrategyVersion)
                or strategy.fingerprint != strategy_fingerprint
            ):
                raise ValueError("walk-forward strategy resource identity is invalid")
            if (
                not isinstance(package, StrategyPackage)
                or package.fingerprint != package_fingerprint
            ):
                raise ValueError("walk-forward package resource identity is invalid")
            if (
                package.strategy_fingerprint != strategy.fingerprint
                or package.sdk_version != strategy.sdk_version
            ):
                raise ValueError("walk-forward package is inconsistent with its strategy pin")
            typed_strategies.append(strategy)
            typed_packages.append(package)

        boundaries = self._offloader(
            self._resolve_calendar,
            snapshot,
            tuple(typed_strategies),
            tuple(typed_packages),
        )
        result = await boundaries if inspect.isawaitable(boundaries) else boundaries
        if not isinstance(result, tuple) or len(result) < 2:
            raise TypeError("verified event-tape resolver returned an invalid calendar")
        return result

    def _resolve_calendar(
        self,
        snapshot: DataSnapshot,
        strategies: tuple[StrategyVersion, ...],
        packages: tuple[StrategyPackage, ...],
    ) -> tuple[datetime, ...]:
        resolved = tuple(
            self._package_resolver.resolve(package, strategy)
            for package, strategy in zip(packages, strategies, strict=True)
        )
        if any(
            package.package_fingerprint != expected_package.fingerprint
            or package.strategy_fingerprint != expected_strategy.fingerprint
            for package, expected_package, expected_strategy in zip(
                resolved,
                packages,
                strategies,
                strict=True,
            )
        ):
            raise ValueError("resolved strategy package differs from its immutable experiment pin")
        manifest = build_frozen_tape_manifest(
            strategies[0],
            tuple(package.manifest for package in resolved),
        )
        tape = self._event_tape_resolver.resolve(snapshot, manifest)
        return verified_observation_boundaries(
            tape,
            self._event_tape_resolver.artifact_store,
        )


__all__ = ["AuthenticatedWalkForwardCalendarResolver", "WalkForwardCalendarDomainReader"]
