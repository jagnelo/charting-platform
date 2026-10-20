"""Merge the released Provider and Strategy migration histories.

Revision ID: slv2_0009
Revises: b6e9a42d1c73, slv2_0008
Create Date: 2026-10-20
"""

from collections.abc import Sequence

revision: str = "slv2_0009"
down_revision: tuple[str, str] = ("b6e9a42d1c73", "slv2_0008")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the already-applied histories without changing either schema."""


def downgrade() -> None:
    """The merge point carries no schema change to reverse."""
