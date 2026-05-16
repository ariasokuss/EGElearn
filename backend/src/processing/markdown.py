import re

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from src.config import MistralSettings, ProcessingSettings

RETRYABLE_MISTRAL_STATUS_CODES = {429, 500, 502, 503, 504}
_TRANSCRIPT_BOUNDARY_RE = re.compile(
    r"^(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?"
    r"(?:[A-Z][A-Za-z0-9&.'-]{1,30}(?:\s+[A-Z][A-Za-z0-9&.'-]{1,30}){0,4})"
    r"\s*:\s+"
)
_TIMESTAMP_ONLY_RE = re.compile(r"^\[?\d{1,2}:\d{2}(?::\d{2})?\]?$")
_SHORT_HEADING_RE = re.compile(r"^(?:#{1,6}\s+.+|[A-Z][A-Z0-9 /&()-]{4,80})$")
_PAGE_MARKER_RE = re.compile(r"^\[PAGE\s+(\d+)\]\s*$", re.MULTILINE)


class TransientOCRProviderError(RuntimeError):
    """Raised when Mistral OCR is temporarily unavailable."""


class MistralOCR:
    """Convert PDF bytes into markdown by using Mistral OCR."""

    def __init__(self, settings: MistralSettings) -> None:
        self._api_key = settings.api_key
        self._model = settings.ocr_model
        self._client = Mistral(api_key=settings.api_key) if settings.api_key else None

    @staticmethod
    def _extract_status_code(exc: SDKError) -> int | None:
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)
            if isinstance(status_code, int):
                return status_code

        match = re.search(r"Status\s+(\d{3})", str(exc))
        if match:
            return int(match.group(1))
        return None

    def _raise_if_retryable(self, exc: SDKError) -> None:
        status_code = self._extract_status_code(exc)
        if status_code in RETRYABLE_MISTRAL_STATUS_CODES:
            raise TransientOCRProviderError(
                f"Mistral OCR is temporarily unavailable (HTTP {status_code})."
            ) from exc

    async def _upload_pdf_and_get_signed_url(self, pdf_bytes: bytes) -> str:
        if self._client is None or not self._api_key:
            raise RuntimeError("MISTRAL__API_KEY is not set")

        try:
            upload = await self._client.files.upload_async(
                file={
                    "file_name": "document.pdf",
                    "content": pdf_bytes,
                },
                purpose="ocr",
            )
        except SDKError as exc:
            self._raise_if_retryable(exc)
            raise

        file_id = getattr(upload, "id", None)
        if not file_id:
            raise RuntimeError("Mistral upload did not return file id")

        signed = await self._client.files.get_signed_url_async(
            file_id=file_id, expiry=24
        )
        signed_url = getattr(signed, "url", None)
        if not signed_url:
            raise RuntimeError("Mistral signed URL missing")
        return str(signed_url)

    async def pdf_to_markdown(self, pdf_bytes: bytes) -> str:
        """Run OCR on a PDF and return markdown with page markers."""
        if self._client is None:
            raise RuntimeError("MISTRAL__API_KEY is not set")

        document_url = await self._upload_pdf_and_get_signed_url(pdf_bytes)

        try:
            response = await self._client.ocr.process_async(
                model=self._model,
                document={
                    "type": "document_url",
                    "document_url": document_url,
                },
                include_image_base64=False,
                table_format="markdown",
            )
        except SDKError as exc:
            self._raise_if_retryable(exc)
            raise

        parts: list[str] = []
        for page in response.pages:
            parts.append(f"[PAGE {page.index + 1}]")
            content = (page.markdown or "").strip()
            if content:
                parts.append(content)

        return process_markdown("\n\n".join(parts))


def process_markdown(markdown: str) -> str:
    """Normalize markdown before it is stored and used by the pipeline."""
    normalized = markdown.replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    return normalized + "\n"


def infer_page_count(markdown: str | None, *, content_type: str) -> int | None:
    """Infer a stable page count from stored markdown content."""
    normalized = (markdown or "").strip()
    if not normalized:
        return None
    if content_type == "application/pdf":
        markers = [int(match) for match in _PAGE_MARKER_RE.findall(normalized)]
        if markers:
            return max(markers)
    return 1


def wrap_line(line: str, max_length: int) -> list[str]:
    """Wrap one text line to the configured maximum length."""
    if len(line) <= max_length:
        return [line] if line else []
    result: list[str] = []
    rest = line
    while rest:
        if len(rest) <= max_length:
            result.append(rest)
            break
        chunk = rest[: max_length + 1]
        last_space = chunk.rfind(" ")
        if last_space > max_length // 2:
            cut = last_space
        else:
            cut = max_length
        result.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return result


def wrap_text_lines(content: str, max_length: int) -> str:
    """Apply the provided text wrapping logic before markdown normalization."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    wrapped: list[str] = []
    previous_was_blank = True
    for raw_line in normalized.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            if wrapped and not previous_was_blank:
                wrapped.append("")
            previous_was_blank = True
            continue

        is_boundary = _looks_like_transcript_boundary(stripped)
        if is_boundary and wrapped and not previous_was_blank:
            wrapped.append("")

        for part in wrap_line(stripped, max_length):
            wrapped.append(part)

        previous_was_blank = False

    while wrapped and wrapped[-1] == "":
        wrapped.pop()
    return process_markdown("\n".join(wrapped))


def _looks_like_transcript_boundary(line: str) -> bool:
    """Return True for speaker/timestamp/heading lines worth isolating."""
    if _TRANSCRIPT_BOUNDARY_RE.match(line):
        return True
    if _TIMESTAMP_ONLY_RE.match(line):
        return True
    return bool(_SHORT_HEADING_RE.match(line) and len(line.split()) <= 10)


async def collect_markdown(
    *,
    content_type: str,
    source_bytes: bytes,
    mistral: MistralOCR,
    processing: ProcessingSettings,
) -> str:
    """Collect markdown from the source file content."""
    if content_type == "application/pdf":
        return await mistral.pdf_to_markdown(source_bytes)
    if content_type == "text/plain":
        return wrap_text_lines(
            source_bytes.decode("utf-8", errors="replace"),
            processing.txt_wrap_max_length,
        )
    raise RuntimeError(f"Unsupported content type {content_type!r}")
