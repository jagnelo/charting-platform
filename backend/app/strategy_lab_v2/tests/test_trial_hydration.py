from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Any

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    DataSnapshot,
    ETFMembershipReference,
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


def _inputs_with_etf_membership_reference() -> dict[str, Any]:
    values = _inputs()
    old_snapshot: DataSnapshot = values["snapshot"]
    reference = ETFMembershipReference(
        etf_instrument_id="US:ETF:SPY",
        decision_time=old_snapshot.created_at,
        snapshot_id=41,
        content_digest=content_digest("frozen-membership"),
    )
    snapshot = replace(old_snapshot, etf_memberships=(reference,))
    experiment: ExperimentDefinition = values["experiment"]
    experiment = replace(experiment, snapshot_fingerprint=snapshot.fingerprint)
    old_trial: ScientificTrial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=old_trial.preflight_report,
        parameter_set=old_trial.parameter_set,
        scenario=old_trial.scenario,
        seed=old_trial.seed,
        randomization=old_trial.randomization,
        evaluation_window=old_trial.evaluation_window,
    )
    attempt: RunAttempt = values["attempt"]
    values.update(
        snapshot=snapshot,
        experiment=experiment,
        trial=trial,
        attempt=replace(attempt, trial_id=trial.trial_id),
        etf_reference=reference,
    )
    return values


class PinnedMembershipReader:
    def __init__(self, digest: str, *, snapshot_id: int = 41) -> None:
        self.digest = digest
        self.snapshot_id = snapshot_id
        self.references: list[ETFMembershipReference] = []

    async def resolve_pinned_etf_membership(self, reference: ETFMembershipReference) -> Any:
        from types import SimpleNamespace

        self.references.append(reference)
        return SimpleNamespace(
            etf_instrument_id=reference.etf_instrument_id,
            snapshot_id=self.snapshot_id,
            content_digest=self.digest,
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


@pytest.mark.asyncio
async def test_hydrator_revalidates_frozen_etf_membership_digest_on_restart() -> None:
    values = _inputs_with_etf_membership_reference()
    membership_reader = PinnedMembershipReader(values["etf_reference"].content_digest)
    hydrated = await NautilusTrialDomainHydrator(
        MemoryDomainReader(values), etf_membership_reader=membership_reader
    ).hydrate_attempt(principal="alice", attempt_resource_id=values["attempt"].attempt_id)

    assert hydrated.snapshot.etf_memberships == (values["etf_reference"],)
    assert membership_reader.references == [values["etf_reference"]]


@pytest.mark.asyncio
async def test_hydrator_rejects_changed_or_unavailable_etf_membership_on_restart() -> None:
    values = _inputs_with_etf_membership_reference()
    with pytest.raises(TrialDomainHydrationError, match="cannot be revalidated"):
        await NautilusTrialDomainHydrator(MemoryDomainReader(values)).hydrate_attempt(
            principal="alice", attempt_resource_id=values["attempt"].attempt_id
        )

    changed = PinnedMembershipReader(content_digest("changed-membership"))
    with pytest.raises(TrialDomainHydrationError, match="digest differs"):
        await NautilusTrialDomainHydrator(
            MemoryDomainReader(values), etf_membership_reader=changed
        ).hydrate_attempt(principal="alice", attempt_resource_id=values["attempt"].attempt_id)

    substituted_snapshot = PinnedMembershipReader(
        values["etf_reference"].content_digest, snapshot_id=42
    )
    with pytest.raises(TrialDomainHydrationError, match="digest differs"):
        await NautilusTrialDomainHydrator(
            MemoryDomainReader(values), etf_membership_reader=substituted_snapshot
        ).hydrate_attempt(principal="alice", attempt_resource_id=values["attempt"].attempt_id)
