"""Make provider quota contracts explicit and support multiple dimensions."""

import sqlalchemy as sa

from alembic import op

revision = "ff5a6b7c8d9e"
down_revision = "4d5e6f708192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("provider_policy") as batch:
        batch.alter_column("max_concurrency", existing_type=sa.Integer(), nullable=True, server_default=None)
        batch.alter_column("tokens_per_minute", existing_type=sa.Integer(), nullable=True, server_default=None)
        batch.alter_column("burst_capacity", existing_type=sa.Integer(), nullable=True, server_default=None)
        batch.alter_column("cooldown_seconds", existing_type=sa.Integer(), nullable=True, server_default=None)
        batch.add_column(sa.Column("quota_contract", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("quota_scope", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("quota_source", sa.String(length=240), nullable=True))
        batch.add_column(sa.Column("quota_verified_at", sa.DateTime(timezone=True), nullable=True))

    # Values created by the old implementation were one-size-fits-all
    # fallbacks, not provider evidence.  Remove them instead of silently
    # carrying unsafe assumptions through an upgrade.
    op.execute(
        "UPDATE provider_policy SET max_concurrency = NULL, tokens_per_minute = NULL, "
        "burst_capacity = NULL, cooldown_seconds = NULL "
        "WHERE quota_source IS NULL"
    )

    with op.batch_alter_table("provider_quota_window") as batch:
        batch.add_column(
            sa.Column("dimension", sa.String(length=80), nullable=False, server_default="default")
        )
        batch.drop_constraint("uq_provider_quota_window", type_="unique")
        batch.create_unique_constraint(
            "uq_provider_quota_window",
            ["data_source_id", "capability", "dimension", "window_started_at", "window_seconds"],
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_quota_window") as batch:
        batch.drop_constraint("uq_provider_quota_window", type_="unique")
        batch.create_unique_constraint(
            "uq_provider_quota_window",
            ["data_source_id", "capability", "window_started_at", "window_seconds"],
        )
        batch.drop_column("dimension")
    with op.batch_alter_table("provider_policy") as batch:
        batch.drop_column("quota_verified_at")
        batch.drop_column("quota_source")
        batch.drop_column("quota_scope")
        batch.drop_column("quota_contract")
        batch.alter_column("max_concurrency", existing_type=sa.Integer(), nullable=False, server_default="2")
        batch.alter_column("tokens_per_minute", existing_type=sa.Integer(), nullable=False, server_default="60")
        batch.alter_column("burst_capacity", existing_type=sa.Integer(), nullable=False, server_default="15")
        batch.alter_column("cooldown_seconds", existing_type=sa.Integer(), nullable=False, server_default="30")
