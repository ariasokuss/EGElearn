import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.prompts.models import PromptModel, PromptVersionModel


async def list_all(session: AsyncSession) -> list[PromptModel]:
    result = await session.execute(
        select(PromptModel).order_by(PromptModel.service, PromptModel.key)
    )
    return list(result.scalars().all())


async def list_active(session: AsyncSession) -> list[PromptModel]:
    result = await session.execute(
        select(PromptModel)
        .where(PromptModel.is_active.is_(True))
        .order_by(PromptModel.service, PromptModel.key)
    )
    return list(result.scalars().all())


async def list_by_service(session: AsyncSession, service: str) -> list[PromptModel]:
    result = await session.execute(
        select(PromptModel)
        .where(PromptModel.service == service)
        .order_by(PromptModel.key)
    )
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, prompt_id: uuid.UUID) -> PromptModel | None:
    result = await session.execute(
        select(PromptModel).where(PromptModel.id == prompt_id)
    )
    return result.scalar_one_or_none()


async def get_by_service_key(
    session: AsyncSession, service: str, key: str
) -> PromptModel | None:
    result = await session.execute(
        select(PromptModel).where(
            PromptModel.service == service, PromptModel.key == key
        )
    )
    return result.scalar_one_or_none()


async def create_prompt(
    session: AsyncSession,
    service: str,
    key: str,
    content: str,
    description: str | None = None,
    variables: list | None = None,
) -> PromptModel:
    prompt = PromptModel(
        id=uuid.uuid4(),
        service=service,
        key=key,
        content=content,
        description=description,
        variables=variables or [],
    )
    session.add(prompt)
    await session.flush()

    version = PromptVersionModel(
        id=uuid.uuid4(),
        prompt_id=prompt.id,
        content=content,
        version=1,
        changed_by="admin",
    )
    session.add(version)
    await session.flush()
    return prompt


async def update_prompt(
    session: AsyncSession,
    prompt: PromptModel,
    content: str | None = None,
    description: str | None = None,
    variables: list | None = None,
    is_active: bool | None = None,
) -> PromptModel:
    content_changed = content is not None and content != prompt.content

    if content is not None:
        prompt.content = content
    if description is not None:
        prompt.description = description
    if variables is not None:
        prompt.variables = variables
    if is_active is not None:
        prompt.is_active = is_active

    if content_changed:
        prompt.version += 1
        version = PromptVersionModel(
            id=uuid.uuid4(),
            prompt_id=prompt.id,
            content=content,
            version=prompt.version,
            changed_by="admin",
        )
        session.add(version)

    prompt.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return prompt


async def delete_prompt(session: AsyncSession, prompt: PromptModel) -> None:
    await session.delete(prompt)
    await session.flush()


async def list_versions(
    session: AsyncSession, prompt_id: uuid.UUID
) -> list[PromptVersionModel]:
    result = await session.execute(
        select(PromptVersionModel)
        .where(PromptVersionModel.prompt_id == prompt_id)
        .order_by(PromptVersionModel.version.desc())
    )
    return list(result.scalars().all())


async def restore_version(
    session: AsyncSession, prompt: PromptModel, version: PromptVersionModel
) -> PromptModel:
    return await update_prompt(session, prompt, content=version.content)
