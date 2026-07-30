"""add TC2000 workstation persistence foundation

Revision ID: c0a1b2c3d4e5
Revises: f0a1b2c3d4e5
Create Date: 2026-07-29 20:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0a1b2c3d4e5"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_user_id", "workspace", ["user_id"])
    op.create_table(
        "workspace_tab",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("stable_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layout_config", sa.JSON(), nullable=False),
        sa.Column("active_window_key", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "stable_key", name="uq_workspace_tab_key"),
    )
    op.create_index("ix_workspace_tab_workspace_id", "workspace_tab", ["workspace_id"])
    op.create_table(
        "workspace_window",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tab_id", sa.Integer(), nullable=False),
        sa.Column("instance_key", sa.String(length=80), nullable=False),
        sa.Column("tool_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("link_group", sa.String(length=24), nullable=False, server_default="blue"),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("state_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tab_id"], ["workspace_tab.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tab_id", "instance_key", name="uq_workspace_window_key"),
    )
    op.create_index("ix_workspace_window_tab_id", "workspace_window", ["tab_id"])
    op.create_table(
        "workspace_library_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("stable_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("dependency_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "stable_key", name="uq_library_item_key"),
    )
    op.create_index("ix_workspace_library_item_user_id", "workspace_library_item", ["user_id"])
    op.create_index("ix_workspace_library_item_kind", "workspace_library_item", ["kind"])
    op.create_table(
        "instrument_note",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "instrument_id", name="uq_instrument_note_user"),
    )
    op.create_index("ix_instrument_note_user_id", "instrument_note", ["user_id"])
    op.create_index("ix_instrument_note_instrument_id", "instrument_note", ["instrument_id"])
    op.create_table(
        "market_group",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stable_key", sa.String(length=80), nullable=False),
        sa.Column("group_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("representative_instrument_id", sa.Integer(), nullable=True),
        sa.Column("equal_weight_instrument_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="curated"),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["market_group.id"]),
        sa.ForeignKeyConstraint(["representative_instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equal_weight_instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stable_key"),
    )
    op.create_index("ix_market_group_group_type", "market_group", ["group_type"])
    op.create_table(
        "market_group_member",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_group_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(length=48), nullable=False, server_default="constituent"),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="curated"),
        sa.Column("verification_state", sa.String(length=40), nullable=False, server_default="unverified"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_group_id"], ["market_group.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_group_member_market_group_id", "market_group_member", ["market_group_id"])
    op.create_index("ix_market_group_member_instrument_id", "market_group_member", ["instrument_id"])
    op.create_index("ix_market_group_member_time", "market_group_member", ["market_group_id", "effective_at", "known_at"])
    op.create_table(
        "market_group_proxy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_group_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(length=48), nullable=False, server_default="industry_proxy"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="curated"),
        sa.Column("verification_state", sa.String(length=40), nullable=False, server_default="unverified"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_group_id"], ["market_group.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_group_id", "instrument_id", name="uq_market_group_proxy"),
    )
    op.create_index("ix_market_group_proxy_market_group_id", "market_group_proxy", ["market_group_id"])
    op.create_index("ix_market_group_proxy_instrument_id", "market_group_proxy", ["instrument_id"])


def downgrade() -> None:
    op.drop_index("ix_market_group_proxy_instrument_id", table_name="market_group_proxy")
    op.drop_index("ix_market_group_proxy_market_group_id", table_name="market_group_proxy")
    op.drop_table("market_group_proxy")
    op.drop_index("ix_market_group_member_time", table_name="market_group_member")
    op.drop_index("ix_market_group_member_instrument_id", table_name="market_group_member")
    op.drop_index("ix_market_group_member_market_group_id", table_name="market_group_member")
    op.drop_table("market_group_member")
    op.drop_index("ix_market_group_group_type", table_name="market_group")
    op.drop_table("market_group")
    op.drop_index("ix_instrument_note_instrument_id", table_name="instrument_note")
    op.drop_index("ix_instrument_note_user_id", table_name="instrument_note")
    op.drop_table("instrument_note")
    op.drop_index("ix_workspace_library_item_kind", table_name="workspace_library_item")
    op.drop_index("ix_workspace_library_item_user_id", table_name="workspace_library_item")
    op.drop_table("workspace_library_item")
    op.drop_index("ix_workspace_window_tab_id", table_name="workspace_window")
    op.drop_table("workspace_window")
    op.drop_index("ix_workspace_tab_workspace_id", table_name="workspace_tab")
    op.drop_table("workspace_tab")
    op.drop_index("ix_workspace_user_id", table_name="workspace")
    op.drop_table("workspace")
