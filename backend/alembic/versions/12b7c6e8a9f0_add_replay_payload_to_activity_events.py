"""add_replay_payload_to_activity_events

Revision ID: 12b7c6e8a9f0
Revises: 9df4b23ac1d0
Create Date: 2026-05-05 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "12b7c6e8a9f0"
down_revision: Union[str, None] = "9df4b23ac1d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_activity_events",
        sa.Column(
            "replay_payload",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_activity_events", "replay_payload")
