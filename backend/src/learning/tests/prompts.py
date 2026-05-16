"""Prompts for test generation, question allocation, and short-answer grading."""

from __future__ import annotations

from src.prompts.manager import PromptManager

# ── Question allocation ─────────────────────────────────────────────────────

ALLOCATION_SYSTEM = """\
You are a study planner. Given a list of topics with their current mastery \
levels, allocate a specified number of test questions across the topics.

Rules:
- Topics with LOWER mastery should receive MORE questions.
- Some topics may receive 0 questions if the total is less than the number of topics.
- The total must equal the requested question count exactly.
- Return valid JSON only — no markdown, no extra text.

Output schema:
{
  "allocations": [
    {"node_id": "<uuid>", "topic": "<name>", "count": <int>}
  ]
}
"""

ALLOCATION_USER_TEMPLATE = """\
Allocate {total_questions} questions across {num_topics} topics.

Topics:
{topics_list}

Return JSON only.\
"""


def build_allocation_messages(
    total_questions: int,
    topics: list[dict],  # [{"node_id": str, "name": str, "progress": int}]
    pm: PromptManager | None = None,
) -> list[dict[str, str]]:
    topics_list = "\n".join(
        f'- node_id: "{t["node_id"]}", topic: "{t["name"]}", mastery: {t["progress"]}%'
        for t in topics
    )
    return [
        {"role": "system", "content": pm.get("tests", "allocation_system") if pm else ALLOCATION_SYSTEM},
        {
            "role": "user",
            "content": (pm.get("tests", "allocation_user_template") if pm else ALLOCATION_USER_TEMPLATE).format(
                total_questions=total_questions,
                num_topics=len(topics),
                topics_list=topics_list,
            ),
        },
    ]


# ── Question generation ─────────────────────────────────────────────────────

GENERATION_SYSTEM = """\
You are an expert exam question writer. Generate high-quality test questions \
from the provided lesson content.

Rules:
- Mix of MCQ (~60%) and short-answer (~40%) questions.
- MCQ questions: exactly 4 options. Include plausible distractors. \
  The model_answer must explain why the correct option is right AND \
  why each distractor is wrong.
- Short-answer questions: model_answer gives a full ideal response. \
  mark_scheme must always be null — do NOT generate or invent marking guidance.
- Difficulty mix: ~25% easy, ~50% medium, ~25% hard.
- Points: MCQ are ALWAYS exactly 1 mark. Short-answer 2-25 depending on complexity.
- Questions must test understanding, not just recall of text.
- Do NOT copy lesson text verbatim into questions.
- The hint must be 1–2 sentences. Point the student toward the relevant concept, \
definition, or reasoning approach without revealing the answer. Use a direct, \
supportive tone (e.g. "Think about how X relates to Y" or "Recall the definition \
of Z"). Do not start with "Hint:".

You MUST respond with a JSON array only — no markdown fences, no extra text.
Each element:
{
  "question": "<string>",
  "model_answer": "<string>",
  "mark_scheme": "<string or null>",
  "type": "mcq" | "short",
  "options": ["<A>", "<B>", "<C>", "<D>"] | null,
  "correct_option_index": <0-3> | null,
  "hint": "<string>",
  "points": <int>,
  "sources": ["<section ref>"] | null
}
"""

GENERATION_USER_TEMPLATE = """\
Generate exactly {count} questions from this lesson content.
Topic: {topic_name}

--- LESSON CONTENT ---
{lesson_content}
--- END ---

Return a JSON array of {count} question objects. JSON only, no markdown.\
"""


def build_generation_messages(
    topic_name: str,
    lesson_content: str,
    count: int,
    pm: PromptManager | None = None,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": pm.get("tests", "generation_system") if pm else GENERATION_SYSTEM},
        {
            "role": "user",
            "content": (pm.get("tests", "generation_user_template") if pm else GENERATION_USER_TEMPLATE).format(
                count=count,
                topic_name=topic_name,
                lesson_content=lesson_content,
            ),
        },
    ]


# ── Single question generation (for streaming, one at a time) ──────────────

SINGLE_QUESTION_SYSTEM = """\
You are an expert exam question writer. Generate exactly ONE high-quality test \
question from the provided lesson content.

Rules:
- Either MCQ or short-answer (you choose based on the topic).
- MCQ questions: exactly 4 options. Include plausible distractors. \
  The model_answer must explain why the correct option is right AND \
  why each distractor is wrong.
- Short-answer questions: model_answer gives a full ideal response. \
  mark_scheme must always be null — do NOT generate or invent marking guidance.
- Points: MCQ are ALWAYS exactly 1 mark. Short-answer 2-25 depending on complexity.
- The question must test understanding, not just recall of text.
- Do NOT copy lesson text verbatim into the question.
- The hint must be 1–2 sentences. Point the student toward the relevant concept, \
definition, or reasoning approach without revealing the answer. Use a direct, \
supportive tone (e.g. "Think about how X relates to Y" or "Recall the definition \
of Z"). Do not start with "Hint:".
- The question MUST be different from all previously generated questions listed below.

You MUST respond with a single JSON object only — no markdown fences, no extra text.
Schema:
{
  "question": "<string>",
  "model_answer": "<string>",
  "mark_scheme": "<string or null>",
  "type": "mcq" | "short",
  "options": ["<A>", "<B>", "<C>", "<D>"] | null,
  "correct_option_index": <0-3> | null,
  "hint": "<string>",
  "points": <int>,
  "sources": ["<section ref>"] | null
}
"""

SINGLE_QUESTION_USER_TEMPLATE = """\
Generate 1 question (question {current} of {total}) for this topic.
Topic: {topic_name}

--- LESSON CONTENT ---
{lesson_content}
--- END ---

{previous_block}\
Return a single JSON object. JSON only, no markdown.\
"""


def build_single_question_messages(
    topic_name: str,
    lesson_content: str,
    current: int,
    total: int,
    previous_questions: list[str],
    pm: PromptManager | None = None,
) -> list[dict[str, str]]:
    if previous_questions:
        prev_list = "\n".join(
            f"  {i + 1}. {q}" for i, q in enumerate(previous_questions)
        )
        previous_block = (
            f"Previously generated questions for this topic (DO NOT repeat these):\n"
            f"{prev_list}\n\n"
        )
    else:
        previous_block = ""

    return [
        {"role": "system", "content": pm.get("tests", "single_question_system") if pm else SINGLE_QUESTION_SYSTEM},
        {
            "role": "user",
            "content": (pm.get("tests", "single_question_user_template") if pm else SINGLE_QUESTION_USER_TEMPLATE).format(
                current=current,
                total=total,
                topic_name=topic_name,
                lesson_content=lesson_content,
                previous_block=previous_block,
            ),
        },
    ]


# ── Short-answer grading ───────────────────────────────────────────────────

GRADING_SYSTEM = """\
You are an exam marker. Grade the student's answer fairly against the \
mark scheme. Award partial credit where justified.

Rules:
- Compare the student's answer point-by-point against the mark scheme.
- Award marks only for demonstrated understanding, not for restating the question.
- Be generous with alternative correct phrasings but strict on factual errors.
- The feedback should be 1-2 sentences focused ONLY on what the student did \
  well — the strong points of their answer. Do NOT mention anything missing, \
  weak, or wrong here. If the student earned no marks, return an empty string.
- The recommendations should explain specifically what the student could have \
  added or changed to earn more marks — e.g. "You could earn more points if \
  you included the full calculation / mentioned definition X / explained the \
  link between Y and Z." Keep it 1-2 sentences. If the student earned full \
  marks (earned_marks == max_marks), return an empty string.
- Include feedback_notes ONLY for high-impact conceptual mistakes that materially \
  reduced marks. Do not create cards for minor wording issues or tiny slips.
- Return at most 2 feedback_notes total. Prefer 1 note when one root misconception \
  explains multiple misses.
- Merge overlapping mistakes into one note instead of splitting them.
- Use only these severities in feedback_notes: moderate or critical. \
  If there are no substantial mistakes, return an empty array.
- For each feedback_note:
  - "mistake": 2–4 sentences. Describe what the student got wrong, reference the \
    question context, and explain why their answer is incorrect.
  - "correction": 1 short sentence. State only the correct answer or fact — \
    nothing more. E.g. "The answer is X." or "X equals Y."

You MUST respond with valid JSON only — no markdown, no extra text.
Schema:
{
  "earned_marks": <int 0 to max_marks>,
  "feedback": "<string>",
  "recommendations": "<string>",
  "feedback_notes": [{"severity": "minor|moderate|critical", "topic": "<concept area>", "mistake": "<2-4 sentences explaining what the student got wrong and why>", "correction": "<one short sentence stating the correct answer or fact>"}]
}
"""

GRADING_USER_TEMPLATE = """\
Question: {question}
Max marks: {points}
Mark scheme: {mark_scheme}
Model answer: {model_answer}

Student's answer: {student_answer}

Grade this answer. Return JSON only.\
"""


def build_grading_messages(
    question: str,
    points: int,
    mark_scheme: str | None,
    model_answer: str,
    student_answer: str,
    pm: PromptManager | None = None,
) -> list[dict[str, str]]:
    scheme = (
        mark_scheme or f"Award marks based on the model answer. Max {points} marks."
    )
    return [
        {"role": "system", "content": pm.get("tests", "grading_system") if pm else GRADING_SYSTEM},
        {
            "role": "user",
            "content": (pm.get("tests", "grading_user_template") if pm else GRADING_USER_TEMPLATE).format(
                question=question,
                points=points,
                mark_scheme=scheme,
                model_answer=model_answer,
                student_answer=student_answer,
            ),
        },
    ]


# ── Review question generation (Feynman mistakes only) ─────────────────────

REVIEW_QUESTION_SYSTEM = """\
You are an expert exam question writer. A student made a mistake that has been \
recorded with its correction. Generate exactly ONE short-answer question that \
tests whether the student now understands the corrected concept.

Rules:
- The question must directly probe the concept described in the correction.
- Do NOT reveal the mistake or the correction in the question text.
- model_answer must fully satisfy the correct understanding in 1–3 sentences.
- The hint must be 1–2 sentences. Point the student toward the relevant concept, \
definition, or reasoning approach without revealing the answer. Use a direct, \
supportive tone (e.g. "Think about how X relates to Y" or "Recall the definition \
of Z"). Do not start with "Hint:".
- Points: 1–3 based on how conceptually demanding the question is.

You MUST respond with a single JSON object only — no markdown, no extra text.
Schema:
{
  "question": "<string>",
  "model_answer": "<string>",
  "hint": "<string>",
  "points": <int 1-3>
}
"""

REVIEW_QUESTION_USER_TEMPLATE = """\
Topic: {topic}
Mistake made: {mistake}
Correct understanding: {correction}

Generate one short-answer question that tests the student's mastery of this \
correction. Return JSON only.\
"""


def build_review_question_messages(
    topic: str,
    mistake: str,
    correction: str,
    pm: PromptManager | None = None,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": pm.get("tests", "review_question_system") if pm else REVIEW_QUESTION_SYSTEM},
        {
            "role": "user",
            "content": (pm.get("tests", "review_question_user_template") if pm else REVIEW_QUESTION_USER_TEMPLATE).format(
                topic=topic,
                mistake=mistake,
                correction=correction,
            ),
        },
    ]


# ── Practice hint (SSE — kept for dormant endpoint / hint_service imports) ──

PRACTICE_HINT_CHAT_MARKER = "<<<NV_CHAT>>>"
PRACTICE_HINT_PANEL_MARKER = "<<<NV_HINT>>>"

PRACTICE_HINT_USER_CHAT_MESSAGE = "Give me a hint for this question."

PRACTICE_HINT_SYSTEM = f"""\
You are a tutor helping a student in **practice test** mode.

The student has conceptually asked: "Give me a hint for this question."

Rules:
- Guide with questions, angles, or what to revisit — **do not** give a ready-made \
solution or final answer.
- For **multiple-choice** questions: **never** name, imply, or hint which option \
letter/index is correct. Do not eliminate specific options as wrong.
- Keep the response to 1–3 short sentences: supportive and directional.
- If a template "author hint" is provided, you may rephrase or build on it — still \
follow the rules above.

Output format (strict):
1. Output **exactly** the line `{PRACTICE_HINT_CHAT_MARKER}` first (nothing before it).
2. Then the response text (1–3 sentences).
3. Then a newline and **exactly** the line `{PRACTICE_HINT_PANEL_MARKER}`.
4. Then a concrete study angle, still without giving away the answer.

No markdown headings, no labels like "Chat:" — only the two markers and two bodies.
"""


def build_practice_hint_user_content(
    *,
    question_type: str,
    question_text: str,
    options: list[str] | None,
    author_hint: str | None,
) -> str:
    """User message for practice hint (no correct answer / index leaked)."""
    lines: list[str] = [
        "The student asked (for the chat context): give a hint for this practice question.",
        "",
        f"Question type: {question_type}",
        "Question:",
        question_text.strip(),
    ]
    if question_type == "mcq" and options:
        lines.append("")
        lines.append("Options (indexed for your reasoning only — do not reveal which is correct):")
        for i, opt in enumerate(options):
            lines.append(f"  [{i}] {opt}")
    if author_hint and author_hint.strip():
        lines.extend(
            [
                "",
                "Author / template hint (reference only; rephrase if needed):",
                author_hint.strip(),
            ]
        )
    return "\n".join(lines)


def build_practice_hint_messages(
    *,
    question_type: str,
    question_text: str,
    options: list[str] | None,
    author_hint: str | None,
    pm: PromptManager | None = None,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": pm.get("tests", "practice_hint_system") if pm else PRACTICE_HINT_SYSTEM},
        {
            "role": "user",
            "content": build_practice_hint_user_content(
                question_type=question_type,
                question_text=question_text,
                options=options,
                author_hint=author_hint,
            ),
        },
    ]

