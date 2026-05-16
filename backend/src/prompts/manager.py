import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.prompts.models import PromptModel

logger = logging.getLogger(__name__)


class PromptNotFoundError(Exception):
    def __init__(self, service: str, key: str) -> None:
        self.service = service
        self.key = key
        super().__init__(f"Prompt not found: {service}.{key}")


class PromptManager:
    """In-memory prompt cache. Loads from DB on startup, reloads on admin changes.

    Usage:
        prompt = prompt_manager.get("chat", "system_prompt")
        prompt = prompt_manager.get_formatted("chat", "system_prompt", variable=value)
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._cache: dict[str, dict[str, str]] = {}

    async def start(self) -> None:
        await self._load()
        total = sum(len(v) for v in self._cache.values())
        logger.info("PromptManager started — %d prompts loaded", total)

    def get(self, service: str, key: str) -> str:
        try:
            return self._cache[service][key]
        except KeyError:
            raise PromptNotFoundError(service, key)

    def get_formatted(self, service: str, key: str, **kwargs: Any) -> str:
        """Return prompt content with placeholders replaced by the given variables.

        Placeholders in the prompt use Python format syntax: {variable_name}.
        Literal braces in the text must be escaped as {{ and }}.

        Raises PromptNotFoundError if the prompt is not found, or KeyError if a
        placeholder is missing from kwargs.
        """
        content = self.get(service, key)
        return content.format(**kwargs)

    def get_or_none(self, service: str, key: str) -> str | None:
        return self._cache.get(service, {}).get(key)

    def get_all(self, service: str) -> dict[str, str]:
        return dict(self._cache.get(service, {}))

    @property
    def services(self) -> list[str]:
        return sorted(self._cache.keys())

    async def reload(self) -> None:
        await self._load()
        total = sum(len(v) for v in self._cache.values())
        logger.info("PromptManager reloaded — %d prompts", total)

    async def _load(self) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromptModel.service, PromptModel.key, PromptModel.content).where(
                    PromptModel.is_active.is_(True)
                )
            )
            rows = result.all()

        cache: dict[str, dict[str, str]] = {}
        for service, key, content in rows:
            cache.setdefault(service, {})[key] = content
        self._cache = cache
