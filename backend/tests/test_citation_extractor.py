"""Tests for CitationExtractor — citation parsing and document matching."""

from __future__ import annotations

from src.chat.citation_extractor import CitationExtractor, _parse_pages
from src.chat.entities import DocumentInfo, RetrievedChunk


def make_doc(name: str, doc_id: str = "doc-1", pages: int = 10) -> DocumentInfo:
    return DocumentInfo(document_id=doc_id, name=name, page_count=pages)


def make_chunk(chunk_id: str, doc_id: str, page: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text="content",
        document_id=doc_id,
        document_name="Doc",
        page=page,
    )


# ── _parse_pages ──────────────────────────────────────────────────────────────


class TestParsePages:
    def test_single_page(self):
        assert _parse_pages("5") == [5]

    def test_range(self):
        assert _parse_pages("3-6") == [3, 4, 5, 6]

    def test_comma_separated(self):
        assert _parse_pages("1, 3, 5") == [1, 3, 5]

    def test_mixed_range_and_single(self):
        assert _parse_pages("1-3, 7") == [1, 2, 3, 7]

    def test_empty_string_returns_empty(self):
        assert _parse_pages("") == []

    def test_deduplicates(self):
        result = _parse_pages("1-3, 2-4")
        assert result == sorted(set(result))

    def test_reversed_range_handled(self):
        # 5-3 should produce [3,4,5]
        assert _parse_pages("5-3") == [3, 4, 5]

    def test_invalid_text_ignored(self):
        assert _parse_pages("abc") == []


# ── CitationExtractor.extract ─────────────────────────────────────────────────


class TestCitationExtractor:
    def setup_method(self):
        self.extractor = CitationExtractor()

    def test_empty_response_returns_empty(self):
        result = self.extractor.extract("", [], [])
        assert result == []

    def test_no_citation_markers_returns_empty(self):
        result = self.extractor.extract("No citations here.", [], [make_doc("Physics")])
        assert result == []

    def test_single_citation_parsed(self):
        text = ':::link Doc:"Physics 101", page:"5":::'
        docs = [make_doc("Physics 101", "doc-1")]
        result = self.extractor.extract(text, [], docs)
        assert len(result) == 1
        assert result[0].document_id == "doc-1"
        assert 5 in result[0].pages

    def test_citation_with_range(self):
        text = ':::link Doc:"Physics 101", pages:"3-5":::'
        docs = [make_doc("Physics 101", "doc-1")]
        result = self.extractor.extract(text, [], docs)
        assert result[0].pages == [3, 4, 5]

    def test_citation_attaches_matching_chunk_ids(self):
        text = ':::link Doc:"Chemistry", page:"2":::'
        docs = [make_doc("Chemistry", "doc-2")]
        chunks = [make_chunk("chunk-x", "doc-2", 2), make_chunk("chunk-y", "doc-2", 3)]
        result = self.extractor.extract(text, chunks, docs)
        assert "chunk-x" in result[0].chunk_ids
        assert "chunk-y" not in result[0].chunk_ids

    def test_multiple_citations_same_doc_aggregated(self):
        text = ':::link Doc:"Math", page:"1"::::::link Doc:"Math", page:"3":::'
        docs = [make_doc("Math", "doc-3")]
        result = self.extractor.extract(text, [], docs)
        assert len(result) == 1
        assert sorted(result[0].pages) == [1, 3]

    def test_multiple_docs_returned_sorted_by_name(self):
        text = ':::link Doc:"Zoology", page:"1"::::::link Doc:"Anatomy", page:"2":::'
        docs = [make_doc("Zoology", "doc-z"), make_doc("Anatomy", "doc-a")]
        result = self.extractor.extract(text, [], docs)
        assert result[0].document_name == "Anatomy"
        assert result[1].document_name == "Zoology"

    def test_unknown_document_skipped(self):
        # Use names with no substring overlap so partial-match logic doesn't fire
        text = ':::link Doc:"Astronomy", page:"1":::'
        docs = [make_doc("Chemistry", "doc-1")]
        result = self.extractor.extract(text, [], docs)
        assert result == []

    def test_case_insensitive_doc_name_match(self):
        text = ':::link Doc:"physics 101", page:"1":::'
        docs = [make_doc("Physics 101", "doc-1")]
        result = self.extractor.extract(text, [], docs)
        assert len(result) == 1

    def test_partial_name_match(self):
        # "Physics" matches document named "Physics 101"
        text = ':::link Doc:"Physics", page:"1":::'
        docs = [make_doc("Physics 101", "doc-1")]
        result = self.extractor.extract(text, [], docs)
        assert len(result) == 1
        assert result[0].document_id == "doc-1"

    def test_match_by_document_id(self):
        text = ':::link Doc:"doc-99", page:"1":::'
        docs = [make_doc("Some Title", "doc-99")]
        result = self.extractor.extract(text, [], docs)
        assert len(result) == 1
        assert result[0].document_id == "doc-99"

    def test_citation_result_sorted_chunk_ids(self):
        text = ':::link Doc:"Bio", pages:"1-2":::'
        docs = [make_doc("Bio", "doc-b")]
        chunks = [
            make_chunk("z-chunk", "doc-b", 1),
            make_chunk("a-chunk", "doc-b", 2),
        ]
        result = self.extractor.extract(text, chunks, docs)
        assert result[0].chunk_ids == sorted(result[0].chunk_ids)
