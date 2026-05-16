"""add_pending_email_changes

Revision ID: ecdd360ff44b
Revises: dee84a70062b
Create Date: 2026-04-05 09:43:16.603843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ecdd360ff44b'
down_revision: Union[str, None] = 'dee84a70062b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('pending_email_changes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('new_email', sa.String(length=255), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pending_email_changes_user_id'), 'pending_email_changes', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pending_email_changes_user_id'), table_name='pending_email_changes')
    op.drop_table('pending_email_changes')
