"""Immutable, engine-neutral input bindings for persistent forward execution.

Forward instances must not select an arbitrary package or silently inherit
mutable strategy defaults at worker start. This value pins one exact strategy
version, package, parameter set, and seed for each immutable portfolio
component. Persistence and artifact resolution remain host-owned adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import ForwardInstance, PortfolioComposition


@dataclass(frozen=True, slots=True)
class ForwardComponentExecutionPlan:
    """Reproducible executable inputs for one portfolio component."""

    component_id: str
    strategy_fingerprint: str
    package_fingerprint: str
    parameters: Mapping[str, Any]
    random_seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        require_sha256_digest(self.strategy_fingerprint, field_name="strategy_fingerprint")
        require_sha256_digest(self.package_fingerprint, field_name="package_fingerprint")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise TypeError("random_seed must be an integer")
        frozen_parameters = freeze_json(dict(self.parameters))
        if not isinstance(frozen_parameters, Mapping):
            raise TypeError("parameters must freeze to a mapping")
        object.__setattr__(self, "parameters", frozen_parameters)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardExecutionPlan:
    """Exact immutable strategy inputs bound to a forward instance and portfolio."""

    instance_id: str
    portfolio_fingerprint: str
    components: tuple[ForwardComponentExecutionPlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        components = tuple(self.components)
        if not components or any(
            not isinstance(item, ForwardComponentExecutionPlan) for item in components
        ):
            raise TypeError("components must contain ForwardComponentExecutionPlan values")
        component_ids = [item.component_id for item in components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("forward execution plan component ids must be unique")
        object.__setattr__(
            self, "components", tuple(sorted(components, key=lambda x: x.component_id))
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def validate_bindings(
        self,
        *,
        instance: ForwardInstance,
        portfolio: PortfolioComposition,
    ) -> None:
        """Fail closed unless this plan exactly covers the immutable portfolio."""

        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must use ForwardInstance")
        if not isinstance(portfolio, PortfolioComposition):
            raise TypeError("portfolio must use PortfolioComposition")
        if self.instance_id != instance.instance_id:
            raise ValueError("forward execution plan belongs to another instance")
        if (
            self.portfolio_fingerprint != instance.portfolio_fingerprint
            or portfolio.fingerprint != instance.portfolio_fingerprint
        ):
            raise ValueError("forward execution plan portfolio differs from its instance")
        component_by_id = {item.component_id: item for item in portfolio.components}
        plan_by_id = {item.component_id: item for item in self.components}
        if set(component_by_id) != set(plan_by_id):
            raise ValueError("forward execution plan must bind every portfolio component exactly")
        for component_id, component in component_by_id.items():
            if plan_by_id[component_id].strategy_fingerprint != component.strategy_fingerprint:
                raise ValueError(
                    f"forward execution plan strategy differs for component {component_id!r}"
                )


__all__ = ["ForwardComponentExecutionPlan", "ForwardExecutionPlan"]
