"""Citation extractor — parses :::link Doc:"...", pages:"..."::: from response text."""

from __future__ import annotations

import re
from collections import defaultdict

from src.chat.entities import Citation, DocumentInfo, RetrievedChunk

CITATION_PATTERN = re.compile(
    r":::link\s+Doc:\"(?P<doc>[^\"]*)\"\s*,\s*page(?:s|):\"(?P<pages>[^\"]*)\"\s*:::",
    flags=re.IGNORECASE,
)


def _parse_pages(pages_str: str) -> list[int]:
    """Parse pages string: '10', '10-15', '10, 12, 15', '10-12, 15'."""
    result: set[int] = set()
    for part in pages_str.replace(" ", "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, _, end_s = part.partition("-")
            try:
                start_p = int(start_s)
                end_p = int(end_s)
                result.update(range(min(start_p, end_p), max(start_p, end_p) + 1))
            except ValueError:
                try:
                    result.add(int(part))
                except ValueError:
                    pass
        else:
            try:
                result.add(int(part))
            except ValueError:
                pass
    return sorted(result)


class CitationExtractor:
    def extract(
        self,
        response_text: str,
        retrieved_chunks: list[RetrievedChunk],
        document_registry: list[DocumentInfo],
    ) -> list[Citation]:
        if not response_text:
            return []

        documents_by_name = {doc.name.strip().lower(): doc for doc in document_registry}
        chunks_by_doc_and_page: dict[tuple[str, int], list[str]] = defaultdict(list)

        for chunk in retrieved_chunks:
            chunks_by_doc_and_page[(chunk.document_id, int(chunk.page))].append(
                chunk.chunk_id
            )

        aggregated: dict[str, dict] = {}

        for match in CITATION_PATTERN.finditer(response_text):
            doc_name_raw = match.group("doc").strip()
            doc = self._match_document(
                doc_name_raw, documents_by_name, document_registry
            )
            if not doc:
                continue

            pages = _parse_pages(match.group("pages"))
            key = doc.document_id

            if key not in aggregated:
                aggregated[key] = {
                    "document_id": doc.document_id,
                    "document_name": doc.name,
                    "pages": set(),
                    "chunk_ids": set(),
                }

            aggregated[key]["pages"].update(pages)

            for page in pages:
                for chunk_id in chunks_by_doc_and_page.get((doc.document_id, page), []):
                    aggregated[key]["chunk_ids"].add(chunk_id)

        citations: list[Citation] = []
        for entry in aggregated.values():
            citations.append(
                Citation(
                    document_id=entry["document_id"],
                    document_name=entry["document_name"],
                    pages=sorted(entry["pages"]),
                    chunk_ids=sorted(entry["chunk_ids"]),
                )
            )

        citations.sort(key=lambda c: c.document_name.lower())
        return citations

    @staticmethod
    def _match_document(
        cited_name: str,
        documents_by_name: dict[str, DocumentInfo],
        document_registry: list[DocumentInfo],
    ) -> DocumentInfo | None:
        normalized = cited_name.strip().lower()
        if normalized in documents_by_name:
            return documents_by_name[normalized]

        for name, doc in documents_by_name.items():
            if normalized in name or name in normalized:
                return doc

        for doc in document_registry:
            if doc.document_id == cited_name:
                return doc

        return None
