from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    DataSnapshot,
    ExperimentDefinition,
    PortfolioComposition,
    RunAttempt,
    ScientificTrial,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.resource_domains import DomainResourceContract
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
    TrialDomainHydrationError,
)


class MemoryDomainReader:
    def __init__(self, values: dict[str, Any], *, owner: str = "alice") -> None:
        self.owner = owner
        self.by_id: dict[tuple[ApiResourceType, str], DomainResourceContract] = {}
        self.by_fingerprint: dict[tuple[ApiResourceType, str], DomainResourceContract] = {}
        self.calls: list[tuple[str, ApiResourceType, tuple[str, ...]]] = []
        self._put(ApiResourceType.ATTEMPT, values["attempt"].attempt_id, values["attempt"])
        self._put(ApiResourceType.TRIAL, values["trial"].trial_id, values["trial"])
        self._put(
            ApiResourceType.EXPERIMENT, values["experiment"].fingerprint, values["experiment"]
        )
        self._put(ApiResourceType.PORTFOLIO, values["portfolio"].fingerprint, values["portfolio"])
        self._put(ApiResourceType.SNAPSHOT, values["snapshot"].fingerprint, values["snapshot"])
        if "strategies" in values:
            strategies = tuple(values["strategies"])
            packages = values["packages"]
        else:
            strategy: StrategyVersion = values["strategy_manifest"].strategy
            strategies = (strategy,)
            packages = {strategy.fingerprint: values["strategy_package"]}
        for strategy in strategies:
            package: StrategyPackage = packages[strategy.fingerprint]
            self._put(ApiResourceType.STRATEGY, strategy.fingerprint, strategy)
            self._put(ApiResourceType.PACKAGE, package.fingerprint, package)

    def _put(
        self,
        resource_type: ApiResourceType,
        resource_id: str,
        contract: DomainResourceContract,
    ) -> None:
        self.by_id[(resource_type, resource_id)] = contract
        fingerprint = getattr(contract, "fingerprint", None)
        if isinstance(contract, ScientificTrial):
            fingerprint = contract.trial_id
        if fingerprint is not None:
            self.by_fingerprint[(resource_type, fingerprint)] = contract

    async def get_domain_contract(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> DomainResourceContract | None:
        self.calls.append(("id", resource_type, (resource_id,)))
        if str(getattr(principal, "id", principal)) != self.owner:
            return None
        return self.by_id.get((resource_type, resource_id))

    async def get_domain_contract_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprint: str,
    ) -> DomainResourceContract | None:
        result = await self.get_domain_contracts_by_fingerprint(
            principal=principal,
            resource_type=resource_type,
            fingerprints=(fingerprint,),
        )
        return result.get(fingerprint)

    async def get_domain_contracts_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprints: Sequence[str],
    ) -> Mapping[str, DomainResourceContract]:
        requested = tuple(fingerprints)
        self.calls.append(("fingerprint", resource_type, requested))
        if str(getattr(principal, "id", principal)) != self.owner:
            return MappingProxyType({})
        return MappingProxyType(
            {
                fingerprint: self.by_fingerprint[(resource_type, fingerprint)]
                for fingerprint in requested
                if (resource_type, fingerprint) in self.by_fingerprint
            }
        )

    async def get_run_attempt_by_attempt_id(
        self,
        *,
        principal: Any,
        attempt_id: str,
    ) -> RunAttempt | None:
        contract = await self.get_domain_contract(
            principal=principal,
            resource_type=ApiResourceType.ATTEMPT,
            resource_id=attempt_id,
        )
        return contract if isinstance(contract, RunAttempt) else None

    async def get_run_attempts_for_trial(
        self,
        *,
        principal: Any,
        trial_id: str,
    ) -> tuple[RunAttempt, ...]:
        if str(getattr(principal, "id", principal)) != self.owner:
            return ()
        attempts = (
            contract
            for (resource_type, _resource_id), contract in self.by_id.items()
            if resource_type is ApiResourceType.ATTEMPT
            and isinstance(contract, RunAttempt)
            and contract.trial_id == trial_id
        )
        return tuple(sorted(attempts, key=lambda attempt: attempt.ordinal))


@pytest.mark.asyncio
async def test_hydrator_resolves_and_authenticates_the_attempt_domain_graph() -> None:
    values = _inputs()
    reader = MemoryDomainReader(values)

    hydrated = await NautilusTrialDomainHydrator(reader).hydrate_attempt(
        principal="alice",
        attempt_resource_id=values["attempt"].attempt_id,
    )

    assert isinstance(hydrated.attempt, RunAttempt)
    assert isinstance(hydrated.trial, ScientificTrial)
    assert isinstance(hydrated.experiment, ExperimentDefinition)
    assert isinstance(hydrated.portfolio, PortfolioComposition)
    assert isinstance(hydrated.snapshot, DataSnapshot)
    strategy = values["strategy_manifest"].strategy
    assert hydrated.strategies == (strategy,)
    assert hydrated.packages[strategy.fingerprint] == values["strategy_package"]
    assert len(hydrated.fingerprint) == len("sha256:") + 64
    assert [call[1] for call in reader.calls].count(ApiResourceType.STRATEGY) == 1
    assert [call[1] for call in reader.calls].count(ApiResourceType.PACKAGE) == 1


@pytest.mark.asyncio
async def test_hydrator_fails_closed_when_attempt_is_not_owner_visible() -> None:
    values = _inputs()
    reader = MemoryDomainReader(values, owner="bob")

    with pytest.raises(TrialDomainHydrationError, match="attempt is missing"):
        await NautilusTrialDomainHydrator(reader).hydrate_attempt(
            principal="alice",
            attempt_resource_id=values["attempt"].attempt_id,
        )


@pytest.mark.asyncio
async def test_hydrator_fails_closed_when_an_experiment_package_pin_is_unavailable() -> None:
    values = _inputs()
    experiment: ExperimentDefinition = values["experiment"]
    missing_package = content_digest("missing-pinned-package")
    values["experiment"] = ExperimentDefinition(
        experiment_id=experiment.experiment_id,
        portfolio_fingerprint=experiment.portfolio_fingerprint,
        strategy_fingerprints=experiment.strategy_fingerprints,
        snapshot_fingerprint=experiment.snapshot_fingerprint,
        capability_contract_digest=experiment.capability_contract_digest,
        seed=experiment.seed,
        metric_definition_version=experiment.metric_definition_version,
        engine_contract=experiment.engine_contract,
        strategy_package_fingerprints={experiment.strategy_fingerprints[0]: missing_package},
    )
    trial: ScientificTrial = values["trial"]
    values["trial"] = ScientificTrial.create(
        experiment_fingerprint=values["experiment"].fingerprint,
        snapshot_fingerprint=trial.snapshot_fingerprint,
        preflight_report=trial.preflight_report,
        parameter_set=trial.parameter_set,
        scenario=trial.scenario,
        seed=trial.seed,
        randomization=trial.randomization,
        evaluation_window=trial.evaluation_window,
    )
    attempt: RunAttempt = values["attempt"]
    values["attempt"] = RunAttempt(
        attempt_id=attempt.attempt_id,
        trial_id=values["trial"].trial_id,
        ordinal=attempt.ordinal,
        state=attempt.state,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )
    reader = MemoryDomainReader(values)

    with pytest.raises(TrialDomainHydrationError, match="package is missing"):
        await NautilusTrialDomainHydrator(reader).hydrate_attempt(
            principal="alice",
            attempt_resource_id=values["attempt"].attempt_id,
        )
