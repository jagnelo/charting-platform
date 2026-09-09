"""Track provider quotas metered by distinct identities."""

import sqlalchemy as sa

from alembic import op

revision = "2d3e4f5a6b7c"
down_revision = "1c2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_quota_identity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("dimension", sa.String(length=80), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("identity_key", sa.String(length=180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "capability",
            "dimension",
            "window_started_at",
            "window_seconds",
            "identity_key",
            name="uq_provider_quota_identity",
        ),
    )
    op.create_index(
        "ix_provider_quota_identity_data_source_id",
        "provider_quota_identity",
        ["data_source_id"],
    )
    op.create_index(
        "ix_provider_quota_identity_capability",
        "provider_quota_identity",
        ["capability"],
    )
    op.create_index(
        "ix_provider_quota_identity_lookup",
        "provider_quota_identity",
        ["data_source_id", "capability", "dimension", "window_started_at", "window_seconds"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_quota_identity_lookup", table_name="provider_quota_identity")
    op.drop_index("ix_provider_quota_identity_capability", table_name="provider_quota_identity")
    op.drop_index("ix_provider_quota_identity_data_source_id", table_name="provider_quota_identity")
    op.drop_table("provider_quota_identity")
