"""add etf holdings

Revision ID: b8c9d0e1f2a3
Revises: ab12cd34ef56
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "ab12cd34ef56"
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

    if not inspector.has_table("etf_profile"):
        op.create_table(
            "etf_profile",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("issuer", sa.String(length=120), nullable=True),
            sa.Column("sponsor", sa.String(length=120), nullable=True),
            sa.Column("fund_family", sa.String(length=120), nullable=True),
            sa.Column("index_name", sa.String(length=180), nullable=True),
            sa.Column("product_url", sa.String(length=500), nullable=True),
            sa.Column("sec_cik", sa.String(length=20), nullable=True),
            sa.Column("sec_series_id", sa.String(length=40), nullable=True),
            sa.Column("sec_class_id", sa.String(length=40), nullable=True),
            sa.Column("adapter_key", sa.String(length=80), nullable=True),
            sa.Column("adapter_confidence", sa.Numeric(8, 4), nullable=True),
            sa.Column("adapter_status", sa.String(length=40), nullable=False),
            sa.Column("provider_aliases", sa.JSON(), nullable=True),
            sa.Column("legal_metadata", sa.JSON(), nullable=True),
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("instrument_id", name="uq_etf_profile_instrument_id"),
        )
    for name, cols in [
        ("ix_etf_profile_issuer", ["issuer"]),
        ("ix_etf_profile_fund_family", ["fund_family"]),
        ("ix_etf_profile_sec_cik", ["sec_cik"]),
        ("ix_etf_profile_sec_series_id", ["sec_series_id"]),
        ("ix_etf_profile_sec_class_id", ["sec_class_id"]),
        ("ix_etf_profile_adapter_key", ["adapter_key"]),
        ("ix_etf_profile_adapter_status", ["adapter_status"]),
    ]:
        _create_index_once(name, "etf_profile", cols)

    if not inspector.has_table("etf_holdings_raw_artifact"):
        op.create_table(
            "etf_holdings_raw_artifact",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("etf_profile_id", sa.Integer(), nullable=False),
            sa.Column("data_source_id", sa.Integer(), nullable=True),
            sa.Column("source_kind", sa.String(length=60), nullable=False),
            sa.Column("source_url", sa.String(length=800), nullable=True),
            sa.Column("source_identifier", sa.String(length=180), nullable=True),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("content_hash", sa.String(length=80), nullable=False),
            sa.Column("composition_date", sa.Date(), nullable=True),
            sa.Column("as_of_date", sa.Date(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("parser_version", sa.String(length=40), nullable=False),
            sa.Column("payload_text", sa.Text(), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("legal_metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["etf_profile_id"], ["etf_profile.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "etf_profile_id",
                "source_kind",
                "content_hash",
                name="uq_etf_holdings_raw_artifact_hash",
            ),
        )
    for name, cols in [
        ("ix_etf_holdings_raw_artifact_etf_profile_id", ["etf_profile_id"]),
        ("ix_etf_holdings_raw_artifact_data_source_id", ["data_source_id"]),
        ("ix_etf_holdings_raw_artifact_source_kind", ["source_kind"]),
        ("ix_etf_holdings_raw_artifact_source_identifier", ["source_identifier"]),
        ("ix_etf_holdings_raw_artifact_content_hash", ["content_hash"]),
        ("ix_etf_holdings_raw_artifact_composition_date", ["composition_date"]),
        ("ix_etf_holdings_raw_artifact_as_of_date", ["as_of_date"]),
    ]:
        _create_index_once(name, "etf_holdings_raw_artifact", cols)

    if not inspector.has_table("etf_holdings_snapshot"):
        op.create_table(
            "etf_holdings_snapshot",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("etf_profile_id", sa.Integer(), nullable=False),
            sa.Column("source_artifact_id", sa.Integer(), nullable=True),
            sa.Column("data_source_id", sa.Integer(), nullable=True),
            sa.Column("composition_date", sa.Date(), nullable=False),
            sa.Column("as_of_date", sa.Date(), nullable=True),
            sa.Column("known_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provenance", sa.String(length=60), nullable=False),
            sa.Column("source_provider", sa.String(length=80), nullable=False),
            sa.Column("source_url", sa.String(length=800), nullable=True),
            sa.Column("source_identifier", sa.String(length=180), nullable=True),
            sa.Column("source_quality", sa.String(length=40), nullable=False),
            sa.Column("completeness_status", sa.String(length=40), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("resolved_count", sa.Integer(), nullable=False),
            sa.Column("unresolved_count", sa.Integer(), nullable=False),
            sa.Column("total_weight", sa.Numeric(18, 8), nullable=True),
            sa.Column("parser_version", sa.String(length=40), nullable=False),
            sa.Column("snapshot_hash", sa.String(length=80), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["etf_profile_id"], ["etf_profile.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["source_artifact_id"], ["etf_holdings_raw_artifact.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "etf_profile_id",
                "composition_date",
                "provenance",
                "source_provider",
                "snapshot_hash",
                name="uq_etf_holdings_snapshot_version",
            ),
        )
    for name, cols in [
        ("ix_etf_holdings_snapshot_etf_profile_id", ["etf_profile_id"]),
        ("ix_etf_holdings_snapshot_source_artifact_id", ["source_artifact_id"]),
        ("ix_etf_holdings_snapshot_data_source_id", ["data_source_id"]),
        ("ix_etf_holdings_snapshot_composition_date", ["composition_date"]),
        ("ix_etf_holdings_snapshot_as_of_date", ["as_of_date"]),
        ("ix_etf_holdings_snapshot_provenance", ["provenance"]),
        ("ix_etf_holdings_snapshot_source_provider", ["source_provider"]),
        (
            "ix_etf_holdings_snapshot_latest",
            ["etf_profile_id", "composition_date", "known_at"],
        ),
    ]:
        _create_index_once(name, "etf_holdings_snapshot", cols)

    if not inspector.has_table("etf_holding"):
        op.create_table(
            "etf_holding",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("snapshot_id", sa.Integer(), nullable=False),
            sa.Column("constituent_instrument_id", sa.Integer(), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("reported_symbol", sa.String(length=80), nullable=True),
            sa.Column("reported_name", sa.String(length=300), nullable=True),
            sa.Column("cusip", sa.String(length=20), nullable=True),
            sa.Column("isin", sa.String(length=20), nullable=True),
            sa.Column("sedol", sa.String(length=20), nullable=True),
            sa.Column("weight", sa.Numeric(18, 8), nullable=True),
            sa.Column("shares", sa.Numeric(28, 8), nullable=True),
            sa.Column("market_value", sa.Numeric(28, 6), nullable=True),
            sa.Column("currency", sa.String(length=10), nullable=True),
            sa.Column("country", sa.String(length=80), nullable=True),
            sa.Column("exchange", sa.String(length=80), nullable=True),
            sa.Column("holding_type", sa.String(length=40), nullable=False),
            sa.Column("row_type", sa.String(length=40), nullable=False),
            sa.Column("source_row_id", sa.String(length=160), nullable=True),
            sa.Column("source_row_hash", sa.String(length=80), nullable=False),
            sa.Column("is_resolved", sa.Boolean(), nullable=False),
            sa.Column("resolution_confidence", sa.Numeric(8, 4), nullable=True),
            sa.Column("resolution_note", sa.String(length=300), nullable=True),
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["constituent_instrument_id"], ["instrument.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["snapshot_id"], ["etf_holdings_snapshot.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("snapshot_id", "source_row_hash", name="uq_etf_holding_snapshot_row_hash"),
        )
    for name, cols in [
        ("ix_etf_holding_snapshot_id", ["snapshot_id"]),
        ("ix_etf_holding_constituent_instrument_id", ["constituent_instrument_id"]),
        ("ix_etf_holding_reported_symbol", ["reported_symbol"]),
        ("ix_etf_holding_cusip", ["cusip"]),
        ("ix_etf_holding_isin", ["isin"]),
        ("ix_etf_holding_sedol", ["sedol"]),
        ("ix_etf_holding_is_resolved", ["is_resolved"]),
        ("ix_etf_holding_snapshot_weight", ["snapshot_id", "weight"]),
        ("ix_etf_holding_snapshot_resolved", ["snapshot_id", "is_resolved"]),
    ]:
        _create_index_once(name, "etf_holding", cols)

    if not inspector.has_table("etf_holdings_adapter_state"):
        op.create_table(
            "etf_holdings_adapter_state",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("etf_profile_id", sa.Integer(), nullable=False),
            sa.Column("data_source_id", sa.Integer(), nullable=True),
            sa.Column("adapter_key", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("source_url", sa.String(length=800), nullable=True),
            sa.Column("source_identifier", sa.String(length=180), nullable=True),
            sa.Column("parser_version", sa.String(length=40), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=True),
            sa.Column("resolved_count", sa.Integer(), nullable=True),
            sa.Column("unresolved_count", sa.Integer(), nullable=True),
            sa.Column("composition_date", sa.Date(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completeness_status", sa.String(length=40), nullable=True),
            sa.Column("rate_limit_state", sa.String(length=80), nullable=True),
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["etf_profile_id"], ["etf_profile.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("etf_profile_id", "adapter_key", name="uq_etf_holdings_adapter_state"),
        )
    for name, cols in [
        ("ix_etf_holdings_adapter_state_etf_profile_id", ["etf_profile_id"]),
        ("ix_etf_holdings_adapter_state_data_source_id", ["data_source_id"]),
        ("ix_etf_holdings_adapter_state_adapter_key", ["adapter_key"]),
        ("ix_etf_holdings_adapter_state_status", ["status"]),
    ]:
        _create_index_once(name, "etf_holdings_adapter_state", cols)

    if not inspector.has_table("etf_index_proxy_mapping"):
        op.create_table(
            "etf_index_proxy_mapping",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("etf_profile_id", sa.Integer(), nullable=False),
            sa.Column("index_name", sa.String(length=180), nullable=False),
            sa.Column("proxy_symbol", sa.String(length=50), nullable=False),
            sa.Column("confidence", sa.Numeric(8, 4), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["etf_profile_id"], ["etf_profile.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "etf_profile_id",
                "index_name",
                name="uq_etf_index_proxy_mapping_profile_index",
            ),
        )
    for name, cols in [
        ("ix_etf_index_proxy_mapping_etf_profile_id", ["etf_profile_id"]),
        ("ix_etf_index_proxy_mapping_index_name", ["index_name"]),
        ("ix_etf_index_proxy_mapping_proxy_symbol", ["proxy_symbol"]),
    ]:
        _create_index_once(name, "etf_index_proxy_mapping", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in [
        "etf_index_proxy_mapping",
        "etf_holdings_adapter_state",
        "etf_holding",
        "etf_holdings_snapshot",
        "etf_holdings_raw_artifact",
        "etf_profile",
    ]:
        if inspector.has_table(table):
            op.drop_table(table)
