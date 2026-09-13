"""Merge the provider-platform migration heads.

This is a schema-neutral merge boundary for the independent provider-platform
branches that were added on top of the staging graph.  The migration keeps the
already-applied schema changes intact while restoring one deterministic Alembic
head for compatibility and deployment checks.
"""

from collections.abc import Sequence

revision: str = "bc2d3e4f5a6b"
down_revision: tuple[str, str] = (
    "5f6a7b8c9d0e",
    "b4c5d6e7f8a9",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
