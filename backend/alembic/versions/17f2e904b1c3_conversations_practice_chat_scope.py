"""conversations practice chat scope

Revision ID: 17f2e904b1c3
Revises: 012fa0498b24
Create Date: 

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "17f2e904b1c3"
down_revision: Union[str, None] = "012fa0498b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("test_session_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("question_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_conversations_test_session_id"),
        "conversations",
        ["test_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversations_question_id"),
        "conversations",
        ["question_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_conversations_practice_scope_pair",
        "conversations",
        "(test_session_id IS NULL AND question_id IS NULL) OR "
        "(test_session_id IS NOT NULL AND question_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversations_practice_scope_pair",
        "conversations",
        type_="check",
    )
    op.drop_index(op.f("ix_conversations_question_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_test_session_id"), table_name="conversations")
    op.drop_column("conversations", "question_id")
    op.drop_column("conversations", "test_session_id")
