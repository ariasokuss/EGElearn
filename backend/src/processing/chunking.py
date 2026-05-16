"""Document chunking pipeline: tokenizer, line markers, prompts, splitter,
topic clustering (LLM), and semantic chunking (embeddings).

Consolidates DSA file-processing-service modules into a single async-first module
that reuses the backend's YandexGPTLLMGateway and VoyageEmbeddingService.
"""

import json
import logging
import re
from dataclasses import dataclass

import numpy as np
import tiktoken

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.core.voyage import VoyageEmbeddingService
from src.prompts.manager import PromptManager
from src.processing.types import ClusterSegment, SemanticChunk, TopicCluster, Window

logger = logging.getLogger(__name__)


_ENCODERS: dict[str, tiktoken.Encoding] = {}


def get_encoder(encoding: str = "cl100k_base") -> tiktoken.Encoding:
    """Return a cached tiktoken encoder for *encoding*."""
    if encoding not in _ENCODERS:
        _ENCODERS[encoding] = tiktoken.get_encoding(encoding)
    return _ENCODERS[encoding]


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    return len(get_encoder(encoding).encode(text))


_LINE_MARKER_RE = re.compile(r"<<(\d+)>>")
_PAGE_MARKER_RE = re.compile(r"^\[PAGE\s+(\d+)\]", re.MULTILINE)


def insert_line_markers(text: str, start_at: int = 1) -> str:
    """Prepend ``<<N>>`` to every line."""
    lines = text.split("\n")
    return "\n".join(f"<<{start_at + i}>>{line}" for i, line in enumerate(lines))


def parse_line_markers(marked_text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line in marked_text.split("\n"):
        m = _LINE_MARKER_RE.match(line)
        if m:
            result.append((int(m.group(1)), line[m.end() :]))
    return result


def extract_text_by_lines(marked_text: str, start_line: int, end_line: int) -> str:
    return "\n".join(
        content
        for num, content in parse_line_markers(marked_text)
        if start_line <= num <= end_line
    )


def preview_with_ending(text: str, head_len: int = 150, tail_len: int = 150) -> str:
    text = text.strip()
    if len(text) <= head_len + tail_len + 20:
        return text
    return text[:head_len] + "\n[...]\n" + text[-tail_len:]


def build_page_map(text: str) -> dict[int, int]:
    """Map line numbers (1-based) → page number from ``[PAGE N]`` markers."""
    page_map: dict[int, int] = {}
    current_page = 0
    for i, line in enumerate(text.split("\n")):
        line_num = i + 1
        m = _PAGE_MARKER_RE.match(line.strip())
        if m:
            current_page = int(m.group(1))
        if current_page > 0:
            page_map[line_num] = current_page
    return page_map


def get_pages_for_line_range(
    page_map: dict[int, int], start_line: int, end_line: int
) -> list[int]:
    if not page_map:
        return []
    pages: set[int] = set()
    for line_num in range(start_line, end_line + 1):
        if line_num in page_map:
            pages.add(page_map[line_num])
    return sorted(pages)


LINE_CLUSTERING_SYSTEM_PROMPT = """\
You are a document analysis assistant. You will receive a text chunk with \
line markers. Each line starts with <<N>> where N is the line number (1-based).

Your job is to split this text into thematic clusters. A cluster is a \
self-sustaining unit of learning material — a block that could appear as a \
single node in a study roadmap. Each cluster should cover one focused topic \
deeply enough that exam questions can be generated from it.

{carry_over_instruction}

WHAT MAKES A GOOD CLUSTER:
- A single concept, model, framework, or technique with its definitions, \
examples, properties, and discussion. E.g. if a section covers 4 models of \
risk, keep all 4 in ONE cluster so a comparison question can be generated.
- A worked example or case study with its setup, analysis, and conclusions.
- A proof or derivation with its statement, steps, and implications.
- Prefer more granular splits over large blobs, but never split a concept \
that needs to stay together. Clusters can be any size — small or large — \
whatever the topic naturally requires.
- If the text is lecture-like, conversational, or transcript-like, split when \
the teaching focus changes to a new concept, example, derivation, case study, \
question/answer exchange, or practical application. Do not collapse a whole \
lecture into one cluster if it clearly covers multiple teachable subtopics.

CONTENT TYPES:
- "study": learning material with testable content (concepts, formulas, methods, \
theories, examples, case studies). This is the default.
- "admin": administrative content not useful for exam questions but useful for \
context (course logistics, assignment details, grading policy, schedules). \
Mark as admin, not trash.
- "trash": content with zero educational or administrative value (chitchat, \
filler, repeated headers/footers, blank sections, purely motivational text).

Return a JSON object with a single key "clusters" whose value is a list of \
objects in reading order, each with:
- "topic": theme description summarizing the cluster's content (200-400 words). \
Be specific — mention key terms, models, formulas covered.
- "start_line": line number where this cluster begins (integer)
- "end_line": line number where this cluster ends (integer, inclusive)
- "content_type": "study" or "admin" or "trash"
- "content_quality": integer from 1 to 5 — rate how good this content is for \
generating exam/test questions. 5 = specific facts, concepts, formulas, \
definitions, or methods that directly form exam questions. 4 = solid learning \
material with testable content. 3 = moderate — some testable content mixed with \
general discussion. 2 = mostly overviews or context with few testable details. \
1 = no testable content.

CRITICAL RULES:
- Clusters must be contiguous: first at line {first_line}, last at line {last_line}.
- Each cluster's end_line = next cluster's start_line - 1 (no gaps, no overlaps).
- SPLIT when the subject shifts to a clearly different area.
- Do NOT split a concept across clusters — keep related material together.
- If the chunk contains several teachable subtopics, most valid answers will \
have multiple clusters. Return a single cluster only when the whole chunk \
genuinely covers one coherent topic.
- Return ONLY valid JSON, no explanation.
"""

_CARRY_OVER_INSTRUCTION = """\
IMPORTANT: You will also receive a PREVIOUS CONTEXT block without line markers. \
That block is already processed and is provided only for thematic continuity. \
Only create clusters for the numbered lines in the NEW TEXT block, starting at line {first_line}."""

_NO_CARRY_OVER_INSTRUCTION = """\
There is no carry-over. Your first cluster starts at line {first_line}."""

LINE_CLUSTERING_USER_PROMPT = """\
Identify thematic clusters in this text. Use the <<N>> markers for start_line and end_line.

{text}"""


def _format_clustering_system(
    pm: PromptManager | None,
    first_line: int,
    last_line: int,
    carry_over_end_line: int | None = None,
) -> str:
    if pm:
        system_tpl = pm.get("processing", "line_clustering_system")
        if carry_over_end_line is not None:
            instr = pm.get_formatted(
                "processing",
                "line_clustering_carry_over_instruction",
                carry_over_end=carry_over_end_line,
                first_line=first_line,
            )
        else:
            instr = pm.get_formatted(
                "processing",
                "line_clustering_no_carry_over_instruction",
                first_line=first_line,
            )
        return system_tpl.format(
            carry_over_instruction=instr,
            first_line=first_line,
            last_line=last_line,
        )
    return format_line_clustering_system_prompt(first_line, last_line, carry_over_end_line)


def _format_clustering_user(pm: PromptManager | None, marked_text: str) -> str:
    if pm:
        return pm.get_formatted("processing", "line_clustering_user", text=marked_text)
    return format_line_clustering_user_prompt(marked_text)


def format_line_clustering_system_prompt(
    first_line: int,
    last_line: int,
    carry_over_end_line: int | None = None,
) -> str:
    if carry_over_end_line is not None:
        instr = _CARRY_OVER_INSTRUCTION.format(
            carry_over_end=carry_over_end_line,
            first_line=first_line,
        )
    else:
        instr = _NO_CARRY_OVER_INSTRUCTION.format(first_line=first_line)
    return LINE_CLUSTERING_SYSTEM_PROMPT.format(
        carry_over_instruction=instr,
        first_line=first_line,
        last_line=last_line,
    )


def format_line_clustering_user_prompt(marked_text: str) -> str:
    return LINE_CLUSTERING_USER_PROMPT.format(text=marked_text)


def format_line_clustering_user_prompt_with_context(
    marked_text: str,
    carry_over_text: str,
) -> str:
    return (
        "Identify thematic clusters in the NEW TEXT block. "
        "Use the PREVIOUS CONTEXT block only for continuity.\n\n"
        "[PREVIOUS CONTEXT]\n"
        f"{carry_over_text}\n\n"
        "[NEW TEXT]\n"
        f"{marked_text}"
    )


def split_to_windows(
    text: str,
    max_tokens: int = 40_000,
    encoding: str = "cl100k_base",
) -> list[Window]:
    """Split *text* into windows of at most *max_tokens* tokens."""
    total = count_tokens(text, encoding)
    if total <= max_tokens:
        return [Window(text=text, token_count=total)]

    enc = get_encoder(encoding)
    tokens = enc.encode(text)
    windows: list[Window] = []
    start = 0

    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        segment = enc.decode(tokens[start:end])

        if end < len(tokens):
            nl = segment.rfind("\n")
            if nl > len(segment) * 0.9:
                segment = segment[: nl + 1]
                end = start + len(enc.encode(segment))

        trimmed = segment.strip()
        if trimmed:
            windows.append(
                Window(text=trimmed, token_count=count_tokens(trimmed, encoding))
            )
        start = end

    return windows


class TopicClusteringService:
    """Identify thematic clusters in document windows using an LLM."""

    def __init__(
        self,
        llm: YandexGPTLLMGateway,
        model: str,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._pm = prompt_manager

    async def identify_clusters(
        self,
        windows: list[Window],
        *,
        max_retries: int = 3,
    ) -> list[TopicCluster]:
        """Run line-based clustering over all *windows* with carry-over."""
        clusters: list[TopicCluster] = []
        carry_over: dict | None = None

        for i, window in enumerate(windows):
            marked = insert_line_markers(window.text, start_at=1)
            line_count = marked.count("\n") + 1
            first_line = 1
            last_line = line_count

            system = _format_clustering_system(
                self._pm,
                first_line=first_line,
                last_line=last_line,
                carry_over_end_line=1 if carry_over else None,
            )
            user = (
                format_line_clustering_user_prompt_with_context(
                    marked, carry_over["text"]
                )
                if carry_over
                else _format_clustering_user(self._pm, marked)
            )

            cluster_results: list[dict] | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    raw, _ = await self._llm.chat_complete(
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        model_override=self._model,
                    )
                    cluster_results = _parse_line_clustering_response(raw)
                    if cluster_results:
                        break
                    logger.warning("Attempt %d: no clusters for window %d", attempt, i)
                except Exception:
                    logger.exception(
                        "Attempt %d: line clustering failed for window %d", attempt, i
                    )

            if not cluster_results:
                cluster_results = [
                    {
                        "topic": "Document content",
                        "start_line": first_line,
                        "end_line": last_line,
                        "content_type": "study",
                        "content_quality": 3,
                    }
                ]

            for cr in cluster_results:
                segs = _build_segments_from_line_range(
                    cr["start_line"],
                    cr["end_line"],
                    0,
                    "",
                    0,
                    window.uuid,
                    marked,
                    include_preview=True,
                )
                if not segs:
                    continue
                clusters.append(
                    TopicCluster(
                        topic_description=cr["topic"],
                        segments=segs,
                        window_uuids=list({s.window_uuid for s in segs}),
                        content_type=cr.get("content_type", "study"),
                        content_quality=cr.get("content_quality", 3),
                    )
                )

            if cluster_results:
                carry_result = cluster_results[-1]
                carry_text = extract_text_by_lines(
                    marked,
                    carry_result["start_line"],
                    carry_result["end_line"],
                )
                carry_text_lines = carry_text.splitlines()
                carry_text = "\n".join(carry_text_lines[-60:]).strip()
                carry_over = {
                    "text": carry_text,
                }
            else:
                carry_over = None

        return clusters


def _parse_line_clustering_response(raw: str) -> list[dict] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(raw)
    cluster_list = data.get("clusters", [])
    result: list[dict] = []
    for c in cluster_list:
        start = c.get("start_line")
        end = c.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start >= end:
            continue
        cq = c.get("content_quality", 3)
        if not isinstance(cq, int) or cq < 1 or cq > 5:
            cq = 3
        result.append(
            {
                "topic": str(c.get("topic", "")),
                "start_line": start,
                "end_line": end,
                "content_type": c.get("content_type", "study"),
                "content_quality": cq,
            }
        )
    return result if result else None


def _build_segments_from_line_range(
    start_line: int,
    end_line: int,
    carry_boundary: int,
    prev_window_uuid: str,
    prev_window_line_count: int,
    curr_window_uuid: str,
    marked_text: str,
    include_preview: bool = False,
) -> list[ClusterSegment]:
    segs: list[ClusterSegment] = []

    if carry_boundary > 0 and start_line <= carry_boundary:
        end_in_prev = min(end_line, carry_boundary)
        prev_content = extract_text_by_lines(marked_text, start_line, end_in_prev)
        prev_preview = preview_with_ending(prev_content) if include_preview else ""
        prev_start = max(1, prev_window_line_count - carry_boundary + start_line)
        prev_end = prev_window_line_count - carry_boundary + end_in_prev
        segs.append(
            ClusterSegment(
                window_uuid=prev_window_uuid,
                start_line=prev_start,
                end_line=prev_end,
                preview=prev_preview,
            )
        )
        if end_line > carry_boundary:
            curr_content = extract_text_by_lines(
                marked_text, carry_boundary + 1, end_line
            )
            curr_preview = preview_with_ending(curr_content) if include_preview else ""
            segs.append(
                ClusterSegment(
                    window_uuid=curr_window_uuid,
                    start_line=1,
                    end_line=end_line - carry_boundary,
                    preview=curr_preview,
                )
            )
    else:
        curr_content = extract_text_by_lines(marked_text, start_line, end_line)
        preview = preview_with_ending(curr_content) if include_preview else ""
        segs.append(
            ClusterSegment(
                window_uuid=curr_window_uuid,
                start_line=start_line - carry_boundary,
                end_line=end_line - carry_boundary,
                preview=preview,
            )
        )
    return segs


_PAGE_SEGMENT_RE = re.compile(r"^\[PAGE\s+(\d+)\]\s*$")


@dataclass
class _Segment:
    text: str
    page: int


def _parse_page_segments(text: str, fallback_pages: list[int]) -> list[_Segment]:
    """Split *text* into segments grouped by ``[PAGE N]`` markers."""
    lines = text.split("\n")
    current_page = fallback_pages[0] if fallback_pages else 0
    content_lines: list[tuple[str, int]] = []
    for line in lines:
        m = _PAGE_SEGMENT_RE.match(line.strip())
        if m:
            current_page = int(m.group(1))
        else:
            content_lines.append((line, current_page))

    if not content_lines:
        return []

    segments: list[_Segment] = []
    buf: list[str] = []
    buf_page = content_lines[0][1]

    def _flush() -> None:
        nonlocal buf
        joined = "\n".join(buf).strip()
        if joined:
            segments.append(_Segment(text=joined, page=buf_page))
        buf = []

    for line_text, page in content_lines:
        if page != buf_page:
            if buf:
                _flush()
            buf_page = page
        if not line_text.strip():
            if buf:
                _flush()
            buf_page = page
        else:
            buf.append(line_text)

    _flush()
    return segments


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    denom = float(np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


class SemanticChunkingService:
    """Break clusters into semantic chunks using embedding similarity."""

    def __init__(
        self,
        voyage: VoyageEmbeddingService,
        *,
        percentile: int = 3,
        min_segments: int = 4,
    ) -> None:
        self._voyage = voyage
        self._percentile = percentile
        self._min_segments = min_segments

    async def chunk_cluster(
        self,
        cluster_text: str,
        pages: list[int],
    ) -> list[SemanticChunk]:
        if not cluster_text.strip():
            return []

        segments = _parse_page_segments(cluster_text, pages)
        if not segments:
            return []

        if len(segments) == 1:
            return [SemanticChunk(text=segments[0].text, page=segments[0].page)]

        if len(segments) < self._min_segments:
            return _enforce_page_boundaries([segments])

        texts = [s.text for s in segments if s.text.strip()]
        if not texts:
            return []

        embeddings = await self._voyage.embed_batch(texts, input_type="document")

        if len(embeddings) != len(texts):
            return [SemanticChunk(text=s.text, page=s.page) for s in segments]

        similarities = [
            _cosine_similarity(embeddings[i], embeddings[i + 1])
            for i in range(len(embeddings) - 1)
        ]
        breakpoints = _find_breakpoints(similarities, self._percentile)
        grouped = _group_segments(segments, breakpoints)
        return _enforce_page_boundaries(grouped)


def _find_breakpoints(similarities: list[float], percentile: int = 3) -> set[int]:
    if not similarities:
        return set()
    arr = np.array(similarities)
    threshold = float(np.percentile(arr, percentile))
    return {i for i, sim in enumerate(similarities) if sim <= threshold}


def _group_segments(
    segments: list[_Segment], breakpoints: set[int]
) -> list[list[_Segment]]:
    chunks: list[list[_Segment]] = []
    current: list[_Segment] = []
    for i, seg in enumerate(segments):
        current.append(seg)
        if i in breakpoints:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _enforce_page_boundaries(chunks: list[list[_Segment]]) -> list[SemanticChunk]:
    result: list[SemanticChunk] = []
    for chunk_segs in chunks:
        page_groups: dict[int, list[str]] = {}
        page_order: list[int] = []
        for seg in chunk_segs:
            if seg.page not in page_groups:
                page_groups[seg.page] = []
                page_order.append(seg.page)
            page_groups[seg.page].append(seg.text)

        for page in page_order:
            text = "\n\n".join(page_groups[page])
            if text.strip():
                result.append(SemanticChunk(text=text, page=page))
    return result
