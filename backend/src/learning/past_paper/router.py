from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from enum import Enum

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_container, get_db
from src.files.models import Folder
from src.learning.image_rewrite import rewrite_image_urls_to_presigned
from src.learning.past_paper import service as pp_svc
from src.learning.tests.models import TestTemplate
from src.learning.past_paper.schemas import (
    PastPaperListOut,
    PastPaperOut,
    PastPaperStatusOut,
)
from src.runtime import AppContainer

_logger = logging.getLogger(__name__)

# Keep strong references to background upload tasks so they are not GC'd mid-run.
_UPLOAD_TASKS: set[asyncio.Task[None]] = set()

class AssetType(str, Enum):
    images = "images"
    tables = "tables"


router = APIRouter(prefix="/past-papers", tags=["past-papers"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _sse(event_name: str, data: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/upload",
    summary="Upload a PDF past paper and stream processing progress via SSE",
)
async def upload_past_paper_stream(
    request: Request,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(...)],
    name: Annotated[str, Form(...)],
    folder_id: Annotated[uuid.UUID, Form(...)],
    mark_scheme_file: Annotated[UploadFile | None, File()] = None,
    container: AppContainer = Depends(get_container),
) -> StreamingResponse:
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
    if mark_scheme_file is not None:
        if mark_scheme_file.content_type != "application/pdf":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Mark scheme must be a PDF file",
            )
        mark_scheme_bytes = await mark_scheme_file.read() or None

    # Validate folder before starting the stream
    async with container.session_factory() as db:
        folder = await db.scalar(select(Folder).where(Folder.id == folder_id))
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Folder not found")

    # Queue used to pass SSE strings from the background task to the SSE stream.
    # None is the sentinel that signals the stream is done.
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _bg() -> None:
        """Run the full upload pipeline as a detached background task.

        This task is NOT tied to the HTTP request coroutine, so it survives
        client disconnects (CancelledError never reaches it).
        """
        try:
            async for event in pp_svc.upload_and_process_streaming(
                session_factory=container.session_factory,
                user_id=current_user.id,
                pdf_bytes=pdf_bytes,
                name=name.strip(),
                original_filename=file.filename or "",
                folder_id=folder_id,
                mark_scheme_bytes=mark_scheme_bytes,
                mark_scheme_filename=mark_scheme_file.filename if mark_scheme_file else None,
                usage_service=getattr(request.app.state, "usage_service", None),
                s3=container.s3,
                prompt_manager=container.prompt_manager,
            ):
                await queue.put(_sse(event["event"], event))
        except Exception as exc:
            _logger.error(
                "upload_past_paper_stream background task failed: %s",
                exc,
                exc_info=True,
            )
            await queue.put(_sse("error", {"event": "error", "message": "Internal server error"}))
        finally:
            await queue.put(None)  # always signal end

    task = asyncio.create_task(_bg())
    _UPLOAD_TASKS.add(task)
    task.add_done_callback(_UPLOAD_TASKS.discard)

    async def event_stream() -> AsyncGenerator[str, None]:
        """Read SSE events from the queue. Closes cleanly on client disconnect
        while the background task keeps running.

        One persistent getter task is created and reused across heartbeat timeouts.
        This avoids the bug where asyncio.shield(queue.get()) in a loop spawns
        multiple competing getters that silently consume events.
        """
        yield "event: heartbeat\ndata: {}\n\n"
        getter: asyncio.Task[str | None] = asyncio.ensure_future(queue.get())
        try:
            while True:
                done, _ = await asyncio.wait({getter}, timeout=30.0)
                if not done:
                    # Timeout — send heartbeat but keep the same getter alive
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue
                item = getter.result()
                if item is None:
                    break
                yield item
                getter = asyncio.ensure_future(queue.get())
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected — background task continues independently.
            getter.cancel()
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "",
    response_model=list[PastPaperListOut],
    summary="List past papers for the current user",
)
async def list_past_papers(
    db: DbDep,
    current_user: CurrentUser,
    response: Response,
    folder_id: uuid.UUID | None = None,
) -> list[PastPaperListOut]:
    papers = await pp_svc.list_past_papers(db, current_user.id, folder_id)
    response.headers["Cache-Control"] = "no-store"
    return [PastPaperListOut.model_validate(p) for p in papers]


@router.get(
    "/{past_paper_id}/assets/{asset_type}/{filename}",
    summary="Serve a past paper asset (image or table) from S3",
)
async def get_past_paper_asset(
    past_paper_id: uuid.UUID,
    asset_type: AssetType,
    filename: str,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        data, content_type = await pp_svc.serve_asset(
            container.s3, past_paper_id, asset_type.value, filename
        )
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get(
    "/{past_paper_id}/pdf",
    summary="Redirect to a presigned S3 URL for the past paper PDF",
)
async def download_past_paper_pdf(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> RedirectResponse:
    paper = await pp_svc.get_past_paper(db, current_user.id, past_paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    s3_key = f"past-papers/{past_paper_id}/origin/paper.pdf"
    url = await container.s3.presigned_get_url(
        s3_key,
        expires_in=3600,
        filename=paper.original_filename or "past-paper.pdf",
    )
    return RedirectResponse(url=url, status_code=302)


@router.get(
    "/{past_paper_id}/mark-scheme/pdf",
    summary="Redirect to a presigned S3 URL for the mark scheme PDF",
)
async def download_mark_scheme_pdf(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> RedirectResponse:
    paper = await pp_svc.get_past_paper(db, current_user.id, past_paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    s3_key = f"past-papers/{past_paper_id}/origin/mark-scheme.pdf"
    url = await container.s3.presigned_get_url(
        s3_key,
        expires_in=3600,
        filename=paper.mark_scheme_filename or "mark-scheme.pdf",
    )
    return RedirectResponse(url=url, status_code=302)


@router.get(
    "/{past_paper_id}",
    response_model=PastPaperOut,
    summary="Get a single past paper with its questions",
)
async def get_past_paper(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> PastPaperOut:
    paper = await pp_svc.get_past_paper(db, current_user.id, past_paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    out = PastPaperOut.model_validate(paper)
    for q in out.questions:
        q.context = await rewrite_image_urls_to_presigned(q.context, container.s3)
    return out


@router.get(
    "/{past_paper_id}/status",
    response_model=PastPaperStatusOut,
    summary="Get current processing status and phase of a past paper",
)
async def get_past_paper_status(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> PastPaperStatusOut:
    row = await db.scalar(
        select(TestTemplate).where(
            TestTemplate.id == past_paper_id,
            TestTemplate.user_id == current_user.id,
            TestTemplate.type == "past_paper",
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Past paper not found")
    return PastPaperStatusOut.model_validate(row)


@router.post(
    "/{past_paper_id}/mark-scheme",
    response_model=PastPaperOut,
    responses={
        200: {"description": "Mark scheme applied successfully"},
        406: {"description": "Mark scheme uploaded but 0 questions were matched"},
    },
    summary="Upload a mark scheme PDF for an existing past paper",
)
async def upload_mark_scheme(
    request: Request,
    response: Response,
    past_paper_id: uuid.UUID,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(..., description="Mark scheme PDF")],
    container: AppContainer = Depends(get_container),
) -> PastPaperOut:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF files are accepted for the mark scheme",
        )
    mark_scheme_bytes = await file.read()
    if not mark_scheme_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded mark scheme file is empty",
        )
    try:
        paper, applied_ms, total_short = await pp_svc.upload_mark_scheme(
            container.session_factory,
            user_id=current_user.id,
            past_paper_id=past_paper_id,
            mark_scheme_bytes=mark_scheme_bytes,
            mark_scheme_filename=file.filename,
            usage_service=getattr(request.app.state, "usage_service", None),
            s3=container.s3,
            prompt_manager=container.prompt_manager,
        )
    except pp_svc.PastPaperError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if total_short > 0 and applied_ms == 0:
        response.status_code = status.HTTP_406_NOT_ACCEPTABLE

    return PastPaperOut.model_validate(paper)


@router.delete(
    "/{past_paper_id}/mark-scheme",
    response_model=PastPaperOut,
    summary="Remove the mark scheme from all questions in a past paper",
)
async def delete_mark_scheme(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> PastPaperOut:
    try:
        paper = await pp_svc.delete_mark_scheme(db, current_user.id, past_paper_id)
    except pp_svc.PastPaperError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PastPaperOut.model_validate(paper)


@router.patch(
    "/{past_paper_id}/rename",
    response_model=PastPaperOut,
    summary="Rename a past paper",
)
async def rename_past_paper(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    name: Annotated[str, Form(...)],
) -> PastPaperOut:
    try:
        paper = await pp_svc.rename_past_paper(
            db, current_user.id, past_paper_id, name.strip()
        )
    except pp_svc.PastPaperError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PastPaperOut.model_validate(paper)


@router.delete(
    "/{past_paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a past paper and all its questions",
)
async def delete_past_paper(
    past_paper_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    container: AppContainer = Depends(get_container),
) -> None:
    try:
        await pp_svc.delete_past_paper(
            db, current_user.id, past_paper_id, s3=container.s3
        )
    except pp_svc.PastPaperError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
