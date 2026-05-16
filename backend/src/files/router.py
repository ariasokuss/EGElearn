import uuid
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db, get_rabbitmq, get_s3
from src.core.rabbitmq import RabbitMQClient, RabbitMQNotConnectedError
from src.core.s3 import S3Client
from src.files import service as files_svc
from src.files.models import Folder, FolderType
from src.files.schemas import (
    BatchUploadResponse,
    DocumentOut,
    DownloadUrlResponse,
    FolderCreate,
    FolderOut,
    FolderReorderRequest,
    MarkdownResponse,
    UploadConfirmRequest,
    UploadRequest,
    UploadResponse,
)
from src.roadmap.ege_subjects import EGE_SUBJECT_NAME_SET

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]
RabbitMQDep = Annotated[RabbitMQClient, Depends(get_rabbitmq)]
S3Dep = Annotated[S3Client, Depends(get_s3)]


@router.post(
    "/folders",
    response_model=FolderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a folder",
)
async def create_folder(
    body: FolderCreate,
    db: DbDep,
    current_user: CurrentUser,
) -> FolderOut:
    folder = await files_svc.create_folder(db, current_user.id, body.name, body.type)
    return FolderOut.model_validate(folder)


@router.get(
    "/folders",
    response_model=list[FolderOut],
    summary="List all folders",
)
async def list_folders(
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    folders = await files_svc.list_folders(db, current_user.id)
    return [FolderOut.model_validate(f) for f in folders]


@router.patch(
    "/folders/{folder_id}",
    response_model=FolderOut,
    summary="Rename a folder",
)
async def rename_folder(
    folder_id: uuid.UUID,
    body: FolderCreate,
    db: DbDep,
    current_user: CurrentUser,
) -> FolderOut:
    try:
        folder = await files_svc.rename_folder(
            db, current_user.id, folder_id, body.name
        )
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FolderOut.model_validate(folder)


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a folder and all its documents",
)
async def delete_folder(
    folder_id: uuid.UUID,
    db: DbDep,
    s3: S3Dep,
    current_user: CurrentUser,
) -> None:
    try:
        await files_svc.delete_folder(db, current_user.id, folder_id, s3)
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/folders/{folder_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document through the API gateway",
)
async def upload_document(
    folder_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
    rabbitmq: RabbitMQDep,
    s3: S3Dep,
    current_user: CurrentUser,
    name: Annotated[str | None, Form()] = None,
) -> DocumentOut:
    started = time.perf_counter()
    try:
        payload = await file.read()
        document, job = await files_svc.upload_document(
            db,
            s3,
            current_user.id,
            folder_id,
            filename=file.filename or "",
            content_type=file.content_type or "application/octet-stream",
            payload=payload,
            name=name,
        )
        await rabbitmq.publish_job(job.id)
    except RabbitMQNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except files_svc.FilesError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    logger.info(
        "Accepted document upload document_id=%s job_id=%s folder_id=%s user_id=%s filename=%r size_bytes=%s elapsed=%.2fs",
        document.id,
        job.id,
        folder_id,
        current_user.id,
        file.filename or "",
        len(payload),
        time.perf_counter() - started,
    )
    return DocumentOut.model_validate(document)


@router.post(
    "/folders/{folder_id}/documents/batch",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple documents through the API gateway",
)
async def upload_documents(
    folder_id: uuid.UUID,
    files: Annotated[list[UploadFile], File(...)],
    db: DbDep,
    rabbitmq: RabbitMQDep,
    s3: S3Dep,
    current_user: CurrentUser,
    names: Annotated[list[str] | None, Form()] = None,
) -> BatchUploadResponse:
    started = time.perf_counter()
    if not files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one file is required",
        )
    if names and len(names) not in {0, len(files)}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Names count must match files count",
        )

    documents = []
    job_ids: list[str] = []
    for index, file in enumerate(files):
        try:
            payload = await file.read()
            document, job = await files_svc.upload_document(
                db,
                s3,
                current_user.id,
                folder_id,
                filename=file.filename or "",
                content_type=file.content_type or "application/octet-stream",
                payload=payload,
                name=names[index] if names else None,
            )
            await rabbitmq.publish_job(job.id)
        except RabbitMQNotConnectedError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        except files_svc.FilesError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        documents.append(DocumentOut.model_validate(document))
        job_ids.append(str(job.id))

    logger.info(
        "Accepted batch upload folder_id=%s user_id=%s documents=%d job_ids=%s elapsed=%.2fs",
        folder_id,
        current_user.id,
        len(documents),
        job_ids,
        time.perf_counter() - started,
    )
    return BatchUploadResponse(documents=documents)


@router.post(
    "/folders/{folder_id}/documents/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a direct-to-S3 upload (returns presigned PUT URL)",
)
async def initiate_upload(
    folder_id: uuid.UUID,
    body: UploadRequest,
    db: DbDep,
    s3: S3Dep,
    current_user: CurrentUser,
) -> UploadResponse:
    try:
        doc, upload_url = await files_svc.initiate_upload(
            db,
            s3,
            current_user.id,
            folder_id,
            name=body.name,
            filename=body.filename,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
    except files_svc.FilesError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return UploadResponse(
        document_id=doc.id,
        upload_url=upload_url,
        source_s3_key=doc.source_s3_key,
        expires_in=900,
    )


@router.post(
    "/folders/{folder_id}/documents/{document_id}/confirm",
    response_model=DocumentOut,
    summary="Confirm upload completed — moves document to 'uploaded' status",
)
async def confirm_upload(
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    body: UploadConfirmRequest,
    db: DbDep,
    rabbitmq: RabbitMQDep,
    current_user: CurrentUser,
) -> DocumentOut:
    try:
        doc, job = await files_svc.confirm_upload(
            db, current_user.id, document_id, body.size_bytes
        )
        await rabbitmq.publish_job(job.id)
    except RabbitMQNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except files_svc.FilesError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return DocumentOut.model_validate(doc)


@router.get(
    "/folders/{folder_id}/documents",
    response_model=list[DocumentOut],
    summary="List documents in a folder",
)
async def list_documents(
    folder_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> list[DocumentOut]:
    try:
        docs = await files_svc.list_documents(db, current_user.id, folder_id)
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [DocumentOut.model_validate(d) for d in docs]


@router.get(
    "/folders/{folder_id}/documents/{document_id}",
    response_model=DocumentOut,
    summary="Get a single document",
)
async def get_document(
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> DocumentOut:
    try:
        doc = await files_svc.get_document(db, current_user.id, document_id)
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DocumentOut.model_validate(doc)


@router.get(
    "/folders/{folder_id}/documents/{document_id}/markdown",
    response_model=MarkdownResponse,
    summary="Get processed markdown content for a document",
)
async def get_document_markdown(
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> MarkdownResponse:
    try:
        doc = await files_svc.get_document(db, current_user.id, document_id)
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not doc.markdown_content:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Document markdown is not available yet",
        )

    return MarkdownResponse(markdown=doc.markdown_content)


@router.get(
    "/folders/{folder_id}/documents/{document_id}/download-url",
    response_model=DownloadUrlResponse,
    summary="Generate a presigned GET URL for the document",
)
async def download_url(
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbDep,
    s3: S3Dep,
    current_user: CurrentUser,
) -> DownloadUrlResponse:
    try:
        url = await files_svc.get_download_url(s3, db, current_user.id, document_id)
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DownloadUrlResponse(download_url=url)


@router.delete(
    "/folders/{folder_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its S3 object",
)
async def delete_document(
    folder_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbDep,
    s3: S3Dep,
    current_user: CurrentUser,
) -> None:
    try:
        await files_svc.delete_document(db, s3, current_user.id, document_id)
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _folder_out_pairs(pairs: list[tuple[Folder, int]]) -> list[FolderOut]:
    return [
        FolderOut.model_validate({**folder.__dict__, "position": position})
        for folder, position in pairs
    ]


def _filter_ege_pairs(pairs: list[tuple[Folder, int]]) -> list[tuple[Folder, int]]:
    return [
        (folder, position)
        for folder, position in pairs
        if folder.user_id is None and folder.name in EGE_SUBJECT_NAME_SET
    ]


async def _list_ege_pairs(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Folder, int]]:
    pairs = await files_svc.list_folders_by_type(db, user_id, FolderType.a_level)
    return _filter_ege_pairs(pairs)


@router.get("/folders/ege", summary="Get EGE subject folders")
async def get_ege_folders(
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    return _folder_out_pairs(await _list_ege_pairs(db, current_user.id))


@router.patch("/folders/ege/reorder", summary="Reorder EGE subject folders")
async def reorder_ege_folders(
    body: FolderReorderRequest,
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    all_pairs = await files_svc.list_folders_by_type(
        db, current_user.id, FolderType.a_level
    )
    ege_pairs = _filter_ege_pairs(all_pairs)
    ege_ids = {folder.id for folder, _position in ege_pairs}
    requested_ids = list(body.folder_ids)
    if len(requested_ids) != len(ege_ids) or set(requested_ids) != ege_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="EGE reorder request must contain every EGE subject folder exactly once.",
        )
    requested_iter = iter(requested_ids)
    full_order_ids = [
        next(requested_iter) if folder.id in ege_ids else folder.id
        for folder, _position in all_pairs
    ]
    try:
        pairs = await files_svc.reorder_folders(
            db, current_user.id, FolderType.a_level, full_order_ids
        )
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _folder_out_pairs(_filter_ege_pairs(pairs))


@router.get("/folders/a-level", summary="Get A-level folders")
async def get_a_level_folders(
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    pairs = await files_svc.list_folders_by_type(
        db, current_user.id, FolderType.a_level
    )
    return _folder_out_pairs(pairs)


@router.get("/folders/gcse", summary="Get GCSE folders")
async def get_gcse_folders(
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    pairs = await files_svc.list_folders_by_type(db, current_user.id, FolderType.gcse)
    return _folder_out_pairs(pairs)


@router.patch("/folders/a-level/reorder", summary="Reorder A-level folders")
async def reorder_a_level_folders(
    body: FolderReorderRequest,
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    try:
        pairs = await files_svc.reorder_folders(
            db, current_user.id, FolderType.a_level, body.folder_ids
        )
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _folder_out_pairs(pairs)


@router.patch("/folders/gcse/reorder", summary="Reorder GCSE folders")
async def reorder_gcse_folders(
    body: FolderReorderRequest,
    db: DbDep,
    current_user: CurrentUser,
) -> list[FolderOut]:
    try:
        pairs = await files_svc.reorder_folders(
            db, current_user.id, FolderType.gcse, body.folder_ids
        )
    except files_svc.FilesError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _folder_out_pairs(pairs)
