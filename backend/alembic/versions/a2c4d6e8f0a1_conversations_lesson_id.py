"""conversations lesson_id for per-lesson chat

Revision ID: a2c4d6e8f0a1
Revises: 3041cec3a8b5
Create Date: 2026-04-04 03:30:36.742321

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a2c4d6e8f0a1"
down_revision: Union[str, None] = "3041cec3a8b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("lesson_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_lesson_id_lessons",
        "conversations",
        "lessons",
        ["lesson_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_conversations_lesson_id"),
        "conversations",
        ["lesson_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_conversations_lesson_vs_practice",
        "conversations",
        "lesson_id IS NULL OR (test_session_id IS NULL AND question_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversations_lesson_vs_practice",
        "conversations",
        type_="check",
    )
    op.drop_index(op.f("ix_conversations_lesson_id"), table_name="conversations")
    op.drop_constraint(
        "fk_conversations_lesson_id_lessons",
        "conversations",
        type_="foreignkey",
    )
    op.drop_column("conversations", "lesson_id")
