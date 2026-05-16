"""add_star_reward_shown_to_lesson_progress

Revision ID: 725702bf1d8c
Revises: c6e27125ce6d
Create Date: 2026-04-27 08:57:31.547710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '725702bf1d8c'
down_revision: Union[str, None] = 'c6e27125ce6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lesson_progress',
        sa.Column(
            'star_reward_shown',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('lesson_progress', 'star_reward_shown')
