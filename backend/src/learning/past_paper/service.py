"""Past paper upload pipeline and CRUD operations.

Creates TestTemplate(type='past_paper') + TestQuestion rows using the
unified test schema.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.past_paper.mistral import PastPaperOCR
from src.learning.past_paper.node_matcher import NodeInfo, RoadmapNodeMatcher
from src.learning.past_paper.parser import PastPaperParser
from src.prompts.manager import PromptManager
from src.learning.past_paper.schemas import ParsedQuestion
from src.learning.tests.models import TestQuestion, TestTemplate
from src.roadmap.models import RoadmapNode

logger = logging.getLogger(__name__)

_IMG_REF_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LABEL_ONLY_CONTEXT_RE = re.compile(
    r"^\s*(?:table|figure)\s+\d+[a-z]?\s*[:.]?\s*$",
    re.IGNORECASE,
)
_TABLE_REF_RE = re.compile(r"\btable\s+(\d+[a-z]?)\b", re.IGNORECASE)
_FIGURE_REF_RE = re.compile(r"\bfigure\s+(\d+[a-z]?)\b", re.IGNORECASE)
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_DIRECTIVE_REF_RE = re.compile(
    r"^\s*:::\s*(?:text|figure)\s*\[\s*(Figure|Table)\s+(\d+[a-z]?)\b",
    re.IGNORECASE | re.MULTILINE,
)
_CAPTION_RE = re.compile(
    r"^\s*(Figure|Table)\s+(\d+[a-z]?)\s*[:\-–—]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class PastPaperError(Exception):
    """Business-logic failures in the past paper domain."""


@dataclass(slots=True)
class MarkSchemeUploadJob:
    id: uuid.UUID
    user_id: uuid.UUID
    past_paper_id: uuid.UUID
    status: str
    phase: str | None
    message: str | None
    matched_questions: int | None
    total_short_questions: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    events: list[dict[str, Any]] = field(default_factory=list)


_MARK_SCHEME_JOB_RETENTION = timedelta(hours=6)
_MARK_SCHEME_UPLOAD_JOBS: dict[uuid.UUID, MarkSchemeUploadJob] = {}
_MARK_SCHEME_UPLOAD_TASKS: dict[uuid.UUID, asyncio.Task[None]] = {}
_MARK_SCHEME_UPLOAD_LOCK = asyncio.Lock()


@dataclass(slots=True)
class _AssignmentQuestion:
    index: int
    question: str
    type: str
    model_answer: str | None


def _compute_pdf_sha256(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def _extract_mark_scheme_sha256(template: TestTemplate) -> str | None:
    if template.mark_scheme_sha256:
        return template.mark_scheme_sha256
    meta = template.generation_progress
    if not isinstance(meta, dict):
        return None
    value = meta.get("mark_scheme_sha256")
    if isinstance(value, str) and value:
        return value
    return None


def _rewrite_template_asset_refs(
    text: str | None,
    source_template_id: uuid.UUID,
    target_template_id: uuid.UUID,
) -> str | None:
    if text is None:
        return None
    source_prefix = f"past-papers/{source_template_id}/"
    target_prefix = f"past-papers/{target_template_id}/"
    source_api_prefix = f"/past-papers/{source_template_id}/"
    target_api_prefix = f"/past-papers/{target_template_id}/"
    return (
        text.replace(source_prefix, target_prefix)
        .replace(source_api_prefix, target_api_prefix)
    )


async def _clone_s3_prefix(
    s3: "S3Client",
    source_prefix: str,
    target_prefix: str,
) -> None:
    continuation_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "Bucket": s3._settings.bucket,
            "Prefix": source_prefix,
        }
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = await s3._client.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []):
            source_key = obj["Key"]
            target_key = source_key.replace(source_prefix, target_prefix, 1)
            await s3._client.copy_object(
                Bucket=s3._settings.bucket,
                CopySource={"Bucket": s3._settings.bucket, "Key": source_key},
                Key=target_key,
                MetadataDirective="COPY",
            )

        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")


async def _clone_cached_past_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cached: TestTemplate,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    name: str,
    original_filename: str,
    pdf_bytes: bytes,
    pdf_sha256: str,
    mark_scheme_bytes: bytes | None,
    mark_scheme_sha256: str | None,
    mark_scheme_filename: str | None,
    s3: "S3Client | None",
) -> TestTemplate:
    template_id = uuid.uuid4()

    cloned_ocr_markdown = _rewrite_template_asset_refs(
        cached.ocr_markdown,
        cached.id,
        template_id,
    )
    cloned_questions = [
        TestQuestion(
            template_id=template_id,
            index=q.index,
            item_id=_compute_item_id(template_id, q.question),
            type=q.type,
            question=q.question,
            model_answer=q.model_answer,
            mark_scheme=q.mark_scheme if mark_scheme_sha256 else None,
            context=_rewrite_template_asset_refs(q.context, cached.id, template_id),
            options=q.options,
            correct_option_index=q.correct_option_index,
            hint=q.hint,
            points=q.points,
            sources=q.sources,
            node_ids=q.node_ids,
            is_unsupported=q.is_unsupported,
        )
        for q in cached.questions
    ]
    cloned_template = TestTemplate(
        id=template_id,
        user_id=user_id,
        folder_id=folder_id,
        name=name,
        type="past_paper",
        status="ready",
        original_filename=original_filename,
        mark_scheme_filename=mark_scheme_filename if mark_scheme_sha256 else None,
        source_pdf_sha256=pdf_sha256,
        mark_scheme_sha256=mark_scheme_sha256,
        is_canonical=False,
        generation_progress=None,
        node_ids=cached.node_ids,
        total_questions=cached.total_questions,
        total_marks=cached.total_marks,
        mark_scheme=cached.mark_scheme if mark_scheme_sha256 else None,
        ocr_markdown=cloned_ocr_markdown,
    )

    if s3:
        source_prefix = f"past-papers/{cached.id}"
        target_prefix = f"past-papers/{template_id}"

        await s3.upload_bytes(
            f"{target_prefix}/origin/paper.pdf",
            pdf_bytes,
            content_type="application/pdf",
        )
        if cloned_ocr_markdown:
            await s3.upload_bytes(
                f"{target_prefix}/origin_md/paper.md",
                cloned_ocr_markdown.encode("utf-8"),
                content_type="text/markdown",
            )

        await _clone_s3_prefix(
            s3,
            f"{source_prefix}/assets/",
            f"{target_prefix}/assets/",
        )

        if mark_scheme_sha256 and mark_scheme_bytes:
            await s3.upload_bytes(
                f"{target_prefix}/origin/mark-scheme.pdf",
                mark_scheme_bytes,
                content_type="application/pdf",
            )
            if cloned_template.mark_scheme:
                await s3.upload_bytes(
                    f"{target_prefix}/origin_md/mark-scheme.md",
                    cloned_template.mark_scheme.encode("utf-8"),
                    content_type="text/markdown",
                )

    async with session_factory() as db:
        db.add(cloned_template)
        db.add_all(cloned_questions)
        await db.commit()
        result = await db.execute(
            select(TestTemplate)
            .where(TestTemplate.id == template_id)
            .options(selectinload(TestTemplate.questions))
        )
        return result.scalar_one()


async def _find_cached_past_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    pdf_sha256: str,
) -> TestTemplate | None:
    """Find the canonical past-paper template for this PDF SHA, if any.

    A canonical template is one an admin has explicitly hashed via the
    /admin/past-papers UI. When found, the upload pipeline clones it
    instead of re-running OCR/parsing.
    """
    async with session_factory() as db:
        result = await db.execute(
            select(TestTemplate)
            .where(
                TestTemplate.is_canonical.is_(True),
                TestTemplate.type == "past_paper",
                TestTemplate.status == "ready",
                TestTemplate.source_pdf_sha256 == pdf_sha256,
            )
            .options(selectinload(TestTemplate.questions))
            .order_by(TestTemplate.created_at.desc())
            .limit(1)
        )
        cached = result.scalar_one_or_none()
        if cached is None or not cached.questions:
            return None
        return cached


# ---------------------------------------------------------------------------
# Upload pipeline
# ---------------------------------------------------------------------------


async def upload_and_process(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    pdf_bytes: bytes,
    name: str,
    original_filename: str,
    folder_id: uuid.UUID,
    mark_scheme_bytes: bytes | None = None,
    usage_service: object | None = None,
    s3: "S3Client | None" = None,
    prompt_manager: PromptManager | None = None,
) -> TestTemplate:
    """
    Full pipeline:
      1. Fetch roadmap nodes (short-lived session, released immediately)
      2. OCR past paper + mark scheme (Mistral) — no DB connection held
      3. LLM parses questions
      4. LLM matches questions to roadmap nodes
      5. Persist TestTemplate + TestQuestion rows in a single commit
    """
    mark_scheme_sha256 = (
        _compute_pdf_sha256(mark_scheme_bytes) if mark_scheme_bytes else None
    )
    pdf_sha256 = _compute_pdf_sha256(pdf_bytes)
    cached = await _find_cached_past_paper(
        session_factory=session_factory,
        pdf_sha256=pdf_sha256,
    )
    if cached is not None:
        logger.info(
            "Past paper cache hit user_id=%s folder_id=%s paper_id=%s",
            user_id,
            folder_id,
            cached.id,
        )
        return await _clone_cached_past_paper(
            session_factory=session_factory,
            cached=cached,
            user_id=user_id,
            folder_id=folder_id,
            name=name,
            original_filename=original_filename,
            pdf_bytes=pdf_bytes,
            pdf_sha256=pdf_sha256,
            mark_scheme_bytes=mark_scheme_bytes,
            mark_scheme_sha256=mark_scheme_sha256,
            mark_scheme_filename=None,
            s3=s3,
        )

    settings = get_settings()
    ocr = PastPaperOCR(settings.mistral)
    llm = YandexGPTLLMGateway()
    _usage_svc = usage_service
    parser = PastPaperParser(llm, usage_service=_usage_svc, prompt_manager=prompt_manager)
    parser._current_user_id = user_id
    matcher = RoadmapNodeMatcher(llm, usage_service=_usage_svc, prompt_manager=prompt_manager)
    matcher._current_user_id = user_id
    template_id = uuid.uuid4()

    # ── Phase 1: Quick DB read — own session, released when block exits ───────
    async with session_factory() as db:
        nodes_result = await db.execute(
            select(
                RoadmapNode.id,
                RoadmapNode.level,
                RoadmapNode.name,
                RoadmapNode.position,
                RoadmapNode.parent_id,
            )
            .where(RoadmapNode.folder_id == folder_id)
            .order_by(RoadmapNode.level, RoadmapNode.position)
        )
        roadmap_nodes = [
            NodeInfo(
                id=row.id,
                level=row.level,
                name=row.name,
                position=row.position,
                parent_id=row.parent_id,
            )
            for row in nodes_result.all()
        ]

    level_counts: dict[int, int] = {}
    for n in roadmap_nodes:
        level_counts[n.level] = level_counts.get(n.level, 0) + 1
    logger.info(
        "Roadmap nodes for folder_id=%s: total=%d levels=%s",
        folder_id,
        len(roadmap_nodes),
        level_counts,
    )

    # ── Phase 2: All slow I/O (OCR + LLM) — no DB connection held ────────────
    mark_scheme_markdown: str | None = None
    try:
        markdown, images_dict, tables_dict = await ocr.pdf_to_markdown_with_images(pdf_bytes)
        if s3 and images_dict:
            path_map = await _upload_images_to_s3(s3, template_id, images_dict)
        else:
            path_map = {img_id: f"uploads/images/{img_id}.png" for img_id in images_dict}
        markdown = _replace_image_refs(markdown, path_map)
        image_url_by_path = _build_image_url_map(template_id, path_map)

        if mark_scheme_bytes:
            ms_text, _, _ = await ocr.pdf_to_markdown_with_images(mark_scheme_bytes)
            mark_scheme_markdown = ms_text.strip() or None
            if not mark_scheme_markdown:
                logger.warning(
                    "Mark scheme OCR returned empty content for template_id=%s — "
                    "mark scheme will be ignored",
                    template_id,
                )

        if s3:
            await _save_ocr_assets_to_s3(
                s3, template_id,
                pdf_bytes=pdf_bytes,
                markdown=markdown,
                images_dict=images_dict,
                tables_dict=tables_dict,
                mark_scheme_bytes=mark_scheme_bytes,
                mark_scheme_markdown=mark_scheme_markdown,
            )

        parsed_questions = await parser.parse(markdown, mark_scheme_markdown)
        _enrich_question_contexts(parsed_questions, markdown, image_url_by_path)
        applied_ms, total_short = _sanitize_mark_schemes_on_parsed_questions(
            parsed_questions
        )
        if mark_scheme_markdown and total_short > 0 and applied_ms == 0:
            try:
                applied_ms, total_short = await _fallback_assign_mark_schemes(
                    parser,
                    parsed_questions,
                    mark_scheme_markdown,
                )
            except Exception as fallback_exc:
                logger.warning(
                    "Mark scheme fallback matching failed for template_id=%s: %s",
                    template_id,
                    fallback_exc,
                    exc_info=True,
                )
        if mark_scheme_markdown:
            logger.info(
                "Applied mark scheme answers: %d out of %d short-answer questions "
                "(total questions=%d) for template_id=%s",
                applied_ms,
                total_short,
                len(parsed_questions),
                template_id,
            )
            if applied_ms == 0:
                logger.info(
                    "No mark scheme entries matched for template_id=%s; "
                    "mark schemes were cleared automatically",
                    template_id,
                )

        node_mapping: dict[int, list[uuid.UUID]] = {}
        try:
            node_mapping = await matcher.match(roadmap_nodes, parsed_questions)
        except Exception as match_exc:
            logger.error(
                "Node matching failed for folder_id=%s (non-fatal): %s",
                folder_id,
                match_exc,
                exc_info=True,
            )

        question_rows = _build_question_rows(template_id, parsed_questions)
        for row in question_rows:
            matched = node_mapping.get(row.index)
            row.node_ids = matched if matched else None

    except Exception as exc:
        logger.error(
            "Past paper processing failed template_id=%s: %s",
            template_id,
            exc,
            exc_info=True,
        )
        async with session_factory() as db:
            db.add(
                TestTemplate(
                    id=template_id,
                    user_id=user_id,
                    folder_id=folder_id,
                    name=name,
                    type="past_paper",
                    status="failed",
                    original_filename=original_filename,
                    source_pdf_sha256=pdf_sha256,
                    mark_scheme_sha256=mark_scheme_sha256,
                    generation_progress=None,
                    total_questions=0,
                )
            )
            await db.commit()
        raise PastPaperError(f"Processing failed: {exc}") from exc

    # ── Phase 3: Persist everything in one commit ─────────────────────────────
    # Aggregate all unique node_ids matched across questions for the template
    all_node_ids: list[uuid.UUID] = list(
        dict.fromkeys(
            nid
            for row in question_rows
            if row.node_ids
            for nid in row.node_ids
        )
    )

    async with session_factory() as db:
        template = TestTemplate(
            id=template_id,
            user_id=user_id,
            folder_id=folder_id,
            name=name,
            type="past_paper",
            status="ready",
            original_filename=original_filename,
            source_pdf_sha256=pdf_sha256,
            mark_scheme_sha256=mark_scheme_sha256,
            generation_progress=None,
            total_questions=len(question_rows),
            total_marks=sum(q.points for q in question_rows),
            mark_scheme=_template_mark_scheme_value(mark_scheme_markdown, applied_ms),
            node_ids=all_node_ids or None,
            ocr_markdown=markdown,
        )
        db.add(template)
        db.add_all(question_rows)
        await db.commit()

        result = await db.execute(
            select(TestTemplate)
            .where(TestTemplate.id == template_id)
            .options(selectinload(TestTemplate.questions))
        )
        return result.scalar_one()


_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,")


def _decode_image_base64(b64_data: str) -> bytes:
    """Decode base64 image data, stripping data URI prefix if present."""
    import base64

    cleaned = _DATA_URI_RE.sub("", b64_data)
    return base64.b64decode(cleaned)


async def _upload_images_to_s3(
    s3: "S3Client",
    template_id: uuid.UUID,
    images_dict: dict[str, str],
) -> dict[str, str]:
    """Upload extracted images to S3, return {image_id: s3_key} map."""
    path_map: dict[str, str] = {}
    for image_id, b64_data in images_dict.items():
        image_bytes = _decode_image_base64(b64_data)
        # Detect format and avoid double extensions
        if "." in image_id:
            filename = image_id
        elif image_bytes[:2] == b"\xff\xd8":
            filename = f"{image_id}.jpeg"
        else:
            filename = f"{image_id}.png"
        content_type = "image/jpeg" if filename.endswith((".jpeg", ".jpg")) else "image/png"
        s3_key = f"past-papers/{template_id}/assets/images/{filename}"
        await s3.upload_bytes(s3_key, image_bytes, content_type=content_type)
        path_map[image_id] = s3_key
    return path_map


async def _save_ocr_assets_to_s3(
    s3: "S3Client",
    template_id: uuid.UUID,
    *,
    pdf_bytes: bytes,
    markdown: str,
    images_dict: dict[str, str],
    tables_dict: dict[str, str] | None = None,
    mark_scheme_bytes: bytes | None = None,
    mark_scheme_markdown: str | None = None,
) -> None:
    """Save all OCR artifacts to S3. Keys are deterministic from template_id.

    Layout:
        past-papers/{template_id}/origin/paper.pdf
        past-papers/{template_id}/origin/mark-scheme.pdf
        past-papers/{template_id}/origin_md/paper.md
        past-papers/{template_id}/origin_md/mark-scheme.md
        past-papers/{template_id}/assets/{image_id}.png
        past-papers/{template_id}/assets/tables/{tbl_id}

    """
    prefix = f"past-papers/{template_id}"

    # Origin PDFs
    await s3.upload_bytes(
        f"{prefix}/origin/paper.pdf", pdf_bytes, content_type="application/pdf"
    )

    # Origin markdown
    await s3.upload_bytes(
        f"{prefix}/origin_md/paper.md",
        markdown.encode("utf-8"),
        content_type="text/markdown",
    )

    # Table markdown files
    for tbl_id, tbl_content in (tables_dict or {}).items():
        await s3.upload_bytes(
            f"{prefix}/assets/tables/{tbl_id}",
            tbl_content.encode("utf-8"),
            content_type="text/markdown",
        )

    if mark_scheme_bytes:
        await s3.upload_bytes(
            f"{prefix}/origin/mark-scheme.pdf",
            mark_scheme_bytes,
            content_type="application/pdf",
        )
    if mark_scheme_markdown:
        await s3.upload_bytes(
            f"{prefix}/origin_md/mark-scheme.md",
            mark_scheme_markdown.encode("utf-8"),
            content_type="text/markdown",
        )


def _replace_image_refs(markdown: str, path_map: dict[str, str]) -> str:
    def replace(m: re.Match) -> str:
        alt = m.group(1)
        src = m.group(2)
        new_src = path_map.get(src) or path_map.get(alt)
        if new_src:
            return f"![{alt}]({new_src})"
        return m.group(0)

    return _IMG_REF_RE.sub(replace, markdown)


def _build_image_url_map(
    template_id: uuid.UUID,
    path_map: dict[str, str],
    api_prefix: str = "/api/v1",
) -> dict[str, str]:
    """Map S3 keys to clean backend serving URLs."""
    url_map: dict[str, str] = {}
    for image_id, s3_key in path_map.items():
        # Extract just the filename from the S3 key
        filename = s3_key.rsplit("/", 1)[-1]
        url_map[s3_key] = f"{api_prefix}/past-papers/{template_id}/assets/images/{filename}"
    return url_map


def _normalize_mark_scheme_text(mark_scheme: str | None) -> str | None:
    if mark_scheme is None:
        return None
    normalized = str(mark_scheme).strip()
    return normalized or None


def _template_mark_scheme_value(
    mark_scheme_markdown: str | None,
    applied_matches: int,
) -> str | None:
    if not mark_scheme_markdown:
        return None
    if applied_matches <= 0:
        return None
    return mark_scheme_markdown


def _sanitize_mark_schemes_on_parsed_questions(
    questions: list[ParsedQuestion],
) -> tuple[int, int]:
    applied = 0
    total_short = 0
    for question in questions:
        if question.type != "short":
            question.mark_scheme = None
            continue
        total_short += 1
        question.mark_scheme = _normalize_mark_scheme_text(question.mark_scheme)
        if question.mark_scheme:
            applied += 1
    return applied, total_short


def _prepare_mark_scheme_assignment(
    questions: list[TestQuestion],
    assignment: dict[int, str | None],
) -> tuple[dict[int, str | None], int, int]:
    updates: dict[int, str | None] = {}
    applied = 0
    total_short = 0

    for question in questions:
        if question.type != "short" or getattr(question, "is_unsupported", False):
            updates[question.index] = None
            continue
        total_short += 1
        normalized = _normalize_mark_scheme_text(assignment.get(question.index))
        updates[question.index] = normalized
        if normalized:
            applied += 1

    return updates, applied, total_short


async def _fallback_assign_mark_schemes(
    parser: PastPaperParser,
    parsed_questions: list[ParsedQuestion],
    mark_scheme_markdown: str,
) -> tuple[int, int]:
    assignment_questions = [
        _AssignmentQuestion(
            index=i,
            question=q.question,
            type=q.type,
            model_answer=q.model_answer,
        )
        for i, q in enumerate(parsed_questions)
    ]
    assignment = await parser.assign_mark_schemes(
        assignment_questions,
        mark_scheme_markdown,
    )
    updates, applied, total_short = _prepare_mark_scheme_assignment(
        assignment_questions,
        assignment,
    )
    by_index = {i: q for i, q in enumerate(parsed_questions)}
    for idx, mark_scheme in updates.items():
        question = by_index.get(idx)
        if question is not None and question.type == "short":
            question.mark_scheme = mark_scheme
    return applied, total_short


def _extract_reference_ids(text: str, pattern: re.Pattern[str]) -> list[str]:
    seen: set[str] = set()
    refs: list[str] = []
    for match in pattern.finditer(text):
        ref = match.group(1).lower()
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _extract_nearby_reference(
    lines: list[str], line_index: int, pattern: re.Pattern[str]
) -> str | None:
    """Search backward and forward from line_index for a pattern match."""
    # Search backward (up to 10 lines)
    start = max(0, line_index - 10)
    for idx in range(line_index, start - 1, -1):
        match = pattern.search(lines[idx])
        if match:
            return match.group(1).lower()
    # Search forward (up to 5 lines)
    end = min(len(lines), line_index + 6)
    for idx in range(line_index + 1, end):
        match = pattern.search(lines[idx])
        if match:
            return match.group(1).lower()
    return None


def _directive_refs(base: str | None) -> tuple[set[str], set[str]]:
    """Return (figure_refs, table_refs) already wrapped in ::: directives."""
    if not base:
        return set(), set()
    figs: set[str] = set()
    tabs: set[str] = set()
    for kind, ref in _DIRECTIVE_REF_RE.findall(base):
        if kind.lower() == "figure":
            figs.add(ref.lower())
        else:
            tabs.add(ref.lower())
    return figs, tabs


_DIRECTIVE_LABEL_RE = re.compile(
    r"^(\s*:::\s*(?:text|figure)\s*\[\s*)(Figure|Table)\s+(\d+[a-z]?)(\s*\])",
    re.IGNORECASE | re.MULTILINE,
)


_TEXT_DIRECTIVE_BLOCK_RE = re.compile(
    r"^\s*:::\s*text(?:\s*\[[^\]]*\])?\s*$([\s\S]*?)(?=^\s*:::|\Z)",
    re.IGNORECASE | re.MULTILINE,
)
_DIRECTIVE_OPEN_RE = re.compile(r"^\s*:::\s*(?:text|figure)\b", re.IGNORECASE)
_DIRECTIVE_CLOSE_RE = re.compile(r"^\s*:::\s*$")
_BARE_FIG_LABEL_RE = re.compile(
    r"^\s*(Figure|Table)\s+(\d+[a-z]?)\s*$", re.IGNORECASE
)
_BARE_IMG_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)\s]+\)\s*$")


def _normalize_orphan_figures(
    base: str,
    figure_captions: dict[str, str],
    table_captions: dict[str, str],
) -> str:
    """Clean up `(Figure|Table) N\\n![...]` blocks that sit OUTSIDE any ::: directive.

    Drops the pair when ref N is already wrapped in a directive elsewhere in
    `base` (it's a duplicate left over from the old enrichment). Otherwise
    rewraps it as a `::: figure [...]` directive so the frontend doesn't
    absorb it into the previous block.
    """
    if not base:
        return base

    fig_refs, tab_refs = _directive_refs(base)
    lines = base.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_directive = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if not in_directive and _DIRECTIVE_OPEN_RE.match(line):
            in_directive = True
            out.append(line)
            i += 1
            continue
        if in_directive:
            if _DIRECTIVE_CLOSE_RE.match(line):
                in_directive = False
            out.append(line)
            i += 1
            continue

        # Outside any directive — look for `(Figure|Table) N` followed by an image.
        m = _BARE_FIG_LABEL_RE.match(line)
        if m and i + 1 < len(lines) and _BARE_IMG_LINE_RE.match(lines[i + 1]):
            kind = m.group(1)
            ref = m.group(2).lower()
            covered = ref in (fig_refs if kind.lower() == "figure" else tab_refs)
            if covered:
                # Drop the orphan duplicate; eat any single trailing blank line.
                i += 2
                if i < len(lines) and lines[i].strip() == "":
                    i += 1
                # Trim a trailing blank we already emitted.
                while out and out[-1].strip() == "":
                    out.pop()
                continue
            captions = (
                figure_captions if kind.lower() == "figure" else table_captions
            )
            caption = captions.get(ref)
            label = (
                f"{kind} {m.group(2)} — {caption}" if caption
                else f"{kind} {m.group(2)}"
            )
            out.append(f"::: figure [{label}]")
            out.append(lines[i + 1].strip())
            out.append(":::")
            i += 2
            continue

        out.append(line)
        i += 1
    return "\n".join(out)


def _normalize_paragraph(text: str) -> str:
    """Collapse whitespace for paragraph-equivalence comparison."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_text_block_bodies(context: str | None) -> list[str]:
    """Return the bodies of all `::: text` blocks in the context.

    For legacy plain-text contexts (no directives), returns the whole string
    as a single body.
    """
    if not context:
        return []
    text = context.replace("\r\n", "\n")
    bodies: list[str] = []
    for match in _TEXT_DIRECTIVE_BLOCK_RE.finditer(text):
        body = match.group(1).strip()
        body = re.sub(r"\n?\s*:::\s*$", "", body).strip()
        if body:
            bodies.append(body)
    if not bodies:
        bodies.append(text.strip())
    return bodies


def _dedupe_question_against_context(question: str, context: str | None) -> str:
    """Strip the leading paragraph from `question` if it duplicates `context`.

    Conservative: only the first paragraph (text up to the first blank line),
    only on exact whitespace-normalized match against any `::: text` body
    in the context, only when the remainder is non-empty.
    """
    if not question or not context:
        return question

    paragraphs = re.split(r"\n\s*\n", question, maxsplit=1)
    if len(paragraphs) < 2:
        return question
    leading, rest = paragraphs[0], paragraphs[1].lstrip()
    if not rest:
        return question

    leading_norm = _normalize_paragraph(leading)
    if not leading_norm:
        return question

    for body in _extract_text_block_bodies(context):
        if _normalize_paragraph(body) == leading_norm:
            return rest
    return question


_SOURCE_CITATION_RE = re.compile(
    r"\(\s*(?:source|adapted\s+from)\b[^)]*\)\s*",
    re.IGNORECASE,
)
_SOURCE_LINE_RE = re.compile(
    r"^\s*(?:Source|Adapted\s+from)\s*:\s*.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_source_citations(text: str | None) -> str | None:
    """Remove `(Source ...)`, `(adapted from ...)`, and `Source: ...` lines.

    Applied to context blocks where citations leak through despite prompt rules.
    """
    if not text:
        return text
    cleaned = _SOURCE_CITATION_RE.sub("", text)
    cleaned = _SOURCE_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or None


_DIRECTIVE_OPENER_LINE_RE = re.compile(
    r"^\s*:::\s*(?:text|figure)\b.*$",
    re.IGNORECASE,
)
_DIRECTIVE_CLOSER_LINE_RE = re.compile(r"^\s*:::\s*$")


def _close_unclosed_directives(context: str | None) -> str | None:
    """Ensure every `::: type [...]` block is closed with a `:::` line.

    Walks the context line by line. Whenever an opener is seen while another
    block is still open, inserts a closing `:::` before the new opener. Adds a
    final closer if the context ends inside an open block.
    """
    if not context:
        return context
    lines = context.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_block = False
    for line in lines:
        if _DIRECTIVE_OPENER_LINE_RE.match(line):
            if in_block:
                out.append(":::")
            out.append(line)
            in_block = True
            continue
        if _DIRECTIVE_CLOSER_LINE_RE.match(line):
            out.append(line)
            in_block = False
            continue
        out.append(line)
    if in_block:
        out.append(":::")
    return "\n".join(out)


_DIRECTIVE_TITLE_RE = re.compile(
    r"^(\s*:::\s*(text|figure)\s*\[)([^\]]+)(\]\s*)$",
    re.IGNORECASE | re.MULTILINE,
)
_TITLE_KIND_RE = re.compile(
    r"^\s*(figure|table|extract)\s+([A-Za-z0-9]+)\b\s*[:\-—–]?\s*(.*)$",
    re.IGNORECASE,
)


def _normalize_directive_titles(context: str | None) -> str | None:
    """Normalize `[Figure 1: caption]` / `[Figure 1 - caption]` to `[Figure 1 — caption]`.

    Also fixes casing on the kind label (e.g. `figure 1` -> `Figure 1`). Leaves
    titles without a recognised kind prefix untouched.
    """
    if not context:
        return context

    def repl(m: re.Match[str]) -> str:
        prefix, _kind, raw_title, suffix = m.group(1), m.group(2), m.group(3), m.group(4)
        title = raw_title.strip()
        km = _TITLE_KIND_RE.match(title)
        if not km:
            return f"{prefix}{title}{suffix}"
        kind_word = km.group(1).capitalize()
        identifier = km.group(2)
        caption = km.group(3).strip().rstrip(".,;: ")
        if caption:
            normalized = f"{kind_word} {identifier} — {caption}"
        else:
            normalized = f"{kind_word} {identifier}"
        return f"{prefix}{normalized}{suffix}"

    return _DIRECTIVE_TITLE_RE.sub(repl, context)


_MCQ_INSTRUCTION_LINE_RE = re.compile(
    r"^\s*(?:tick\s+one\s+box|select\s+one(?:\s+answer)?|circle\s+one|"
    r"choose\s+one(?:\s+option)?)\.?\s*$",
    re.IGNORECASE,
)
_MCQ_OPTION_PREFIX_RE = re.compile(
    r"^\s*(?:[☐☑☒□■]|"
    r"\[\s*[xX ]?\s*\]|"
    r"[A-D][.):]"
    r")\s+",
)


def _strip_mcq_options_from_context(
    context: str | None,
    options: list[str] | None,
) -> str | None:
    """Drop lines mirroring MCQ options, tick-box markers, or "Tick one box." instructions.

    Only meaningful for MCQ questions. Compares each line to every option
    string after stripping common prefixes (`A.`, `□`, `[ ]`) and normalizing
    whitespace and case.
    """
    if not context:
        return context
    option_keys: set[str] = set()
    if options:
        for opt in options:
            stripped = _MCQ_OPTION_PREFIX_RE.sub("", opt or "").strip()
            if stripped:
                option_keys.add(_normalize_paragraph(stripped).lower())

    out_lines: list[str] = []
    for line in context.replace("\r\n", "\n").split("\n"):
        if _MCQ_INSTRUCTION_LINE_RE.match(line):
            continue
        bare = _MCQ_OPTION_PREFIX_RE.sub("", line).strip()
        if bare and option_keys and _normalize_paragraph(bare).lower() in option_keys:
            continue
        out_lines.append(line)

    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or None


def _dedupe_mcq_options(
    options: list[str] | None,
    correct_option_index: int | None,
) -> tuple[list[str] | None, int | None]:
    """Drop duplicate option strings while preserving order.

    Two options are considered duplicates when their normalized text matches
    (whitespace-collapsed, case-insensitive). The correct option index is
    remapped to the first surviving occurrence.
    """
    if not options:
        return options, correct_option_index

    seen: dict[str, int] = {}
    new_options: list[str] = []
    old_to_new: dict[int, int] = {}
    for old_idx, opt in enumerate(options):
        key = re.sub(r"\s+", " ", (opt or "").strip()).lower()
        if not key:
            continue
        if key in seen:
            old_to_new[old_idx] = seen[key]
            continue
        new_idx = len(new_options)
        seen[key] = new_idx
        new_options.append(opt)
        old_to_new[old_idx] = new_idx

    if len(new_options) == len(options):
        return options, correct_option_index

    new_correct = correct_option_index
    if correct_option_index is not None and 0 <= correct_option_index < len(options):
        new_correct = old_to_new.get(correct_option_index)
    return new_options, new_correct


def _patch_directive_captions(
    base: str,
    figure_captions: dict[str, str],
    table_captions: dict[str, str],
) -> str:
    """Rewrite `[Figure N]` / `[Table N]` to include captions when available.

    Only patches labels with no existing caption. Idempotent.
    """
    if not base:
        return base

    def repl(m: re.Match[str]) -> str:
        prefix, kind, ref, suffix = m.group(1), m.group(2), m.group(3), m.group(4)
        ref_lower = ref.lower()
        captions = figure_captions if kind.lower() == "figure" else table_captions
        caption = captions.get(ref_lower)
        if not caption:
            return m.group(0)
        return f"{prefix}{kind} {ref} — {caption}{suffix}"

    return _DIRECTIVE_LABEL_RE.sub(repl, base)


def _extract_table_blocks(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    tables: dict[str, str] = {}
    i = 0
    while i + 1 < len(lines):
        line = lines[i]
        if "|" not in line or not _TABLE_SEPARATOR_RE.match(lines[i + 1].strip()):
            i += 1
            continue

        end = i + 2
        while end < len(lines) and "|" in lines[end]:
            end += 1
        block = "\n".join(lines[i:end]).strip()
        table_ref = _extract_nearby_reference(lines, i, _TABLE_REF_RE)
        if table_ref and table_ref not in tables:
            tables[table_ref] = block
        i = end
    return tables


def _extract_image_blocks(
    markdown: str, image_url_by_path: dict[str, str]
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """Extract image references and captions for 'Table X' / 'Figure X' labels.

    Returns:
        (table_images, figure_images, table_captions, figure_captions)
        - *_images map ref id → markdown img tag with the serving URL
        - *_captions map ref id → caption text (first occurrence wins)

    Matches every label to its nearest image in the entire document.
    """
    lines = markdown.splitlines()
    table_images: dict[str, str] = {}
    figure_images: dict[str, str] = {}
    table_captions: dict[str, str] = {}
    figure_captions: dict[str, str] = {}

    # Captions first — independent of images, paper convention is to caption
    # on first appearance.
    for match in _CAPTION_RE.finditer(markdown):
        kind = match.group(1).lower()
        ref = match.group(2).lower()
        caption = match.group(3).strip()
        if not caption:
            continue
        target = figure_captions if kind == "figure" else table_captions
        target.setdefault(ref, caption)

    # Collect all images with their line positions (only real images with S3 URLs)
    all_images: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        for match in _IMG_REF_RE.finditer(line):
            alt = match.group(1).strip()
            src = match.group(2).strip()
            # Only include images that were actually uploaded to S3
            if src not in image_url_by_path:
                continue
            render_src = image_url_by_path[src]
            all_images.append((idx, f"![{alt}]({render_src})"))

    if not all_images:
        return table_images, figure_images, table_captions, figure_captions

    # Collect all Table/Figure labels with their line positions
    labels: list[tuple[int, str, str]] = []  # (line_idx, ref, "table"|"figure")
    for idx, line in enumerate(lines):
        for match in _TABLE_REF_RE.finditer(line):
            labels.append((idx, match.group(1).lower(), "table"))
        for match in _FIGURE_REF_RE.finditer(line):
            labels.append((idx, match.group(1).lower(), "figure"))

    # Match each label to its nearest image (global, not limited by range)
    for label_idx, ref, kind in labels:
        target = table_images if kind == "table" else figure_images
        if ref in target:
            continue
        # Find the closest image by line distance
        best_img = None
        best_dist = float("inf")
        for img_idx, img_tag in all_images:
            dist = abs(img_idx - label_idx)
            if dist < best_dist:
                best_dist = dist
                best_img = img_tag
        if best_img:
            target[ref] = best_img

    return table_images, figure_images, table_captions, figure_captions


def _replace_image_paths_with_urls(
    text: str, image_url_by_path: dict[str, str]
) -> str:
    rendered = text
    for path, url in image_url_by_path.items():
        rendered = rendered.replace(f"({path})", f"({url})")
    return rendered


def _build_enriched_context(
    question_text: str,
    context: str | None,
    table_blocks: dict[str, str],
    table_images: dict[str, str],
    figure_images: dict[str, str],
    image_url_by_path: dict[str, str],
    table_captions: dict[str, str] | None = None,
    figure_captions: dict[str, str] | None = None,
) -> str | None:
    table_captions = table_captions or {}
    figure_captions = figure_captions or {}

    base = context.strip() if isinstance(context, str) else ""
    if base:
        base = _replace_image_paths_with_urls(base, image_url_by_path)
        base = _patch_directive_captions(base, figure_captions, table_captions)
        base = _normalize_orphan_figures(base, figure_captions, table_captions)

    llm_fig_refs, llm_tab_refs = _directive_refs(base)

    combined = f"{question_text}\n{base}".strip()
    table_refs = _extract_reference_ids(combined, _TABLE_REF_RE)
    figure_refs = _extract_reference_ids(combined, _FIGURE_REF_RE)

    parts: list[str] = []
    if base:
        parts.append(base)

    for ref in table_refs:
        if ref in llm_tab_refs:
            continue
        content = table_blocks.get(ref) or table_images.get(ref)
        if not content:
            continue
        caption = table_captions.get(ref)
        label = f"Table {ref} — {caption}" if caption else f"Table {ref}"
        part = f"::: figure [{label}]\n{content}\n:::"
        if part not in parts:
            parts.append(part)

    for ref in figure_refs:
        if ref in llm_fig_refs:
            continue
        content = figure_images.get(ref)
        if not content:
            continue
        caption = figure_captions.get(ref)
        label = f"Figure {ref} — {caption}" if caption else f"Figure {ref}"
        part = f"::: figure [{label}]\n{content}\n:::"
        if part not in parts:
            parts.append(part)

    if parts:
        return "\n\n".join(parts)
    return None


def _enrich_question_contexts(
    questions: list[ParsedQuestion],
    markdown: str,
    image_url_by_path: dict[str, str],
) -> None:
    table_blocks = _extract_table_blocks(markdown)
    (
        table_images,
        figure_images,
        table_captions,
        figure_captions,
    ) = _extract_image_blocks(markdown, image_url_by_path)
    for question in questions:
        question.context = _build_enriched_context(
            question_text=question.question,
            context=question.context,
            table_blocks=table_blocks,
            table_images=table_images,
            figure_images=figure_images,
            image_url_by_path=image_url_by_path,
            table_captions=table_captions,
            figure_captions=figure_captions,
        )
        question.context = _strip_source_citations(question.context)
        question.context = _close_unclosed_directives(question.context)
        question.context = _normalize_directive_titles(question.context)
        question.question = _dedupe_question_against_context(
            question.question, question.context
        )
        if question.type == "mcq":
            question.options, question.correct_option_index = _dedupe_mcq_options(
                question.options, question.correct_option_index
            )
            question.context = _strip_mcq_options_from_context(
                question.context, question.options
            )


def _compute_item_id(template_id: uuid.UUID, question_text: str) -> str:
    """Stable 16-char hash for deduplication — scoped to this template."""
    import re

    normalized = re.sub(r"\s+", " ", question_text.strip().lower())
    raw = f"{template_id}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_question_rows(
    template_id: uuid.UUID,
    parsed: list[ParsedQuestion],
) -> list[TestQuestion]:
    return [
        TestQuestion(
            template_id=template_id,
            index=idx,
            item_id=_compute_item_id(template_id, q.question),
            type=q.type,
            question=q.question,
            model_answer=q.model_answer,
            mark_scheme=q.mark_scheme,
            context=q.context,
            options=q.options or None,
            correct_option_index=q.correct_option_index,
            hint=q.hint,
            points=q.points,
            question_number=q.question_number,
            is_unsupported=q.is_unsupported,
        )
        for idx, q in enumerate(parsed)
    ]


# ---------------------------------------------------------------------------
# Streaming upload pipeline
# ---------------------------------------------------------------------------


async def _set_processing_phase(
    session_factory: async_sessionmaker[AsyncSession],
    template_id: uuid.UUID,
    phase: str | None,
) -> None:
    """Write processing_phase to DB. Best-effort — never raises."""
    try:
        async with session_factory() as db:
            tpl = await db.get(TestTemplate, template_id)
            if tpl:
                tpl.processing_phase = phase
                await db.commit()
    except Exception:
        logger.warning(
            "Failed to persist processing_phase=%s for template_id=%s",
            phase,
            template_id,
            exc_info=True,
        )


async def upload_and_process_streaming(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    pdf_bytes: bytes,
    name: str,
    original_filename: str,
    folder_id: uuid.UUID,
    mark_scheme_bytes: bytes | None = None,
    mark_scheme_filename: str | None = None,
    usage_service: object | None = None,
    s3: "S3Client | None" = None,
    prompt_manager: PromptManager | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Same pipeline as upload_and_process but yields SSE-ready dicts:
      {"event": "processing", "phase": "ocr" | "mark_scheme_parsing" | "parsing" | "matching", "message": str}
      {"event": "mark_scheme_failed", "matched_questions": 0, "total_short_questions": int, "message": str}
      {"event": "complete", "paper_id": str, "total_questions": int, "name": str}
      {"event": "error", "message": str}
    """
    mark_scheme_sha256 = (
        _compute_pdf_sha256(mark_scheme_bytes) if mark_scheme_bytes else None
    )
    pdf_sha256 = _compute_pdf_sha256(pdf_bytes)
    cached = await _find_cached_past_paper(
        session_factory=session_factory,
        pdf_sha256=pdf_sha256,
    )
    if cached is not None:
        logger.info(
            "Past paper cache hit user_id=%s folder_id=%s paper_id=%s",
            user_id,
            folder_id,
            cached.id,
        )
        cloned = await _clone_cached_past_paper(
            session_factory=session_factory,
            cached=cached,
            user_id=user_id,
            folder_id=folder_id,
            name=name,
            original_filename=original_filename,
            pdf_bytes=pdf_bytes,
            pdf_sha256=pdf_sha256,
            mark_scheme_bytes=mark_scheme_bytes,
            mark_scheme_sha256=mark_scheme_sha256,
            mark_scheme_filename=mark_scheme_filename,
            s3=s3,
        )
        total_marks = cloned.total_marks or sum((q.points or 1) for q in cloned.questions)
        yield {
            "event": "started",
            "paper_id": str(cloned.id),
            "cached": True,
        }
        yield {
            "event": "complete",
            "paper_id": str(cloned.id),
            "total_questions": len(cloned.questions),
            "total_marks": total_marks,
            "name": cloned.name,
            "cached": True,
        }
        return

    settings = get_settings()
    ocr = PastPaperOCR(settings.mistral)
    llm = YandexGPTLLMGateway()
    _usage_svc = usage_service
    parser = PastPaperParser(llm, usage_service=_usage_svc, prompt_manager=prompt_manager)
    parser._current_user_id = user_id
    matcher = RoadmapNodeMatcher(llm, usage_service=_usage_svc, prompt_manager=prompt_manager)
    matcher._current_user_id = user_id

    template_id = uuid.uuid4()
    _t_start = time.perf_counter()

    # ── Step 0: save template as "processing", fetch roadmap nodes ──────────
    _t0 = time.perf_counter()
    async with session_factory() as db:
        nodes_result = await db.execute(
            select(
                RoadmapNode.id,
                RoadmapNode.level,
                RoadmapNode.name,
                RoadmapNode.position,
                RoadmapNode.parent_id,
            )
            .where(RoadmapNode.folder_id == folder_id)
            .order_by(RoadmapNode.level, RoadmapNode.position)
        )
        roadmap_nodes = [
            NodeInfo(
                id=row.id,
                level=row.level,
                name=row.name,
                position=row.position,
                parent_id=row.parent_id,
            )
            for row in nodes_result.all()
        ]

        db.add(
            TestTemplate(
                id=template_id,
                user_id=user_id,
                folder_id=folder_id,
                name=name,
                type="past_paper",
                status="processing",
                original_filename=original_filename,
                mark_scheme_filename=mark_scheme_filename,
                source_pdf_sha256=pdf_sha256,
                mark_scheme_sha256=mark_scheme_sha256,
                generation_progress=None,
                total_questions=0,
            )
        )
        await db.commit()
    logger.info("past_paper step=init template_id=%s elapsed=%.2fs", template_id, time.perf_counter() - _t0)

    yield {
        "event": "started",
        "paper_id": str(template_id),
    }

    # ── Phase 1: OCR ─────────────────────────────────────────────────────────
    await _set_processing_phase(session_factory, template_id, "ocr")
    yield {"event": "processing", "phase": "ocr", "message": "Extracting text from PDF"}
    image_url_by_path: dict[str, str] = {}
    mark_scheme_markdown: str | None = None
    _t1 = time.perf_counter()
    try:
        _t_ocr_paper = time.perf_counter()
        markdown, images_dict, tables_dict = await ocr.pdf_to_markdown_with_images(pdf_bytes)
        logger.info("past_paper step=ocr_paper template_id=%s chars=%d images=%d elapsed=%.2fs", template_id, len(markdown), len(images_dict), time.perf_counter() - _t_ocr_paper)
        if s3 and images_dict:
            _t_img_upload = time.perf_counter()
            path_map = await _upload_images_to_s3(s3, template_id, images_dict)
            logger.info("past_paper step=upload_images template_id=%s count=%d elapsed=%.2fs", template_id, len(images_dict), time.perf_counter() - _t_img_upload)
        else:
            path_map = {img_id: f"uploads/images/{img_id}.png" for img_id in images_dict}
        markdown = _replace_image_refs(markdown, path_map)
        image_url_by_path = _build_image_url_map(template_id, path_map)

        if mark_scheme_bytes:
            yield {
                "event": "processing",
                "phase": "mark_scheme_parsing",
                "message": "Parsing mark scheme",
            }
            _t_ocr_ms = time.perf_counter()
            ms_text, _, _ = await ocr.pdf_to_markdown_with_images(mark_scheme_bytes)
            logger.info("past_paper step=ocr_mark_scheme template_id=%s chars=%d elapsed=%.2fs", template_id, len(ms_text), time.perf_counter() - _t_ocr_ms)
            mark_scheme_markdown = ms_text.strip() or None
            if not mark_scheme_markdown:
                logger.warning(
                    "Mark scheme OCR returned empty content for template_id=%s",
                    template_id,
                )

        if s3:
            _t_s3_assets = time.perf_counter()
            await _save_ocr_assets_to_s3(
                s3, template_id,
                pdf_bytes=pdf_bytes,
                markdown=markdown,
                images_dict=images_dict,
                tables_dict=tables_dict,
                mark_scheme_bytes=mark_scheme_bytes,
                mark_scheme_markdown=mark_scheme_markdown,
            )
            logger.info("past_paper step=save_ocr_assets template_id=%s elapsed=%.2fs", template_id, time.perf_counter() - _t_s3_assets)
    except Exception as exc:
        logger.error("OCR failed template_id=%s: %s", template_id, exc, exc_info=True)
        async with session_factory() as db:
            tpl = await db.get(TestTemplate, template_id)
            if tpl:
                tpl.status = "failed"
                tpl.processing_phase = None
                await db.commit()
        yield {"event": "error", "message": f"OCR failed: {exc}"}
        return

    logger.info("past_paper step=ocr_phase template_id=%s elapsed=%.2fs", template_id, time.perf_counter() - _t1)

    # ── Phase 2: Parse questions ──────────────────────────────────────────────
    await _set_processing_phase(session_factory, template_id, "parsing")
    yield {"event": "processing", "phase": "parsing", "message": "Parsing questions"}
    _t2 = time.perf_counter()
    try:
        _t_parse = time.perf_counter()
        parsed_questions = await parser.parse(markdown, mark_scheme_markdown)
        logger.info("past_paper step=llm_parse template_id=%s questions=%d elapsed=%.2fs", template_id, len(parsed_questions), time.perf_counter() - _t_parse)
        _t_enrich = time.perf_counter()
        _enrich_question_contexts(parsed_questions, markdown, image_url_by_path)
        logger.info("past_paper step=enrich_contexts template_id=%s elapsed=%.2fs", template_id, time.perf_counter() - _t_enrich)
        applied_ms, total_short = _sanitize_mark_schemes_on_parsed_questions(
            parsed_questions
        )
        if mark_scheme_markdown and total_short > 0 and applied_ms == 0:
            yield {
                "event": "processing",
                "phase": "mark_scheme_matching",
                "message": "Matching mark scheme to parsed questions",
            }
            try:
                _t_ms_fallback = time.perf_counter()
                applied_ms, total_short = await _fallback_assign_mark_schemes(
                    parser,
                    parsed_questions,
                    mark_scheme_markdown,
                )
                logger.info("past_paper step=ms_fallback_match template_id=%s applied=%d total_short=%d elapsed=%.2fs", template_id, applied_ms, total_short, time.perf_counter() - _t_ms_fallback)
            except Exception as fallback_exc:
                logger.warning(
                    "Streaming mark scheme fallback matching failed for template_id=%s: %s",
                    template_id,
                    fallback_exc,
                    exc_info=True,
                )
        if mark_scheme_markdown:
            logger.info(
                "Applied mark scheme answers: %d out of %d short-answer questions "
                "(total questions=%d) for template_id=%s",
                applied_ms,
                total_short,
                len(parsed_questions),
                template_id,
            )
            if applied_ms == 0:
                logger.info(
                    "No mark scheme entries matched for template_id=%s; "
                    "mark schemes were cleared automatically",
                    template_id,
                )
        if mark_scheme_bytes and applied_ms == 0:
            yield {
                "event": "mark_scheme_unassigned",
                "matched_questions": 0,
                "total_short_questions": total_short,
                "total_questions": len(parsed_questions),
                "message": "No questions were assigned mark scheme entries",
            }
        if mark_scheme_bytes and total_short > 0 and applied_ms == 0:
            yield {
                "event": "mark_scheme_failed",
                "matched_questions": 0,
                "total_short_questions": total_short,
                "message": "Mark scheme matched 0 short-answer questions",
            }
    except Exception as exc:
        logger.error(
            "Parsing failed template_id=%s: %s", template_id, exc, exc_info=True
        )
        async with session_factory() as db:
            tpl = await db.get(TestTemplate, template_id)
            if tpl:
                tpl.status = "failed"
                tpl.processing_phase = None
                await db.commit()
        yield {"event": "error", "message": f"Parsing failed: {exc}"}
        return

    logger.info("past_paper step=parse_phase template_id=%s elapsed=%.2fs", template_id, time.perf_counter() - _t2)

    # ── Phase 3: Node matching ────────────────────────────────────────────────
    await _set_processing_phase(session_factory, template_id, "matching")
    yield {
        "event": "processing",
        "phase": "matching",
        "message": "Matching questions to roadmap nodes",
    }
    _t3 = time.perf_counter()
    node_mapping: dict[int, list[uuid.UUID]] = {}
    try:
        node_mapping = await matcher.match(roadmap_nodes, parsed_questions)
    except Exception as match_exc:
        logger.error(
            "Node matching failed for folder_id=%s (non-fatal): %s",
            folder_id,
            match_exc,
            exc_info=True,
        )
    logger.info("past_paper step=node_matching template_id=%s matched=%d elapsed=%.2fs", template_id, len(node_mapping), time.perf_counter() - _t3)

    # ── Persist ───────────────────────────────────────────────────────────────
    _t4 = time.perf_counter()
    try:
        question_rows = _build_question_rows(template_id, parsed_questions)
        for row in question_rows:
            matched = node_mapping.get(row.index)
            row.node_ids = matched if matched else None

        total_marks = sum(q.points or 1 for q in question_rows)

        async with session_factory() as db:
            tpl = await db.get(TestTemplate, template_id)
            if tpl:
                tpl.status = "ready"
                tpl.processing_phase = None
                tpl.total_questions = len(question_rows)
                tpl.total_marks = total_marks
                tpl.mark_scheme = _template_mark_scheme_value(
                    mark_scheme_markdown,
                    applied_ms,
                )
                tpl.ocr_markdown = markdown
                if mark_scheme_filename:
                    tpl.mark_scheme_filename = mark_scheme_filename
            db.add_all(question_rows)
            await db.commit()
    except Exception as exc:
        logger.error(
            "Persist failed template_id=%s: %s", template_id, exc, exc_info=True
        )
        async with session_factory() as db:
            tpl = await db.get(TestTemplate, template_id)
            if tpl:
                tpl.status = "failed"
                tpl.processing_phase = None
                await db.commit()
        yield {"event": "error", "message": f"Failed to save past paper: {exc}"}
        return

    _t_total = time.perf_counter() - _t_start
    logger.info(
        "past_paper step=persist template_id=%s questions=%d elapsed=%.2fs",
        template_id, len(question_rows), time.perf_counter() - _t4,
    )
    logger.info(
        "past_paper summary template_id=%s questions=%d marks=%d total=%.2fs "
        "init=%.2fs ocr=%.2fs parse=%.2fs matching=%.2fs persist=%.2fs",
        template_id,
        len(question_rows),
        total_marks,
        _t_total,
        _t1 - _t_start,
        _t2 - _t1,
        _t3 - _t2,
        _t4 - _t3,
        time.perf_counter() - _t4,
    )

    yield {
        "event": "complete",
        "paper_id": str(template_id),
        "total_questions": len(question_rows),
        "total_marks": total_marks,
        "name": name,
    }


# ---------------------------------------------------------------------------
# Mark-scheme background jobs
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _job_payload(job: MarkSchemeUploadJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "past_paper_id": job.past_paper_id,
        "status": job.status,
        "phase": job.phase,
        "message": job.message,
        "matched_questions": job.matched_questions,
        "total_short_questions": job.total_short_questions,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }


def _job_done(status: str) -> bool:
    return status in {"completed", "failed"}


async def _cleanup_mark_scheme_upload_jobs_locked() -> None:
    now = _utcnow()
    cutoff = now - _MARK_SCHEME_JOB_RETENTION
    stale_job_ids = [
        job_id
        for job_id, job in _MARK_SCHEME_UPLOAD_JOBS.items()
        if _job_done(job.status)
        and job.completed_at is not None
        and job.completed_at < cutoff
    ]
    for job_id in stale_job_ids:
        _MARK_SCHEME_UPLOAD_JOBS.pop(job_id, None)
        task = _MARK_SCHEME_UPLOAD_TASKS.pop(job_id, None)
        if task and not task.done():
            task.cancel()

    done_task_ids = [
        job_id
        for job_id, task in _MARK_SCHEME_UPLOAD_TASKS.items()
        if task.done()
    ]
    for job_id in done_task_ids:
        _MARK_SCHEME_UPLOAD_TASKS.pop(job_id, None)


def _assert_job_access(
    job: MarkSchemeUploadJob | None,
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
) -> MarkSchemeUploadJob:
    if job is None or job.user_id != user_id or job.past_paper_id != past_paper_id:
        raise PastPaperError("Mark scheme job not found or access denied")
    return job


async def _record_mark_scheme_upload_event(
    job_id: uuid.UUID,
    event: dict[str, Any],
) -> None:
    now = _utcnow()
    async with _MARK_SCHEME_UPLOAD_LOCK:
        job = _MARK_SCHEME_UPLOAD_JOBS.get(job_id)
        if job is None:
            return

        payload = dict(event)
        payload.setdefault("timestamp", now.isoformat())
        job.events.append(payload)
        job.updated_at = now

        event_type = payload.get("event")
        if event_type == "processing":
            job.status = "processing"
            job.phase = payload.get("phase")
            job.message = payload.get("message")
            job.error = None
        elif event_type == "mark_scheme_failed":
            job.phase = "mark_scheme_matching"
            job.message = payload.get("message")
            job.matched_questions = payload.get("matched_questions", 0)
            job.total_short_questions = payload.get("total_short_questions")
        elif event_type == "complete":
            job.status = "completed"
            job.phase = "complete"
            job.message = payload.get("message")
            job.matched_questions = payload.get("matched_questions")
            job.total_short_questions = payload.get("total_short_questions")
            job.completed_at = now
        elif event_type == "error":
            job.status = "failed"
            job.phase = "error"
            job.message = payload.get("message")
            job.error = payload.get("message")
            job.completed_at = now


async def _run_mark_scheme_upload_job(
    job_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    mark_scheme_bytes: bytes,
    usage_service: object | None = None,
    prompt_manager: PromptManager | None = None,
) -> None:
    async def emit(event: dict[str, Any]) -> None:
        await _record_mark_scheme_upload_event(job_id, event)

    try:
        await _upload_mark_scheme_core(
            session_factory=session_factory,
            user_id=user_id,
            past_paper_id=past_paper_id,
            mark_scheme_bytes=mark_scheme_bytes,
            usage_service=usage_service,
            event_emitter=emit,
            prompt_manager=prompt_manager,
        )
    except Exception as exc:
        await _record_mark_scheme_upload_event(
            job_id,
            {"event": "error", "message": str(exc)},
        )
    finally:
        async with _MARK_SCHEME_UPLOAD_LOCK:
            _MARK_SCHEME_UPLOAD_TASKS.pop(job_id, None)


async def start_mark_scheme_upload_job(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    mark_scheme_bytes: bytes,
    usage_service: object | None = None,
    prompt_manager: PromptManager | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    job = MarkSchemeUploadJob(
        id=uuid.uuid4(),
        user_id=user_id,
        past_paper_id=past_paper_id,
        status="queued",
        phase="queued",
        message="Job queued",
        matched_questions=None,
        total_short_questions=None,
        error=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    async with _MARK_SCHEME_UPLOAD_LOCK:
        await _cleanup_mark_scheme_upload_jobs_locked()
        _MARK_SCHEME_UPLOAD_JOBS[job.id] = job

    task = asyncio.create_task(
        _run_mark_scheme_upload_job(
            job_id=job.id,
            session_factory=session_factory,
            user_id=user_id,
            past_paper_id=past_paper_id,
            mark_scheme_bytes=mark_scheme_bytes,
            usage_service=usage_service,
            prompt_manager=prompt_manager,
        ),
        name=f"mark-scheme-job-{job.id}",
    )
    async with _MARK_SCHEME_UPLOAD_LOCK:
        _MARK_SCHEME_UPLOAD_TASKS[job.id] = task
    return _job_payload(job)


async def get_mark_scheme_upload_job(
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    job_id: uuid.UUID,
) -> dict[str, Any]:
    async with _MARK_SCHEME_UPLOAD_LOCK:
        await _cleanup_mark_scheme_upload_jobs_locked()
        job = _assert_job_access(
            _MARK_SCHEME_UPLOAD_JOBS.get(job_id),
            user_id,
            past_paper_id,
        )
        return _job_payload(job)


async def stream_mark_scheme_upload_job(
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    interval_seconds: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    cursor = 0
    while True:
        async with _MARK_SCHEME_UPLOAD_LOCK:
            job = _assert_job_access(
                _MARK_SCHEME_UPLOAD_JOBS.get(job_id),
                user_id,
                past_paper_id,
            )
            total_events = len(job.events)
            pending = [dict(e) for e in job.events[cursor:]]
            status = job.status

        if pending:
            for event in pending:
                cursor += 1
                yield event
        else:
            yield {"event": "heartbeat", "status": status}

        if _job_done(status) and cursor >= total_events:
            return
        await asyncio.sleep(interval_seconds)


def _clear_mark_scheme_upload_jobs_for_tests() -> None:
    for task in _MARK_SCHEME_UPLOAD_TASKS.values():
        if not task.done():
            task.cancel()
    _MARK_SCHEME_UPLOAD_TASKS.clear()
    _MARK_SCHEME_UPLOAD_JOBS.clear()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def list_past_papers(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
) -> list[TestTemplate]:
    stmt = (
        select(TestTemplate)
        .where(
            TestTemplate.user_id == user_id,
            TestTemplate.type == "past_paper",
        )
        .options(selectinload(TestTemplate.questions))
        .order_by(TestTemplate.created_at.desc())
    )
    if folder_id is not None:
        stmt = stmt.where(TestTemplate.folder_id == folder_id)
    result = await db.scalars(stmt)
    return list(result)


async def get_past_paper(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    past_paper_id: uuid.UUID,
) -> TestTemplate | None:
    user_filter = (
        TestTemplate.user_id.is_(None)
        if user_id is None
        else TestTemplate.user_id == user_id
    )
    result = await db.execute(
        select(TestTemplate)
        .where(
            TestTemplate.id == past_paper_id,
            user_filter,
            TestTemplate.type == "past_paper",
        )
        .options(selectinload(TestTemplate.questions))
    )
    return result.scalar_one_or_none()


MarkSchemeEventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


async def _emit_mark_scheme_event(
    event_emitter: MarkSchemeEventEmitter | None,
    event: dict[str, Any],
) -> None:
    if event_emitter is None:
        return
    maybe_awaitable = event_emitter(event)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


async def _upload_mark_scheme_core(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    mark_scheme_bytes: bytes,
    mark_scheme_filename: str | None = None,
    usage_service: object | None = None,
    event_emitter: MarkSchemeEventEmitter | None = None,
    s3: "S3Client | None" = None,
    prompt_manager: PromptManager | None = None,
) -> TestTemplate:
    await _emit_mark_scheme_event(
        event_emitter,
        {
            "event": "processing",
            "phase": "validating",
            "message": "Validating past paper",
        },
    )

    # ── Phase 1: load + validate, then release the connection ─────────────────
    async with session_factory() as db:
        paper = await get_past_paper(db, user_id, past_paper_id)
        if paper is None:
            raise PastPaperError("Past paper not found or access denied")
        if paper.status != "ready":
            raise PastPaperError(
                f"Past paper is not ready (status={paper.status}). "
                "Wait until processing completes before uploading a mark scheme."
            )
        if not paper.questions:
            raise PastPaperError(
                "Past paper has no questions to attach a mark scheme to."
            )
        questions_snapshot = list(paper.questions)
        question_ids_by_index = {q.index: q.id for q in questions_snapshot}
        stored_ocr_markdown: str | None = paper.ocr_markdown

    settings = get_settings()
    ocr = PastPaperOCR(settings.mistral)
    llm = YandexGPTLLMGateway()
    parser = PastPaperParser(llm, usage_service=usage_service, prompt_manager=prompt_manager)
    parser._current_user_id = user_id

    await _emit_mark_scheme_event(
        event_emitter,
        {
            "event": "processing",
            "phase": "mark_scheme_parsing",
            "message": "Parsing mark scheme",
        },
    )
    try:
        mark_scheme_markdown, _, _ = await ocr.pdf_to_markdown_with_images(
            mark_scheme_bytes
        )
        mark_scheme_markdown = mark_scheme_markdown.strip()
        if not mark_scheme_markdown:
            raise PastPaperError("Uploaded mark scheme produced empty OCR output")
    except PastPaperError:
        raise
    except Exception as exc:
        raise PastPaperError(f"Mark scheme processing failed: {exc}") from exc

    await _emit_mark_scheme_event(
        event_emitter,
        {
            "event": "processing",
            "phase": "mark_scheme_matching",
            "message": "Matching mark scheme to questions",
        },
    )

    # Use the SAME code path as the combined upload: re-run parser.parse()
    # with the original OCR markdown + mark scheme. This is the most reliable
    # approach because the LLM sees original question numbering (01, 02.1, …)
    # and can match directly to mark scheme entries.
    sorted_qs = sorted(questions_snapshot, key=lambda q: q.index)
    total_short = sum(1 for q in sorted_qs if q.type == "short")
    applied_ms = 0
    updates: dict[int, str | None] = {q.index: None for q in sorted_qs}

    if stored_ocr_markdown:
        try:
            re_parsed = await parser.parse(stored_ocr_markdown, mark_scheme_markdown)
            _sanitize_mark_schemes_on_parsed_questions(re_parsed)

            # Map re-parsed questions back to stored questions by index position.
            for i, pq in enumerate(re_parsed):
                if i >= len(sorted_qs):
                    break
                stored_q = sorted_qs[i]
                if stored_q.type != "short":
                    continue
                normalized = _normalize_mark_scheme_text(pq.mark_scheme)
                updates[stored_q.index] = normalized
                if normalized:
                    applied_ms += 1

            # Fallback within re-parse: if initial parse got 0, try assign
            if total_short > 0 and applied_ms == 0:
                logger.info(
                    "Re-parse with stored OCR matched 0 for past_paper_id=%s; "
                    "trying fallback assign_mark_schemes",
                    past_paper_id,
                )
                parsed_as_assignment = [
                    _AssignmentQuestion(
                        index=i, question=pq.question,
                        type=pq.type, model_answer=pq.model_answer,
                    )
                    for i, pq in enumerate(re_parsed)
                ]
                assignment = await parser.assign_mark_schemes(
                    parsed_as_assignment, mark_scheme_markdown,
                )
                a_updates, applied_ms, _ = _prepare_mark_scheme_assignment(
                    parsed_as_assignment, assignment,
                )
                # Map assignment results back to stored question indexes
                for a_idx, ms_text in a_updates.items():
                    if a_idx < len(sorted_qs):
                        stored_q = sorted_qs[a_idx]
                        if stored_q.type == "short":
                            updates[stored_q.index] = ms_text
        except Exception as exc:
            logger.warning(
                "Re-parse with stored OCR failed for past_paper_id=%s: %s",
                past_paper_id, exc, exc_info=True,
            )
    else:
        # No stored OCR markdown (old papers uploaded before this feature).
        # Fall back to content-based matching via reparse_with_mark_scheme.
        logger.info(
            "No stored OCR markdown for past_paper_id=%s; "
            "falling back to content-based matching",
            past_paper_id,
        )
        try:
            entries = await parser.reparse_with_mark_scheme(
                questions_snapshot, mark_scheme_markdown
            )
            for pos, q in enumerate(sorted_qs):
                if q.type != "short":
                    continue
                raw_entry = entries[pos] if pos < len(entries) else None
                normalized = _normalize_mark_scheme_text(raw_entry)
                updates[q.index] = normalized
                if normalized:
                    applied_ms += 1
        except Exception as exc:
            logger.warning(
                "reparse_with_mark_scheme failed for past_paper_id=%s: %s",
                past_paper_id, exc, exc_info=True,
            )

    logger.info(
        "Applied mark scheme answers: %d out of %d short-answer questions "
        "(total questions=%d) for past_paper_id=%s",
        applied_ms, total_short, len(questions_snapshot), past_paper_id,
    )
    if total_short > 0 and applied_ms == 0:
        await _emit_mark_scheme_event(
            event_emitter,
            {
                "event": "mark_scheme_failed",
                "matched_questions": 0,
                "total_short_questions": total_short,
                "message": "Mark scheme matched 0 short-answer questions",
            },
        )

    await _emit_mark_scheme_event(
        event_emitter,
        {
            "event": "processing",
            "phase": "persisting",
            "message": "Saving mark scheme",
        },
    )
    # Upload mark scheme PDF + markdown to S3
    if s3:
        prefix = f"past-papers/{past_paper_id}"
        await s3.upload_bytes(
            f"{prefix}/origin/mark-scheme.pdf",
            mark_scheme_bytes,
            content_type="application/pdf",
        )
        if mark_scheme_markdown:
            await s3.upload_bytes(
                f"{prefix}/origin_md/mark-scheme.md",
                mark_scheme_markdown.encode("utf-8"),
                content_type="text/markdown",
            )

    async with session_factory() as db:
        tpl = await db.get(TestTemplate, past_paper_id)
        if tpl:
            tpl.mark_scheme = _template_mark_scheme_value(
                mark_scheme_markdown,
                applied_ms,
            )
            if applied_ms > 0 and mark_scheme_filename:
                tpl.mark_scheme_filename = mark_scheme_filename
            elif applied_ms == 0:
                tpl.mark_scheme_filename = None
        for idx, ms_text in updates.items():
            q_id = question_ids_by_index.get(idx)
            if q_id is None:
                continue
            q = await db.get(TestQuestion, q_id)
            if q:
                q.mark_scheme = ms_text
        await db.commit()

        result = await db.execute(
            select(TestTemplate)
            .where(TestTemplate.id == past_paper_id)
            .options(selectinload(TestTemplate.questions))
        )
        paper = result.scalar_one()

    await _emit_mark_scheme_event(
        event_emitter,
        {
            "event": "complete",
            "past_paper_id": str(past_paper_id),
            "matched_questions": applied_ms,
            "total_short_questions": total_short,
            "message": "Mark scheme upload completed",
        },
    )
    return paper


async def upload_mark_scheme(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    mark_scheme_bytes: bytes,
    mark_scheme_filename: str | None = None,
    usage_service: object | None = None,
    s3: "S3Client | None" = None,
    prompt_manager: PromptManager | None = None,
) -> tuple[TestTemplate, int, int]:
    """Returns (paper, applied_ms, total_short)."""
    paper = await _upload_mark_scheme_core(
        session_factory=session_factory,
        user_id=user_id,
        past_paper_id=past_paper_id,
        mark_scheme_bytes=mark_scheme_bytes,
        mark_scheme_filename=mark_scheme_filename,
        usage_service=usage_service,
        event_emitter=None,
        s3=s3,
        prompt_manager=prompt_manager,
    )
    # Re-derive counts from persisted questions so we don't need to thread
    # internal state through _upload_mark_scheme_core's return value.
    total_short = sum(1 for q in paper.questions if q.type == "short")
    applied_ms = sum(1 for q in paper.questions if q.type == "short" and q.mark_scheme)
    return paper, applied_ms, total_short


async def delete_mark_scheme(
    db: AsyncSession,
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
) -> TestTemplate:
    """Set mark_scheme to NULL on all questions for this past paper."""
    paper = await get_past_paper(db, user_id, past_paper_id)
    if paper is None:
        raise PastPaperError("Past paper not found or access denied")
    paper.mark_scheme = None
    paper.mark_scheme_filename = None
    for question in paper.questions:
        question.mark_scheme = None
    await db.commit()
    result = await db.execute(
        select(TestTemplate)
        .where(TestTemplate.id == past_paper_id)
        .options(selectinload(TestTemplate.questions))
    )
    return result.scalar_one()


async def rename_past_paper(
    db: AsyncSession,
    user_id: uuid.UUID,
    past_paper_id: uuid.UUID,
    name: str,
) -> TestTemplate:
    """Rename a past paper."""
    paper = await get_past_paper(db, user_id, past_paper_id)
    if paper is None:
        raise PastPaperError("Past paper not found or access denied")
    if not name:
        raise PastPaperError("Name cannot be empty")
    paper.name = name
    await db.commit()
    await db.refresh(paper)
    return paper


async def delete_past_paper(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    past_paper_id: uuid.UUID,
    s3: "S3Client | None" = None,
) -> None:
    user_filter = (
        TestTemplate.user_id.is_(None)
        if user_id is None
        else TestTemplate.user_id == user_id
    )
    result = await db.execute(
        select(TestTemplate.id).where(
            TestTemplate.id == past_paper_id,
            user_filter,
            TestTemplate.type == "past_paper",
        )
    )
    template_id = result.scalar_one_or_none()
    if template_id is None:
        raise PastPaperError("Past paper not found or access denied")

    # Clean up ALL S3 objects under the template prefix
    if s3:
        s3_keys: list[str] = []
        full_prefix = f"past-papers/{template_id}/"
        try:
            resp = await s3._client.list_objects_v2(
                Bucket=s3._settings.bucket, Prefix=full_prefix
            )
            for obj in resp.get("Contents", []):
                s3_keys.append(obj["Key"])
        except Exception as exc:
            logger.warning("Failed to list S3 images for cleanup: %s", exc)
        if s3_keys:
            await s3.delete_objects(s3_keys)

    await db.execute(delete(TestTemplate).where(TestTemplate.id == template_id))
    await db.commit()


_ASSET_CONTENT_TYPES: dict[str, str] = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".png": "image/png",
    ".md": "text/markdown; charset=utf-8",
}


async def serve_asset(
    s3: "S3Client",
    past_paper_id: uuid.UUID,
    asset_type: str,
    filename: str,
) -> tuple[bytes, str]:
    """Fetch a past-paper asset from S3 and return (bytes, content_type).

    Raises ``FileNotFoundError`` if the asset does not exist.
    """
    s3_key = f"past-papers/{past_paper_id}/assets/{asset_type}/{filename}"
    try:
        data = await s3.download_bytes(s3_key)
    except Exception as exc:
        raise FileNotFoundError(s3_key) from exc

    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    return data, _ASSET_CONTENT_TYPES.get(ext, "application/octet-stream")
