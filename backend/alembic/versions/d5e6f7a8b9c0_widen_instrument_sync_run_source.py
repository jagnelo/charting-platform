"""Widen instrument_sync_run.source so long provider chains fit."""

import sqlalchemy as sa

from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "a7c3e5f9b2d4"
branch_labels = None
depends_on = None

_TABLE = "instrument_sync_run"
_PREVIOUS_MAX_LENGTH = 50


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            "source",
            existing_type=sa.String(length=_PREVIOUS_MAX_LENGTH),
            type_=sa.String(length=255),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    too_long = bind.execute(
        sa.text(f"SELECT 1 FROM {_TABLE} WHERE length(source) > :max_length LIMIT 1"),
        {"max_length": _PREVIOUS_MAX_LENGTH},
    ).first()
    if too_long:
        raise RuntimeError(
            f"Cannot narrow {_TABLE}.source; values exceed {_PREVIOUS_MAX_LENGTH} characters"
        )
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            "source",
            existing_type=sa.String(length=255),
            type_=sa.String(length=_PREVIOUS_MAX_LENGTH),
            existing_nullable=False,
        )
