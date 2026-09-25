"""Retain every provider identity-quarantine evidence envelope."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9f3a4b5c6d7"
down_revision: str | None = "e9f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_identity_quarantine_observation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("quarantine_id", sa.BigInteger(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("proposed_domain_key", sa.String(length=120), nullable=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("exchange_mic", sa.String(length=10), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["quarantine_id"], ["instrument_identity_quarantine.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_instrument_identity_quarantine_observation_quarantine_id", ["quarantine_id"]),
        ("ix_instrument_identity_quarantine_observation_instrument_id", ["instrument_id"]),
        ("ix_instrument_identity_quarantine_observation_proposed_domain_key", ["proposed_domain_key"]),
        ("ix_instrument_identity_quarantine_observation_provider_name", ["provider_name"]),
        ("ix_instrument_identity_quarantine_observation_provider_symbol", ["provider_symbol"]),
        ("ix_instrument_identity_quarantine_observation_exchange_mic", ["exchange_mic"]),
        ("ix_instrument_identity_quarantine_observation_status", ["status"]),
        ("ix_instrument_identity_quarantine_observation_observed_at", ["observed_at"]),
        (
            "ix_instrument_identity_quarantine_observation_lookup",
            ["quarantine_id", "observed_at"],
        ),
    ):
        op.create_index(name, "instrument_identity_quarantine_observation", columns)


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text("SELECT 1 FROM instrument_identity_quarantine_observation LIMIT 1")
    ).first()
    if populated is not None:
        raise RuntimeError(
            "refusing to downgrade: identity-quarantine evidence exists and would be lost"
        )
    for name in (
        "ix_instrument_identity_quarantine_observation_lookup",
        "ix_instrument_identity_quarantine_observation_observed_at",
        "ix_instrument_identity_quarantine_observation_status",
        "ix_instrument_identity_quarantine_observation_exchange_mic",
        "ix_instrument_identity_quarantine_observation_provider_symbol",
        "ix_instrument_identity_quarantine_observation_provider_name",
        "ix_instrument_identity_quarantine_observation_proposed_domain_key",
        "ix_instrument_identity_quarantine_observation_instrument_id",
        "ix_instrument_identity_quarantine_observation_quarantine_id",
    ):
        op.drop_index(name, table_name="instrument_identity_quarantine_observation")
    op.drop_table("instrument_identity_quarantine_observation")
