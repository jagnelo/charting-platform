from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    DataSnapshot,
    ETFMembershipReference,
    ExperimentDefinition,
    PortfolioComposition,
    ResolvedStudyArtifactOutput,
    RunAttempt,
    ScientificTrial,
    SelectedStudyArtifactReference,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.resource_domains import DomainResourceContract
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
    SelectedStudyArtifactResolver,
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


def _inputs_with_selected_study_artifact_reference(
    *, artifact_type: str = "series", value: Any = None
) -> dict[str, Any]:
    values = _inputs()
    old_strategy: StrategyVersion = values["strategy_manifest"].strategy
    study_value = [1.25, 2.5] if value is None else value
    study_payload = {"type": artifact_type, "value": study_value}
    reference = SelectedStudyArtifactReference(
        research_run_id=41,
        code_version_id=12,
        artifact_id=87,
        artifact_name="study.output",
        artifact_type=artifact_type,
        output_contract="study",
        run_reproducibility_hash="a" * 64,
        code_version_digest=content_digest("code-version"),
        dataset_manifest_digest=content_digest("dataset-manifest"),
        artifact_content_digest=content_digest(study_payload),
    )
    strategy = replace(old_strategy, selected_study_artifact=reference)
    old_portfolio: PortfolioComposition = values["portfolio"]
    portfolio = replace(
        old_portfolio,
        components=tuple(
            replace(component, strategy_fingerprint=strategy.fingerprint)
            for component in old_portfolio.components
        ),
    )
    old_package: StrategyPackage = values["strategy_package"]
    package = replace(old_package, strategy_fingerprint=strategy.fingerprint)
    old_experiment: ExperimentDefinition = values["experiment"]
    experiment = replace(
        old_experiment,
        portfolio_fingerprint=portfolio.fingerprint,
        strategy_fingerprints=(strategy.fingerprint,),
        strategy_package_fingerprints={strategy.fingerprint: package.fingerprint},
    )
    old_trial: ScientificTrial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=old_trial.snapshot_fingerprint,
        preflight_report=old_trial.preflight_report,
        parameter_set=old_trial.parameter_set,
        scenario=old_trial.scenario,
        seed=old_trial.seed,
        randomization=old_trial.randomization,
        evaluation_window=old_trial.evaluation_window,
    )
    attempt: RunAttempt = values["attempt"]
    values.update(
        strategy_manifest=replace(values["strategy_manifest"], strategy=strategy),
        strategy_package=package,
        portfolio=portfolio,
        experiment=experiment,
        trial=trial,
        attempt=replace(attempt, trial_id=trial.trial_id),
        strategies=(strategy,),
        packages={strategy.fingerprint: package},
        selected_study_artifact=reference,
        selected_study_payload=study_payload,
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
async def test_hydrator_resolver_validation_accepts_functions_and_async_callable_objects() -> None:
    values = _inputs()

    async def async_function(
        *, principal: Any, reference: SelectedStudyArtifactReference
    ) -> ResolvedStudyArtifactOutput:
        return ResolvedStudyArtifactOutput(
            reference,
            {"type": reference.artifact_type, "value": {"lookback": 20}},
        )

    class AsyncResolver:
        async def __call__(
            self, *, principal: Any, reference: SelectedStudyArtifactReference
        ) -> ResolvedStudyArtifactOutput:
            return ResolvedStudyArtifactOutput(
                reference,
                {"type": reference.artifact_type, "value": {"lookback": 20}},
            )

    NautilusTrialDomainHydrator(
        MemoryDomainReader(values),
        selected_study_artifact_resolver=async_function,
    )
    NautilusTrialDomainHydrator(
        MemoryDomainReader(values),
        selected_study_artifact_resolver=AsyncResolver(),
    )

    def synchronous_resolver(
        *, principal: Any, reference: SelectedStudyArtifactReference
    ) -> ResolvedStudyArtifactOutput:
        return ResolvedStudyArtifactOutput(
            reference,
            {"type": reference.artifact_type, "value": {"lookback": 20}},
        )

    with pytest.raises(TypeError, match="must be asynchronous"):
        NautilusTrialDomainHydrator(
            MemoryDomainReader(values),
            selected_study_artifact_resolver=cast(
                SelectedStudyArtifactResolver, synchronous_resolver
            ),
        )


@pytest.mark.asyncio
async def test_hydrator_rejects_selected_study_reference_without_trusted_resolver() -> None:
    values = _inputs_with_selected_study_artifact_reference()

    with pytest.raises(TrialDomainHydrationError, match="cannot be revalidated"):
        await NautilusTrialDomainHydrator(MemoryDomainReader(values)).hydrate_attempt(
            principal="alice",
            attempt_resource_id=values["attempt"].attempt_id,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_type", "study_value"),
    (
        ("scalar", 2.5),
        ("series", [{"time": "t1", "value": 2.5}, {"time": "t2", "value": 3.0}]),
        ("boolean", True),
        ("table", {"columns": ["time", "value"], "rows": [["t1", 4.0]]}),
        ("bar", {"time": "t1", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}),
        ("histogram", {"bins": [{"lower": 0.0, "upper": 1.0, "count": 2}]}),
        ("range", {"low": 1.25, "high": 3.75}),
        ("scatter", {"points": [{"x": 1.0, "y": 2.0}]}),
        ("heatmap", {"x": ["x1"], "y": ["y1"], "values": [[2.0]]}),
        ("dashboard", {"panels": [{"name": "equity", "value": [1.0, 2.0]}]}),
        ("events", [{"event_id": "event-1", "timestamp": "2026-10-23T00:00:00Z"}]),
    ),
)
async def test_hydrator_injects_owner_scoped_study_resolver_and_checks_exact_reference(
    artifact_type: str, study_value: Any
) -> None:
    values = _inputs_with_selected_study_artifact_reference(
        artifact_type=artifact_type, value=study_value
    )
    expected = values["selected_study_artifact"]
    seen: list[tuple[Any, SelectedStudyArtifactReference]] = []
    output_payload = values["selected_study_payload"]
    expected_output = ResolvedStudyArtifactOutput(expected, output_payload)

    async def resolver(
        *, principal: Any, reference: SelectedStudyArtifactReference
    ) -> ResolvedStudyArtifactOutput:
        seen.append((principal, reference))
        return ResolvedStudyArtifactOutput(reference, output_payload)

    hydrated = await NautilusTrialDomainHydrator(
        MemoryDomainReader(values),
        selected_study_artifact_resolver=resolver,
    ).hydrate_attempt(principal="alice", attempt_resource_id=values["attempt"].attempt_id)

    assert hydrated.strategies[0].selected_study_artifact == expected
    assert hydrated.study_artifacts is not None
    assert hydrated.study_artifacts[hydrated.strategies[0].fingerprint] == expected_output
    assert seen == [("alice", expected)]

    with pytest.raises(TrialDomainHydrationError, match="attempt is missing"):
        await NautilusTrialDomainHydrator(
            MemoryDomainReader(values),
            selected_study_artifact_resolver=resolver,
        ).hydrate_attempt(principal="bob", attempt_resource_id=values["attempt"].attempt_id)
    assert seen == [("alice", expected)]

    async def mismatched_resolver(
        *, principal: Any, reference: SelectedStudyArtifactReference
    ) -> ResolvedStudyArtifactOutput:
        return ResolvedStudyArtifactOutput(
            replace(reference, artifact_id=reference.artifact_id + 1),
            output_payload,
        )

    with pytest.raises(
        TrialDomainHydrationError,
        match="differs from the immutable strategy reference",
    ):
        await NautilusTrialDomainHydrator(
            MemoryDomainReader(values),
            selected_study_artifact_resolver=mismatched_resolver,
        ).hydrate_attempt(principal="alice", attempt_resource_id=values["attempt"].attempt_id)


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
