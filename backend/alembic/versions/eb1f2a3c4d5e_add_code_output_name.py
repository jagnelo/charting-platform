"""add immutable selected output name to code versions

Revision ID: eb1f2a3c4d5e
Revises: ea0f1a2b3c4d
Create Date: 2026-08-06 20:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "eb1f2a3c4d5e"
down_revision: str | None = "ea0f1a2b3c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("code_version", sa.Column("output_name", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("code_version", "output_name")
