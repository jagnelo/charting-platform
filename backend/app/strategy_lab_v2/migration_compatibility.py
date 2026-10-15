"""Read-only admission for historically colliding Alembic revision identifiers.

No revision is translated, stamped or inferred from a table name. Legacy
Strategy databases need a separately reviewed transition before upgrade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sqlalchemy as sa

from alembic.runtime.migration import MigrationContext

LEGACY_STRATEGY_REVISIONS = (
    "ff0a1b2c3d4e",
    "ff1a2b3c4d5e",
    "ff2a3b4c5d6e",
    "ff3a4b5c6d7e",
    "ff4a5b6c7d8e",
    "ff5a6b7c8d9e",
    "ff6a7b8c9d0e",
    "ff7a8b9c0d1e",
)
STRATEGY_REVISION_MAPPING = {
    revision: f"slv2_{index:04d}" for index, revision in enumerate(LEGACY_STRATEGY_REVISIONS, 1)
}

# These are upstream schema signatures, not copies of upstream migrations.
# Their original identifiers belong to those upstream scripts after integration.
_UPSTREAM_SIGNATURES: dict[str, tuple[str, dict[str, frozenset[str]]]] = {
    "ff0a1b2c3d4e": (
        "ff0a1b2c3d4e_add_ohlcv_derivation_provenance.py",
        {
            "ohlcv_bar": frozenset(
                {
                    "is_derived",
                    "source_timeframe",
                    "derivation_method",
                    "derived_at",
                    "source_bar_count",
                    "source_start",
                    "source_end",
                }
            )
        },
    ),
    "ff1a2b3c4d5e": (
        "ff1a2b3c4d5e_add_adjustment_factor_observations.py",
        {
            "adjustment_factor_observation": frozenset(
                {
                    "id",
                    "instrument_id",
                    "data_source_id",
                    "provider_symbol",
                    "factor_type",
                    "effective_at",
                    "factor",
                    "amount",
                    "source_event_key",
                    "observed_at",
                    "factor_version",
                    "raw_payload",
                    "created_at",
                    "updated_at",
                }
            )
        },
    ),
    "ff2a3b4c5d6e": (
        "ff2a3b4c5d6e_add_provider_adjustment_factor_fields.py",
        {
            "instrument_event": frozenset({"adjustment_factor"}),
            "adjustment_factor_observation": frozenset({"factor_kind"}),
        },
    ),
    "ff5a6b7c8d9e": (
        "ff5a6b7c8d9e_make_provider_limits_explicit.py",
        {
            "provider_policy": frozenset(
                {"quota_contract", "quota_scope", "quota_source", "quota_verified_at"}
            ),
            "provider_quota_window": frozenset({"dimension"}),
        },
    ),
}


class MigrationHistoryCompatibilityError(RuntimeError):
    """Upgrade refused before DDL; current version and all user data are intact."""


def assert_unambiguous_migration_history(connection: Any, scripts: Any) -> None:
    """Reject legacy Strategy, mixed, unknown and partial collision histories.

    A recognized upstream head is admitted only when its owning migration is
    installed, its distinguishing columns exist, and no Strategy tables exist.
    This is an admission check, never an automatic repair of applied revisions.
    """

    heads = MigrationContext.configure(connection).get_current_heads()
    legacy_heads = sorted(set(heads).intersection(LEGACY_STRATEGY_REVISIONS))
    if not legacy_heads:
        return
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    if any(name.startswith("strategy_lab_v2_") for name in tables):
        raise MigrationHistoryCompatibilityError(
            "Legacy Strategy or mixed migration history requires reviewed recovery; "
            "no schema or version changes were made. See the Strategy migration compatibility plan."
        )
    for revision in legacy_heads:
        signature = _UPSTREAM_SIGNATURES.get(revision)
        if signature is None:
            raise MigrationHistoryCompatibilityError(
                "Legacy Strategy revision requires reviewed recovery before upgrade."
            )
        filename, required = signature
        try:
            installed = scripts.get_revision(revision)
        except Exception as error:
            raise MigrationHistoryCompatibilityError(
                "Colliding revision has no installed upstream owner; upgrade refused."
            ) from error
        if installed is None or Path(installed.path).name != filename:
            raise MigrationHistoryCompatibilityError(
                "Colliding revision has an unexpected migration owner; upgrade refused."
            )
        for table, columns in required.items():
            if table not in tables or not columns.issubset(
                {column["name"] for column in inspector.get_columns(table)}
            ):
                raise MigrationHistoryCompatibilityError(
                    "Colliding revision has missing upstream schema evidence; upgrade refused."
                )
