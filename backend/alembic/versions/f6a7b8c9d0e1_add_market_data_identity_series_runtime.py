"""add stable market-data identity, scoped series, calendars, and runtime telemetry

Revision ID: 1a2b3c4d5e6f
Revises: fe4f5a6b7c8d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "1a2b3c4d5e6f"
down_revision: str | None = "fe4f5a6b7c8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_enum_values(type_name: str, values: tuple[str, ...]) -> None:
    for value in values:
        escaped = value.replace("'", "''")
        op.execute(
            sa.text(
                f"DO $$ BEGIN ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{escaped}'; "
                "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
            )
        )


def _enum(name: str, *values: str) -> postgresql.ENUM:
    # Types are created explicitly above so repeated migration/test runs do not
    # race SQLAlchemy's table-level CREATE TYPE hook.
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    _add_enum_values(
        "providercapability",
        (
            "CORPORATE_ACTIONS",
            "EARNINGS",
            "FUNDAMENTALS",
            "SHORT_INTEREST",
            "MARKET_CALENDAR",
            "FUTURES_HISTORY",
            "CRYPTO_HISTORY",
            "OPTIONS_CURRENT",
            "MARKET_EVENTS",
        ),
    )
    _add_enum_values("instrumentidentifiertype", ("CIK",))

    adjustment_basis = _enum(
        "adjustmentbasis", "RAW", "SPLIT_ADJUSTED", "TOTAL_RETURN", "PROVIDER_ADJUSTED"
    )
    calendar_exception_kind = _enum(
        "calendarexceptionkind", "HOLIDAY", "EARLY_CLOSE", "LATE_OPEN", "CLOSED"
    )
    bind = op.get_bind()
    adjustment_basis.create(bind, checkfirst=True)
    calendar_exception_kind.create(bind, checkfirst=True)

    op.create_table(
        "issuer",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("domain_key", sa.String(length=120), nullable=False),
        sa.Column("legal_name", sa.String(length=300), nullable=False),
        sa.Column("cik", sa.String(length=20), nullable=True),
        sa.Column("lei", sa.String(length=30), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issuer_domain_key", "issuer", ["domain_key"], unique=True)
    op.create_index("ix_issuer_cik", "issuer", ["cik"], unique=True)
    op.create_index("ix_issuer_lei", "issuer", ["lei"], unique=True)

    op.add_column("instrument", sa.Column("domain_key", sa.String(length=120), nullable=True))
    op.add_column("instrument", sa.Column("identity_status", sa.String(length=24), nullable=False, server_default="provisional"))
    op.add_column("instrument", sa.Column("issuer_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_instrument_domain_key", "instrument", ["domain_key"], unique=True)
    op.create_index("ix_instrument_issuer_id", "instrument", ["issuer_id"])
    op.create_foreign_key("fk_instrument_issuer", "instrument", "issuer", ["issuer_id"], ["id"], ondelete="SET NULL")

    op.add_column("instrument_identifier", sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instrument_identifier", sa.Column("known_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instrument_identifier", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instrument_listing", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instrument_listing", sa.Column("source", sa.String(length=80), nullable=True))
    op.add_column("instrument_listing", sa.Column("provenance", sa.JSON(), nullable=True))

    op.create_table(
        "exchange_session_rule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=False),
        sa.Column("session_code", sa.String(length=24), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
        sa.Column("crosses_midnight", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trade_date_rule", sa.String(length=32), nullable=False, server_default="local_open_date"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchange.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_id", "session_code", "weekday", "valid_from", name="uq_exchange_session_rule_version"),
    )
    op.create_index("ix_exchange_session_rule_exchange_id", "exchange_session_rule", ["exchange_id"])
    op.create_index("ix_exchange_session_rule_lookup", "exchange_session_rule", ["exchange_id", "session_code", "valid_from"])
    op.create_table(
        "exchange_calendar_exception",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("exception_kind", calendar_exception_kind, nullable=False),
        sa.Column("session_code", sa.String(length=24), nullable=False, server_default="regular"),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchange.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_id", "session_date", "session_code", name="uq_exchange_calendar_exception"),
    )
    op.create_index("ix_exchange_calendar_exception_exchange_id", "exchange_calendar_exception", ["exchange_id"])

    op.create_table(
        "market_series",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("feed_scope", sa.String(length=40), nullable=False, server_default="consolidated"),
        sa.Column("session_code", sa.String(length=24), nullable=False, server_default="regular"),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("adjustment_basis", adjustment_basis, nullable=False, server_default="RAW"),
        sa.Column("adjustment_version", sa.String(length=80), nullable=False, server_default="v1"),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_series_key", sa.String(length=160), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchange.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", "exchange_id", "data_source_id", "feed_scope", "session_code", "timeframe", "adjustment_basis", "adjustment_version", name="uq_market_series_scope"),
    )
    op.create_index("ix_market_series_instrument_id", "market_series", ["instrument_id"])
    op.create_index("ix_market_series_exchange_id", "market_series", ["exchange_id"])
    op.create_index("ix_market_series_data_source_id", "market_series", ["data_source_id"])
    op.create_index("ix_market_series_instrument_lookup", "market_series", ["instrument_id", "timeframe", "session_code"])

    op.add_column("ohlcv_bar", sa.Column("market_series_id", sa.BigInteger(), nullable=True))
    op.add_column("ohlcv_bar", sa.Column("adjustment_basis", sa.String(length=32), nullable=False, server_default="raw"))
    op.add_column("ohlcv_bar", sa.Column("adjustment_version", sa.String(length=80), nullable=False, server_default="legacy"))
    op.add_column("ohlcv_bar", sa.Column("provenance", sa.JSON(), nullable=True))
    op.create_index("ix_ohlcv_bar_market_series_id", "ohlcv_bar", ["market_series_id"])
    op.create_index("ix_ohlcv_series_tf_ts", "ohlcv_bar", ["market_series_id", "timeframe", "ts"])
    op.create_foreign_key("fk_ohlcv_bar_market_series", "ohlcv_bar", "market_series", ["market_series_id"], ["id"], ondelete="SET NULL")

    op.add_column("market_bar_observation", sa.Column("market_series_id", sa.BigInteger(), nullable=True))
    op.add_column("market_bar_observation", sa.Column("adjustment_basis", sa.String(length=32), nullable=False, server_default="raw"))
    op.add_column("market_bar_observation", sa.Column("adjustment_version", sa.String(length=80), nullable=False, server_default="legacy"))
    op.add_column("market_bar_observation", sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_bar_observation", sa.Column("source_payload", sa.JSON(), nullable=True))
    op.create_index("ix_market_bar_observation_market_series_id", "market_bar_observation", ["market_series_id"])
    op.create_foreign_key("fk_market_bar_observation_market_series", "market_bar_observation", "market_series", ["market_series_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "instrument_identity_quarantine",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("proposed_domain_key", sa.String(length=120), nullable=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("exchange_mic", sa.String(length=10), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("candidate_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, cols in (
        ("ix_instrument_identity_quarantine_proposed_domain_key", ["proposed_domain_key"]),
        ("ix_instrument_identity_quarantine_provider_name", ["provider_name"]),
        ("ix_instrument_identity_quarantine_provider_symbol", ["provider_symbol"]),
        ("ix_instrument_identity_quarantine_exchange_mic", ["exchange_mic"]),
        ("ix_instrument_identity_quarantine_status", ["status"]),
    ):
        op.create_index(name, "instrument_identity_quarantine", cols)

    _create_runtime_tables()
    _create_domain_data_tables()


def _create_runtime_tables() -> None:
    def timestamps() -> list[sa.Column]:
        return [
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]
    op.create_table(
        "provider_quota_window",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("limit_units", sa.Integer(), nullable=False),
        sa.Column("reserved_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="configured"),
        *timestamps(),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "capability", "window_started_at", "window_seconds", name="uq_provider_quota_window"),
    )
    op.create_index("ix_provider_quota_window_data_source_id", "provider_quota_window", ["data_source_id"])
    op.create_index("ix_provider_quota_window_capability", "provider_quota_window", ["capability"])
    op.create_table(
        "provider_workload_lease",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workload_key", sa.String(length=180), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="reserved"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("request_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_workload_lease_workload_key", "provider_workload_lease", ["workload_key"])
    op.create_index("ix_provider_workload_lease_capability", "provider_workload_lease", ["capability"])
    op.create_index("ix_provider_workload_lease_data_source_id", "provider_workload_lease", ["data_source_id"])
    op.create_index("ix_provider_workload_lease_status", "provider_workload_lease", ["status"])
    op.create_table(
        "provider_routing_decision",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=180), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("selected_data_source_id", sa.Integer(), nullable=True),
        sa.Column("candidates", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("rejected", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("workload_key", sa.String(length=180), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_routing_decision_request_key", "provider_routing_decision", ["request_key"])
    op.create_index("ix_provider_routing_decision_capability", "provider_routing_decision", ["capability"])
    op.create_index("ix_provider_routing_decision_instrument_id", "provider_routing_decision", ["instrument_id"])
def _create_domain_data_tables() -> None:
    def timestamps() -> list[sa.Column]:
        return [
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]
    op.create_table(
        "market_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("issuer_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_provisional", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "source", name="uq_market_event_source_key"),
    )
    for name, cols in (
        ("ix_market_event_instrument_id", ["instrument_id"]),
        ("ix_market_event_issuer_id", ["issuer_id"]),
        ("ix_market_event_event_type", ["event_type"]),
        ("ix_market_event_event_key", ["event_key"]),
        ("ix_market_event_event_time", ["event_time"]),
        ("ix_market_event_effective_date", ["effective_date"]),
    ):
        op.create_index(name, "market_event", cols)
    op.create_table(
        "fundamental_fact",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("issuer_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("fact_namespace", sa.String(length=120), nullable=False),
        sa.Column("fact_key", sa.String(length=160), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("value_numeric", sa.Numeric(30, 10), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("filed_at", sa.Date(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_identifier", sa.String(length=180), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
        sa.ForeignKeyConstraint(["issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fundamental_fact_issuer_id", "fundamental_fact", ["issuer_id"])
    op.create_index("ix_fundamental_fact_instrument_id", "fundamental_fact", ["instrument_id"])
    op.create_index("ix_fundamental_fact_point_in_time", "fundamental_fact", ["issuer_id", "fact_key", "filed_at"])
    op.create_table(
        "short_interest_observation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("short_position", sa.Numeric(30, 4), nullable=True),
        sa.Column("short_percent_float", sa.Numeric(12, 8), nullable=True),
        sa.Column("days_to_cover", sa.Numeric(12, 8), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_identifier", sa.String(length=180), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", "settlement_date", "source", name="uq_short_interest_observation"),
    )
    op.create_index("ix_short_interest_observation_instrument_id", "short_interest_observation", ["instrument_id"])
    op.create_index("ix_short_interest_observation_settlement_date", "short_interest_observation", ["settlement_date"])


def downgrade() -> None:
    for table in (
        "short_interest_observation",
        "fundamental_fact",
        "market_event",
        "provider_routing_decision",
        "provider_workload_lease",
        "provider_quota_window",
        "instrument_identity_quarantine",
        "market_bar_observation",
        "ohlcv_bar",
        "market_series",
        "exchange_calendar_exception",
        "exchange_session_rule",
    ):
        # This migration is intentionally additive; dropping legacy tables would
        # be destructive, so only its additive columns are removed on downgrade.
        if table == "market_bar_observation":
            for column in ("source_payload", "provider_timestamp", "adjustment_version", "adjustment_basis", "market_series_id"):
                op.drop_column(table, column)
        elif table == "ohlcv_bar":
            op.drop_constraint("fk_ohlcv_bar_market_series", table, type_="foreignkey")
            op.drop_index("ix_ohlcv_series_tf_ts", table_name=table)
            op.drop_index("ix_ohlcv_bar_market_series_id", table_name=table)
            for column in ("provenance", "adjustment_version", "adjustment_basis", "market_series_id"):
                op.drop_column(table, column)
        else:
            op.drop_table(table)
    for table, columns in (("instrument_listing", ("provenance", "source", "last_verified_at")), ("instrument_identifier", ("retired_at", "known_at", "effective_at"))):
        for column in columns:
            op.drop_column(table, column)
    op.drop_constraint("fk_instrument_issuer", "instrument", type_="foreignkey")
    op.drop_index("ix_instrument_issuer_id", table_name="instrument")
    op.drop_index("ix_instrument_domain_key", table_name="instrument")
    op.drop_column("instrument", "issuer_id")
    op.drop_column("instrument", "identity_status")
    op.drop_column("instrument", "domain_key")
    op.drop_index("ix_issuer_lei", table_name="issuer")
    op.drop_index("ix_issuer_cik", table_name="issuer")
    op.drop_index("ix_issuer_domain_key", table_name="issuer")
    op.drop_table("issuer")
    adjustment_basis = sa.Enum(name="adjustmentbasis")
    calendar_exception_kind = sa.Enum(name="calendarexceptionkind")
    adjustment_basis.drop(op.get_bind(), checkfirst=True)
    calendar_exception_kind.drop(op.get_bind(), checkfirst=True)
