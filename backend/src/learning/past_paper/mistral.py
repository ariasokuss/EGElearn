"""Mistral OCR wrapper for past paper PDF processing with image extraction."""

from __future__ import annotations

import re

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from src.config import MistralSettings

RETRYABLE_MISTRAL_STATUS_CODES = {429, 500, 502, 503, 504}


class TransientOCRError(RuntimeError):
    """Raised when Mistral OCR is temporarily unavailable."""


def _process_markdown(markdown: str) -> str:
    normalized = markdown.replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    return normalized + "\n"


class PastPaperOCR:
    """Convert a past-paper PDF into markdown and extract embedded images."""

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
            raise TransientOCRError(
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

    async def pdf_to_markdown_with_images(
        self, pdf_bytes: bytes
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        """
        Run OCR on a PDF with image extraction enabled.

        Returns:
            (markdown, images_dict, tables_dict) where:
            - images_dict maps image_id → base64 string
            - tables_dict maps table_id (e.g. "tbl-0.md") → markdown content
            Tables are also inlined into the markdown, replacing their
            ``[tbl-X.md](tbl-X.md)`` references with actual content.
        """
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
                include_image_base64=True,
                table_format="markdown",
            )
        except SDKError as exc:
            self._raise_if_retryable(exc)
            raise

        # Build a map of table id → markdown content from OCR response
        tables_by_id: dict[str, str] = {}
        for page in response.pages:
            for tbl in getattr(page, "tables", None) or []:
                tbl_id = getattr(tbl, "id", None)
                tbl_content = getattr(tbl, "content", None)
                if tbl_id and tbl_content:
                    tables_by_id[tbl_id] = tbl_content.strip()

        parts: list[str] = []
        images_dict: dict[str, str] = {}

        for page in response.pages:
            parts.append(f"[PAGE {page.index + 1}]")
            content = (page.markdown or "").strip()
            if content:
                # Replace tbl-X.md references with actual table content
                for tbl_id, tbl_content in tables_by_id.items():
                    # Handle both ![tbl-X.md](tbl-X.md) and [tbl-X.md](tbl-X.md)
                    content = content.replace(f"![{tbl_id}]({tbl_id})", tbl_content)
                    content = content.replace(f"[{tbl_id}]({tbl_id})", tbl_content)
                parts.append(content)
            for img in getattr(page, "images", []):
                b64 = getattr(img, "image_base64", None)
                if b64 and isinstance(b64, str):
                    images_dict[img.id] = b64

        return _process_markdown("\n\n".join(parts)), images_dict, tables_by_id
