"""Persist daily and weekly provider availability observations."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "fd3e4f5a6b7c"
down_revision = "fc2d3e4f5a6b"
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
    op.create_table(
        "provider_availability_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("application_version", sa.String(80), nullable=False),
        sa.Column("probe_contract_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_provider_availability_run_mode", "provider_availability_run", ["mode"])
    op.create_table(
        "provider_availability_observation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("provider_availability_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "data_source_id",
            sa.Integer(),
            sa.ForeignKey("data_source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("representative_request", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("classification", sa.String(48), nullable=False),
        sa.Column("response_shape", sa.JSON(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_provider_availability_observation_run_id",
        "provider_availability_observation",
        ["run_id"],
    )
    op.create_index(
        "ix_provider_availability_observation_data_source_id",
        "provider_availability_observation",
        ["data_source_id"],
    )
    op.create_index(
        "ix_provider_availability_observation_capability",
        "provider_availability_observation",
        ["capability"],
    )
    op.create_index(
        "ix_provider_availability_observation_source_capability",
        "provider_availability_observation",
        ["data_source_id", "capability"],
    )
    op.create_index(
        "ix_provider_availability_observation_classification",
        "provider_availability_observation",
        ["classification"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_availability_observation_classification",
        table_name="provider_availability_observation",
    )
    op.drop_index(
        "ix_provider_availability_observation_source_capability",
        table_name="provider_availability_observation",
    )
    op.drop_index(
        "ix_provider_availability_observation_capability",
        table_name="provider_availability_observation",
    )
    op.drop_index(
        "ix_provider_availability_observation_data_source_id",
        table_name="provider_availability_observation",
    )
    op.drop_index(
        "ix_provider_availability_observation_run_id",
        table_name="provider_availability_observation",
    )
    op.drop_table("provider_availability_observation")
    op.drop_index("ix_provider_availability_run_mode", table_name="provider_availability_run")
    op.drop_table("provider_availability_run")
