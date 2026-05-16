"""add_display_name_avatar_to_users

Revision ID: dee84a70062b
Revises: c46fa3c86dd4
Create Date: 2026-04-05 08:46:05.161194

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dee84a70062b'
down_revision: Union[str, None] = 'c46fa3c86dd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('display_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('avatar_s3_key', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_s3_key')
    op.drop_column('users', 'display_name')
