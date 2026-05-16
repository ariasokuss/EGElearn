# """Test template + session API endpoints."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from types import SimpleNamespace
from typing import Any, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request as FastAPIRequest, status
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_container, get_db
from src.activity.service import ActivityEventInput, log_activity_from_request
from src.learning.image_rewrite import rewrite_image_urls_to_presigned
from src.auth.models import User
from src.chat.entities import Message, MessageRole
from src.chat.interfaces import ChatRepository
from src.chat.practice_scope import resolve_practice_scope_params
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.tests.hint_service import stream_practice_hint_events
from src.learning.tests.prompts import PRACTICE_HINT_USER_CHAT_MESSAGE
from src.learning.tests.activity_replay import (
    answer_replay_payload,
    hint_used_replay_payload,
    question_skipped_replay_payload,
    submit_session_replay_payload,
    test_started_replay_payload,
)
from src.learning.tests.schemas import (
    CheckAnswerOut,
    DiagramAnswerRequest,
    DiagramUploadUrlOut,
    FeedbackItemOut,
    GenerateStartedOut,
    GenerateTemplateRequest,
    InlineAnswerEntry,
    InlineQuestionMapEntry,
    InlineSessionOut,
    PracticeHintRequest,
    QuestionResultOut,
    QuestionTypeOut,
    QuestionWithAnswerOut,
    SaveAnswerRequest,
    SessionAnswerOut,
    SessionDetailOut,
    SessionFeedbackOut,
    SessionResultsOut,
    SkipQuestionRequest,
    StartSessionRequest,
    SubmitSessionRequest,
    TemplateDetailOut,
    TestQuestionOut,
    TestSessionOut,
    TestStatusOut,
    TestTemplateOut,
)
from src.learning.tests.models import TestQuestion, TestSession, TestTemplate
from src.learning.tests.session_service import SessionServiceError, TestSessionService
from src.learning.tests.template_service import (
    TemplateServiceError,
    TestTemplateService,
)
from src.runtime import AppContainer

router = APIRouter(prefix="/tests", tags=["tests"])


class _LazyYandexGPTLLMGateway:
    def __init__(self) -> None:
        self._gateway: YandexGPTLLMGateway | None = None

    def _get_gateway(self) -> YandexGPTLLMGateway:
        if self._gateway is None:
            self._gateway = YandexGPTLLMGateway()
        return self._gateway

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_gateway(), name)


def _session_questions_with_progress(
    test_session: TestSession,
) -> tuple[list[QuestionWithAnswerOut], list[uuid.UUID], list[uuid.UUID]]:
    """Merge template questions with saved answers; hide solutions until question is graded."""
    answer_map = {a.question_id: a for a in test_session.answers}
    q_index = {q.id: q.index for q in test_session.template.questions}
    hint_at: dict[uuid.UUID, Any] = {
        h.question_id: h.consumed_at for h in (test_session.ai_hint_usages or [])
    }
    graded_question_ids = sorted(
        (
            a.question_id
            for a in test_session.answers
            if a.graded_at is not None
        ),
        key=lambda qid: q_index.get(qid, 0),
    )
    hint_used_question_ids = sorted(
        hint_at.keys(),
        key=lambda qid: q_index.get(qid, 0),
    )
    reveal_all = test_session.status in ("graded", "grading", "completed")
    questions: list[QuestionWithAnswerOut] = []
    for q in test_session.template.questions:
        ua = answer_map.get(q.id)
        if reveal_all:
            questions.append(
                QuestionWithAnswerOut(
                    id=q.id,
                    index=q.index,
                    type=q.type,
                    question=q.question,
                    options=q.options,
                    hint=q.hint,
                    points=q.points,
                    context=q.context,
                    node_ids=q.node_ids,
                    is_unsupported=q.is_unsupported,
                    question_number=q.question_number,
                    model_answer=q.model_answer,
                    mark_scheme=q.mark_scheme,
                    correct_option_index=q.correct_option_index,
                    user_answer=ua.answer if ua else None,
                    is_correct=ua.is_correct if ua else None,
                    score=ua.score if ua else None,
                    earned_marks=ua.earned_marks if ua else None,
                    feedback=ua.feedback if ua else None,
                    recommendations=ua.recommendations if ua else None,
                    ai_hint_used_at=hint_at.get(q.id),
                )
            )
        else:
            reveal = ua is not None and ua.graded_at is not None
            questions.append(
                QuestionWithAnswerOut(
                    id=q.id,
                    index=q.index,
                    type=q.type,
                    question=q.question,
                    options=q.options,
                    hint=q.hint,
                    points=q.points,
                    context=q.context,
                    node_ids=q.node_ids,
                    is_unsupported=q.is_unsupported,
                    question_number=q.question_number,
                    model_answer=q.model_answer if reveal else None,
                    mark_scheme=q.mark_scheme if reveal else None,
                    correct_option_index=q.correct_option_index if reveal else None,
                    user_answer=ua.answer if ua else None,
                    is_correct=ua.is_correct if reveal else None,
                    score=ua.score if reveal else None,
                    earned_marks=ua.earned_marks if reveal else None,
                    feedback=ua.feedback if reveal else None,
                    recommendations=ua.recommendations if reveal else None,
                    ai_hint_used_at=hint_at.get(q.id),
                )
            )
    return questions, graded_question_ids, hint_used_question_ids


def _get_template_service(
    request: FastAPIRequest,
    container: AppContainer = Depends(get_container),
) -> TestTemplateService:
    return TestTemplateService(
        session_factory=container.session_factory,
        usage_service=getattr(request.app.state, "usage_service", None),
        prompt_manager=container.prompt_manager,
    )


def _get_session_service(
    request: FastAPIRequest,
    container: AppContainer = Depends(get_container),
) -> TestSessionService:
    return TestSessionService(
        session_factory=container.session_factory,
        usage_service=getattr(request.app.state, "usage_service", None),
        activity_service=getattr(request.app.state, "activity_service", None),
        prompt_manager=container.prompt_manager,
        s3=container.s3,
    )


def _score_percent(score: float | None) -> float | None:
    return float(score) * 100 if score is not None else None


def _answer_metadata(answer: object, question_id: uuid.UUID, answer_text: str | None = None) -> dict:
    image_keys = list(
        getattr(answer, "image_keys", None)
        or ([getattr(answer, "image_key", None)] if getattr(answer, "image_key", None) else [])
    )
    typed_answer = answer_text if answer_text is not None else getattr(answer, "answer", "")
    typed_answer_present = bool((typed_answer or "").strip())
    return {
        "question_id": str(question_id),
        "answer_length": len(answer_text or getattr(answer, "answer", "") or ""),
        "typed_answer_present": typed_answer_present,
        "is_correct": getattr(answer, "is_correct", None),
        "score_percent": _score_percent(getattr(answer, "score", None)),
        "earned_marks": getattr(answer, "earned_marks", None),
        "graded": getattr(answer, "graded_at", None) is not None,
        "used_image": bool(image_keys),
        "image_count": len(image_keys),
        "answer_content_type": (
            "text+image"
            if typed_answer_present and image_keys
            else "image"
            if image_keys
            else "text"
            if typed_answer_present
            else "empty"
        ),
    }


def _test_session_metadata(
    test_session: TestSession,
    submitted_answers: list[SubmitAnswerItem] | None = None,
) -> dict:
    answers = list(getattr(test_session, "answers", None) or [])
    questions = list(getattr(getattr(test_session, "template", None), "questions", None) or [])
    skipped_question_ids = {
        getattr(answer, "question_id", None)
        for answer in answers
        if getattr(answer, "is_skipped", False)
    }
    answered_question_ids = {
        getattr(answer, "question_id", None)
        for answer in answers
        if not getattr(answer, "is_skipped", False)
        and (
            bool((getattr(answer, "answer", "") or "").strip())
            or bool(getattr(answer, "image_key", None) or getattr(answer, "image_keys", None))
        )
    }
    for submitted_answer in submitted_answers or []:
        if submitted_answer.question_id in skipped_question_ids:
            continue
        if submitted_answer.answer.strip() or submitted_answer.image_keys:
            answered_question_ids.add(submitted_answer.question_id)
    answered_question_ids.discard(None)
    return {
        "answered_count": len(answered_question_ids),
        "skipped_count": len(skipped_question_ids),
        "total_questions": len(questions) or None,
        "earned_marks": getattr(test_session, "earned_marks", None),
        "total_marks": getattr(test_session, "total_marks", None),
        "score_percent": _score_percent(getattr(test_session, "score", None)),
        "status": getattr(test_session, "status", None),
    }


async def _inline_question_activity_context(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
) -> tuple[TestTemplate, TestQuestion] | None:
    result = await db.execute(
        select(TestSession, TestTemplate, TestQuestion)
        .join(TestTemplate, TestTemplate.id == TestSession.template_id)
        .join(TestQuestion, TestQuestion.template_id == TestTemplate.id)
        .where(
            TestSession.id == session_id,
            TestQuestion.id == question_id,
        )
    )
    row = result.first()
    if inspect.isawaitable(row):
        row = await row
    if not isinstance(row, tuple):
        row_tuple = getattr(type(row), "_tuple", None)
        if row_tuple is None:
            return None
        row = row._tuple()
    if not isinstance(row, tuple):
        row = tuple(row)
    if len(row) != 3:
        return None
    _, template, question = row
    if getattr(template, "type", None) != "inline_quiz":
        return None
    return template, question


async def _activity_question_for_answer(
    db: AsyncSession,
    question_id: uuid.UUID,
) -> TestQuestion | None:
    try:
        question = await db.get(TestQuestion, question_id)
    except Exception:
        return None
    if inspect.isawaitable(question):
        question = await question
    if getattr(question, "id", None) != question_id:
        return None
    if not isinstance(getattr(question, "question", None), str):
        return None
    return question


def _lesson_question_metadata(
    *,
    question_id: uuid.UUID,
    question_type: str | None,
    answer_text: str,
    total_marks: int | None,
    is_correct: bool | None,
    earned_marks: int | None,
    score: float | None,
) -> dict:
    return {
        "question_id": str(question_id),
        "question_type": question_type,
        "answer_length": len(answer_text or ""),
        "is_correct": is_correct,
        "earned_marks": earned_marks,
        "total_marks": total_marks,
        "score_percent": _score_percent(score),
    }


async def _log_inline_lesson_question_activity(
    *,
    db: AsyncSession,
    request: FastAPIRequest,
    current_user: CurrentUser,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    answer_text: str,
    result: object,
) -> bool:
    context = await _inline_question_activity_context(
        db,
        session_id=session_id,
        question_id=question_id,
    )
    if context is None:
        return False
    template, question = context
    result_get = (
        result.get
        if isinstance(result, dict)
        else lambda key, default=None: getattr(result, key, default)
    )
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="lesson_question_answered",
            event_group="lesson",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="inline_question",
            entity_id=question_id,
            lesson_id=getattr(template, "lesson_id", None),
            test_session_id=session_id,
            metadata=_lesson_question_metadata(
                question_id=question_id,
                question_type=getattr(question, "type", None),
                answer_text=answer_text,
                total_marks=getattr(question, "points", None)
                or result_get("total_marks"),
                is_correct=result_get("is_correct"),
                earned_marks=result_get("earned_marks"),
                score=result_get("score"),
            ),
            replay_payload=answer_replay_payload(
                question=question,
                question_id=question_id,
                answer_text=answer_text,
                result=result,
            ),
        ),
    )
    return True


async def _resolve_hint_chat_conversation_id(
    *,
    body: PracticeHintRequest,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: User,
    tests_service: TestSessionService,
    chat_repo: ChatRepository,
) -> str:
    uid = str(current_user.id)

    if body.conversation_id is not None:
        conv = await chat_repo.get_conversation(body.conversation_id)
        if conv is None or conv.user_id != uid:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        if conv.lesson_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Practice hints can only be synced to practice-scoped conversations.",
            )
        if conv.test_session_id != str(session_id) or conv.question_id != str(question_id):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Conversation does not match this test session and question.",
            )
        folder_for_scope = body.folder_id or conv.folder_id
        if folder_for_scope is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot validate practice scope: conversation has no folder_id.",
            )
        if body.folder_id is not None and conv.folder_id != body.folder_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="folder_id does not match the conversation's folder.",
            )
        await resolve_practice_scope_params(
            folder_for_scope,
            str(session_id),
            str(question_id),
            current_user,
            tests_service,
        )
        return body.conversation_id

    if body.folder_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="folder_id is required when starting a new chat thread for hints.",
        )
    await resolve_practice_scope_params(
        body.folder_id,
        str(session_id),
        str(question_id),
        current_user,
        tests_service,
    )
    return await chat_repo.create_conversation(
        user_id=uid,
        folder_id=body.folder_id,
        title=None,
        test_session_id=str(session_id),
        question_id=str(question_id),
        scope_type="practice",
    )


async def _persist_practice_hint_messages(
    chat_repo: ChatRepository,
    conversation_id: str,
    assistant_chat: str,
    hint_panel: str,
) -> None:
    assistant_msg_id = str(uuid.uuid4())

    meta: dict[str, Any] = {"practice_hint": True}
    if hint_panel:
        meta["hint_panel"] = hint_panel

    # Use proper version_index instead of hardcoded 1 to avoid duplicates
    # when multiple hints are saved to the same conversation.
    next_vi = await chat_repo.get_next_version_index(
        None, conversation_id, role=MessageRole.ASSISTANT.value
    )
    await chat_repo.save_message(
        Message(
            id=assistant_msg_id,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=assistant_chat,
            metadata=meta,
        ),
        parent_id=None,
        version_index=next_vi,
    )
    await chat_repo.append_to_active_path(conversation_id, assistant_msg_id)

    await chat_repo.touch_conversation(conversation_id)


async def _generate_title_for_new_hint_conversation(
    *,
    llm: YandexGPTLLMGateway,
    chat_repo: ChatRepository,
    conversation_id: str,
    user_id: str,
    usage_service: Any | None,
    seed_user_message: str,
) -> None:
    """LLM title for a conversation created via hint-only flow (matches chat agent behavior)."""
    from src.config import get_settings

    settings = get_settings()
    max_len = settings.chat.conversation_title_max_length

    title: str | None = None
    usage: Any = None
    try:
        title, usage = await asyncio.wait_for(
            llm.generate_title(seed_user_message),
            timeout=5.0,
        )
    except Exception:
        title = None

    if usage_service is not None and usage is not None:
        usage_service.log_usage_fire_and_forget(
            user_id=user_id,
            feature="chat_title",
            usage=usage,
        )

    if title:
        title = title.strip().strip('"').strip("'")[:max_len]
    if not title:
        fb = seed_user_message.strip().replace("\n", " ")
        title = (
            fb
            if len(fb) <= max_len
            else fb[: max_len - 3].rstrip() + "..."
        )

    try:
        if title:
            await chat_repo.update_conversation_title(conversation_id, title)
    except Exception:
        pass


# ── Template endpoints ──────────────────────────────────────────────────


@router.post(
    "/templates/generate",
    response_model=TestTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new test template from selected topics",
)
async def generate_template(
    body: GenerateTemplateRequest,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> TestTemplateOut:
    try:
        template = await service.generate_template(
            user_id=current_user.id,
            folder_id=body.folder_id,
            node_ids=body.node_ids,
            total_questions=body.total_questions,
            name=body.name,
            question_type_counts=body.question_type_counts,
        )
        return TestTemplateOut.model_validate(template)
    except TemplateServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


def _format_sse(event_name: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


@router.post(
    "/templates/generate/stream",
    response_model=GenerateStartedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start background test generation, returns template ID immediately",
)
async def generate_template_stream(
    body: GenerateTemplateRequest,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> GenerateStartedOut:
    try:
        template = await service.start_generation(
            user_id=current_user.id,
            folder_id=body.folder_id,
            node_ids=body.node_ids,
            total_questions=body.total_questions,
            name=body.name,
            question_type_counts=body.question_type_counts,
        )
        return GenerateStartedOut(
            template_id=template.id,
            name=template.name,
            status=template.status,
        )
    except TemplateServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/templates/{template_id}/progress",
    summary="SSE stream of generation progress (push-based)",
)
async def template_progress_stream(
    template_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> StreamingResponse:
    async def _fetch_initial(tid: uuid.UUID) -> dict | None:
        """Fetch template snapshot in shielded context (safe on disconnect)."""
        async with service._session_factory() as session:
            t = await session.get(TestTemplate, tid)
            if t is None:
                return None
            return {
                "status": t.status,
                "user_id": t.user_id,
                "generation_progress": t.generation_progress,
                "id": str(t.id),
                "total_questions": t.total_questions,
                "total_marks": t.total_marks,
                "name": t.name,
            }

    async def event_stream() -> AsyncIterator[str]:
        # Check initial state — template might already be done
        try:
            data = await asyncio.shield(_fetch_initial(template_id))
        except asyncio.CancelledError:
            return

        if not data or (data["user_id"] and data["user_id"] != current_user.id):
            yield _format_sse("error", {"message": "Template not found"})
            return

        if data["status"] == "ready":
            yield _format_sse("complete", {
                "event": "complete",
                "template_id": data["id"],
                "total_questions": data["total_questions"],
                "total_marks": data["total_marks"],
                "name": data["name"],
            })
            return

        if data["status"] == "failed":
            error_msg = "Generation failed"
            if data["generation_progress"] and data["generation_progress"].get("error"):
                error_msg = data["generation_progress"]["error"]
            yield _format_sse("error", {"event": "error", "message": error_msg})
            return

        if data["status"] != "processing":
            yield _format_sse("complete", {
                "event": "complete",
                "template_id": data["id"],
                "total_questions": data["total_questions"],
                "total_marks": data["total_marks"],
                "name": data["name"],
            })
            return

        # Send current progress snapshot
        yield _format_sse("progress", {
            "event": "progress",
            "nodes": (data["generation_progress"] or {}).get("nodes", {}),
        })

        # Subscribe to push updates — no DB polling
        sub_queue = service.subscribe_progress(template_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(sub_queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Keep-alive: check if template is still processing
                    try:
                        fallback = await asyncio.shield(_fetch_initial(template_id))
                    except asyncio.CancelledError:
                        return
                    if not fallback or fallback["status"] != "processing":
                        return
                    continue
                except asyncio.CancelledError:
                    return

                if event["event"] == "progress":
                    yield _format_sse("progress", event)
                elif event["event"] == "complete":
                    yield _format_sse("complete", event)
                    return
                elif event["event"] == "error":
                    yield _format_sse("error", event)
                    return
        finally:
            service.unsubscribe_progress(template_id, sub_queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/templates/{template_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel an in-progress generation",
)
async def cancel_generation(
    template_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> dict:
    success = await service.cancel_generation(template_id, current_user.id)
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found or not cancellable")
    return {"status": "cancelled"}


@router.post(
    "/templates/{template_id}/retry",
    response_model=GenerateStartedOut,
    status_code=status.HTTP_200_OK,
    summary="Retry a failed generation",
)
async def retry_generation(
    template_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> GenerateStartedOut:
    try:
        template = await service.retry_generation(template_id, current_user.id)
        return GenerateStartedOut(
            template_id=template.id,
            name=template.name,
            status=template.status,
        )
    except TemplateServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/templates",
    response_model=list[TestTemplateOut],
    summary="List test templates in a folder",
)
async def list_templates(
    folder_id: uuid.UUID,
    current_user: CurrentUser,
    type: str | None = None,
    service: TestTemplateService = Depends(_get_template_service),
) -> list[TestTemplateOut]:
    await service.mark_stale_templates(folder_id, current_user.id)
    templates = await service.list_templates(folder_id, current_user.id, type)
    return [TestTemplateOut.model_validate(t) for t in templates]


@router.get(
    "/templates/lesson/{lesson_id}/available",
    summary="Check if a pre-authored lesson test exists and return its template ID",
)
async def check_lesson_template(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> dict:
    template_id = await service.get_lesson_template_id(lesson_id)
    return {"available": template_id is not None, "template_id": str(template_id) if template_id else None}


@router.get(
    "/templates/lesson/{lesson_id}",
    summary="Get the template ID for a lesson test",
)
async def get_lesson_template_id(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> dict:
    template_id = await service.get_lesson_template_id(lesson_id)
    return {"available": template_id is not None, "template_id": str(template_id) if template_id else None}


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetailOut,
    summary="Get template with questions",
)
async def get_template(
    template_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
    container: AppContainer = Depends(get_container),
) -> TemplateDetailOut:
    template = await service.get_template(template_id, current_user.id)
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")

    template_out = TestTemplateOut.model_validate(template)
    questions = [TestQuestionOut.model_validate(q) for q in template.questions]
    for q in questions:
        q.context = await rewrite_image_urls_to_presigned(q.context, container.s3)
    return TemplateDetailOut(template=template_out, questions=questions)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a template",
)
async def delete_template(
    template_id: uuid.UUID,
    current_user: CurrentUser,
    service: TestTemplateService = Depends(_get_template_service),
) -> None:
    deleted = await service.delete_template(template_id, current_user.id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")


@router.get(
    "/question-types",
    response_model=list[QuestionTypeOut],
    summary="Get available question types for a folder",
)
async def get_question_types(
    folder_id: uuid.UUID,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> list[QuestionTypeOut]:
    """Returns question types for typed generation, or empty list if unavailable."""
    async with container.session_factory() as session:
        from src.files.models import Folder

        folder = await session.get(Folder, folder_id)
        if not folder or not folder.pqg_service:
            return []

    pm = container.prompt_manager
    qt_json = pm.get_or_none(folder.pqg_service, "_question_types")
    if not qt_json:
        return []

    types = json.loads(qt_json)
    return [QuestionTypeOut(**t) for t in types]


# ── Session endpoints ───────────────────────────────────────────────────


@router.post(
    "/sessions/start",
    response_model=SessionDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new test session",
)
async def start_session(
    body: StartSessionRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: TestSessionService = Depends(_get_session_service),
    container: AppContainer = Depends(get_container),
) -> SessionDetailOut:
    try:
        test_session, template = await service.start_session(
            user_id=current_user.id,
            template_id=body.template_id,
            mode=body.mode,
        )
        session_out = TestSessionOut.model_validate(test_session)
        session_out.template_name = template.name
        questions = [QuestionWithAnswerOut.model_validate(q) for q in template.questions]
        for q in questions:
            q.context = await rewrite_image_urls_to_presigned(q.context, container.s3)
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="test_started",
                event_group="test",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="test_session",
                entity_id=test_session.id,
                folder_id=getattr(template, "folder_id", None),
                lesson_id=getattr(template, "lesson_id", None),
                test_session_id=test_session.id,
                metadata={
                    "mode": body.mode,
                    "template_type": getattr(template, "type", None),
                    "total_questions": len(getattr(template, "questions", []) or []),
                    "total_marks": getattr(test_session, "total_marks", None),
                },
                replay_payload=test_started_replay_payload(
                    template=template,
                    test_session=test_session,
                    mode=body.mode,
                ),
            ),
        )
        return SessionDetailOut(
            session=session_out,
            template=TestTemplateOut.model_validate(template),
            questions=questions,
            answers=[],
        )
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/sessions",
    response_model=list[TestSessionOut],
    summary="List test sessions",
)
async def list_sessions(
    current_user: CurrentUser,
    template_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    type: str | None = None,
    lesson_id: uuid.UUID | None = None,
    service: TestSessionService = Depends(_get_session_service),
) -> list[TestSessionOut]:
    sessions = await service.list_sessions(
        user_id=current_user.id,
        template_id=template_id,
        folder_id=folder_id,
        type=type,
        lesson_id=lesson_id,
    )
    result = []
    for s in sessions:
        out = TestSessionOut.model_validate(s)
        if s.template:
            out.template_name = s.template.name
        result.append(out)
    return result


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailOut,
    summary="Get session detail with questions and answers",
)
async def get_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
    container: AppContainer = Depends(get_container),
) -> SessionDetailOut:
    test_session = await service.get_session(session_id, current_user.id, session=db)
    if not test_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    session_out = TestSessionOut.model_validate(test_session)
    if test_session.template:
        session_out.template_name = test_session.template.name

    template_out = TestTemplateOut.model_validate(test_session.template)
    answers_out = [SessionAnswerOut.model_validate(a) for a in test_session.answers]
    questions, graded_question_ids, hint_used_question_ids = (
        _session_questions_with_progress(test_session)
    )
    for q in questions:
        q.context = await rewrite_image_urls_to_presigned(q.context, container.s3)

    return SessionDetailOut(
        session=session_out,
        template=template_out,
        questions=questions,
        answers=answers_out,
        graded_question_ids=graded_question_ids,
        hint_used_question_ids=hint_used_question_ids,
    )



@router.get(
    "/sessions/{session_id}/results",
    response_model=SessionResultsOut,
    summary="Get test results — overall progress and per-question breakdown",
)
async def get_session_results(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
) -> SessionResultsOut:
    from sqlalchemy import select as sa_select
    from src.roadmap.models import RoadmapNode

    test_session = await service.get_session(session_id, current_user.id, session=db)
    if not test_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    if test_session.status not in ("graded", "grading", "completed"):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Results not available yet (status={test_session.status})",
        )
    if test_session.status == "grading":
        await service.grade_session(session_id)
        # Reload in a fresh session — the existing `db` session may cache stale identity-map state
        test_session = await service.get_session(session_id, current_user.id)
        if not test_session:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Batch-load node names for relation field
    all_node_ids: list[uuid.UUID] = []
    for q in test_session.template.questions:
        if q.node_ids:
            all_node_ids.extend(q.node_ids)

    node_name_map: dict[uuid.UUID, str] = {}
    if all_node_ids:
        rows = await db.execute(
            sa_select(RoadmapNode.id, RoadmapNode.name).where(
                RoadmapNode.id.in_(all_node_ids)
            )
        )
        node_name_map = {row.id: row.name for row in rows}

    answer_map = {a.question_id: a for a in test_session.answers}
    template = test_session.template

    # Batch-load part titles from lesson blocks (sources → block_id → title)
    part_title_map: dict[str, str] = {}
    if template.lesson_id:
        from src.learning.models import LessonBlock

        all_slugs: list[str] = []
        for q in template.questions:
            if q.sources:
                all_slugs.extend(q.sources)
        if all_slugs:
            rows = await db.execute(
                sa_select(LessonBlock.block_id, LessonBlock.title).where(
                    LessonBlock.lesson_id == template.lesson_id,
                    LessonBlock.block_id.in_(all_slugs),
                    LessonBlock.title.isnot(None),
                )
            )
            part_title_map = {row.block_id: row.title for row in rows}

    def _relation(q) -> str:
        if q.sources:
            title = part_title_map.get(q.sources[0])
            if title:
                return title
        if q.node_ids:
            return node_name_map.get(q.node_ids[0], template.name)
        if template.type == "past_paper":
            return template.original_filename or template.name
        return template.name

    questions = [
        QuestionResultOut(
            question=q.question,
            relation=_relation(q),
            points=answer_map[q.id].earned_marks if q.id in answer_map else None,
            max_points=q.points,
            is_skipped=(
                answer_map[q.id].is_skipped if q.id in answer_map else False
            ),
            question_number=q.question_number,
        )
        for q in template.questions
    ]

    marks = sum(
        (a.earned_marks or 0)
        for a in test_session.answers
        if a.earned_marks is not None and not a.is_skipped
    )

    return SessionResultsOut(
        marks=marks,
        total_marks=test_session.total_marks,
        mode=test_session.session_mode,
        questions=questions,
    )


@router.get(
    "/sessions/{session_id}/feedback",
    response_model=SessionFeedbackOut,
    summary="Get per-question feedback for a graded session",
)
async def get_session_feedback(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
    container: AppContainer = Depends(get_container),
) -> SessionFeedbackOut:
    test_session = await service.get_session(session_id, current_user.id, session=db)
    if not test_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    if test_session.status not in ("graded", "grading", "completed"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Feedback not available yet (status={test_session.status})",
        )

    answer_map = {a.question_id: a for a in test_session.answers}

    items = []
    for q in test_session.template.questions:
        user_ans = answer_map.get(q.id)
        image_url: str | None = None
        image_urls: list[str] = []
        if user_ans and container.s3:
            raw_keys = list(user_ans.image_keys or ([user_ans.image_key] if user_ans.image_key else []))
            seen: set[str] = set()
            all_keys: list[str] = []
            for key in raw_keys:
                if key in seen:
                    continue
                seen.add(key)
                all_keys.append(key)
            for key in all_keys:
                url = await container.s3.presigned_get_url(key, expires_in=3600)
                image_urls.append(url)
            if image_urls:
                image_url = image_urls[0]
        items.append(
            FeedbackItemOut(
                type=q.type,
                answer=user_ans.answer if user_ans else None,
                correct_option_index=q.correct_option_index,
                model_answer=q.model_answer,
                feedback=user_ans.feedback if user_ans else None,
                recommendation=user_ans.recommendations if user_ans else None,
                points=user_ans.earned_marks if user_ans else None,
                total_points=q.points,
                image_url=image_url,
                image_urls=image_urls,
                question_number=q.question_number,
            )
        )

    return SessionFeedbackOut(session_id=test_session.id, items=items)


@router.put(
    "/sessions/{session_id}/answers/{question_id}",
    response_model=SessionAnswerOut,
    summary="Auto-save a single answer",
)
async def save_answer(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: SaveAnswerRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
) -> SessionAnswerOut:
    try:
        answer = await service.save_answer(
            session_id=session_id,
            user_id=current_user.id,
            question_id=question_id,
            answer_text=body.answer,
            image_keys=body.image_keys,
            session=db,
        )
        logged_inline = await _log_inline_lesson_question_activity(
            db=db,
            request=request,
            current_user=current_user,
            session_id=session_id,
            question_id=question_id,
            answer_text=body.answer,
            result=answer,
        )
        if not logged_inline:
            question = await _activity_question_for_answer(db, question_id)
            log_activity_from_request(
                request,
                ActivityEventInput(
                    user_id=current_user.id,
                    event_type="answer_saved",
                    event_group="test",
                    request_path=request.url.path,
                    http_method=request.method,
                    entity_type="test_session",
                    entity_id=session_id,
                    test_session_id=session_id,
                    metadata=_answer_metadata(answer, question_id, body.answer),
                    replay_payload=answer_replay_payload(
                        question=question,
                        question_id=question_id,
                        answer_text=body.answer,
                        result=answer,
                    ),
                ),
            ),
        return SessionAnswerOut.model_validate(answer)
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic"})
_IMAGE_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}


@router.get(
    "/sessions/{session_id}/answers/{question_id}/diagram-upload-url",
    response_model=DiagramUploadUrlOut,
    summary="Get a presigned S3 PUT URL for uploading a diagram answer image",
)
async def get_diagram_upload_url(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: CurrentUser,
    content_type: str = Query(default="image/jpeg"),
    db: AsyncSession = Depends(get_db),
    container: AppContainer = Depends(get_container),
) -> DiagramUploadUrlOut:
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{content_type}'. Allowed: image/jpeg, image/png, image/webp, image/heic",
        )
    test_session = await db.get(TestSession, session_id)
    if not test_session or test_session.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    question = await db.get(TestQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    if question.type == "mcq":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Image attachments are not supported for MCQ questions",
        )
    ext = _IMAGE_EXT[content_type]
    image_key = f"session-answers/{session_id}/{question_id}/{uuid.uuid4()}.{ext}"
    upload_url = await container.s3.presigned_put_url(
        image_key, content_type=content_type, expires_in=900
    )
    return DiagramUploadUrlOut(upload_url=upload_url, image_key=image_key)


@router.post(
    "/sessions/{session_id}/answers/{question_id}/diagram",
    response_model=SessionAnswerOut,
    summary="Submit a diagram answer image key and trigger LLM vision grading",
)
async def submit_diagram_answer(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: DiagramAnswerRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
) -> SessionAnswerOut:
    try:
        answer = await service.save_diagram_answer(
            session_id=session_id,
            user_id=current_user.id,
            question_id=question_id,
            image_key=body.image_key,
            session=db,
        )
        background_tasks.add_task(service.grade_single_answer, session_id, question_id)
        question = await _activity_question_for_answer(db, question_id)
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="diagram_answer_submitted",
                event_group="test",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="test_session",
                entity_id=session_id,
                test_session_id=session_id,
                metadata=_answer_metadata(answer, question_id),
                replay_payload=answer_replay_payload(
                    question=question,
                    question_id=question_id,
                    answer_text=None,
                    result=answer,
                    title="Diagram answer",
                ),
            ),
        )
        return SessionAnswerOut.model_validate(answer)
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/sessions/{session_id}/answers/{question_id}/regrade",
    summary="Reset grading state and re-trigger vision grading for an image answer",
    status_code=200,
)
async def regrade_answer(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    background_tasks: BackgroundTasks,
    service: TestSessionService = Depends(_get_session_service),
) -> dict:
    try:
        await service.regrade_answer(
            session_id=session_id,
            user_id=current_user.id,
            question_id=question_id,
        )
        background_tasks.add_task(service.grade_single_answer, session_id, question_id)
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="answer_regrade_requested",
                event_group="test",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="test_session",
                entity_id=session_id,
                test_session_id=session_id,
                metadata={"question_id": str(question_id)},
                replay_payload={
                    "schema_version": 1,
                    "items": [
                        {
                            "kind": "user_action",
                            "title": "Answer regrade requested",
                            "value": "Requested answer regrade",
                        }
                    ],
                    "refs": {
                        "question_id": str(question_id),
                        "test_session_id": str(session_id),
                    },
                },
            ),
        )
        return {"ok": True}
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.put(
    "/sessions/{session_id}/answers/{question_id}/skip",
    response_model=SessionAnswerOut,
    summary="Mark a question as skipped or unskipped (excluded from totals)",
)
async def set_question_skipped(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: SkipQuestionRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
) -> SessionAnswerOut:
    try:
        answer = await service.set_question_skipped(
            session_id=session_id,
            user_id=current_user.id,
            question_id=question_id,
            skipped=body.skipped,
            session=db,
        )
        question = await _activity_question_for_answer(db, question_id)
        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="question_skipped",
                event_group="test",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="test_session",
                entity_id=session_id,
                test_session_id=session_id,
                metadata={
                    "question_id": str(question_id),
                    "skipped": body.skipped,
                    "answer_length": len(getattr(answer, "answer", "") or ""),
                },
                replay_payload=question_skipped_replay_payload(
                    question=question,
                    question_id=question_id,
                    answer=answer,
                    skipped=body.skipped,
                ),
            ),
        )
        return SessionAnswerOut.model_validate(answer)
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/sessions/{session_id}/check/{question_id}",
    response_model=CheckAnswerOut,
    summary="Check a single answer — MCQ auto-graded, short answer LLM-graded",
)
async def check_answer(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: SaveAnswerRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
) -> CheckAnswerOut:
    try:
        result = await service.check_answer(
            session_id=session_id,
            user_id=current_user.id,
            question_id=question_id,
            answer_text=body.answer,
            image_keys=body.image_keys,
        )
        logged_inline = await _log_inline_lesson_question_activity(
            db=db,
            request=request,
            current_user=current_user,
            session_id=session_id,
            question_id=question_id,
            answer_text=body.answer,
            result=result,
        )
        if not logged_inline:
            question = await _activity_question_for_answer(db, question_id)
            result_obj = SimpleNamespace(**result) if isinstance(result, dict) else result
            log_activity_from_request(
                request,
                ActivityEventInput(
                    user_id=current_user.id,
                    event_type="answer_checked",
                    event_group="test",
                    request_path=request.url.path,
                    http_method=request.method,
                    entity_type="test_session",
                    entity_id=session_id,
                    test_session_id=session_id,
                    metadata=_answer_metadata(result_obj, question_id, body.answer),
                    replay_payload=answer_replay_payload(
                        question=question,
                        question_id=question_id,
                        answer_text=body.answer,
                        result=result,
                        title="Checked answer",
                    ),
                ),
            )
        return CheckAnswerOut(**result)
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/sessions/{session_id}/hint/{question_id}",
    summary="Practice mode: stream hint (SSE) — chat line + hint panel",
    response_description=(
        "Server-Sent Events. Event types: `hint_meta`, `hint_chat_token`, "
        "`hint_panel_token`, `hint_complete` ({assistant_chat, hint_panel}), `error`. "
        "When chat sync is enabled, `hint_meta` includes `conversation_id`."
    ),
)
async def stream_practice_hint(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
    body: PracticeHintRequest = Body(default_factory=PracticeHintRequest),
) -> StreamingResponse:
    """
    Logically equivalent to a user message asking for a hint for this practice question.

    Optional chat sync (body): send `folder_id` to open a **new** practice-scoped thread, or
    `conversation_id` to append to the **current** thread (folder_id optional then).
    Omit both to skip persisting messages. On success, user + assistant rows are saved
    after the stream; assistant `content` is the short chat line, `hint_panel` is in metadata.

    SSE payload shapes:
    - `hint_meta`: `{session_id, question_id}` and `conversation_id` when syncing to chat
    - `hint_chat_token` / `hint_panel_token`: `{content}` — token chunks for two UI layers
    - `hint_complete`: `{assistant_chat, hint_panel}` — full strings when the stream ends
    - `error`: `{message, recoverable}`

    **409 Conflict** if this session+question already consumed an AI hint, or another hint
    request for the same question is still in progress (PostgreSQL advisory lock; no second LLM).
    """
    test_session = await service.get_session(session_id, current_user.id, session=db)
    if not test_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    if test_session.session_mode != "practice":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hints are only available in practice mode",
        )
    if test_session.status not in ("not_started", "active"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Hints not available for session status={test_session.status}",
        )

    question = next(
        (q for q in test_session.template.questions if q.id == question_id),
        None,
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")

    if await service.is_ai_hint_consumed(session_id, question_id, session=db):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="AI hint for this question was already used in this session.",
        )

    if not await service.try_acquire_hint_inflight_lock(db, session_id, question_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Another AI hint request for this question is already in progress.",
        )

    chat_repo: ChatRepository | None = getattr(request.app.state, "chat_repo", None)
    hint_chat_conversation_id: str | None = None
    if body.folder_id is not None or body.conversation_id is not None:
        if chat_repo is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat repository is not configured.",
            )
        hint_chat_conversation_id = await _resolve_hint_chat_conversation_id(
            body=body,
            session_id=session_id,
            question_id=question_id,
            current_user=current_user,
            tests_service=service,
            chat_repo=chat_repo,
        )

    usage_service = getattr(request.app.state, "usage_service", None)

    hint_conversation_was_created = (
        hint_chat_conversation_id is not None
        and body.folder_id is not None
        and body.conversation_id is None
    )

    async def event_stream() -> AsyncIterator[str]:
        yield ": " + (" " * 2046) + "\n\n"
        try:
            llm = _LazyYandexGPTLLMGateway()
            async for event in stream_practice_hint_events(
                user_id=current_user.id,
                session_id=session_id,
                question=question,
                template_id=test_session.template_id,
                model=body.model,
                reasoning=body.reasoning,
                llm=llm,
                usage_service=usage_service,
                chat_conversation_id=hint_chat_conversation_id,
                pm=service._pm,
            ):
                ev = event["event"]
                if ev == "hint_complete":
                    data = event["data"]
                    if hint_chat_conversation_id is not None and chat_repo is not None:
                        await _persist_practice_hint_messages(
                            chat_repo,
                            hint_chat_conversation_id,
                            data["assistant_chat"],
                            data["hint_panel"],
                        )
                        if hint_conversation_was_created:
                            await _generate_title_for_new_hint_conversation(
                                llm=llm,
                                chat_repo=chat_repo,
                                conversation_id=hint_chat_conversation_id,
                                user_id=str(current_user.id),
                                usage_service=usage_service,
                                seed_user_message=service._pm.get("tests", "practice_hint_user_chat_message") if service._pm else PRACTICE_HINT_USER_CHAT_MESSAGE,
                            )
                    await service.record_ai_hint_consumed(
                        session_id, question_id, current_user.id
                    )
                    log_activity_from_request(
                        request,
                        ActivityEventInput(
                            user_id=current_user.id,
                            event_type="hint_used",
                            event_group="test",
                            request_path=request.url.path,
                            http_method=request.method,
                            entity_type="test_session",
                            entity_id=session_id,
                            test_session_id=session_id,
                            metadata={"question_id": str(question_id)},
                            replay_payload=hint_used_replay_payload(
                                question=question,
                                question_id=question_id,
                                assistant_chat=data["assistant_chat"],
                                hint_panel=data["hint_panel"],
                                conversation_id=hint_chat_conversation_id,
                            ),
                        ),
                    )
                yield _format_sse(ev, event["data"])
                if ev in ("hint_chat_token", "hint_panel_token"):
                    await asyncio.sleep(0.05)
        except (GeneratorExit, asyncio.CancelledError):
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/sessions/{session_id}/submit",
    response_model=TestSessionOut,
    summary="Submit a session for grading",
)
async def submit_session(
    session_id: uuid.UUID,
    body: SubmitSessionRequest,
    current_user: CurrentUser,
    request: FastAPIRequest,
    background_tasks: BackgroundTasks,
    service: TestSessionService = Depends(_get_session_service),
) -> TestSessionOut:
    try:
        final_answers = (
            [
                {
                    "question_id": a.question_id,
                    "answer": a.answer,
                    "image_keys": a.image_keys,
                }
                for a in body.answers
            ]
            if body.answers
            else None
        )
        test_session, ungraded_ids = await service.submit_session(
            session_id, current_user.id, final_answers
        )

        if ungraded_ids:
            # Grade in-process to avoid queue/consumer dependency for session finalization.
            background_tasks.add_task(service.grade_session, session_id)

        log_activity_from_request(
            request,
            ActivityEventInput(
                user_id=current_user.id,
                event_type="test_submitted",
                event_group="test",
                request_path=request.url.path,
                http_method=request.method,
                entity_type="test_session",
                entity_id=session_id,
                test_session_id=session_id,
                metadata=_test_session_metadata(test_session, body.answers),
                replay_payload=submit_session_replay_payload(
                    test_session=test_session,
                    submitted_answers=body.answers,
                ),
            ),
        )
        out = TestSessionOut.model_validate(test_session)
        return out
    except SessionServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "/sessions/{session_id}/status",
    response_model=TestStatusOut,
    summary="Check session grading status",
)
async def get_session_status(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    service: TestSessionService = Depends(_get_session_service),
) -> TestStatusOut:
    result = await service.get_session_status(session_id, current_user.id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    if result.get("status") == "grading":
        background_tasks.add_task(service.grade_session, session_id)
    return TestStatusOut(**result)


@router.post(
    "/sessions/{session_id}/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Abort a session",
)
async def abort_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    service: TestSessionService = Depends(_get_session_service),
) -> None:
    aborted = await service.abort_session(session_id, current_user.id)
    if not aborted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="test_aborted",
            event_group="test",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="test_session",
            entity_id=session_id,
            test_session_id=session_id,
        ),
    )


# ── Inline quiz (lesson mini-questions) ────────────────────────────────


async def _build_inline_session_response(
    session_factory,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
) -> InlineSessionOut:
    """Find or create an inline quiz session, return bootstrap payload."""
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload
    from src.learning.tests.models import TestQuestion, TestSession, TestTemplate
    from datetime import datetime, timezone

    async with session_factory() as db:
        # 1. Find inline_quiz template for this lesson
        template = await db.scalar(
            sa_select(TestTemplate)
            .where(
                TestTemplate.lesson_id == lesson_id,
                TestTemplate.type == "inline_quiz",
                TestTemplate.status == "ready",
            )
            .options(selectinload(TestTemplate.questions))
            .limit(1)
        )
        if not template:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="No inline quiz found for this lesson",
            )

        # 2. Find existing active session or create new
        existing_session = await db.scalar(
            sa_select(TestSession)
            .where(
                TestSession.template_id == template.id,
                TestSession.user_id == user_id,
                TestSession.status.in_(["not_started", "active"]),
            )
            .options(selectinload(TestSession.answers))
            .order_by(TestSession.created_at.desc())
            .limit(1)
        )

        if existing_session:
            test_session = existing_session
        else:
            now = datetime.now(timezone.utc)
            test_session = TestSession(
                template_id=template.id,
                user_id=user_id,
                session_mode="practice",
                status="not_started",
                total_marks=template.total_marks or 0,
                created_at=now,
                updated_at=now,
            )
            db.add(test_session)
            await db.flush()
            await db.refresh(test_session, ["answers"])

        # 3. Build question_map: inline_key → {question_id, type}
        question_map: dict[str, InlineQuestionMapEntry] = {}
        question_by_id: dict[uuid.UUID, TestQuestion] = {}
        for q in template.questions:
            if q.inline_key:
                question_map[q.inline_key] = InlineQuestionMapEntry(
                    question_id=q.id,
                    type=q.type,
                )
                question_by_id[q.id] = q

        # 4. Build answers map from existing session answers
        answers: dict[str, InlineAnswerEntry] = {}
        for ans in test_session.answers:
            q = question_by_id.get(ans.question_id)
            if not q or not q.inline_key:
                continue
            answers[q.inline_key] = InlineAnswerEntry(
                answer=ans.answer,
                is_correct=ans.is_correct,
                earned_marks=ans.earned_marks,
                total_marks=q.points,
                feedback=ans.feedback,
                recommendations=ans.recommendations,
                graded_at=ans.graded_at,
            )

        await db.commit()

        return InlineSessionOut(
            session_id=test_session.id,
            question_map=question_map,
            answers=answers,
        )


@router.get(
    "/inline-session/{lesson_id}",
    response_model=InlineSessionOut,
    summary="Get or create an inline quiz session for a lesson",
)
async def get_inline_session(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> InlineSessionOut:
    return await _build_inline_session_response(
        container.session_factory,
        current_user.id,
        lesson_id,
    )


@router.post(
    "/inline-session/{lesson_id}/reset",
    response_model=InlineSessionOut,
    summary="Reset inline quiz — abort current session and create a new one",
)
async def reset_inline_session(
    lesson_id: uuid.UUID,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> InlineSessionOut:
    from sqlalchemy import select as sa_select
    from src.learning.tests.models import TestSession, TestTemplate
    from src.mastery.emitters import _get_node_id_for_lesson
    from src.mastery.service import invalidate_previous_events, recalculate_mastery

    async with container.session_factory() as db:

        # Find the template
        template = await db.scalar(
            sa_select(TestTemplate)
            .where(
                TestTemplate.lesson_id == lesson_id,
                TestTemplate.type == "inline_quiz",
                TestTemplate.status == "ready",
            )
            .limit(1)
        )
        if not template:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="No inline quiz found for this lesson",
            )

        # Abort all active sessions for this user+template
        active_sessions = list(
            await db.scalars(
                sa_select(TestSession).where(
                    TestSession.template_id == template.id,
                    TestSession.user_id == current_user.id,
                    TestSession.status.in_(["not_started", "active"]),
                )
            )
        )
        for s in active_sessions:
            s.status = "aborted"

        # Invalidate inline mastery events (stored as inline_mcq/inline_short, not inline_quiz)
        node_id = await _get_node_id_for_lesson(db, lesson_id)
        if node_id:
            await invalidate_previous_events(
                db, current_user.id, node_id, "inline_mcq"
            )
            await invalidate_previous_events(
                db, current_user.id, node_id, "inline_short"
            )
            await recalculate_mastery(db, current_user.id, node_id)

        await db.commit()

    # Create fresh session
    return await _build_inline_session_response(
        container.session_factory,
        current_user.id,
        lesson_id,
    )


# ── Save pre-generated hint as chat messages (no LLM) ───────────────────


class SaveHintRequest(BaseModel):
    folder_id: str
    conversation_id: str | None = None


@router.post(
    "/sessions/{session_id}/save-hint/{question_id}",
    status_code=status.HTTP_200_OK,
)
async def save_practice_hint(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: CurrentUser,
    request: FastAPIRequest,
    body: SaveHintRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    service: TestSessionService = Depends(_get_session_service),
) -> dict:
    """Save the pre-generated hint as a user+assistant message pair in a practice chat."""
    test_session = await service.get_session(session_id, current_user.id, session=db)
    if not test_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    if test_session.session_mode != "practice":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hints are only available in practice mode",
        )

    question = next(
        (q for q in test_session.template.questions if q.id == question_id),
        None,
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")

    hint_text = question.hint
    if not hint_text or not hint_text.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This question has no hint.",
        )

    chat_repo: ChatRepository | None = getattr(request.app.state, "chat_repo", None)
    if chat_repo is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat repository is not configured.",
        )

    hint_body = PracticeHintRequest(
        folder_id=body.folder_id,
        conversation_id=body.conversation_id,
    )
    conversation_id = await _resolve_hint_chat_conversation_id(
        body=hint_body,
        session_id=session_id,
        question_id=question_id,
        current_user=current_user,
        tests_service=service,
        chat_repo=chat_repo,
    )

    await _persist_practice_hint_messages(
        chat_repo,
        conversation_id,
        assistant_chat=hint_text.strip(),
        hint_panel="",
    )

    await chat_repo.update_conversation_title(conversation_id, "Hint")
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=current_user.id,
            event_type="hint_used",
            event_group="test",
            request_path=request.url.path,
            http_method=request.method,
            entity_type="test_session",
            entity_id=session_id,
            test_session_id=session_id,
            metadata={"question_id": str(question_id), "conversation_id": conversation_id},
            replay_payload=hint_used_replay_payload(
                question=question,
                question_id=question_id,
                assistant_chat=hint_text.strip(),
                hint_panel="",
                conversation_id=conversation_id,
            ),
        ),
    )

    return {"conversation_id": conversation_id}
