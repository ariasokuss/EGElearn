"""rename_feynman_services

Revision ID: deb7186c2ce2
Revises: 38e3a698a91f
Create Date: 2026-04-17 10:31:42.730052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'deb7186c2ce2'
down_revision: Union[str, None] = '38e3a698a91f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE prompts SET service = 'mini_feynman' WHERE service = 'feynman'")
    op.execute("UPDATE prompts SET service = 'feynman' WHERE service = 'feynman_standard'")


def downgrade() -> None:
    op.execute("UPDATE prompts SET service = 'feynman_standard' WHERE service = 'feynman'")
    op.execute("UPDATE prompts SET service = 'feynman' WHERE service = 'mini_feynman'")
