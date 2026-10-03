"""Owner-scoped hydration of immutable trial inputs for local workers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    AttemptState,
    DataSnapshot,
    ExperimentDefinition,
    PortfolioComposition,
    RunAttempt,
    ScientificTrial,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.resource_domains import DomainResourceContract


class TrialDomainHydrationError(ValueError):
    """A persisted trial graph is missing, foreign, or semantically inconsistent."""


class OwnerScopedDomainReader(Protocol):
    async def get_domain_contract(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> DomainResourceContract | None: ...

    async def get_domain_contract_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprint: str,
    ) -> DomainResourceContract | None: ...

    async def get_domain_contracts_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprints: Sequence[str],
    ) -> Mapping[str, DomainResourceContract]: ...


@dataclass(frozen=True, slots=True)
class HydratedNautilusTrial:
    """Validated immutable domain graph needed before Nautilus input assembly."""

    attempt: RunAttempt
    trial: ScientificTrial
    experiment: ExperimentDefinition
    portfolio: PortfolioComposition
    snapshot: DataSnapshot
    strategies: tuple[StrategyVersion, ...]
    packages: Mapping[str, StrategyPackage]

    def __post_init__(self) -> None:
        expected = (
            ("attempt", self.attempt, RunAttempt),
            ("trial", self.trial, ScientificTrial),
            ("experiment", self.experiment, ExperimentDefinition),
            ("portfolio", self.portfolio, PortfolioComposition),
            ("snapshot", self.snapshot, DataSnapshot),
        )
        for name, value, value_type in expected:
            if not isinstance(value, value_type):
                raise TypeError(f"{name} must be a {value_type.__name__}")
        strategies = tuple(self.strategies)
        if not strategies or any(not isinstance(item, StrategyVersion) for item in strategies):
            raise TypeError("strategies must contain StrategyVersion values")
        if not isinstance(self.packages, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, StrategyPackage)
            for key, value in self.packages.items()
        ):
            raise TypeError("packages must map strategy fingerprints to StrategyPackage values")
        ordered_strategies = tuple(sorted(strategies, key=lambda item: item.fingerprint))
        ordered_packages = dict(sorted(self.packages.items()))
        strategy_fingerprints = tuple(item.fingerprint for item in ordered_strategies)
        if strategy_fingerprints != self.experiment.strategy_fingerprints:
            raise ValueError("hydrated strategy set differs from the immutable experiment")
        if set(ordered_packages) != set(strategy_fingerprints):
            raise ValueError("hydrated packages must bind every experiment strategy")
        for strategy in ordered_strategies:
            package = ordered_packages[strategy.fingerprint]
            if package.strategy_fingerprint != strategy.fingerprint:
                raise ValueError("hydrated package references a different strategy")
            if package.fingerprint != self.experiment.strategy_package_fingerprints.get(
                strategy.fingerprint
            ):
                raise ValueError("hydrated package differs from the experiment package pin")
        if {item.strategy_fingerprint for item in self.portfolio.components} != set(
            strategy_fingerprints
        ):
            raise ValueError("hydrated portfolio strategy set differs from the experiment")
        if self.attempt.trial_id != self.trial.trial_id:
            raise ValueError("hydrated attempt references a different scientific trial")
        if self.trial.experiment_fingerprint != self.experiment.fingerprint:
            raise ValueError("hydrated trial references a different experiment")
        if self.trial.snapshot_fingerprint != self.snapshot.fingerprint:
            raise ValueError("hydrated trial references a different frozen snapshot")
        if self.experiment.portfolio_fingerprint != self.portfolio.fingerprint:
            raise ValueError("hydrated experiment references a different portfolio")
        if self.experiment.snapshot_fingerprint != self.snapshot.fingerprint:
            raise ValueError("hydrated experiment references a different frozen snapshot")
        if self.experiment.capability_contract_digest != self.snapshot.capability_contract_digest:
            raise ValueError("hydrated experiment capability contract differs from its snapshot")
        if self.trial.preflight_report.fingerprint != self.snapshot.preflight_report.fingerprint:
            raise ValueError("hydrated trial preflight differs from its frozen snapshot")
        object.__setattr__(self, "strategies", ordered_strategies)
        object.__setattr__(self, "packages", MappingProxyType(ordered_packages))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class NautilusTrialDomainHydrator:
    """Resolve and authenticate an attempt's complete persisted domain graph.

    Artifact bytes, canonical market events, venue/account metadata, and the
    engine execution plan remain separate adapters. This layer guarantees that
    every immutable database identity used by those adapters belongs to the
    requesting owner and agrees with the experiment's content bindings.
    """

    def __init__(self, reader: OwnerScopedDomainReader) -> None:
        if not all(
            callable(getattr(reader, method, None))
            for method in (
                "get_domain_contract",
                "get_domain_contract_by_fingerprint",
                "get_domain_contracts_by_fingerprint",
            )
        ):
            raise TypeError("reader must provide owner-scoped domain contract reads")
        self._reader = reader

    async def hydrate_attempt(
        self,
        *,
        principal: Any,
        attempt_resource_id: str,
    ) -> HydratedNautilusTrial:
        """Hydrate one non-terminal attempt and all of its content-linked inputs."""

        if not isinstance(attempt_resource_id, str) or not attempt_resource_id.strip():
            raise ValueError("attempt_resource_id must not be empty")
        attempt = await self._reader.get_domain_contract(
            principal=principal,
            resource_type=ApiResourceType.ATTEMPT,
            resource_id=attempt_resource_id,
        )
        if not isinstance(attempt, RunAttempt):
            raise TrialDomainHydrationError("run attempt is missing or unavailable to this owner")
        if attempt.state not in {AttemptState.QUEUED, AttemptState.RUNNING}:
            raise TrialDomainHydrationError(
                "terminal run attempts cannot be hydrated for execution"
            )

        trial = await self._one(
            principal=principal,
            resource_type=ApiResourceType.TRIAL,
            fingerprint=attempt.trial_id,
        )
        if not isinstance(trial, ScientificTrial):
            raise TrialDomainHydrationError("attempt trial is missing or unavailable to this owner")

        experiment_by_fingerprint = await self._reader.get_domain_contracts_by_fingerprint(
            principal=principal,
            resource_type=ApiResourceType.EXPERIMENT,
            fingerprints=(trial.experiment_fingerprint,),
        )
        experiment = experiment_by_fingerprint.get(trial.experiment_fingerprint)
        if not isinstance(experiment, ExperimentDefinition):
            raise TrialDomainHydrationError(
                "trial experiment is missing or unavailable to this owner"
            )

        (
            portfolio_by_fingerprint,
            snapshot_by_fingerprint,
            strategies_by_fingerprint,
            packages_by_fingerprint,
        ) = await self._read_linked_inputs(
            principal=principal,
            experiment=experiment,
        )
        portfolio = portfolio_by_fingerprint.get(experiment.portfolio_fingerprint)
        snapshot = snapshot_by_fingerprint.get(experiment.snapshot_fingerprint)
        if not isinstance(portfolio, PortfolioComposition):
            raise TrialDomainHydrationError(
                "experiment portfolio is missing or unavailable to this owner"
            )
        if not isinstance(snapshot, DataSnapshot):
            raise TrialDomainHydrationError(
                "experiment snapshot is missing or unavailable to this owner"
            )

        strategies: list[StrategyVersion] = []
        packages: dict[str, StrategyPackage] = {}
        for strategy_fingerprint in experiment.strategy_fingerprints:
            strategy = strategies_by_fingerprint.get(strategy_fingerprint)
            package_fingerprint = experiment.strategy_package_fingerprints.get(strategy_fingerprint)
            package = (
                packages_by_fingerprint.get(package_fingerprint)
                if package_fingerprint is not None
                else None
            )
            if not isinstance(strategy, StrategyVersion):
                raise TrialDomainHydrationError(
                    "experiment strategy is missing or unavailable to this owner"
                )
            if not isinstance(package, StrategyPackage):
                raise TrialDomainHydrationError(
                    "experiment strategy package is missing or unavailable to this owner"
                )
            strategies.append(strategy)
            packages[strategy_fingerprint] = package

        try:
            return HydratedNautilusTrial(
                attempt=attempt,
                trial=trial,
                experiment=experiment,
                portfolio=portfolio,
                snapshot=snapshot,
                strategies=tuple(strategies),
                packages=packages,
            )
        except (TypeError, ValueError) as error:
            raise TrialDomainHydrationError(
                "persisted trial graph failed binding validation"
            ) from error

    async def _one(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprint: str,
    ) -> DomainResourceContract | None:
        require_sha256_digest(fingerprint, field_name="domain_fingerprint")
        return await self._reader.get_domain_contract_by_fingerprint(
            principal=principal,
            resource_type=resource_type,
            fingerprint=fingerprint,
        )

    async def _read_linked_inputs(
        self,
        *,
        principal: Any,
        experiment: ExperimentDefinition,
    ) -> tuple[
        Mapping[str, DomainResourceContract],
        Mapping[str, DomainResourceContract],
        Mapping[str, DomainResourceContract],
        Mapping[str, DomainResourceContract],
    ]:
        async def read(
            resource_type: ApiResourceType,
            fingerprints: Sequence[str],
        ) -> Mapping[str, DomainResourceContract]:
            return await self._reader.get_domain_contracts_by_fingerprint(
                principal=principal,
                resource_type=resource_type,
                fingerprints=tuple(sorted(set(fingerprints))),
            )

        package_fingerprints = tuple(experiment.strategy_package_fingerprints.values())
        return (
            await read(ApiResourceType.PORTFOLIO, (experiment.portfolio_fingerprint,)),
            await read(ApiResourceType.SNAPSHOT, (experiment.snapshot_fingerprint,)),
            await read(ApiResourceType.STRATEGY, experiment.strategy_fingerprints),
            await read(ApiResourceType.PACKAGE, package_fingerprints),
        )


__all__ = [
    "HydratedNautilusTrial",
    "NautilusTrialDomainHydrator",
    "OwnerScopedDomainReader",
    "TrialDomainHydrationError",
]
