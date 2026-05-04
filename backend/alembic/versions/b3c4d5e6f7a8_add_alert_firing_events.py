"""add alert firing events table

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-05-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("alert_firing_event"):
        op.create_table(
            "alert_firing_event",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("instrument_id", sa.Integer(), nullable=True),
            sa.Column("alert_type", sa.String(length=20), nullable=False),
            sa.Column("alert_id", sa.Integer(), nullable=False),
            sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("trigger_value", sa.Numeric(20, 8), nullable=True),
            sa.Column("condition_snapshot", sa.Text(), nullable=False),
            sa.Column("is_viewed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("alert_firing_event")}
    for index_name, columns in [
        ("ix_alert_firing_event_user_id", ["user_id"]),
        ("ix_alert_firing_event_instrument_id", ["instrument_id"]),
        ("ix_alert_firing_event_fired_at", ["fired_at"]),
        ("ix_alert_firing_event_user_viewed", ["user_id", "is_viewed"]),
        ("ix_alert_firing_event_instrument_time", ["instrument_id", "fired_at"]),
    ]:
        if index_name not in existing_indexes:
            op.create_index(index_name, "alert_firing_event", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("alert_firing_event"):
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("alert_firing_event")}
    for index_name in [
        "ix_alert_firing_event_instrument_time",
        "ix_alert_firing_event_user_viewed",
        "ix_alert_firing_event_fired_at",
        "ix_alert_firing_event_instrument_id",
        "ix_alert_firing_event_user_id",
    ]:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="alert_firing_event")
    op.drop_table("alert_firing_event")
