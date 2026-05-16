import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.files import service as files_svc
from src.files.schemas import DocumentOut


async def stream_folder_documents(
    db: AsyncSession,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    *,
    interval_seconds: float,
) -> AsyncGenerator[str, None]:
    """Yield SSE events with the latest document states for a folder."""
    await files_svc.get_folder(db, user_id, folder_id)
    last_payload = ""

    while True:
        documents = await files_svc.list_documents(db, user_id, folder_id)
        payload = json.dumps(
            {
                "documents": [
                    DocumentOut.model_validate(document).model_dump(mode="json")
                    for document in documents
                ]
            }
        )
        if payload != last_payload:
            yield f"event: documents\ndata: {payload}\n\n"
            last_payload = payload
        else:
            yield "event: heartbeat\ndata: {}\n\n"
        await db.rollback()
        await asyncio.sleep(interval_seconds)
