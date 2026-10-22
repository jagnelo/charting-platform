"""Persist normalized provider adjustment-factor observations."""

import sqlalchemy as sa

from alembic import op

revision = "ff1a2b3c4d5e"
down_revision = "ff0a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "adjustment_factor_observation" in inspector.get_table_names():
        return

    op.create_table(
        "adjustment_factor_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("factor_type", sa.String(length=24), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("factor", sa.Numeric(precision=24, scale=12), nullable=True),
        sa.Column("amount", sa.Numeric(precision=24, scale=12), nullable=True),
        sa.Column("source_event_key", sa.String(length=240), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("factor_version", sa.String(length=80), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "factor_type",
            "effective_at",
            "source_event_key",
            name="uq_adjustment_factor_observation",
        ),
    )
    op.create_index(
        "ix_adjustment_factor_observation_instrument_id",
        "adjustment_factor_observation",
        ["instrument_id"],
    )
    op.create_index(
        "ix_adjustment_factor_observation_data_source_id",
        "adjustment_factor_observation",
        ["data_source_id"],
    )
    op.create_index(
        "ix_adjustment_factor_observation_instrument_effective",
        "adjustment_factor_observation",
        ["instrument_id", "effective_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_adjustment_factor_observation_instrument_effective",
        table_name="adjustment_factor_observation",
    )
    op.drop_index(
        "ix_adjustment_factor_observation_data_source_id",
        table_name="adjustment_factor_observation",
    )
    op.drop_index(
        "ix_adjustment_factor_observation_instrument_id",
        table_name="adjustment_factor_observation",
    )
    op.drop_table("adjustment_factor_observation")
