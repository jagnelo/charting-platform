"""Cache verified, content-addressed ETF issuer product catalogs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6f7a8b9c012"
down_revision: str | None = "d4a5b6c7e812"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etf_issuer_catalog_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("catalog_key", sa.String(length=120), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=800), nullable=False),
        sa.Column("final_url", sa.String(length=800), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_bytes", sa.Integer(), nullable=False),
        sa.Column("response_encoding", sa.String(length=40), nullable=False),
        sa.Column("raw_body_base64", sa.Text(), nullable=False),
        sa.Column("parsed_entries", sa.JSON(), nullable=False),
        sa.Column("reported_total", sa.Integer(), nullable=True),
        sa.Column("catalog_complete", sa.Boolean(), nullable=False),
        sa.Column("requested_symbol", sa.String(length=20), nullable=False),
        sa.Column("provider_request_log_ids", sa.JSON(), nullable=False),
        sa.Column("request_urls", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_key",
            "content_sha256",
            name="uq_etf_issuer_catalog_cache_content",
        ),
    )
    op.create_index(
        "ix_etf_issuer_catalog_cache_provider_name",
        "etf_issuer_catalog_cache",
        ["provider_name"],
    )
    op.create_index(
        "ix_etf_issuer_catalog_cache_catalog_key",
        "etf_issuer_catalog_cache",
        ["catalog_key"],
    )
    op.create_index(
        "ix_etf_issuer_catalog_cache_data_source_id",
        "etf_issuer_catalog_cache",
        ["data_source_id"],
    )
    op.create_index(
        "ix_etf_issuer_catalog_cache_fetched_at",
        "etf_issuer_catalog_cache",
        ["fetched_at"],
    )
    op.create_index(
        "ix_etf_issuer_catalog_cache_latest",
        "etf_issuer_catalog_cache",
        ["provider_name", "catalog_key", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_etf_issuer_catalog_cache_latest", table_name="etf_issuer_catalog_cache")
    op.drop_index("ix_etf_issuer_catalog_cache_fetched_at", table_name="etf_issuer_catalog_cache")
    op.drop_index(
        "ix_etf_issuer_catalog_cache_data_source_id", table_name="etf_issuer_catalog_cache"
    )
    op.drop_index("ix_etf_issuer_catalog_cache_catalog_key", table_name="etf_issuer_catalog_cache")
    op.drop_index(
        "ix_etf_issuer_catalog_cache_provider_name", table_name="etf_issuer_catalog_cache"
    )
    op.drop_table("etf_issuer_catalog_cache")
