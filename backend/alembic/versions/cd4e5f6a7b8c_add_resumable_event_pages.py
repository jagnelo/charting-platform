"""Persist resumable provider event pages and raw envelopes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cd4e5f6a7b8c"
down_revision: str | Sequence[str] | None = ("b0c1d2e3f4a5", "bc2d3e4f5a6b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "instrument_event_fetch_state" in tables:
        columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
        additions = (
            ("continuation_token", sa.Text(), None),
            ("query_fingerprint", sa.String(length=128), None),
            ("query_start_date", sa.String(length=16), None),
            ("query_end_date", sa.String(length=16), None),
            ("page_count", sa.Integer(), "0"),
            ("complete", sa.Boolean(), "false"),
        )
        for name, column_type, default in additions:
            if name not in columns:
                op.add_column(
                    "instrument_event_fetch_state",
                    sa.Column(
                        name,
                        column_type,
                        nullable=name
                        in {
                            "continuation_token",
                            "query_fingerprint",
                            "query_start_date",
                            "query_end_date",
                        },
                        server_default=default,
                    ),
                )

    if "instrument_event_page_snapshot" not in tables:
        op.create_table(
            "instrument_event_page_snapshot",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("query_fingerprint", sa.String(length=128), nullable=False),
            sa.Column("request_page_token", sa.Text(), nullable=True),
            sa.Column("next_page_token", sa.Text(), nullable=True),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_instrument_event_page_snapshot_instrument_id",
            "instrument_event_page_snapshot",
            ["instrument_id"],
        )
        op.create_index(
            "ix_instrument_event_page_snapshot_progress",
            "instrument_event_page_snapshot",
            ["instrument_id", "source", "query_fingerprint", "page_number"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "instrument_event_page_snapshot" in tables:
        op.drop_index(
            "ix_instrument_event_page_snapshot_progress",
            table_name="instrument_event_page_snapshot",
        )
        op.drop_index(
            "ix_instrument_event_page_snapshot_instrument_id",
            table_name="instrument_event_page_snapshot",
        )
        op.drop_table("instrument_event_page_snapshot")
    if "instrument_event_fetch_state" in tables:
        columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
        for name in (
            "complete",
            "page_count",
            "query_end_date",
            "query_start_date",
            "query_fingerprint",
            "continuation_token",
        ):
            if name in columns:
                op.drop_column("instrument_event_fetch_state", name)
