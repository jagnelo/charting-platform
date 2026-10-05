"""Owner-scoped PostgreSQL persistence for immutable result manifests.

Result-manifest construction remains pure in :mod:`result_materialization`.
This adapter retains the canonical manifest payload and a compact identity
projection, making successful engine evidence inspectable and retry-safe while
leaving artifact bytes and official publication to their existing gates.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

from app.strategy_lab_v2 import (
    admission,
    capabilities,
    conformance,
    contracts,
    dispatch,
    engine_execution,
    execution,
    execution_orchestration,
    forward_account,
    forward_context,
    lease_observations,
    lifecycle,
    nautilus_forward_delivery,
    nautilus_runtime_bundle,
    rebalance,
    runtime,
    runtime_execution,
    sandbox,
    sdk,
    search_dispatch,
    search_state,
    worker_process,
    workers,
)
from app.strategy_lab_v2.canonical import canonical_json, content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    DataSnapshot,
    MetricSet,
    PortfolioComposition,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    StrategyPackage,
)
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceReference
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsReference
from app.strategy_lab_v2.nautilus_result_materialization import (
    materialize_nautilus_oos_run_result,
)
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationDecision,
    ResultMaterializationResolution,
    materialize_run_result,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class ResultManifestStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class PersistedResultManifest:
    """Canonical manifest projection retained by PostgreSQL."""

    manifest_fingerprint: str
    attempt_id: str
    trial_id: str
    metric_set_fingerprint: str
    snapshot_fingerprint: str
    manifest_json: str
    record_fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "manifest_fingerprint",
            "trial_id",
            "metric_set_fingerprint",
            "snapshot_fingerprint",
            "record_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("attempt_id", "manifest_json"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.manifest_fingerprint != _payload_digest(self.manifest_json):
            raise ValueError("manifest fingerprint does not match canonical payload")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "manifest_fingerprint": self.manifest_fingerprint,
                "manifest_json": self.manifest_json,
                "metric_set_fingerprint": self.metric_set_fingerprint,
                "snapshot_fingerprint": self.snapshot_fingerprint,
                "trial_id": self.trial_id,
            }
        )


@dataclass(frozen=True, slots=True)
class PersistedArtifactReference:
    """One owner-scoped artifact reference extracted from a result manifest."""

    artifact: ArtifactManifest
    manifest_fingerprint: str
    attempt_id: str
    trial_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        require_sha256_digest(self.manifest_fingerprint, field_name="manifest_fingerprint")
        require_sha256_digest(self.trial_id, field_name="trial_id")
        for name in ("attempt_id",):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")

    @property
    def content_digest(self) -> str:
        return self.artifact.content_digest

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ResultManifestStateResolution:
    decision: ResultManifestStateDecision
    manifest: RunResultManifest
    record: PersistedResultManifest

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResultManifestStateDecision):
            raise TypeError("decision must be a ResultManifestStateDecision")
        if not isinstance(self.manifest, RunResultManifest):
            raise TypeError("manifest must be a RunResultManifest")
        if not isinstance(self.record, PersistedResultManifest):
            raise TypeError("record must be a PersistedResultManifest")


@dataclass(frozen=True, slots=True)
class PostgresResultMaterializationSchema:
    """Explicit additive DDL for immutable canonical result manifests."""

    manifest_table: str = "strategy_lab_v2_result_manifests"

    def __post_init__(self) -> None:
        if not isinstance(self.manifest_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.manifest_table
        ):
            raise ValueError("manifest_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.manifest_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                manifest_fingerprint TEXT NOT NULL,
                trial_id TEXT NOT NULL,
                metric_set_fingerprint TEXT NOT NULL,
                snapshot_fingerprint TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id),
                UNIQUE (owner_id, manifest_fingerprint)
            )
            """,
        )


class PostgresResultMaterializationAdapter:
    """Persist and authenticate canonical result-manifest projections."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresResultMaterializationSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresResultMaterializationSchema()

    @property
    def schema(self) -> PostgresResultMaterializationSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, manifest: RunResultManifest
    ) -> ResultManifestStateResolution:
        """Register a manifest or replay its exact immutable attempt identity."""

        if not isinstance(manifest, RunResultManifest):
            raise TypeError("manifest must be a RunResultManifest")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, manifest.attempt_id)
                candidate = _record(manifest)
                if current is None:
                    await self._insert(session, owner_id, candidate)
                    return ResultManifestStateResolution(
                        ResultManifestStateDecision.REGISTERED, manifest, candidate
                    )
                if current.manifest_fingerprint != candidate.manifest_fingerprint:
                    raise ValueError("PostgreSQL result manifest attempt is already bound")
                if current != candidate:
                    raise ValueError("PostgreSQL result manifest payload is already bound")
                return ResultManifestStateResolution(
                    ResultManifestStateDecision.REPLAY_EXISTING, manifest, current
                )

    async def materialize(
        self,
        *,
        principal: Any,
        trial: ScientificTrial,
        attempt: RunAttempt,
        strategy_packages: Sequence[StrategyPackage],
        portfolio: PortfolioComposition,
        snapshot: DataSnapshot,
        evidence: EngineResultEvidence,
        metric_set: MetricSet,
        output_artifacts: Sequence[ArtifactManifest],
        created_at: datetime,
    ) -> ResultMaterializationResolution:
        """Build through the pure contract, then register its manifest atomically."""

        candidate = materialize_run_result(
            trial,
            attempt,
            strategy_packages,
            portfolio,
            snapshot,
            evidence,
            metric_set,
            output_artifacts,
            created_at=created_at,
        )
        if candidate.decision is not ResultMaterializationDecision.MATERIALIZE:
            return candidate
        if candidate.manifest is None:  # pragma: no cover - pure contract guard
            raise ValueError("materialization omitted its manifest")
        try:
            persisted = await self.ensure(principal=principal, manifest=candidate.manifest)
        except ValueError as error:
            if "already bound" not in str(error):
                raise
            return ResultMaterializationResolution(
                ResultMaterializationDecision.CONFLICT,
                candidate.candidate_fingerprint,
                candidate.manifest,
                str(error),
            )
        decision = (
            ResultMaterializationDecision.MATERIALIZE
            if persisted.decision is ResultManifestStateDecision.REGISTERED
            else ResultMaterializationDecision.REPLAY_EXISTING
        )
        return ResultMaterializationResolution(
            decision, candidate.candidate_fingerprint, candidate.manifest
        )

    async def materialize_nautilus_oos(
        self,
        *,
        principal: Any,
        trial: ScientificTrial,
        attempt: RunAttempt,
        strategy_packages: Sequence[StrategyPackage],
        portfolio: PortfolioComposition,
        snapshot: DataSnapshot,
        evidence: EngineResultEvidence,
        equity_reference: NautilusAccountEquityTraceReference,
        equity_trace_path: str | Path,
        equity_expected_events: Iterable[Mapping[str, Any]],
        native_reports_reference: NautilusNativeReportsReference,
        native_reports_path: str | Path,
        output_artifacts: Sequence[ArtifactManifest],
        created_at: datetime,
        existing: RunResultManifest | None = None,
    ) -> ResultMaterializationResolution:
        """Materialize and persist one verified Nautilus OOS result manifest.

        This is the owner-scoped persistence counterpart to the pure OOS
        materializer. It registers only successful candidates, keeps the same
        immutable attempt key as the general result path, and translates a
        manifest already bound to different content into an explicit conflict.
        """

        candidate = materialize_nautilus_oos_run_result(
            trial,
            attempt,
            strategy_packages,
            portfolio,
            snapshot,
            evidence,
            equity_reference,
            equity_trace_path,
            equity_expected_events,
            native_reports_reference,
            native_reports_path,
            output_artifacts,
            created_at=created_at,
            existing=existing,
        )
        if candidate.decision is ResultMaterializationDecision.CONFLICT:
            return candidate.resolution
        if candidate.manifest is None:  # pragma: no cover - pure contract guard
            raise ValueError("Nautilus OOS materialization omitted its result manifest")
        try:
            persisted = await self.ensure(principal=principal, manifest=candidate.manifest)
        except ValueError as error:
            if "already bound" not in str(error):
                raise
            return ResultMaterializationResolution(
                ResultMaterializationDecision.CONFLICT,
                candidate.candidate_fingerprint,
                candidate.manifest,
                str(error),
            )
        decision = (
            ResultMaterializationDecision.MATERIALIZE
            if persisted.decision is ResultManifestStateDecision.REGISTERED
            else ResultMaterializationDecision.REPLAY_EXISTING
        )
        return ResultMaterializationResolution(
            decision,
            candidate.candidate_fingerprint,
            candidate.manifest,
        )

    async def load(self, *, principal: Any, attempt_id: str) -> PersistedResultManifest | None:
        """Read the canonical manifest projection for one owner-scoped attempt."""

        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, attempt_id)

    async def load_all(self, *, principal: Any) -> tuple[PersistedResultManifest, ...]:
        """Read all retained manifest projections in deterministic attempt order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, attempt_id, manifest_fingerprint, trial_id,
                               metric_set_fingerprint, snapshot_fingerprint,
                               manifest_json, record_fingerprint
                        FROM {self._schema.manifest_table}
                        WHERE owner_id = :owner_id
                        ORDER BY attempt_id ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                records = tuple(
                    self._authenticate(_decode_record(row), row, owner_id)
                    for row in result.mappings()
                )
                ordered = tuple(sorted(records, key=lambda item: item.attempt_id))
                if records != ordered:
                    raise ValueError(
                        "PostgreSQL result manifests are not deterministically ordered"
                    )
                return records

    async def load_manifest(self, *, principal: Any, attempt_id: str) -> RunResultManifest | None:
        """Read and fully rehydrate one authenticated result manifest."""

        record = await self.load(principal=principal, attempt_id=attempt_id)
        if record is None:
            return None
        return _decode_authenticated_manifest(record)

    async def load_all_manifests(self, *, principal: Any) -> tuple[RunResultManifest, ...]:
        """Read and fully rehydrate all manifests in deterministic attempt order."""

        records = await self.load_all(principal=principal)
        return tuple(_decode_authenticated_manifest(record) for record in records)

    async def load_artifacts(self, *, principal: Any) -> tuple[PersistedArtifactReference, ...]:
        """Read owner-scoped artifact references from authenticated manifests.

        Artifact metadata is immutable result provenance, so the manifest table
        remains the source of truth. The full typed manifest is rehydrated and
        every artifact is returned from its validated ``output_artifacts`` field.
        """

        records = await self.load_all(principal=principal)
        references: list[PersistedArtifactReference] = []
        for record in records:
            manifest = _decode_authenticated_manifest(record)
            references.extend(
                PersistedArtifactReference(
                    artifact,
                    manifest.fingerprint,
                    manifest.attempt_id,
                    manifest.trial_id,
                )
                for artifact in manifest.output_artifacts
            )
        ordered = tuple(
            sorted(
                references,
                key=lambda item: (
                    item.content_digest,
                    item.manifest_fingerprint,
                    item.attempt_id,
                ),
            )
        )
        return ordered

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> PersistedResultManifest | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, manifest_fingerprint, trial_id,
                       metric_set_fingerprint, snapshot_fingerprint,
                       manifest_json, record_fingerprint
                FROM {self._schema.manifest_table}
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "attempt_id": attempt_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL result manifest query returned duplicate keys")
        return self._authenticate(_decode_record(rows[0]), rows[0], owner_id, attempt_id)

    async def _insert(
        self, session: AsyncSessionLike, owner_id: str, record: PersistedResultManifest
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.manifest_table}
                    (owner_id, attempt_id, manifest_fingerprint, trial_id,
                     metric_set_fingerprint, snapshot_fingerprint, manifest_json,
                     record_fingerprint)
                VALUES (:owner_id, :attempt_id, :manifest_fingerprint, :trial_id,
                        :metric_set_fingerprint, :snapshot_fingerprint, :manifest_json,
                        :record_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "attempt_id": record.attempt_id,
                "manifest_fingerprint": record.manifest_fingerprint,
                "trial_id": record.trial_id,
                "metric_set_fingerprint": record.metric_set_fingerprint,
                "snapshot_fingerprint": record.snapshot_fingerprint,
                "manifest_json": record.manifest_json,
                "record_fingerprint": record.record_fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL result manifest insert lost a uniqueness race")

    @staticmethod
    def _authenticate(
        record: PersistedResultManifest,
        row: Mapping[str, Any],
        owner_id: str,
        attempt_id: str | None = None,
    ) -> PersistedResultManifest:
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL result manifest owner identity drifted")
        if attempt_id is not None and record.attempt_id != attempt_id:
            raise ValueError("PostgreSQL result manifest attempt identity drifted")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("PostgreSQL result manifest fingerprint does not match bytes")
        return record


def _record(manifest: RunResultManifest) -> PersistedResultManifest:
    payload = canonical_json(manifest)
    record = PersistedResultManifest(
        manifest.fingerprint,
        manifest.attempt_id,
        manifest.trial_id,
        manifest.metric_set.fingerprint,
        manifest.snapshot_fingerprint,
        payload,
        content_digest(
            {
                "attempt_id": manifest.attempt_id,
                "manifest_fingerprint": manifest.fingerprint,
                "manifest_json": payload,
                "metric_set_fingerprint": manifest.metric_set.fingerprint,
                "snapshot_fingerprint": manifest.snapshot_fingerprint,
                "trial_id": manifest.trial_id,
            }
        ),
    )
    return record


def _payload_digest(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_authenticated_manifest(record: PersistedResultManifest) -> RunResultManifest:
    try:
        manifest = _decode_result_manifest(record.manifest_json)
    except (TypeError, ValueError) as error:
        raise ValueError("PostgreSQL result manifest payload is malformed") from error
    if manifest.fingerprint != record.manifest_fingerprint:
        raise ValueError("PostgreSQL result manifest payload identity drifted")
    if manifest.attempt_id != record.attempt_id or manifest.trial_id != record.trial_id:
        raise ValueError("PostgreSQL result manifest lineage drifted")
    if manifest.metric_set.fingerprint != record.metric_set_fingerprint:
        raise ValueError("PostgreSQL result manifest metric identity drifted")
    if manifest.snapshot_fingerprint != record.snapshot_fingerprint:
        raise ValueError("PostgreSQL result manifest snapshot identity drifted")
    return manifest


def _decode_result_manifest(payload: str) -> RunResultManifest:
    return decode_canonical_contract(payload, RunResultManifest)


_ContractT = TypeVar("_ContractT")


def decode_canonical_contract(payload: str, expected_type: type[_ContractT]) -> _ContractT:
    """Decode one allowlisted canonical contract and require exact bytes."""

    try:
        root = json.loads(payload)
        decoded = _decode_canonical_value(root)
        if not isinstance(decoded, expected_type):
            raise ValueError(f"canonical payload root is not a {expected_type.__qualname__}")
        if canonical_json(decoded) != payload:
            raise ValueError("canonical payload is not canonical")
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("canonical contract payload is malformed") from error
    return cast(_ContractT, decoded)


def _decode_canonical_value(value: Any) -> Any:
    if not isinstance(value, list) or not value or not isinstance(value[0], str):
        raise ValueError("canonical value must be a tagged list")
    tag = value[0]
    if tag == "null":
        if len(value) != 1:
            raise ValueError("null canonical value is malformed")
        return None
    if tag in {"bool", "str"}:
        if (
            len(value) != 2
            or (tag == "bool" and not isinstance(value[1], bool))
            or (tag == "str" and not isinstance(value[1], str))
        ):
            raise ValueError(f"{tag} canonical value is malformed")
        return value[1]
    if tag == "int":
        return _decode_canonical_int(value)
    if tag == "float":
        if len(value) != 2 or not isinstance(value[1], str):
            raise ValueError("float canonical value is malformed")
        try:
            return float.fromhex(value[1])
        except ValueError as error:
            raise ValueError("float canonical value is invalid") from error
    if tag == "decimal":
        return _decode_canonical_decimal(value)
    if tag == "datetime":
        return _decode_canonical_datetime(value)
    if tag == "date":
        if len(value) != 2 or not isinstance(value[1], str):
            raise ValueError("date canonical value is malformed")
        try:
            return date.fromisoformat(value[1])
        except ValueError as error:
            raise ValueError("date canonical value is invalid") from error
    if tag == "mapping":
        if len(value) != 2 or not isinstance(value[1], list):
            raise ValueError("mapping canonical value is malformed")
        result: dict[str, Any] = {}
        for item in value[1]:
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
                raise ValueError("mapping canonical entry is malformed")
            if item[0] in result:
                raise ValueError("mapping canonical value contains duplicate keys")
            result[item[0]] = _decode_canonical_value(item[1])
        return result
    if tag == "set":
        if len(value) != 2 or not isinstance(value[1], list):
            raise ValueError("set canonical value is malformed")
        try:
            return frozenset(_decode_canonical_value(item) for item in value[1])
        except TypeError as error:
            raise ValueError("set canonical value contains an unhashable item") from error
    if tag in {"tuple", "list"}:
        if len(value) != 2 or not isinstance(value[1], list):
            raise ValueError(f"{tag} canonical value is malformed")
        decoded = tuple(_decode_canonical_value(item) for item in value[1])
        return decoded if tag == "tuple" else list(decoded)
    if tag == "enum":
        if len(value) != 3 or not isinstance(value[1], str):
            raise ValueError("enum canonical value is malformed")
        enum_type = _canonical_enum_registry().get(value[1])
        if enum_type is None:
            raise ValueError("enum canonical value uses an unsupported type")
        return enum_type(_decode_canonical_value(value[2]))
    if tag == "dataclass":
        return _decode_canonical_dataclass(value)
    raise ValueError(f"unsupported canonical tag: {tag}")


def _decode_canonical_int(value: list[Any]) -> int:
    if len(value) != 2 or not isinstance(value[1], str):
        raise ValueError("int canonical value is malformed")
    try:
        parsed = int(value[1], 10)
    except ValueError as error:
        raise ValueError("int canonical value is invalid") from error
    if str(parsed) != value[1]:
        raise ValueError("int canonical value is not normalized")
    return parsed


def _decode_canonical_decimal(value: list[Any]) -> Any:
    from decimal import Decimal

    if len(value) != 2 or not isinstance(value[1], str):
        raise ValueError("decimal canonical value is malformed")
    parts = value[1].split(":")
    if len(parts) != 3 or parts[0] not in {"0", "1"} or not parts[1].isdigit():
        raise ValueError("decimal canonical value is invalid")
    try:
        exponent = int(parts[2], 10)
        digits = tuple(int(item) for item in parts[1])
        return Decimal((int(parts[0]), digits, exponent))
    except (TypeError, ValueError, ArithmeticError) as error:
        raise ValueError("decimal canonical value is invalid") from error


def _decode_canonical_datetime(value: list[Any]) -> datetime:
    if len(value) != 2 or not isinstance(value[1], str):
        raise ValueError("datetime canonical value is malformed")
    try:
        parsed = datetime.fromisoformat(value[1].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("datetime canonical value is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime canonical value must be timezone-aware")
    return parsed.astimezone(UTC)


def _decode_canonical_dataclass(value: list[Any]) -> Any:
    if len(value) != 3 or not isinstance(value[1], str) or not isinstance(value[2], list):
        raise ValueError("dataclass canonical value is malformed")
    dataclass_type = _canonical_dataclass_registry().get(value[1])
    if dataclass_type is None:
        raise ValueError("dataclass canonical value uses an unsupported type")
    decoded_fields: dict[str, Any] = {}
    for item in value[2]:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
            raise ValueError("dataclass canonical field is malformed")
        if item[0] in decoded_fields:
            raise ValueError("dataclass canonical value contains duplicate fields")
        decoded_fields[item[0]] = _decode_canonical_value(item[1])
    dataclass_fields = tuple(
        field for field in fields(dataclass_type) if not field.name.startswith("_")
    )
    expected_fields = {field.name for field in dataclass_fields}
    if set(decoded_fields) != expected_fields:
        raise ValueError("dataclass canonical value fields do not match its schema")
    try:
        constructor_values = {
            field.name: decoded_fields[field.name] for field in dataclass_fields if field.init
        }
        return dataclass_type(**constructor_values)
    except (TypeError, ValueError) as error:
        raise ValueError("dataclass canonical value failed contract validation") from error


def _canonical_dataclass_registry() -> dict[str, type[Any]]:
    registry: dict[str, type[Any]] = {}
    for module in (
        admission,
        capabilities,
        conformance,
        contracts,
        engine_execution,
        execution,
        execution_orchestration,
        forward_context,
        forward_account,
        lifecycle,
        lease_observations,
        nautilus_forward_delivery,
        nautilus_runtime_bundle,
        rebalance,
        runtime,
        runtime_execution,
        dispatch,
        search_dispatch,
        search_state,
        sandbox,
        sdk,
        worker_process,
        workers,
    ):
        for candidate in vars(module).values():
            if isinstance(candidate, type) and is_dataclass(candidate):
                registry[f"{candidate.__module__}.{candidate.__qualname__}"] = candidate
    return registry


def _canonical_enum_registry() -> dict[str, type[Enum]]:
    registry: dict[str, type[Enum]] = {}
    for module in (
        admission,
        capabilities,
        conformance,
        contracts,
        engine_execution,
        execution,
        execution_orchestration,
        lease_observations,
        lifecycle,
        rebalance,
        runtime,
        runtime_execution,
        dispatch,
        search_dispatch,
        search_state,
        sandbox,
        sdk,
        worker_process,
        workers,
    ):
        for candidate in vars(module).values():
            if isinstance(candidate, type) and issubclass(candidate, Enum):
                registry[f"{candidate.__module__}.{candidate.__qualname__}"] = candidate
    return registry


def _decode_record(row: Mapping[str, Any]) -> PersistedResultManifest:
    try:
        return PersistedResultManifest(
            row["manifest_fingerprint"],
            row["attempt_id"],
            row["trial_id"],
            row["metric_set_fingerprint"],
            row["snapshot_fingerprint"],
            row["manifest_json"],
            row["record_fingerprint"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL result manifest row is malformed") from error


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _validate_attempt(attempt_id: str) -> None:
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError("attempt_id must not be empty")


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "decode_canonical_contract",
    "PersistedArtifactReference",
    "PersistedResultManifest",
    "PostgresResultMaterializationAdapter",
    "PostgresResultMaterializationSchema",
    "ResultManifestStateDecision",
    "ResultManifestStateResolution",
]
