"""Widen provider entitlement description fields without truncation."""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


_TABLES = ("provider_entitlement", "provider_entitlement_revision")
_COLUMNS = ("history_depth", "venue_coverage", "freshness_semantics")
_PREVIOUS_MAX_LENGTH = 160


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            for column in _COLUMNS:
                batch.alter_column(
                    column,
                    existing_type=sa.String(length=_PREVIOUS_MAX_LENGTH),
                    type_=sa.Text(),
                )


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        for column in _COLUMNS:
            too_long = bind.execute(
                sa.text(f"SELECT 1 FROM {table} WHERE length({column}) > :max_length LIMIT 1"),
                {"max_length": _PREVIOUS_MAX_LENGTH},
            ).first()
            if too_long:
                raise RuntimeError(
                    f"Cannot narrow {table}.{column}; values exceed "
                    f"{_PREVIOUS_MAX_LENGTH} characters"
                )

    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            for column in _COLUMNS:
                batch.alter_column(
                    column,
                    existing_type=sa.Text(),
                    type_=sa.String(length=_PREVIOUS_MAX_LENGTH),
                )
