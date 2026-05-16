from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.files import models as _files_models  # noqa: F401
from src.processing import models as _processing_models  # noqa: F401
from src.config import S3Settings
from src.roadmap.seed import (
    _build_diagram_public_url,
    _build_subject_diagram_s3_key,
    _extract_lesson_id_from_filename,
    _find_ordered_diagram_paths,
    _sync_subject_lessons_in_place,
    _rewrite_diagram_markers,
)


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _DummySession:
    def __init__(self, nodes):
        self._nodes = nodes
        self.flush_count = 0

    async def execute(self, _stmt):
        return _ScalarRows(self._nodes)

    async def flush(self):
        self.flush_count += 1

    def add(self, _obj):
        return None


def test_collects_ordered_diagrams_by_lesson_prefix(tmp_path: Path):
    diagrams_dir = tmp_path / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "1.2.6 - 2.png").write_bytes(b"two")
    (diagrams_dir / "1.2.6 - 1.png").write_bytes(b"one")
    (diagrams_dir / "2.1.1 - 1.png").write_bytes(b"other")

    result = _find_ordered_diagram_paths("1.2.6", diagrams_dir)

    assert [path.name for path in result] == [
        "1.2.6 - 1.png",
        "1.2.6 - 2.png",
    ]


def test_collects_ordered_diagrams_by_ocr_lesson_prefixes(tmp_path: Path):
    diagrams_dir = tmp_path / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "3.2.2f-g - 2.png").write_bytes(b"two")
    (diagrams_dir / "3.2.2f-g - 1.png").write_bytes(b"one")
    (diagrams_dir / "4.1.1(f-g) - 1.png").write_bytes(b"bio")
    (diagrams_dir / "6.03.3a - 1.png").write_bytes(b"physics")

    assert [path.name for path in _find_ordered_diagram_paths("3.2.2f-g", diagrams_dir)] == [
        "3.2.2f-g - 1.png",
        "3.2.2f-g - 2.png",
    ]
    assert [path.name for path in _find_ordered_diagram_paths("4.1.1(f-g)", diagrams_dir)] == [
        "4.1.1(f-g) - 1.png",
    ]
    assert [path.name for path in _find_ordered_diagram_paths("6.03.3a", diagrams_dir)] == [
        "6.03.3a - 1.png",
    ]


def test_extracts_ocr_lesson_id_from_filename():
    assert _extract_lesson_id_from_filename(Path("3.2.2f-g - Boltzmann distributions.md")) == "3.2.2f-g"
    assert _extract_lesson_id_from_filename(Path("4.1.1(f-g) - Lymphocytes.md")) == "4.1.1(f-g)"
    assert _extract_lesson_id_from_filename(Path("6.03.3a - Magnetic flux.md")) == "6.03.3a"


def test_rewrites_diagram_markers_with_s3_urls():
    content = "\n".join(
        [
            "# Lesson",
            "[DIAGRAM: First]",
            "Text after first.",
            "[DIAGRAM: Second]",
            "",
        ]
    )

    rewritten = _rewrite_diagram_markers(
        content,
        [
            "https://bucket.s3.eu-north-1.amazonaws.com/a-level/economics/diagrams/1-1.png",
            "https://bucket.s3.eu-north-1.amazonaws.com/a-level/economics/diagrams/1-2.png",
        ],
    )

    assert "[DIAGRAM: First]\n![Diagram](https://bucket.s3.eu-north-1.amazonaws.com/a-level/economics/diagrams/1-1.png)\nText after first." in rewritten
    assert "[DIAGRAM: Second]\n![Diagram](https://bucket.s3.eu-north-1.amazonaws.com/a-level/economics/diagrams/1-2.png)\n" in rewritten


def test_rewrites_lowercase_diagram_markers_with_s3_urls():
    content = "# Lesson\n[diagram: asset_slug: x; description: Example]\nBody\n"

    rewritten = _rewrite_diagram_markers(
        content,
        ["https://new.example/diagram.png"],
    )

    assert "[diagram: asset_slug: x; description: Example]\n![Diagram](https://new.example/diagram.png)\nBody" in rewritten


def test_rewrite_replaces_existing_image_line_idempotently():
    content = "\n".join(
        [
            "# Lesson",
            "[DIAGRAM: Existing]",
            "![Diagram](https://old.example/old.png)",
            "Body text",
            "",
        ]
    )

    rewritten = _rewrite_diagram_markers(
        content,
        ["https://new.example/fresh.png"],
    )

    assert rewritten.count("![Diagram](") == 1
    assert "https://new.example/fresh.png" in rewritten
    assert "https://old.example/old.png" not in rewritten


def test_raises_when_marker_count_and_diagram_count_differ():
    content = "# Lesson\n[DIAGRAM: One]\n"

    with pytest.raises(ValueError, match="Diagram marker count"):
        _rewrite_diagram_markers(content, [])


def test_builds_shared_diagram_key_and_public_url():
    settings = S3Settings(
        endpoint_url="https://s3.eu-north-1.amazonaws.com",
        access_key_id="key",
        secret_access_key="secret",
        region="eu-north-1",
        bucket="nls3-bucket",
        use_ssl=True,
        use_path_style=False,
    )

    key = _build_subject_diagram_s3_key("Edexcel A-Level Economics", "3.3.4", 2)
    url = _build_diagram_public_url(settings, key)

    assert key == "diagrams/economics/3.3.4-2.png"
    assert url == "https://nls3-bucket.s3.eu-north-1.amazonaws.com/diagrams/economics/3.3.4-2.png"


@pytest.mark.asyncio
async def test_sync_subject_lessons_updates_existing_linked_lessons_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    subject_dir = tmp_path / "Edexcel A-Level Economics"
    lessons_dir = subject_dir / "lessons"
    lessons_dir.mkdir(parents=True)
    (subject_dir / "roadmap.md").write_text(
        "\n".join(
            [
                "# Subject",
                "",
                "## Theme 1",
                "",
                "### 1.1: Nature of economics",
                "",
                "| ID | Lesson |",
                "|----|--------|",
                "| 1.1.1 | Economics as a social science |",
            ]
        ),
        encoding="utf-8",
    )
    (lessons_dir / "1.1.1 Economics as a social science.md").write_text(
        "# Lesson\n\nUpdated body.\n",
        encoding="utf-8",
    )

    lesson_id = uuid.uuid4()
    lesson = SimpleNamespace(
        id=lesson_id,
        name="1.1.1 Economics as a social science",
        content="# Old\n",
        description="old",
        num_blocks=0,
    )
    node = SimpleNamespace(
        id=uuid.uuid4(),
        name="1.1.1 Economics as a social science",
        lesson_id=lesson_id,
        lesson=lesson,
    )
    session = _DummySession([node])

    parsed_calls: list[tuple[uuid.UUID, str]] = []

    async def _fake_parse_and_store_blocks(_session, parsed_lesson_id, content):
        parsed_calls.append((parsed_lesson_id, content))

    monkeypatch.setattr(
        "src.roadmap.seed._parse_and_store_blocks",
        _fake_parse_and_store_blocks,
    )

    lesson_nodes = await _sync_subject_lessons_in_place(
        session,
        subject_dir,
        folder_id=uuid.uuid4(),
    )

    assert lesson.content == "# Lesson\n\nUpdated body.\n"
    assert node.lesson_id == lesson_id
    assert parsed_calls == [(lesson_id, "# Lesson\n\nUpdated body.\n")]
    assert lesson_nodes[0][0] == "1.1.1"
    assert lesson_nodes[0][1] == "Economics as a social science"
