"""merge alert firing events and radar tables

Revision ID: 40b528649be0
Revises: b3c4d5e6f7a8, b7c8d9e0f1a2
Create Date: 2026-05-05 10:51:56.313779

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '40b528649be0'
down_revision: Union[str, None] = ('b3c4d5e6f7a8', 'b7c8d9e0f1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
