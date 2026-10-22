"""Owner-authenticated recipe resolution for persistent forward instances."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ForwardInstance,
    PortfolioComposition,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.forward_execution_plan import (
    ForwardComponentExecutionPlan,
    ForwardExecutionPlan,
)
from app.strategy_lab_v2.strategy_package_resolution import (
    ResolvedStrategyPackage,
    StrategyPackageArtifactResolver,
)


class ForwardExecutionPlanReader(Protocol):
    """Owner-scoped canonical domain reads used by the forward worker."""

    async def get_domain_contract(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> Any | None: ...

    async def get_domain_contracts_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprints: Sequence[str],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ResolvedForwardExecutionComponent:
    """One component's exact package bytes and immutable strategy settings."""

    binding: ForwardComponentExecutionPlan
    strategy: StrategyVersion
    package: StrategyPackage
    resolved_package: ResolvedStrategyPackage

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ForwardComponentExecutionPlan):
            raise TypeError("binding must use ForwardComponentExecutionPlan")
        if not isinstance(self.strategy, StrategyVersion):
            raise TypeError("strategy must use StrategyVersion")
        if not isinstance(self.package, StrategyPackage):
            raise TypeError("package must use StrategyPackage")
        if not isinstance(self.resolved_package, ResolvedStrategyPackage):
            raise TypeError("resolved_package must use ResolvedStrategyPackage")
        if self.strategy.fingerprint != self.binding.strategy_fingerprint:
            raise ValueError("resolved forward strategy differs from its pinned fingerprint")
        if self.package.fingerprint != self.binding.package_fingerprint:
            raise ValueError("resolved forward package differs from its pinned fingerprint")
        if self.package.strategy_fingerprint != self.strategy.fingerprint:
            raise ValueError("resolved forward package references a different strategy")
        if self.resolved_package.package_fingerprint != self.package.fingerprint:
            raise ValueError("resolved forward archive differs from its pinned package")
        if self.resolved_package.strategy_fingerprint != self.strategy.fingerprint:
            raise ValueError("resolved forward archive differs from its pinned strategy")
        if self.resolved_package.manifest.strategy.fingerprint != self.strategy.fingerprint:
            raise ValueError("resolved forward manifest differs from its pinned strategy")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "binding": self.binding,
                "package_fingerprint": self.package.fingerprint,
                "resolved_package_fingerprint": self.resolved_package.fingerprint,
                "strategy_fingerprint": self.strategy.fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class ResolvedForwardExecutionPlan:
    """Fully authenticated, portfolio-wide forward strategy recipe."""

    instance: ForwardInstance
    portfolio: PortfolioComposition
    plan: ForwardExecutionPlan
    components: Mapping[str, ResolvedForwardExecutionComponent]

    def __post_init__(self) -> None:
        if not isinstance(self.instance, ForwardInstance):
            raise TypeError("instance must use ForwardInstance")
        if not isinstance(self.portfolio, PortfolioComposition):
            raise TypeError("portfolio must use PortfolioComposition")
        if not isinstance(self.plan, ForwardExecutionPlan):
            raise TypeError("plan must use ForwardExecutionPlan")
        if not isinstance(self.components, Mapping):
            raise TypeError("components must be a mapping")
        components = dict(self.components)
        if any(
            not isinstance(key, str)
            or not isinstance(value, ResolvedForwardExecutionComponent)
            or key != value.binding.component_id
            for key, value in components.items()
        ):
            raise TypeError("components must map component ids to resolved component inputs")
        if set(components) != {item.component_id for item in self.plan.components}:
            raise ValueError("resolved components do not exactly cover the execution plan")
        self.plan.validate_bindings(instance=self.instance, portfolio=self.portfolio)
        object.__setattr__(self, "components", MappingProxyType(dict(sorted(components.items()))))

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "instance_fingerprint": content_digest(self.instance),
                "portfolio_fingerprint": self.portfolio.fingerprint,
                "plan_fingerprint": self.plan.fingerprint,
                "components": {
                    component_id: component.fingerprint
                    for component_id, component in self.components.items()
                },
            }
        )


class AuthenticatedForwardExecutionPlanResolver:
    """Resolve exact owner-scoped packages for every forward portfolio component.

    All domain lookups are scoped to the authenticated principal and pinned
    fingerprints. Strategy source and dependency artifacts are verified by the
    existing package resolver; no provider or mutable package selection is
    involved.
    """

    def __init__(
        self,
        reader: ForwardExecutionPlanReader,
        package_resolver: StrategyPackageArtifactResolver,
        *,
        principal: Any,
    ) -> None:
        if not callable(getattr(reader, "get_domain_contract", None)) or not callable(
            getattr(reader, "get_domain_contracts_by_fingerprint", None)
        ):
            raise TypeError("reader must provide owner-scoped typed domain reads")
        if not isinstance(package_resolver, StrategyPackageArtifactResolver):
            raise TypeError("package_resolver must use StrategyPackageArtifactResolver")
        self._reader = reader
        self._package_resolver = package_resolver
        self._principal = principal

    async def resolve(self, instance: ForwardInstance) -> ResolvedForwardExecutionPlan:
        """Load and verify one exact plan and all packages in the instance portfolio."""

        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must use ForwardInstance")
        plan = await self._reader.get_domain_contract(
            principal=self._principal,
            resource_type=ApiResourceType.FORWARD_EXECUTION_PLAN,
            resource_id=instance.instance_id,
        )
        if not isinstance(plan, ForwardExecutionPlan):
            raise ValueError("owner-scoped forward execution plan is unavailable")
        if plan.instance_id != instance.instance_id:
            raise ValueError("forward execution plan belongs to another instance")
        if plan.portfolio_fingerprint != instance.portfolio_fingerprint:
            raise ValueError("forward execution plan differs from the instance portfolio")

        portfolios = await self._reader.get_domain_contracts_by_fingerprint(
            principal=self._principal,
            resource_type=ApiResourceType.PORTFOLIO,
            fingerprints=(instance.portfolio_fingerprint,),
        )
        portfolio = portfolios.get(instance.portfolio_fingerprint)
        if not isinstance(portfolio, PortfolioComposition):
            raise ValueError("owner-scoped forward portfolio is unavailable")
        plan.validate_bindings(instance=instance, portfolio=portfolio)

        strategy_fingerprints = tuple(
            sorted({item.strategy_fingerprint for item in plan.components})
        )
        package_fingerprints = tuple(sorted({item.package_fingerprint for item in plan.components}))
        strategies, packages = await _read_component_domains(
            self._reader,
            principal=self._principal,
            strategy_fingerprints=strategy_fingerprints,
            package_fingerprints=package_fingerprints,
        )
        resolved: dict[str, ResolvedForwardExecutionComponent] = {}
        for binding in plan.components:
            strategy = strategies[binding.strategy_fingerprint]
            package = packages[binding.package_fingerprint]
            if package.strategy_fingerprint != strategy.fingerprint:
                raise ValueError("pinned forward package does not match its strategy")
            if package.sdk_version != strategy.sdk_version:
                raise ValueError("pinned forward package SDK differs from its strategy")
            resolved_package = self._package_resolver.resolve(package, strategy)
            resolved[binding.component_id] = ResolvedForwardExecutionComponent(
                binding=binding,
                strategy=strategy,
                package=package,
                resolved_package=resolved_package,
            )
        return ResolvedForwardExecutionPlan(instance, portfolio, plan, resolved)


async def _read_component_domains(
    reader: ForwardExecutionPlanReader,
    *,
    principal: Any,
    strategy_fingerprints: tuple[str, ...],
    package_fingerprints: tuple[str, ...],
) -> tuple[dict[str, StrategyVersion], dict[str, StrategyPackage]]:
    strategies_by_fingerprint = await reader.get_domain_contracts_by_fingerprint(
        principal=principal,
        resource_type=ApiResourceType.STRATEGY,
        fingerprints=strategy_fingerprints,
    )
    packages_by_fingerprint = await reader.get_domain_contracts_by_fingerprint(
        principal=principal,
        resource_type=ApiResourceType.PACKAGE,
        fingerprints=package_fingerprints,
    )
    if set(strategies_by_fingerprint) != set(strategy_fingerprints) or any(
        not isinstance(value, StrategyVersion) for value in strategies_by_fingerprint.values()
    ):
        raise ValueError("an owner-scoped forward strategy is unavailable")
    if set(packages_by_fingerprint) != set(package_fingerprints) or any(
        not isinstance(value, StrategyPackage) for value in packages_by_fingerprint.values()
    ):
        raise ValueError("an owner-scoped forward package is unavailable")
    strategies: dict[str, StrategyVersion] = {}
    for fingerprint, value in strategies_by_fingerprint.items():
        if value.fingerprint != fingerprint:
            raise ValueError("owner-scoped strategy lookup returned a mismatched fingerprint")
        strategies[fingerprint] = value
    packages: dict[str, StrategyPackage] = {}
    for fingerprint, value in packages_by_fingerprint.items():
        if value.fingerprint != fingerprint:
            raise ValueError("owner-scoped package lookup returned a mismatched fingerprint")
        packages[fingerprint] = value
    return strategies, packages


__all__ = [
    "AuthenticatedForwardExecutionPlanResolver",
    "ForwardExecutionPlanReader",
    "ResolvedForwardExecutionComponent",
    "ResolvedForwardExecutionPlan",
]
