"""Join accepted TC and Strategy migration histories without DDL.

Revision ID: slv2_0011
Revises: e9c23a7b1d40, slv2_0010
Create Date: 2026-10-22
"""

from collections.abc import Sequence

revision: str = "slv2_0011"
down_revision: tuple[str, str] = ("e9c23a7b1d40", "slv2_0010")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join accepted histories; their schema changes are independently additive."""


def downgrade() -> None:
    """The merge point carries no schema change to reverse."""
