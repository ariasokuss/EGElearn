"""add_lesson_access_events

Revision ID: 5f9d1c2b7e41
Revises: bd35b64317a2
Create Date: 2026-04-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5f9d1c2b7e41"
down_revision: Union[str, None] = "bd35b64317a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lesson_access_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lesson_id",
            "user_id",
            name="uq_lesson_access_lesson_user",
        ),
    )
    op.create_index(
        "ix_lesson_access_events_lesson_id",
        "lesson_access_events",
        ["lesson_id"],
        unique=False,
    )
    op.create_index(
        "ix_lesson_access_events_user_id",
        "lesson_access_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_lesson_access_user_last_accessed_at",
        "lesson_access_events",
        ["user_id", "last_accessed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lesson_access_user_last_accessed_at",
        table_name="lesson_access_events",
    )
    op.drop_index("ix_lesson_access_events_user_id", table_name="lesson_access_events")
    op.drop_index("ix_lesson_access_events_lesson_id", table_name="lesson_access_events")
    op.drop_table("lesson_access_events")
