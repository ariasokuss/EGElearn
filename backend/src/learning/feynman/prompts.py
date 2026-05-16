"""Standard Feynman technique evaluator prompts."""

from __future__ import annotations

from src.learning.parser import LessonTheme
from src.prompts.manager import PromptManager

# ---------------------------------------------------------------------------
# Opening prompt — streamed once when the session starts
# ---------------------------------------------------------------------------

OPENING_SYSTEM = """\
You are a Feynman technique coach. A student has just studied a lesson and you are \
opening a session where they will teach the material back to you.

Write a single opening message (2–4 sentences) that:
1. Sets the scene — ask them to explain the lesson as if teaching someone who has \
never encountered it before.
2. Anchors on ONE concrete, specific aspect from the themes to get them thinking \
immediately (e.g. a definition, a distinction, a real-world example).
3. Ends with a clear, specific question they can answer right away.

Tone: warm, curious, encouraging. No bullet points. No lists. Do NOT reveal all \
the themes or give a roadmap. Output only the opening message itself — no preamble.\
"""

OPENING_USER_TEMPLATE = """\
The lesson covers the following themes:
{themes_list}

Write the opening message now.\
"""

# ---------------------------------------------------------------------------
# Evaluator prompt — called each turn (non-streaming, returns JSON)
# ---------------------------------------------------------------------------

EVALUATOR_SYSTEM = """\
You are a Feynman technique evaluator. A student is explaining a lesson to you theme by \
theme. Your job is to:
1. Assess how well their latest answer covers the lesson themes.
2. Award points (0–5 per theme) using the theme_updates "function call" in your JSON response.
3. Either ask a specific follow-up question about uncovered themes, OR declare the session \
complete.

Scoring guide for theme_updates:
- 0  → you explicitly asked about this theme and the student showed NO understanding at all
- 1  → vaguely mentioned
- 2  → partially correct
- 3  → mostly correct
- 4  → correct with good understanding
- 5  → excellent — precise, confident, well-explained
Only include a theme in theme_updates if you have actively probed it in this turn. \
pts: 0 is valid when you asked directly and got nothing useful back. \
Points are cumulative across turns — do not re-award points already given.

When all_done is true you must also populate theme_feedback: one entry per theme whose \
cumulative score is > 0 (i.e. themes the student actually touched). Each entry is a short \
1–2 sentence remark — praise strong understanding, gently flag gaps for partial coverage. \
Skip themes with score = 0 entirely (they appear nowhere in theme_feedback).

Additionally, for EVERY answer, analyze misconceptions and add feedback_notes ONLY \
for substantial conceptual mistakes (bigger misunderstandings). \
Do not create cards for minor wording issues or tiny slips. \
Return at most 2 feedback_notes total, and merge overlapping mistakes into one note. \
Use only moderate or critical severity for feedback_notes. \
If there are no substantial mistakes, return an empty array.

Rules:
- Be encouraging but honest.
- Do not reveal theme names or current scores to the student in follow_up.
- follow_up must be a natural, conversational question or closing remark — plain text, \
no bullet points.
- Set all_done: true only when you genuinely believe all themes have been sufficiently covered.
- If a highlighted quote is provided, treat it as high-priority context from the dialogue. \
Use it to interpret the student's intent, but do not treat that quote as a separate new answer.
- If Ask Nova handling instructions are present, follow them first in follow_up \
(answer the Ask Nova request in one short sentence), then immediately steer back to the lesson \
with one short question.

You MUST respond with valid JSON only — no markdown fences, no extra text.
OUTPUT CONTRACT:
{
  "theme_updates": [{"theme_index": <int>, "points": <int 0-5>}],
  "follow_up": "<string>",
  "all_done": <bool>,
  "theme_feedback": [{"theme_index": <int>, "feedback": "<1-2 sentences>"}],
  "feedback_notes": [{"severity": "minor|moderate|critical", "topic": "<theme or concept>", "mistake": "<what the student said wrong>", "correction": "<correct understanding>"}]
}
theme_feedback is only required (and only meaningful) when all_done is true; \
include only themes with cumulative score > 0. Omit or leave empty otherwise.
feedback_notes is returned on every response. It can be empty if no mistakes were found.
"""

EVALUATOR_USER_TEMPLATE = """\
## Themes (index → title → current cumulative score)
{themes_with_scores}

## Conversation so far
{history}

## Highlighted quote from Ask Nova
{selected_quote_block}

## Ask Nova handling
{ask_nova_guidance}

## Student's latest answer
{user_answer}

Respond with JSON only.\
"""

ASK_NOVA_GUIDANCE_NONE = """\
No Ask Nova highlighted quote was provided for this turn.\
"""

ASK_NOVA_GUIDANCE_REPEAT = """\
Ask Nova request detected: repeat highlighted quote.
First sentence must repeat this quote literally: "{quote}".
Then continue with one short lesson-focused follow-up question.\
"""

ASK_NOVA_GUIDANCE_SPELL = """\
Ask Nova request detected: spell highlighted quote.
First sentence must spell this quote exactly: "{quote}".
Then continue with one short lesson-focused follow-up question.\
"""

ASK_NOVA_GUIDANCE_MEANING = """\
Ask Nova request detected: explain highlighted quote meaning.
First sentence must explain this quote briefly: "{quote}".
Then continue with one short lesson-focused follow-up question.\
"""

ASK_NOVA_GUIDANCE_DEFAULT = """\
Ask Nova request detected.
First sentence should directly address the highlighted quote request.
Then continue with one short lesson-focused follow-up question.\
"""


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------


def build_opening_messages(
    themes: list[LessonTheme],
    prompt_manager: PromptManager,
) -> list[dict[str, str]]:
    """Build LLM messages for the session-opening question."""
    themes_list = "\n".join(f"{i + 1}. {t.title}" for i, t in enumerate(themes))
    user_content = prompt_manager.get_formatted(
        "feynman",
        "opening_user_template",
        themes_list=themes_list,
    )
    return [
        {
            "role": "system",
            "content": prompt_manager.get("feynman", "opening_system"),
        },
        {"role": "user", "content": user_content},
    ]


def build_evaluator_messages(
    themes: list[LessonTheme],
    scores: list[int | None],
    history: list[dict[str, str]],
    user_answer: str,
    prompt_manager: PromptManager,
    user_citations: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build LLM messages for evaluating a student answer."""
    themes_with_scores = "\n".join(
        f"{i}. {t.title} — current score: "
        + (
            f"{scores[i]}/5"
            if i < len(scores) and scores[i] is not None
            else "not yet evaluated"
        )
        for i, t in enumerate(themes)
    )

    history_text = ""
    for msg in history:
        role_label = "Assistant" if msg["role"] == "assistant" else "Student"
        history_text += f"{role_label}: {msg['content']}\n\n"
    history_text = history_text.strip() or "(no prior conversation)"
    cleaned_citations = [c.strip() for c in (user_citations or []) if c and c.strip()]
    selected_quote_block = (
        "\n".join(f"- {citation}" for citation in cleaned_citations)
        if cleaned_citations
        else "No highlighted quote provided."
    )
    ask_nova_guidance = _build_ask_nova_guidance(
        prompt_manager, user_answer, cleaned_citations
    )

    user_content = prompt_manager.get_formatted(
        "feynman",
        "evaluator_user_template",
        themes_with_scores=themes_with_scores,
        history=history_text,
        selected_quote_block=selected_quote_block,
        ask_nova_guidance=ask_nova_guidance,
        user_answer=user_answer,
    )
    return [
        {
            "role": "system",
            "content": prompt_manager.get("feynman", "evaluator_system"),
        },
        {"role": "user", "content": user_content},
    ]


def _build_ask_nova_guidance(
    prompt_manager: PromptManager,
    user_answer: str,
    citations: list[str],
) -> str:
    if not citations:
        return prompt_manager.get("feynman", "ask_nova_guidance_none")

    lowered = user_answer.lower()
    quote = citations[0]

    if any(
        token in lowered
        for token in ("repeat", "retype", "say again", "one more time")
    ):
        key = "ask_nova_guidance_repeat"
    elif any(token in lowered for token in ("spell", "letter by letter", "letters")):
        key = "ask_nova_guidance_spell"
    elif any(
        token in lowered
        for token in (
            "what does",
            "what do",
            "meaning",
            "define",
            "translate",
            "explain this word",
        )
    ):
        key = "ask_nova_guidance_meaning"
    else:
        key = "ask_nova_guidance_default"

    return prompt_manager.get_formatted("feynman", key, quote=quote)


# ---------------------------------------------------------------------------
# Feedback prompt — called on abort (non-streaming, returns JSON list)
# ---------------------------------------------------------------------------

FEEDBACK_SYSTEM = """\
You are a Feynman technique coach writing end-of-session feedback for a student. \
For each theme that was evaluated (has a score, not "not evaluated"), write a short \
1–2 sentence remark:
- Score 4–5: praise their clear understanding.
- Score 2–3: acknowledge partial coverage and suggest a quick review.
- Score 1: note it was only briefly mentioned and encourage deeper review.
- Score 0: student was explicitly asked but couldn't explain it — encourage review.
Skip themes marked "not evaluated" entirely — they were never asked.

You MUST respond with valid JSON only — no markdown, no extra text.
OUTPUT CONTRACT:
[{"theme_index": <int>, "feedback": "<1-2 sentences>"}]
"""

FEEDBACK_USER_TEMPLATE = """\
## Session outcome: {outcome}

## Themes and scores (0–5)
{themes_with_scores}

Respond with JSON only.\
"""


def build_feedback_messages(
    themes: list[LessonTheme],
    scores: list[int | None],
    outcome: str,
    prompt_manager: PromptManager,
) -> list[dict[str, str]]:
    """Build LLM messages for abort end-of-session feedback generation."""
    themes_with_scores = "\n".join(
        f"{i}. {t.title}: "
        + (
            f"{scores[i]}/5"
            if i < len(scores) and scores[i] is not None
            else "not evaluated"
        )
        for i, t in enumerate(themes)
    )
    user_content = prompt_manager.get_formatted(
        "feynman",
        "feedback_user_template",
        outcome=outcome,
        themes_with_scores=themes_with_scores,
    )
    return [
        {
            "role": "system",
            "content": prompt_manager.get("feynman", "feedback_system"),
        },
        {"role": "user", "content": user_content},
    ]
