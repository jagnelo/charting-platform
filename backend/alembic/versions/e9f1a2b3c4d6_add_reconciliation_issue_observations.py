"""Retain every provider evidence envelope for reconciliation issues."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9f2a3b4c5d6"
down_revision: str | None = "e9f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_reconciliation_issue_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=False),
        sa.Column("issue_type", sa.String(length=60), nullable=False),
        sa.Column("fingerprint", sa.String(length=80), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["instrument_reconciliation_issue.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_instrument_reconciliation_issue_observation_issue_id", ["issue_id"]),
        ("ix_instrument_reconciliation_issue_observation_data_source_id", ["data_source_id"]),
        ("ix_instrument_reconciliation_issue_observation_provider_symbol", ["provider_symbol"]),
        ("ix_instrument_reconciliation_issue_observation_issue_type", ["issue_type"]),
        ("ix_instrument_reconciliation_issue_observation_fingerprint", ["fingerprint"]),
        ("ix_instrument_reconciliation_issue_observation_observed_at", ["observed_at"]),
        (
            "ix_instrument_reconciliation_observation_issue_observed",
            ["issue_id", "observed_at"],
        ),
    ):
        op.create_index(name, "instrument_reconciliation_issue_observation", columns)


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text("SELECT 1 FROM instrument_reconciliation_issue_observation LIMIT 1")
    ).first()
    if populated is not None:
        raise RuntimeError(
            "refusing to downgrade: reconciliation issue evidence exists and would be lost"
        )
    for name in (
        "ix_instrument_reconciliation_observation_issue_observed",
        "ix_instrument_reconciliation_issue_observation_observed_at",
        "ix_instrument_reconciliation_issue_observation_fingerprint",
        "ix_instrument_reconciliation_issue_observation_issue_type",
        "ix_instrument_reconciliation_issue_observation_provider_symbol",
        "ix_instrument_reconciliation_issue_observation_data_source_id",
        "ix_instrument_reconciliation_issue_observation_issue_id",
    ):
        op.drop_index(name, table_name="instrument_reconciliation_issue_observation")
    op.drop_table("instrument_reconciliation_issue_observation")
