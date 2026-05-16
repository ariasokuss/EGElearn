"""add is_canonical to test_templates

Revision ID: 8aef54f52466
Revises: b3a2c5e579a7
Create Date: 2026-05-01 08:47:02.742166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8aef54f52466'
down_revision: Union[str, None] = 'b3a2c5e579a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'test_templates',
        sa.Column(
            'is_canonical',
            sa.Boolean(),
            server_default='false',
            nullable=False,
        ),
    )
    op.create_index(
        'ix_test_templates_canonical_sha',
        'test_templates',
        ['source_pdf_sha256'],
        unique=False,
        postgresql_where=sa.text('is_canonical = true'),
    )


def downgrade() -> None:
    op.drop_index(
        'ix_test_templates_canonical_sha',
        table_name='test_templates',
        postgresql_where=sa.text('is_canonical = true'),
    )
    op.drop_column('test_templates', 'is_canonical')
