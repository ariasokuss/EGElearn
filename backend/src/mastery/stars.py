"""Star evaluation — independent completion badges based on real performance."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.learning.models import FeynmanSession, LessonProgress
from src.learning.tests.models import TestSession, TestTemplate


@dataclass
class StarEvaluation:
    study: bool = False
    feynman: bool = False
    test: bool = False

    @property
    def stars(self) -> int:
        return sum([self.study, self.feynman, self.test])


async def evaluate_stars(
    db: AsyncSession,
    lesson_id: uuid.UUID,
    user_id: uuid.UUID,
) -> StarEvaluation:
    """Evaluate all three stars based on actual performance data.

    Stars are independent — each can be earned separately.
    Checks BEST attempt across all sessions (not just the latest).
    """
    result = StarEvaluation()

    result.study = await _check_study_star(db, lesson_id, user_id)
    result.feynman = await _check_feynman_star(db, lesson_id, user_id)
    result.test = await _check_test_star(db, lesson_id, user_id)

    return result


async def _check_study_star(
    db: AsyncSession,
    lesson_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Study star: inline questions avg ≥ 70% AND all mini-feynmans ≥ 2/3 covered.

    If no feynman blocks exist for this lesson, the mini-feynman requirement
    is waived — inline quiz score alone is sufficient.
    """
    from src.learning.models import FeynmanBlock

    # ── Check inline quiz score ──
    template_result = await db.execute(
        select(TestTemplate.id).where(
            TestTemplate.lesson_id == lesson_id,
            TestTemplate.type == "inline_quiz",
        )
    )
    template_ids = list(template_result.scalars().all())
    if not template_ids:
        return False

    # Find best session (graded or active with score)
    session_result = await db.execute(
        select(TestSession)
        .where(
            TestSession.template_id.in_(template_ids),
            TestSession.user_id == user_id,
            TestSession.status.in_(["graded", "active"]),
        )
        .order_by(TestSession.score.desc())
    )
    sessions = list(session_result.scalars().all())
    if not sessions:
        return False

    inline_ok = any(s.score is not None and s.score >= 0.7 for s in sessions)
    if not inline_ok:
        return False

    # ── Check if feynman blocks exist ──
    feynman_block_count = await db.scalar(
        select(func.count(FeynmanBlock.id)).where(
            FeynmanBlock.lesson_id == lesson_id,
        )
    )
    if not feynman_block_count:
        # No feynman blocks — inline quiz alone earns the study star
        return True

    # ── Check mini-feynmans ──
    mini_sessions_result = await db.execute(
        select(FeynmanSession)
        .join(FeynmanBlock, FeynmanSession.feynman_block_id == FeynmanBlock.id)
        .where(
            FeynmanBlock.lesson_id == lesson_id,
            FeynmanSession.user_id == user_id,
            FeynmanSession.type == "mini",
            FeynmanSession.status == "completed",
        )
    )
    mini_sessions = list(mini_sessions_result.scalars().all())
    if not mini_sessions:
        # No mini-feynman sessions completed — inline quiz alone is enough
        return True

    # Group by feynman_block_id, take best per block
    best_per_block: dict[uuid.UUID, FeynmanSession] = {}
    for s in mini_sessions:
        block_id = s.feynman_block_id
        if block_id not in best_per_block:
            best_per_block[block_id] = s
        else:
            current_covered = sum(1 for p in (s.covered_points or []) if p)
            best_covered = sum(
                1 for p in (best_per_block[block_id].covered_points or []) if p
            )
            if current_covered > best_covered:
                best_per_block[block_id] = s

    for block_id, session in best_per_block.items():
        points = session.covered_points or []
        total = len(points)
        if total == 0:
            continue
        covered = sum(1 for p in points if p)
        required = math.ceil(2 / 3 * total)
        if covered < required:
            return False

    return True


async def _check_feynman_star(
    db: AsyncSession,
    lesson_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Feynman star: end-of-lesson feynman with ALL points ≥ 3/5."""
    from src.learning.models import FeynmanBlock

    sessions_result = await db.execute(
        select(FeynmanSession)
        .join(FeynmanBlock, FeynmanSession.feynman_block_id == FeynmanBlock.id)
        .where(
            FeynmanBlock.lesson_id == lesson_id,
            FeynmanSession.user_id == user_id,
            FeynmanSession.type == "standard",
            FeynmanSession.status.in_(["completed", "aborted"]),
        )
    )
    sessions = list(sessions_result.scalars().all())
    if not sessions:
        return False

    # Check if ANY session has all points ≥ 3
    for session in sessions:
        points = session.covered_points or []
        if not points:
            continue
        if all(isinstance(p, (int, float)) and p >= 3 for p in points):
            return True

    return False


async def _check_test_star(
    db: AsyncSession,
    lesson_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Test star: lesson test with score ≥ 70%."""
    result = await db.execute(
        select(TestSession.score)
        .join(TestTemplate, TestSession.template_id == TestTemplate.id)
        .where(
            TestTemplate.lesson_id == lesson_id,
            TestTemplate.type == "lesson_test",
            TestSession.user_id == user_id,
            TestSession.status == "graded",
        )
    )
    scores = list(result.scalars().all())
    return any(s is not None and s >= 0.7 for s in scores)


async def sync_stars_to_progress(
    db: AsyncSession,
    lesson_id: uuid.UUID,
    user_id: uuid.UUID,
    stars: StarEvaluation,
) -> None:
    """Update LessonProgress with star evaluation results.

    Stars live only on lessons, not on roadmap nodes.
    Roadmap nodes track mastery % only (via the mastery engine).
    Backward-compatible: works before and after the mastery migration.
    """
    lp_result = await db.execute(
        select(LessonProgress).where(
            LessonProgress.lesson_id == lesson_id,
            LessonProgress.user_id == user_id,
        )
    )
    lp = lp_result.scalar_one_or_none()
    if lp:
        if stars.stars > lp.stars:
            # In-flight popup fires from this same update path; mark as
            # shown so a subsequent page reload doesn't replay it.
            lp.star_reward_shown = True
        lp.stars = stars.stars
        # New columns — write only if migration has run
        try:
            lp.study_star = stars.study
            lp.feynman_star = stars.feynman
            lp.test_star = stars.test
        except AttributeError:
            pass
    else:
        lp = LessonProgress(
            lesson_id=lesson_id,
            user_id=user_id,
            stars=stars.stars,
            star_reward_shown=stars.stars > 0,
        )
        # New columns — set only if migration has run
        try:
            lp.study_star = stars.study
            lp.feynman_star = stars.feynman
            lp.test_star = stars.test
        except AttributeError:
            pass
        db.add(lp)
