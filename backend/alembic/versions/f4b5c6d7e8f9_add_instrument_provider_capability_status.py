"""add instrument provider capability status

Revision ID: f4b5c6d7e8f9
Revises: e2f3a4b5c6d7
Create Date: 2026-04-28 11:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f4b5c6d7e8f9"
down_revision = "e2f3a4b5c6d7"
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
    bind = op.get_bind()
    provider_capability.create(bind, checkfirst=True)

    op.create_table(
        "instrument_provider_capability_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("support_status", sa.String(length=16), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "capability",
            name="uq_instrument_provider_capability_status",
        ),
    )
    op.create_index(
        "ix_instrument_provider_capability_status_inst_cap",
        "instrument_provider_capability_status",
        ["instrument_id", "capability"],
        unique=False,
    )
    op.create_index(
        "ix_instrument_provider_capability_status_expires",
        "instrument_provider_capability_status",
        ["status_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instrument_provider_capability_status_expires",
        table_name="instrument_provider_capability_status",
    )
    op.drop_index(
        "ix_instrument_provider_capability_status_inst_cap",
        table_name="instrument_provider_capability_status",
    )
    op.drop_table("instrument_provider_capability_status")
