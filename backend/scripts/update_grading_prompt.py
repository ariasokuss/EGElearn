"""One-shot: push the in-code GRADING_SYSTEM into the prompts table."""

import asyncio

from src.config import get_settings
from src.core.db import create_engine, create_session_factory
from src.core import model_registry  # noqa: F401
from src.learning.tests.prompts import GRADING_SYSTEM
from src.prompts import repository


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.postgres)
    factory = create_session_factory(engine)
    async with factory() as session:
        existing = await repository.get_by_service_key(session, "tests", "grading_system")
        if not existing:
            print("no row found — seeder will create it on next startup")
            return
        if existing.content == GRADING_SYSTEM:
            print("already in sync")
            return
        await repository.update_prompt(
            session,
            existing,
            content=GRADING_SYSTEM,
            description="Short-answer grading system prompt — awards marks against a mark scheme.",
        )
        await session.commit()
        print(f"updated tests/grading_system -> v{existing.version}")


if __name__ == "__main__":
    asyncio.run(main())
