"""add etf holdings backfill state

Revision ID: d0e1f2a3b4d5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-05 21:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d0e1f2a3b4d5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_once(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "etf_holdings_backfill_job" not in tables:
        op.create_table(
            "etf_holdings_backfill_job",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("etf_profile_id", sa.Integer(), nullable=False),
            sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
            sa.Column("source_provider", sa.String(length=80), nullable=False),
            sa.Column("job_type", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("max_filings", sa.Integer(), nullable=True),
            sa.Column("discovered_count", sa.Integer(), nullable=False),
            sa.Column("ingested_count", sa.Integer(), nullable=False),
            sa.Column("skipped_count", sa.Integer(), nullable=False),
            sa.Column("failed_count", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("summary", sa.JSON(), nullable=True),
            sa.Column("extra_data", sa.JSON(), nullable=True),
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
            sa.ForeignKeyConstraint(["etf_profile_id"], ["etf_profile.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, cols in [
        ("ix_etf_holdings_backfill_job_etf_profile_id", ["etf_profile_id"]),
        ("ix_etf_holdings_backfill_job_requested_by_user_id", ["requested_by_user_id"]),
        ("ix_etf_holdings_backfill_job_source_provider", ["source_provider"]),
        ("ix_etf_holdings_backfill_job_job_type", ["job_type"]),
        ("ix_etf_holdings_backfill_job_status", ["status"]),
        (
            "ix_etf_holdings_backfill_job_profile_started",
            ["etf_profile_id", "started_at"],
        ),
    ]:
        _create_index_once(name, "etf_holdings_backfill_job", cols)

    tables = set(sa.inspect(bind).get_table_names())
    if "etf_holdings_backfill_filing" not in tables:
        op.create_table(
            "etf_holdings_backfill_filing",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("etf_profile_id", sa.Integer(), nullable=False),
            sa.Column("last_job_id", sa.Integer(), nullable=True),
            sa.Column("snapshot_id", sa.Integer(), nullable=True),
            sa.Column("accession_number", sa.String(length=40), nullable=False),
            sa.Column("form", sa.String(length=40), nullable=False),
            sa.Column("filing_date", sa.Date(), nullable=True),
            sa.Column("report_date", sa.Date(), nullable=True),
            sa.Column("acceptance_datetime", sa.DateTime(timezone=True), nullable=True),
            sa.Column("primary_document", sa.String(length=260), nullable=True),
            sa.Column("filing_url", sa.String(length=800), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("extra_data", sa.JSON(), nullable=True),
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
            sa.ForeignKeyConstraint(["etf_profile_id"], ["etf_profile.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["last_job_id"],
                ["etf_holdings_backfill_job.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["snapshot_id"],
                ["etf_holdings_snapshot.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "etf_profile_id",
                "accession_number",
                name="uq_etf_holdings_backfill_filing_accession",
            ),
        )
    for name, cols in [
        ("ix_etf_holdings_backfill_filing_etf_profile_id", ["etf_profile_id"]),
        ("ix_etf_holdings_backfill_filing_last_job_id", ["last_job_id"]),
        ("ix_etf_holdings_backfill_filing_snapshot_id", ["snapshot_id"]),
        ("ix_etf_holdings_backfill_filing_accession_number", ["accession_number"]),
        ("ix_etf_holdings_backfill_filing_form", ["form"]),
        ("ix_etf_holdings_backfill_filing_filing_date", ["filing_date"]),
        ("ix_etf_holdings_backfill_filing_report_date", ["report_date"]),
        ("ix_etf_holdings_backfill_filing_status", ["status"]),
        (
            "ix_etf_holdings_backfill_filing_profile_status",
            ["etf_profile_id", "status"],
        ),
    ]:
        _create_index_once(name, "etf_holdings_backfill_filing", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ["etf_holdings_backfill_filing", "etf_holdings_backfill_job"]:
        if inspector.has_table(table):
            op.drop_table(table)
