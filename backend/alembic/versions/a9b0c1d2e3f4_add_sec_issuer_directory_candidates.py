"""Persist reviewable row-level SEC issuer admission decisions."""

import sqlalchemy as sa

from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f0a1b2c3d4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sec_issuer_directory_candidate",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("directory_offset", sa.Integer(), nullable=False),
        sa.Column("directory_total", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("materialization_mode", sa.String(length=24), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("conformed_name", sa.String(length=300), nullable=False),
        sa.Column("name_candidates", sa.JSON(), nullable=False),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.Column("admission_decision", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.String(length=500), nullable=False),
        sa.Column("cycle_status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("cycle_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cycle_clean", sa.Boolean(), nullable=True),
        sa.Column("cycle_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_issuer_id", sa.BigInteger(), nullable=True),
        sa.Column("matched_issuer_domain_key", sa.String(length=120), nullable=True),
        sa.Column("matched_issuer_legal_name", sa.String(length=300), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["matched_issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_number", "cik", name="uq_sec_issuer_directory_candidate_cycle_cik"
        ),
    )
    op.create_index(
        "ix_sec_issuer_directory_candidate_matched_issuer_id",
        "sec_issuer_directory_candidate",
        ["matched_issuer_id"],
    )
    op.create_index(
        "ix_sec_issuer_directory_candidate_cycle_page",
        "sec_issuer_directory_candidate",
        ["cycle_number", "directory_offset", "cik"],
    )
    op.create_index(
        "ix_sec_issuer_directory_candidate_decision",
        "sec_issuer_directory_candidate",
        ["cycle_number", "admission_decision"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sec_issuer_directory_candidate_decision",
        table_name="sec_issuer_directory_candidate",
    )
    op.drop_index(
        "ix_sec_issuer_directory_candidate_cycle_page",
        table_name="sec_issuer_directory_candidate",
    )
    op.drop_index(
        "ix_sec_issuer_directory_candidate_matched_issuer_id",
        table_name="sec_issuer_directory_candidate",
    )
    op.drop_table("sec_issuer_directory_candidate")
