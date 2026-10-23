from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CarryInMode,
    ForwardInstance,
    ForwardState,
    PortfolioComponent,
    PortfolioComposition,
    ResolvedStudyArtifactOutput,
    SelectedStudyArtifactReference,
)
from app.strategy_lab_v2.forward_execution_plan import (
    ForwardComponentExecutionPlan,
    ForwardExecutionPlan,
)
from app.strategy_lab_v2.forward_execution_plan_resolution import (
    AuthenticatedForwardExecutionPlanResolver,
)
from app.strategy_lab_v2.nautilus_forward_session import (
    ResolvedForwardExecutionPlanRecipeResolver,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.study_artifact_payloads import FrozenStudyArtifactPayload
from app.strategy_lab_v2.tests.test_strategy_package_resolution import (
    RUNTIME_ABI as PACKAGE_RUNTIME_ABI,
)
from app.strategy_lab_v2.tests.test_strategy_package_resolution import (
    _fixture as _strategy_package_fixture,
)

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def _digest(value: str) -> str:
    return content_digest(value)


def _portfolio() -> PortfolioComposition:
    return PortfolioComposition(
        portfolio_id="portfolio-1",
        version_id="v1",
        initial_capital=Decimal("10000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                "momentum", _digest("strategy-momentum"), ("US.ABC",), Decimal("0.6")
            ),
            PortfolioComponent(
                "mean-reversion", _digest("strategy-mean-reversion"), ("US.XYZ",), Decimal("0.4")
            ),
        ),
    )


def _instance(portfolio: PortfolioComposition) -> ForwardInstance:
    return ForwardInstance(
        "forward-1",
        portfolio.fingerprint,
        _digest("snapshot"),
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW,
        NOW,
    )


def _component(
    component_id: str,
    strategy_fingerprint: str,
    *,
    seed: int = 23,
) -> ForwardComponentExecutionPlan:
    return ForwardComponentExecutionPlan(
        component_id,
        strategy_fingerprint,
        _digest(f"package:{component_id}"),
        {"threshold": 0.5},
        seed,
    )


def test_forward_plan_is_canonical_and_binds_every_component() -> None:
    portfolio = _portfolio()
    instance = _instance(portfolio)
    momentum, mean_reversion = portfolio.components
    plan = ForwardExecutionPlan(
        instance.instance_id,
        portfolio.fingerprint,
        (
            _component("mean-reversion", mean_reversion.strategy_fingerprint),
            _component("momentum", momentum.strategy_fingerprint),
        ),
    )

    plan.validate_bindings(instance=instance, portfolio=portfolio)

    assert tuple(item.component_id for item in plan.components) == (
        "mean-reversion",
        "momentum",
    )
    with pytest.raises(TypeError):
        plan.components[0].parameters["threshold"] = 0.7  # type: ignore[index]


def test_forward_plan_fingerprint_changes_with_any_executable_input() -> None:
    portfolio = _portfolio()
    momentum = portfolio.components[0]
    first = ForwardExecutionPlan(
        "forward-1",
        portfolio.fingerprint,
        (_component(momentum.component_id, momentum.strategy_fingerprint),),
    )
    changed_seed = ForwardExecutionPlan(
        "forward-1",
        portfolio.fingerprint,
        (_component(momentum.component_id, momentum.strategy_fingerprint, seed=24),),
    )

    assert first.fingerprint != changed_seed.fingerprint


def test_forward_plan_rejects_incomplete_or_mismatched_portfolio_bindings() -> None:
    portfolio = _portfolio()
    instance = _instance(portfolio)
    momentum = portfolio.components[0]
    missing_component = ForwardExecutionPlan(
        instance.instance_id,
        portfolio.fingerprint,
        (_component(momentum.component_id, momentum.strategy_fingerprint),),
    )
    wrong_strategy = ForwardExecutionPlan(
        instance.instance_id,
        portfolio.fingerprint,
        tuple(
            _component(
                item.component_id,
                _digest("wrong-strategy") if index == 0 else item.strategy_fingerprint,
            )
            for index, item in enumerate(portfolio.components)
        ),
    )
    foreign_instance = ForwardExecutionPlan(
        "another-instance",
        portfolio.fingerprint,
        tuple(
            _component(item.component_id, item.strategy_fingerprint)
            for item in portfolio.components
        ),
    )

    with pytest.raises(ValueError, match="every portfolio component"):
        missing_component.validate_bindings(instance=instance, portfolio=portfolio)
    with pytest.raises(ValueError, match="strategy differs"):
        wrong_strategy.validate_bindings(instance=instance, portfolio=portfolio)
    with pytest.raises(ValueError, match="another instance"):
        foreign_instance.validate_bindings(instance=instance, portfolio=portfolio)


def test_forward_component_plan_rejects_boolean_seed_and_non_digest_package() -> None:
    with pytest.raises(TypeError, match="random_seed"):
        _component("momentum", _digest("strategy"), seed=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="package_fingerprint"):
        ForwardComponentExecutionPlan("momentum", _digest("strategy"), "unverified", {}, 1)


@pytest.mark.asyncio
async def test_authenticated_resolver_reads_every_pinned_package_and_archive(tmp_path) -> None:
    artifact_store, package, strategy, manifest, _archive = _strategy_package_fixture(tmp_path)
    portfolio = PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("10000"),
        "USD",
        (
            PortfolioComponent("momentum", strategy.fingerprint, ("US.AAPL",), Decimal("0.6")),
            PortfolioComponent(
                "mean-reversion", strategy.fingerprint, ("US.MSFT",), Decimal("0.4")
            ),
        ),
    )
    instance = _instance(portfolio)
    binding = ForwardComponentExecutionPlan(
        "momentum",
        strategy.fingerprint,
        package.fingerprint,
        {"lookback": 20},
        1337,
    )
    second_binding = ForwardComponentExecutionPlan(
        "mean-reversion",
        strategy.fingerprint,
        package.fingerprint,
        {"lookback": 8},
        7,
    )
    plan = ForwardExecutionPlan(
        instance.instance_id,
        portfolio.fingerprint,
        (binding, second_binding),
    )

    class Reader:
        async def get_domain_contract(
            self, *, principal, resource_type, resource_id
        ) -> object | None:
            if principal == "owner" and resource_type is ApiResourceType.FORWARD_EXECUTION_PLAN:
                return plan if resource_id == instance.instance_id else None
            return None

        async def get_domain_contracts_by_fingerprint(
            self, *, principal, resource_type, fingerprints
        ) -> dict[str, object]:
            if principal != "owner":
                return {}
            available: dict[ApiResourceType, dict[str, object]] = {
                ApiResourceType.PORTFOLIO: {portfolio.fingerprint: portfolio},
                ApiResourceType.STRATEGY: {strategy.fingerprint: strategy},
                ApiResourceType.PACKAGE: {package.fingerprint: package},
            }
            source = available.get(resource_type, {})
            return {
                fingerprint: source[fingerprint]
                for fingerprint in fingerprints
                if fingerprint in source
            }

    resolver = AuthenticatedForwardExecutionPlanResolver(
        Reader(),
        StrategyPackageArtifactResolver(artifact_store, runtime_abi=PACKAGE_RUNTIME_ABI),
        principal="owner",
    )

    resolved = await resolver.resolve(instance)

    assert resolved.plan.fingerprint == plan.fingerprint
    assert resolved.components["momentum"].binding == binding
    assert resolved.components["momentum"].package == package
    assert resolved.components["momentum"].strategy == strategy
    assert resolved.components["momentum"].resolved_package.manifest == manifest
    assert resolved.components["mean-reversion"].binding == second_binding

    recipe_resolver = ResolvedForwardExecutionPlanRecipeResolver(
        resolved,
        component_id="momentum",
        principal="owner",
    )
    recipe = recipe_resolver(principal="owner", instance=instance)
    assert recipe.portfolio_fingerprint == portfolio.fingerprint
    assert recipe.component_id == "momentum"
    assert recipe.manifest == manifest
    assert recipe.parameters == binding.parameters
    assert recipe.random_seed == binding.random_seed
    with pytest.raises(ValueError, match="another principal"):
        recipe_resolver(principal="other-owner", instance=instance)
    with pytest.raises(ValueError, match="another instance revision"):
        recipe_resolver(
            principal="owner",
            instance=replace(instance, updated_at=NOW.replace(day=6)),
        )
    with pytest.raises(ValueError, match="not present in the resolved forward plan"):
        ResolvedForwardExecutionPlanRecipeResolver(
            resolved,
            component_id="missing-component",
            principal="owner",
        )
    second_recipe = ResolvedForwardExecutionPlanRecipeResolver(
        resolved,
        component_id="mean-reversion",
        principal="owner",
    )(principal="owner", instance=instance)
    assert second_recipe.manifest == recipe.manifest
    assert second_recipe.parameters == second_binding.parameters
    assert second_recipe.random_seed == second_binding.random_seed


@pytest.mark.asyncio
async def test_authenticated_resolver_fails_closed_for_another_owner(tmp_path) -> None:
    artifact_store, _package, _strategy, _manifest, _archive = _strategy_package_fixture(tmp_path)
    portfolio = _portfolio()
    instance = _instance(portfolio)

    class Reader:
        async def get_domain_contract(self, **_kwargs) -> object | None:
            return None

        async def get_domain_contracts_by_fingerprint(self, **_kwargs) -> dict[str, object]:
            return {}

    resolver = AuthenticatedForwardExecutionPlanResolver(
        Reader(),
        StrategyPackageArtifactResolver(artifact_store, runtime_abi=PACKAGE_RUNTIME_ABI),
        principal="another-owner",
    )

    with pytest.raises(ValueError, match="execution plan is unavailable"):
        await resolver.resolve(instance)


@pytest.mark.asyncio
async def test_authenticated_resolver_binds_selected_study_output_or_fails_closed(
    tmp_path,
) -> None:
    payload = {"type": "series", "value": [1.25, 2.5]}
    reference = SelectedStudyArtifactReference(
        research_run_id=17,
        code_version_id=23,
        artifact_id=31,
        artifact_name="study.close",
        artifact_type="series",
        output_contract="study",
        run_reproducibility_hash="a" * 64,
        code_version_digest=content_digest("code-version"),
        dataset_manifest_digest=content_digest("dataset"),
        artifact_content_digest=content_digest(payload),
    )
    output = ResolvedStudyArtifactOutput(reference, cast(FrozenStudyArtifactPayload, payload))
    artifact_store, package, strategy, _manifest, _archive = _strategy_package_fixture(
        tmp_path,
        selected_study_artifact=reference,
    )
    portfolio = PortfolioComposition(
        "portfolio-study",
        "v1",
        Decimal("10000"),
        "USD",
        (PortfolioComponent("momentum", strategy.fingerprint, ("US.AAPL",), Decimal("1")),),
    )
    instance = _instance(portfolio)
    binding = ForwardComponentExecutionPlan(
        "momentum",
        strategy.fingerprint,
        package.fingerprint,
        {"lookback": 5},
        1337,
    )
    plan = ForwardExecutionPlan(instance.instance_id, portfolio.fingerprint, (binding,))

    class Reader:
        async def get_domain_contract(self, *, principal, resource_type, resource_id):
            if (
                principal == "owner"
                and resource_type is ApiResourceType.FORWARD_EXECUTION_PLAN
                and resource_id == instance.instance_id
            ):
                return plan
            return None

        async def get_domain_contracts_by_fingerprint(
            self, *, principal, resource_type, fingerprints
        ):
            if principal != "owner":
                return {}
            available = {
                ApiResourceType.PORTFOLIO: {portfolio.fingerprint: portfolio},
                ApiResourceType.STRATEGY: {strategy.fingerprint: strategy},
                ApiResourceType.PACKAGE: {package.fingerprint: package},
            }.get(resource_type, {})
            return {key: available[key] for key in fingerprints if key in available}

    resolver_calls = 0

    async def resolve_study(*, principal, reference):
        nonlocal resolver_calls
        assert principal == "owner"
        assert reference == expected_reference
        resolver_calls += 1
        if resolver_calls > 1:
            return ResolvedStudyArtifactOutput(
                replace(reference, artifact_id=reference.artifact_id + 1),
                payload,
            )
        return output

    expected_reference = reference
    resolver = AuthenticatedForwardExecutionPlanResolver(
        Reader(),
        StrategyPackageArtifactResolver(artifact_store, runtime_abi=PACKAGE_RUNTIME_ABI),
        principal="owner",
        selected_study_artifact_resolver=resolve_study,
    )
    resolved = await resolver.resolve(instance)
    assert resolved.components["momentum"].study_artifacts == {"study.close": output}
    recipe = ResolvedForwardExecutionPlanRecipeResolver(
        resolved,
        component_id="momentum",
        principal="owner",
    )(principal="owner", instance=instance)
    assert recipe.study_artifacts == {"study.close": output}
    assert resolver_calls == 1

    without_study_resolver = AuthenticatedForwardExecutionPlanResolver(
        Reader(),
        StrategyPackageArtifactResolver(artifact_store, runtime_abi=PACKAGE_RUNTIME_ABI),
        principal="owner",
    )
    with pytest.raises(ValueError, match="cannot be revalidated"):
        await without_study_resolver.resolve(instance)

    with pytest.raises(ValueError, match="mismatched immutable output"):
        await resolver.resolve(instance)
    assert resolver_calls == 2
