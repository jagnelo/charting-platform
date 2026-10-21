"""Join the accepted ETF and Strategy migration histories without DDL.

Revision ID: slv2_0010
Revises: d1e7f2a9c4b6, slv2_0009
Create Date: 2026-10-21
"""

from collections.abc import Sequence

revision: str = "slv2_0010"
down_revision: tuple[str, str] = ("d1e7f2a9c4b6", "slv2_0009")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the released histories; neither schema requires alteration."""


def downgrade() -> None:
    """The merge point carries no schema change to reverse."""
