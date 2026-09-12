"""Persist provider-native account usage observations."""

import sqlalchemy as sa
from alembic import op


revision = "4e5f6a7b8c9d"
down_revision = "3e4f5a6b7c8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN ALTER TYPE providercapability "
            "ADD VALUE IF NOT EXISTS 'ACCOUNT_USAGE'; "
            "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
        )
    op.create_table(
        "provider_account_usage_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.Column("remaining", sa.Integer(), nullable=True),
        sa.Column("consumed", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("options_data_permissions", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_account_usage_observation_data_source_id",
        "provider_account_usage_observation",
        ["data_source_id"],
    )
    op.create_index(
        "ix_provider_account_usage_observation_observed_at",
        "provider_account_usage_observation",
        ["observed_at"],
    )
    op.create_index(
        "ix_provider_account_usage_source_observed",
        "provider_account_usage_observation",
        ["data_source_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_account_usage_source_observed",
        table_name="provider_account_usage_observation",
    )
    op.drop_index(
        "ix_provider_account_usage_observation_observed_at",
        table_name="provider_account_usage_observation",
    )
    op.drop_index(
        "ix_provider_account_usage_observation_data_source_id",
        table_name="provider_account_usage_observation",
    )
    op.drop_table("provider_account_usage_observation")
    # PostgreSQL enum values are intentionally not removed; removing a value
    # is unsafe once observations may reference the capability.
