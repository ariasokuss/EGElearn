"""stamp shared physics paper3 sentinel exam date

Revision ID: b3a2c5e579a7
Revises: 64056be1476a
Create Date: 2026-04-30 01:47:38.985076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3a2c5e579a7'
down_revision: Union[str, None] = '64056be1476a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The shared (user_id IS NULL) Physics Paper 3 was seeded with
    # exam_date '2026-06-08T09:00:00+01:00' before we introduced the
    # .929929 microsecond sentinel that marks an exam as the optional-
    # topics paper for a folder. Stamp it now so the frontend matches
    # it as the optional exam (and doesn't render an extra synthetic
    # "Paper 3" card next to it).
    op.execute(
        sa.text(
            """
            UPDATE exams e
            SET exam_date = date_trunc('second', e.exam_date) + interval '929929 microseconds'
            FROM folders f
            WHERE e.folder_id = f.id
              AND f.name = 'AQA A-Level Physics'
              AND e.user_id IS NULL
              AND e.name = 'Paper 3 Practical Skills and Option Topic'
              AND (date_part('microseconds', e.exam_date)::bigint % 1000000) <> 929929
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE exams e
            SET exam_date = date_trunc('second', e.exam_date)
            FROM folders f
            WHERE e.folder_id = f.id
              AND f.name = 'AQA A-Level Physics'
              AND e.user_id IS NULL
              AND e.name = 'Paper 3 Practical Skills and Option Topic'
              AND (date_part('microseconds', e.exam_date)::bigint % 1000000) = 929929
            """
        )
    )
