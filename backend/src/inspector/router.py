import uuid
import asyncio
import json
from pathlib import Path

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse

from src.api.deps import get_inspector_service
from src.inspector.schemas import DocumentInspectorRead, InspectorOverviewRead
from src.inspector.service import InspectorService
from src.learning.schemas import (
    FeynmanBlockRead,
    LessonBlockSchema,
    LessonDetailRead,
    LessonSchema,
    LessonUploadResponse,
    ParseFeynmanResponse,
)
from src.learning.service import LearningService
from src.runtime import AppContainer

router = APIRouter(prefix="/inspector", tags=["inspector"])
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
CHAT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "chat" / "assets"
ALLOWED_ASSETS = {
    "app.js": ASSETS_DIR / "app.js",
    "styles.css": ASSETS_DIR / "styles.css",
}


def _get_container(request: Request) -> AppContainer:
    return request.app.state.container


def _get_learning_service(
    container: AppContainer = Depends(_get_container),
) -> LearningService:
    return LearningService(session_factory=container.session_factory)


@router.get("", include_in_schema=False)
async def inspector_page() -> FileResponse:
    return FileResponse(ASSETS_DIR / "index.html")


@router.get("/dashboard", include_in_schema=False)
async def inspector_dashboard_page() -> FileResponse:
    return FileResponse(ASSETS_DIR / "dashboard.html")


@router.get("/folder", include_in_schema=False)
async def inspector_folder_page() -> FileResponse:
    return FileResponse(ASSETS_DIR / "folder.html")


@router.get("/document", include_in_schema=False)
async def inspector_document_page() -> FileResponse:
    return FileResponse(ASSETS_DIR / "document.html")


@router.get("/chat", include_in_schema=False)
async def inspector_chat_page() -> FileResponse:
    """Serve the RAG chat UI (combined with inspector)."""
    return FileResponse(CHAT_ASSETS_DIR / "index.html")


@router.get("/assets/{asset_name}", include_in_schema=False)
async def inspector_asset(asset_name: str) -> FileResponse:
    path = ALLOWED_ASSETS.get(asset_name)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )
    return FileResponse(path)


@router.get("/overview", response_model=InspectorOverviewRead)
async def get_overview(
    user_id: uuid.UUID = Query(...),
    service: InspectorService = Depends(get_inspector_service),
) -> InspectorOverviewRead:
    overview = await service.get_overview(user_id)
    if overview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return overview


@router.get(
    "/folders/{folder_id}/documents/{document_id}", response_model=DocumentInspectorRead
)
async def get_document_detail(
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    service: InspectorService = Depends(get_inspector_service),
) -> DocumentInspectorRead:
    detail = await service.get_document_detail(
        user_id=user_id,
        folder_id=folder_id,
        document_id=document_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return detail


@router.get("/folders/{folder_id}/stream", include_in_schema=False)
async def stream_folder_status(
    request: Request,
    folder_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    service: InspectorService = Depends(get_inspector_service),
) -> StreamingResponse:
    async def event_stream():
        while not await request.is_disconnected():
            folder = await service.get_folder_status(
                user_id=user_id, folder_id=folder_id
            )
            if folder is None:
                yield 'event: error\ndata: {"detail": "Folder not found"}\n\n'
                break
            payload = json.dumps(folder.model_dump(mode="json"))
            yield f"event: folder\ndata: {payload}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/folders/{folder_id}/documents/{document_id}/stream", include_in_schema=False
)
async def stream_document_status(
    request: Request,
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    service: InspectorService = Depends(get_inspector_service),
) -> StreamingResponse:
    async def event_stream():
        while not await request.is_disconnected():
            detail = await service.get_document_live_status(
                user_id=user_id,
                folder_id=folder_id,
                document_id=document_id,
            )
            if detail is None:
                yield 'event: error\ndata: {"detail": "Document not found"}\n\n'
                break
            payload = json.dumps(detail.model_dump(mode="json"))
            yield f"event: document\ndata: {payload}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Lessons — HTML pages
# ---------------------------------------------------------------------------


@router.get("/lessons", include_in_schema=False)
async def inspector_lessons_page() -> FileResponse:
    return FileResponse(ASSETS_DIR / "lessons.html")


@router.get("/lessons/{lesson_id}", include_in_schema=False)
async def inspector_lesson_detail_page() -> FileResponse:
    return FileResponse(ASSETS_DIR / "lesson.html")


# ---------------------------------------------------------------------------
# Lessons — API data endpoints (used by inspector JS)
# ---------------------------------------------------------------------------


@router.get("/api/lessons", response_model=list[LessonSchema])
async def api_list_lessons(
    user_id: uuid.UUID = Query(...),
    service: LearningService = Depends(_get_learning_service),
) -> list[LessonSchema]:
    lessons = await service.list_lessons(user_id)
    return [LessonSchema.model_validate(lesson) for lesson in lessons]


@router.get("/api/lessons/{lesson_id}", response_model=LessonDetailRead)
async def api_get_lesson(
    lesson_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    service: LearningService = Depends(_get_learning_service),
) -> LessonDetailRead:
    lesson = await service.get_lesson(lesson_id, user_id)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found"
        )
    blocks = await service.get_lesson_blocks(lesson_id)
    return LessonDetailRead(
        lesson=LessonSchema.model_validate(lesson),
        blocks=[LessonBlockSchema.model_validate(b) for b in blocks],
        feynman_blocks=[
            FeynmanBlockRead.model_validate(fb) for fb in lesson.feynman_blocks
        ],
    )


@router.post(
    "/api/lessons/upload",
    response_model=LessonUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_upload_lesson(
    file: Annotated[UploadFile, File(...)],
    user_id: Annotated[uuid.UUID, Form(...)],
    name: Annotated[str | None, Form()] = None,
    service: LearningService = Depends(_get_learning_service),
) -> LessonUploadResponse:
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .md files are accepted",
        )
    raw = await file.read()
    content = raw.decode("utf-8")
    lesson_name = name or file.filename.removesuffix(".md")
    lesson, blocks = await service.upload_lesson(user_id, lesson_name, content)
    return LessonUploadResponse(
        lesson=LessonSchema.model_validate(lesson),
        blocks=[LessonBlockSchema.model_validate(b) for b in blocks],
        num_blocks=len(blocks),
    )


@router.post(
    "/api/lessons/{lesson_id}/parse-feynman", response_model=ParseFeynmanResponse
)
async def api_parse_feynman(
    lesson_id: uuid.UUID,
    user_id: uuid.UUID = Query(...),
    service: LearningService = Depends(_get_learning_service),
) -> ParseFeynmanResponse:
    blocks = await service.parse_and_store_feynman_blocks(lesson_id, user_id)
    return ParseFeynmanResponse(
        count=len(blocks),
        blocks=[FeynmanBlockRead.model_validate(b) for b in blocks],
    )
