"""Store explicit provider adjustment factors when supplied."""

import sqlalchemy as sa

from alembic import op

revision = "ff2a3b4c5d6e"
down_revision = "ff1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("instrument_event")}
    if "adjustment_factor" not in event_columns:
        op.add_column(
            "instrument_event",
            sa.Column("adjustment_factor", sa.Numeric(precision=24, scale=12), nullable=True),
        )
    observation_columns = {
        column["name"] for column in inspector.get_columns("adjustment_factor_observation")
    }
    if "factor_kind" not in observation_columns:
        op.add_column(
            "adjustment_factor_observation",
            sa.Column("factor_kind", sa.String(length=24), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("adjustment_factor_observation", "factor_kind")
    op.drop_column("instrument_event", "adjustment_factor")
