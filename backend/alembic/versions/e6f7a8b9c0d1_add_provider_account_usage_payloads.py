"""Retain raw provider account-usage payloads and safe capacity headers."""

from collections.abc import Sequence
import json

import sqlalchemy as sa

from alembic import op


revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_account_usage_observation",
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "provider_account_usage_observation",
        sa.Column(
            "response_headers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT payload, response_headers "
        "FROM provider_account_usage_observation"
    ).fetchall()
    for payload, response_headers in rows:
        for value, field in ((payload, "payload"), (response_headers, "response_headers")):
            if value in (None, "", "{}"):
                continue
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"refusing to downgrade: account-usage {field} is not valid JSON"
                    ) from exc
            if value:
                raise RuntimeError(
                    f"refusing to downgrade: account-usage {field} evidence would be lost"
                )
    op.drop_column("provider_account_usage_observation", "response_headers")
    op.drop_column("provider_account_usage_observation", "payload")
