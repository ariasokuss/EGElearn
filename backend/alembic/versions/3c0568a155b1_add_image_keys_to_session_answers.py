"""add_image_keys_to_session_answers

Revision ID: 3c0568a155b1
Revises: 5cc4cfd2e6ed
Create Date: 2026-04-28 22:53:14.892504

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c0568a155b1'
down_revision: Union[str, None] = '5cc4cfd2e6ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_answers', sa.Column('image_keys', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('session_answers', 'image_keys')
