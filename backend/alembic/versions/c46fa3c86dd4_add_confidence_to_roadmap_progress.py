"""add_confidence_to_roadmap_progress

Revision ID: c46fa3c86dd4
Revises: b3d5e7f9a0b2
Create Date: 2026-04-05 07:15:23.629929

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c46fa3c86dd4'
down_revision: Union[str, None] = 'b3d5e7f9a0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('roadmap_progress', sa.Column('confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('roadmap_progress', 'confidence')
