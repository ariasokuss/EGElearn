"""add_user_activity_events

Revision ID: 9df4b23ac1d0
Revises: 7c8b0a8190b1
Create Date: 2026-05-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9df4b23ac1d0"
down_revision: Union[str, None] = "7c8b0a8190b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_activity_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_group", sa.String(length=32), nullable=False),
        sa.Column("request_path", sa.String(length=500), nullable=True),
        sa.Column("http_method", sa.String(length=12), nullable=True),
        sa.Column("route_label", sa.String(length=255), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("folder_id", sa.UUID(), nullable=True),
        sa.Column("lesson_id", sa.UUID(), nullable=True),
        sa.Column("test_session_id", sa.UUID(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(none_as_null=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_activity_events_user_id", "user_activity_events", ["user_id"], unique=False)
    op.create_index("ix_user_activity_events_event_type", "user_activity_events", ["event_type"], unique=False)
    op.create_index("ix_user_activity_events_event_group", "user_activity_events", ["event_group"], unique=False)
    op.create_index("ix_user_activity_user_created", "user_activity_events", ["user_id", "created_at"], unique=False)
    op.create_index("ix_user_activity_user_type_created", "user_activity_events", ["user_id", "event_type", "created_at"], unique=False)
    op.create_index("ix_user_activity_test_session", "user_activity_events", ["test_session_id"], unique=False)
    op.create_index("ix_user_activity_lesson", "user_activity_events", ["lesson_id"], unique=False)
    op.create_index("ix_user_activity_folder", "user_activity_events", ["folder_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_activity_folder", table_name="user_activity_events")
    op.drop_index("ix_user_activity_lesson", table_name="user_activity_events")
    op.drop_index("ix_user_activity_test_session", table_name="user_activity_events")
    op.drop_index("ix_user_activity_user_type_created", table_name="user_activity_events")
    op.drop_index("ix_user_activity_user_created", table_name="user_activity_events")
    op.drop_index("ix_user_activity_events_event_group", table_name="user_activity_events")
    op.drop_index("ix_user_activity_events_event_type", table_name="user_activity_events")
    op.drop_index("ix_user_activity_events_user_id", table_name="user_activity_events")
    op.drop_table("user_activity_events")
