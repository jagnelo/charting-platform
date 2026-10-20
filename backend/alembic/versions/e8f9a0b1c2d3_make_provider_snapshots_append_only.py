"""Allow repeated identical provider responses as append-only evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9a0b1c2e4"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS = (
    ("instrument_profile_snapshot", "uq_instrument_profile_snapshot_hash"),
    ("instrument_identifier_snapshot", "uq_instrument_identifier_snapshot_hash"),
    ("instrument_search_snapshot", "uq_instrument_search_snapshot_hash"),
    ("universe_discovery_snapshot", "uq_universe_discovery_snapshot_hash"),
    ("option_chain_snapshot", "uq_option_chain_snapshot_hash"),
)


def upgrade() -> None:
    for table_name, constraint_name in _CONSTRAINTS:
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(constraint_name, type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_queries = (
        (
            "instrument_profile_snapshot",
            "instrument_id, data_source_id, profile_hash",
        ),
        (
            "instrument_identifier_snapshot",
            "instrument_id, data_source_id, snapshot_hash",
        ),
        (
            "instrument_search_snapshot",
            "data_source_id, query, result_hash",
        ),
        (
            "universe_discovery_snapshot",
            "data_source_id, quote_type, offset, snapshot_hash",
        ),
        (
            "option_chain_snapshot",
            "underlying_instrument_id, data_source_id, expiration_date, snapshot_hash",
        ),
    )
    for table_name, columns in duplicate_queries:
        duplicate = bind.execute(
            sa.text(
                f"SELECT 1 FROM {table_name} GROUP BY {columns} HAVING COUNT(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError(
                f"refusing to downgrade: repeated provider evidence exists in {table_name}"
            )
    for table_name, constraint_name in reversed(_CONSTRAINTS):
        with op.batch_alter_table(table_name) as batch:
            if table_name == "instrument_profile_snapshot":
                columns = ["instrument_id", "data_source_id", "profile_hash"]
            elif table_name == "instrument_identifier_snapshot":
                columns = ["instrument_id", "data_source_id", "snapshot_hash"]
            elif table_name == "instrument_search_snapshot":
                columns = ["data_source_id", "query", "result_hash"]
            elif table_name == "universe_discovery_snapshot":
                columns = ["data_source_id", "quote_type", "offset", "snapshot_hash"]
            else:
                columns = [
                    "underlying_instrument_id",
                    "data_source_id",
                    "expiration_date",
                    "snapshot_hash",
                ]
            batch.create_unique_constraint(constraint_name, columns)
