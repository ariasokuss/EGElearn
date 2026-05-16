from __future__ import annotations

import asyncio
import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.learning import models as _learning_models  # noqa: F401
from src.learning.past_paper.schemas import ParsedQuestion
from src.learning.past_paper.service import (
    PastPaperError,
    _enrich_question_contexts,
    _prepare_mark_scheme_assignment,
    _sanitize_mark_schemes_on_parsed_questions,
    _template_mark_scheme_value,
    _clear_mark_scheme_upload_jobs_for_tests,
    delete_past_paper,
    get_mark_scheme_upload_job,
    start_mark_scheme_upload_job,
    stream_mark_scheme_upload_job,
    upload_and_process_streaming,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def one_or_none(self):
        return self._value


def test_prepare_mark_scheme_assignment_counts_only_short_questions():
    questions = [
        SimpleNamespace(index=0, type="short"),
        SimpleNamespace(index=1, type="mcq"),
        SimpleNamespace(index=2, type="short"),
    ]
    assignment = {
        0: "  Award 1 mark for mentioning acceleration. ",
        1: "Should be ignored for MCQ",
        2: "   ",
    }

    updates, applied, total = _prepare_mark_scheme_assignment(questions, assignment)

    assert updates == {
        0: "Award 1 mark for mentioning acceleration.",
        1: None,
        2: None,
    }
    assert applied == 1
    assert total == 2


def test_sanitize_mark_schemes_on_parsed_questions_normalizes_values():
    questions = [
        ParsedQuestion(
            question="Q1",
            model_answer="A1",
            mark_scheme="  2 points for correct method. ",
            type="short",
        ),
        ParsedQuestion(
            question="Q2",
            model_answer="A2",
            mark_scheme="This must be removed",
            type="mcq",
            options=["A", "B"],
            correct_option_index=0,
        ),
        ParsedQuestion(
            question="Q3",
            model_answer="A3",
            mark_scheme="   ",
            type="short",
        ),
    ]

    applied, total = _sanitize_mark_schemes_on_parsed_questions(questions)

    assert questions[0].mark_scheme == "2 points for correct method."
    assert questions[1].mark_scheme is None
    assert questions[2].mark_scheme is None
    assert applied == 1
    assert total == 2


def test_template_mark_scheme_value_clears_when_no_matches():
    assert _template_mark_scheme_value("Mark scheme text", 0) is None
    assert _template_mark_scheme_value("Mark scheme text", -1) is None
    assert _template_mark_scheme_value(None, 5) is None
    assert _template_mark_scheme_value("", 5) is None
    assert _template_mark_scheme_value("Mark scheme text", 1) == "Mark scheme text"


def test_enrich_question_contexts_includes_full_table_markdown():
    markdown = """
Table 1: Mass and force
| Mass (kg) | Force (N) |
|---|---|
| 1 | 10 |
| 2 | 20 |
""".strip()
    questions = [
        ParsedQuestion(
            question="Using Table 1, find the gradient.",
            model_answer="10",
            context="Table 1",
            type="short",
        )
    ]

    _enrich_question_contexts(questions, markdown, image_url_by_path={})

    ctx = questions[0].context
    assert ctx is not None
    assert "::: figure [Table 1 — Mass and force]" in ctx
    assert "| Mass (kg) | Force (N) |" in ctx
    assert "| 2 | 20 |" in ctx
    assert ctx.rstrip().endswith(":::")


def test_enrich_question_contexts_includes_renderable_figure_image():
    markdown = """
Figure 2 shows the setup.
![img-2](uploads/images/img-2.png)
""".strip()
    questions = [
        ParsedQuestion(
            question="Explain what Figure 2 demonstrates.",
            model_answer="A description",
            context="Figure 2",
            type="short",
        )
    ]

    _enrich_question_contexts(
        questions,
        markdown,
        image_url_by_path={
            "uploads/images/img-2.png": "/api/v1/past-papers/images/uploads/images/img-2.png",
        },
    )

    ctx = questions[0].context
    assert ctx is not None
    assert "::: figure [Figure 2" in ctx
    assert "![img-2](/api/v1/past-papers/images/uploads/images/img-2.png)" in ctx
    assert ctx.rstrip().endswith(":::")


@pytest.mark.asyncio
async def test_delete_past_paper_raises_when_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))

    with pytest.raises(PastPaperError, match="not found"):
        await delete_past_paper(db, uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_past_paper_deletes_template_without_loading_relations():
    template_id = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(template_id),
            _ScalarResult(None),
        ]
    )

    await delete_past_paper(db, uuid.uuid4(), template_id)

    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()


class _NodeRows:
    def all(self):
        return []

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return []


class _DummyTemplate:
    def __init__(self):
        self.status = "processing"
        self.total_questions = 0
        self.total_marks = 0
        self.mark_scheme = None


class _DummySession:
    def __init__(self, template=None):
        self.template = template or _DummyTemplate()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _NodeRows()

    def add(self, _obj):
        return None

    def add_all(self, _objs):
        return None

    async def commit(self):
        return None

    async def get(self, _model, _obj_id):
        return self.template


class _DummySessionFactory:
    def __init__(self):
        self.template = _DummyTemplate()

    def __call__(self):
        return _DummySession(self.template)


@pytest.mark.asyncio
async def test_streaming_upload_emits_mark_scheme_unassigned_and_zero_match_fail_events(
    monkeypatch,
):
    class _FakeOCR:
        def __init__(self, _settings):
            pass

        async def pdf_to_markdown_with_images(self, _payload):
            return "[PAGE 1]\nQ1", {}, {}

    class _FakeParser:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def parse(self, _markdown, _mark_scheme_markdown=None):
            return [
                ParsedQuestion(
                    question="Explain this.",
                    model_answer="A",
                    mark_scheme=None,
                    type="short",
                    )
                ]

        async def assign_mark_schemes(self, _questions, _mark_scheme_markdown):
            return {}

    class _FakeMatcher:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def match(self, _nodes, _questions):
            return {}

    monkeypatch.setattr("src.learning.past_paper.service.PastPaperOCR", _FakeOCR)
    monkeypatch.setattr("src.learning.past_paper.service.PastPaperParser", _FakeParser)
    monkeypatch.setattr(
        "src.learning.past_paper.service.RoadmapNodeMatcher", _FakeMatcher
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service.YandexGPTLLMGateway", lambda: None
    )

    session_factory = _DummySessionFactory()
    events = []
    async for event in upload_and_process_streaming(
        session_factory=session_factory,
        user_id=uuid.uuid4(),
        pdf_bytes=b"%PDF-past-paper",
        name="Paper",
        original_filename="paper.pdf",
        folder_id=uuid.uuid4(),
        mark_scheme_bytes=b"%PDF-mark-scheme",
        usage_service=None,
    ):
        events.append(event)

    phases = [e.get("phase") for e in events if e.get("event") == "processing"]
    assert "mark_scheme_parsing" in phases

    unassigned_events = [e for e in events if e.get("event") == "mark_scheme_unassigned"]
    assert len(unassigned_events) == 1
    assert unassigned_events[0]["matched_questions"] == 0
    assert unassigned_events[0]["total_short_questions"] == 1
    assert unassigned_events[0]["total_questions"] == 1

    fail_events = [e for e in events if e.get("event") == "mark_scheme_failed"]
    assert len(fail_events) == 1
    assert fail_events[0]["matched_questions"] == 0
    assert fail_events[0]["total_short_questions"] == 1
    assert session_factory.template.mark_scheme is None


@pytest.mark.asyncio
async def test_streaming_upload_reuses_cached_paper_without_reprocessing(monkeypatch):
    class _FailIfCalledOCR:
        def __init__(self, _settings):
            raise AssertionError("OCR should not be called on cache hit")

    cached_id = uuid.uuid4()
    cached_paper = SimpleNamespace(
        id=cached_id,
        name="Cached paper",
        total_marks=7,
        generation_progress=None,
        questions=[
            SimpleNamespace(points=3),
            SimpleNamespace(points=4),
        ],
    )
    cloned_id = uuid.uuid4()
    cloned_paper = SimpleNamespace(
        id=cloned_id,
        name="Any name",
        total_marks=7,
        questions=[
            SimpleNamespace(points=3),
            SimpleNamespace(points=4),
        ],
    )

    async def _fake_find_cached(
        session_factory,
        *,
        pdf_sha256,
    ):
        return cached_paper

    async def _fake_clone_cached(
        session_factory,
        *,
        cached,
        user_id,
        folder_id,
        name,
        original_filename,
        pdf_bytes,
        pdf_sha256,
        mark_scheme_bytes,
        mark_scheme_sha256,
        mark_scheme_filename,
        s3,
    ):
        assert cached is cached_paper
        assert mark_scheme_bytes is None
        return cloned_paper

    monkeypatch.setattr("src.learning.past_paper.service.PastPaperOCR", _FailIfCalledOCR)
    monkeypatch.setattr(
        "src.learning.past_paper.service._find_cached_past_paper",
        _fake_find_cached,
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service._clone_cached_past_paper",
        _fake_clone_cached,
    )

    events = []
    async for event in upload_and_process_streaming(
        session_factory=_DummySessionFactory(),
        user_id=uuid.uuid4(),
        pdf_bytes=b"%PDF-duplicate",
        name="Any name",
        original_filename="duplicate.pdf",
        folder_id=uuid.uuid4(),
        mark_scheme_bytes=None,
        usage_service=None,
    ):
        events.append(event)

    assert len(events) == 2
    assert events[0]["event"] == "started"
    assert events[0]["paper_id"] == str(cloned_id)
    assert events[0]["cached"] is True
    assert events[1]["event"] == "complete"
    assert events[1]["paper_id"] == str(cloned_id)
    assert events[1]["total_questions"] == 2
    assert events[1]["total_marks"] == 7
    assert events[1]["cached"] is True


@pytest.mark.asyncio
async def test_streaming_upload_passes_mark_scheme_hash_to_cache_lookup(monkeypatch):
    captured: dict[str, str | None] = {}

    async def _fake_find_cached(
        session_factory,
        *,
        pdf_sha256,
    ):
        captured["pdf_sha256"] = pdf_sha256
        return None

    class _FakeOCR:
        def __init__(self, _settings):
            pass

        async def pdf_to_markdown_with_images(self, _payload):
            return "[PAGE 1]\nQ1", {}, {}

    class _FakeParser:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def parse(self, _markdown, _mark_scheme_markdown=None):
            return [
                ParsedQuestion(
                    question="Explain this.",
                    model_answer="A",
                    mark_scheme=None,
                    type="short",
                )
            ]

        async def assign_mark_schemes(self, _questions, _mark_scheme_markdown):
            return {}

    class _FakeMatcher:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def match(self, _nodes, _questions):
            return {}

    monkeypatch.setattr(
        "src.learning.past_paper.service._find_cached_past_paper",
        _fake_find_cached,
    )
    monkeypatch.setattr("src.learning.past_paper.service.PastPaperOCR", _FakeOCR)
    monkeypatch.setattr("src.learning.past_paper.service.PastPaperParser", _FakeParser)
    monkeypatch.setattr(
        "src.learning.past_paper.service.RoadmapNodeMatcher", _FakeMatcher
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service.YandexGPTLLMGateway", lambda: None
    )

    mark_scheme_bytes = b"%PDF-mark-scheme-for-hash"
    async for _ in upload_and_process_streaming(
        session_factory=_DummySessionFactory(),
        user_id=uuid.uuid4(),
        pdf_bytes=b"%PDF-paper",
        name="Paper",
        original_filename="paper.pdf",
        folder_id=uuid.uuid4(),
        mark_scheme_bytes=mark_scheme_bytes,
        usage_service=None,
    ):
        pass

    import hashlib as _hashlib
    assert captured["pdf_sha256"] == _hashlib.sha256(b"%PDF-paper").hexdigest()


@pytest.mark.asyncio
async def test_streaming_upload_fallback_matching_populates_mark_scheme(monkeypatch):
    captured_mark_schemes: list[str | None] = []

    class _FakeOCR:
        def __init__(self, _settings):
            pass

        async def pdf_to_markdown_with_images(self, _payload):
            return "[PAGE 1]\nQ1", {}, {}

    class _FakeParser:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def parse(self, _markdown, _mark_scheme_markdown=None):
            return [
                ParsedQuestion(
                    question="Explain this.",
                    model_answer="A",
                    mark_scheme=None,
                    type="short",
                )
            ]

        async def assign_mark_schemes(self, _questions, _mark_scheme_markdown):
            return {0: "Award 1 mark for any correct explanation."}

    class _FakeMatcher:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def match(self, _nodes, _questions):
            return {}

    def _fake_build_question_rows(_template_id, parsed):
        captured_mark_schemes.extend([q.mark_scheme for q in parsed])
        return []

    monkeypatch.setattr("src.learning.past_paper.service.PastPaperOCR", _FakeOCR)
    monkeypatch.setattr("src.learning.past_paper.service.PastPaperParser", _FakeParser)
    monkeypatch.setattr(
        "src.learning.past_paper.service.RoadmapNodeMatcher", _FakeMatcher
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service.YandexGPTLLMGateway", lambda: None
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service._build_question_rows", _fake_build_question_rows
    )

    session_factory = _DummySessionFactory()
    events = []
    async for event in upload_and_process_streaming(
        session_factory=session_factory,
        user_id=uuid.uuid4(),
        pdf_bytes=b"%PDF-past-paper",
        name="Paper",
        original_filename="paper.pdf",
        folder_id=uuid.uuid4(),
        mark_scheme_bytes=b"%PDF-mark-scheme",
        usage_service=None,
    ):
        events.append(event)

    assert "Award 1 mark for any correct explanation." in captured_mark_schemes
    phases = [e.get("phase") for e in events if e.get("event") == "processing"]
    assert "mark_scheme_matching" in phases
    assert not any(e.get("event") == "mark_scheme_failed" for e in events)


@pytest.mark.asyncio
async def test_streaming_upload_emits_unassigned_event_even_without_short_questions(
    monkeypatch,
):
    class _FakeOCR:
        def __init__(self, _settings):
            pass

        async def pdf_to_markdown_with_images(self, _payload):
            return "[PAGE 1]\nQ1", {}, {}

    class _FakeParser:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def parse(self, _markdown, _mark_scheme_markdown=None):
            return [
                ParsedQuestion(
                    question="Pick one option",
                    model_answer="A",
                    mark_scheme=None,
                    type="mcq",
                    options=["A", "B"],
                    correct_option_index=0,
                )
            ]

        async def assign_mark_schemes(self, _questions, _mark_scheme_markdown):
            return {}

    class _FakeMatcher:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def match(self, _nodes, _questions):
            return {}

    monkeypatch.setattr("src.learning.past_paper.service.PastPaperOCR", _FakeOCR)
    monkeypatch.setattr("src.learning.past_paper.service.PastPaperParser", _FakeParser)
    monkeypatch.setattr(
        "src.learning.past_paper.service.RoadmapNodeMatcher", _FakeMatcher
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service.YandexGPTLLMGateway", lambda: None
    )

    session_factory = _DummySessionFactory()
    events = []
    async for event in upload_and_process_streaming(
        session_factory=session_factory,
        user_id=uuid.uuid4(),
        pdf_bytes=b"%PDF-past-paper",
        name="Paper",
        original_filename="paper.pdf",
        folder_id=uuid.uuid4(),
        mark_scheme_bytes=b"%PDF-mark-scheme",
        usage_service=None,
    ):
        events.append(event)

    unassigned_events = [e for e in events if e.get("event") == "mark_scheme_unassigned"]
    assert len(unassigned_events) == 1
    assert unassigned_events[0]["total_short_questions"] == 0
    assert not any(e.get("event") == "mark_scheme_failed" for e in events)
    assert session_factory.template.mark_scheme is None


@pytest.mark.asyncio
async def test_streaming_upload_sets_template_mark_scheme_field(monkeypatch):
    class _FakeOCR:
        def __init__(self, _settings):
            pass

        async def pdf_to_markdown_with_images(self, payload):
            if payload == b"%PDF-mark-scheme":
                return "MS 1: Award 1 mark", {}, {}
            return "[PAGE 1]\nQ1", {}, {}

    class _FakeParser:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def parse(self, _markdown, _mark_scheme_markdown=None):
            return [
                ParsedQuestion(
                    question="Explain this.",
                    model_answer="A",
                    mark_scheme="Award 1 mark",
                    type="short",
                )
            ]

        async def assign_mark_schemes(self, _questions, _mark_scheme_markdown):
            return {0: "Award 1 mark"}

    class _FakeMatcher:
        def __init__(self, _llm, usage_service=None, prompt_manager=None):
            self._current_user_id = None

        async def match(self, _nodes, _questions):
            return {}

    monkeypatch.setattr("src.learning.past_paper.service.PastPaperOCR", _FakeOCR)
    monkeypatch.setattr("src.learning.past_paper.service.PastPaperParser", _FakeParser)
    monkeypatch.setattr(
        "src.learning.past_paper.service.RoadmapNodeMatcher", _FakeMatcher
    )
    monkeypatch.setattr(
        "src.learning.past_paper.service.YandexGPTLLMGateway", lambda: None
    )

    session_factory = _DummySessionFactory()
    async for _ in upload_and_process_streaming(
        session_factory=session_factory,
        user_id=uuid.uuid4(),
        pdf_bytes=b"%PDF-past-paper",
        name="Paper",
        original_filename="paper.pdf",
        folder_id=uuid.uuid4(),
        mark_scheme_bytes=b"%PDF-mark-scheme",
        usage_service=None,
    ):
        pass

    assert session_factory.template.mark_scheme == "MS 1: Award 1 mark"


@pytest.mark.asyncio
async def test_mark_scheme_background_job_reports_progress_and_completion(monkeypatch):
    _clear_mark_scheme_upload_jobs_for_tests()

    async def _fake_core(
        session_factory,
        user_id,
        past_paper_id,
        mark_scheme_bytes,
        usage_service=None,
        event_emitter=None,
        prompt_manager=None,
        **_kwargs,
    ):
        if event_emitter:
            await event_emitter(
                {
                    "event": "processing",
                    "phase": "mark_scheme_parsing",
                    "message": "Parsing mark scheme",
                }
            )
            await event_emitter(
                {
                    "event": "complete",
                    "past_paper_id": str(past_paper_id),
                    "matched_questions": 3,
                    "total_short_questions": 4,
                    "message": "done",
                }
            )
        return SimpleNamespace(id=past_paper_id)

    monkeypatch.setattr("src.learning.past_paper.service._upload_mark_scheme_core", _fake_core)

    user_id = uuid.uuid4()
    past_paper_id = uuid.uuid4()
    job = await start_mark_scheme_upload_job(
        session_factory=object(),
        user_id=user_id,
        past_paper_id=past_paper_id,
        mark_scheme_bytes=b"%PDF-test",
        usage_service=None,
    )

    for _ in range(50):
        current = await get_mark_scheme_upload_job(user_id, past_paper_id, job["id"])
        if current["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("background mark-scheme job did not complete")

    assert current["matched_questions"] == 3
    assert current["total_short_questions"] == 4
    assert current["phase"] == "complete"

    events = []
    async for event in stream_mark_scheme_upload_job(
        user_id,
        past_paper_id,
        job["id"],
        interval_seconds=0.001,
    ):
        events.append(event)

    assert any(e.get("phase") == "mark_scheme_parsing" for e in events)
    assert any(e.get("event") == "complete" for e in events)

    _clear_mark_scheme_upload_jobs_for_tests()


def test_prepare_mark_scheme_assignment_excludes_unsupported_questions():
    """Unsupported questions must not be counted in total_short or have mark schemes applied."""
    from types import SimpleNamespace

    questions = [
        SimpleNamespace(type="short", is_unsupported=False, index=0, question="Define osmosis."),
        SimpleNamespace(type="short", is_unsupported=True, index=1, question="Draw a diagram."),
        SimpleNamespace(type="mcq", is_unsupported=False, index=2, question="Which is correct?"),
    ]
    assignment = {
        0: "Award 1 mark for correct definition.",
        1: "Should be ignored for unsupported.",
        2: "Should be ignored for MCQ.",
    }
    updates, applied, total_short = _prepare_mark_scheme_assignment(questions, assignment)

    # unsupported short question (index=1) must not count toward total_short
    assert total_short == 1, f"expected total_short=1, got {total_short}"
    # unsupported short question must get None update (no mark scheme assigned)
    assert updates[1] is None, "unsupported question should have None mark scheme update"
    # supported short question (index=0) should get its mark scheme
    assert updates[0] == "Award 1 mark for correct definition."
    assert applied == 1


@pytest.mark.asyncio
async def test_mark_scheme_background_job_reports_failure(monkeypatch):
    _clear_mark_scheme_upload_jobs_for_tests()

    async def _fake_core(
        session_factory,
        user_id,
        past_paper_id,
        mark_scheme_bytes,
        usage_service=None,
        event_emitter=None,
        prompt_manager=None,
        **_kwargs,
    ):
        raise PastPaperError("mock failure")

    monkeypatch.setattr("src.learning.past_paper.service._upload_mark_scheme_core", _fake_core)

    user_id = uuid.uuid4()
    past_paper_id = uuid.uuid4()
    job = await start_mark_scheme_upload_job(
        session_factory=object(),
        user_id=user_id,
        past_paper_id=past_paper_id,
        mark_scheme_bytes=b"%PDF-test",
        usage_service=None,
    )

    for _ in range(50):
        current = await get_mark_scheme_upload_job(user_id, past_paper_id, job["id"])
        if current["status"] == "failed":
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("background mark-scheme job did not fail")

    assert "mock failure" in (current["error"] or "")
    _clear_mark_scheme_upload_jobs_for_tests()


def test_directive_refs_extracts_figure_and_table_refs():
    from src.learning.past_paper.service import _directive_refs

    base = (
        "::: figure [Figure 4]\n"
        "| ... |\n"
        ":::\n"
        "::: text [Extract A]\n"
        "passage text\n"
        ":::\n"
        "::: figure [Table 1 — Data]\n"
        "| ... |\n"
        ":::\n"
    )
    figs, tabs = _directive_refs(base)
    assert figs == {"4"}
    assert tabs == {"1"}


def test_directive_refs_handles_empty_and_none():
    from src.learning.past_paper.service import _directive_refs

    assert _directive_refs("") == (set(), set())
    assert _directive_refs(None) == (set(), set())


def test_extract_image_blocks_returns_captions():
    from src.learning.past_paper.service import _extract_image_blocks

    markdown = """
Figure 4: Income tax rates for 2023–24, compared to 2022–23

| Tax band | Rate |
| --- | --- |
| Basic | 20% |

Table 1 — Mass and force
![img-2](path/to/img-2.png)

Figure 5: Another caption goes here.
![img-5](path/to/img-5.png)
""".strip()

    image_url_by_path = {
        "path/to/img-2.png": "/api/v1/past-papers/X/assets/images/img-2.png",
        "path/to/img-5.png": "/api/v1/past-papers/X/assets/images/img-5.png",
    }

    result = _extract_image_blocks(markdown, image_url_by_path)
    assert len(result) == 4
    table_images, figure_images, table_captions, figure_captions = result
    assert figure_captions["4"] == "Income tax rates for 2023–24, compared to 2022–23"
    assert figure_captions["5"] == "Another caption goes here."
    assert table_captions["1"] == "Mass and force"


def test_enrichment_skips_when_llm_directive_present_with_table():
    """Real bug scenario from row 56f73007: LLM wraps a table as Figure 4;
    OCR has an unrelated image bound to ref 4. The image must NOT be appended."""
    markdown = """
Figure 4: Income tax rates for 2023–24
| Tax band | Rate |
| --- | --- |
| Basic | 20% |

![img-5](uploads/img-5.png)
""".strip()
    base_context = (
        "::: figure [Figure 4]\n"
        "| Tax band | Rate |\n"
        "| --- | --- |\n"
        "| Basic | 20% |\n"
        ":::"
    )
    questions = [
        ParsedQuestion(
            question="With reference to Figure 4, examine the impact.",
            model_answer="A",
            context=base_context,
            type="short",
        )
    ]
    _enrich_question_contexts(
        questions, markdown,
        image_url_by_path={"uploads/img-5.png": "/api/v1/x/img-5.png"},
    )
    ctx = questions[0].context
    assert ctx is not None
    # No second "Figure 4" outside the directive.
    assert ctx.count("Figure 4") == 1
    # Image url is not present.
    assert "/api/v1/x/img-5.png" not in ctx
    # And the original directive block is preserved.
    assert "::: figure [Figure 4" in ctx


def test_enrichment_appended_block_is_wrapped_in_directive():
    """When the LLM omitted the figure entirely, we append it — wrapped in a directive."""
    markdown = """
Figure 2: Setup diagram

![img-2](uploads/img-2.png)
""".strip()
    questions = [
        ParsedQuestion(
            question="Explain Figure 2.",
            model_answer="A",
            context=None,
            type="short",
        )
    ]
    _enrich_question_contexts(
        questions, markdown,
        image_url_by_path={"uploads/img-2.png": "/api/v1/x/img-2.png"},
    )
    ctx = questions[0].context
    assert ctx is not None
    # Wrapped in directive form, with caption.
    assert "::: figure [Figure 2 — Setup diagram]" in ctx
    assert ctx.rstrip().endswith(":::")
    # Image included inside.
    assert "![img-2](/api/v1/x/img-2.png)" in ctx
    # No bare "Figure 2\n!" pattern.
    assert "Figure 2\n![" not in ctx


def test_enrichment_injects_caption_into_existing_directive():
    """LLM emitted [Figure 4] without a caption; OCR has the caption — patch it in."""
    markdown = """
Figure 4: Income tax rates for 2023–24, compared to 2022–23
| Tax band | Rate |
| --- | --- |
| Basic | 20% |
""".strip()
    base_context = (
        "::: figure [Figure 4]\n"
        "| Tax band | Rate |\n"
        "| --- | --- |\n"
        "| Basic | 20% |\n"
        ":::"
    )
    questions = [
        ParsedQuestion(
            question="With reference to Figure 4, explain.",
            model_answer="A",
            context=base_context,
            type="short",
        )
    ]
    _enrich_question_contexts(questions, markdown, image_url_by_path={})
    ctx = questions[0].context
    assert ctx is not None
    assert "::: figure [Figure 4 — Income tax rates for 2023–24, compared to 2022–23]" in ctx
    # The bare `[Figure 4]` form is gone.
    assert "::: figure [Figure 4]" not in ctx


def test_enrichment_drops_pre_existing_orphan_figure_when_ref_covered():
    """Backfill scenario: stored context already contains a stray
    'Figure 4\\n![img]' AFTER a closing ::: of a [Figure 4] directive.
    The new pipeline must remove the orphan so the chart no longer renders
    inside the previous text block."""
    markdown = """
Figure 4: Income tax rates for 2023–24, compared to 2022–23
| Tax band | Rate |
| --- | --- |
| Basic | 20% |
""".strip()
    base_context = (
        "::: figure [Figure 4]\n"
        "| Tax band | Rate |\n"
        "| --- | --- |\n"
        "| Basic | 20% |\n"
        ":::\n"
        "::: text [Extract A]\n"
        "passage text\n"
        ":::\n"
        "\n"
        "Figure 4\n"
        "![img-5.jpeg](/api/v1/x/img-5.jpeg)"
    )
    questions = [
        ParsedQuestion(
            question="With reference to Figure 4 and Extract A, examine.",
            model_answer="A",
            context=base_context,
            type="short",
        )
    ]
    _enrich_question_contexts(questions, markdown, image_url_by_path={})
    ctx = questions[0].context
    assert ctx is not None
    # Orphan markdown must be gone.
    assert "Figure 4\n![img-5.jpeg]" not in ctx
    assert "/api/v1/x/img-5.jpeg" not in ctx
    # Original directives preserved (with caption now injected).
    assert "::: figure [Figure 4 — Income tax rates for 2023–24, compared to 2022–23]" in ctx
    assert "::: text [Extract A]" in ctx
    assert "passage text" in ctx


def test_enrichment_wraps_pre_existing_orphan_figure_when_ref_not_covered():
    """Orphan 'Figure 7\\n![img]' for a ref that isn't in any directive must
    be re-wrapped as a proper directive block (data preservation)."""
    markdown = """
Figure 7: Setup diagram
""".strip()
    base_context = (
        "::: text [Extract A]\n"
        "passage text\n"
        ":::\n"
        "\n"
        "Figure 7\n"
        "![img-7](/api/v1/x/img-7.jpeg)"
    )
    questions = [
        ParsedQuestion(
            question="With reference to Figure 7, explain.",
            model_answer="A",
            context=base_context,
            type="short",
        )
    ]
    _enrich_question_contexts(questions, markdown, image_url_by_path={})
    ctx = questions[0].context
    assert ctx is not None
    # Now wrapped as a directive with the OCR-derived caption.
    assert "::: figure [Figure 7 — Setup diagram]" in ctx
    assert "![img-7](/api/v1/x/img-7.jpeg)" in ctx
    # No bare label form remains.
    assert "\nFigure 7\n![img-7" not in ctx


def test_dedupe_question_strips_leading_context_paragraph():
    """Real bug scenario from row 67ff40e1."""
    from src.learning.past_paper.service import _dedupe_question_against_context

    question = (
        "In July 2020 a survey estimated that the marginal propensity to consume "
        "in the UK was 0.1.\n\n"
        "Calculate the total increase in aggregate demand from an increase in "
        "government spending of £60 million."
    )
    context = (
        "::: text\n"
        "In July 2020 a survey estimated that the marginal propensity to consume "
        "in the UK was 0.1.\n"
        ":::"
    )
    out = _dedupe_question_against_context(question, context)
    assert out == (
        "Calculate the total increase in aggregate demand from an increase in "
        "government spending of £60 million."
    )


def test_dedupe_question_no_op_when_no_overlap():
    from src.learning.past_paper.service import _dedupe_question_against_context

    question = "Calculate the multiplier given MPC = 0.1."
    context = "::: text [Extract A]\nA passage about something else entirely.\n:::"
    assert _dedupe_question_against_context(question, context) == question


def test_dedupe_question_no_op_when_only_partial_overlap():
    """Conservative: only strip on EXACT match of the leading paragraph."""
    from src.learning.past_paper.service import _dedupe_question_against_context

    question = (
        "In July 2020 a survey estimated that the MPC was 0.1.\n\n"
        "Calculate the multiplier."
    )
    context = (
        "::: text\n"
        "In July 2020 a survey estimated that the marginal propensity to consume "
        "in the UK was 0.1.\n"
        ":::"
    )
    # Leading paragraph "...the MPC was 0.1." is similar but NOT exact — leave as-is.
    assert _dedupe_question_against_context(question, context) == question


def test_dedupe_question_handles_none_context():
    from src.learning.past_paper.service import _dedupe_question_against_context

    question = "Calculate the multiplier."
    assert _dedupe_question_against_context(question, None) == question
    assert _dedupe_question_against_context(question, "") == question


def test_enrich_question_contexts_strips_duplicated_stem_from_question():
    markdown = (
        "In July 2020 a survey estimated that the marginal propensity to consume "
        "in the UK was 0.1.\n\n"
        "Calculate the total increase in aggregate demand."
    )
    questions = [
        ParsedQuestion(
            question=(
                "In July 2020 a survey estimated that the marginal propensity to "
                "consume in the UK was 0.1.\n\n"
                "Calculate the total increase in aggregate demand from an increase "
                "in government spending of £60 million."
            ),
            model_answer="A",
            context=(
                "::: text\n"
                "In July 2020 a survey estimated that the marginal propensity to "
                "consume in the UK was 0.1.\n"
                ":::"
            ),
            type="short",
        )
    ]
    _enrich_question_contexts(questions, markdown, image_url_by_path={})
    assert questions[0].question == (
        "Calculate the total increase in aggregate demand from an increase "
        "in government spending of £60 million."
    )
    # Context still has the stem.
    assert "marginal propensity" in (questions[0].context or "")


# --- Source citation stripping (26A-20) ---


def test_strip_source_citations_inline_parens():
    from src.learning.past_paper.service import _strip_source_citations

    text = "Inflation rose sharply (Source: ONS, 2023). Other text."
    assert _strip_source_citations(text) == "Inflation rose sharply . Other text."


def test_strip_source_citations_adapted_from():
    from src.learning.past_paper.service import _strip_source_citations

    text = "Some passage (adapted from BBC News, 2024) continues here."
    assert _strip_source_citations(text) == "Some passage continues here."


def test_strip_source_citations_full_line():
    from src.learning.past_paper.service import _strip_source_citations

    text = "Body paragraph one.\nSource: The Economist, 2023\nBody paragraph two."
    out = _strip_source_citations(text)
    assert "Source:" not in out
    assert "Body paragraph one." in out
    assert "Body paragraph two." in out


def test_strip_source_citations_empty_returns_none():
    from src.learning.past_paper.service import _strip_source_citations

    assert _strip_source_citations(None) is None
    assert _strip_source_citations("") == ""


# --- Unclosed directive blocks (26A-6) ---


def test_close_unclosed_directives_inserts_close_before_next_open():
    from src.learning.past_paper.service import _close_unclosed_directives

    text = (
        "::: text [Extract A]\n"
        "First passage body.\n"
        "::: figure [Figure 1]\n"
        "![alt](url)\n"
        ":::"
    )
    out = _close_unclosed_directives(text)
    # Should have inserted a `:::` before the figure opener.
    assert out == (
        "::: text [Extract A]\n"
        "First passage body.\n"
        ":::\n"
        "::: figure [Figure 1]\n"
        "![alt](url)\n"
        ":::"
    )


def test_close_unclosed_directives_appends_final_close():
    from src.learning.past_paper.service import _close_unclosed_directives

    text = "::: text [Extract A]\nBody text without closer."
    out = _close_unclosed_directives(text)
    assert out.endswith("\n:::")


def test_close_unclosed_directives_idempotent_when_well_formed():
    from src.learning.past_paper.service import _close_unclosed_directives

    text = (
        "::: text [Extract A]\n"
        "Body.\n"
        ":::\n"
        "::: figure [Figure 1]\n"
        "![alt](url)\n"
        ":::"
    )
    assert _close_unclosed_directives(text) == text


# --- Directive title normalization (26A-21 / 30) ---


def test_normalize_directive_titles_colon_to_em_dash():
    from src.learning.past_paper.service import _normalize_directive_titles

    text = "::: figure [Figure 4: Income tax rates]\n![alt](url)\n:::"
    out = _normalize_directive_titles(text)
    assert "[Figure 4 — Income tax rates]" in out


def test_normalize_directive_titles_hyphen_to_em_dash():
    from src.learning.past_paper.service import _normalize_directive_titles

    text = "::: text [extract b - inflation outlook]\nBody.\n:::"
    out = _normalize_directive_titles(text)
    assert "[Extract b — inflation outlook]" in out


def test_normalize_directive_titles_no_caption_keeps_label():
    from src.learning.past_paper.service import _normalize_directive_titles

    text = "::: figure [Figure 1]\n![alt](url)\n:::"
    out = _normalize_directive_titles(text)
    assert "[Figure 1]" in out


def test_normalize_directive_titles_unrecognised_kind_left_alone():
    from src.learning.past_paper.service import _normalize_directive_titles

    text = "::: text [Some custom title]\nBody.\n:::"
    out = _normalize_directive_titles(text)
    assert "[Some custom title]" in out


# --- MCQ option dedup (26A-3 / 23) ---


def test_dedupe_mcq_options_drops_exact_duplicates():
    from src.learning.past_paper.service import _dedupe_mcq_options

    options = ["alpha", "beta", "alpha", "gamma"]
    new_opts, new_correct = _dedupe_mcq_options(options, correct_option_index=1)
    assert new_opts == ["alpha", "beta", "gamma"]
    assert new_correct == 1  # beta moved from index 1 to index 1


def test_dedupe_mcq_options_remaps_correct_index_after_dedup():
    from src.learning.past_paper.service import _dedupe_mcq_options

    # The correct answer is the duplicate at index 2; should remap to index 0.
    options = ["alpha", "beta", "alpha"]
    new_opts, new_correct = _dedupe_mcq_options(options, correct_option_index=2)
    assert new_opts == ["alpha", "beta"]
    assert new_correct == 0


def test_dedupe_mcq_options_case_and_whitespace_insensitive():
    from src.learning.past_paper.service import _dedupe_mcq_options

    options = ["£12 million", "  £12 million  ", "£20 million"]
    new_opts, new_correct = _dedupe_mcq_options(options, correct_option_index=2)
    assert new_opts == ["£12 million", "£20 million"]
    assert new_correct == 1


def test_dedupe_mcq_options_no_duplicates_passthrough():
    from src.learning.past_paper.service import _dedupe_mcq_options

    options = ["a", "b", "c"]
    out_opts, out_idx = _dedupe_mcq_options(options, correct_option_index=2)
    assert out_opts == options
    assert out_idx == 2


def test_dedupe_mcq_options_none_passthrough():
    from src.learning.past_paper.service import _dedupe_mcq_options

    out_opts, out_idx = _dedupe_mcq_options(None, correct_option_index=None)
    assert out_opts is None
    assert out_idx is None


# --- Strip MCQ options leaked into context ---


def test_strip_mcq_options_from_context_removes_tickbox_lines():
    from src.learning.past_paper.service import _strip_mcq_options_from_context

    context = (
        "::: text\n"
        "10 people can complete a job in 9 hours.\n"
        ":::\n"
        "□ It is greater than the answer to (a)\n"
        "□ It is the same as the answer to (a)\n"
        "□ It is less than the answer to (a)\n"
        "□ It is not possible to say"
    )
    options = [
        "It is greater than the answer to (a)",
        "It is the same as the answer to (a)",
        "It is less than the answer to (a)",
        "It is not possible to say",
    ]
    out = _strip_mcq_options_from_context(context, options)
    assert "□" not in out
    for opt in options:
        assert opt not in out
    assert "10 people can complete a job in 9 hours." in out


def test_strip_mcq_options_removes_tick_one_box_instruction():
    from src.learning.past_paper.service import _strip_mcq_options_from_context

    context = "Some passage.\nTick one box."
    out = _strip_mcq_options_from_context(context, options=["A", "B", "C", "D"])
    assert "Tick one box" not in out
    assert "Some passage." in out


def test_strip_mcq_options_handles_letter_prefixes():
    from src.learning.past_paper.service import _strip_mcq_options_from_context

    context = "Stimulus.\nA. alpha\nB. beta\nC. gamma"
    options = ["alpha", "beta", "gamma"]
    out = _strip_mcq_options_from_context(context, options)
    assert "alpha" not in out
    assert "Stimulus." in out


def test_strip_mcq_options_passthrough_when_none():
    from src.learning.past_paper.service import _strip_mcq_options_from_context

    assert _strip_mcq_options_from_context(None, options=["a"]) is None
    text = "Just stimulus, no options."
    assert _strip_mcq_options_from_context(text, options=None) == text


def test_strip_mcq_options_preserves_directive_lines():
    from src.learning.past_paper.service import _strip_mcq_options_from_context

    context = (
        "::: text [Extract A]\n"
        "Body text.\n"
        ":::"
    )
    out = _strip_mcq_options_from_context(context, options=["alpha"])
    assert out == context
