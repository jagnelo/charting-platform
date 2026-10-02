"""Add effective/known/retired timestamps to provider symbol bindings."""

import sqlalchemy as sa

from alembic import op

revision: str = "fa1b2c3d4e5f"
down_revision: str | None = "e9f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "instrument_provider_symbol" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("instrument_provider_symbol")}
    for name in ("effective_at", "known_at", "retired_at"):
        if name not in columns:
            op.add_column(
                "instrument_provider_symbol",
                sa.Column(name, sa.DateTime(timezone=True), nullable=True),
            )

    indexes = {index["name"] for index in inspector.get_indexes("instrument_provider_symbol")}
    for name in ("effective_at", "known_at", "retired_at"):
        index_name = f"ix_instrument_provider_symbol_{name}"
        if index_name not in indexes:
            op.create_index(index_name, "instrument_provider_symbol", [name])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "instrument_provider_symbol" not in tables:
        return

    indexes = {index["name"] for index in inspector.get_indexes("instrument_provider_symbol")}
    for name in ("retired_at", "known_at", "effective_at"):
        index_name = f"ix_instrument_provider_symbol_{name}"
        if index_name in indexes:
            op.drop_index(index_name, table_name="instrument_provider_symbol")
    columns = {column["name"] for column in inspector.get_columns("instrument_provider_symbol")}
    for name in ("retired_at", "known_at", "effective_at"):
        if name in columns:
            op.drop_column("instrument_provider_symbol", name)
