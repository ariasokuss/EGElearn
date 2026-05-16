"""Database operations for lesson highlights."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.learning.highlights.models import LessonHighlight


class HighlightService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        user_id: uuid.UUID,
        lesson_id: uuid.UUID,
        text: str,
        comment: str | None = None,
    ) -> LessonHighlight:
        async with self._session_factory() as session:
            highlight = LessonHighlight(
                user_id=user_id,
                lesson_id=lesson_id,
                text=text,
                comment=comment or None,
            )
            session.add(highlight)
            await session.commit()
            await session.refresh(highlight)
            return highlight

    async def list_by_lesson(
        self,
        user_id: uuid.UUID,
        lesson_id: uuid.UUID,
        type_filter: str | None = None,
    ) -> list[LessonHighlight]:
        async with self._session_factory() as session:
            stmt = select(LessonHighlight).where(
                LessonHighlight.user_id == user_id,
                LessonHighlight.lesson_id == lesson_id,
            )
            if type_filter == "highlight":
                stmt = stmt.where(
                    (LessonHighlight.comment.is_(None))
                    | (LessonHighlight.comment == "")
                )
            elif type_filter == "note":
                stmt = stmt.where(
                    LessonHighlight.comment.isnot(None),
                    LessonHighlight.comment != "",
                )
            stmt = stmt.order_by(LessonHighlight.created_at.asc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_all(
        self,
        user_id: uuid.UUID,
        type_filter: str | None = None,
    ) -> list[LessonHighlight]:
        async with self._session_factory() as session:
            stmt = select(LessonHighlight).where(
                LessonHighlight.user_id == user_id,
            )
            if type_filter == "highlight":
                stmt = stmt.where(
                    (LessonHighlight.comment.is_(None))
                    | (LessonHighlight.comment == "")
                )
            elif type_filter == "note":
                stmt = stmt.where(
                    LessonHighlight.comment.isnot(None),
                    LessonHighlight.comment != "",
                )
            stmt = stmt.order_by(LessonHighlight.created_at.desc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def patch(
        self,
        highlight_id: uuid.UUID,
        user_id: uuid.UUID,
        comment: str | None,
    ) -> LessonHighlight | None:
        async with self._session_factory() as session:
            stmt = select(LessonHighlight).where(
                LessonHighlight.id == highlight_id,
                LessonHighlight.user_id == user_id,
            )
            result = await session.execute(stmt)
            highlight = result.scalar_one_or_none()
            if highlight is None:
                return None
            highlight.comment = comment or None
            await session.commit()
            await session.refresh(highlight)
            return highlight

    async def delete(
        self,
        highlight_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        async with self._session_factory() as session:
            stmt = select(LessonHighlight).where(
                LessonHighlight.id == highlight_id,
                LessonHighlight.user_id == user_id,
            )
            result = await session.execute(stmt)
            highlight = result.scalar_one_or_none()
            if highlight is None:
                return False
            await session.delete(highlight)
            await session.commit()
            return True
