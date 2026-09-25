"""Retain every provider response for fundamental and short-interest data."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "d3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bigint_id = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "fundamental_fact_observation",
        sa.Column("id", bigint_id, autoincrement=True, nullable=False),
        sa.Column("fundamental_fact_id", bigint_id, nullable=True),
        sa.Column("issuer_id", bigint_id, nullable=True),
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
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["fundamental_fact_id"], ["fundamental_fact.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_fundamental_fact_observation_fundamental_fact_id", ["fundamental_fact_id"]),
        ("ix_fundamental_fact_observation_issuer_id", ["issuer_id"]),
        ("ix_fundamental_fact_observation_instrument_id", ["instrument_id"]),
        ("ix_fundamental_fact_observation_source", ["source"]),
        ("ix_fundamental_fact_observation_observed_at", ["observed_at"]),
        (
            "ix_fundamental_fact_observation_source_identity",
            ["source", "fact_namespace", "fact_key", "observed_at"],
        ),
    ):
        op.create_index(name, "fundamental_fact_observation", columns)

    op.create_table(
        "short_interest_provider_observation",
        sa.Column("id", bigint_id, autoincrement=True, nullable=False),
        sa.Column("canonical_observation_id", bigint_id, nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("short_position", sa.Numeric(30, 4), nullable=True),
        sa.Column("short_percent_float", sa.Numeric(12, 8), nullable=True),
        sa.Column("days_to_cover", sa.Numeric(12, 8), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_identifier", sa.String(length=180), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["canonical_observation_id"], ["short_interest_observation.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_short_interest_provider_observation_canonical_observation_id", ["canonical_observation_id"]),
        ("ix_short_interest_provider_observation_instrument_id", ["instrument_id"]),
        ("ix_short_interest_provider_observation_settlement_date", ["settlement_date"]),
        ("ix_short_interest_provider_observation_source", ["source"]),
        ("ix_short_interest_provider_observation_observed_at", ["observed_at"]),
        (
            "ix_short_interest_provider_observation_identity",
            ["instrument_id", "settlement_date", "source", "observed_at"],
        ),
    ):
        op.create_index(name, "short_interest_provider_observation", columns)


def downgrade() -> None:
    for name in (
        "ix_short_interest_provider_observation_identity",
        "ix_short_interest_provider_observation_observed_at",
        "ix_short_interest_provider_observation_source",
        "ix_short_interest_provider_observation_settlement_date",
        "ix_short_interest_provider_observation_instrument_id",
        "ix_short_interest_provider_observation_canonical_observation_id",
    ):
        op.drop_index(name, table_name="short_interest_provider_observation")
    op.drop_table("short_interest_provider_observation")
    for name in (
        "ix_fundamental_fact_observation_source_identity",
        "ix_fundamental_fact_observation_observed_at",
        "ix_fundamental_fact_observation_source",
        "ix_fundamental_fact_observation_instrument_id",
        "ix_fundamental_fact_observation_issuer_id",
        "ix_fundamental_fact_observation_fundamental_fact_id",
    ):
        op.drop_index(name, table_name="fundamental_fact_observation")
    op.drop_table("fundamental_fact_observation")
