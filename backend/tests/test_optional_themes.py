import uuid

from src.roadmap.optional_themes import OPTIONAL_THEMES
from src.roadmap.schemas import OptionalThemeOption, OptionalThemesOut


def test_config_subjects_present():
    assert "AQA A-Level Psychology" in OPTIONAL_THEMES
    assert "AQA A-Level Physics" in OPTIONAL_THEMES
    assert "AQA A-Level Sociology" in OPTIONAL_THEMES


def test_config_structure():
    for subject, cfg in OPTIONAL_THEMES.items():
        assert "title" in cfg, f"{subject}: missing title"
        assert "exam_date" in cfg, f"{subject}: missing exam_date"
        assert ".929929" in cfg["exam_date"], f"{subject}: wrong exam_date sentinel"
        assert "blocks" in cfg, f"{subject}: missing blocks"
        assert len(cfg["blocks"]) >= 1, f"{subject}: need at least one block"
        for block in cfg["blocks"]:
            assert len(block) >= 1, f"{subject}: empty block"
            for option in block:
                if isinstance(option, dict):
                    assert "name" in option and "backend_name" in option
                else:
                    assert isinstance(option, str)


def test_optional_theme_option_serializes():
    opt = OptionalThemeOption(id=uuid.uuid4(), name="Astrophysics")
    assert opt.name == "Astrophysics"
    assert isinstance(opt.id, uuid.UUID)


def test_optional_themes_out_serializes():
    opt = OptionalThemeOption(id=uuid.uuid4(), name="Astrophysics")
    out = OptionalThemesOut(
        title="Paper 3 Practical Skills and Option Topic",
        exam_date="2026-06-08T08:00:00.929929Z",
        blocks=[[opt]],
    )
    assert out.title == "Paper 3 Practical Skills and Option Topic"
    assert len(out.blocks) == 1
    assert out.blocks[0][0].name == "Astrophysics"


# --- service layer tests ---

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.roadmap.service import resolve_optional_themes


def _make_folder(name: str) -> MagicMock:
    f = MagicMock()
    f.name = name
    return f


def _make_node(name: str, node_id: uuid.UUID | None = None) -> MagicMock:
    n = MagicMock()
    n.name = name
    n.id = node_id or uuid.uuid4()
    return n


@pytest.mark.asyncio
async def test_resolve_returns_none_when_folder_missing():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    result = await resolve_optional_themes(db, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_resolve_returns_none_for_unknown_subject():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=_make_folder("Unknown Subject"))
    result = await resolve_optional_themes(db, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_resolve_psychology_paper3():
    db = AsyncMock()
    folder_id = uuid.uuid4()
    db.scalar = AsyncMock(return_value=_make_folder("AQA A-Level Psychology"))

    node_ids = {name: uuid.uuid4() for name in [
        "3.2 Relationships", "3.3 Gender", "3.4 Cognition and Development",
        "3.5 Schizophrenia", "3.6 Eating Behaviour", "3.7 Stress",
        "3.8 Aggression", "3.9 Offending Behaviour", "3.10 Addiction",
    ]}
    nodes = [_make_node(name, nid) for name, nid in node_ids.items()]
    # iter() works here because service iterates rows synchronously in a dict comprehension
    db.scalars = AsyncMock(return_value=iter(nodes))

    result = await resolve_optional_themes(db, folder_id)
    assert isinstance(result, OptionalThemesOut)
    assert result.title == "Paper 3"
    assert result.exam_date.endswith(".929929Z")
    assert len(result.blocks) == 3
    assert len(result.blocks[0]) == 3
    assert result.blocks[0][0].name == "3.2 Relationships"
    assert result.blocks[0][0].id == node_ids["3.2 Relationships"]


@pytest.mark.asyncio
async def test_resolve_physics_display_names():
    """Verifies that display_name differs from backend_name for Physics options."""
    db = AsyncMock()
    folder_id = uuid.uuid4()
    db.scalar = AsyncMock(return_value=_make_folder("AQA A-Level Physics"))

    astro_id = uuid.uuid4()
    nodes = [_make_node("Option A: Astrophysics", astro_id)]
    # iter() works here because service iterates rows synchronously in a dict comprehension
    db.scalars = AsyncMock(return_value=iter(nodes))

    result = await resolve_optional_themes(db, folder_id)
    assert isinstance(result, OptionalThemesOut)
    assert result.title == "Paper 3 Practical Skills and Option Topic"
    # Display name should differ from backend name
    assert result.blocks[0][0].name == "Astrophysics"
    assert result.blocks[0][0].id == astro_id
