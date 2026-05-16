"""add is_skipped to session_answers

Revision ID: 5cc4cfd2e6ed
Revises: 725702bf1d8c
Create Date: 2026-04-27 14:35:34.914074

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5cc4cfd2e6ed'
down_revision: Union[str, None] = '725702bf1d8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('session_answers')}
    if 'is_skipped' not in cols:
        op.add_column(
            'session_answers',
            sa.Column('is_skipped', sa.Boolean(), server_default='false', nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('session_answers')}
    if 'is_skipped' in cols:
        op.drop_column('session_answers', 'is_skipped')
