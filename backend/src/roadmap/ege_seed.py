from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.files.models import Folder, FolderType
from src.roadmap.ege_subjects import EGE_SUBJECT_NAMES

_EGE_SEED_ADVISORY_LOCK_KEY = 2026051601


async def _lock_ege_seed(session: AsyncSession) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(CAST(:k AS BIGINT))"),
            {"k": _EGE_SEED_ADVISORY_LOCK_KEY},
        )


async def seed_ege_subject_folders(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Create empty shared EGE subject folders without seeding roadmap content."""
    async with session_factory() as session:
        await _lock_ege_seed(session)
        existing_names = set(
            await session.scalars(
                select(Folder.name).where(
                    Folder.user_id.is_(None),
                    Folder.type == FolderType.a_level,
                    Folder.name.in_(EGE_SUBJECT_NAMES),
                )
            )
        )
        missing_names = [
            name for name in EGE_SUBJECT_NAMES if name not in existing_names
        ]
        if not missing_names:
            return

        created_at = datetime.now(UTC)
        for offset, name in enumerate(missing_names):
            timestamp = created_at + timedelta(microseconds=offset)
            session.add(
                Folder(
                    user_id=None,
                    name=name,
                    type=FolderType.a_level,
                    pqg_service=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )

        await session.commit()
