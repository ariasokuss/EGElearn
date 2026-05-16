from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


class AdminIPBlacklist(Base):
    __tablename__ = "admin_ip_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ip: Mapped[str] = mapped_column(String(45), unique=True, nullable=False, index=True)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class AdminBruteForceGuard:
    """Tracks failed admin login attempts per IP.

    Failed counts are in-memory (reset on restart; that's fine — attackers
    just have to try again). The blacklist is persisted in Postgres so it
    survives restarts and devs can remove IPs via SQL.
    """

    def __init__(self) -> None:
        self._failed: dict[str, int] = {}

    async def is_blacklisted(
        self, ip: str, session_factory: async_sessionmaker[AsyncSession]
    ) -> bool:
        async with session_factory() as session:
            result = await session.execute(
                select(AdminIPBlacklist).where(AdminIPBlacklist.ip == ip)
            )
            return result.scalar_one_or_none() is not None

    async def record_failure(
        self,
        ip: str,
        threshold: int,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> bool:
        """Increment failure counter. Returns True if the IP was just blacklisted."""
        count = self._failed.get(ip, 0) + 1
        self._failed[ip] = count
        if count >= threshold:
            await self._persist_blacklist(
                ip,
                f"Too many failed admin login attempts ({count})",
                session_factory,
            )
            self._failed.pop(ip, None)
            return True
        return False

    def record_success(self, ip: str) -> None:
        self._failed.pop(ip, None)

    async def _persist_blacklist(
        self,
        ip: str,
        reason: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as session:
            existing = await session.execute(
                select(AdminIPBlacklist).where(AdminIPBlacklist.ip == ip)
            )
            if existing.scalar_one_or_none() is None:
                session.add(AdminIPBlacklist(ip=ip, reason=reason))
                await session.commit()
