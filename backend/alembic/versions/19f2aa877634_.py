"""empty message

Revision ID: 19f2aa877634
Revises: d4e5f6a7b8c9, e1f2a3b4c5d6
Create Date: 2026-04-06 16:21:25.219813

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '19f2aa877634'
down_revision: Union[str, None] = ('d4e5f6a7b8c9', 'e1f2a3b4c5d6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
