"""Test template generation and CRUD."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.exam.service import _expand_nodes
from src.prompts.manager import PromptManager
from src.learning.tests.models import TestTemplate, TestQuestion
from src.learning.tests.prompts import (
    build_allocation_messages,
    build_generation_messages,
    build_single_question_messages,
)
from src.roadmap.models import RoadmapNode, RoadmapProgress
from src.learning.tests.markdown_validator import validate_question_markdown

logger = logging.getLogger(__name__)


class TemplateServiceError(Exception):
    """Raised for business-logic failures in the template domain."""


def _typed_question_from_raw(raw: dict, type_key: str, fixed_points: int, node_ids: list) -> dict:
    """Normalise an LLM response into the canonical TestQuestion field dict."""
    question_text = raw.get("question", "")
    model_answer = raw.get("model_answer", "")
    is_mcq = type_key == "mcq"

    options = None
    correct_option_index = None

    if is_mcq:
        # Preferred: options as a separate JSON array (PQG prompt contract).
        raw_options = raw.get("options")
        if isinstance(raw_options, list):
            cleaned = [str(o).strip() for o in raw_options if str(o).strip()]
            if len(cleaned) >= 3:
                options = cleaned

        if options:
            # PQG prompts use 1-based "correct_option" (A=1..D=4).
            # The legacy field is 0-based "correct_option_index".
            raw_co = raw.get("correct_option")
            raw_coi = raw.get("correct_option_index")
            if isinstance(raw_co, int) and 1 <= raw_co <= len(options):
                correct_option_index = raw_co - 1
            elif isinstance(raw_coi, int) and 0 <= raw_coi < len(options):
                correct_option_index = raw_coi
            else:
                correct_option_index = _resolve_correct_option(model_answer, options)
        else:
            # Fallback: some prompts embed A./B./C./D. inside the question text.
            options, stem = _extract_mcq_options(question_text)
            if options:
                question_text = stem
                correct_option_index = _resolve_correct_option(model_answer, options)

    return {
        "type": "mcq" if is_mcq and options else "open",
        "question": question_text,
        "options": options,
        "correct_option_index": correct_option_index,
        "model_answer": model_answer,
        "mark_scheme": raw.get("mark_scheme") or None,
        "hint": raw.get("hint"),
        "points": fixed_points,
        "sources": None,
        "context": raw.get("context") or None,
        "_node_ids": node_ids,
    }


def _extract_mcq_options(question_text: str) -> tuple[list[str] | None, str]:
    """Extract A/B/C/D options from a question string. Returns (options, stem)."""
    option_re = re.compile(r"^([A-D])[.)]\s*(.+)$", re.MULTILINE)
    matches = list(option_re.finditer(question_text))
    if len(matches) < 3:
        return None, question_text

    options = [m.group(2).strip() for m in matches]
    stem = question_text[: matches[0].start()].strip()
    return options, stem


def _resolve_correct_option(model_answer: str, options: list[str]) -> int | None:
    """Find 0-based index of correct option from model_answer (usually just a letter)."""
    answer = model_answer.strip().upper()
    for i, letter in enumerate("ABCD"):
        if answer.startswith(letter) and (len(answer) == 1 or not answer[1].isalpha()):
            return i
    return None


def _compute_item_id(node_id: uuid.UUID, question_text: str) -> str:
    """Stable hash for mastery dedup — same question for same topic = same id."""
    normalized = re.sub(r"\s+", " ", question_text.strip().lower())
    raw = f"{node_id}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _fix_backslash_escapes(s: str) -> str:
    """Escape invalid backslash sequences in LLM JSON output.

    Scans two characters at a time so that valid \\X pairs are never broken.
    Any \\ followed by a character that is not a valid JSON escape is doubled.
    """
    valid = frozenset('"\\/bfnrtu')
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in valid:
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                out.append('\\\\')
                i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def _parse_json_response(raw: str) -> list | dict:
    """Best-effort JSON parsing from LLM output."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```\s*$", "", clean)
    clean = _fix_backslash_escapes(clean)
    return json.loads(clean)


class TestTemplateService:
    """Creates and manages test templates (no session logic)."""

    # Class-level shared state — survives across per-request instances
    _active_tasks: dict[uuid.UUID, asyncio.Task] = {}
    _progress_subscribers: dict[uuid.UUID, list[asyncio.Queue]] = {}

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: YandexGPTLLMGateway | None = None,
        usage_service: object | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm or YandexGPTLLMGateway()
        self._usage_service = usage_service
        self._pm = prompt_manager

    # ── Generate ────────────────────────────────────────────────────────

    async def _generate_typed_question(
        self,
        type_key: str,
        topic_name: str,
        lesson_content: str,
        node_ids: list[uuid.UUID],
        pqg_service: str,
        points: int,
        previous_questions: list[str] | None = None,
    ) -> dict | None:
        """Generate one typed question using prompts from the prompt manager.

        Returns None if the question has markdown issues after one retry.
        """
        t0 = time.monotonic()
        logger.info(
            "test_gen | LLM start  | type=%-16s marks=%-2d topic=%r",
            type_key, points, topic_name[:60],
        )

        system_content = self._pm.get(pqg_service, f"{type_key}_system")
        user_template = self._pm.get(pqg_service, f"{type_key}_user_template")

        user_content = user_template.format(
            topic_name=topic_name,
            topic_names=topic_name,
            lesson_content=lesson_content[:8000],
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        if previous_questions:
            prev_text = "\n".join(f"- {q[:120]}" for q in previous_questions)
            messages[-1]["content"] += (
                f"\n\nAlready generated for this topic — do NOT repeat or closely resemble:\n{prev_text}"
            )

        raw_str, _usage = await self._llm.chat_complete(messages)
        elapsed = time.monotonic() - t0
        tokens = getattr(_usage, "total_tokens", None) if _usage else None
        logger.info(
            "test_gen | LLM done   | type=%-16s marks=%-2d elapsed=%.1fs tokens=%s topic=%r",
            type_key, points, elapsed, tokens, topic_name[:60],
        )
        if self._usage_service and hasattr(self, "_current_user_id"):
            self._usage_service.log_usage_fire_and_forget(
                user_id=self._current_user_id, feature="test_gen", usage=_usage,
            )
        raw = _parse_json_response(raw_str)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        issues = validate_question_markdown(raw)
        if issues:
            issue_desc = "; ".join(f"{i.field}: {i.issue}" for i in issues)
            logger.warning("test_gen | markdown issues, retrying | %s", issue_desc)
            correction = (
                f"Your previous response had markdown formatting errors: {issue_desc}. "
                "Fix them: close all LaTeX with matching $ or $$ delimiters, "
                "close all ``` code fences, and add a separator row (|---|) after every table header. "
                "Return the corrected question as JSON only."
            )
            messages.append({"role": "assistant", "content": raw_str})
            messages.append({"role": "user", "content": correction})
            t1 = time.monotonic()
            raw_str, _usage = await self._llm.chat_complete(messages)
            logger.info(
                "test_gen | LLM retry  | type=%-16s elapsed=%.1fs topic=%r",
                type_key, time.monotonic() - t1, topic_name[:60],
            )
            if self._usage_service and hasattr(self, "_current_user_id"):
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="test_gen", usage=_usage,
                )
            raw = _parse_json_response(raw_str)
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            retry_issues = validate_question_markdown(raw)
            if retry_issues:
                retry_desc = "; ".join(f"{i.field}: {i.issue}" for i in retry_issues)
                logger.warning(
                    "test_gen | markdown issues after retry, skipping | %s", retry_desc
                )
                return None

        return _typed_question_from_raw(raw, type_key, points, node_ids)

    async def _generate_group_sequential(
        self,
        group: list[dict],
        topics: list[dict],
        lessons_by_node: dict[str, str],
        names_by_node: dict[str, str],
        pqg_service: str,
        points_map: dict[str, int],
    ) -> list[dict]:
        """Generate questions for a node group sequentially, passing previous as context."""
        results = []
        previous_questions: list[str] = []

        for alloc in group:
            type_key = alloc["type"]
            node_ids = alloc["node_ids"]
            primary_nid = node_ids[0]

            topic_name = names_by_node.get(primary_nid, "")
            lesson_content = lessons_by_node.get(primary_nid, "")

            if len(node_ids) > 1:
                for extra_nid in node_ids[1:]:
                    extra_name = names_by_node.get(extra_nid, "")
                    extra_content = lessons_by_node.get(extra_nid, "")
                    if extra_content:
                        lesson_content += (
                            f"\n\n--- RELATED TOPIC: {extra_name} ---\n"
                            f"{extra_content}"
                        )
                topic_name = ", ".join(
                    names_by_node.get(nid, "") for nid in node_ids
                )

            nid_uuids = [uuid.UUID(nid) for nid in node_ids]

            try:
                q = None
                for attempt in range(3):
                    q = await self._generate_typed_question(
                        type_key, topic_name, lesson_content, nid_uuids,
                        pqg_service=pqg_service,
                        points=points_map[type_key],
                        previous_questions=previous_questions or None,
                    )
                    if q is not None:
                        break
                    logger.warning(
                        "test_gen | markdown retry %d/3 | type=%s node=%s",
                        attempt + 1, type_key, primary_nid[:8],
                    )
                if q is None:
                    logger.error(
                        "test_gen | skipping question | type=%s node=%s after 3 attempts",
                        type_key, primary_nid[:8],
                    )
                    continue
                results.append(q)
                if q.get("question"):
                    previous_questions.append(q["question"])
            except Exception as exc:
                logger.error(
                    "test_gen | group gen ERROR | type=%s node=%s: %s",
                    type_key, primary_nid[:8], exc,
                )

        return results

    async def _generate_group_sequential_streaming(
        self,
        group: list[dict],
        topics: list[dict],
        lessons_by_node: dict[str, str],
        names_by_node: dict[str, str],
        progress_queue: asyncio.Queue,
        pqg_service: str,
        points_map: dict[str, int],
    ) -> tuple[str, list[dict]]:
        """Like _generate_group_sequential but pushes progress events."""
        results = []
        previous_questions: list[str] = []

        for alloc in group:
            type_key = alloc["type"]
            node_ids = alloc["node_ids"]
            primary_nid = node_ids[0]

            topic_name = names_by_node.get(primary_nid, "")
            lesson_content = lessons_by_node.get(primary_nid, "")

            if len(node_ids) > 1:
                for extra_nid in node_ids[1:]:
                    extra_name = names_by_node.get(extra_nid, "")
                    extra_content = lessons_by_node.get(extra_nid, "")
                    if extra_content:
                        lesson_content += (
                            f"\n\n--- RELATED TOPIC: {extra_name} ---\n"
                            f"{extra_content}"
                        )
                topic_name = ", ".join(
                    names_by_node.get(nid, "") for nid in node_ids
                )

            nid_uuids = [uuid.UUID(nid) for nid in node_ids]

            try:
                q = None
                for attempt in range(3):
                    q = await self._generate_typed_question(
                        type_key, topic_name, lesson_content, nid_uuids,
                        pqg_service=pqg_service,
                        points=points_map[type_key],
                        previous_questions=previous_questions or None,
                    )
                    if q is not None:
                        break
                    logger.warning(
                        "test_gen | markdown retry %d/3 | type=%s node=%s",
                        attempt + 1, type_key, primary_nid[:8],
                    )
                if q is None:
                    logger.error(
                        "test_gen | skipping question | type=%s node=%s after 3 attempts",
                        type_key, primary_nid[:8],
                    )
                    continue
                results.append(q)
                if q.get("question"):
                    previous_questions.append(q["question"])
                await progress_queue.put({
                    "label": type_key,
                    "generated": 1,
                    "total": 1,
                })
            except Exception as exc:
                logger.error(
                    "test_gen | group gen ERROR | type=%s node=%s: %s",
                    type_key, primary_nid[:8], exc,
                )

        return "grouped", results

    async def generate_template(
        self,
        user_id: uuid.UUID,
        folder_id: uuid.UUID,
        node_ids: list[uuid.UUID],
        total_questions: int,
        name: str | None = None,
        question_type_counts: dict[str, int] | None = None,
    ) -> TestTemplate:
        self._current_user_id = user_id
        async with self._session_factory() as session:
            # 1. Expand nodes to level-3
            expanded = await _expand_nodes(session, node_ids)
            logger.info(
                "Expanded %d input nodes to %d level-3 nodes",
                len(node_ids),
                len(expanded),
            )
            if not expanded:
                raise TemplateServiceError(
                    "No lesson nodes found for the selected topics"
                )

            # 2. Fetch lesson content + node names
            nodes_result = await session.scalars(
                select(RoadmapNode).where(RoadmapNode.id.in_(expanded))
            )
            nodes = {n.id: n for n in nodes_result}

            # Fetch parent (level-2) nodes for enriched allocation
            parent_ids = [n.parent_id for n in nodes.values() if n.parent_id]
            if parent_ids:
                parent_result = await session.scalars(
                    select(RoadmapNode).where(RoadmapNode.id.in_(parent_ids))
                )
                parents_by_id = {p.id: p for p in parent_result}
            else:
                parents_by_id = {}

            from src.learning.models import Lesson

            lesson_ids = [n.lesson_id for n in nodes.values() if n.lesson_id]
            if lesson_ids:
                lessons_result = await session.scalars(
                    select(Lesson).where(Lesson.id.in_(lesson_ids))
                )
                lessons_by_id = {lesson.id: lesson for lesson in lessons_result}
            else:
                lessons_by_id = {}

            # Batch-fetch all RoadmapProgress rows (avoids N+1)
            progress_result = await session.scalars(
                select(RoadmapProgress).where(
                    RoadmapProgress.node_id.in_(expanded),
                    RoadmapProgress.user_id == user_id,
                )
            )
            progress_by_node = {rp.node_id: rp for rp in progress_result}

            # Build topic info
            topics = []
            for nid in expanded:
                node = nodes.get(nid)
                if not node or not node.lesson_id:
                    continue
                lesson = lessons_by_id.get(node.lesson_id)
                if not lesson:
                    continue

                rp = progress_by_node.get(nid)
                # Prefer mastery (Beta engine) over legacy progress
                mastery_val = (
                    rp.mastery
                    if rp and rp.mastery is not None
                    else (rp.progress if rp else 0)
                )
                parent = parents_by_id.get(node.parent_id) if node.parent_id else None
                topics.append({
                    "node_id": str(nid),
                    "name": node.name,
                    "parent_name": parent.name if parent else "",
                    "progress": round(mastery_val),
                    "content": lesson.content,
                    "content_summary": (lesson.content or "")[:200],
                })

            if not topics:
                raise TemplateServiceError(
                    "No lessons with content found for the selected topics"
                )

            # 3. Create template
            effective_total = (
                sum(question_type_counts.values())
                if question_type_counts
                else total_questions
            )
            template_name = name or self._auto_name(topics)
            template = TestTemplate(
                user_id=user_id,
                folder_id=folder_id,
                name=template_name,
                type="practice_questions",
                status="ready",
                node_ids=expanded,
                total_questions=effective_total,
            )
            session.add(template)
            await session.flush()

            # 4 + 5. Generate questions
            all_question_dicts: list[dict] = []
            gen_t0 = time.monotonic()

            if question_type_counts:
                # ── Typed path (dynamic via prompt manager) ───────────────
                from src.files.models import Folder
                folder_obj = await session.get(Folder, folder_id)
                pqg_service = folder_obj.pqg_service if folder_obj else None

                if not pqg_service:
                    raise TemplateServiceError(
                        "This folder does not support typed question generation"
                    )

                import json as _json
                qt_json = self._pm.get(pqg_service, "_question_types")
                qt_list = _json.loads(qt_json)
                points_map = {qt["key"]: qt["points"] for qt in qt_list}

                logger.info(
                    "test_gen | typed path | types=%s topics=%d",
                    list(question_type_counts.keys()), len(topics),
                )
                allocations = await self._allocate_questions_unified(
                    question_type_counts, topics,
                    pqg_service=pqg_service,
                )
                logger.info(
                    "test_gen | unified alloc | assignments=%d",
                    len(allocations),
                )

                # Group by primary node_id for sequential generation within each node
                node_groups: dict[str, list[dict]] = defaultdict(list)
                for alloc in allocations:
                    primary_nid = alloc["node_ids"][0]
                    node_groups[primary_nid].append(alloc)

                # Build a coroutine per node group: sequential within, parallel across
                gen_tasks = []
                for primary_nid, group in node_groups.items():
                    gen_tasks.append(
                        self._generate_group_sequential(
                            group=group,
                            topics=topics,
                            lessons_by_node={
                                t["node_id"]: t["content"]
                                for t in topics
                            },
                            names_by_node={
                                t["node_id"]: t["name"]
                                for t in topics
                            },
                            pqg_service=pqg_service,
                            points_map=points_map,
                        )
                    )

                results = await asyncio.gather(*gen_tasks, return_exceptions=True)
                logger.info(
                    "test_gen | gather done  | elapsed=%.1fs",
                    time.monotonic() - gen_t0,
                )
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("test_gen | task ERROR | %s", result)
                        continue
                    all_question_dicts.extend(result)
            else:
                # ── Generic fallback (original behaviour) ──────────────────
                allocation = await self._allocate_questions(topics, total_questions)
                logger.info(
                    "test_gen | generic    | allocation=%s",
                    [(a["node_id"][:8], a["count"]) for a in allocation],
                )
                gen_tasks = []
                for alloc in allocation:
                    nid = alloc["node_id"]
                    count = alloc["count"]
                    topic = next((t for t in topics if t["node_id"] == nid), None)
                    if topic and count > 0:
                        gen_tasks.append(
                            self._gen_for_topic_with_id(
                                node_id=nid,
                                topic_name=topic["name"],
                                lesson_content=topic["content"],
                                count=count,
                            )
                        )
                results = await asyncio.gather(*gen_tasks, return_exceptions=True)
                logger.info(
                    "test_gen | gather done  | elapsed=%.1fs",
                    time.monotonic() - gen_t0,
                )
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("test_gen | task ERROR | %s", result)
                        continue
                    topic_node_id, questions_data = result
                    logger.info(
                        "test_gen | task result | node=%s questions=%d",
                        str(topic_node_id)[:8], len(questions_data),
                    )
                    nid_uuid = uuid.UUID(topic_node_id)
                    for q in questions_data:
                        q["_node_ids"] = [nid_uuid]
                    all_question_dicts.extend(questions_data)

            # 6. Create TestQuestion rows
            logger.info(
                "test_gen | persist    | total_questions=%d template_id=%s",
                len(all_question_dicts), template.id,
            )
            idx = 0
            total_marks = 0
            for q in all_question_dicts:
                q_node_ids = q.pop("_node_ids", None) or [expanded[0]] if expanded else []
                first_nid = q_node_ids[0] if q_node_ids else expanded[0]
                tq = TestQuestion(
                    template_id=template.id,
                    node_ids=q_node_ids,
                    item_id=_compute_item_id(first_nid, q.get("question", "")),
                    index=idx,
                    type=q.get("type", "mcq"),
                    question=q.get("question", ""),
                    options=q.get("options"),
                    correct_option_index=q.get("correct_option_index"),
                    model_answer=q.get("model_answer", ""),
                    mark_scheme=q.get("mark_scheme"),
                    hint=q.get("hint"),
                    points=1 if q.get("type") == "mcq" else min(q.get("points", 1), 25),
                    sources=q.get("sources"),
                    context=q.get("context"),
                )
                session.add(tq)
                total_marks += tq.points
                idx += 1

            template.total_marks = total_marks
            template.total_questions = idx

            await session.commit()
            await session.refresh(template)
            logger.info(
                "test_gen | complete   | template_id=%s questions=%d marks=%d elapsed=%.1fs",
                template.id, idx, total_marks, time.monotonic() - gen_t0,
            )
            return template

    async def _generate_questions_sequential(
        self,
        node_id: str,
        topic_name: str,
        lesson_content: str,
        count: int,
        progress_queue: asyncio.Queue,
    ) -> tuple[str, list[dict]]:
        """Generate questions one-by-one for a single node.

        Each question sees all previously generated questions as context
        so the LLM avoids duplicates. Pushes a progress event to the queue
        after each question is generated.
        """
        max_content = 12000
        if len(lesson_content) > max_content:
            lesson_content = (
                lesson_content[:max_content] + "\n\n[...content truncated...]"
            )

        generated: list[dict] = []
        previous_texts: list[str] = []

        for i in range(count):
            messages = build_single_question_messages(
                topic_name=topic_name,
                lesson_content=lesson_content,
                current=i + 1,
                total=count,
                previous_questions=previous_texts,
                pm=self._pm,
            )
            try:
                raw, _usage = await self._llm.chat_complete(messages)
                if self._usage_service and hasattr(self, "_current_user_id"):
                    self._usage_service.log_usage_fire_and_forget(
                        user_id=self._current_user_id, feature="test_gen", usage=_usage,
                    )
                question = _parse_json_response(raw)
                if isinstance(question, list):
                    question = question[0] if question else {}

                issues = validate_question_markdown(question)
                if issues:
                    issue_desc = "; ".join(f"{iss.field}: {iss.issue}" for iss in issues)
                    logger.warning(
                        "test_gen | sequential markdown issues, retrying | node=%s q=%d/%d | %s",
                        node_id, i + 1, count, issue_desc,
                    )
                    correction = (
                        f"Your previous response had markdown formatting errors: {issue_desc}. "
                        "Fix them: close all LaTeX with matching $ or $$ delimiters, "
                        "close all ``` code fences, and add a separator row (|---|) after every table header. "
                        "Return the corrected question as JSON only."
                    )
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content": correction})
                    raw, _usage = await self._llm.chat_complete(messages)
                    if self._usage_service and hasattr(self, "_current_user_id"):
                        self._usage_service.log_usage_fire_and_forget(
                            user_id=self._current_user_id, feature="test_gen", usage=_usage,
                        )
                    question = _parse_json_response(raw)
                    if isinstance(question, list):
                        question = question[0] if question else {}
                    retry_issues = validate_question_markdown(question)
                    if retry_issues:
                        retry_desc = "; ".join(f"{iss.field}: {iss.issue}" for iss in retry_issues)
                        logger.warning(
                            "test_gen | sequential markdown issues after retry, skipping | node=%s q=%d/%d | %s",
                            node_id, i + 1, count, retry_desc,
                        )
                        continue

                generated.append(question)
                previous_texts.append(question.get("question", ""))
            except Exception as exc:
                logger.error(
                    "Single question generation failed (node=%s, q=%d/%d): %s",
                    node_id,
                    i + 1,
                    count,
                    exc,
                )
                continue

            # Push per-question progress update
            await progress_queue.put(
                {
                    "node_id": node_id,
                    "topic_name": topic_name,
                    "generated": len(generated),
                    "total": count,
                }
            )

        return node_id, generated

    async def generate_template_streaming(
        self,
        user_id: uuid.UUID,
        folder_id: uuid.UUID,
        node_ids: list[uuid.UUID],
        total_questions: int,
        name: str | None = None,
        question_type_counts: dict[str, int] | None = None,
    ):
        self._current_user_id = user_id
        """Yield per-node progress dicts as each question is generated.

        Questions are generated one-by-one per node (sequential within a node,
        parallel across nodes). Each question sees previously generated
        questions as context to avoid duplicates.

        Yields:
            {"event": "progress", "nodes": {<node_name>: {"generated": int, "total": int}, ...}}
            {"event": "complete", "template_id": str, ...}
            {"event": "error", "message": str}
        """
        async with self._session_factory() as session:
            # ── setup ──
            expanded = await _expand_nodes(session, node_ids)
            if not expanded:
                yield {
                    "event": "error",
                    "message": "No lesson nodes found for the selected topics",
                }
                return

            nodes_result = await session.scalars(
                select(RoadmapNode).where(RoadmapNode.id.in_(expanded))
            )
            nodes = {n.id: n for n in nodes_result}

            # Fetch parent (level-2) nodes for enriched allocation
            parent_ids = [n.parent_id for n in nodes.values() if n.parent_id]
            if parent_ids:
                parent_result = await session.scalars(
                    select(RoadmapNode).where(RoadmapNode.id.in_(parent_ids))
                )
                parents_by_id = {p.id: p for p in parent_result}
            else:
                parents_by_id = {}

            from src.learning.models import Lesson

            lesson_ids = [n.lesson_id for n in nodes.values() if n.lesson_id]
            if lesson_ids:
                lessons_result = await session.scalars(
                    select(Lesson).where(Lesson.id.in_(lesson_ids))
                )
                lessons_by_id = {lesson.id: lesson for lesson in lessons_result}
            else:
                lessons_by_id = {}

            # Batch-fetch all RoadmapProgress rows (avoids N+1)
            progress_result = await session.scalars(
                select(RoadmapProgress).where(
                    RoadmapProgress.node_id.in_(expanded),
                    RoadmapProgress.user_id == user_id,
                )
            )
            progress_by_node = {rp.node_id: rp for rp in progress_result}

            topics = []
            for nid in expanded:
                node = nodes.get(nid)
                if not node or not node.lesson_id:
                    continue
                lesson = lessons_by_id.get(node.lesson_id)
                if not lesson:
                    continue
                rp = progress_by_node.get(nid)
                # Prefer mastery (Beta engine) over legacy progress
                mastery_val = (
                    rp.mastery
                    if rp and rp.mastery is not None
                    else (rp.progress if rp else 0)
                )
                parent = parents_by_id.get(node.parent_id) if node.parent_id else None
                topics.append({
                    "node_id": str(nid),
                    "name": node.name,
                    "parent_name": parent.name if parent else "",
                    "progress": round(mastery_val),
                    "content": lesson.content,
                    "content_summary": (lesson.content or "")[:200],
                })

            if not topics:
                yield {
                    "event": "error",
                    "message": "No lessons with content found for the selected topics",
                }
                return

            effective_total = (
                sum(question_type_counts.values())
                if question_type_counts
                else total_questions
            )
            template_name = name or self._auto_name(topics)
            template = TestTemplate(
                user_id=user_id,
                folder_id=folder_id,
                name=template_name,
                type="practice_questions",
                status="ready",
                node_ids=expanded,
                total_questions=effective_total,
            )
            session.add(template)
            await session.flush()

            # ── build task list and progress map ──
            node_progress: dict[str, dict] = {}
            progress_queue: asyncio.Queue = asyncio.Queue()
            gen_tasks = []
            ", ".join(t["name"] for t in topics)

            if question_type_counts:
                # ── Typed path (dynamic via prompt manager) ───────────────
                from src.files.models import Folder
                folder_obj = await session.get(Folder, folder_id)
                pqg_service = folder_obj.pqg_service if folder_obj else None

                if not pqg_service:
                    yield {
                        "event": "error",
                        "message": "This folder does not support typed question generation",
                    }
                    return

                import json as _json
                qt_json = self._pm.get(pqg_service, "_question_types")
                qt_list = _json.loads(qt_json)
                points_map = {qt["key"]: qt["points"] for qt in qt_list}

                allocations = await self._allocate_questions_unified(
                    question_type_counts, topics,
                    pqg_service=pqg_service,
                )

                for type_key, count in question_type_counts.items():
                    if count > 0:
                        node_progress[type_key] = {"generated": 0, "total": count}

                node_groups: dict[str, list[dict]] = defaultdict(list)
                for alloc in allocations:
                    primary_nid = alloc["node_ids"][0]
                    node_groups[primary_nid].append(alloc)

                for primary_nid, group in node_groups.items():
                    gen_tasks.append(
                        self._generate_group_sequential_streaming(
                            group=group,
                            topics=topics,
                            lessons_by_node={
                                t["node_id"]: t["content"]
                                for t in topics
                            },
                            names_by_node={
                                t["node_id"]: t["name"]
                                for t in topics
                            },
                            progress_queue=progress_queue,
                            pqg_service=pqg_service,
                            points_map=points_map,
                        )
                    )
            else:
                # ── Generic fallback ────────────────────────────────────────
                allocation = await self._allocate_questions(topics, total_questions)
                for alloc in allocation:
                    nid = alloc["node_id"]
                    count = alloc["count"]
                    topic = next((t for t in topics if t["node_id"] == nid), None)
                    if topic and count > 0:
                        node_progress[topic["name"]] = {"generated": 0, "total": count}
                        gen_tasks.append(
                            self._generate_questions_sequential(
                                node_id=nid,
                                topic_name=topic["name"],
                                lesson_content=topic["content"],
                                count=count,
                                progress_queue=progress_queue,
                            )
                        )

            # ── send initial state (all zeros) ──
            yield {
                "event": "progress",
                "nodes": {k: dict(v) for k, v in node_progress.items()},
            }

            # ── run all tasks in parallel, drain progress queue ──
            _DONE = object()

            async def _run_and_signal():
                results = await asyncio.gather(*gen_tasks, return_exceptions=True)
                await progress_queue.put(_DONE)
                return results

            runner = asyncio.ensure_future(_run_and_signal())

            while True:
                update = await progress_queue.get()
                if update is _DONE:
                    break
                key = update.get("label") or update.get("topic_name")
                if key and key in node_progress:
                    node_progress[key]["generated"] = min(
                        node_progress[key]["generated"] + 1,
                        node_progress[key]["total"],
                    )
                yield {
                    "event": "progress",
                    "nodes": {k: dict(v) for k, v in node_progress.items()},
                }

            # ── collect results ──
            results = runner.result()
            all_question_dicts: list[dict] = []

            if question_type_counts:
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("Typed generation failed: %s", result)
                        continue
                    _, questions = result
                    all_question_dicts.extend(questions)
            else:
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("Node generation failed: %s", result)
                        continue
                    topic_node_id, questions_data = result
                    nid_uuid = uuid.UUID(topic_node_id)
                    for q in questions_data:
                        q["_node_ids"] = [nid_uuid]
                    all_question_dicts.extend(questions_data)

            # ── persist questions ──
            idx = 0
            total_marks = 0
            for q in all_question_dicts:
                q_node_ids = q.pop("_node_ids", None) or ([expanded[0]] if expanded else [])
                first_nid = q_node_ids[0] if q_node_ids else (expanded[0] if expanded else None)
                tq = TestQuestion(
                    template_id=template.id,
                    node_ids=q_node_ids,
                    item_id=_compute_item_id(first_nid, q.get("question", "")),
                    index=idx,
                    type=q.get("type", "mcq"),
                    question=q.get("question", ""),
                    options=q.get("options"),
                    correct_option_index=q.get("correct_option_index"),
                    model_answer=q.get("model_answer", ""),
                    mark_scheme=q.get("mark_scheme"),
                    hint=q.get("hint"),
                    points=1 if q.get("type") == "mcq" else min(q.get("points", 1), 25),
                    sources=q.get("sources"),
                    context=q.get("context"),
                )
                session.add(tq)
                total_marks += tq.points
                idx += 1

            template.total_marks = total_marks
            template.total_questions = idx

            await session.commit()
            await session.refresh(template)

            yield {
                "event": "complete",
                "template_id": str(template.id),
                "total_questions": template.total_questions,
                "total_marks": template.total_marks,
                "name": template.name,
            }

    # ── Background generation (persistent) ──────────────────────────────

    async def _build_topics(
        self,
        session: AsyncSession,
        expanded: list[uuid.UUID],
        user_id: uuid.UUID,
    ) -> list[dict]:
        """Fetch nodes, lessons, progress and build the topics list.

        Shared helper used by both start_generation and retry_generation.
        """
        nodes_result = await session.scalars(
            select(RoadmapNode).where(RoadmapNode.id.in_(expanded))
        )
        nodes = {n.id: n for n in nodes_result}

        parent_ids = [n.parent_id for n in nodes.values() if n.parent_id]
        if parent_ids:
            parent_result = await session.scalars(
                select(RoadmapNode).where(RoadmapNode.id.in_(parent_ids))
            )
            parents_by_id = {p.id: p for p in parent_result}
        else:
            parents_by_id = {}

        from src.learning.models import Lesson

        lesson_ids = [n.lesson_id for n in nodes.values() if n.lesson_id]
        if lesson_ids:
            lessons_result = await session.scalars(
                select(Lesson).where(Lesson.id.in_(lesson_ids))
            )
            lessons_by_id = {lesson.id: lesson for lesson in lessons_result}
        else:
            lessons_by_id = {}

        progress_result = await session.scalars(
            select(RoadmapProgress).where(
                RoadmapProgress.node_id.in_(expanded),
                RoadmapProgress.user_id == user_id,
            )
        )
        progress_by_node = {rp.node_id: rp for rp in progress_result}

        topics: list[dict] = []
        for nid in expanded:
            node = nodes.get(nid)
            if not node or not node.lesson_id:
                continue
            lesson = lessons_by_id.get(node.lesson_id)
            if not lesson:
                continue
            rp = progress_by_node.get(nid)
            mastery_val = (
                rp.mastery
                if rp and rp.mastery is not None
                else (rp.progress if rp else 0)
            )
            parent = parents_by_id.get(node.parent_id) if node.parent_id else None
            topics.append({
                "node_id": str(nid),
                "name": node.name,
                "parent_name": parent.name if parent else "",
                "progress": round(mastery_val),
                "content": lesson.content,
                "content_summary": (lesson.content or "")[:200],
            })
        return topics

    async def start_generation(
        self,
        user_id: uuid.UUID,
        folder_id: uuid.UUID,
        node_ids: list[uuid.UUID],
        total_questions: int,
        name: str | None = None,
        question_type_counts: dict[str, int] | None = None,
    ) -> TestTemplate:
        """Create template with status='processing' and launch background generation.

        Returns the template immediately without waiting for questions.
        """
        self._current_user_id = user_id
        async with self._session_factory() as session:
            expanded = await _expand_nodes(session, node_ids)
            if not expanded:
                raise TemplateServiceError(
                    "No lesson nodes found for the selected topics"
                )

            topics = await self._build_topics(session, expanded, user_id)
            if not topics:
                raise TemplateServiceError(
                    "No lessons with content found for the selected topics"
                )

            # Resolve PQG service for typed path
            pqg_service = None
            points_map = {}
            if question_type_counts:
                from src.files.models import Folder
                folder_obj = await session.get(Folder, folder_id)
                pqg_service = folder_obj.pqg_service if folder_obj else None

                if not pqg_service:
                    raise TemplateServiceError(
                        "This folder does not support typed question generation"
                    )

                import json as _json
                qt_json = self._pm.get(pqg_service, "_question_types")
                qt_list = _json.loads(qt_json)
                points_map = {qt["key"]: qt["points"] for qt in qt_list}

            # Build allocations before committing so we fail fast on bad input
            if question_type_counts:
                allocations = await self._allocate_questions_unified(
                    question_type_counts, topics,
                    pqg_service=pqg_service,
                )
            else:
                allocations = await self._allocate_questions(topics, total_questions)

            effective_total = (
                sum(question_type_counts.values())
                if question_type_counts
                else total_questions
            )

            # Build initial progress with zero counts
            initial_progress: dict[str, dict] = {}
            if question_type_counts:
                for type_key, count in question_type_counts.items():
                    if count > 0:
                        initial_progress[type_key] = {"generated": 0, "total": count}
            else:
                for alloc in allocations:
                    nid = alloc["node_id"]
                    count = alloc["count"]
                    topic = next((t for t in topics if t["node_id"] == nid), None)
                    if topic and count > 0:
                        initial_progress[topic["name"]] = {"generated": 0, "total": count}

            template_name = name or self._auto_name(topics)
            task_id = str(uuid.uuid4())
            template = TestTemplate(
                user_id=user_id,
                folder_id=folder_id,
                name=template_name,
                type="practice_questions",
                status="processing",
                node_ids=expanded,
                total_questions=effective_total,
                generation_progress={"nodes": initial_progress, "error": None},
                generation_task_id=task_id,
                question_type_counts=question_type_counts,
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)

            # Launch background task
            bg_task = asyncio.create_task(
                self._run_generation_task(
                    template_id=template.id,
                    user_id=user_id,
                    expanded=expanded,
                    topics=topics,
                    allocations=allocations,
                    question_type_counts=question_type_counts,
                    total_questions=total_questions,
                    pqg_service=pqg_service,
                    points_map=points_map,
                ),
                name=f"gen-{template.id}",
            )
            self._active_tasks[template.id] = bg_task
            bg_task.add_done_callback(
                lambda _t, _tid=template.id: self._active_tasks.pop(_tid, None)
            )

            return template

    async def _run_generation_task(
        self,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        expanded: list[uuid.UUID],
        topics: list[dict],
        allocations: list[dict],
        question_type_counts: dict[str, int] | None,
        total_questions: int,
        pqg_service: str | None = None,
        points_map: dict[str, int] | None = None,
    ) -> None:
        """Background task: generate questions and persist them."""
        gen_t0 = time.monotonic()
        progress_queue: asyncio.Queue = asyncio.Queue()

        try:
            gen_tasks = []
            lessons_by_node = {t["node_id"]: t["content"] for t in topics}
            names_by_node = {t["node_id"]: t["name"] for t in topics}

            if question_type_counts:
                # Typed path — parallel across node groups, sequential within
                node_groups: dict[str, list[dict]] = defaultdict(list)
                for alloc in allocations:
                    primary_nid = alloc["node_ids"][0]
                    node_groups[primary_nid].append(alloc)

                for primary_nid, group in node_groups.items():
                    gen_tasks.append(
                        self._generate_group_sequential_streaming(
                            group=group,
                            topics=topics,
                            lessons_by_node=lessons_by_node,
                            names_by_node=names_by_node,
                            progress_queue=progress_queue,
                            pqg_service=pqg_service,
                            points_map=points_map,
                        )
                    )
            else:
                # Generic path
                for alloc in allocations:
                    nid = alloc["node_id"]
                    count = alloc["count"]
                    topic = next((t for t in topics if t["node_id"] == nid), None)
                    if topic and count > 0:
                        gen_tasks.append(
                            self._generate_questions_sequential(
                                node_id=nid,
                                topic_name=topic["name"],
                                lesson_content=topic["content"],
                                count=count,
                                progress_queue=progress_queue,
                            )
                        )

            # Drain progress queue while tasks run
            _DONE = object()

            async def _run_and_signal():
                results = await asyncio.gather(*gen_tasks, return_exceptions=True)
                await progress_queue.put(_DONE)
                return results

            runner = asyncio.ensure_future(_run_and_signal())

            while True:
                update = await progress_queue.get()
                if update is _DONE:
                    break
                # Update progress in DB
                key = update.get("label") or update.get("topic_name")
                if key:
                    await self._update_generation_progress(template_id, key)

            results = runner.result()

            # Collect all question dicts
            all_question_dicts: list[dict] = []
            if question_type_counts:
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("test_gen | bg task ERROR | %s", result)
                        continue
                    _, questions = result
                    all_question_dicts.extend(questions)
            else:
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("test_gen | bg task ERROR | %s", result)
                        continue
                    topic_node_id, questions_data = result
                    nid_uuid = uuid.UUID(topic_node_id)
                    for q in questions_data:
                        q["_node_ids"] = [nid_uuid]
                    all_question_dicts.extend(questions_data)

            # Persist questions
            async with self._session_factory() as session:
                template = await session.get(TestTemplate, template_id)
                if not template:
                    logger.error("test_gen | bg task | template %s disappeared", template_id)
                    return

                idx = 0
                total_marks = 0
                for q in all_question_dicts:
                    q_node_ids = q.pop("_node_ids", None) or ([expanded[0]] if expanded else [])
                    first_nid = q_node_ids[0] if q_node_ids else (expanded[0] if expanded else None)
                    tq = TestQuestion(
                        template_id=template.id,
                        node_ids=q_node_ids,
                        item_id=_compute_item_id(first_nid, q.get("question", "")),
                        index=idx,
                        type=q.get("type", "mcq"),
                        question=q.get("question", ""),
                        options=q.get("options"),
                        correct_option_index=q.get("correct_option_index"),
                        model_answer=q.get("model_answer", ""),
                        mark_scheme=q.get("mark_scheme"),
                        hint=q.get("hint"),
                        points=1 if q.get("type") == "mcq" else min(q.get("points", 1), 25),
                        sources=q.get("sources"),
                        context=q.get("context"),
                    )
                    session.add(tq)
                    total_marks += tq.points
                    idx += 1

                template.total_marks = total_marks
                template.total_questions = idx
                template.status = "ready"
                template.generation_progress = None
                template.generation_task_id = None
                template_name = template.name  # capture before session closes
                await session.commit()

            logger.info(
                "test_gen | bg complete | template_id=%s questions=%d marks=%d elapsed=%.1fs",
                template_id, idx, total_marks, time.monotonic() - gen_t0,
            )
            self._notify_subscribers(template_id, {
                "event": "complete",
                "template_id": str(template_id),
                "total_questions": idx,
                "total_marks": total_marks,
                "name": template_name,
            })

        except asyncio.CancelledError:
            logger.info("test_gen | bg cancelled | template_id=%s", template_id)
            async with self._session_factory() as session:
                # Delete partial questions
                await session.execute(
                    TestQuestion.__table__.delete().where(
                        TestQuestion.__table__.c.template_id == template_id
                    )
                )
                template = await session.get(TestTemplate, template_id)
                if template:
                    template.status = "failed"
                    template.generation_progress = {"nodes": {}, "error": "Cancelled by user"}
                    template.generation_task_id = None
                await session.commit()
            self._notify_subscribers(template_id, {
                "event": "error",
                "message": "Cancelled by user",
            })

        except Exception as exc:
            logger.exception("test_gen | bg FAILED | template_id=%s: %s", template_id, exc)
            async with self._session_factory() as session:
                await session.execute(
                    TestQuestion.__table__.delete().where(
                        TestQuestion.__table__.c.template_id == template_id
                    )
                )
                template = await session.get(TestTemplate, template_id)
                if template:
                    template.status = "failed"
                    template.generation_progress = {"nodes": {}, "error": str(exc)[:500]}
                    template.generation_task_id = None
                await session.commit()
            self._notify_subscribers(template_id, {
                "event": "error",
                "message": str(exc)[:500],
            })

    # ── Push-based SSE subscriber management ────────────────────────

    def subscribe_progress(self, template_id: uuid.UUID) -> asyncio.Queue:
        """Subscribe to progress updates for a template. Returns a queue."""
        q: asyncio.Queue = asyncio.Queue()
        self._progress_subscribers.setdefault(template_id, []).append(q)
        return q

    def unsubscribe_progress(self, template_id: uuid.UUID, q: asyncio.Queue) -> None:
        """Unsubscribe from progress updates."""
        subs = self._progress_subscribers.get(template_id)
        if subs:
            try:
                subs.remove(q)
            except ValueError:
                pass
            if not subs:
                del self._progress_subscribers[template_id]

    def _notify_subscribers(self, template_id: uuid.UUID, event: dict) -> None:
        """Push an event to all subscribers for a template (non-blocking)."""
        for q in self._progress_subscribers.get(template_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # subscriber is slow, skip

    async def _update_generation_progress(
        self,
        template_id: uuid.UUID,
        progress_key: str,
    ) -> None:
        """Increment the generated count for a node/type in generation_progress."""
        async with self._session_factory() as session:
            template = await session.get(TestTemplate, template_id)
            if not template or not template.generation_progress:
                return
            progress = dict(template.generation_progress)
            nodes = dict(progress.get("nodes", {}))
            if progress_key in nodes:
                entry = dict(nodes[progress_key])
                entry["generated"] = min(
                    entry.get("generated", 0) + 1,
                    entry.get("total", 0),
                )
                nodes[progress_key] = entry
            progress["nodes"] = nodes
            template.generation_progress = progress
            await session.commit()

        # Push to SSE subscribers
        self._notify_subscribers(template_id, {
            "event": "progress",
            "nodes": nodes,
        })

    async def cancel_generation(
        self,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Cancel an in-progress generation task. Returns True if cancelled."""
        async with self._session_factory() as session:
            template = await session.get(TestTemplate, template_id)
            if not template or template.user_id != user_id:
                return False
            if template.status != "processing":
                return False

        task = self._active_tasks.get(template_id)
        if task and not task.done():
            task.cancel()
            # The CancelledError handler in _run_generation_task will clean up
            return True

        # Task not found (e.g. server restart) — mark failed directly
        async with self._session_factory() as session:
            template = await session.get(TestTemplate, template_id)
            if template and template.status == "processing":
                await session.execute(
                    TestQuestion.__table__.delete().where(
                        TestQuestion.__table__.c.template_id == template_id
                    )
                )
                template.status = "failed"
                template.generation_progress = {"nodes": {}, "error": "Cancelled by user"}
                template.generation_task_id = None
                await session.commit()
        return True

    async def retry_generation(
        self,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TestTemplate:
        """Retry generation for a failed template. Returns the updated template."""
        async with self._session_factory() as session:
            template = await session.get(TestTemplate, template_id)
            if not template or template.user_id != user_id:
                raise TemplateServiceError("Template not found")
            if template.status != "failed":
                raise TemplateServiceError("Only failed templates can be retried")

            # Delete old partial questions
            await session.execute(
                TestQuestion.__table__.delete().where(
                    TestQuestion.__table__.c.template_id == template_id
                )
            )

            # Rebuild topics from stored node_ids
            expanded = template.node_ids or []
            if not expanded:
                raise TemplateServiceError("Template has no node_ids to retry")

            self._current_user_id = user_id
            topics = await self._build_topics(session, expanded, user_id)
            if not topics:
                raise TemplateServiceError(
                    "No lessons with content found for the selected topics"
                )

            question_type_counts = template.question_type_counts
            total_questions = template.total_questions

            # Resolve PQG service for typed path
            pqg_service = None
            points_map = {}
            if question_type_counts:
                from src.files.models import Folder
                folder_obj = await session.get(Folder, template.folder_id)
                pqg_service = folder_obj.pqg_service if folder_obj else None

                if not pqg_service:
                    raise TemplateServiceError(
                        "This folder does not support typed question generation"
                    )

                import json as _json
                qt_json = self._pm.get(pqg_service, "_question_types")
                qt_list = _json.loads(qt_json)
                points_map = {qt["key"]: qt["points"] for qt in qt_list}

            # Re-allocate
            if question_type_counts:
                allocations = await self._allocate_questions_unified(
                    question_type_counts, topics,
                    pqg_service=pqg_service,
                )
            else:
                allocations = await self._allocate_questions(topics, total_questions)

            # Rebuild initial progress
            initial_progress: dict[str, dict] = {}
            if question_type_counts:
                for type_key, count in question_type_counts.items():
                    if count > 0:
                        initial_progress[type_key] = {"generated": 0, "total": count}
            else:
                for alloc in allocations:
                    nid = alloc["node_id"]
                    count = alloc["count"]
                    topic = next((t for t in topics if t["node_id"] == nid), None)
                    if topic and count > 0:
                        initial_progress[topic["name"]] = {"generated": 0, "total": count}

            task_id = str(uuid.uuid4())
            template.status = "processing"
            template.generation_progress = {"nodes": initial_progress, "error": None}
            template.generation_task_id = task_id
            await session.commit()
            await session.refresh(template)

        # Launch background task
        bg_task = asyncio.create_task(
            self._run_generation_task(
                template_id=template.id,
                user_id=user_id,
                expanded=expanded,
                topics=topics,
                allocations=allocations,
                question_type_counts=question_type_counts,
                total_questions=total_questions,
                pqg_service=pqg_service,
                points_map=points_map,
            ),
            name=f"gen-retry-{template.id}",
        )
        self._active_tasks[template.id] = bg_task
        bg_task.add_done_callback(
            lambda _t, _tid=template.id: self._active_tasks.pop(_tid, None)
        )

        return template

    async def mark_stale_templates(
        self,
        folder_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> int:
        """Mark processing templates older than 15 min as failed. Returns count."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        async with self._session_factory() as session:
            result = await session.scalars(
                select(TestTemplate).where(
                    TestTemplate.folder_id == folder_id,
                    TestTemplate.user_id == user_id,
                    TestTemplate.status == "processing",
                    TestTemplate.created_at < cutoff,
                )
            )
            stale = list(result)
            for template in stale:
                template.status = "failed"
                template.generation_progress = {"nodes": {}, "error": "Generation timed out"}
                template.generation_task_id = None
            if stale:
                await session.commit()
            return len(stale)

    # ── Allocation ─────────────────────────────────────────────────────

    async def _allocate_questions(
        self,
        topics: list[dict],
        total_questions: int,
    ) -> list[dict]:
        """LLM-driven allocation of questions per topic based on mastery."""
        if len(topics) == 1:
            return [{"node_id": topics[0]["node_id"], "count": total_questions}]

        messages = build_allocation_messages(total_questions, topics, pm=self._pm)
        try:
            raw, _usage = await self._llm.chat_complete(messages)
            if self._usage_service and hasattr(self, '_current_user_id'):
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="test_gen", usage=_usage,
                )
            data = _parse_json_response(raw)
            allocations = (
                data.get("allocations", []) if isinstance(data, dict) else data
            )

            alloc_map = {}
            for a in allocations:
                nid = a.get("node_id", "")
                count = max(0, int(a.get("count", 0)))
                alloc_map[nid] = count

            current = sum(alloc_map.values())
            if current != total_questions:
                factor = total_questions / max(current, 1)
                for k in alloc_map:
                    alloc_map[k] = max(0, round(alloc_map[k] * factor))
                diff = total_questions - sum(alloc_map.values())
                if diff != 0:
                    largest = max(alloc_map, key=alloc_map.get)
                    alloc_map[largest] = max(0, alloc_map[largest] + diff)

            return [{"node_id": k, "count": v} for k, v in alloc_map.items()]

        except Exception as exc:
            logger.warning("LLM allocation failed, falling back to uniform: %s", exc)
            return self._uniform_allocation(topics, total_questions)

    def _uniform_allocation(
        self, topics: list[dict], total_questions: int
    ) -> list[dict]:
        base = total_questions // len(topics)
        remainder = total_questions - base * len(topics)
        result = []
        for i, t in enumerate(topics):
            extra = 1 if i < remainder else 0
            result.append({"node_id": t["node_id"], "count": base + extra})
        return result

    async def _allocate_questions_unified(
        self,
        question_type_counts: dict[str, int],
        topics: list[dict],
        pqg_service: str | None = None,
    ) -> list[dict]:
        """Unified type-aware allocation: returns [{type, node_ids, index}, ...]."""
        valid_counts = {
            k: v for k, v in question_type_counts.items()
            if v > 0
        }
        if not valid_counts:
            return []

        if len(topics) == 1:
            result = []
            for type_key, count in valid_counts.items():
                for i in range(count):
                    result.append({
                        "type": type_key,
                        "node_ids": [topics[0]["node_id"]],
                        "index": i,
                    })
            return result

        # Build allocation messages — prefer PQG service prompts if available
        if pqg_service and self._pm:
            alloc_system = self._pm.get_or_none(pqg_service, "allocation_system")
            alloc_user = self._pm.get_or_none(pqg_service, "allocation_user_template")
            if alloc_system and alloc_user:
                question_types_list = "\n".join(
                    f"- {type_key}: {count} question(s)"
                    for type_key, count in valid_counts.items()
                )
                topics_list = "\n".join(
                    f'- node_id: "{t["node_id"]}", topic: "{t["name"]}", '
                    f'parent_theme: "{t["parent_name"]}", mastery: {t["progress"]}%, '
                    f'preview: "{t["content_summary"]}"'
                    for t in topics
                )
                messages = [
                    {"role": "system", "content": alloc_system},
                    {"role": "user", "content": alloc_user.format(
                        question_types_list=question_types_list,
                        topics_list=topics_list,
                    )},
                ]
            else:
                # Fallback to generic allocation
                messages = build_allocation_messages(
                    sum(valid_counts.values()), topics, pm=self._pm
                )
        else:
            messages = build_allocation_messages(
                sum(valid_counts.values()), topics, pm=self._pm
            )
        try:
            raw, _usage = await self._llm.chat_complete(messages)
            if self._usage_service and hasattr(self, "_current_user_id"):
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="test_gen", usage=_usage,
                )
            data = _parse_json_response(raw)
            if isinstance(data, dict):
                data = data.get("assignments", data.get("allocations", []))

            valid_node_ids = {t["node_id"] for t in topics}
            type_counts_seen: dict[str, int] = {}
            validated = []
            for item in data:
                t = item.get("type", "")
                nids = item.get("node_ids", [])
                if t not in valid_counts:
                    continue
                nids = [n for n in nids if n in valid_node_ids]
                if not nids:
                    continue
                if t not in ("fifteen_mark", "twenty_five_mark"):
                    nids = nids[:1]
                type_counts_seen[t] = type_counts_seen.get(t, 0) + 1
                if type_counts_seen[t] <= valid_counts[t]:
                    validated.append({
                        "type": t,
                        "node_ids": nids,
                        "index": type_counts_seen[t] - 1,
                    })

            for type_key, expected in valid_counts.items():
                actual = type_counts_seen.get(type_key, 0)
                if actual < expected:
                    sorted_topics = sorted(topics, key=lambda t: t["progress"])
                    for i in range(expected - actual):
                        topic = sorted_topics[i % len(sorted_topics)]
                        validated.append({
                            "type": type_key,
                            "node_ids": [topic["node_id"]],
                            "index": actual + i,
                        })

            return validated

        except Exception as exc:
            logger.warning("Unified allocation failed, falling back to round-robin: %s", exc)
            return self._uniform_allocation_unified(valid_counts, topics)

    def _uniform_allocation_unified(
        self,
        question_type_counts: dict[str, int],
        topics: list[dict],
    ) -> list[dict]:
        """Round-robin fallback for unified allocation."""
        sorted_topics = sorted(topics, key=lambda t: t["progress"])
        result = []
        idx = 0
        for type_key, count in question_type_counts.items():
            if count <= 0:
                continue
            for i in range(count):
                topic = sorted_topics[idx % len(sorted_topics)]
                result.append({
                    "type": type_key,
                    "node_ids": [topic["node_id"]],
                    "index": i,
                })
                idx += 1
        return result

    async def _generate_questions_for_topic(
        self,
        topic_name: str,
        lesson_content: str,
        count: int,
    ) -> tuple[str, list[dict]]:
        max_content = 12000
        if len(lesson_content) > max_content:
            lesson_content = (
                lesson_content[:max_content] + "\n\n[...content truncated...]"
            )

        messages = build_generation_messages(topic_name, lesson_content, count, pm=self._pm)
        raw, _usage = await self._llm.chat_complete(messages)
        if self._usage_service and hasattr(self, '_current_user_id'):
            self._usage_service.log_usage_fire_and_forget(
                user_id=self._current_user_id, feature="test_gen", usage=_usage,
            )
        questions = _parse_json_response(raw)

        if not isinstance(questions, list):
            raise TemplateServiceError(
                f"Expected list of questions, got {type(questions)}"
            )

        return topic_name, questions

    async def _gen_for_topic_with_id(
        self, node_id: str, topic_name: str, lesson_content: str, count: int
    ) -> tuple[str, list[dict]]:
        _, questions = await self._generate_questions_for_topic(
            topic_name, lesson_content, count
        )
        return node_id, questions

    def _auto_name(self, topics: list[dict]) -> str:
        names = [t["name"] for t in topics[:3]]
        suffix = f" +{len(topics) - 3} more" if len(topics) > 3 else ""
        return f"Practice: {', '.join(names)}{suffix}"

    # ── Reads ───────────────────────────────────────────────────────────

    async def get_template(
        self, template_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> TestTemplate | None:
        async with self._session_factory() as session:
            template = await session.get(
                TestTemplate,
                template_id,
                options=[selectinload(TestTemplate.questions)],
            )
            if not template:
                return None
            # Allow access to shared templates (user_id=None) or own templates
            if template.user_id is not None and template.user_id != user_id:
                return None
            return template

    async def list_templates(
        self,
        folder_id: uuid.UUID,
        user_id: uuid.UUID,
        template_type: str | None = None,
    ) -> list[TestTemplate]:
        async with self._session_factory() as session:
            stmt = (
                select(TestTemplate)
                .where(
                    TestTemplate.folder_id == folder_id,
                    (TestTemplate.user_id == user_id)
                    | (TestTemplate.user_id.is_(None)),
                )
                .order_by(TestTemplate.created_at.desc())
            )
            if template_type:
                stmt = stmt.where(TestTemplate.type == template_type)
            result = await session.scalars(stmt)
            return list(result)

    async def has_lesson_template(self, lesson_id: uuid.UUID) -> bool:
        async with self._session_factory() as session:
            exists = await session.scalar(
                select(TestTemplate.id)
                .where(
                    TestTemplate.lesson_id == lesson_id,
                    TestTemplate.user_id.is_(None),
                    TestTemplate.type == "lesson_test",
                )
                .limit(1)
            )
            return exists is not None

    async def get_lesson_template_id(self, lesson_id: uuid.UUID) -> uuid.UUID | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(TestTemplate.id)
                .where(
                    TestTemplate.lesson_id == lesson_id,
                    TestTemplate.user_id.is_(None),
                    TestTemplate.type == "lesson_test",
                )
                .limit(1)
            )

    async def delete_template(self, template_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        async with self._session_factory() as session:
            template = await session.get(TestTemplate, template_id)
            if not template or template.user_id != user_id:
                return False
            await session.delete(template)
            await session.commit()
            return True
