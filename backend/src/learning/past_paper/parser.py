"""Parse past paper markdown into structured questions using the LLM."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.past_paper.schemas import ParsedQuestion
from src.prompts.manager import PromptManager


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.learning.tests.models import TestQuestion

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_ASSIGN_KEY_QUESTION_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:q|question)[\s_\-#:]*([0-9]+)",
    re.IGNORECASE,
)
_ASSIGN_KEY_ANY_INT_RE = re.compile(r"([0-9]+)")

_SYSTEM_PROMPT_BASE = """\
You are an expert exam question extractor.
Given the markdown content of an exam past paper, extract ALL questions.

For questions that require a graphical answer — e.g. "draw", "sketch", \
"construct", "plot a graph", "complete the diagram", "shade the region", \
"label the diagram" — include the question but set "requires_diagram": true. \
These are shown to the student with a self-marking UI.

IMPORTANT: Preserve ALL LaTeX / math notation exactly as it appears in the \
source markdown. Keep $…$ and $$…$$ delimiters intact. Do NOT convert LaTeX \
to plain text (e.g. keep $\\frac{1}{2}$ — do not write 1/2). This applies to \
question, model_answer, hint, context, and options fields.

Return a JSON array where each element has exactly these fields:
  - "question": string (the question text only — do not embed tables or images here. Preserve LaTeX. \
The question MUST NOT repeat any text you have placed in `context`. Put the stem, passage, or stimulus \
in `context` only; the `question` field contains only the imperative or instruction \
(e.g. "Calculate the multiplier", "With reference to Figure 4, explain…"). \
MCQ SENTENCE-COMPLETION PREFIX: if the MCQ options are sentence fragments that grammatically \
complete a prefix statement rather than standing alone (e.g. options are "fell in 2015", \
"fell throughout the time period shown" completing "UK household savings as a percentage of \
household disposable income:"), that prefix MUST be appended to the `question` field, \
on a new line after the imperative. NEVER drop it. NEVER put it in `options`. \
Example — question: "With reference to the chart above, which one of the following is \
correct?\n\nUK household savings as a percentage of household disposable income:", \
options: ["fell in 2015", "fell throughout the time period shown", …].)
  - "model_answer": string (complete correct answer. Preserve LaTeX.)
  - "mark_scheme": string or null (verbatim marking guidance — null for mcq, null if not in mark scheme)
  - "sources": array of strings (topic areas or syllabus references, may be empty)
  - "context": string or null — CRITICAL field. Read EVERY question carefully and ask: \
"Is there ANY stimulus material — a table, figure, image, diagram, graph, data set, \
equation, definition, scenario, statement, isotope/formula notation, or passage — that \
the student must read in order to answer the imperative?" If YES, you MUST include \
that material here. This applies whether the stimulus appears elsewhere in the paper \
OR inline within the same numbered question block, immediately before the imperative. \
EXAMPLE: "Two isotopes of iodine are ¹²⁵₅₃I and ¹³¹₅₃I. Determine, for these two \
isotopes, the difference between the constituents of the nuclei." — here the first \
sentence is the stem and MUST go into `context`; only "Determine, for these two \
isotopes, the difference between the constituents of the nuclei." goes into `question`. \
Never drop the stem. A student taking this test sees ONLY the question and context \
fields — if you leave context null when the question references stimulus material, \
the student cannot answer it. When in doubt, INCLUDE context. \
IMPORTANT: questions are often grouped — e.g. questions 2(a), 2(b), 2(c) all \
share the same table/figure/scenario introduced before 2(a). If a later \
sub-question relies on context from an earlier one, you MUST duplicate that context \
for every sub-question that needs it. Each question is displayed independently. \
INCLUDE-ALL POLICY: For each question, include ALL source materials that were \
available to students for that question in the original exam paper, not only the \
ones you think are most relevant. If a question is grouped under an extract, table, \
or figure cluster, copy every block from that cluster — students may need to \
cross-reference. Better to include too much than too little. \
DO NOT DUPLICATE: text that you place inside any context block MUST NOT also appear \
in the `question` field. Move passages, tables, figures, captions, and stimulus text \
to `context` only — leave the imperative/instruction in `question`. \
NO ANSWER OPTIONS IN CONTEXT: for MCQ questions, the answer choices belong ONLY in \
the `options` array. NEVER copy the MCQ options ("A …", "B …", "It is greater than …") \
or their tick-box markers ("□", "☐", "[ ]") into the `context` field. The `context` \
field is for stimulus material (passages, figures, tables, scenarios) — never the \
answer choices, never instructions like "Tick one box." or "Select one answer.". \
\
FORMAT context as a sequence of typed blocks using this exact syntax: \
\
  ::: text [Extract A — title of the passage] \
  The passage text goes here. \
  ::: \
  \
  ::: figure [Figure 1 — caption describing the image or table] \
  ![alt text](image_url) \
  ::: \
  \
  ::: figure [Table 1 — caption] \
  | col1 | col2 | \
  |------|------| \
  | a    | b    | \
  ::: \
  \
Use type "text" for written passages and extracts. \
Use type "figure" for images (![alt](url)), diagrams, charts, and markdown tables. \
BLOCK CLOSURE IS MANDATORY: every block that opens with "::: type [...]" or \
"::: type" MUST be closed with a line containing exactly ":::" before the next \
block opens or the context ends. Never leave a block open. Never put two openers \
back-to-back without a closing ":::" in between. The frontend will render raw \
":::" markers as text if a block is not closed properly. \
The title inside [ ] is the label exactly as it appears in the paper (e.g. "Extract A", \
"Figure 2", "Table 1 — Data set"). If the paper has no visible label for that block, \
omit the brackets entirely — write "::: text" or "::: figure" with no [ ] at all. \
NEVER invent or generate a title that does not appear in the original paper. \
SEPARATE NUMBERING: figures and tables have INDEPENDENT numbering schemes in the \
paper. "Figure 3" and "Table 3" are different objects. Never reuse the same number \
for both kinds. Never label a table as "Figure" or a figure as "Table" — copy the \
exact label from the paper. If the paper labels diagrams as "Figure" and tables as \
"Table", preserve that exactly. \
LABEL FORMAT: when a label appears in the paper, write the title as \
"<Kind> <Number> — <caption>" where <Kind> is "Figure", "Table", or "Extract", \
<Number> is the literal identifier ("1", "2", "A", "B", "3a"), and <caption> is the \
paper's caption text after an em-dash. Example: "[Figure 4 — Income tax rates for \
2023–24]" or "[Extract B — Inflation outlook]". Use this exact formatting. \
Omit the caption only when the paper genuinely has no caption text. \
NO SOURCE CITATIONS: do NOT include "(Source ...)", "(Source: adapted from ...)", \
"(adapted from ...)", attribution lines, or any other source citations or copyright \
notices inside any block. Strip them from the passage text before placing it in the \
block. \
Set context to null only if the question requires no external material at all.
  - "type": "mcq" if multiple choice, otherwise "short"
  - "options": array of strings or null (only for mcq — the answer choices A, B, C, D)
  - "correct_option_index": integer (REQUIRED for mcq — 0-based index of the correct answer in "options". You MUST always determine the correct answer for every MCQ question. Use your expert knowledge if the paper does not state the answer explicitly.) null only for non-mcq.
  - "hint": string or null (a helpful hint for a student, generated by you)
  - "points": integer (marks for this question, default 1 if not stated)
  - "question_number": string or null — the original question label exactly as it appears \
in the paper (e.g. "1", "2(a)", "3b", "Q4", "Part ii"). Copy it verbatim. Set to null \
only if the paper has no visible question numbering. \
IMPORTANT: do NOT include the question label inside the "question" or "context" fields — \
strip it from the question text. The label belongs ONLY in this field.
  - "requires_diagram": boolean — true if the question requires a drawn/plotted/sketched \
answer that cannot be typed. Default false.

Output ONLY the JSON array inside a ```json ... ``` code fence. No prose outside it.\
"""

_MARK_SCHEME_INSTRUCTION_WITHOUT = 'For "mark_scheme": ALWAYS set to null. Do NOT generate, invent, or paraphrase any marking guidance.'

_MARK_SCHEME_INSTRUCTION_WITH = (
    "A separate mark scheme document is provided after the past paper. "
    'For "mark_scheme": match each question by its number/part label to the corresponding entry in '
    "the mark scheme document and copy that entry's text VERBATIM — do not paraphrase, summarise, "
    "or add anything. Set to null if no corresponding entry can be found, or if the question type "
    'is "mcq". NEVER generate or invent marking guidance.'
)

_REPARSE_MARK_SCHEME_SYSTEM = """\
You are an expert exam marker. You receive a numbered list of exam questions \
(each with its model answer, mark allocation, and sometimes context) and an \
official mark scheme document for the same exam.

Your ONLY task: for each question, find the corresponding entry in the mark \
scheme and extract the marking guidance VERBATIM.

HOW TO MATCH:
- The question numbers in the input ('Question 1', 'Question 2', …) are \
  sequential labels — they do NOT correspond to the mark scheme's own \
  numbering (e.g. '25.1', '01.2', '7(a)').
- Match by CONTENT: read the question text and its model answer, then find \
  the mark scheme entry that covers the same topic, concept, or calculation. \
  The model answer is especially useful — look for mark scheme entries whose \
  accepted answers overlap with the model answer provided.
- Use the mark allocation (marks) as a secondary signal — a 3-mark question \
  likely matches a 3-mark entry in the mark scheme.
- Copy the matching mark scheme text VERBATIM. Do not paraphrase or summarise.
- Return null ONLY for MCQ questions or if genuinely no match is found.
- You MUST try hard to match every short-answer question. Most questions \
  WILL have a corresponding mark scheme entry.

Return a JSON array with one element per question, in the same order as the \
input. Each element is either a string (the verbatim mark scheme text) or null.

Example: ["Award 1 mark for …", null, "Accept any two of: …", null]

Output ONLY the JSON array inside a ```json … ``` code fence. No other text.\
"""


_RECOVER_JSON_SYSTEM = """\
You are a JSON repair assistant.
The text below is a JSON value that failed to parse due to a syntax error \
(e.g. trailing comma, truncated output, unquoted key, missing bracket).

Your ONLY task: output the corrected, valid JSON. Do NOT add, remove, or change \
any data values — fix syntax only.

Output ONLY the corrected JSON inside a ```json ... ``` code fence. No prose.\
"""

_ASSIGN_MARK_SCHEME_SYSTEM = """\
You are an expert exam marker.
You are given a numbered list of exam questions and a mark scheme document.
Your task is to find the marking guidance for each question by reading and \
understanding the question content, then locating the matching entry in the \
mark scheme document.

How to match:
- The "index" values (0, 1, 2, …) are internal identifiers — do NOT look for \
  these numbers in the mark scheme.
- The mark scheme uses its own numbering (e.g. "1", "2(a)", "Q3b"). \
  Identify which mark scheme entry corresponds to each question by \
  comparing the question TEXT to the mark scheme structure and content.
- Copy the matching mark scheme text VERBATIM — do not paraphrase or summarise.
- Set the value to null only if you genuinely cannot find a corresponding entry.

Output format:
Return a JSON object. Each key is a question's "index" value as a string. \
Each value is the verbatim mark scheme text, or null.
You MUST include EVERY provided question index in your output, even as null.

Example: {"0": "Award 1 mark for…", "1": null, "2": "Accept any two of…"}

Output ONLY the JSON object inside a ```json … ``` code fence. No prose outside it.\
"""



class PastPaperParseError(Exception):
    """Raised when the LLM cannot produce a valid question list."""


class PastPaperParser:
    def __init__(
        self,
        llm: YandexGPTLLMGateway,
        usage_service: object | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._llm = llm
        self._usage_service = usage_service
        self._current_user_id: object | None = None
        self._pm = prompt_manager

    async def parse(
        self,
        markdown: str,
        mark_scheme_markdown: str | None = None,
    ) -> list[ParsedQuestion]:
        """Send markdown (and optional mark scheme) to the LLM and return ParsedQuestion list."""
        if mark_scheme_markdown:
            base = self._pm.get("past_paper", "parser_system") if self._pm else _SYSTEM_PROMPT_BASE
            instr = self._pm.get("past_paper", "mark_scheme_instruction_with") if self._pm else _MARK_SCHEME_INSTRUCTION_WITH
            system = f"{base}\n{instr}"
            user_content = (
                f"## Past Paper\n\n{markdown}\n\n"
                f"## Mark Scheme\n\n{mark_scheme_markdown}"
            )
        else:
            base = self._pm.get("past_paper", "parser_system") if self._pm else _SYSTEM_PROMPT_BASE
            instr = self._pm.get("past_paper", "mark_scheme_instruction_without") if self._pm else _MARK_SCHEME_INSTRUCTION_WITHOUT
            system = f"{base}\n{instr}"
            user_content = f"Extract all questions from this past paper:\n\n{markdown}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        try:
            raw, _usage = await self._llm.chat_complete(messages, reasoning_level="off")
            if self._usage_service and self._current_user_id:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="past_paper", usage=_usage,
                )
        except Exception as exc:
            raise PastPaperParseError(f"LLM call failed: {exc}") from exc

        try:
            return _parse_llm_output(raw)
        except PastPaperParseError as first_exc:
            logger.warning(
                "Initial parse failed (%s) — attempting JSON recovery", first_exc
            )
            try:
                raw = await self._recover_json(raw)
                return _parse_llm_output(raw)
            except Exception as recovery_exc:
                logger.error("JSON recovery also failed: %s", recovery_exc)
                raise first_exc

    async def _recover_json(self, raw: str) -> str:
        """Ask the LLM to fix a malformed JSON response and return the repaired text."""
        recover_system = self._pm.get("past_paper", "recover_json_system") if self._pm else _RECOVER_JSON_SYSTEM
        messages = [
            {"role": "system", "content": recover_system},
            {"role": "user", "content": f"Fix this JSON:\n\n{raw}"},
        ]
        recovered, _ = await self._llm.chat_complete(messages, reasoning_level="off")
        return recovered

    async def reparse_with_mark_scheme(
        self,
        questions: list,  # list[TestQuestion] — duck-typed to avoid circular import
        mark_scheme_markdown: str,
    ) -> list[str | None]:
        """Assign mark schemes to stored questions using a separately uploaded mark scheme.

        Reconstructs a numbered question list from stored data and sends it
        alongside the mark scheme to the LLM with a dedicated matching prompt
        (NOT the extraction prompt). Returns a list of verbatim mark scheme
        strings (or None) in the same order as `questions` sorted by index.
        """
        sorted_qs = sorted(questions, key=lambda q: q.index)

        # Build a rich question list with all available context so the LLM
        # can match by content (question text + model answer + marks).
        q_parts: list[str] = []
        for i, q in enumerate(sorted_qs, start=1):
            marks = getattr(q, "points", 1) or 1
            tag = f"Question {i} (type: {q.type}, marks: {marks})"
            q_parts.append(tag)
            q_parts.append(q.question)
            if q.type == "mcq" and q.options:
                for j, opt in enumerate(q.options):
                    q_parts.append(f"   {chr(65 + j)}. {opt}")
            model_answer = getattr(q, "model_answer", None)
            if model_answer:
                q_parts.append(f"Model answer: {model_answer}")
            context = getattr(q, "context", None)
            if context:
                q_parts.append(f"Context: {context}")
            q_parts.append("")

        user_content = (
            f"## Questions\n\n{''.join(line + chr(10) for line in q_parts)}\n"
            f"## Mark Scheme\n\n{mark_scheme_markdown}"
        )
        reparse_system = self._pm.get("past_paper", "reparse_mark_scheme_system") if self._pm else _REPARSE_MARK_SCHEME_SYSTEM
        messages = [
            {"role": "system", "content": reparse_system},
            {"role": "user", "content": user_content},
        ]
        try:
            raw, _usage = await self._llm.chat_complete(messages, reasoning_level="medium")
            if self._usage_service and self._current_user_id:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="past_paper", usage=_usage,
                )
        except Exception as exc:
            raise PastPaperParseError(f"LLM call failed: {exc}") from exc

        logger.info("reparse_with_mark_scheme raw LLM response: %s", raw[:1000])

        # Parse the flat JSON array of strings / nulls.
        match = _JSON_FENCE_RE.search(raw)
        json_str = match.group(1).strip() if match else raw.strip()
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise PastPaperParseError(
                f"Mark scheme reparse returned invalid JSON: {exc}\n"
                f"Raw: {raw[:300]}"
            ) from exc
        if not isinstance(data, list):
            raise PastPaperParseError(
                f"Expected JSON array, got {type(data).__name__}"
            )
        ms_values: list[str | None] = [
            entry.strip() if isinstance(entry, str) and entry.strip() else None
            for entry in data
        ]
        non_null = sum(1 for v in ms_values if v)
        logger.info(
            "reparse_with_mark_scheme: %d entries, %d with mark_scheme. "
            "First non-null: %s",
            len(ms_values),
            non_null,
            next((v[:200] for v in ms_values if v), "NONE"),
        )
        return ms_values

    async def assign_mark_schemes(
        self,
        questions: list[TestQuestion],
        mark_scheme_markdown: str,
    ) -> dict[int, str | None]:
        """Match mark scheme entries to existing questions.

        Returns a mapping of *index* → mark scheme text (or None).
        The LLM receives a list of question entries and the mark scheme
        document, then maps each question number to its marking guidance.
        """
        question_rows = "\n\n".join(
            (
                f"- index: {q.index}\n"
                f"  type: {q.type}\n"
                f"  marks: {getattr(q, 'points', 1) or 1}\n"
                f"  question: {q.question}\n"
                f"  model_answer: {q.model_answer or ''}"
            )
            for q in questions
        )
        user_content = (
            f"## Questions\n\n{question_rows}\n\n"
            f"## Mark Scheme\n\n{mark_scheme_markdown}"
        )
        assign_system = self._pm.get("past_paper", "assign_mark_scheme_system") if self._pm else _ASSIGN_MARK_SCHEME_SYSTEM
        messages = [
            {"role": "system", "content": assign_system},
            {"role": "user", "content": user_content},
        ]
        try:
            raw, _usage = await self._llm.chat_complete(messages, reasoning_level="medium")
            if self._usage_service and self._current_user_id:
                self._usage_service.log_usage_fire_and_forget(
                    user_id=self._current_user_id, feature="past_paper", usage=_usage,
                )
        except Exception as exc:
            raise PastPaperParseError(f"LLM call failed: {exc}") from exc

        return _parse_mark_scheme_assignment(raw, questions)


def _parse_mark_scheme_assignment(
    raw: str,
    questions: list[TestQuestion],
) -> dict[int, str | None]:
    """Parse the LLM's JSON object into an index → mark_scheme map."""
    match = _JSON_FENCE_RE.search(raw)
    json_str = match.group(1).strip() if match else raw.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise PastPaperParseError(
            f"LLM returned invalid JSON: {exc}\nRaw output (first 500 chars): {raw[:500]}"
        ) from exc

    if not isinstance(data, dict):
        raise PastPaperParseError(f"Expected JSON object, got {type(data).__name__}")

    result: dict[int, str | None] = {q.index: None for q in questions}
    index_set = {q.index for q in questions}
    ordered_indexes = [q.index for q in sorted(questions, key=lambda q: q.index)]
    one_based_to_index = {
        i + 1: idx for i, idx in enumerate(ordered_indexes)
    }
    numeric_mode = _infer_assignment_numeric_mode(data, ordered_indexes)

    for raw_key, raw_value in data.items():
        target_index = _resolve_assignment_target_index(
            raw_key=raw_key,
            index_set=index_set,
            one_based_to_index=one_based_to_index,
            numeric_mode=numeric_mode,
        )
        if target_index is None:
            continue
        normalized = _normalize_assignment_value(raw_value)
        if normalized and not result.get(target_index):
            result[target_index] = normalized

    return result


def _infer_assignment_numeric_mode(
    data: dict[str, object],
    ordered_indexes: list[int],
) -> str:
    numeric_keys = [int(k.strip()) for k in data if str(k).strip().isdigit()]
    if not numeric_keys:
        return "mixed"
    if 0 in numeric_keys:
        return "index"
    max_index = max(ordered_indexes) if ordered_indexes else -1
    if max(numeric_keys) > max_index:
        return "one_based"
    # Backward-compatible default for plain numeric keys emitted by the old prompt.
    return "one_based"


def _resolve_assignment_target_index(
    raw_key: object,
    index_set: set[int],
    one_based_to_index: dict[int, int],
    numeric_mode: str,
) -> int | None:
    key = str(raw_key).strip()
    if not key:
        return None

    if key.isdigit():
        numeric_key = int(key)
        if numeric_mode == "one_based":
            if numeric_key in one_based_to_index:
                return one_based_to_index[numeric_key]
            if numeric_key in index_set:
                return numeric_key
        else:
            if numeric_key in index_set:
                return numeric_key
            if numeric_key in one_based_to_index:
                return one_based_to_index[numeric_key]
        return None

    question_match = _ASSIGN_KEY_QUESTION_RE.search(key)
    if question_match:
        numeric_key = int(question_match.group(1))
        if numeric_key in index_set:
            return numeric_key
        if numeric_key in one_based_to_index:
            return one_based_to_index[numeric_key]

    any_int_match = _ASSIGN_KEY_ANY_INT_RE.search(key)
    if any_int_match:
        numeric_key = int(any_int_match.group(1))
        if numeric_key in index_set:
            return numeric_key
        if numeric_key in one_based_to_index:
            return one_based_to_index[numeric_key]

    return None


def _normalize_assignment_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    normalized = str(value).strip()
    return normalized or None


_OPTION_LETTER_RE = re.compile(r"^[A-Da-d]$")


def _infer_correct_option_index(
    model_answer: str | None,
    options: list[str],
) -> int | None:
    """Try to determine the correct option index from model_answer text.

    Handles cases like:
      - "A", "B", "C", "D" (letter only)
      - "A. some text" (letter prefix)
      - Exact or substring match against option text
    """
    if not model_answer or not options:
        return None

    answer = model_answer.strip()

    # Check if answer is a single letter A-D
    if _OPTION_LETTER_RE.match(answer):
        idx = ord(answer.upper()) - ord("A")
        if 0 <= idx < len(options):
            return idx

    # Check if answer starts with a letter like "A." or "A:"
    if len(answer) >= 2 and answer[0].upper() in "ABCD" and answer[1] in ".):- ":
        idx = ord(answer[0].upper()) - ord("A")
        if 0 <= idx < len(options):
            return idx

    # Exact match against option text (case-insensitive)
    answer_lower = answer.lower()
    for i, opt in enumerate(options):
        if opt.strip().lower() == answer_lower:
            return i

    # Substring match — answer contained in option or option contained in answer
    for i, opt in enumerate(options):
        opt_lower = opt.strip().lower()
        if opt_lower and (opt_lower in answer_lower or answer_lower in opt_lower):
            return i

    return None


_GRAPHICAL_RE = re.compile(
    r"(?:^|\.\s+)(?:draw|sketch|construct|shade|label the diagram)"
    r"(?!\s+(?:a conclusion|attention|upon|from|on the fact|a table|a comparison))"
    r"|"
    r"\b(?:complete the (?:diagram|ray diagram)|"
    r"plot .* on the (?:graph|grid|axes)|"
    r"add .* to the diagram|mark .* on the diagram|"
    r"on the (?:graph|grid|axes|diagram),? (?:draw|sketch|plot|mark|shade))",
    re.IGNORECASE,
)


def _is_graphical_question(question_text: str) -> bool:
    """Return True if the question requires a graphical answer (drawing, plotting, etc.)."""
    return bool(_GRAPHICAL_RE.search(question_text))


def _parse_llm_output(raw: str) -> list[ParsedQuestion]:
    match = _JSON_FENCE_RE.search(raw)
    json_str = match.group(1).strip() if match else raw.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise PastPaperParseError(
            f"LLM returned invalid JSON: {exc}\nRaw output (first 500 chars): {raw[:500]}"
        ) from exc

    if not isinstance(data, list):
        raise PastPaperParseError(f"Expected JSON array, got {type(data).__name__}")

    questions: list[ParsedQuestion] = []
    for i, item in enumerate(data):
        try:
            q = ParsedQuestion.model_validate(item)
            if q.type != "mcq" and (q.requires_diagram or _is_graphical_question(q.question)):
                q.is_unsupported = True
            else:
                q.is_unsupported = False
            # MCQ questions must never have a mark scheme
            if q.type == "mcq":
                q.mark_scheme = None
                # Ensure correct_option_index is always set for MCQs
                if q.correct_option_index is None and q.options:
                    q.correct_option_index = _infer_correct_option_index(
                        q.model_answer, q.options
                    )
            questions.append(q)
        except Exception as exc:
            raise PastPaperParseError(f"Question {i} failed validation: {exc}") from exc

    return questions
