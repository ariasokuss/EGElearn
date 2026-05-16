"""session_ai_hint_usages

Revision ID: b3d5e7f9a0b2
Revises: a2c4d6e8f0a1
Create Date: 2026-04-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3d5e7f9a0b2"
down_revision: Union[str, None] = "a2c4d6e8f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_ai_hint_usages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["test_questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["test_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "question_id",
            name="uq_session_ai_hint_session_question",
        ),
    )
    op.create_index(
        op.f("ix_session_ai_hint_usages_session_id"),
        "session_ai_hint_usages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_ai_hint_usages_question_id"),
        "session_ai_hint_usages",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_session_ai_hint_usages_question_id"),
        table_name="session_ai_hint_usages",
    )
    op.drop_index(
        op.f("ix_session_ai_hint_usages_session_id"),
        table_name="session_ai_hint_usages",
    )
    op.drop_table("session_ai_hint_usages")
