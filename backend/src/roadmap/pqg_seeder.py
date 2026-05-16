"""PQG (Practice Question Generation) seeder.

Discovers question-types.md and prompts/ in subject folders,
parses them, and upserts into the prompt manager DB.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.prompts import repository

logger = logging.getLogger(__name__)


def slugify_service_name(folder_name: str) -> str:
    """Convert folder name to PQG service name."""
    return "pqg-" + folder_name.lower().replace(" ", "-")


def parse_question_types_md(content: str) -> list[dict]:
    """Parse a markdown table into [{label, key, points}, ...].

    Expected format:
    | Label | Key | Points |
    |-------|-----|--------|
    | Section A questions | section_a | 5 |
    """
    rows: list[dict] = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip separator rows like |---|---|---|
        if re.match(r"^\|[\s\-|]+\|$", line):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Remove empty strings from leading/trailing |
        parts = [p for p in parts if p]
        if len(parts) < 3:
            continue
        label, key, points_str = parts[0], parts[1], parts[2]
        # Skip header row
        if label == "Label":
            continue
        try:
            points = int(points_str)
        except ValueError:
            continue
        rows.append({"label": label, "key": key, "points": points})
    return rows


def parse_prompt_file(content: str) -> tuple[str, str]:
    """Split a prompt .md file on ---system--- / ---user--- markers.

    Returns (system_text, user_text). If ---user--- is absent, user_text is "".
    """
    system_marker = "---system---"
    user_marker = "---user---"

    if system_marker in content:
        after_system = content.split(system_marker, 1)[1]
        if user_marker in after_system:
            system_text, user_text = after_system.split(user_marker, 1)
        else:
            system_text = after_system
            user_text = ""
    else:
        system_text = content
        user_text = ""

    return system_text.strip(), user_text.strip()


async def seed_pqg_prompts(
    session: AsyncSession,
    subject_dir: Path,
    folder_pqg_service: str,
) -> int:
    """Seed PQG prompts from a subject's prompts/ dir into the DB.

    Returns number of prompts upserted.
    """
    question_types_path = subject_dir / "question-types.md"
    prompts_dir = subject_dir / "prompts"

    if not question_types_path.exists():
        return 0

    question_types = parse_question_types_md(
        question_types_path.read_text(encoding="utf-8")
    )
    if not question_types:
        logger.warning("No question types found in %s", question_types_path)
        return 0

    count = 0

    # Store question types metadata
    qt_content = json.dumps(question_types, ensure_ascii=False)
    await _upsert_prompt(
        session,
        service=folder_pqg_service,
        key="_question_types",
        content=qt_content,
        description=f"Question type definitions for {subject_dir.name}",
        variables=[],
    )
    count += 1

    # Store each prompt file
    if prompts_dir.is_dir():
        for qt in question_types:
            prompt_path = prompts_dir / f"{qt['key']}.md"
            if not prompt_path.exists():
                logger.warning("Prompt file missing: %s", prompt_path)
                continue

            raw = prompt_path.read_text(encoding="utf-8")
            system_text, user_text = parse_prompt_file(raw)

            await _upsert_prompt(
                session,
                service=folder_pqg_service,
                key=f"{qt['key']}_system",
                content=system_text,
                description=f"{qt['label']} system prompt ({subject_dir.name})",
                variables=[],
            )
            count += 1

            if user_text:
                variables = _extract_variables(user_text)
                await _upsert_prompt(
                    session,
                    service=folder_pqg_service,
                    key=f"{qt['key']}_user_template",
                    content=user_text,
                    description=f"{qt['label']} user template ({subject_dir.name})",
                    variables=variables,
                )
                count += 1

        # Allocation prompt (optional)
        alloc_path = prompts_dir / "allocation.md"
        if alloc_path.exists():
            raw = alloc_path.read_text(encoding="utf-8")
            system_text, user_text = parse_prompt_file(raw)

            await _upsert_prompt(
                session,
                service=folder_pqg_service,
                key="allocation_system",
                content=system_text,
                description=f"Type-aware allocation system prompt ({subject_dir.name})",
                variables=[],
            )
            count += 1

            if user_text:
                variables = _extract_variables(user_text)
                await _upsert_prompt(
                    session,
                    service=folder_pqg_service,
                    key="allocation_user_template",
                    content=user_text,
                    description=f"Type-aware allocation user template ({subject_dir.name})",
                    variables=variables,
                )
                count += 1

    logger.info(
        "PQG seeder: upserted %d prompts for service %s",
        count, folder_pqg_service,
    )
    return count


def _extract_variables(template: str) -> list[str]:
    """Extract unique variable names from a format string."""
    variables = re.findall(r"\{(\w+)\}", template)
    seen: set[str] = set()
    unique: list[str] = []
    for v in variables:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


async def _upsert_prompt(
    session: AsyncSession,
    service: str,
    key: str,
    content: str,
    description: str,
    variables: list[str],
) -> None:
    """Insert or update a prompt in the DB."""
    existing = await repository.get_by_service_key(session, service, key)
    if existing:
        if existing.content != content:
            await repository.update_prompt(
                session, existing,
                content=content,
                description=description,
                variables=variables,
            )
    else:
        await repository.create_prompt(
            session,
            service=service,
            key=key,
            content=content,
            description=description,
            variables=variables,
        )
