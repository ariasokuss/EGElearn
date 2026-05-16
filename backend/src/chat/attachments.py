"""Process file attachments for chat messages."""

from __future__ import annotations

import base64
import io
import logging
import uuid
from dataclasses import dataclass, field

from src.config import ChatSettings, get_settings
from src.core.s3 import S3Client
from src.processing.markdown import MistralOCR

logger = logging.getLogger(__name__)

_IMAGE_MIMES = {"image/png", "image/jpeg", "image/heic", "image/heif"}
_TEXT_MIMES = {"text/plain", "text/markdown"}
_PDF_MIME = "application/pdf"

_MIME_TO_LLM_MIME: dict[str, str] = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/heic": "image/jpeg",  # converted
    "image/heif": "image/jpeg",  # converted
}


@dataclass
class TextBlock:
    filename: str
    content: str
    source_type: str  # "pdf_ocr" | "text_file"


@dataclass
class ProcessedAttachments:
    image_data_uris: list[str] = field(default_factory=list)
    text_blocks: list[TextBlock] = field(default_factory=list)
    s3_keys: list[str] = field(default_factory=list)
    attachment_meta: list[dict] = field(default_factory=list)


def _convert_heic_to_jpeg(raw_bytes: bytes) -> bytes:
    """Convert HEIC/HEIF bytes to JPEG."""
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    img = Image.open(io.BytesIO(raw_bytes))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _decode_base64(data: str) -> bytes:
    """Decode base64 string, stripping whitespace."""
    return base64.b64decode(data, validate=True)


def _classify_type(mime_type: str) -> str:
    """Classify a mime type into 'image', 'pdf', or 'text'."""
    if mime_type in _IMAGE_MIMES:
        return "image"
    if mime_type == _PDF_MIME:
        return "pdf"
    return "text"


def _human_size(n: int) -> str:
    """Return a human-readable file size string."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.0f}MB"
    return f"{n / 1024:.0f}KB"


def _validate_size(raw_bytes: bytes, mime_type: str, settings: ChatSettings) -> None:
    """Raise ValueError if the file exceeds size limits."""
    size = len(raw_bytes)
    if mime_type in _IMAGE_MIMES:
        if size > settings.max_image_size_bytes:
            raise ValueError(
                f"Image exceeds {_human_size(settings.max_image_size_bytes)} limit."
            )
    elif mime_type == _PDF_MIME:
        if size > settings.max_pdf_size_bytes:
            raise ValueError(
                f"PDF exceeds {_human_size(settings.max_pdf_size_bytes)} limit."
            )
    elif mime_type in _TEXT_MIMES:
        if size > settings.max_text_size_bytes:
            raise ValueError(
                f"Text file exceeds {_human_size(settings.max_text_size_bytes)} limit."
            )


async def process_attachments(
    attachments: list,
    conversation_id: str,
    s3: S3Client,
    mistral_ocr: MistralOCR | None,
    settings: ChatSettings | None = None,
) -> ProcessedAttachments:
    """Process file attachments and return results for LLM and storage.

    Args:
        attachments: List of FileAttachment schema objects.
        conversation_id: Conversation ID for S3 key paths.
        s3: S3 client for file uploads.
        mistral_ocr: MistralOCR instance for PDF processing.
        settings: Chat settings (defaults from config).

    Returns:
        ProcessedAttachments with images, text blocks, S3 keys, and metadata.
    """
    if settings is None:
        settings = get_settings().chat

    result = ProcessedAttachments()

    for attachment in attachments:
        mime = attachment.mime_type
        filename = attachment.filename
        file_type = _classify_type(mime)

        try:
            raw_bytes = _decode_base64(attachment.data)
        except Exception:
            logger.warning("Failed to decode base64 for attachment %s", filename)
            continue

        try:
            _validate_size(raw_bytes, mime, settings)
        except ValueError as e:
            logger.warning("Attachment %s rejected: %s", filename, e)
            raise

        try:
            if file_type == "image":
                await _process_image(
                    raw_bytes, mime, filename, conversation_id, s3, result
                )
            elif file_type == "pdf":
                await _process_pdf(
                    raw_bytes, filename, conversation_id, s3, mistral_ocr, settings, result
                )
            elif file_type == "text":
                await _process_text(
                    raw_bytes, filename, mime, conversation_id, s3, settings, result
                )
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to process attachment %s", filename)
            continue

    return result


async def _process_image(
    raw_bytes: bytes,
    mime: str,
    filename: str,
    conversation_id: str,
    s3: S3Client,
    result: ProcessedAttachments,
) -> None:
    """Process an image attachment: convert HEIC if needed, upload to S3, create data-URI."""
    if mime in ("image/heic", "image/heif"):
        try:
            raw_bytes = _convert_heic_to_jpeg(raw_bytes)
        except Exception:
            logger.exception("HEIC conversion failed for %s", filename)
            raise ValueError(f"Failed to convert HEIC image '{filename}'.")
        store_mime = "image/jpeg"
        ext = "jpg"
    else:
        store_mime = mime
        ext = "png" if mime == "image/png" else "jpg"

    # Build data-URI for LLM
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    llm_mime = _MIME_TO_LLM_MIME.get(mime, store_mime)
    data_uri = f"data:{llm_mime};base64,{b64}"
    result.image_data_uris.append(data_uri)

    # Upload to S3
    key = f"chat-attachments/{conversation_id}/{uuid.uuid4()}.{ext}"
    try:
        await s3.upload_bytes(key, raw_bytes, content_type=store_mime)
        result.s3_keys.append(key)
    except Exception:
        logger.exception("Failed to upload image to S3 key=%s", key)

    result.attachment_meta.append(
        {"filename": filename, "mime_type": mime, "type": "image", "s3_key": key}
    )


async def _process_pdf(
    raw_bytes: bytes,
    filename: str,
    conversation_id: str,
    s3: S3Client,
    mistral_ocr: MistralOCR | None,
    settings: ChatSettings,
    result: ProcessedAttachments,
) -> None:
    """Process a PDF attachment: OCR with Mistral, upload original to S3."""
    if mistral_ocr is None:
        raise ValueError("PDF processing is not available (Mistral OCR not configured).")

    # Upload original PDF to S3
    key = f"chat-attachments/{conversation_id}/{uuid.uuid4()}.pdf"
    try:
        await s3.upload_bytes(key, raw_bytes, content_type="application/pdf")
        result.s3_keys.append(key)
    except Exception:
        logger.exception("Failed to upload PDF to S3 key=%s", key)

    # OCR with Mistral
    markdown = await mistral_ocr.pdf_to_markdown(raw_bytes)

    # Truncate if needed
    if len(markdown) > settings.max_attachment_text_chars:
        markdown = markdown[: settings.max_attachment_text_chars] + "\n\n[...truncated]"

    result.text_blocks.append(
        TextBlock(filename=filename, content=markdown, source_type="pdf_ocr")
    )
    result.attachment_meta.append(
        {"filename": filename, "mime_type": "application/pdf", "type": "pdf", "s3_key": key}
    )


async def _process_text(
    raw_bytes: bytes,
    filename: str,
    mime: str,
    conversation_id: str,
    s3: S3Client,
    settings: ChatSettings,
    result: ProcessedAttachments,
) -> None:
    """Process a text/markdown attachment: decode and store."""
    text = raw_bytes.decode("utf-8", errors="replace")

    # Truncate if needed
    if len(text) > settings.max_attachment_text_chars:
        text = text[: settings.max_attachment_text_chars] + "\n\n[...truncated]"

    source_type = "text_file"
    result.text_blocks.append(
        TextBlock(filename=filename, content=text, source_type=source_type)
    )

    # Upload original to S3
    ext = "md" if "markdown" in mime else "txt"
    key = f"chat-attachments/{conversation_id}/{uuid.uuid4()}.{ext}"
    try:
        await s3.upload_bytes(key, raw_bytes, content_type=mime)
        result.s3_keys.append(key)
    except Exception:
        logger.exception("Failed to upload text file to S3 key=%s", key)

    result.attachment_meta.append(
        {"filename": filename, "mime_type": mime, "type": "text", "s3_key": key}
    )


def format_text_blocks_for_message(text_blocks: list[TextBlock]) -> str:
    """Format text blocks as XML-delimited sections to append to user message."""
    if not text_blocks:
        return ""

    parts: list[str] = []
    for block in text_blocks:
        parts.append(
            f'<attached_file name="{block.filename}" type="{block.source_type}">\n'
            f"{block.content}\n"
            f"</attached_file>"
        )
    return "\n\n" + "\n\n".join(parts)


def text_blocks_to_metadata(text_blocks: list[TextBlock]) -> list[dict]:
    """Convert text blocks to serializable metadata for storage."""
    return [
        {
            "filename": b.filename,
            "content": b.content,
            "source_type": b.source_type,
        }
        for b in text_blocks
    ]


def metadata_to_text_blocks(meta: list[dict]) -> list[TextBlock]:
    """Reconstruct text blocks from stored metadata."""
    return [
        TextBlock(
            filename=m["filename"],
            content=m["content"],
            source_type=m["source_type"],
        )
        for m in meta
    ]
