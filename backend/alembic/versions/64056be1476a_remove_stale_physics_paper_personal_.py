"""remove stale physics paper personal exams

Revision ID: 64056be1476a
Revises: 3c0568a155b1
Create Date: 2026-04-30 01:43:12.223744

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64056be1476a'
down_revision: Union[str, None] = '3c0568a155b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop personal exams left over from when the Physics optional-themes title
    # was "Physics paper". They sit in AQA A-Level Physics folders, are tagged
    # with the .929929 sentinel exam_date, and are now superseded by the
    # renamed "Paper 3 Practical Skills and Option Topic" upsert flow.
    op.execute(
        sa.text(
            """
            DELETE FROM exams e
            USING folders f
            WHERE e.folder_id = f.id
              AND f.name = 'AQA A-Level Physics'
              AND e.user_id IS NOT NULL
              AND e.name = 'Physics paper'
              AND (date_part('microseconds', e.exam_date)::bigint % 1000000) = 929929
            """
        )
    )


def downgrade() -> None:
    # Data deletion is not reversible; no-op.
    pass
