"""Add explicit provider quota groups shared across capabilities."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7d8e9f0a1b2c"
down_revision: str | None = "6c7d8e9f0a1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_and_require(table_name: str) -> None:
    """Preserve legacy capability buckets before requiring the new key."""

    op.execute(
        sa.text(
            f"UPDATE {table_name} SET quota_group = capability "
            "WHERE quota_group IS NULL OR TRIM(quota_group) = ''"
        )
    )
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column(
            "quota_group",
            existing_type=sa.String(length=80),
            nullable=False,
        )


def upgrade() -> None:
    # Nullable additions make this safe for existing installations; the
    # backfill below turns every pre-group row into its legacy capability
    # bucket before the new unique keys are installed.
    # The identity table already has a capability-keyed lookup index from its
    # original migration. Replace it after the key changes so the index name
    # remains stable for existing admin/diagnostic queries.
    op.drop_index("ix_provider_quota_identity_lookup", table_name="provider_quota_identity")

    with op.batch_alter_table("provider_quota_window") as batch:
        batch.add_column(sa.Column("quota_group", sa.String(length=80), nullable=True))
        batch.drop_constraint("uq_provider_quota_window", type_="unique")

    with op.batch_alter_table("provider_quota_identity") as batch:
        batch.add_column(sa.Column("quota_group", sa.String(length=80), nullable=True))
        batch.drop_constraint("uq_provider_quota_identity", type_="unique")

    _backfill_and_require("provider_quota_window")
    _backfill_and_require("provider_quota_identity")

    with op.batch_alter_table("provider_quota_window") as batch:
        batch.create_unique_constraint(
            "uq_provider_quota_window",
            [
                "data_source_id",
                "quota_group",
                "dimension",
                "window_started_at",
                "window_seconds",
            ],
        )
    op.create_index(
        "ix_provider_quota_window_quota_group",
        "provider_quota_window",
        ["quota_group"],
    )
    with op.batch_alter_table("provider_quota_identity") as batch:
        batch.create_unique_constraint(
            "uq_provider_quota_identity",
            [
                "data_source_id",
                "quota_group",
                "dimension",
                "window_started_at",
                "window_seconds",
                "identity_key",
            ],
        )
    op.create_index(
        "ix_provider_quota_identity_quota_group",
        "provider_quota_identity",
        ["quota_group"],
    )
    op.create_index(
        "ix_provider_quota_identity_lookup",
        "provider_quota_identity",
        [
            "data_source_id",
            "quota_group",
            "dimension",
            "window_started_at",
            "window_seconds",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_quota_identity_lookup", table_name="provider_quota_identity"
    )
    op.drop_index(
        "ix_provider_quota_identity_quota_group", table_name="provider_quota_identity"
    )
    with op.batch_alter_table("provider_quota_identity") as batch:
        batch.drop_constraint("uq_provider_quota_identity", type_="unique")
        batch.create_unique_constraint(
            "uq_provider_quota_identity",
            [
                "data_source_id",
                "capability",
                "dimension",
                "window_started_at",
                "window_seconds",
                "identity_key",
            ],
        )
        batch.drop_column("quota_group")
    op.create_index(
        "ix_provider_quota_identity_lookup",
        "provider_quota_identity",
        ["data_source_id", "capability", "dimension", "window_started_at", "window_seconds"],
    )

    op.drop_index("ix_provider_quota_window_quota_group", table_name="provider_quota_window")
    with op.batch_alter_table("provider_quota_window") as batch:
        batch.drop_constraint("uq_provider_quota_window", type_="unique")
        batch.create_unique_constraint(
            "uq_provider_quota_window",
            ["data_source_id", "capability", "dimension", "window_started_at", "window_seconds"],
        )
        batch.drop_column("quota_group")
