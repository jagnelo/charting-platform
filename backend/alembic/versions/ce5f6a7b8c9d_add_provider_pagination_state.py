"""Add durable continuation state for provider-wide paginated refreshes."""

import sqlalchemy as sa

from alembic import op

revision = "ce5f6a7b8c9d"
down_revision = "cd4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_pagination_state",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("state_key", sa.String(length=240), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("page_size", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("pages_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("cursor_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_key", name="uq_provider_pagination_state_key"),
    )
    op.create_index(
        "ix_provider_pagination_state_state_key",
        "provider_pagination_state",
        ["state_key"],
        unique=False,
    )
    op.create_index(
        "ix_provider_pagination_state_provider",
        "provider_pagination_state",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_provider_pagination_state_capability",
        "provider_pagination_state",
        ["capability"],
        unique=False,
    )
    op.create_index(
        "ix_provider_pagination_provider_capability",
        "provider_pagination_state",
        ["provider", "capability"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_provider_pagination_provider_capability", table_name="provider_pagination_state")
    op.drop_index("ix_provider_pagination_state_capability", table_name="provider_pagination_state")
    op.drop_index("ix_provider_pagination_state_provider", table_name="provider_pagination_state")
    op.drop_index("ix_provider_pagination_state_state_key", table_name="provider_pagination_state")
    op.drop_table("provider_pagination_state")
