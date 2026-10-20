"""Fail-closed production composition for local Provider capability preflight.

Only the currently source-proven equity/market/cash backtest scope is exposed.
Provider data resolution remains a local database read; Nautilus evidence is
loaded from the exact operator-pinned artifact and checked by the existing
conformance binding builder. This module never starts an engine or contacts a
provider.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.strategy_lab_v2.capabilities import ProductClass
from app.strategy_lab_v2.capability_preparation import CapabilityPreflightService
from app.strategy_lab_v2.conformance_fixtures import build_nautilus_backtest_execution_binding
from app.strategy_lab_v2.local_conformance_source import LocalNautilusRcConformanceEvidenceSource
from app.strategy_lab_v2.provider_preflight import ProviderLocalCapabilityEvidenceReader

CAPABILITY_SCOPE_CONFIG_ENV = "STRATEGY_LAB_V2_BACKTEST_CAPABILITY_SCOPE"
_SUPPORTED_SCOPE = {
    "product_classes": ("equity",),
    "execution_models": ("market",),
    "account_models": ("cash",),
}


def _configured_scope(
    environment: Mapping[str, str],
) -> tuple[frozenset[ProductClass], frozenset[str], frozenset[str]] | None:
    raw = environment.get(CAPABILITY_SCOPE_CONFIG_ENV, "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{CAPABILITY_SCOPE_CONFIG_ENV} must be valid JSON") from error
    if not isinstance(value, dict) or set(value) != set(_SUPPORTED_SCOPE):
        raise ValueError(
            f"{CAPABILITY_SCOPE_CONFIG_ENV} must declare exactly the supported scope fields"
        )
    for field, supported in _SUPPORTED_SCOPE.items():
        configured = value[field]
        if not isinstance(configured, list) or tuple(configured) != supported:
            raise ValueError(f"{CAPABILITY_SCOPE_CONFIG_ENV} contains an unproven {field} scope")
    return (
        frozenset({ProductClass.EQUITY}),
        frozenset({"market"}),
        frozenset({"cash"}),
    )


def build_provider_capability_preflight(
    session_factory: Any,
    *,
    environment: Mapping[str, str] | None = None,
) -> CapabilityPreflightService | None:
    """Compose the real API preflight only for complete, exact host evidence.

    Unconfigured, partial, malformed, or invalid evidence remains unavailable;
    the caller preserves the registered route's existing 501 response.
    """

    import os

    values = os.environ if environment is None else environment
    try:
        scope = _configured_scope(values)
        if scope is None:
            return None
        evidence_source = LocalNautilusRcConformanceEvidenceSource.from_environment(values)
        if evidence_source is None:
            return None
        resolution = evidence_source.load()
        product_classes, execution_models, account_models = scope
        execution_binding = build_nautilus_backtest_execution_binding(
            resolution,
            product_classes=product_classes,
            execution_models=execution_models,
            account_models=account_models,
        )
    except (OSError, TypeError, ValueError):
        # Invalid operator config/evidence must not take down search/calendar
        # registrations or accidentally enable a looser fallback.
        return None

    provider_reader = ProviderLocalCapabilityEvidenceReader(
        session_factory,
        execution_models=tuple(execution_models),
        account_models=tuple(account_models),
    )

    def resolve_execution_binding(**_kwargs: Any) -> Any:
        return execution_binding

    return CapabilityPreflightService(
        capability_cells=provider_reader,
        execution_binding=resolve_execution_binding,
    )
