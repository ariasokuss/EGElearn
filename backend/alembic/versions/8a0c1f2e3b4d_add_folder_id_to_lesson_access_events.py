"""add_folder_id_to_lesson_access_events

Revision ID: 8a0c1f2e3b4d
Revises: 5f9d1c2b7e41
Create Date: 2026-04-24 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8a0c1f2e3b4d"
down_revision: Union[str, None] = "5f9d1c2b7e41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lesson_access_events",
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_lesson_access_events_folder_id",
        "lesson_access_events",
        ["folder_id"],
        unique=False,
    )
    op.drop_constraint("uq_lesson_access_lesson_user", "lesson_access_events", type_="unique")
    # One legacy row per (user, lesson) with folder_id IS NULL; one per folder when not null.
    op.create_index(
        "uq_lesson_access_user_lesson_no_folder",
        "lesson_access_events",
        ["user_id", "lesson_id"],
        unique=True,
        postgresql_where=sa.text("folder_id IS NULL"),
    )
    op.create_index(
        "uq_lesson_access_user_lesson_folder",
        "lesson_access_events",
        ["user_id", "lesson_id", "folder_id"],
        unique=True,
        postgresql_where=sa.text("folder_id IS NOT NULL"),
    )
    op.create_index(
        "ix_lesson_access_user_folder_last_at",
        "lesson_access_events",
        ["user_id", "folder_id", "last_accessed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_lesson_access_user_folder_last_at", table_name="lesson_access_events")
    op.drop_index("uq_lesson_access_user_lesson_folder", table_name="lesson_access_events")
    op.drop_index("uq_lesson_access_user_lesson_no_folder", table_name="lesson_access_events")
    op.create_unique_constraint(
        "uq_lesson_access_lesson_user",
        "lesson_access_events",
        ["lesson_id", "user_id"],
    )
    op.drop_index("ix_lesson_access_events_folder_id", table_name="lesson_access_events")
    op.drop_column("lesson_access_events", "folder_id")
