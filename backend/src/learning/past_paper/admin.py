from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path as FastAPIPath,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_container, get_db, require_admin_secret
from src.learning.image_rewrite import rewrite_image_urls_to_presigned
from src.learning.past_paper import service as pp_svc
from src.learning.past_paper.admin_library import ADMIN_LIBRARY_FOLDER_ID
from src.learning.tests.models import TestQuestion, TestTemplate
from src.runtime import AppContainer


_logger = logging.getLogger(__name__)
_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(
    prefix="/admin/past-papers",
    tags=["admin"],
    dependencies=[Depends(require_admin_secret)],
    include_in_schema=False,
)

# Strong refs to background upload tasks so they are not GC'd mid-run.
_UPLOAD_TASKS: set[asyncio.Task[None]] = set()

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/static/style.css", include_in_schema=False)
async def serve_css() -> FileResponse:
    return FileResponse(_TEMPLATES_DIR / "style.css", media_type="text/css")


@router.get("")
async def list_page(request: Request, db: DbDep):
    rows = (
        await db.execute(
            select(TestTemplate)
            .where(
                TestTemplate.user_id.is_(None),
                TestTemplate.folder_id == ADMIN_LIBRARY_FOLDER_ID,
                TestTemplate.type == "past_paper",
            )
            .order_by(TestTemplate.created_at.desc())
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "list.html",
        {"title": "Past Papers", "papers": rows},
    )


@router.get("/new")
async def new_page(request: Request):
    return templates.TemplateResponse(request, "new.html", {"title": "Upload"})


@router.post("")
async def upload_form(
    request: Request,
    name: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
    mark_scheme_file: Annotated[UploadFile | None, File()] = None,
    container: AppContainer = Depends(get_container),
):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF files are accepted",
        )
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    mark_scheme_bytes: bytes | None = None
    if mark_scheme_file is not None and mark_scheme_file.filename:
        if mark_scheme_file.content_type != "application/pdf":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Mark scheme must be a PDF file",
            )
        mark_scheme_bytes = await mark_scheme_file.read() or None

    async def _bg() -> None:
        try:
            async for _ in pp_svc.upload_and_process_streaming(
                session_factory=container.session_factory,
                user_id=None,
                pdf_bytes=pdf_bytes,
                name=name.strip(),
                original_filename=file.filename or "",
                folder_id=ADMIN_LIBRARY_FOLDER_ID,
                mark_scheme_bytes=mark_scheme_bytes,
                mark_scheme_filename=(
                    mark_scheme_file.filename if mark_scheme_file else None
                ),
                usage_service=getattr(request.app.state, "usage_service", None),
                s3=container.s3,
                prompt_manager=container.prompt_manager,
            ):
                pass  # admin upload is fire-and-forget
        except Exception as exc:
            _logger.error("admin past-paper upload failed: %s", exc, exc_info=True)

    task = asyncio.create_task(_bg())
    _UPLOAD_TASKS.add(task)
    task.add_done_callback(_UPLOAD_TASKS.discard)

    return RedirectResponse("/admin/past-papers", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{paper_id}")
async def detail_page(
    request: Request,
    paper_id: uuid.UUID,
    db: DbDep,
    container: AppContainer = Depends(get_container),
):
    paper = await pp_svc.get_past_paper(db, None, paper_id)
    if paper is None or paper.folder_id != ADMIN_LIBRARY_FOLDER_ID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")

    questions = []
    for q in paper.questions:
        ctx = await rewrite_image_urls_to_presigned(q.context, container.s3) or ""
        qtext = await rewrite_image_urls_to_presigned(q.question, container.s3) or ""
        ms = await rewrite_image_urls_to_presigned(q.mark_scheme, container.s3)
        questions.append(
            {
                "id": q.id,
                "question_number": q.question_number,
                "question": qtext,
                "question_raw": q.question or "",
                "options": q.options,
                "mark_scheme": ms,
                "mark_scheme_raw": q.mark_scheme or "",
                "context_html": ctx,
                "context_raw": q.context or "",
            }
        )
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"title": paper.name, "paper": paper, "questions": questions},
    )


@router.post("/{paper_id}/hash")
async def toggle_hash(paper_id: uuid.UUID, db: DbDep):
    paper = await db.get(TestTemplate, paper_id)
    if (
        paper is None
        or paper.user_id is not None
        or paper.folder_id != ADMIN_LIBRARY_FOLDER_ID
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    if paper.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only ready papers can be hashed"
        )
    paper.is_canonical = not paper.is_canonical
    await db.commit()
    return RedirectResponse(
        f"/admin/past-papers/{paper_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{paper_id}/questions/{question_id}/edit-question")
async def edit_question(
    paper_id: uuid.UUID,
    question_id: uuid.UUID,
    db: DbDep,
    question: Annotated[str, Form(...)] = "",
):
    paper = await db.get(TestTemplate, paper_id)
    if (
        paper is None
        or paper.user_id is not None
        or paper.folder_id != ADMIN_LIBRARY_FOLDER_ID
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    q = await db.get(TestQuestion, question_id)
    if q is None or q.template_id != paper_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    q_text = question.strip()
    if not q_text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Question text cannot be empty"
        )
    q.question = q_text
    await db.commit()
    return RedirectResponse(
        f"/admin/past-papers/{paper_id}", status_code=status.HTTP_303_SEE_OTHER
    )

@router.post("/{paper_id}/questions/{question_id}/edit-context")
async def edit_context(
    paper_id: uuid.UUID,
    question_id: uuid.UUID,
    db: DbDep,
    context: Annotated[str, Form(...)] = "",
):
    paper = await db.get(TestTemplate, paper_id)
    if (
        paper is None
        or paper.user_id is not None
        or paper.folder_id != ADMIN_LIBRARY_FOLDER_ID
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    q = await db.get(TestQuestion, question_id)
    if q is None or q.template_id != paper_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    q_context = context.strip() or None
    q.context = q_context
    await db.commit()
    return RedirectResponse(
        f"/admin/past-papers/{paper_id}", status_code=status.HTTP_303_SEE_OTHER
    )

@router.post("/{paper_id}/questions/{question_id}/edit-mark-scheme")
async def edit_mark_scheme(
    paper_id: uuid.UUID,
    question_id: uuid.UUID,
    db: DbDep,
    mark_scheme: Annotated[str, Form(...)] = "",
):
    paper = await db.get(TestTemplate, paper_id)
    if (
        paper is None
        or paper.user_id is not None
        or paper.folder_id != ADMIN_LIBRARY_FOLDER_ID
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    q = await db.get(TestQuestion, question_id)
    if q is None or q.template_id != paper_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    q_mark_scheme = mark_scheme.strip() or None
    q.mark_scheme = q_mark_scheme
    await db.commit()
    return RedirectResponse(
        f"/admin/past-papers/{paper_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{paper_id}/delete")
async def delete_form(
    paper_id: uuid.UUID,
    db: DbDep,
    container: AppContainer = Depends(get_container),
):
    try:
        await pp_svc.delete_past_paper(db, None, paper_id, s3=container.s3)
    except pp_svc.PastPaperError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RedirectResponse("/admin/past-papers", status_code=status.HTTP_303_SEE_OTHER)


_STATUS_STREAM_POLL_SECONDS = 1.5
_STATUS_STREAM_MAX_DURATION_SECONDS = 600  # safety cap


def _sse_message(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/{paper_id}/status-stream")
async def status_stream(
    paper_id: uuid.UUID,
    container: AppContainer = Depends(get_container),
) -> StreamingResponse:
    """SSE stream of {status, processing_phase} for an admin-library past paper.

    Emits an event on every change and a final ``end`` event when the paper
    reaches a terminal status (``ready`` or ``failed``). Closes after the
    safety cap if the paper is still ``processing`` — clients are expected
    to reconnect.
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        last_payload: dict[str, object] | None = None
        elapsed = 0.0
        yield "event: heartbeat\ndata: {}\n\n"
        while elapsed < _STATUS_STREAM_MAX_DURATION_SECONDS:
            async with container.session_factory() as db:
                paper = await db.get(TestTemplate, paper_id)
            if (
                paper is None
                or paper.user_id is not None
                or paper.folder_id != ADMIN_LIBRARY_FOLDER_ID
            ):
                yield _sse_message("error", {"message": "not found"})
                return

            payload: dict[str, object] = {
                "status": paper.status,
                "processing_phase": paper.processing_phase,
                "total_questions": paper.total_questions,
                "is_canonical": paper.is_canonical,
            }
            if payload != last_payload:
                yield _sse_message("status", payload)
                last_payload = payload

            if paper.status in ("ready", "failed"):
                yield _sse_message("end", payload)
                return

            await asyncio.sleep(_STATUS_STREAM_POLL_SECONDS)
            elapsed += _STATUS_STREAM_POLL_SECONDS

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _require_valid_asset_type(request: Request) -> str:
    asset_type = request.path_params.get("asset_type", "")
    if asset_type not in {"images", "tables"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invalid asset type")
    return asset_type


@router.get("/{paper_id}/assets/{asset_type}/{filename}")
async def serve_asset(
    request: Request,
    paper_id: uuid.UUID,
    filename: str,
    asset_type: str = Depends(_require_valid_asset_type),
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        data, content_type = await pp_svc.serve_asset(
            container.s3, paper_id, asset_type, filename
        )
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
