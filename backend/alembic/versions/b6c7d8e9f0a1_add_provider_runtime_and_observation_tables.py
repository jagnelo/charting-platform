"""add provider runtime and observation tables

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-04-23 11:30:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
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

dataset_status = postgresql.ENUM(
    "FRESH",
    "STALE",
    "PENDING",
    "FAILED",
    name="datasetstatus",
    create_type=False,
)

timeframe_enum = postgresql.ENUM(
    "M1", "M5", "M15", "M30", "H1", "H2", "H4", "H12", "D1", "W1", "MN",
    name="timeframe",
    create_type=False,
)


def _create_enum_if_missing(name: str, values: tuple[str, ...]) -> None:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"""
        DO $$
        BEGIN
            BEGIN
                EXECUTE format($ddl$CREATE TYPE %I AS ENUM ({quoted_values})$ddl$, '{name}');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END;
        END
        $$;
        """
    )


def upgrade() -> None:
    _create_enum_if_missing(
        "providercapability",
        (
            "INSTRUMENT_SEARCH",
            "INSTRUMENT_METADATA",
            "PRICE_HISTORY",
            "LATEST_PRICE",
            "INSTRUMENT_EVENTS",
            "INSTRUMENT_IDENTIFIERS",
            "UNIVERSE_DISCOVERY",
            "OPTION_CHAIN",
            "OPTION_QUOTE_HISTORY",
        ),
    )
    _create_enum_if_missing("datasetstatus", ("FRESH", "STALE", "PENDING", "FAILED"))

    op.add_column("option_detail", sa.Column("contract_key", sa.String(length=160), nullable=True))
    op.add_column("option_detail", sa.Column("venue_code", sa.String(length=30), nullable=True))
    op.add_column("option_detail", sa.Column("rho", sa.Numeric(precision=10, scale=6), nullable=True))
    op.create_index(op.f("ix_option_detail_contract_key"), "option_detail", ["contract_key"], unique=True)

    op.create_table(
        "provider_policy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_weight_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("base_priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("tokens_per_minute", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("burst_capacity", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("freshness_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("score_floor", sa.Numeric(precision=10, scale=4), nullable=False, server_default="0"),
        sa.Column("score_ceiling", sa.Numeric(precision=10, scale=4), nullable=False, server_default="100"),
        sa.Column("learned_weight", sa.Numeric(precision=10, scale=4), nullable=False, server_default="0"),
        sa.Column("effective_score", sa.Numeric(precision=10, scale=4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "capability", name="uq_provider_policy_source_capability"),
    )
    op.create_index(
        "ix_provider_policy_capability_rank",
        "provider_policy",
        ["capability", "is_enabled", "is_pinned", "effective_score", "base_priority"],
        unique=False,
    )

    op.create_table(
        "provider_health_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("failure_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ewma_latency_ms", sa.Numeric(precision=12, scale=4), nullable=False, server_default="0"),
        sa.Column("ewma_success_rate", sa.Numeric(precision=12, scale=6), nullable=False, server_default="1"),
        sa.Column("ewma_completeness", sa.Numeric(precision=12, scale=6), nullable=False, server_default="1"),
        sa.Column("ewma_freshness", sa.Numeric(precision=12, scale=6), nullable=False, server_default="1"),
        sa.Column("ewma_consistency", sa.Numeric(precision=12, scale=6), nullable=False, server_default="1"),
        sa.Column("observed_score", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column("last_error_type", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id", "capability", name="uq_provider_health_state_source_capability"
        ),
    )

    op.create_table(
        "provider_request_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("capability", provider_capability, nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("response_items", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_request_log_capability_requested",
        "provider_request_log",
        ["capability", "requested_at"],
        unique=False,
    )

    op.create_table(
        "instrument_dataset_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("dataset_type", sa.String(length=40), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", dataset_status, nullable=False, server_default="PENDING"),
        sa.Column("coverage_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coverage_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot_hash", sa.String(length=80), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "dataset_type",
            "dataset_key",
            name="uq_instrument_dataset_state",
        ),
    )

    op.create_table(
        "instrument_profile_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile_hash", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "profile_hash",
            name="uq_instrument_profile_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_instrument_profile_snapshot_inst_source_observed",
        "instrument_profile_snapshot",
        ["instrument_id", "data_source_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "market_bar_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("timeframe", timeframe_enum, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=30, scale=4), nullable=True),
        sa.Column("vwap", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("is_adjusted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "timeframe",
            "ts",
            "is_adjusted",
            name="uq_market_bar_observation",
        ),
    )

    op.create_table(
        "option_chain_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("underlying_instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["underlying_instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "underlying_instrument_id",
            "data_source_id",
            "expiration_date",
            "snapshot_hash",
            name="uq_option_chain_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_option_chain_snapshot_underlying_exp_observed",
        "option_chain_snapshot",
        ["underlying_instrument_id", "expiration_date", "observed_at"],
        unique=False,
    )

    op.create_table(
        "option_quote_point",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("option_instrument_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bid", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("ask", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("mark", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("last", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("volume", sa.Numeric(precision=30, scale=4), nullable=True),
        sa.Column("open_interest", sa.Numeric(precision=30, scale=4), nullable=True),
        sa.Column("implied_vol", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("delta", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("gamma", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("theta", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("vega", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("rho", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("extra_greeks", sa.JSON(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("observation_hash", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["option_instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["option_chain_snapshot.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "option_instrument_id",
            "data_source_id",
            "observed_at",
            name="uq_option_quote_point_observed",
        ),
    )
    op.create_index(
        "ix_option_quote_point_option_observed",
        "option_quote_point",
        ["option_instrument_id", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_option_quote_point_option_observed", table_name="option_quote_point")
    op.drop_table("option_quote_point")

    op.drop_index(
        "ix_option_chain_snapshot_underlying_exp_observed", table_name="option_chain_snapshot"
    )
    op.drop_table("option_chain_snapshot")

    op.drop_table("market_bar_observation")

    op.drop_index(
        "ix_instrument_profile_snapshot_inst_source_observed",
        table_name="instrument_profile_snapshot",
    )
    op.drop_table("instrument_profile_snapshot")

    op.drop_table("instrument_dataset_state")

    op.drop_index("ix_provider_request_log_capability_requested", table_name="provider_request_log")
    op.drop_table("provider_request_log")

    op.drop_table("provider_health_state")

    op.drop_index("ix_provider_policy_capability_rank", table_name="provider_policy")
    op.drop_table("provider_policy")

    op.drop_index(op.f("ix_option_detail_contract_key"), table_name="option_detail")
    op.drop_column("option_detail", "rho")
    op.drop_column("option_detail", "venue_code")
    op.drop_column("option_detail", "contract_key")

    dataset_status.drop(op.get_bind(), checkfirst=True)
    provider_capability.drop(op.get_bind(), checkfirst=True)
