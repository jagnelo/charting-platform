"""Trusted host composition for Strategy Lab capability preflight.

The API client declares what it wants to test.  Local host adapters supply
coverage cells and an exact engine/conformance binding; client payloads never
provide those facts.  This module joins the existing engine-neutral preflight
and execution-capability contracts into the summary persisted by the API.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    Degradation,
    preflight_capabilities,
)
from app.strategy_lab_v2.capability_summary import CapabilitySummary, build_capability_summary
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.etf_pit import ETFPointInTimeMembership, membership_reference
from app.strategy_lab_v2.execution_capabilities import (
    ExecutionCapabilityBinding,
    preflight_execution_capability,
)
from app.strategy_lab_v2.provider_series_contract import (
    ProviderSeriesCapabilityEvidence,
    provider_series_capability_cell,
)

CapabilityCellsResolver = Callable[
    ...,
    Sequence[CapabilityCell | ProviderSeriesCapabilityEvidence]
    | Awaitable[Sequence[CapabilityCell | ProviderSeriesCapabilityEvidence]],
]
ExecutionBindingResolver = Callable[
    ..., ExecutionCapabilityBinding | Awaitable[ExecutionCapabilityBinding]
]


@dataclass(frozen=True, slots=True)
class CapabilityPreflightRequest:
    """Strictly parsed client requirements, without trusted evidence fields."""

    requirements: tuple[CapabilityRequirement, ...]
    allow_degraded: bool = False
    degradations: tuple[Degradation, ...] = ()
    etf_memberships: tuple[tuple[str, datetime], ...] = ()

    def __post_init__(self) -> None:
        requirements = tuple(self.requirements)
        degradations = tuple(self.degradations)
        etf_memberships = tuple(self.etf_memberships)
        if not requirements or any(
            not isinstance(item, CapabilityRequirement) for item in requirements
        ):
            raise ValueError("requirements must contain at least one typed capability requirement")
        if any(not isinstance(item, Degradation) for item in degradations):
            raise TypeError("degradations must contain typed Degradation values")
        if not isinstance(self.allow_degraded, bool):
            raise TypeError("allow_degraded must be a boolean")
        membership_keys = tuple(etf_memberships)
        if len(membership_keys) != len(set(membership_keys)):
            raise ValueError("ETF membership selectors must be unique in a preflight")
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "degradations", degradations)
        object.__setattr__(self, "etf_memberships", etf_memberships)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CapabilityPreflightRequest:
        if not isinstance(payload, Mapping):
            raise ValueError("capability preflight payload must be an object")
        unknown = sorted(
            set(payload) - {"requirements", "allow_degraded", "degradations", "etf_memberships"}
        )
        if unknown:
            raise ValueError(
                "capability preflight payload contains unsupported fields: " + ", ".join(unknown)
            )
        raw_requirements = payload.get("requirements")
        if not isinstance(raw_requirements, Sequence) or isinstance(raw_requirements, str | bytes):
            raise ValueError("requirements must be an array")
        raw_degradations = payload.get("degradations", ())
        if not isinstance(raw_degradations, Sequence) or isinstance(raw_degradations, str | bytes):
            raise ValueError("degradations must be an array")
        allow_degraded = payload.get("allow_degraded", False)
        if not isinstance(allow_degraded, bool):
            raise ValueError("allow_degraded must be a boolean")
        raw_memberships = payload.get("etf_memberships", ())
        if not isinstance(raw_memberships, Sequence) or isinstance(raw_memberships, str | bytes):
            raise ValueError("etf_memberships must be an array")
        return cls(
            requirements=tuple(_requirement(item) for item in raw_requirements),
            allow_degraded=allow_degraded,
            degradations=tuple(_degradation(item) for item in raw_degradations),
            etf_memberships=tuple(_etf_membership(item) for item in raw_memberships),
        )


class CapabilityPreflightService:
    """Resolve trusted data/engine evidence and produce an API capability summary."""

    def __init__(
        self,
        *,
        capability_cells: CapabilityCellsResolver,
        execution_binding: ExecutionBindingResolver,
        etf_membership_reader: Callable[..., Any] | None = None,
    ) -> None:
        if not callable(capability_cells):
            raise TypeError("capability_cells must be callable")
        if not callable(execution_binding):
            raise TypeError("execution_binding must be callable")
        self._capability_cells = capability_cells
        self._execution_binding = execution_binding
        if etf_membership_reader is not None and not callable(etf_membership_reader):
            raise TypeError("etf_membership_reader must be callable")
        self._etf_membership_reader = etf_membership_reader

    async def __call__(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        payload_digest: str,
    ) -> CapabilitySummary:
        """Preflight client requirements against host-owned evidence only."""

        if not _nonempty(request_id) or not _nonempty(idempotency_key):
            raise ValueError("request_id and idempotency_key must not be empty")
        if not isinstance(payload_digest, str) or payload_digest != content_digest(payload):
            raise ValueError("payload_digest does not match the canonical request payload")
        request = CapabilityPreflightRequest.from_payload(payload)

        etf_memberships = []
        for etf_instrument_id, decision_time in request.etf_memberships:
            if self._etf_membership_reader is None:
                raise ValueError("ETF membership preflight is unavailable on this host")
            resolved = self._etf_membership_reader(
                etf_instrument_id=etf_instrument_id,
                decision_time=decision_time,
            )
            evidence = await resolved if inspect.isawaitable(resolved) else resolved
            if not isinstance(evidence, ETFPointInTimeMembership):
                raise TypeError("ETF membership reader returned untrusted evidence")
            if evidence.etf_instrument_id != etf_instrument_id:
                raise ValueError("ETF membership reader returned a foreign ETF identity")
            if (
                evidence.known_at.tzinfo is None
                or evidence.known_at.utcoffset() is None
                or evidence.known_at > decision_time
                or evidence.composition_date > decision_time.date()
            ):
                raise ValueError("ETF membership is missing or later than decision_time")
            member_keys = tuple(member.domain_key for member in evidence.constituents)
            member_ids = tuple(member.instrument_id for member in evidence.constituents)
            if (
                not member_keys
                or len(member_keys) != len(set(member_keys))
                or len(member_ids) != len(set(member_ids))
            ):
                raise ValueError("ETF membership is empty or contains duplicate identities")
            for member in evidence.constituents:
                member_requirements = tuple(
                    item for item in request.requirements if item.instrument_id == member.domain_key
                )
                if len(member_requirements) != 1:
                    raise ValueError(
                        "every frozen ETF constituent requires one explicit Provider coverage requirement"
                    )
                member_requirement = member_requirements[0]
                if (
                    member_requirement.product_class is not ProductClass.EQUITY
                    or member_requirement.event_type != "ohlcv"
                    or member_requirement.event_granularity is not EventGranularity.BAR
                    or not member_requirement.start <= decision_time <= member_requirement.end
                ):
                    raise ValueError(
                        "ETF constituents require equity OHLCV coverage spanning decision_time"
                    )
            etf_memberships.append(evidence)

        cells_result = self._capability_cells(
            principal=principal,
            request_id=request_id,
            idempotency_key=idempotency_key,
            requirements=request.requirements,
        )
        cells = await cells_result if inspect.isawaitable(cells_result) else cells_result
        if not isinstance(cells, Sequence) or isinstance(cells, str | bytes):
            raise TypeError("capability_cells must return a sequence")
        if any(
            not isinstance(item, CapabilityCell | ProviderSeriesCapabilityEvidence)
            for item in cells
        ):
            raise TypeError(
                "capability_cells must return typed CapabilityCell or ProviderSeriesCapabilityEvidence values"
            )
        verified_cells: list[CapabilityCell] = []
        for requirement in request.requirements:
            if (
                requirement.event_type == "ohlcv"
                and requirement.event_granularity is EventGranularity.BAR
            ):
                verification_requirement = requirement
                for degradation in request.degradations:
                    if degradation.instrument_id != requirement.instrument_id:
                        continue
                    if degradation.field not in {
                        "timeframe",
                        "adjustment",
                        "session",
                        "feed",
                        "corporate_action_semantics",
                    }:
                        continue
                    replacement_value: Any = degradation.substituted_value
                    if degradation.field == "adjustment":
                        replacement_value = AdjustmentMode(replacement_value)
                    verification_requirement = replace(
                        verification_requirement,
                        **{degradation.field: replacement_value},
                    )
                candidates = tuple(
                    item
                    for item in cells
                    if isinstance(item, ProviderSeriesCapabilityEvidence)
                    and item.manifest.instrument_id == verification_requirement.instrument_id
                )
                matching_cells = tuple(
                    cell
                    for candidate in candidates
                    if (
                        cell := provider_series_capability_cell(candidate, verification_requirement)
                    )
                    is not None
                )
                if len(matching_cells) != 1:
                    continue
                verified_cells.append(matching_cells[0])
                continue
            verified_cells.extend(
                item
                for item in cells
                if isinstance(item, CapabilityCell)
                and item.instrument_id == requirement.instrument_id
            )
        report = preflight_capabilities(
            request.requirements,
            tuple(verified_cells),
            allow_degraded=request.allow_degraded,
            degradations=request.degradations,
        )

        binding_result = self._execution_binding(
            principal=principal,
            request_id=request_id,
            idempotency_key=idempotency_key,
            requirements=request.requirements,
            report=report,
        )
        binding = await binding_result if inspect.isawaitable(binding_result) else binding_result
        if not isinstance(binding, ExecutionCapabilityBinding):
            raise TypeError("execution_binding must return an ExecutionCapabilityBinding")
        execution = preflight_execution_capability(report, binding)
        summary = build_capability_summary(report, execution)
        if etf_memberships:
            lineage_digests = tuple(item.content_digest for item in etf_memberships)
            membership_references = tuple(
                membership_reference(item, decision_time=decision_time)
                for item, (_, decision_time) in zip(
                    etf_memberships, request.etf_memberships, strict=True
                )
            )
            return replace(
                summary,
                binding_fingerprint=content_digest(
                    {"execution": summary.binding_fingerprint, "etf_lineage": lineage_digests}
                ),
                input_lineage_fingerprints=lineage_digests,
                etf_memberships=membership_references,
            )
        return summary


def _requirement(value: Any) -> CapabilityRequirement:
    fields = {
        "instrument_id",
        "product_class",
        "event_granularity",
        "event_type",
        "timeframe",
        "start",
        "end",
        "adjustment",
        "session",
        "feed",
        "execution_model",
        "account_model",
        "corporate_action_semantics",
    }
    if not isinstance(value, Mapping):
        raise ValueError("requirements must contain objects")
    unknown = sorted(set(value) - fields)
    if unknown:
        raise ValueError("requirement contains unsupported fields: " + ", ".join(unknown))
    missing = sorted(fields - set(value))
    if missing:
        raise ValueError("requirement is missing fields: " + ", ".join(missing))
    try:
        return CapabilityRequirement(
            instrument_id=value["instrument_id"],
            product_class=ProductClass(value["product_class"]),
            event_granularity=EventGranularity(value["event_granularity"]),
            event_type=value["event_type"],
            timeframe=value["timeframe"],
            start=_datetime(value["start"], "start"),
            end=_datetime(value["end"], "end"),
            adjustment=AdjustmentMode(value["adjustment"]),
            session=value["session"],
            feed=value["feed"],
            execution_model=value["execution_model"],
            account_model=value["account_model"],
            corporate_action_semantics=value["corporate_action_semantics"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid capability requirement: {error}") from error


def _degradation(value: Any) -> Degradation:
    fields = {"instrument_id", "field", "substituted_value", "reason"}
    if not isinstance(value, Mapping):
        raise ValueError("degradations must contain objects")
    unknown = sorted(set(value) - fields)
    if unknown:
        raise ValueError("degradation contains unsupported fields: " + ", ".join(unknown))
    missing = sorted(fields - set(value))
    if missing:
        raise ValueError("degradation is missing fields: " + ", ".join(missing))
    try:
        return Degradation(
            instrument_id=value["instrument_id"],
            field=value["field"],
            substituted_value=value["substituted_value"],
            reason=value["reason"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid capability degradation: {error}") from error


def _etf_membership(value: Any) -> tuple[str, datetime]:
    if not isinstance(value, Mapping) or set(value) != {"etf_instrument_id", "decision_time"}:
        raise ValueError(
            "ETF membership inputs require exactly etf_instrument_id and decision_time"
        )
    instrument_id = value["etf_instrument_id"]
    if not _nonempty(instrument_id):
        raise ValueError("etf_instrument_id must not be empty")
    return instrument_id, _datetime(value["decision_time"], "decision_time")


def _datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__ = [
    "CapabilityCellsResolver",
    "CapabilityPreflightRequest",
    "CapabilityPreflightService",
    "ExecutionBindingResolver",
]
