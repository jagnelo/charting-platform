"""add dashboard workspace tables

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-04-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "dashboard" not in tables:
        op.create_table(
            "dashboard",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_dashboard_user_id", "dashboard", ["user_id"])

    if "dashboard_tab" not in tables:
        op.create_table(
            "dashboard_tab",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("dashboard_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("layout_settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["dashboard_id"], ["dashboard.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_dashboard_tab_dashboard_id", "dashboard_tab", ["dashboard_id"])

    if "dashboard_widget" not in tables:
        op.create_table(
            "dashboard_widget",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tab_id", sa.Integer(), nullable=False),
            sa.Column("widget_type", sa.String(length=60), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=True),
            sa.Column("layout", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("style", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tab_id"], ["dashboard_tab.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_dashboard_widget_tab_id", "dashboard_widget", ["tab_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "dashboard_widget" in tables:
        op.drop_index("ix_dashboard_widget_tab_id", table_name="dashboard_widget")
        op.drop_table("dashboard_widget")

    if "dashboard_tab" in tables:
        op.drop_index("ix_dashboard_tab_dashboard_id", table_name="dashboard_tab")
        op.drop_table("dashboard_tab")

    if "dashboard" in tables:
        op.drop_index("ix_dashboard_user_id", table_name="dashboard")
        op.drop_table("dashboard")
