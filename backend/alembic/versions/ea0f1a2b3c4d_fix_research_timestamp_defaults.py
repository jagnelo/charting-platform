"""add server-side timestamps to unified code and research rows

Revision ID: ea0f1a2b3c4d
Revises: e9f0a1b2c3d4
Create Date: 2026-08-04 21:20:00.000000

The original unified-code migration declared these timestamp columns as
non-nullable but omitted their PostgreSQL defaults.  SQLAlchemy's model
defaults therefore worked in fixture databases while real PostgreSQL inserts
failed before Study Lab could create an asset.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ea0f1a2b3c4d"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("code_asset", "code_version", "research_run", "research_artifact")


def upgrade() -> None:
    for table in _TABLES:
        for column in ("created_at", "updated_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=sa.func.now(),
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        for column in ("updated_at", "created_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=None,
            )
