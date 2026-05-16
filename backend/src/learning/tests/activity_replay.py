from __future__ import annotations

import uuid
from typing import Any, Iterable


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _clean_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if _present(value)}


def _safe_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_uuid(value: Any) -> str | None:
    return str(value) if isinstance(value, uuid.UUID) else None


def _safe_list(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) and value else None


def _option_letter(index: int) -> str:
    letters: list[str] = []
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _option_is_labeled(option: Any, index: int) -> bool:
    return isinstance(option, str) and option.strip().startswith(f"{_option_letter(index)}.")


def _format_option(option: Any, index: int) -> str:
    if _option_is_labeled(option, index):
        return str(option)
    return f"{_option_letter(index)}. {option}"


def _format_options(options: list[Any] | None) -> list[str] | None:
    if not options:
        return None
    return [_format_option(option, index) for index, option in enumerate(options)]


def _int_from_text(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _format_option_choice(
    value: Any,
    question: Any | None,
    *,
    one_based: bool,
) -> str | None:
    index = _int_from_text(value)
    options = _safe_list(getattr(question, "options", None)) if question is not None else None
    if index is None or not options:
        return None
    option_index = index - 1 if one_based else index
    if option_index < 0 or option_index >= len(options):
        return None
    return _format_option(options[option_index], option_index)


def _format_answer_text(answer_text: str | None, question: Any | None) -> str | None:
    formatted = _format_option_choice(answer_text, question, one_based=False)
    return formatted or answer_text


def _result_get(result: Any, key: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _score_percent(score: Any) -> float | None:
    try:
        return float(score) * 100 if score is not None else None
    except (TypeError, ValueError):
        return None


def _question_title(question: Any | None, fallback_id: uuid.UUID | None = None) -> str:
    if question is None:
        return f"Question {fallback_id}" if fallback_id is not None else "Question"
    number = _safe_text(getattr(question, "question_number", None))
    if number:
        return f"Question {number}"
    index = getattr(question, "index", None)
    if isinstance(index, int):
        return f"Question {index + 1}"
    return f"Question {fallback_id}" if fallback_id is not None else "Question"


def _question_item(question: Any | None, fallback_id: uuid.UUID | None = None) -> dict[str, Any] | None:
    if question is None:
        return None
    text = _safe_text(getattr(question, "question", None))
    options = _safe_list(getattr(question, "options", None))
    if not text and not options:
        return None
    return _clean_dict(
        {
            "kind": "question",
            "title": _question_title(question, fallback_id),
            "text": text,
            "options": _format_options(options),
            "question_type": _safe_text(getattr(question, "type", None)),
            "points": getattr(question, "points", None),
        }
    )


def _answer_status(result: Any, question: Any | None = None) -> dict[str, Any]:
    is_correct = _result_get(result, "is_correct")
    earned_marks = _result_get(result, "earned_marks")
    total_marks = _result_get(result, "total_marks")
    if total_marks is None and question is not None:
        total_marks = getattr(question, "points", None)
    score_percent = _score_percent(_result_get(result, "score"))
    return _clean_dict(
        {
            "is_correct": is_correct,
            "correctness": "Correct" if is_correct is True else "Incorrect" if is_correct is False else None,
            "earned_marks": earned_marks,
            "total_marks": total_marks,
            "score_percent": score_percent,
        }
    )


def _answer_item(
    *,
    title: str,
    answer_text: str | None,
    result: Any | None = None,
    question: Any | None = None,
) -> dict[str, Any] | None:
    result = result or {}
    used_image = bool(_result_get(result, "image_key") or _result_get(result, "image_keys"))
    answer_text = _format_answer_text(answer_text, question)
    if not answer_text and not used_image:
        return None
    return _clean_dict(
        {
            "kind": "user_answer",
            "title": title,
            "text": answer_text,
            "value": "Image answer uploaded" if used_image and not answer_text else None,
            **_answer_status(result, question),
        }
    )


def _feedback_items(result: Any, question: Any | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    model_answer = _safe_text(_result_get(result, "model_answer")) or (
        _safe_text(getattr(question, "model_answer", None)) if question is not None else None
    )
    feedback = _safe_text(_result_get(result, "feedback"))
    recommendations = _safe_text(_result_get(result, "recommendations"))
    mark_scheme = _safe_text(getattr(question, "mark_scheme", None)) if question is not None else None
    correct_option_index = _result_get(result, "correct_option_index")
    if correct_option_index is None and question is not None:
        correct_option_index = getattr(question, "correct_option_index", None)

    for title, text in (
        ("Model answer", model_answer),
        ("Feedback", feedback),
        ("Recommendation", recommendations),
        ("Mark scheme", mark_scheme),
    ):
        if text:
            items.append({"kind": "llm_response", "title": title, "text": text})
    if correct_option_index is not None:
        formatted_choice = _format_option_choice(
            correct_option_index,
            question,
            one_based=False,
        )
        items.append(
            {
                "kind": "answer_key",
                "title": "Correct option",
                "value": formatted_choice
                or (
                    _option_letter(correct_option_index)
                    if isinstance(correct_option_index, int)
                    else correct_option_index
                ),
            }
        )
    return items


def _payload(items: Iterable[dict[str, Any] | None], refs: dict[str, Any]) -> dict[str, Any]:
    cleaned_items = [item for item in items if item]
    return {
        "schema_version": 1,
        "items": cleaned_items,
        "refs": _clean_dict(refs),
    }


def test_started_replay_payload(
    *,
    template: Any,
    test_session: Any,
    mode: str | None,
) -> dict[str, Any]:
    questions = list(getattr(template, "questions", None) or [])
    items: list[dict[str, Any] | None] = [
        _clean_dict(
            {
                "kind": "test",
                "title": "Test opened",
                "value": _safe_text(getattr(template, "name", None)),
                "mode": mode,
                "total_questions": len(questions),
                "total_marks": getattr(test_session, "total_marks", None),
            }
        )
    ]
    items.extend(_question_item(question, getattr(question, "id", None)) for question in questions)
    return _payload(
        items,
        {
            "template_id": _safe_uuid(getattr(template, "id", None)),
            "test_session_id": _safe_uuid(getattr(test_session, "id", None)),
            "lesson_id": _safe_uuid(getattr(template, "lesson_id", None)),
            "folder_id": _safe_uuid(getattr(template, "folder_id", None)),
        },
    )


def answer_replay_payload(
    *,
    question: Any | None,
    question_id: uuid.UUID,
    answer_text: str | None,
    result: Any,
    title: str = "User answer",
) -> dict[str, Any]:
    question = question or getattr(result, "question", None)
    return _payload(
        [
            _question_item(question, question_id),
            _answer_item(
                title=title,
                answer_text=answer_text,
                result=result,
                question=question,
            ),
            *_feedback_items(result, question),
        ],
        {"question_id": str(question_id)},
    )


def question_skipped_replay_payload(
    *,
    question: Any | None,
    question_id: uuid.UUID,
    answer: Any,
    skipped: bool,
) -> dict[str, Any]:
    answer_text = _safe_text(getattr(answer, "answer", None))
    return _payload(
        [
            _question_item(question or getattr(answer, "question", None), question_id),
            _clean_dict(
                {
                    "kind": "user_action",
                    "title": "Question skipped" if skipped else "Question unskipped",
                    "value": "Skipped" if skipped else "Unskipped",
                }
            ),
            _answer_item(
                title="Existing answer",
                answer_text=answer_text,
                result=answer,
                question=question or getattr(answer, "question", None),
            ),
        ],
        {"question_id": str(question_id)},
    )


def submit_session_replay_payload(
    *,
    test_session: Any,
    submitted_answers: Iterable[Any] | None,
) -> dict[str, Any]:
    template = getattr(test_session, "template", None)
    questions = list(getattr(template, "questions", None) or [])
    question_by_id = {
        getattr(question, "id", None): question
        for question in questions
        if isinstance(getattr(question, "id", None), uuid.UUID)
    }
    persisted_answers = {
        getattr(answer, "question_id", None): answer
        for answer in list(getattr(test_session, "answers", None) or [])
        if isinstance(getattr(answer, "question_id", None), uuid.UUID)
        and not getattr(answer, "is_skipped", False)
    }
    submitted_by_id = {
        getattr(answer, "question_id", None): answer
        for answer in list(submitted_answers or [])
        if isinstance(getattr(answer, "question_id", None), uuid.UUID)
    }
    ordered_ids = [getattr(question, "id", None) for question in questions]
    for question_id in [*submitted_by_id.keys(), *persisted_answers.keys()]:
        if question_id not in ordered_ids:
            ordered_ids.append(question_id)

    answer_rows: list[tuple[uuid.UUID, Any | None, Any | None]] = []
    for question_id in ordered_ids:
        if not isinstance(question_id, uuid.UUID):
            continue
        submitted = submitted_by_id.get(question_id)
        persisted = persisted_answers.get(question_id)
        answer_text = _safe_text(getattr(submitted, "answer", None))
        if answer_text is None:
            answer_text = _safe_text(getattr(persisted, "answer", None))
        has_image = bool(
            getattr(persisted, "image_key", None)
            or getattr(persisted, "image_keys", None)
        )
        if not answer_text and not has_image:
            continue
        answer_rows.append((question_id, submitted, persisted))

    items: list[dict[str, Any] | None] = [
        _clean_dict(
            {
                "kind": "test",
                "title": "Test submitted",
                "answered_count": len(answer_rows) or None,
                "earned_marks": getattr(test_session, "earned_marks", None),
                "total_marks": getattr(test_session, "total_marks", None),
                "score_percent": _score_percent(getattr(test_session, "score", None)),
                "status": _safe_text(getattr(test_session, "status", None)),
            }
        )
    ]
    for question_id, submitted, persisted in answer_rows:
        question = question_by_id.get(question_id)
        answer_text = _safe_text(getattr(submitted, "answer", None))
        if answer_text is None:
            answer_text = _safe_text(getattr(persisted, "answer", None))
        items.append(_question_item(question, question_id))
        items.append(
            _answer_item(
                title="Submitted answer",
                answer_text=answer_text,
                result=persisted or submitted or {},
                question=question,
            )
        )

    return _payload(
        items,
        {
            "template_id": _safe_uuid(getattr(test_session, "template_id", None)),
            "test_session_id": _safe_uuid(getattr(test_session, "id", None)),
        },
    )


def hint_used_replay_payload(
    *,
    question: Any | None,
    question_id: uuid.UUID,
    assistant_chat: str | None,
    hint_panel: str | None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    return _payload(
        [
            _question_item(question, question_id),
            {"kind": "user_action", "title": "User action", "value": "Requested AI hint"},
            _clean_dict(
                {
                    "kind": "llm_response",
                    "title": "AI hint",
                    "text": assistant_chat,
                }
            ),
            _clean_dict(
                {
                    "kind": "llm_response",
                    "title": "Hint panel",
                    "text": hint_panel,
                }
            ),
        ],
        {"question_id": str(question_id), "conversation_id": conversation_id},
    )


def test_graded_replay_payload(
    *,
    test_session: Any,
    template_questions: Iterable[Any],
) -> dict[str, Any]:
    question_by_id = {
        getattr(question, "id", None): question
        for question in template_questions
        if isinstance(getattr(question, "id", None), uuid.UUID)
    }
    items: list[dict[str, Any] | None] = [
        _clean_dict(
            {
                "kind": "test_result",
                "title": "Test graded",
                "earned_marks": getattr(test_session, "earned_marks", None),
                "total_marks": getattr(test_session, "total_marks", None),
                "score_percent": _score_percent(getattr(test_session, "score", None)),
            }
        )
    ]
    for answer in list(getattr(test_session, "answers", None) or []):
        if getattr(answer, "is_skipped", False):
            continue
        question_id = getattr(answer, "question_id", None)
        if not isinstance(question_id, uuid.UUID):
            continue
        question = getattr(answer, "question", None) or question_by_id.get(question_id)
        answer_text = _safe_text(getattr(answer, "answer", None))
        items.append(_question_item(question, question_id))
        items.append(
            _answer_item(
                title="User answer",
                answer_text=answer_text,
                result=answer,
                question=question,
            )
        )
        items.extend(_feedback_items(answer, question))

    return _payload(
        items,
        {
            "template_id": _safe_uuid(getattr(test_session, "template_id", None)),
            "test_session_id": _safe_uuid(getattr(test_session, "id", None)),
        },
    )
