"""Retain append-only provider entitlement revisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "eb1f2a3c4d5e"
branch_labels = None
depends_on = None

provider_capability = postgresql.ENUM(
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
    create_type=False,
)


def upgrade() -> None:
    op.add_column(
        "provider_entitlement",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "provider_entitlement_revision",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
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
        sa.Column("change_reason", sa.String(length=240), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "capability",
            "revision",
            name="uq_provider_entitlement_revision_source_capability_revision",
        ),
    )
    op.create_index(
        "ix_provider_entitlement_revision_data_source_id",
        "provider_entitlement_revision",
        ["data_source_id"],
    )
    op.create_index(
        "ix_provider_entitlement_revision_capability",
        "provider_entitlement_revision",
        ["capability"],
    )
    op.create_index(
        "ix_provider_entitlement_revision_lookup",
        "provider_entitlement_revision",
        ["data_source_id", "capability", "revision"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_entitlement_revision_lookup", table_name="provider_entitlement_revision")
    op.drop_index("ix_provider_entitlement_revision_capability", table_name="provider_entitlement_revision")
    op.drop_index(
        "ix_provider_entitlement_revision_data_source_id", table_name="provider_entitlement_revision"
    )
    op.drop_table("provider_entitlement_revision")
    op.drop_column("provider_entitlement", "revision")
