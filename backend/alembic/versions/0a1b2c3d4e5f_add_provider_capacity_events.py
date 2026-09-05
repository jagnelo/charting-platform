"""Persist typed provider capacity and quota rejection events."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0a1b2c3d4e5f"
down_revision = "ff5a6b7c8d9e"
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
    "CORPORATE_ACTIONS",
    "EARNINGS",
    "FUNDAMENTALS",
    "SHORT_INTEREST",
    "MARKET_CALENDAR",
    "FUTURES_HISTORY",
    "CRYPTO_HISTORY",
    "OPTIONS_CURRENT",
    "MARKET_EVENTS",
    name="providercapability",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "provider_capacity_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column(
            "error_type",
            sa.String(length=80),
            nullable=False,
            server_default="ProviderRateLimitError",
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "response_headers",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_log_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_log_id"], ["provider_request_log.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_capacity_event_data_source_id",
        "provider_capacity_event",
        ["data_source_id"],
    )
    op.create_index(
        "ix_provider_capacity_event_capability",
        "provider_capacity_event",
        ["capability"],
    )
    op.create_index(
        "ix_provider_capacity_event_retry_at",
        "provider_capacity_event",
        ["retry_at"],
    )
    op.create_index(
        "ix_provider_capacity_event_observed_at",
        "provider_capacity_event",
        ["observed_at"],
    )
    op.create_index(
        "ix_provider_capacity_event_request_log_id",
        "provider_capacity_event",
        ["request_log_id"],
    )
    op.create_index(
        "ix_provider_capacity_event_source_observed",
        "provider_capacity_event",
        ["data_source_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_capacity_event_source_observed", table_name="provider_capacity_event")
    op.drop_index("ix_provider_capacity_event_request_log_id", table_name="provider_capacity_event")
    op.drop_index("ix_provider_capacity_event_observed_at", table_name="provider_capacity_event")
    op.drop_index("ix_provider_capacity_event_retry_at", table_name="provider_capacity_event")
    op.drop_index("ix_provider_capacity_event_capability", table_name="provider_capacity_event")
    op.drop_index("ix_provider_capacity_event_data_source_id", table_name="provider_capacity_event")
    op.drop_table("provider_capacity_event")
