import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.prompts import repository
from src.prompts.schemas import (
    PromptCreate,
    PromptRead,
    PromptUpdate,
    PromptVersionRead,
)


class PromptService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_all(self, service: str | None = None) -> list[PromptRead]:
        async with self._session_factory() as session:
            if service:
                prompts = await repository.list_by_service(session, service)
            else:
                prompts = await repository.list_all(session)
            return [PromptRead.model_validate(p) for p in prompts]

    async def get(self, prompt_id: uuid.UUID) -> PromptRead | None:
        async with self._session_factory() as session:
            prompt = await repository.get_by_id(session, prompt_id)
            if not prompt:
                return None
            return PromptRead.model_validate(prompt)

    async def create(self, data: PromptCreate) -> PromptRead:
        async with self._session_factory() as session:
            existing = await repository.get_by_service_key(
                session, data.service, data.key
            )
            if existing:
                raise ValueError(f"Prompt '{data.service}.{data.key}' already exists")
            prompt = await repository.create_prompt(
                session,
                service=data.service,
                key=data.key,
                content=data.content,
                description=data.description,
                variables=data.variables,
            )
            await session.commit()
            return PromptRead.model_validate(prompt)

    async def update(self, prompt_id: uuid.UUID, data: PromptUpdate) -> PromptRead:
        async with self._session_factory() as session:
            prompt = await repository.get_by_id(session, prompt_id)
            if not prompt:
                raise ValueError("Prompt not found")
            prompt = await repository.update_prompt(
                session,
                prompt,
                content=data.content,
                description=data.description,
                variables=data.variables,
                is_active=data.is_active,
            )
            await session.commit()
            return PromptRead.model_validate(prompt)

    async def delete(self, prompt_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            prompt = await repository.get_by_id(session, prompt_id)
            if not prompt:
                raise ValueError("Prompt not found")
            await repository.delete_prompt(session, prompt)
            await session.commit()

    async def list_versions(self, prompt_id: uuid.UUID) -> list[PromptVersionRead]:
        async with self._session_factory() as session:
            versions = await repository.list_versions(session, prompt_id)
            return [PromptVersionRead.model_validate(v) for v in versions]

    async def restore_version(
        self, prompt_id: uuid.UUID, version_id: uuid.UUID
    ) -> PromptRead:
        async with self._session_factory() as session:
            prompt = await repository.get_by_id(session, prompt_id)
            if not prompt:
                raise ValueError("Prompt not found")
            versions = await repository.list_versions(session, prompt_id)
            version = next((v for v in versions if v.id == version_id), None)
            if not version:
                raise ValueError("Version not found")
            prompt = await repository.restore_version(session, prompt, version)
            await session.commit()
            return PromptRead.model_validate(prompt)
