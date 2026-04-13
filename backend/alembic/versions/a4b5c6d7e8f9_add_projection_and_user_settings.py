"""add projection and user settings persistence

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-04-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    price_alert_cols = {col["name"] for col in inspector.get_columns("price_alert")}
    if "show_projection" not in price_alert_cols:
        op.add_column(
            "price_alert",
            sa.Column(
                "show_projection",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    user_cols = {col["name"] for col in inspector.get_columns("user")}
    if "settings" not in user_cols:
        op.add_column(
            "user",
            sa.Column(
                "settings",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'::json"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_cols = {col["name"] for col in inspector.get_columns("user")}
    if "settings" in user_cols:
        op.drop_column("user", "settings")

    price_alert_cols = {col["name"] for col in inspector.get_columns("price_alert")}
    if "show_projection" in price_alert_cols:
        op.drop_column("price_alert", "show_projection")
