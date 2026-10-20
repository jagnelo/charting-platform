"""add coverage, shadow, and anomaly telemetry"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3c4d5e6f7081"
down_revision: str | None = "2b3c4d5e6f70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_coverage_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("market_series_id", sa.BigInteger(), nullable=True),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("expected_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_ratio", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="unavailable"),
        sa.Column("missing_slices", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_series_id"], ["market_series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_series_id", "timeframe", "evaluated_at", name="uq_market_coverage_snapshot"),
    )
    for name, columns in (
        ("ix_market_coverage_snapshot_instrument_id", ["instrument_id"]),
        ("ix_market_coverage_snapshot_market_series_id", ["market_series_id"]),
        ("ix_market_coverage_snapshot_status", ["status"]),
        ("ix_market_coverage_snapshot_evaluated", ["evaluated_at"]),
    ):
        op.create_index(name, "market_coverage_snapshot", columns)

    op.create_table(
        "provider_shadow_observation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=180), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("primary_data_source_id", sa.Integer(), nullable=True),
        sa.Column("alternate_data_source_id", sa.Integer(), nullable=True),
        sa.Column("comparison_status", sa.String(length=24), nullable=False),
        sa.Column("discrepancy_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("routing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["primary_data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["alternate_data_source_id"], ["data_source.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_provider_shadow_observation_request_key", ["request_key"]),
        ("ix_provider_shadow_observation_capability", ["capability"]),
        ("ix_provider_shadow_observation_instrument_id", ["instrument_id"]),
        ("ix_provider_shadow_observation_comparison_status", ["comparison_status"]),
        ("ix_provider_shadow_observation_observed", ["observed_at"]),
    ):
        op.create_index(name, "provider_shadow_observation", columns)

    op.create_table(
        "market_data_anomaly",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("market_series_id", sa.BigInteger(), nullable=True),
        sa.Column("anomaly_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["market_series_id"], ["market_series.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_market_data_anomaly_instrument_id", ["instrument_id"]),
        ("ix_market_data_anomaly_market_series_id", ["market_series_id"]),
        ("ix_market_data_anomaly_anomaly_type", ["anomaly_type"]),
        ("ix_market_data_anomaly_severity", ["severity"]),
        ("ix_market_data_anomaly_status", ["status"]),
    ):
        op.create_index(name, "market_data_anomaly", columns)


def downgrade() -> None:
    for name in (
        "ix_market_data_anomaly_status",
        "ix_market_data_anomaly_severity",
        "ix_market_data_anomaly_anomaly_type",
        "ix_market_data_anomaly_market_series_id",
        "ix_market_data_anomaly_instrument_id",
    ):
        op.drop_index(name, table_name="market_data_anomaly")
    op.drop_table("market_data_anomaly")
    for name in (
        "ix_provider_shadow_observation_observed",
        "ix_provider_shadow_observation_comparison_status",
        "ix_provider_shadow_observation_instrument_id",
        "ix_provider_shadow_observation_capability",
        "ix_provider_shadow_observation_request_key",
    ):
        op.drop_index(name, table_name="provider_shadow_observation")
    op.drop_table("provider_shadow_observation")
    for name in (
        "ix_market_coverage_snapshot_evaluated",
        "ix_market_coverage_snapshot_status",
        "ix_market_coverage_snapshot_market_series_id",
        "ix_market_coverage_snapshot_instrument_id",
    ):
        op.drop_index(name, table_name="market_coverage_snapshot")
    op.drop_table("market_coverage_snapshot")
