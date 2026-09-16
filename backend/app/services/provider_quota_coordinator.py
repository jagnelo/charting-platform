"""Independently committed, account-scoped provider quota reservations.

The application database remains useful for product-level usage reporting, but
it cannot coordinate isolated worktrees or direct live probes and its caller's
transaction can roll back after a provider has accepted a request. This ledger
commits a conservative reservation before transport. Local use is a private
SQLite file shared by the host and worktree containers; trusted multi-host
environments may configure a dedicated PostgreSQL URL.

No provider defaults are declared here. Every limit, reset, operation cost,
quota group and applicable dimension must come from the same reviewed provider
contract used by the router. An ambiguous request keeps its reservation until
the provider-defined bucket resets or an operator reconciles native usage.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)
_QUOTA_EVIDENCE_REFERENCE = re.compile(
    r"(?i)^(?:dashboard|account-usage|provider-doc|support-ticket|workflow-run|test-fixture|operator-note):"
    r"[a-z][a-z0-9]{0,19}(?:-[a-z][a-z0-9]{0,19}){0,4}:"
    r"(?:\d{4}-\d{2}-\d{2}|[a-z][a-z0-9]{0,19}(?:-[a-z0-9]{1,20}){1,4})$"
)


class ProviderQuotaCoordinatorError(RuntimeError):
    """The durable quota coordinator is unavailable or incorrectly configured."""


class ProviderQuotaAdmissionError(ProviderQuotaCoordinatorError):
    """A provider operation lacks a complete reviewed cost/limit contract."""


@dataclass(frozen=True)
class QuotaReservation:
    reservation_id: str
    provider_name: str
    account_scope: str


_LIVE_RECEIPT_STATUSES = frozenset(
    {"observed", "provider_error", "expected_entitlement_denial"}
)
_LIVE_RECEIPT_RECONCILIATION_STATES = frozenset(
    {"reconciled", "pending", "uncertain"}
)


def _validated_live_receipt_field(
    value: object, *, name: str, maximum: int, allow_empty: bool = False
) -> str:
    candidate = str(value or "").strip()
    if not candidate and allow_empty:
        return ""
    if (
        not candidate
        or len(candidate) > maximum
        or not candidate.isprintable()
        or any(marker in candidate.lower() for marker in ("api_key", "secret", "token", "password"))
    ):
        raise ProviderQuotaCoordinatorError(f"live receipt {name} is invalid")
    return candidate


metadata = MetaData()

_scope_locks = Table(
    "provider_quota_ledger_scope_lock",
    metadata,
    Column("provider_name", String(100), primary_key=True),
    Column("account_scope", String(128), primary_key=True),
)

_windows = Table(
    "provider_quota_ledger_window",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider_name", String(100), nullable=False),
    Column("account_scope", String(128), nullable=False),
    Column("quota_group", String(128), nullable=False),
    Column("dimension", String(128), nullable=False),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("window_seconds", Integer, nullable=False),
    Column("limit_units", Integer, nullable=False),
    Column("reserved_units", Integer, nullable=False, default=0),
    Column("consumed_units", Integer, nullable=False, default=0),
    UniqueConstraint(
        "provider_name",
        "account_scope",
        "quota_group",
        "dimension",
        "window_started_at",
        "window_seconds",
        name="uq_provider_quota_ledger_window",
    ),
)

# A quota window is not usable merely because this process has observed no
# requests in it. Existing provider accounts may have been used before this
# coordinator was installed or by another client. A verified provider snapshot
# or explicit operator attestation establishes the starting point; reservations
# after that observation are tracked separately and added exactly once.
_baselines = Table(
    "provider_quota_ledger_baseline",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_scope", String(128), nullable=False),
    Column("quota_group", String(128), nullable=False),
    Column("dimension", String(128), nullable=False),
    Column("unit", String(32), nullable=False),
    Column("reset", String(64), nullable=False),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("window_seconds", Integer, nullable=False),
    Column("rolling", Boolean, nullable=False),
    Column("limit_units", Integer, nullable=False),
    Column("used_units", Integer, nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("source", String(48), nullable=False),
    Column("evidence_reference", String(256), nullable=False),
    Column("source_provider_name", String(100), nullable=False),
    Column("actor_user_id", Integer, nullable=True),
    Column("idempotency_key", String(64), nullable=False, unique=True),
)

_reservations = Table(
    "provider_quota_ledger_reservation",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reservation_id", String(36), nullable=False),
    Column("provider_name", String(100), nullable=False),
    Column("account_scope", String(128), nullable=False),
    Column("operation", String(160), nullable=False),
    Column("quota_group", String(128), nullable=False),
    Column("dimension", String(128), nullable=False),
    Column("unit", String(32), nullable=False),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("window_seconds", Integer, nullable=False),
    Column("reserved_units", Integer, nullable=False),
    Column("release_only", Boolean, nullable=False, default=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("identity_digest", String(64), nullable=True),
    Column("state", String(24), nullable=False, default="pending"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("settled_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint(
        "reservation_id", "dimension", name="uq_provider_quota_ledger_reservation_dim"
    ),
)

_identities = Table(
    "provider_quota_ledger_identity",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider_name", String(100), nullable=False),
    Column("account_scope", String(128), nullable=False),
    Column("quota_group", String(128), nullable=False),
    Column("dimension", String(128), nullable=False),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("window_seconds", Integer, nullable=False),
    Column("identity_digest", String(64), nullable=False),
    Column("owner_reservation_id", String(36), nullable=True),
    Column("state", String(24), nullable=False, default="consumed"),
    UniqueConstraint(
        "provider_name",
        "account_scope",
        "quota_group",
        "dimension",
        "window_started_at",
        "window_seconds",
        "identity_digest",
        name="uq_provider_quota_ledger_identity",
    ),
)

_maintenance = Table(
    "provider_quota_ledger_maintenance",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("last_run_at", DateTime(timezone=True), nullable=False),
)

# Aggregate JSONL receipts are useful audit artifacts, but they are not an
# authority for quota accounting.  This small registry links a redacted live
# observation to the reservation that was already admitted in this same
# durable database.  It deliberately stores no provider response data,
# request counts, byte counts, credentials, or inferred quota units.
_live_receipts = Table(
    "provider_quota_ledger_live_receipt",
    metadata,
    Column("reservation_id", String(36), primary_key=True),
    Column("provider_name", String(100), nullable=False),
    Column("operation", String(160), nullable=False),
    Column("run_id", String(128), nullable=False),
    Column("usage_scope", String(128), nullable=False),
    Column("receipt_status", String(32), nullable=False),
    Column("reconciliation_state", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("reconciled_at", DateTime(timezone=True), nullable=True),
    Column("error", String(256), nullable=True),
)

_ACCOUNT_SCOPE_BUCKET = "__account_scope__"
_HEALTH_PROBE_KEY = "health-probe-v1"


def _engine_url() -> str:
    configured_url = str(
        getattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "") or ""
    ).strip()
    if configured_url:
        return configured_url
    configured_path = str(
        getattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", "")
        or "~/.config/charting-platform/provider-quota/usage.sqlite3"
    )
    path = Path(configured_path).expanduser()
    return "sqlite:///" + str(path.resolve())


def _validate_engine_url(url: str, *, require_persistent: bool = False) -> None:
    """Validate supported SQL semantics and the GitHub live-run persistence gate."""

    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        scheme = ""
    if scheme not in {"sqlite", "postgresql", "postgresql+psycopg2"}:
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator supports only SQLite or PostgreSQL"
        )
    if (
        require_persistent
        and os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"
        and scheme not in {"postgresql", "postgresql+psycopg2"}
    ):
        raise ProviderQuotaCoordinatorError(
            "GitHub live probes require a persistent PostgreSQL quota coordinator"
        )


@lru_cache(maxsize=4)
def _engine_for(url: str, require_persistent: bool = False) -> Engine:
    _validate_engine_url(url, require_persistent=require_persistent)
    if url.startswith("sqlite:"):
        engine = create_engine(
            url,
            connect_args={"timeout": 30, "check_same_thread": False},
            poolclass=NullPool,
        )
    else:
        # Keep URLs and driver exceptions out of diagnostics: credentialed
        # coordinator URLs may contain passwords.
        engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    if engine.dialect.name not in {"sqlite", "postgresql"}:
        engine.dispose()
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator supports only SQLite or PostgreSQL"
        )
    _secure_sqlite_location(engine, url)
    if engine.dialect.name == "sqlite":
        # Serialize first-use schema creation between API/worker processes and
        # isolated worktrees. `create_all()` alone is not safe when two
        # processes observe an empty ledger at the same time.
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA busy_timeout=30000")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                metadata.create_all(connection)
                _upgrade_identity_schema(engine, connection=connection)
                _upgrade_baseline_schema(engine, connection=connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    else:
        metadata.create_all(engine)
        _upgrade_identity_schema(engine)
        _upgrade_baseline_schema(engine)
    if engine.dialect.name == "sqlite" and engine.url.database != ":memory:":
        try:
            database = Path(engine.url.database or "").expanduser()
            if stat.S_IMODE(database.stat().st_mode) != 0o600:
                os.chmod(database, 0o600)
        except OSError:
            raise ProviderQuotaCoordinatorError(
                "provider quota ledger file permissions could not be secured"
            ) from None
    return engine


def _upgrade_identity_schema(engine: Engine, *, connection=None) -> None:
    """Add claim ownership to pre-existing private coordinator ledgers."""

    if engine.dialect.name == "sqlite":
        def upgrade_sqlite(connection) -> None:
            columns = {
                str(row[1])
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(provider_quota_ledger_identity)"
                )
            }
            if "owner_reservation_id" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE provider_quota_ledger_identity "
                    "ADD COLUMN owner_reservation_id VARCHAR(36)"
                )
            if "state" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE provider_quota_ledger_identity "
                    "ADD COLUMN state VARCHAR(24) NOT NULL DEFAULT 'consumed'"
                )
        if connection is not None:
            upgrade_sqlite(connection)
        else:
            with engine.begin() as upgrade_connection:
                upgrade_sqlite(upgrade_connection)
    elif engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE provider_quota_ledger_identity "
                "ADD COLUMN IF NOT EXISTS owner_reservation_id VARCHAR(36)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE provider_quota_ledger_identity "
                "ADD COLUMN IF NOT EXISTS state VARCHAR(24) NOT NULL DEFAULT 'consumed'"
            )


def _upgrade_baseline_schema(engine: Engine, *, connection=None) -> None:
    """Add resolved provider reset semantics to existing private ledgers."""

    if engine.dialect.name == "sqlite":
        def upgrade_sqlite(connection) -> None:
            columns = {
                str(row[1])
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(provider_quota_ledger_baseline)"
                )
            }
            if "reset" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE provider_quota_ledger_baseline "
                    "ADD COLUMN reset VARCHAR(64) NOT NULL DEFAULT 'unknown'"
                )

        if connection is not None:
            upgrade_sqlite(connection)
        else:
            with engine.begin() as upgrade_connection:
                upgrade_sqlite(upgrade_connection)
    elif engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE provider_quota_ledger_baseline "
                "ADD COLUMN IF NOT EXISTS reset VARCHAR(64) NOT NULL DEFAULT 'unknown'"
            )


def _secure_sqlite_location(engine: Engine, url: str) -> None:
    if engine.dialect.name != "sqlite" or url.endswith(":memory:"):
        return
    database = Path(engine.url.database or "").expanduser()
    if not database.is_absolute():
        database = database.resolve()
    parent = database.parent
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise ProviderQuotaCoordinatorError(
                "provider quota ledger directory must be a private owner-only directory"
            )
        if not database.exists():
            # Create the SQLite file with its final private mode before the
            # engine can open it.  This avoids a window where a newly-created
            # ledger inherits a permissive umask and also means a sandbox or
            # filesystem that rejects a redundant chmod does not make an
            # already-private ledger unusable.
            try:
                descriptor = os.open(
                    database,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
        if database.is_symlink() or not stat.S_ISREG(database.stat().st_mode):
            raise ProviderQuotaCoordinatorError(
                "provider quota ledger path must be a regular non-symlink file"
            )
        # Do not perform a needless metadata mutation.  Apart from avoiding
        # noise, this permits owner-only files on restricted filesystems where
        # the owner can use the file but chmod is denied by the sandbox.
        if stat.S_IMODE(database.stat().st_mode) != 0o600:
            os.chmod(database, 0o600)
    except ProviderQuotaCoordinatorError:
        raise
    except OSError:
        raise ProviderQuotaCoordinatorError(
            "provider quota ledger path is unavailable"
        ) from None


@contextmanager
def _write_transaction(engine: Engine):
    connection = engine.connect()
    try:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA busy_timeout=30000")
            connection.exec_driver_sql("PRAGMA synchronous=FULL")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
            if engine.dialect.name == "postgresql":
                connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def account_scope_for_provider(provider_name: str, quota_scope: str | None = None) -> str:
    """Return a non-secret, operator-controlled identity for this provider key."""

    raw_scopes = getattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", {}) or {}
    if not isinstance(raw_scopes, dict):
        raise ProviderQuotaCoordinatorError(
            "provider quota account scopes must be a JSON object"
        )
    scope_kind = str(quota_scope or "").strip().lower()
    keyed_scope = f"{provider_name}:{scope_kind}" if scope_kind else ""
    if scope_kind in {"ip", "ip_or_pair", "public_api"}:
        default_scope = f"{provider_name}:shared-{scope_kind}"
        if provider_name in {"finra", "finra_otc_directory"} and scope_kind == "ip":
            # Both adapters call the same FINRA API platform from the same
            # public egress IP; its published 1,200/min ceiling is not per
            # adapter or dataset.
            default_scope = "finra:shared-ip"
        if provider_name in {"kraken", "kraken_xstocks"} and scope_kind == "ip":
            # Both adapters use Kraken's public Spot REST API from the same
            # deployment egress address.
            default_scope = "kraken:shared-ip"
    else:
        default_scope = provider_name
    if scope_kind in {"ip", "ip_or_pair", "public_api"}:
        value = raw_scopes.get(keyed_scope, default_scope)
    else:
        value = raw_scopes.get(keyed_scope, raw_scopes.get(provider_name, default_scope))
    scope = str(value or "").strip()
    if (
        not scope
        or len(scope) > 128
        or not scope.isprintable()
        or "://" in scope
        or re.search(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]", scope)
    ):
        raise ProviderQuotaCoordinatorError(
            f"provider quota account scope is missing or invalid for {provider_name}"
        )
    return scope


def account_scope_is_exclusive(account_scope: str) -> bool:
    """Return whether the owner explicitly guarantees coordinator-only use."""

    configured = getattr(settings, "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES", {}) or {}
    if not isinstance(configured, dict):
        raise ProviderQuotaCoordinatorError(
            "exclusive provider quota account scopes must be a JSON object"
        )
    value = configured.get(account_scope, False)
    if not isinstance(value, bool):
        raise ProviderQuotaCoordinatorError(
            "exclusive provider quota account scope values must be booleans"
        )
    return value


def normalize_quota_evidence_reference(value: str) -> str:
    """Accept a structured evidence locator, never arbitrary free text."""

    candidate = str(value).strip()
    if (
        not candidate
        or len(candidate) > 128
        or not _QUOTA_EVIDENCE_REFERENCE.fullmatch(candidate)
        or re.search(
            r"(?i)(?:^|[-:])(?:api[-_]?key|secret|token|password|credential)(?:$|[-:])",
            candidate,
        )
    ):
        raise ValueError(
            "evidence_reference must use a non-secret source:provider:date-or-description locator"
        )
    return candidate


def _safe_stored_evidence_reference(value: str | None) -> str | None:
    """Hide legacy evidence text that predates the strict locator contract."""

    if value is None:
        return None
    try:
        return normalize_quota_evidence_reference(value)
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    # SQLAlchemy returns naive values for timezone-aware DateTime columns on
    # SQLite, but those values were stored as UTC by this module. Do not
    # reinterpret them as the host's local timezone when normalizing twice.
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _window_start(
    dimension: dict[str, Any], *, reset: str, now: datetime
) -> tuple[datetime, bool]:
    """Mirror the runtime's provider-defined fixed/calendar/rolling resets."""

    from app.services.provider_routing import _window_start_for_dimension

    start, rolling = _window_start_for_dimension(dimension, reset=reset, now=now)
    seconds = int(dimension["window_seconds"])
    if start is not None:
        return _utc(start), False
    if rolling:
        start = datetime.fromtimestamp(int(now.timestamp()), tz=UTC)
        return _utc(start), True
    epoch = int(now.timestamp())
    start = datetime.fromtimestamp(epoch - epoch % seconds, tz=UTC)
    return _utc(start), False


def _dimension_specs(
    *,
    provider_name: str,
    capability: str,
    policy: Any,
    operation: str,
    dimension_units: dict[str, int],
    usage_identity: str | None,
    now: datetime,
) -> list[dict[str, Any]]:
    from app.services.provider_routing import quota_group_for_dimension
    from app.services.provider_runtime import quota_dimensions

    contract = dict(getattr(policy, "quota_contract", None) or {})
    dimensions = quota_dimensions(policy)
    if not dimensions:
        raise ProviderQuotaAdmissionError(
            f"provider quota contract is incomplete for {provider_name}/{operation}"
        )
    reset = str(contract.get("reset") or "")
    result: list[dict[str, Any]] = []
    for raw_dimension in dimensions:
        dimension = dict(raw_dimension)
        name = str(dimension["name"])
        applies_to = dimension.get("applies_to_operations")
        if applies_to is not None:
            if not isinstance(applies_to, list) or not applies_to:
                continue
            family = operation.split(":", 1)[0].strip() or operation
            if operation not in {str(item) for item in applies_to} and family not in {
                str(item) for item in applies_to
            }:
                continue
        units = dimension_units.get(name)
        if isinstance(units, bool) or not isinstance(units, int) or units < 0:
            raise ProviderQuotaAdmissionError(
                f"provider operation cost is missing for {provider_name}/{operation}/{name}"
            )
        if units == 0:
            continue
        unit = str(dimension.get("unit") or "").strip().lower()
        distinct = unit in {"symbol", "symbols", "unique_symbol", "unique_symbols"}
        release_only = unit in {"concurrent_requests", "concurrency"}
        if distinct and not usage_identity:
            raise ProviderQuotaAdmissionError(
                f"provider operation identity is missing for {provider_name}/{operation}/{name}"
            )
        window_start, rolling = _window_start(dimension, reset=reset, now=now)
        dimension_reset = str(dimension.get("reset") or reset).strip()
        lease_expires_at = None
        if release_only:
            if provider_name == "ibkr":
                timeout = float(getattr(settings, "IBKR_READ_ONLY_TIMEOUT_SECONDS", 30.0))
            else:
                # The REST base class uses a 30 second transport timeout. This
                # is a lease-recovery horizon, not a provider quota/default.
                timeout = 30.0
            grace = int(
                getattr(settings, "PROVIDER_QUOTA_CONCURRENCY_LEASE_GRACE_SECONDS", 10)
            )
            if timeout <= 0 or grace < 0:
                raise ProviderQuotaAdmissionError(
                    f"provider concurrency lease is invalid for {provider_name}"
                )
            lease_expires_at = _utc(now + timedelta(seconds=timeout + grace))
        result.append(
            {
                "provider_name": provider_name,
                "account_scope": account_scope_for_provider(
                    provider_name, str(dimension.get("scope") or policy.quota_scope or "")
                ),
                "operation": operation,
                "quota_group": quota_group_for_dimension(capability, dimension),
                "dimension": name,
                "unit": unit,
                "window_started_at": window_start,
                "window_seconds": int(dimension["window_seconds"]),
                "reset": dimension_reset,
                "rolling": rolling,
                "limit_units": int(dimension["limit"]),
                "units": 1 if release_only else units,
                "release_only": release_only,
                "lease_expires_at": lease_expires_at,
                "identity_digest": hashlib.sha256(
                    str(usage_identity or "").strip().upper().encode("utf-8")
                ).hexdigest()
                if distinct
                else None,
            }
        )
    if not result:
        raise ProviderQuotaAdmissionError(
            f"provider operation has no reservable quota dimensions for {provider_name}/{operation}"
        )
    return result


def _insert_ignore(connection, table: Table, values: dict[str, Any], conflict_columns: list[str]):
    dialect = connection.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

        statement = dialect_insert(table).values(**values).on_conflict_do_nothing(
            index_elements=conflict_columns
        )
        return connection.execute(statement)
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

        statement = dialect_insert(table).values(**values).on_conflict_do_nothing(
            index_elements=conflict_columns
        )
        return connection.execute(statement)
    return connection.execute(insert(table).values(**values))


def _window_values(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _ACCOUNT_SCOPE_BUCKET if key == "provider_name" else spec[key]
        for key in (
            "provider_name",
            "account_scope",
            "quota_group",
            "dimension",
            "window_started_at",
            "window_seconds",
        )
    }


def _find_window(
    connection, spec: dict[str, Any], *, lock: bool = True, required: bool = True
):
    query = select(_windows).where(
        *[
            getattr(_windows.c, key) == value
            for key, value in _window_values(spec).items()
        ]
    )
    if lock and connection.dialect.name == "postgresql":
        query = query.with_for_update()
    result = connection.execute(query).mappings()
    return result.one() if required else result.first()


def _baseline_query(spec: dict[str, Any], *, lock: bool = True):
    predicates = [
        _baselines.c.account_scope == spec["account_scope"],
        _baselines.c.quota_group == spec["quota_group"],
        _baselines.c.dimension == spec["dimension"],
        _baselines.c.window_seconds == int(spec["window_seconds"]),
        _baselines.c.unit == spec["unit"],
        _baselines.c.reset == spec["reset"],
    ]
    if spec["rolling"]:
        predicates.extend(
            [
                _baselines.c.rolling.is_(True),
                _baselines.c.observed_at <= _utc(spec["now"]),
                _baselines.c.observed_at
                >= _utc(spec["now"] - timedelta(seconds=int(spec["window_seconds"]))),
            ]
        )
    else:
        predicates.extend(
            [
                _baselines.c.rolling.is_(False),
                _baselines.c.window_started_at == spec["window_started_at"],
            ]
        )
    query = select(_baselines).where(*predicates).order_by(
        _baselines.c.observed_at.desc(), _baselines.c.id.desc()
    )
    if lock:
        query = query.with_for_update()
    return query


def _baseline_for_reservation(connection, spec: dict[str, Any], now: datetime):
    """Find an exact active baseline, or safely roll a prior one forward.

    A missing first baseline always blocks. After an operator has established
    one, an explicitly exclusive account scope can use zero at a documented
    fixed reset boundary, or after a complete rolling window has elapsed.
    """

    lookup = {**spec, "now": now}
    baseline = connection.execute(_baseline_query(lookup)).mappings().first()
    if baseline is not None:
        return baseline

    prior_query = select(_baselines).where(
        _baselines.c.account_scope == spec["account_scope"],
        _baselines.c.quota_group == spec["quota_group"],
        _baselines.c.dimension == spec["dimension"],
        _baselines.c.window_seconds == int(spec["window_seconds"]),
        _baselines.c.unit == spec["unit"],
        _baselines.c.reset == spec["reset"],
    )
    if spec["rolling"]:
        prior_query = prior_query.where(_baselines.c.rolling.is_(True)).order_by(
            _baselines.c.observed_at.desc(), _baselines.c.id.desc()
        )
    else:
        prior_query = prior_query.where(
            _baselines.c.rolling.is_(False),
            _baselines.c.window_started_at < spec["window_started_at"],
        ).order_by(_baselines.c.window_started_at.desc(), _baselines.c.id.desc())
    prior = connection.execute(prior_query).mappings().first()
    if prior is None or not account_scope_is_exclusive(spec["account_scope"]):
        return None

    if spec["rolling"]:
        if _utc(prior["observed_at"] + timedelta(seconds=int(spec["window_seconds"]))) > _utc(now):
            return None
        rollover_at = _utc(now - timedelta(seconds=int(spec["window_seconds"])))
    else:
        rollover_at = spec["window_started_at"]

    # Record the reset/expiry-derived zero as an auditable baseline rather than
    # relying on an implicit default in a newly created quota window.
    zero = {
        "account_scope": spec["account_scope"],
        "quota_group": spec["quota_group"],
        "dimension": spec["dimension"],
        "unit": spec["unit"],
        "reset": spec["reset"],
        "window_started_at": _utc(rollover_at),
        "window_seconds": int(spec["window_seconds"]),
        "rolling": bool(spec["rolling"]),
        "limit_units": int(spec["limit_units"]),
        "used_units": 0,
        "observed_at": _utc(rollover_at),
        "source": "exclusive_account_reset",
        "evidence_reference": "verified prior baseline; exclusive coordinator scope",
        "source_provider_name": str(spec["provider_name"]),
        "actor_user_id": None,
        "idempotency_key": hashlib.sha256(
            "|".join(
                [
                    spec["account_scope"],
                    spec["quota_group"],
                    spec["dimension"],
                    str(spec["window_seconds"]),
                    spec["reset"],
                    str(rollover_at),
                    "exclusive-reset",
                ]
            ).encode("utf-8")
        ).hexdigest(),
    }
    _insert_ignore(
        connection,
        _baselines,
        zero,
        ["idempotency_key"],
    )
    return connection.execute(_baseline_query(lookup)).mappings().first()


def _settled_units_since_baseline(connection, spec: dict[str, Any], baseline) -> int:
    """Count only completed local debits after the absolute account snapshot."""

    predicates = [
        _reservations.c.account_scope == spec["account_scope"],
        _reservations.c.quota_group == spec["quota_group"],
        _reservations.c.dimension == spec["dimension"],
        _reservations.c.state == "settled",
        _reservations.c.created_at >= baseline["observed_at"],
    ]
    if spec["rolling"]:
        predicates.append(
            _reservations.c.created_at
            >= _utc(spec["now"] - timedelta(seconds=int(spec["window_seconds"])) )
        )
    else:
        predicates.append(
            _reservations.c.window_started_at == spec["window_started_at"]
        )
    return int(
        connection.execute(
            select(func.coalesce(func.sum(_reservations.c.reserved_units), 0)).where(
                *predicates
            )
        ).scalar_one()
    )


def _active_reserved_units(connection, spec: dict[str, Any], now: datetime) -> int:
    predicates = [
        _windows.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
        _windows.c.account_scope == spec["account_scope"],
        _windows.c.quota_group == spec["quota_group"],
        _windows.c.dimension == spec["dimension"],
        _windows.c.window_seconds == int(spec["window_seconds"]),
    ]
    if spec["rolling"]:
        predicates.append(
            _windows.c.window_started_at
            >= _utc(now - timedelta(seconds=int(spec["window_seconds"])))
        )
    else:
        predicates.append(_windows.c.window_started_at == spec["window_started_at"])
    return int(
        connection.execute(
            select(func.coalesce(func.sum(_windows.c.reserved_units), 0)).where(
                *predicates
            )
        ).scalar_one()
    )


def _baseline_local_accounting(engine: Engine, spec: dict[str, Any], baseline, now: datetime):
    with engine.connect() as connection:
        settled = _settled_units_since_baseline(connection, spec, baseline)
        reserved = _active_reserved_units(connection, spec, now)
    return settled, reserved


def reconcile_provider_quota_baseline(
    *,
    provider_name: str,
    capability: str,
    policy: Any,
    dimension_name: str,
    used_units: int,
    observed_at: datetime,
    evidence_reference: str,
    source: str = "operator_dashboard_attestation",
    actor_user_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Seed/reconcile one exact provider/account/reset-window usage baseline.

    The caller supplies the observed used-unit count and non-secret evidence
    reference. Dimension, unit, limit, quota group, account scope, reset, and
    active window all come from the reviewed provider contract.
    """

    current = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ProviderQuotaAdmissionError("quota baseline observed_at must include a timezone")
    if observed_at > current:
        raise ProviderQuotaAdmissionError("quota baseline cannot be from the future")
    if isinstance(used_units, bool) or not isinstance(used_units, int) or used_units < 0:
        raise ProviderQuotaAdmissionError("quota baseline used_units must be non-negative")
    try:
        evidence = normalize_quota_evidence_reference(evidence_reference)
    except (TypeError, ValueError):
        raise ProviderQuotaAdmissionError("quota baseline evidence reference is invalid") from None
    if source not in {"operator_dashboard_attestation", "provider_account_observation"}:
        raise ProviderQuotaAdmissionError("quota baseline source is not supported")

    contract = dict(getattr(policy, "quota_contract", None) or {})
    dimensions = [
        dict(item)
        for item in (contract.get("dimensions") or [])
        if isinstance(item, dict) and str(item.get("name") or "") == dimension_name
    ]
    if len(dimensions) != 1 or contract.get("unknown_dimensions"):
        raise ProviderQuotaAdmissionError("quota baseline dimension is not uniquely reviewed")
    dimension = dimensions[0]
    unit = str(dimension.get("unit") or "").strip().lower()
    if unit in {"concurrent_requests", "concurrency"}:
        raise ProviderQuotaAdmissionError("concurrency leases do not require a usage baseline")
    if not unit or not isinstance(dimension.get("limit"), int) or not isinstance(
        dimension.get("window_seconds"), int
    ):
        raise ProviderQuotaAdmissionError("quota baseline dimension contract is incomplete")
    from app.services.provider_routing import quota_group_for_dimension

    observed_start, rolling = _window_start(
        dimension, reset=str(contract.get("reset") or ""), now=observed_at
    )
    current_start, current_rolling = _window_start(
        dimension, reset=str(contract.get("reset") or ""), now=current
    )
    if rolling != current_rolling:
        raise ProviderQuotaAdmissionError("quota baseline reset semantics changed")
    if rolling:
        if current - observed_at > timedelta(seconds=int(dimension["window_seconds"])):
            raise ProviderQuotaAdmissionError("rolling quota baseline is older than its active window")
    elif observed_start != current_start:
        raise ProviderQuotaAdmissionError("quota baseline is not for the current provider reset window")

    scope_kind = str(dimension.get("scope") or getattr(policy, "quota_scope", ""))
    account_scope = account_scope_for_provider(provider_name, scope_kind)
    quota_group = quota_group_for_dimension(capability, dimension)
    observed_utc = _utc(observed_at)
    window_start = observed_utc if rolling else observed_start
    idem = hashlib.sha256(
        "|".join(
            [
                account_scope,
                quota_group,
                dimension_name,
                str(dimension["window_seconds"]),
                str(dimension.get("reset") or contract.get("reset") or "").strip(),
                str(window_start),
                str(observed_utc),
                str(used_units),
                evidence,
                source,
            ]
        ).encode("utf-8")
    ).hexdigest()
    spec = {
        "provider_name": provider_name,
        "account_scope": account_scope,
        "quota_group": quota_group,
        "dimension": dimension_name,
        "unit": unit,
        "reset": str(dimension.get("reset") or contract.get("reset") or "").strip(),
        "window_started_at": _utc(window_start),
        "window_seconds": int(dimension["window_seconds"]),
        "rolling": rolling,
        "limit_units": int(dimension["limit"]),
    }
    try:
        engine = _engine_for(_engine_url())
        with _write_transaction(engine) as connection:
            _insert_ignore(
                connection,
                _scope_locks,
                {"provider_name": _ACCOUNT_SCOPE_BUCKET, "account_scope": account_scope},
                ["provider_name", "account_scope"],
            )
            lock_query = select(_scope_locks).where(
                _scope_locks.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
                _scope_locks.c.account_scope == account_scope,
            )
            if connection.dialect.name == "postgresql":
                lock_query = lock_query.with_for_update()
            connection.execute(lock_query).first()
            pending_filters = [
                    _reservations.c.account_scope == account_scope,
                    _reservations.c.quota_group == quota_group,
                    _reservations.c.dimension == dimension_name,
                    _reservations.c.state.in_(["pending", "uncertain"]),
            ]
            if rolling:
                pending_filters.append(
                    _reservations.c.created_at
                    >= _utc(current - timedelta(seconds=int(dimension["window_seconds"])))
                )
            else:
                pending_filters.append(
                    _reservations.c.window_started_at == spec["window_started_at"]
                )
            pending = connection.execute(
                select(func.count()).select_from(_reservations).where(*pending_filters)
            ).scalar_one()
            if pending:
                raise ProviderQuotaAdmissionError(
                    "cannot reconcile quota baseline while provider reservations are pending or uncertain"
                )
            lookup = {**spec, "now": current}
            previous = connection.execute(_baseline_query(lookup)).mappings().first()
            if previous is not None and observed_utc < _utc(previous["observed_at"]):
                raise ProviderQuotaAdmissionError(
                    "quota baseline observation is older than the currently reconciled snapshot"
                )
            stored_used_units = int(used_units)
            if previous is not None:
                if rolling and observed_utc == _utc(previous["observed_at"]):
                    # Replaying an equal-time snapshot cannot make usage go
                    # backwards. A strictly newer rolling snapshot is an
                    # authoritative provider view of the moving window and
                    # may legitimately be lower as old calls age out.
                    stored_used_units = max(
                        stored_used_units, int(previous["used_units"])
                    )
                elif not rolling:
                    prior_local_debits = _settled_units_since_baseline(
                        connection,
                        {**spec, "rolling": False, "now": current},
                        previous,
                    )
                    # A fixed-window snapshot may lag coordinator-confirmed
                    # debits, so never erase settled usage in that bucket.
                    stored_used_units = max(
                        stored_used_units,
                        int(previous["used_units"]) + prior_local_debits,
                    )
            _insert_ignore(
                connection,
                _baselines,
                {
                    **{key: value for key, value in spec.items() if key != "provider_name"},
                    "used_units": stored_used_units,
                    "observed_at": observed_utc,
                    "source": source,
                    "evidence_reference": evidence,
                    "source_provider_name": provider_name,
                    "actor_user_id": actor_user_id,
                    "idempotency_key": idem,
                },
                ["idempotency_key"],
            )
            latest = connection.execute(_baseline_query(lookup)).mappings().first()
            if latest is None:
                raise ProviderQuotaCoordinatorError("quota baseline write was not visible")
            effective_used = int(latest["used_units"])
            return {
                "provider": provider_name,
                "account_scope": account_scope,
                "quota_group": quota_group,
                "dimension": dimension_name,
                "unit": unit,
                "limit_units": int(dimension["limit"]),
                "used_units": effective_used,
                "window_started_at": latest["window_started_at"].replace(tzinfo=UTC).isoformat(),
                "window_seconds": int(latest["window_seconds"]),
                "rolling": bool(latest["rolling"]),
                "observed_at": latest["observed_at"].replace(tzinfo=UTC).isoformat(),
                "source": latest["source"],
                "evidence_reference": _safe_stored_evidence_reference(
                    latest["evidence_reference"]
                ),
                "actor_user_id": latest["actor_user_id"],
            }
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota baseline reconciliation failed"
        ) from None


def provider_quota_baseline_status(
    *,
    provider_name: str,
    capability: str,
    policy: Any,
    dimension_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read the active baseline without creating or rolling any ledger state."""

    current = now or datetime.now(UTC)
    contract = dict(getattr(policy, "quota_contract", None) or {})
    dimensions = [
        dict(item)
        for item in (contract.get("dimensions") or [])
        if isinstance(item, dict) and str(item.get("name") or "") == dimension_name
    ]
    if len(dimensions) != 1:
        raise ProviderQuotaAdmissionError("quota baseline dimension is not uniquely reviewed")
    dimension = dimensions[0]
    unit = str(dimension.get("unit") or "").strip().lower()
    if unit in {"concurrent_requests", "concurrency"}:
        return {"required": False, "status": "not_applicable", "baseline": None}
    from app.services.provider_routing import quota_group_for_dimension

    start, rolling = _window_start(
        dimension, reset=str(contract.get("reset") or ""), now=current
    )
    spec = {
        "provider_name": provider_name,
        "account_scope": account_scope_for_provider(
            provider_name, str(dimension.get("scope") or getattr(policy, "quota_scope", ""))
        ),
        "quota_group": quota_group_for_dimension(capability, dimension),
        "dimension": dimension_name,
        "unit": unit,
        "reset": str(dimension.get("reset") or contract.get("reset") or "").strip(),
        "window_started_at": start,
        "window_seconds": int(dimension["window_seconds"]),
        "rolling": rolling,
        "limit_units": int(dimension["limit"]),
        "now": current,
    }
    try:
        engine = _engine_for(_engine_url())
        with engine.connect() as connection:
            row = connection.execute(_baseline_query(spec, lock=False)).mappings().first()
            if row is not None:
                local_settled = _settled_units_since_baseline(connection, spec, row)
                reserved = _active_reserved_units(connection, spec, current)
            else:
                local_settled = reserved = 0
        if row is None:
            return {
                "required": True,
                "status": "unknown",
                "provider": provider_name,
                "account_scope": spec["account_scope"],
                "quota_group": spec["quota_group"],
                "dimension": dimension_name,
                "unit": unit,
                "limit_units": spec["limit_units"],
                "window_started_at": start.replace(tzinfo=UTC).isoformat(),
                "window_seconds": spec["window_seconds"],
                "rolling": rolling,
                "baseline": None,
                "effective_used_units": None,
                "local_settled_since_baseline_units": 0,
                "reserved_units": 0,
                "remaining_units": None,
            }
        effective_used = int(row["used_units"]) + local_settled
        baseline = {
            "used_units": int(row["used_units"]),
            "observed_at": row["observed_at"].replace(tzinfo=UTC).isoformat(),
            "source": row["source"],
            "evidence_reference": _safe_stored_evidence_reference(
                row["evidence_reference"]
            ),
        }
        return {
            "required": True,
            "status": "verified",
            "provider": provider_name,
            "account_scope": spec["account_scope"],
            "quota_group": spec["quota_group"],
            "dimension": dimension_name,
            "unit": unit,
            "limit_units": spec["limit_units"],
            "window_started_at": row["window_started_at"].replace(tzinfo=UTC).isoformat(),
            "window_seconds": spec["window_seconds"],
            "rolling": rolling,
            "baseline": baseline,
            "effective_used_units": effective_used,
            "local_settled_since_baseline_units": local_settled,
            "reserved_units": reserved,
            "remaining_units": max(
                0, int(spec["limit_units"]) - effective_used - reserved
            ),
        }
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota baseline status is unavailable"
        ) from None


def _find_active_identity(connection, spec: dict[str, Any], digest: str, now: datetime):
    predicates = [
        _identities.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
        _identities.c.account_scope == spec["account_scope"],
        _identities.c.quota_group == spec["quota_group"],
        _identities.c.dimension == spec["dimension"],
        _identities.c.window_seconds == spec["window_seconds"],
        _identities.c.identity_digest == digest,
    ]
    if spec["rolling"]:
        predicates.append(
            _identities.c.window_started_at
            >= _utc(now - timedelta(seconds=spec["window_seconds"]))
        )
    else:
        predicates.append(
            _identities.c.window_started_at == spec["window_started_at"]
        )
    query = select(_identities).where(*predicates).order_by(
        _identities.c.window_started_at.desc()
    )
    if connection.dialect.name == "postgresql":
        query = query.with_for_update()
    return connection.execute(query).mappings().first()


def _prune_old_ledger_rows(connection, now: datetime) -> None:
    """Bound history while preserving one full longest quota window."""

    configured_days = getattr(settings, "PROVIDER_QUOTA_LEDGER_RETENTION_DAYS", 180)
    if isinstance(configured_days, bool) or not isinstance(configured_days, int) or configured_days < 1:
        raise ProviderQuotaCoordinatorError(
            "provider quota ledger retention must be a positive integer"
        )
    from app.config import settings as app_settings

    longest_window = max(
        (
            int(dimension.get("window_seconds") or 0)
            for seed in (app_settings.PROVIDER_RATE_LIMIT_SEEDS or {}).values()
            if isinstance(seed, dict)
            for dimension in (seed.get("quota_contract", {}).get("dimensions", []) or [])
            if isinstance(dimension, dict)
        ),
        default=0,
    )
    days = max(configured_days, (longest_window + 86399) // 86400 + 1)
    last_run = connection.execute(
        select(_maintenance.c.last_run_at).where(_maintenance.c.key == "retention-v1")
    ).scalar_one_or_none()
    if last_run is not None and last_run.date() >= now.date():
        return

    cutoff = now - timedelta(days=days)
    stale = connection.execute(
        select(_windows).where(_windows.c.window_started_at < cutoff)
    ).mappings().all()
    for window in stale:
        predicates = [
            _reservations.c.account_scope == window["account_scope"],
            _reservations.c.quota_group == window["quota_group"],
            _reservations.c.dimension == window["dimension"],
            _reservations.c.window_started_at == window["window_started_at"],
            _reservations.c.window_seconds == window["window_seconds"],
        ]
        active = connection.execute(
            select(_reservations.c.id)
            .where(*predicates, _reservations.c.state.in_(["pending", "uncertain"]))
            .limit(1)
        ).first()
        if active is not None:
            continue
        connection.execute(
            _identities.delete().where(
                _identities.c.account_scope == window["account_scope"],
                _identities.c.quota_group == window["quota_group"],
                _identities.c.dimension == window["dimension"],
                _identities.c.window_started_at == window["window_started_at"],
                _identities.c.window_seconds == window["window_seconds"],
            )
        )
        connection.execute(_reservations.delete().where(*predicates))
        connection.execute(_windows.delete().where(_windows.c.id == window["id"]))

    _insert_ignore(
        connection,
        _maintenance,
        {"key": "retention-v1", "last_run_at": now},
        ["key"],
    )
    connection.execute(
        update(_maintenance)
        .where(_maintenance.c.key == "retention-v1")
        .values(last_run_at=now)
    )


def _release_expired_concurrency_leases(
    connection, *, account_scope: str, now: datetime
) -> None:
    if connection.dialect.name == "postgresql":
        query = select(_reservations).where(
            _reservations.c.account_scope == account_scope,
            _reservations.c.release_only.is_(True),
            _reservations.c.state.in_(["pending", "uncertain"]),
            _reservations.c.lease_expires_at <= now,
        ).with_for_update()
    else:
        query = select(_reservations).where(
            _reservations.c.account_scope == account_scope,
            _reservations.c.release_only.is_(True),
            _reservations.c.state.in_(["pending", "uncertain"]),
            _reservations.c.lease_expires_at <= now,
        )
    for row in connection.execute(query).mappings():
        spec = {
            "provider_name": _ACCOUNT_SCOPE_BUCKET,
            "account_scope": row["account_scope"],
            "quota_group": row["quota_group"],
            "dimension": row["dimension"],
            "window_started_at": row["window_started_at"],
            "window_seconds": row["window_seconds"],
        }
        window = _find_window(connection, spec)
        connection.execute(
            update(_windows)
            .where(_windows.c.id == window["id"])
            .values(reserved_units=max(0, int(window["reserved_units"]) - int(row["reserved_units"])))
        )
        connection.execute(
            update(_reservations)
            .where(_reservations.c.id == row["id"])
            .values(state="lease_expired", settled_at=now)
        )


def reserve_provider_quota(
    *,
    provider_name: str,
    capability: str,
    operation: str,
    policy: Any,
    dimension_units: dict[str, int],
    usage_identity: str | None = None,
    now: datetime | None = None,
) -> QuotaReservation | None:
    """Commit every reviewed provider dimension before starting HTTP transport.

    ``None`` means a known dimension has no remaining capacity. Missing policy,
    operation cost, storage, or account scope raises a typed fail-closed error.
    """

    current = now or datetime.now(UTC)
    specs = _dimension_specs(
        provider_name=provider_name,
        capability=capability,
        policy=policy,
        operation=operation,
        dimension_units=dimension_units,
        usage_identity=usage_identity,
        now=current,
    )
    account_scope = specs[0]["account_scope"]
    reservation_id = str(uuid4())
    try:
        engine = _engine_for(_engine_url())
        with _write_transaction(engine) as connection:
            _prune_old_ledger_rows(connection, _utc(current))
            account_scopes = sorted({str(spec["account_scope"]) for spec in specs})
            for scope in account_scopes:
                _insert_ignore(
                    connection,
                    _scope_locks,
                    {"provider_name": _ACCOUNT_SCOPE_BUCKET, "account_scope": scope},
                    ["provider_name", "account_scope"],
                )
                lock_query = select(_scope_locks).where(
                    _scope_locks.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
                    _scope_locks.c.account_scope == scope,
                )
                if connection.dialect.name == "postgresql":
                    lock_query = lock_query.with_for_update()
                connection.execute(lock_query).first()
                _release_expired_concurrency_leases(
                    connection,
                    account_scope=scope,
                    now=_utc(current),
                )
            windows: dict[tuple, dict[str, Any]] = {}
            baselines: dict[tuple, Any] = {}
            created_window_ids: set[int] = set()
            charged_specs: list[tuple[dict[str, Any], int]] = []
            for spec in specs:
                units = int(spec["units"])
                identity_digest = spec.get("identity_digest")
                if identity_digest:
                    identity = _find_active_identity(
                        connection, spec, identity_digest, _utc(current)
                    )
                    if identity is not None:
                        if spec["rolling"]:
                            spec["window_started_at"] = identity["window_started_at"]
                        units = 0
                values = _window_values(spec)
                existing_window = _find_window(connection, spec, required=False)
                _insert_ignore(
                    connection,
                    _windows,
                    {
                        **values,
                        "limit_units": spec["limit_units"],
                        "reserved_units": 0,
                        "consumed_units": 0,
                    },
                    list(values),
                )
                window = _find_window(connection, spec)
                if existing_window is None:
                    created_window_ids.add(int(window["id"]))
                # An operator-reviewed plan/limit change applies immediately,
                # including a trial expiry that lowers MarketData.app's pool.
                connection.execute(
                    update(_windows)
                    .where(_windows.c.id == window["id"])
                    .values(limit_units=spec["limit_units"])
                )
                window = {**window, "limit_units": spec["limit_units"]}
                key = tuple(values.values())
                windows[key] = window
                if not spec["release_only"]:
                    baseline = _baseline_for_reservation(connection, spec, _utc(current))
                    if baseline is None:
                        if created_window_ids:
                            connection.execute(
                                delete(_windows).where(
                                    _windows.c.id.in_(created_window_ids),
                                    _windows.c.reserved_units == 0,
                                    _windows.c.consumed_units == 0,
                                )
                            )
                        return None
                    baselines[key] = baseline
                charged_specs.append((spec, units))

            for spec, units in charged_specs:
                identity_digest = spec.get("identity_digest")
                if units <= 0 and not identity_digest:
                    continue
                if spec["release_only"]:
                    # Concurrency is a lease-only dimension. It has no
                    # provider-reported usage baseline; admission is based
                    # solely on currently reserved in-flight leases.
                    window = windows[tuple(_window_values(spec).values())]
                    reserved = window["reserved_units"]
                    consumed = 0
                elif units > 0 and spec["rolling"]:
                    cutoff = _utc(current - timedelta(seconds=spec["window_seconds"]))
                    active_query = select(
                        func.coalesce(func.sum(_windows.c.reserved_units), 0),
                    ).where(
                        _windows.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
                        _windows.c.account_scope == spec["account_scope"],
                        _windows.c.quota_group == spec["quota_group"],
                        _windows.c.dimension == spec["dimension"],
                        _windows.c.window_seconds == spec["window_seconds"],
                        _windows.c.window_started_at >= cutoff,
                    )
                    reserved = connection.execute(active_query).scalar_one()
                    consumed = int(baselines[tuple(_window_values(spec).values())]["used_units"])
                    consumed += _settled_units_since_baseline(
                        connection, {**spec, "now": _utc(current)}, baselines[tuple(_window_values(spec).values())]
                    )
                elif units > 0:
                    window = windows[tuple(_window_values(spec).values())]
                    reserved = window["reserved_units"]
                    baseline = baselines[tuple(_window_values(spec).values())]
                    consumed = int(baseline["used_units"]) + _settled_units_since_baseline(
                        connection, {**spec, "now": _utc(current)}, baseline
                    )
                else:
                    reserved = consumed = 0
                if units > 0 and int(spec["limit_units"]) - int(reserved) - int(consumed) < units:
                    if created_window_ids:
                        connection.execute(
                            delete(_windows).where(
                                _windows.c.id.in_(created_window_ids),
                                _windows.c.reserved_units == 0,
                                _windows.c.consumed_units == 0,
                            )
                        )
                    return None

            for spec, units in charged_specs:
                identity_digest = spec.get("identity_digest")
                if identity_digest and units > 0:
                    _insert_ignore(
                        connection,
                        _identities,
                        {
                            "provider_name": _ACCOUNT_SCOPE_BUCKET,
                            "account_scope": spec["account_scope"],
                            "quota_group": spec["quota_group"],
                            "dimension": spec["dimension"],
                            "window_started_at": spec["window_started_at"],
                            "window_seconds": spec["window_seconds"],
                            "identity_digest": identity_digest,
                            "owner_reservation_id": reservation_id,
                            "state": "pending",
                        },
                        [
                            "provider_name",
                            "account_scope",
                            "quota_group",
                            "dimension",
                            "window_started_at",
                            "window_seconds",
                            "identity_digest",
                        ],
                    )
                key = tuple(_window_values(spec).values())
                window = windows[key]
                if units > 0:
                    connection.execute(
                        update(_windows)
                        .where(_windows.c.id == window["id"])
                        .values(reserved_units=int(window["reserved_units"]) + units)
                    )
                connection.execute(
                    insert(_reservations).values(
                        reservation_id=reservation_id,
                        provider_name=provider_name,
                        account_scope=spec["account_scope"],
                        operation=operation,
                        quota_group=spec["quota_group"],
                        dimension=spec["dimension"],
                        unit=spec["unit"],
                        window_started_at=spec["window_started_at"],
                        window_seconds=spec["window_seconds"],
                        reserved_units=units,
                        release_only=spec["release_only"],
                        lease_expires_at=spec["lease_expires_at"],
                        identity_digest=identity_digest,
                        state="pending",
                        created_at=_utc(current),
                    )
                )
        return QuotaReservation(reservation_id, provider_name, account_scope)
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator reservation failed; provider call was blocked"
        ) from None


def settle_provider_quota(
    reservation: QuotaReservation,
    *,
    observed_dimension_units: dict[str, int] | None = None,
    unknown_dimensions: set[str] | None = None,
    release_identities: bool = False,
    now: datetime | None = None,
) -> None:
    """Settle confirmed usage; leave ambiguous dimensions reserved to reset."""

    supplied_now = now or datetime.now(UTC)
    current = (
        supplied_now.replace(tzinfo=UTC)
        if supplied_now.tzinfo is None
        else supplied_now.astimezone(UTC)
    )
    observed = observed_dimension_units or {}
    unknown = unknown_dimensions or set()
    try:
        engine = _engine_for(_engine_url())
        with _write_transaction(engine) as connection:
            reservation_query = select(_reservations).where(
                    _reservations.c.reservation_id == reservation.reservation_id,
                    _reservations.c.state == "pending",
                ).order_by(_reservations.c.id)
            if connection.dialect.name == "postgresql":
                reservation_query = reservation_query.with_for_update()
            rows = connection.execute(reservation_query).mappings().all()
            for row in rows:
                spec = {
                    "provider_name": _ACCOUNT_SCOPE_BUCKET,
                    "account_scope": row["account_scope"],
                    "quota_group": row["quota_group"],
                    "dimension": row["dimension"],
                    "window_started_at": row["window_started_at"],
                    "window_seconds": row["window_seconds"],
                }
                window = _find_window(connection, spec)
                if row["dimension"] in unknown:
                    # An interrupted/ambiguous transport can still occupy a
                    # provider-side concurrency slot. The exact client timeout
                    # lease releases only this dimension after timeout+grace.
                    state = "uncertain"
                elif row["release_only"]:
                    connection.execute(
                        update(_windows)
                        .where(_windows.c.id == window["id"])
                        .values(
                            reserved_units=max(
                                0,
                                int(window["reserved_units"]) - int(row["reserved_units"]),
                            )
                        )
                    )
                    state = "settled"
                else:
                    actual = observed.get(row["dimension"], row["reserved_units"])
                    if isinstance(actual, bool) or not isinstance(actual, int) or actual < 0:
                        raise ProviderQuotaAdmissionError(
                            f"invalid observed usage for {row['provider_name']}/{row['dimension']}"
                        )
                    connection.execute(
                        update(_windows)
                        .where(_windows.c.id == window["id"])
                        .values(
                            reserved_units=max(
                                0,
                                int(window["reserved_units"]) - int(row["reserved_units"]),
                            ),
                            consumed_units=int(window["consumed_units"]) + actual,
                        )
                    )
                    connection.execute(
                        update(_reservations)
                        .where(_reservations.c.id == row["id"])
                        .values(reserved_units=actual)
                    )
                    state = "not_sent" if release_identities else "settled"
                connection.execute(
                    update(_reservations)
                    .where(_reservations.c.id == row["id"])
                    .values(state=state, settled_at=current)
                )
                identity_digest = row["identity_digest"]
                if identity_digest:
                    identity_query = select(_identities).where(
                        _identities.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
                        _identities.c.account_scope == row["account_scope"],
                        _identities.c.quota_group == row["quota_group"],
                        _identities.c.dimension == row["dimension"],
                        _identities.c.window_started_at == row["window_started_at"],
                        _identities.c.window_seconds == row["window_seconds"],
                        _identities.c.identity_digest == identity_digest,
                    )
                    if connection.dialect.name == "postgresql":
                        identity_query = identity_query.with_for_update()
                    identity = connection.execute(identity_query).mappings().first()
                    if identity is not None and identity["state"] == "pending":
                        if release_identities and identity["owner_reservation_id"] == reservation.reservation_id:
                            other_query = select(_reservations).where(
                                _reservations.c.account_scope == row["account_scope"],
                                _reservations.c.quota_group == row["quota_group"],
                                _reservations.c.dimension == row["dimension"],
                                _reservations.c.window_started_at == row["window_started_at"],
                                _reservations.c.window_seconds == row["window_seconds"],
                                _reservations.c.identity_digest == identity_digest,
                                _reservations.c.reservation_id != reservation.reservation_id,
                            ).order_by(_reservations.c.id)
                            if connection.dialect.name == "postgresql":
                                other_query = other_query.with_for_update()
                            others = connection.execute(other_query).mappings().all()
                            accepted = next(
                                (item for item in others if item["state"] in {"settled", "uncertain"}),
                                None,
                            )
                            pending = next(
                                (item for item in others if item["state"] == "pending"),
                                None,
                            )
                            if accepted is not None:
                                connection.execute(
                                    update(_identities)
                                    .where(_identities.c.id == identity["id"])
                                    .values(
                                        state="uncertain" if accepted["state"] == "uncertain" else "consumed",
                                        owner_reservation_id=None,
                                    )
                                )
                            elif pending is not None:
                                connection.execute(
                                    update(_identities)
                                    .where(_identities.c.id == identity["id"])
                                    .values(owner_reservation_id=pending["reservation_id"])
                                )
                            else:
                                connection.execute(
                                    _identities.delete().where(_identities.c.id == identity["id"])
                                )
                        elif not release_identities:
                            connection.execute(
                                update(_identities)
                                .where(_identities.c.id == identity["id"])
                                .values(
                                    state="uncertain" if row["dimension"] in unknown else "consumed",
                                    owner_reservation_id=None,
                                )
                            )
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator settlement failed; outstanding reservation retained"
        ) from None


def _reservation_plan_for_live_probe(
    provider_name: str,
    operation: str,
    usage_identity: str | None,
    now: datetime,
    operation_cost_override: int | None = None,
    dimension_cost_overrides: dict[str, int] | None = None,
) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
    """Build the exact same kind of provider-specific plan for direct probes."""

    from app.config import (
        provider_quota_reset_is_admission_safe,
        provider_quota_reset_is_known,
        provider_rate_limit_seed,
    )
    from app.providers.registry import get_provider_usage_profile
    from app.services.provider_routing import _window_start_for_dimension

    seed = provider_rate_limit_seed(provider_name)
    contract = seed.get("quota_contract")
    if not isinstance(contract, dict):
        raise ProviderQuotaAdmissionError(
            f"provider quota is unknown for live operation {provider_name}/{operation}"
        )
    if not provider_quota_reset_is_known(contract.get("reset")):
        raise ProviderQuotaAdmissionError(
            f"provider quota reset semantics are unreviewed for live operation {provider_name}/{operation}"
        )
    if contract.get("unknown_dimensions") or contract.get("untracked_constraints"):
        raise ProviderQuotaAdmissionError(
            f"provider quota contract remains incomplete for live operation {provider_name}/{operation}"
        )
    profile = get_provider_usage_profile(provider_name)
    bootstrap_unknown: set[str] = set()
    bootstrap = contract.get("account_usage_bootstrap")
    if operation == "fetch_account_usage" and isinstance(bootstrap, dict) and bootstrap.get(
        "enabled"
    ) is True:
        policy = SimpleNamespace(
            quota_contract=contract,
            quota_scope=seed.get("quota_scope", ""),
        )
        for item in contract.get("dimensions", []) or []:
            if not isinstance(item, dict):
                continue
            unit = str(item.get("unit") or "").strip().lower()
            if unit in {"concurrent_requests", "concurrency"}:
                continue
            applies_to = item.get("applies_to_operations")
            if applies_to is not None:
                if not isinstance(applies_to, list) or not applies_to:
                    continue
                family = operation.split(":", 1)[0].strip() or operation
                if operation not in {str(value) for value in applies_to} and family not in {
                    str(value) for value in applies_to
                }:
                    continue
            status = provider_quota_baseline_status(
                provider_name=provider_name,
                capability="account_usage",
                policy=policy,
                dimension_name=str(item.get("name") or ""),
                now=now,
            )
            if status.get("status") != "verified":
                bootstrap_unknown.add(str(item.get("name") or ""))
    family = operation.split(":", 1)[0].strip() or operation
    costs = profile.get("operation_costs") or contract.get("operation_costs") or {}
    cost = (
        operation_cost_override
        if operation_cost_override is not None
        else costs.get(family, costs.get(operation))
        if isinstance(costs, dict)
        else None
    )
    if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
        raise ProviderQuotaAdmissionError(
            f"provider operation cost is unreviewed for live operation {provider_name}/{operation}"
        )
    dimensions = contract.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ProviderQuotaAdmissionError(
            f"provider quota dimensions are unknown for live operation {provider_name}/{operation}"
        )
    dimension_costs = profile.get("dimension_costs") or contract.get("dimension_costs") or {}
    result: list[dict[str, Any]] = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            raise ProviderQuotaAdmissionError("provider quota dimension is malformed")
        name = str(dimension.get("name") or "")
        applies_to = dimension.get("applies_to_operations")
        if applies_to is not None:
            if not isinstance(applies_to, list) or not applies_to:
                continue
            if operation not in {str(value) for value in applies_to} and family not in {
                str(value) for value in applies_to
            }:
                continue
        effective_reset = dimension.get("reset", contract.get("reset"))
        if not provider_quota_reset_is_admission_safe(effective_reset):
            suffix = "unknown" if not provider_quota_reset_is_known(effective_reset) else "unresolved"
            raise ProviderQuotaAdmissionError(
                f"provider dimension reset semantics are {suffix} for live operation {provider_name}/{operation}/{name}"
            )
        unit = str(dimension.get("unit") or "").lower()
        if name in bootstrap_unknown:
            amount = 0
            zero_cost_exclusion = True
        else:
            zero_cost_exclusion = False
        raw_cost_map = (
            {family: dimension_cost_overrides[name]}
            if dimension_cost_overrides and name in dimension_cost_overrides
            else dimension_costs.get(name)
            if isinstance(dimension_costs, dict)
            else None
        )
        if name in bootstrap_unknown:
            amount = 0
        elif isinstance(raw_cost_map, dict):
            # An empty per-dimension map is an explicit reviewed exclusion.
            # This is used, for example, when a synchronous operation is not
            # charged against a provider's separate asynchronous-dataset
            # request pool. A non-empty map that omits this operation falls
            # back to the reviewed operation cost only when this contract does
            # not require per-dimension maps. A contract that explicitly
            # requires them still fails closed when the operation is absent;
            # silently treating that case as zero would under-account a newly
            # added operation.
            if not raw_cost_map:
                amount = 0
                zero_cost_exclusion = True
            else:
                missing = object()
                amount = raw_cost_map.get(family, missing)
                if amount is missing:
                    amount = raw_cost_map.get(operation, missing)
                if amount is missing:
                    rate_unit = unit in {
                        "request",
                        "requests",
                        "call",
                        "calls",
                        "credit",
                        "credits",
                        "token",
                        "tokens",
                        "weight",
                        "request_weight",
                    }
                    amount = (
                        cost
                        if not contract.get("dimension_costs_required") and rate_unit
                        else None
                    )
                elif isinstance(amount, dict):
                    # Keep the provider-specific zero-cost meaning consistent
                    # with the runtime reservation path: an explicitly empty
                    # operation value excludes only this dimension, while a
                    # non-empty value that is not an integer remains unknown.
                    zero_cost_exclusion = not amount
                    amount = 0 if zero_cost_exclusion else None
        elif unit in {"concurrent_requests", "concurrency"}:
            amount = 1
        elif unit in {"byte", "bytes"}:
            amount = None
        elif contract.get("dimension_costs_required"):
            rate_unit = unit in {
                "request",
                "requests",
                "call",
                "calls",
                "credit",
                "credits",
                "token",
                "tokens",
                "weight",
                "request_weight",
            }
            # A reviewed provider-profile operation cost is an explicit
            # conservative unit count too; a caller override is not required
            # merely because the provider declares multiple dimensions.
            amount = cost if rate_unit else None
        else:
            amount = cost
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int)
            or amount < 0
            or (amount == 0 and not zero_cost_exclusion)
        ):
            raise ProviderQuotaAdmissionError(
                f"provider dimension cost is unreviewed for live operation {provider_name}/{operation}/{name}"
            )
        if amount == 0:
            continue
        distinct = unit in {"symbol", "symbols", "unique_symbol", "unique_symbols"}
        quota_group = str(dimension.get("quota_group") or "").strip()
        if not quota_group:
            raise ProviderQuotaAdmissionError(
                f"provider quota group is not reviewed for live operation {provider_name}/{operation}/{name}"
            )
        if distinct and not usage_identity:
            raise ProviderQuotaAdmissionError(
                f"provider identity cost is unreviewed for live operation {provider_name}/{operation}"
            )
        window_start, rolling = _window_start_for_dimension(
            dimension, reset=str(contract.get("reset") or ""), now=now
        )
        dimension_reset = str(
            dimension.get("reset") or contract.get("reset") or ""
        ).strip()
        if window_start is None:
            seconds = int(dimension["window_seconds"])
            if rolling:
                window_start = datetime.fromtimestamp(int(now.timestamp()), tz=UTC)
            else:
                epoch = int(now.timestamp())
                window_start = datetime.fromtimestamp(epoch - epoch % seconds, tz=UTC)
        result.append(
            {
                "provider_name": provider_name,
                "account_scope": account_scope_for_provider(
                    provider_name, str(dimension.get("scope") or "")
                ),
                "operation": operation,
                "quota_group": quota_group,
                "dimension": name,
                "unit": unit,
                "window_started_at": _utc(window_start),
                "window_seconds": int(dimension["window_seconds"]),
                "reset": dimension_reset,
                "rolling": rolling,
                "limit_units": int(dimension["limit"]),
                "units": 1 if unit in {"concurrent_requests", "concurrency"} else amount,
                "release_only": unit in {"concurrent_requests", "concurrency"},
                "lease_expires_at": _utc(now + timedelta(seconds=40))
                if unit in {"concurrent_requests", "concurrency"}
                else None,
                "identity_digest": hashlib.sha256(
                    str(usage_identity or "").strip().upper().encode("utf-8")
                ).hexdigest()
                if distinct
                else None,
            }
        )
    return (
        str(contract.get("reset") or ""),
        {str(item["dimension"]): int(item["units"]) for item in result},
        result,
    )


def reserve_live_provider_operation(
    provider_name: str,
    operation: str,
    usage_identity: str | None = None,
    *,
    operation_cost_override: int | None = None,
    dimension_cost_overrides: dict[str, int] | None = None,
    require_persistent_coordinator: bool = False,
) -> QuotaReservation | None:
    """Reserve a bounded direct-live operation before its adapter is invoked.

    ``require_persistent_coordinator`` is set by the real live-test wrapper and
    its runner preflight. Unit tests may still exercise this path against an
    isolated SQLite ledger on GitHub Actions without being mistaken for a live
    credentialed run.
    """

    now = datetime.now(UTC)
    _, dimension_units, specs = _reservation_plan_for_live_probe(
        provider_name,
        operation,
        usage_identity,
        now,
        operation_cost_override=operation_cost_override,
        dimension_cost_overrides=dimension_cost_overrides,
    )
    account_scope = specs[0]["account_scope"]
    reservation_id = str(uuid4())
    try:
        engine = _engine_for(
            _engine_url(), require_persistent=require_persistent_coordinator
        )
        with _write_transaction(engine) as connection:
            _prune_old_ledger_rows(connection, _utc(now))
            account_scopes = sorted({str(spec["account_scope"]) for spec in specs})
            for scope in account_scopes:
                _insert_ignore(
                    connection,
                    _scope_locks,
                    {"provider_name": _ACCOUNT_SCOPE_BUCKET, "account_scope": scope},
                    ["provider_name", "account_scope"],
                )
                lock_query = select(_scope_locks).where(
                    _scope_locks.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
                    _scope_locks.c.account_scope == scope,
                )
                if connection.dialect.name == "postgresql":
                    lock_query = lock_query.with_for_update()
                connection.execute(lock_query).first()
                _release_expired_concurrency_leases(
                    connection,
                    account_scope=scope,
                    now=_utc(now),
                )
            windows: dict[tuple, dict[str, Any]] = {}
            baselines: dict[tuple, Any] = {}
            created_window_ids: set[int] = set()
            charged: list[tuple[dict[str, Any], int]] = []
            for spec in specs:
                units = int(dimension_units.get(str(spec["dimension"]), 0))
                identity_digest = spec.get("identity_digest")
                if identity_digest:
                    identity = _find_active_identity(
                        connection, spec, identity_digest, _utc(now)
                    )
                    if identity is not None:
                        if spec["rolling"]:
                            spec["window_started_at"] = identity["window_started_at"]
                        units = 0
                values = _window_values(spec)
                existing_window = _find_window(connection, spec, required=False)
                _insert_ignore(
                    connection,
                    _windows,
                    {**values, "limit_units": spec["limit_units"], "reserved_units": 0, "consumed_units": 0},
                    list(values),
                )
                window = _find_window(connection, spec)
                if existing_window is None:
                    created_window_ids.add(int(window["id"]))
                connection.execute(
                    update(_windows).where(_windows.c.id == window["id"]).values(limit_units=spec["limit_units"])
                )
                key = tuple(values.values())
                windows[key] = {**window, "limit_units": spec["limit_units"]}
                if not spec["release_only"]:
                    baseline = _baseline_for_reservation(connection, spec, _utc(now))
                    if baseline is None:
                        if created_window_ids:
                            connection.execute(
                                delete(_windows).where(
                                    _windows.c.id.in_(created_window_ids),
                                    _windows.c.reserved_units == 0,
                                    _windows.c.consumed_units == 0,
                                )
                            )
                        return None
                    baselines[key] = baseline
                charged.append((spec, units))
            for spec, units in charged:
                identity_digest = spec.get("identity_digest")
                if units <= 0 and not identity_digest:
                    continue
                if spec["release_only"]:
                    # Concurrency leases are governed by active reservations,
                    # not by a finite provider-usage baseline.
                    window = windows[tuple(_window_values(spec).values())]
                    reserved = window["reserved_units"]
                    consumed = 0
                elif units > 0 and spec["rolling"]:
                    cutoff = _utc(now - timedelta(seconds=spec["window_seconds"]))
                    reserved = connection.execute(
                        select(func.coalesce(func.sum(_windows.c.reserved_units), 0)).where(
                            _windows.c.provider_name == _ACCOUNT_SCOPE_BUCKET,
                            _windows.c.account_scope == spec["account_scope"],
                            _windows.c.quota_group == spec["quota_group"],
                            _windows.c.dimension == spec["dimension"],
                            _windows.c.window_seconds == spec["window_seconds"],
                            _windows.c.window_started_at >= cutoff,
                        )
                    ).scalar_one()
                    baseline = baselines[tuple(_window_values(spec).values())]
                    consumed = int(baseline["used_units"]) + _settled_units_since_baseline(
                        connection, {**spec, "now": _utc(now)}, baseline
                    )
                elif units > 0:
                    window = windows[tuple(_window_values(spec).values())]
                    reserved = window["reserved_units"]
                    baseline = baselines[tuple(_window_values(spec).values())]
                    consumed = int(baseline["used_units"]) + _settled_units_since_baseline(
                        connection, {**spec, "now": _utc(now)}, baseline
                    )
                else:
                    reserved = consumed = 0
                if units > 0 and int(spec["limit_units"]) - int(reserved) - int(consumed) < units:
                    if created_window_ids:
                        connection.execute(
                            delete(_windows).where(
                                _windows.c.id.in_(created_window_ids),
                                _windows.c.reserved_units == 0,
                                _windows.c.consumed_units == 0,
                            )
                        )
                    return None
            for spec, units in charged:
                identity_digest = spec.get("identity_digest")
                if identity_digest and units > 0:
                    _insert_ignore(
                        connection,
                        _identities,
                        {
                            "provider_name": _ACCOUNT_SCOPE_BUCKET,
                            "account_scope": spec["account_scope"],
                            "quota_group": spec["quota_group"],
                            "dimension": spec["dimension"],
                            "window_started_at": spec["window_started_at"],
                            "window_seconds": spec["window_seconds"],
                            "identity_digest": identity_digest,
                            "owner_reservation_id": reservation_id,
                            "state": "pending",
                        },
                        ["provider_name", "account_scope", "quota_group", "dimension", "window_started_at", "window_seconds", "identity_digest"],
                    )
                window = windows[tuple(_window_values(spec).values())]
                if units > 0:
                    connection.execute(
                        update(_windows).where(_windows.c.id == window["id"]).values(reserved_units=int(window["reserved_units"]) + units)
                    )
                connection.execute(
                    insert(_reservations).values(
                        reservation_id=reservation_id,
                        provider_name=provider_name,
                        account_scope=spec["account_scope"],
                        operation=operation,
                        quota_group=spec["quota_group"],
                        dimension=spec["dimension"],
                        unit=spec["unit"],
                        window_started_at=spec["window_started_at"],
                        window_seconds=spec["window_seconds"],
                        reserved_units=units,
                        release_only=spec["release_only"],
                        lease_expires_at=spec["lease_expires_at"],
                        identity_digest=identity_digest,
                        state="pending",
                        created_at=_utc(now),
                    )
                )
        return QuotaReservation(reservation_id, provider_name, account_scope)
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator reservation failed; provider call was blocked"
        ) from None


def settle_live_provider_operation(
    reservation: QuotaReservation,
    *,
    http_requests: int,
    response_bytes: int,
) -> None:
    """Settle a direct live probe immediately from transport telemetry."""

    try:
        engine = _engine_for(_engine_url())
        with engine.connect() as connection:
            rows = connection.execute(
                select(
                    _reservations.c.dimension,
                    _reservations.c.unit,
                    _reservations.c.release_only,
                ).where(
                    _reservations.c.reservation_id == reservation.reservation_id,
                    _reservations.c.state == "pending",
                )
            ).all()
        if http_requests <= 0:
            unknown = {str(name) for name, _ in rows}
            observed: dict[str, int] = {}
        else:
            unknown = set()
            observed = {}
            for name, unit, release_only in rows:
                normalized_unit = str(unit).lower()
                if release_only:
                    continue
                if normalized_unit in {"byte", "bytes"}:
                    observed[str(name)] = int(response_bytes)
                elif normalized_unit in {"request", "requests"}:
                    observed[str(name)] = int(http_requests)
                # ``call(s)`` may be provider-priced credits (EODHD
                # Fundamentals is ten credits for one HTTP request). Keep the
                # reviewed reservation after any completed response instead
                # of refunding credits based on transport count.
        settle_provider_quota(
            reservation,
            observed_dimension_units=observed,
            unknown_dimensions=unknown,
        )
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator settlement failed; outstanding reservation retained"
        ) from None


def register_live_receipt_reservation(
    reservation: QuotaReservation,
    *,
    run_id: str,
    usage_scope: str,
    receipt_status: str,
    now: datetime | None = None,
) -> str:
    """Link one redacted live observation to its existing reservation.

    This function never creates a quota reservation and never adjusts a quota
    window.  It only records the already-generated reservation identity after
    the live wrapper has settled (or retained) that reservation.  Repeating the
    call with the same identity is idempotent; changing its provider, operation,
    run, or scope fails closed.
    """

    try:
        reservation_id = str(UUID(str(reservation.reservation_id).strip()))
    except (TypeError, ValueError, AttributeError):
        raise ProviderQuotaCoordinatorError("live receipt reservation ID is invalid") from None
    provider_name = _validated_live_receipt_field(
        reservation.provider_name, name="provider", maximum=100
    )
    # The operation is not part of QuotaReservation for compatibility with the
    # application-facing API. Read it from the durable reservation rows below,
    # then bind that canonical value into the receipt registry.
    normalized_run_id = _validated_live_receipt_field(run_id, name="run ID", maximum=128)
    normalized_scope = _validated_live_receipt_field(
        usage_scope, name="usage scope", maximum=128
    )
    normalized_status = str(receipt_status or "").strip()
    if normalized_status not in _LIVE_RECEIPT_STATUSES:
        raise ProviderQuotaCoordinatorError("live receipt status is invalid")
    supplied_now = now or datetime.now(UTC)
    current = (
        supplied_now.replace(tzinfo=UTC)
        if supplied_now.tzinfo is None
        else supplied_now.astimezone(UTC)
    )
    try:
        engine = _engine_for(_engine_url())
        with _write_transaction(engine) as connection:
            reservation_query = select(_reservations).where(
                _reservations.c.reservation_id == reservation_id
            )
            if connection.dialect.name == "postgresql":
                reservation_query = reservation_query.with_for_update()
            rows = connection.execute(reservation_query).mappings().all()
            if not rows:
                raise ProviderQuotaCoordinatorError(
                    "live receipt reservation is not present in the durable coordinator"
                )
            if any(str(row["provider_name"]) != provider_name for row in rows):
                raise ProviderQuotaCoordinatorError("live receipt provider does not match reservation")
            operations = {str(row["operation"]) for row in rows}
            if len(operations) != 1:
                raise ProviderQuotaCoordinatorError("live receipt reservation operation is ambiguous")
            operation = next(iter(operations))
            states = {str(row["state"]) for row in rows}
            if states <= {"settled", "not_sent"}:
                reconciliation_state = "reconciled"
                reconciled_at = current
            elif "uncertain" in states or "lease_expired" in states:
                reconciliation_state = "uncertain"
                reconciled_at = None
            elif "pending" in states:
                reconciliation_state = "pending"
                reconciled_at = None
            else:
                raise ProviderQuotaCoordinatorError("live receipt reservation state is invalid")

            existing = connection.execute(
                select(_live_receipts).where(
                    _live_receipts.c.reservation_id == reservation_id
                )
            ).mappings().first()
            values = {
                "reservation_id": reservation_id,
                "provider_name": provider_name,
                "operation": operation,
                "run_id": normalized_run_id,
                "usage_scope": normalized_scope,
                "receipt_status": normalized_status,
                "reconciliation_state": reconciliation_state,
                "created_at": _utc(current),
                "reconciled_at": _utc(reconciled_at) if reconciled_at else None,
                "error": None,
            }
            if existing is not None:
                immutable = ("provider_name", "operation", "run_id", "usage_scope")
                if any(existing[key] != values[key] for key in immutable):
                    raise ProviderQuotaCoordinatorError(
                        "live receipt identity conflicts with an existing registry row"
                    )
                # Preserve a previously conservative state. A later retry may
                # only move pending -> reconciled; it may never erase uncertain.
                if existing["reconciliation_state"] == "uncertain":
                    return "uncertain"
                if existing["reconciliation_state"] == "reconciled":
                    return "reconciled"
                connection.execute(
                    update(_live_receipts)
                    .where(_live_receipts.c.reservation_id == reservation_id)
                    .values(
                        receipt_status=normalized_status,
                        reconciliation_state=reconciliation_state,
                        reconciled_at=values["reconciled_at"],
                        error=None,
                    )
                )
                return reconciliation_state
            connection.execute(insert(_live_receipts).values(**values))
            return reconciliation_state
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "live receipt registry write failed; quota state was not inferred"
        ) from None


def reconcile_live_receipt_reservation(reservation_id: str) -> str:
    """Reconcile one registered receipt without trusting receipt measurements.

    A pending reservation is settled with the original coordinator-reserved
    units.  That is conservative recovery for a process that may have reached
    the provider before it crashed.  Settled/not-sent rows are a no-op;
    uncertain rows remain blocked and require operator/provider-native review.
    """

    try:
        normalized_id = str(UUID(str(reservation_id).strip()))
    except (TypeError, ValueError, AttributeError):
        raise ProviderQuotaCoordinatorError("live receipt reservation ID is invalid") from None
    try:
        engine = _engine_for(_engine_url())
        with engine.connect() as connection:
            receipt = connection.execute(
                select(_live_receipts).where(
                    _live_receipts.c.reservation_id == normalized_id
                )
            ).mappings().first()
            if receipt is None:
                raise ProviderQuotaCoordinatorError(
                    "live receipt is not registered in the durable coordinator"
                )
            if receipt["reconciliation_state"] == "reconciled":
                return "reconciled"
            rows = connection.execute(
                select(_reservations).where(
                    _reservations.c.reservation_id == normalized_id
                )
            ).mappings().all()
        if not rows:
            raise ProviderQuotaCoordinatorError(
                "registered live receipt has no durable reservation rows"
            )
        if any(
            str(row["provider_name"]) != str(receipt["provider_name"])
            or str(row["operation"]) != str(receipt["operation"])
            for row in rows
        ):
            raise ProviderQuotaCoordinatorError(
                "registered live receipt does not match its reservation"
            )
        states = {str(row["state"]) for row in rows}
        if "uncertain" in states or "lease_expired" in states:
            raise ProviderQuotaCoordinatorError(
                "live receipt has an uncertain reservation; provider-native reconciliation is required"
            )
        if "pending" in states:
            settle_provider_quota(
                QuotaReservation(
                    normalized_id,
                    str(receipt["provider_name"]),
                    account_scope=str(rows[0]["account_scope"]),
                ),
                # Empty observed usage makes settlement use the original
                # reserved units. No artifact request/byte field is trusted.
                observed_dimension_units={},
            )
        with _write_transaction(engine) as connection:
            remaining = connection.execute(
                select(_reservations.c.state).where(
                    _reservations.c.reservation_id == normalized_id
                )
            ).scalars().all()
            states = {str(state) for state in remaining}
            if states & {"pending", "uncertain", "lease_expired"}:
                raise ProviderQuotaCoordinatorError(
                    "live receipt reservation remains unresolved after reconciliation"
                )
            connection.execute(
                update(_live_receipts)
                .where(_live_receipts.c.reservation_id == normalized_id)
                .values(
                    reconciliation_state="reconciled",
                    reconciled_at=_utc(datetime.now(UTC)),
                    error=None,
                )
            )
        return "reconciled"
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "live receipt reconciliation failed; reservation remains conservative"
        ) from None


def reconcile_pending_live_receipts() -> dict[str, int]:
    """Recover registered pending receipts before a new live run.

    Legacy aggregate JSONL rows do not contain reservation IDs and are never
    imported. Any unknown, mismatched, or uncertain registry entry blocks the
    caller before network access.
    """

    try:
        engine = _engine_for(_engine_url())
        with engine.connect() as connection:
            ids = connection.execute(
                select(_live_receipts.c.reservation_id)
                .where(_live_receipts.c.reconciliation_state != "reconciled")
                .order_by(_live_receipts.c.created_at, _live_receipts.c.reservation_id)
            ).scalars().all()
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "live receipt reconciliation scan failed"
        ) from None
    reconciled = 0
    unresolved = 0
    for reservation_id in ids:
        try:
            reconcile_live_receipt_reservation(str(reservation_id))
        except ProviderQuotaCoordinatorError:
            unresolved += 1
        else:
            reconciled += 1
    if unresolved:
        raise ProviderQuotaCoordinatorError(
            f"{unresolved} live receipt reservation(s) remain unresolved"
        )
    return {"scanned": len(ids), "reconciled": reconciled, "unresolved": unresolved}


async def reserve_provider_quota_async(**kwargs) -> QuotaReservation | None:
    return await asyncio.to_thread(reserve_provider_quota, **kwargs)


async def settle_provider_quota_async(reservation: QuotaReservation, **kwargs) -> None:
    await asyncio.to_thread(settle_provider_quota, reservation, **kwargs)


def ensure_provider_quota_coordinator(*, require_persistent_coordinator: bool = False) -> None:
    """Initialize and verify read/write/lock semantics before live use.

    A schema creation plus ``SELECT`` only proves that the coordinator can be
    opened. The backend and worker startup checks need stronger evidence: a
    committed write, a transaction-scoped lock, and a read of the value while
    that lock is held. The non-secret health marker is intentionally durable so
    an operator can see the last successful process-level probe in diagnostics.
    """

    try:
        engine = _engine_for(
            _engine_url(), require_persistent=require_persistent_coordinator
        )
        now = datetime.now(UTC)
        with _write_transaction(engine) as connection:
            _insert_ignore(
                connection,
                _maintenance,
                {"key": _HEALTH_PROBE_KEY, "last_run_at": now},
                ["key"],
            )
            updated = connection.execute(
                update(_maintenance)
                .where(_maintenance.c.key == _HEALTH_PROBE_KEY)
                .values(last_run_at=now)
            )
            if updated.rowcount != 1:
                raise ProviderQuotaCoordinatorError(
                    "provider quota coordinator health marker could not be written"
                )
            probe = select(_maintenance.c.last_run_at).where(
                _maintenance.c.key == _HEALTH_PROBE_KEY
            )
            if connection.dialect.name == "postgresql":
                probe = probe.with_for_update()
            if connection.execute(probe).scalar_one_or_none() is None:
                raise ProviderQuotaCoordinatorError(
                    "provider quota coordinator health marker could not be locked"
                )
            connection.execute(select(func.count()).select_from(_windows)).scalar_one()
    except ProviderQuotaCoordinatorError:
        raise
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        raise ProviderQuotaCoordinatorError(
            "provider quota coordinator is unavailable; live provider calls are blocked"
        ) from None


def _current_contract_limit(
    *,
    provider_names: set[str],
    account_scope: str,
    quota_group: str,
    dimension_name: str,
    unit: str,
    reset: str,
    window_seconds: int,
    now: datetime,
) -> tuple[int | None, str]:
    """Resolve a current limit only when every provider sharing the bucket agrees."""

    from app.config import provider_rate_limit_seed
    from app.models.provider_runtime import ProviderCapability
    from app.services.provider_routing import quota_group_for_dimension

    if not provider_names:
        return None, "unknown"
    current_limits: set[int] = set()
    for name in provider_names:
        seed = provider_rate_limit_seed(name)
        contract = seed.get("quota_contract")
        if not isinstance(contract, dict):
            return None, "unknown"
        matches_for_provider: set[int] = set()
        for dimension in contract.get("dimensions") or []:
            if not isinstance(dimension, dict):
                continue
            if str(dimension.get("name") or "") != dimension_name:
                continue
            if str(dimension.get("unit") or "").strip().lower() != unit:
                continue
            if dimension.get("window_seconds") != window_seconds:
                continue
            dimension_reset = str(
                dimension.get("reset") or contract.get("reset") or ""
            ).strip()
            if dimension_reset != reset:
                continue
            scope = str(
                dimension.get("scope") or seed.get("quota_scope") or ""
            ).strip()
            if account_scope_for_provider(name, scope) != account_scope:
                continue
            if not any(
                quota_group_for_dimension(capability.value, dimension) == quota_group
                for capability in ProviderCapability
            ):
                continue
            limit = dimension.get("limit")
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                return None, "unknown"
            matches_for_provider.add(limit)
        if len(matches_for_provider) != 1:
            return None, "unknown" if not matches_for_provider else "ambiguous"
        current_limits.update(matches_for_provider)
    if len(current_limits) != 1:
        return None, "ambiguous"
    return next(iter(current_limits)), "verified"


def provider_quota_coordinator_summary(
    *, provider_name: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Return bounded account-scope, dimension, reservation and usage totals."""

    supplied_now = now or datetime.now(UTC)
    current = (
        supplied_now.replace(tzinfo=UTC)
        if supplied_now.tzinfo is None
        else supplied_now.astimezone(UTC)
    )
    try:
        engine = _engine_for(_engine_url())
        with engine.connect() as connection:
            query = select(_windows).where(_windows.c.window_started_at <= current)
            provider_window_keys: set[tuple] | None = None
            if provider_name:
                matching = connection.execute(
                    select(
                        _reservations.c.account_scope,
                        _reservations.c.quota_group,
                        _reservations.c.dimension,
                        _reservations.c.window_started_at,
                        _reservations.c.window_seconds,
                    ).where(_reservations.c.provider_name == provider_name)
                ).all()
                provider_window_keys = {
                    (scope, group, dimension, started, int(seconds))
                    for scope, group, dimension, started, seconds in matching
                }
            rows = connection.execute(
                query.order_by(
                    _windows.c.account_scope,
                    _windows.c.quota_group,
                    _windows.c.dimension,
                    _windows.c.window_started_at,
                )
            ).mappings().all()
            if provider_window_keys is not None:
                rows = [
                    row
                    for row in rows
                    if (
                        row["account_scope"],
                        row["quota_group"],
                        row["dimension"],
                        row["window_started_at"],
                        int(row["window_seconds"]),
                    )
                    in provider_window_keys
                ]
            providers_query = select(
                _reservations.c.provider_name,
                _reservations.c.account_scope,
                _reservations.c.quota_group,
                _reservations.c.dimension,
                _reservations.c.window_started_at,
                _reservations.c.window_seconds,
            ).distinct()
            provider_rows = connection.execute(providers_query).all()
            providers_by_key: dict[tuple, set[str]] = {}
            for name, scope, group, dimension, started, seconds in provider_rows:
                key = (scope, group, dimension, started, int(seconds))
                providers_by_key.setdefault(key, set()).add(str(name))
            latest_query = select(
                _reservations.c.account_scope,
                _reservations.c.quota_group,
                _reservations.c.dimension,
                _reservations.c.window_started_at,
                _reservations.c.window_seconds,
                _reservations.c.state,
                func.count().label("count"),
            ).where(
                _reservations.c.state.in_(["pending", "uncertain"])
            ).group_by(
                _reservations.c.account_scope,
                _reservations.c.quota_group,
                _reservations.c.dimension,
                _reservations.c.window_started_at,
                _reservations.c.window_seconds,
                _reservations.c.state,
            )
            pending = connection.execute(latest_query).mappings().all()
            baseline_rows = connection.execute(
                select(_baselines)
                .where(_baselines.c.reset != "unknown")
                .order_by(_baselines.c.observed_at.desc(), _baselines.c.id.desc())
                .limit(1000)
            ).mappings().all()
            receipt_query = select(
                _live_receipts.c.reconciliation_state,
                func.count().label("count"),
            )
            if provider_name:
                receipt_query = receipt_query.where(
                    _live_receipts.c.provider_name == provider_name
                )
            receipt_rows = connection.execute(
                receipt_query.group_by(_live_receipts.c.reconciliation_state)
            ).all()
        pending_by_key = {
            (
                row["account_scope"],
                row["quota_group"],
                row["dimension"],
                row["window_started_at"],
                int(row["window_seconds"]),
                row["state"],
            ): int(row["count"])
            for row in pending
        }
        providers_by_quota: dict[tuple, set[str]] = {}
        for name, scope, group, dimension, _started, seconds in provider_rows:
            key = (scope, group, dimension, int(seconds))
            providers_by_quota.setdefault(key, set()).add(str(name))

        active_baselines: dict[tuple, dict[str, Any]] = {}
        for row in baseline_rows:
            reset = str(row["reset"] or "")
            dimension = {"window_seconds": int(row["window_seconds"]), "reset": reset}
            current_start, rolling = _window_start(dimension, reset=reset, now=current)
            if bool(row["rolling"]) != rolling:
                continue
            if rolling:
                if _utc(row["observed_at"]) < _utc(
                    current - timedelta(seconds=int(row["window_seconds"]))
                ) or _utc(row["observed_at"]) > _utc(current):
                    continue
            elif _utc(row["window_started_at"]) != _utc(current_start):
                continue
            key = (
                row["account_scope"],
                row["quota_group"],
                row["dimension"],
                int(row["window_seconds"]),
            )
            if provider_name and provider_name != row["source_provider_name"]:
                if provider_name not in providers_by_quota.get(key, set()):
                    continue
            existing = active_baselines.get(key)
            if existing is not None and _utc(existing["observed_at"]) >= _utc(
                row["observed_at"]
            ):
                continue
            spec = {
                "provider_name": row["source_provider_name"],
                "account_scope": row["account_scope"],
                "quota_group": row["quota_group"],
                "dimension": row["dimension"],
                "unit": row["unit"],
                "reset": reset,
                "window_started_at": current_start,
                "window_seconds": int(row["window_seconds"]),
                "rolling": rolling,
                "limit_units": int(row["limit_units"]),
                "now": current,
            }
            current_limit, current_limit_status = _current_contract_limit(
                provider_names=set(providers_by_quota.get(key, set()))
                | {str(row["source_provider_name"])},
                account_scope=str(row["account_scope"]),
                quota_group=str(row["quota_group"]),
                dimension_name=str(row["dimension"]),
                unit=str(row["unit"]),
                reset=reset,
                window_seconds=int(row["window_seconds"]),
                now=current,
            )
            local_settled, reserved = _baseline_local_accounting(
                engine, spec, row, current
            )
            effective_used = int(row["used_units"]) + local_settled
            active_baselines[key] = {
                "provider": row["source_provider_name"],
                "account_scope": row["account_scope"],
                "quota_group": row["quota_group"],
                "dimension": row["dimension"],
                "unit": row["unit"],
                "window_started_at": _utc(row["window_started_at"]).replace(
                    tzinfo=UTC
                ).isoformat(),
                "window_seconds": int(row["window_seconds"]),
                "rolling": rolling,
                "limit_units": current_limit,
                "recorded_limit_units": int(row["limit_units"]),
                "limit_status": current_limit_status,
                "baseline_used_units": int(row["used_units"]),
                "local_settled_since_baseline_units": local_settled,
                "effective_used_units": effective_used,
                "reserved_units": reserved,
                "remaining_units": (
                    max(0, current_limit - effective_used - reserved)
                    if current_limit is not None
                    else None
                ),
                "observed_at": _utc(row["observed_at"]).replace(tzinfo=UTC).isoformat(),
                "source": row["source"],
                "evidence_reference": _safe_stored_evidence_reference(
                    row["evidence_reference"]
                ),
                "actor_user_id": row["actor_user_id"],
            }

        def count_pending(row, state: str) -> int:
            return pending_by_key.get(
                (
                    row["account_scope"],
                    row["quota_group"],
                    row["dimension"],
                    row["window_started_at"],
                    int(row["window_seconds"]),
                    state,
                ),
                0,
            )

        window_summaries = []
        for row in rows:
            baseline_key = (
                row["account_scope"],
                row["quota_group"],
                row["dimension"],
                int(row["window_seconds"]),
            )
            baseline = active_baselines.get(baseline_key)
            if baseline is not None:
                if baseline["rolling"]:
                    row_is_active = _utc(row["window_started_at"]) >= _utc(
                        current - timedelta(seconds=int(row["window_seconds"]))
                    )
                else:
                    row_is_active = _utc(row["window_started_at"]) == _utc(
                        datetime.fromisoformat(baseline["window_started_at"])
                    )
            else:
                row_is_active = False
            window_summaries.append(
                {
                    "provider": provider_name
                    or ",".join(
                        sorted(
                            providers_by_key.get(
                                (
                                    row["account_scope"],
                                    row["quota_group"],
                                    row["dimension"],
                                    row["window_started_at"],
                                    int(row["window_seconds"]),
                                ),
                                {"shared_account_scope"},
                            )
                        )
                    ),
                    "providers": sorted(
                        providers_by_key.get(
                            (
                                row["account_scope"],
                                row["quota_group"],
                                row["dimension"],
                                row["window_started_at"],
                                int(row["window_seconds"]),
                            ),
                            ({str(row["provider_name"])} if row["provider_name"] != _ACCOUNT_SCOPE_BUCKET else set()),
                        )
                    ),
                    "account_scope": row["account_scope"],
                    "quota_group": row["quota_group"],
                    "dimension": row["dimension"],
                    "window_started_at": row["window_started_at"].replace(tzinfo=UTC).isoformat(),
                    "window_seconds": int(row["window_seconds"]),
                    "limit_units": baseline["limit_units"]
                    if row_is_active and baseline is not None
                    else None,
                    "recorded_limit_units": int(row["limit_units"]),
                    "limit_status": baseline["limit_status"]
                    if row_is_active and baseline is not None
                    else "historical_or_unverified",
                    "reserved_units": int(row["reserved_units"]),
                    "consumed_units": int(row["consumed_units"]),
                    "baseline_used_units": baseline["baseline_used_units"]
                    if row_is_active
                    else None,
                    "local_settled_since_baseline_units": baseline[
                        "local_settled_since_baseline_units"
                    ]
                    if row_is_active
                    else None,
                    "effective_used_units": baseline["effective_used_units"]
                    if row_is_active
                    else int(row["consumed_units"]),
                    "active_reserved_units": baseline["reserved_units"]
                    if row_is_active
                    else int(row["reserved_units"]),
                    "remaining_units": baseline["remaining_units"]
                    if row_is_active and baseline is not None
                    else None,
                    "pending_reservations": count_pending(row, "pending"),
                    "uncertain_reservations": count_pending(row, "uncertain"),
                }
            )

        receipt_counts = {
            str(state): int(count) for state, count in receipt_rows
        }
        return {
            "available": True,
            "source": "durable provider quota coordinator",
            "as_of": current.replace(tzinfo=UTC).isoformat(),
            "windows": window_summaries,
            "baselines": list(active_baselines.values()),
            "live_receipts": {
                "total": sum(receipt_counts.values()),
                "reconciled": receipt_counts.get("reconciled", 0),
                "pending": receipt_counts.get("pending", 0),
                "uncertain": receipt_counts.get("uncertain", 0),
                "unresolved": receipt_counts.get("pending", 0)
                + receipt_counts.get("uncertain", 0),
            },
        }
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        return {
            "available": False,
            "source": "durable provider quota coordinator",
            "as_of": current.replace(tzinfo=UTC).isoformat(),
            "windows": [],
            "baselines": [],
            "live_receipts": {
                "total": 0,
                "reconciled": 0,
                "pending": 0,
                "uncertain": 0,
                "unresolved": 0,
            },
        }
