"""Retain exact SEC issuer-directory candidate rows."""

from collections.abc import Sequence
import json

import sqlalchemy as sa

from alembic import op


revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sec_issuer_directory_candidate",
        sa.Column("source_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT source_payload FROM sec_issuer_directory_candidate"
    ).fetchall()
    for (value,) in rows:
        if value in (None, "", "{}"):
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    "refusing to downgrade: SEC directory source payload is not valid JSON"
                ) from exc
        if value:
            raise RuntimeError(
                "refusing to downgrade: SEC directory source evidence would be lost"
            )
    op.drop_column("sec_issuer_directory_candidate", "source_payload")
