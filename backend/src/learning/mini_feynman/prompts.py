"""Feynman evaluator prompts."""

from src.prompts.manager import PromptManager

EVALUATE_SYSTEM = """\
You are a Feynman technique evaluator. Your job is to assess whether a student's \
answer demonstrates understanding of specific key points, and either ask a \
targeted follow-up question (if points are still missing and iterations remain) \
or produce a concise summary.

Rules:
- Be encouraging but honest.
- Do not reveal the points list verbatim to the student.
- Follow-up questions should probe the specific concepts the student has not yet \
demonstrated understanding of.
- The summary should be brief (3–5 sentences): acknowledge what was understood, \
gently note what was missed, and give a one-line takeaway.

You MUST respond with valid JSON only — no markdown fences, no extra text.
OUTPUT CONTRACT:
- Valid JSON only. No markdown. No preamble. No trailing text.
- If points remain AND iterations remain → populate follow_up, leave summary "".
- Otherwise → populate summary, leave follow_up "".
Schema:
{
  "covered": [<bool>, ...],   // one bool per point in the same order as the input list
  "follow_up": "<string>",    // next question to ask, empty string "" if terminal
  "summary": "<string>"       // summary shown when session ends, empty string "" if not terminal
}
"""

EVALUATE_USER_TEMPLATE = """\
## Points to cover
{points_list}

## Iteration
{iteration} of 3

## Conversation so far
{history}

## Student's latest answer
{user_answer}

{terminal_instruction}

Respond with JSON only.\
"""

_TERMINAL_INSTRUCTION = (
    "This is the final iteration (or all points are already covered). "
    "Set follow_up to an empty string and write a summary."
)
_CONTINUE_INSTRUCTION = (
    "Not all points are covered yet and iterations remain. "
    "Set summary to an empty string and write a follow_up question."
)


def build_evaluate_messages(
    points: list[str],
    history: list[dict[str, str]],
    user_answer: str,
    iteration: int,
    is_terminal: bool,
    prompt_manager: PromptManager | None,
) -> list[dict[str, str]]:
    if prompt_manager is None:
        raise ValueError("prompt_manager must be provided")

    """Build the message list for the evaluation LLM call."""
    points_list = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))

    history_text = ""
    for msg in history:
        role_label = "Assistant" if msg["role"] == "assistant" else "Student"
        history_text += f"{role_label}: {msg['content']}\n\n"
    history_text = history_text.strip() or "(no prior conversation)"

    user_content = prompt_manager.get_formatted(
        "mini_feynman",
        "feynman_user_template",
        points_list=points_list,
        iteration=iteration,
        history=history_text,
        user_answer=user_answer,
        terminal_instruction=(
            prompt_manager.get("mini_feynman", "feynman_terminal_instruction")
            if is_terminal
            else prompt_manager.get("mini_feynman", "feynman_continue_instruction")
        ),
    )

    return [
        {
            "role": "system",
            "content": prompt_manager.get("mini_feynman", "feynman_system_prompt"),
        },
        {"role": "user", "content": user_content},
    ]
