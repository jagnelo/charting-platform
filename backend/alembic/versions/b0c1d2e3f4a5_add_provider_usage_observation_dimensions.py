"""Name provider-native account usage observation dimensions."""

import sqlalchemy as sa

from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_account_usage_observation",
        sa.Column("dimension", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "provider_account_usage_observation",
        sa.Column("account_plan", sa.String(length=80), nullable=True),
    )
    op.execute(
        "UPDATE provider_account_usage_observation "
        "SET dimension = 'default' WHERE dimension IS NULL"
    )
    with op.batch_alter_table("provider_account_usage_observation") as batch:
        batch.alter_column(
            "dimension",
            existing_type=sa.String(length=80),
            nullable=False,
            server_default="default",
        )
    op.create_index(
        "ix_provider_account_usage_observation_dimension",
        "provider_account_usage_observation",
        ["dimension"],
    )
    op.create_index(
        "ix_provider_account_usage_source_dimension_observed",
        "provider_account_usage_observation",
        ["data_source_id", "dimension", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_account_usage_source_dimension_observed",
        table_name="provider_account_usage_observation",
    )
    op.drop_index(
        "ix_provider_account_usage_observation_dimension",
        table_name="provider_account_usage_observation",
    )
    op.drop_column("provider_account_usage_observation", "dimension")
    op.drop_column("provider_account_usage_observation", "account_plan")
