"""Add provider entitlement and terms governance."""

import sqlalchemy as sa

from alembic import op

revision: str = "d2a3b4c5d6e7"
down_revision: str | None = "d1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_entitlement",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column(
            "capability",
            sa.Enum(
                "INSTRUMENT_SEARCH",
                "INSTRUMENT_METADATA",
                "PRICE_HISTORY",
                "LATEST_PRICE",
                "INSTRUMENT_EVENTS",
                "INSTRUMENT_IDENTIFIERS",
                "UNIVERSE_DISCOVERY",
                "OPTION_CHAIN",
                "OPTION_QUOTE_HISTORY",
                name="providercapability",
            ),
            nullable=False,
        ),
        sa.Column("configured_plan", sa.String(length=80), nullable=False),
        sa.Column("is_free", sa.Boolean(), nullable=False),
        sa.Column("authentication_required", sa.Boolean(), nullable=False),
        sa.Column("usage_terms", sa.Text(), nullable=True),
        sa.Column("redistribution_allowed", sa.Boolean(), nullable=False),
        sa.Column("quota_policy", sa.JSON(), nullable=False),
        sa.Column("history_depth", sa.String(length=160), nullable=True),
        sa.Column("venue_coverage", sa.String(length=160), nullable=True),
        sa.Column("freshness_semantics", sa.String(length=160), nullable=True),
        sa.Column("enabled_environments", sa.JSON(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("live_probe_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id", "capability", name="uq_provider_entitlement_source_capability"
        ),
    )
    op.create_index(
        "ix_provider_entitlement_data_source_id", "provider_entitlement", ["data_source_id"]
    )
    op.create_index("ix_provider_entitlement_capability", "provider_entitlement", ["capability"])


def downgrade() -> None:
    op.drop_index("ix_provider_entitlement_capability", table_name="provider_entitlement")
    op.drop_index("ix_provider_entitlement_data_source_id", table_name="provider_entitlement")
    op.drop_table("provider_entitlement")
