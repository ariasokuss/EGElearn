import os
import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from src.config import DatabaseSettings

# ---------------------------------------------------------------------------
# Declarative base — all ORM models import from here
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


def _postgres_wants_ssl(dsn: str) -> bool:
    """Whether to pass TLS to asyncpg.

    Railway private networking (``*.railway.internal``) is usually plain TCP; forcing TLS
    there often ends in ``Connection reset`` during SSL upgrade. Public Railway URLs
    need TLS.
    """
    flag = (os.environ.get("POSTGRES__SSL") or "").strip().lower()
    if flag in ("0", "false", "off", "disable", "no"):
        return False
    if flag in ("1", "true", "on", "require", "yes"):
        return True

    dl = dsn.lower()
    if "sslmode=require" in dl or "ssl=true" in dl:
        return True

    if "railway.internal" in dl:
        return False

    if "rlwy.net" in dl or ".railway.app" in dl:
        return True

    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"):
        return True

    return "railway" in dl


def _postgres_ssl_connect_arg(
    dsn: str,
    *,
    insecure: bool = False,
) -> bool | ssl.SSLContext:
    if not insecure:
        insecure = (os.environ.get("POSTGRES__SSL_INSECURE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return True


def create_engine(settings: DatabaseSettings, *, for_migrations: bool = False) -> AsyncEngine:
    connect_args: dict = {"timeout": int(os.environ.get("POSTGRES__CONNECT_TIMEOUT", "30"))}
    if _postgres_wants_ssl(settings.dsn):
        connect_args["ssl"] = _postgres_ssl_connect_arg(
            settings.dsn,
            insecure=settings.ssl_insecure,
        )

    engine_kw: dict = {
        "echo": settings.echo,
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if for_migrations:
        engine_kw["poolclass"] = NullPool
    else:
        engine_kw["pool_size"] = settings.pool_size
        engine_kw["max_overflow"] = settings.max_overflow

    return create_async_engine(settings.dsn, **engine_kw)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
