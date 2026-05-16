"""Lesson results aggregation — combines Feynman session scores and test scores."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

from sqlalchemy import select, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.schemas import LessonResultBreakdown, LessonResultRead
from src.learning.service import LearningService
from src.mastery.stars import evaluate_stars

logger = logging.getLogger(__name__)

_MAX_THEME_POINTS = 5

# In-memory cache for LLM-generated descriptions (TTL = 1 hour)
_DESCRIPTION_CACHE: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 3600  # seconds


class LessonResultsService:
    def __init__(
        self,
        learning_service: LearningService,
        llm: YandexGPTLLMGateway | None = None,
        usage_service: object | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        self._learning = learning_service
        self._llm = llm or YandexGPTLLMGateway()
        self._usage_service = usage_service
        self._db = db

    async def get_lesson_results(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID
    ) -> LessonResultRead:
        self._current_user_id = user_id

        # Evaluate stars (independent of scoring)
        real_stars = 0
        if self._db is not None:
            star_eval = await evaluate_stars(self._db, lesson_id, user_id)
            real_stars = star_eval.stars

        # Load lesson blocks (parts)
        blocks = await self._load_lesson_blocks(lesson_id)
        if not blocks:
            return LessonResultRead(
                earned_marks=0, total_marks=0, percent=0.0,
                stars=real_stars, breakdown=[], need_review=[],
            )

        # Build lookup maps
        uuid_map = {str(b.id): b for b in blocks}
        slug_map = {b.block_id: b for b in blocks if b.block_id}

        # Gather per-block scores from all 4 sources
        per_block: dict[int, list[int]] = {
            b.block_number: [0, 0] for b in blocks
        }
        has_user_activity = False

        # 1) Standard feynman
        feynman_session = await self._learning.get_latest_standard_session(
            lesson_id, user_id
        )
        if feynman_session and feynman_session.covered_points:
            has_user_activity = True
            fb = feynman_session.feynman_block
            for score, block_num in zip(feynman_session.covered_points, fb.scope):
                if score is None or block_num not in per_block:
                    continue
                per_block[block_num][0] += min(int(score), _MAX_THEME_POINTS)
                per_block[block_num][1] += _MAX_THEME_POINTS

        # 2) Mini feynman
        mini_scores = await self._get_mini_feynman_by_block(lesson_id, user_id)
        if mini_scores:
            has_user_activity = True
        for block_num, (earned, total) in mini_scores.items():
            if block_num in per_block:
                per_block[block_num][0] += earned
                per_block[block_num][1] += total

        # 3) Inline quiz
        inline_scores = await self._get_inline_scores_by_block(lesson_id, user_id)
        if inline_scores:
            has_user_activity = True
        for block_uuid_str, (earned, total) in inline_scores.items():
            block = uuid_map.get(block_uuid_str)
            if block and block.block_number in per_block:
                per_block[block.block_number][0] += earned
                per_block[block.block_number][1] += total

        # 4) Lesson test — earned marks from user's attempt
        test_scores = await self._get_test_scores_by_source(lesson_id, user_id)
        if test_scores:
            has_user_activity = True
        for slug, (earned, total) in test_scores.items():
            block = slug_map.get(slug)
            if block and block.block_number in per_block:
                per_block[block.block_number][0] += earned
                per_block[block.block_number][1] += total

        # 5) Include unattempted test totals in denominator so blocks
        #    aren't inflated when the test hasn't been taken yet.
        test_totals = await self._get_test_totals_by_source(lesson_id)
        for slug, total_marks in test_totals.items():
            if slug in test_scores:
                continue  # already counted from actual attempt
            block = slug_map.get(slug)
            if block and block.block_number in per_block:
                per_block[block.block_number][1] += total_marks

        # Build breakdown — only blocks with at least one assessment
        scored_blocks = [
            (b, per_block[b.block_number])
            for b in blocks
            if per_block[b.block_number][1] > 0
        ]

        if not scored_blocks:
            return LessonResultRead(
                earned_marks=0, total_marks=0, percent=0.0,
                stars=real_stars, breakdown=[], need_review=[],
            )

        titles = [b.title or f"Part {b.block_number}" for b, _ in scored_blocks]
        percents = [
            round(earned / total * 100, 1) if total > 0 else 0.0
            for _, (earned, total) in scored_blocks
        ]

        if has_user_activity:
            descriptions = await self._generate_descriptions(titles, percents)
        else:
            descriptions = [""] * len(titles)

        total_earned = sum(et[0] for _, et in scored_blocks)
        total_marks = sum(et[1] for _, et in scored_blocks)

        # Overall percent — average across 3 lesson phases.
        # Missing phases count as 0 so completing only one phase ≈ 33%.
        inline_total = sum(t for _, t in inline_scores.values())
        inline_earned_sum = sum(e for e, _ in inline_scores.values())
        inline_pct = (inline_earned_sum / inline_total * 100) if inline_total else 0

        feynman_pct = 0.0
        if feynman_session and feynman_session.covered_points:
            fb = feynman_session.feynman_block
            evaluated = [
                min(int(s), _MAX_THEME_POINTS)
                for s in feynman_session.covered_points
                if s is not None
            ]
            if evaluated:
                feynman_pct = sum(evaluated) / (len(evaluated) * _MAX_THEME_POINTS) * 100

        test_total_marks = sum(t for _, t in test_scores.values())
        test_earned_sum = sum(e for e, _ in test_scores.values())
        test_pct = (test_earned_sum / test_total_marks * 100) if test_total_marks else 0

        overall = round((inline_pct + feynman_pct + test_pct) / 3, 1)

        breakdown = [
            LessonResultBreakdown(
                lesson_block_id=b.id,
                title=title,
                percent=pct,
                description=desc,
            )
            for (b, _), title, pct, desc in zip(
                scored_blocks, titles, percents, descriptions
            )
        ]

        need_review = [item.title for item in breakdown if item.percent < 50]

        return LessonResultRead(
            earned_marks=total_earned,
            total_marks=total_marks,
            percent=overall,
            stars=real_stars,
            breakdown=breakdown,
            need_review=need_review,
        )

    async def _load_lesson_blocks(
        self, lesson_id: uuid.UUID,
    ) -> list:
        """Load all non-intro, non-summary lesson blocks."""
        from src.learning.models import LessonBlock

        if self._db is None:
            return []
        blocks = (await self._db.execute(
            sa_select(LessonBlock).where(
                LessonBlock.lesson_id == lesson_id,
                LessonBlock.user_id.is_(None),
                LessonBlock.is_summary.isnot(True),
                LessonBlock.block_number > 0,
            ).order_by(LessonBlock.block_number)
        )).scalars().all()
        return list(blocks)

    async def _generate_descriptions(
        self, titles: list[str], percents: list[float]
    ) -> list[str]:
        # Build a stable cache key from rounded percents + titles
        key_parts = "|".join(
            f"{title}:{round(pct)}" for title, pct in zip(titles, percents)
        )
        cache_key = hashlib.sha256(key_parts.encode()).hexdigest()[:24]

        # Check cache
        cached = _DESCRIPTION_CACHE.get(cache_key)
        if cached is not None:
            ts, descriptions = cached
            if time.monotonic() - ts < _CACHE_TTL:
                return descriptions
            del _DESCRIPTION_CACHE[cache_key]

        lines = "\n".join(
            f"- {title}: {round(pct)}%" for title, pct in zip(titles, percents)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a concise educational feedback generator. "
                    "Given a student's score (0–100%) for each topic in a lesson, "
                    "write a short 1–2 sentence feedback per topic. "
                    "Be encouraging but honest. "
                    'Return a JSON object with key "descriptions" containing an array of strings, '
                    "one per topic, in the same order. Return valid JSON only, no markdown."
                ),
            },
            {
                "role": "user",
                "content": f"The student scored:\n{lines}\n\nGenerate one description per topic.",
            },
        ]
        try:
            raw, _usage = await self._llm.chat_complete(messages)
            if self._usage_service and hasattr(self, '_current_user_id'):
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="results", usage=_usage,
                )
            data = json.loads(raw.strip())
            descriptions = data["descriptions"]
            if len(descriptions) < len(titles):
                descriptions += [""] * (len(titles) - len(descriptions))
            result = descriptions[: len(titles)]
            # Cache the result
            _DESCRIPTION_CACHE[cache_key] = (time.monotonic(), result)
            return result
        except Exception as exc:
            logger.exception("Description generation failed: %s", exc)
            return [""] * len(titles)

    async def _get_inline_scores_by_block(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID,
    ) -> dict[str, tuple[int, int]]:
        """Return {block_uuid_str: (earned, total)} from the best inline quiz session."""
        from src.learning.tests.models import (
            SessionAnswer, TestQuestion, TestSession, TestTemplate,
        )

        if self._db is None:
            return {}

        test_session = await self._db.scalar(
            select(TestSession)
            .join(TestTemplate)
            .where(
                TestTemplate.lesson_id == lesson_id,
                TestTemplate.type == "inline_quiz",
                TestSession.user_id == user_id,
                TestSession.status.in_(["graded", "active"]),
                TestSession.score.isnot(None),
            )
            .order_by(TestSession.score.desc())
        )
        if test_session is None:
            return {}

        answers = (await self._db.execute(
            select(SessionAnswer)
            .join(TestQuestion)
            .where(
                SessionAnswer.session_id == test_session.id,
                SessionAnswer.graded_at.isnot(None),
            )
            .options(selectinload(SessionAnswer.question))
        )).scalars().all()

        result: dict[str, tuple[int, int]] = {}
        for ans in answers:
            key = ans.question.inline_key
            if not key:
                continue
            block_uuid_str = key.split(":")[0]
            earned, total = result.get(block_uuid_str, (0, 0))
            result[block_uuid_str] = (
                earned + (ans.earned_marks or 0),
                total + ans.question.points,
            )
        return result

    async def _get_test_scores_by_source(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID,
    ) -> dict[str, tuple[int, int]]:
        """Return {block_slug: (earned, total)} from the latest graded lesson test."""
        from src.learning.tests.models import (
            SessionAnswer, TestQuestion, TestSession, TestTemplate,
        )

        if self._db is None:
            return {}

        test_session = await self._db.scalar(
            select(TestSession)
            .join(TestTemplate)
            .where(
                TestTemplate.lesson_id == lesson_id,
                TestTemplate.type == "lesson_test",
                TestSession.user_id == user_id,
                TestSession.status == "graded",
            )
            .order_by(TestSession.graded_at.desc())
        )
        if test_session is None:
            return {}

        answers = (await self._db.execute(
            select(SessionAnswer)
            .join(TestQuestion)
            .where(
                SessionAnswer.session_id == test_session.id,
                SessionAnswer.graded_at.isnot(None),
            )
            .options(selectinload(SessionAnswer.question))
        )).scalars().all()

        result: dict[str, tuple[int, int]] = {}
        for ans in answers:
            sources = ans.question.sources
            if not sources:
                continue
            slug = sources[0]
            earned, total = result.get(slug, (0, 0))
            result[slug] = (
                earned + (ans.earned_marks or 0),
                total + ans.question.points,
            )
        return result

    async def _get_test_totals_by_source(
        self, lesson_id: uuid.UUID,
    ) -> dict[str, int]:
        """Return {block_slug: total_marks} from the lesson test template.

        This counts potential marks per block regardless of whether the user
        attempted the test, so unattempted blocks still have a denominator.
        """
        from src.learning.tests.models import TestQuestion, TestTemplate

        if self._db is None:
            return {}

        template = await self._db.scalar(
            select(TestTemplate).where(
                TestTemplate.lesson_id == lesson_id,
                TestTemplate.type == "lesson_test",
                TestTemplate.user_id.is_(None),
            )
        )
        if template is None:
            return {}

        questions = (await self._db.execute(
            select(TestQuestion).where(TestQuestion.template_id == template.id)
        )).scalars().all()

        result: dict[str, int] = {}
        for q in questions:
            if not q.sources:
                continue
            slug = q.sources[0]
            result[slug] = result.get(slug, 0) + q.points
        return result

    async def _get_mini_feynman_by_block(
        self, lesson_id: uuid.UUID, user_id: uuid.UUID,
    ) -> dict[int, tuple[int, int]]:
        """Return {block_number: (earned, total)} from best mini-feynman per block."""
        from src.learning.models import FeynmanBlock, FeynmanSession

        if self._db is None:
            return {}

        sessions = (await self._db.execute(
            select(FeynmanSession)
            .join(FeynmanBlock)
            .where(
                FeynmanBlock.lesson_id == lesson_id,
                FeynmanSession.user_id == user_id,
                FeynmanSession.type == "mini",
                FeynmanSession.status == "completed",
            )
            .options(selectinload(FeynmanSession.feynman_block))
        )).scalars().all()

        best: dict[uuid.UUID, FeynmanSession] = {}
        for s in sessions:
            bid = s.feynman_block_id
            if bid not in best:
                best[bid] = s
            else:
                cur = sum(1 for p in (s.covered_points or []) if p)
                prev = sum(1 for p in (best[bid].covered_points or []) if p)
                if cur > prev:
                    best[bid] = s

        result: dict[int, tuple[int, int]] = {}
        for s in best.values():
            fb = s.feynman_block
            for scope_idx, block_num in enumerate(fb.scope):
                if scope_idx >= len(s.covered_points or []):
                    continue
                covered = s.covered_points[scope_idx]
                earned = 1 if covered else 0
                prev_earned, prev_total = result.get(block_num, (0, 0))
                result[block_num] = (prev_earned + earned, prev_total + 1)
        return result
