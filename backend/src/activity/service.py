from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.activity.models import UserActivityEvent
from src.usage.service import resolve_period_start

logger = logging.getLogger(__name__)

SESSION_GAP = timedelta(hours=1)
LOW_SCORE_PERCENT = 60

UNSAFE_METADATA_KEYS = {
    "answer",
    "answers",
    "assistant_chat",
    "access_token",
    "authorization",
    "body",
    "chat",
    "content",
    "cookie",
    "credential",
    "email",
    "feedback",
    "file",
    "google_credential",
    "hint_panel",
    "id_token",
    "message",
    "messages",
    "model_answer",
    "password",
    "prompt",
    "prompts",
    "question",
    "query",
    "raw",
    "request_body",
    "response",
    "responses",
    "refresh_token",
    "secret",
    "set-cookie",
    "summary",
    "text",
    "token",
    "tokens",
    "transcript",
    "user_answer",
    "visitor_id",
}

CLIENT_EVENT_TYPES = frozenset({"page_view", "route_change", "chat_opened"})


@dataclass(slots=True)
class ActivityEventInput:
    user_id: uuid.UUID
    event_type: str
    event_group: str
    request_path: str | None = None
    http_method: str | None = None
    route_label: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    lesson_id: uuid.UUID | None = None
    test_session_id: uuid.UUID | None = None
    metadata: dict[str, Any] | None = None
    replay_payload: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class ActivityTimelineEvent:
    event_id: str
    event_type: str
    event_group: str
    action_label: str
    created_at: datetime
    label: str
    metadata: dict[str, Any]
    replay_payload: dict[str, Any]


@dataclass(slots=True)
class ActivitySession:
    start_at: datetime
    end_at: datetime
    duration_seconds: int
    event_count: int
    summary: str
    signals: list[str]
    events: list[ActivityTimelineEvent]


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str.lower() in UNSAFE_METADATA_KEYS:
                continue
            sanitized = sanitize_metadata(item)
            if sanitized is not None:
                cleaned[key_str] = sanitized
        return cleaned
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            sanitized = sanitize_metadata(item)
            if sanitized is not None:
                cleaned_items.append(sanitized)
        return cleaned_items
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def sanitize_replay_payload(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            sanitized = sanitize_replay_payload(item)
            if sanitized is not None:
                cleaned[str(key)] = sanitized
        return cleaned
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            sanitized = sanitize_replay_payload(item)
            if sanitized is not None:
                cleaned_items.append(sanitized)
        return cleaned_items
    if isinstance(value, bytes | bytearray | memoryview):
        return "[binary omitted]"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _event_group(event_type: str) -> str:
    if event_type in {"page_view", "route_change"}:
        return "navigation"
    return event_type.split("_", 1)[0] if "_" in event_type else "other"


def _score_percent(metadata: dict[str, Any]) -> float | None:
    raw = metadata.get("score_percent")
    if raw is None and metadata.get("score") is not None:
        try:
            score = float(metadata["score"])
            raw = score * 100 if score <= 1 else score
        except (TypeError, ValueError):
            return None
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _metadata_for(event: Any) -> dict[str, Any]:
    value = getattr(event, "event_metadata", None)
    if value is None:
        value = getattr(event, "metadata", None)
    return value if isinstance(value, dict) else {}


def _replay_payload_for(event: Any) -> dict[str, Any]:
    value = getattr(event, "replay_payload", None)
    return _normalize_replay_payload_for_admin(value) if isinstance(value, dict) else {}


def _option_letter(index: int) -> str:
    letters: list[str] = []
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _option_is_labeled(option: Any, index: int) -> bool:
    return isinstance(option, str) and option.strip().startswith(f"{_option_letter(index)}.")


def _option_text(option: Any, index: int) -> str:
    if isinstance(option, dict):
        raw = option.get("text")
        if raw is None:
            raw = option.get("value")
        return str(raw) if raw is not None else ""
    text = str(option)
    prefix = f"{_option_letter(index)}."
    stripped = text.strip()
    if stripped.startswith(prefix):
        return stripped[len(prefix) :].lstrip()
    return text


def _format_option(option: Any, index: int) -> str:
    if isinstance(option, dict):
        value = option.get("value")
        if value is not None:
            return str(value)
        text = option.get("text")
        label = option.get("label") or _option_letter(index)
        if text is not None:
            return f"{label}. {text}"
    text = str(option)
    if _option_is_labeled(option, index):
        return text
    return f"{_option_letter(index)}. {text}"


def _structured_options(
    options: list[Any],
    *,
    selected_index: int | None = None,
    correct_index: int | None = None,
) -> list[dict[str, Any]]:
    structured: list[dict[str, Any]] = []
    for index, option in enumerate(options):
        label = (
            str(option.get("label"))
            if isinstance(option, dict) and option.get("label")
            else _option_letter(index)
        )
        text = _option_text(option, index)
        value = _format_option(option, index)
        structured.append(
            {
                "label": label,
                "text": text,
                "value": value,
                "is_selected": bool(
                    isinstance(option, dict) and option.get("is_selected")
                )
                or selected_index == index,
                "is_correct": bool(
                    isinstance(option, dict) and option.get("is_correct")
                )
                or correct_index == index,
            }
        )
    return structured


def _int_from_text(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _letter_index_from_text(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    token = stripped.split(".", 1)[0].split(" ", 1)[0].strip().upper()
    if not token.isalpha():
        return None
    index = 0
    for char in token:
        if char < "A" or char > "Z":
            return None
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _choice_index(
    value: Any,
    options: list[Any],
    *,
    one_based: bool,
) -> int | None:
    letter_index = _letter_index_from_text(value)
    if letter_index is not None and 0 <= letter_index < len(options):
        return letter_index

    index = _int_from_text(value)
    if index is not None:
        option_index = index - 1 if one_based else index
        if 0 <= option_index < len(options):
            return option_index

    if isinstance(value, str):
        stripped = value.strip()
        for option_index, option in enumerate(options):
            if stripped in {
                _format_option(option, option_index),
                _option_text(option, option_index),
            }:
                return option_index
    return None


def _format_choice(
    value: Any,
    options: list[Any],
    *,
    one_based: bool,
) -> str | None:
    option_index = _choice_index(value, options, one_based=one_based)
    if option_index is None:
        return None
    return _format_option(options[option_index], option_index)


def _mark_option(
    item: dict[str, Any],
    option_index: int | None,
    flag: str,
) -> None:
    options = item.get("options")
    if option_index is None or not isinstance(options, list):
        return
    if option_index < 0 or option_index >= len(options):
        return
    option = options[option_index]
    if isinstance(option, dict):
        option[flag] = True


def _normalize_replay_payload_for_admin(value: dict[str, Any]) -> dict[str, Any]:
    items = value.get("items")
    if not isinstance(items, list):
        return value

    normalized_items: list[Any] = []
    current_options: list[Any] | None = None
    current_question_index: int | None = None
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue

        normalized = dict(item)
        options = normalized.get("options")
        if isinstance(options, list) and options:
            current_options = options
            current_question_index = len(normalized_items)
            normalized["options"] = _structured_options(options)

        if current_options and normalized.get("kind") == "user_answer":
            selected_index = _choice_index(
                normalized.get("text"),
                current_options,
                one_based=False,
            )
            formatted_answer = _format_choice(
                normalized.get("text"),
                current_options,
                one_based=False,
            )
            if formatted_answer:
                normalized["text"] = formatted_answer
            if current_question_index is not None and selected_index is not None:
                _mark_option(
                    normalized_items[current_question_index],
                    selected_index,
                    "is_selected",
                )
                normalized["absorbed_into_options"] = True

        if current_options and normalized.get("kind") == "answer_key":
            correct_index = _choice_index(
                normalized.get("value"),
                current_options,
                one_based=True,
            )
            formatted_key = _format_choice(
                normalized.get("value"),
                current_options,
                one_based=True,
            )
            if formatted_key:
                normalized["value"] = formatted_key
            if current_question_index is not None and correct_index is not None:
                _mark_option(
                    normalized_items[current_question_index],
                    correct_index,
                    "is_correct",
                )
                normalized["absorbed_into_options"] = True

        normalized_items.append(normalized)

    normalized_payload = dict(value)
    normalized_payload["items"] = normalized_items
    return normalized_payload


def _human_event_label(event: Any) -> str:
    metadata = _metadata_for(event)
    label = getattr(event, "route_label", None)
    if label:
        return str(label)
    if event.event_type == "page_view":
        return f"Viewed {metadata.get('path') or event.request_path or 'page'}"
    if event.event_type == "route_change":
        return f"Navigated to {metadata.get('path') or event.request_path or 'page'}"
    if event.event_type == "lesson_opened":
        lesson_name = metadata.get("lesson_name")
        return f"Opened lesson {lesson_name}" if lesson_name else "Opened lesson"
    if event.event_type == "lesson_step_completed":
        return f"Completed lesson step {metadata.get('step')}"
    if event.event_type == "lesson_question_answered":
        if metadata.get("is_correct") is True:
            return "Answered lesson question correctly"
        if metadata.get("is_correct") is False:
            return "Answered lesson question incorrectly"
        return "Answered lesson question"
    if event.event_type == "lesson_reset":
        return "Reset lesson"
    if event.event_type == "test_started":
        total = metadata.get("total_questions")
        return f"Started test, {total} questions" if total else "Started test"
    if event.event_type == "answer_saved":
        idx = metadata.get("question_index")
        return f"Saved answer for question {idx}" if idx is not None else "Saved answer"
    if event.event_type == "question_skipped":
        idx = metadata.get("question_index")
        skipped = metadata.get("skipped")
        verb = "Skipped" if skipped else "Unskipped"
        return f"{verb} question {idx}" if idx is not None else f"{verb} question"
    if event.event_type == "answer_checked":
        idx = metadata.get("question_index")
        return f"Checked answer for question {idx}" if idx is not None else "Checked answer"
    if event.event_type == "diagram_answer_submitted":
        return "Submitted diagram answer"
    if event.event_type == "answer_regrade_requested":
        return "Requested answer regrade"
    if event.event_type == "hint_used":
        return "Used AI hint"
    if event.event_type == "user_registered":
        return "Registered account"
    if event.event_type == "user_logged_in":
        method = metadata.get("auth_method")
        return f"Logged in via {method}" if method else "Logged in"
    if event.event_type == "user_logged_out":
        return "Logged out"
    if event.event_type in {"test_submitted", "test_graded"}:
        answered = metadata.get("answered_count")
        total = metadata.get("total_questions")
        score = _score_percent(metadata)
        pieces = ["Submitted test" if event.event_type == "test_submitted" else "Test graded"]
        if answered is not None and total is not None:
            pieces.append(f"{answered}/{total} answered")
        if score is not None:
            pieces.append(f"{score:.0f}%")
        return ": ".join([pieces[0], ", ".join(pieces[1:])]) if len(pieces) > 1 else pieces[0]
    if event.event_type == "chat_message_sent":
        return "Sent chat message"
    if event.event_type == "chat_message_regenerated":
        return "Regenerated chat response"
    if event.event_type == "chat_branch_switched":
        return "Switched chat branch"
    if event.event_type == "chat_opened":
        return "Opened chat"
    if event.event_type == "feynman_started":
        return "Started Feynman session"
    if event.event_type == "feynman_completed":
        return "Completed Feynman session"
    if event.event_type == "feynman_aborted":
        return "Aborted Feynman session"
    return event.event_type.replace("_", " ").capitalize()


def _event_action_label(event: Any) -> str:
    event_type = str(event.event_type)
    event_group = str(getattr(event, "event_group", "") or "")
    metadata = _metadata_for(event)
    if event_type == "question_skipped" and metadata.get("skipped") is False:
        return "Question Unskipped"
    action_labels = {
        "page_view": "Viewed",
        "route_change": "Changed",
        "lesson_opened": "Opened",
        "lesson_step_completed": "Step Completed",
        "lesson_question_answered": "Question Answered",
        "lesson_reset": "Reset",
        "test_started": "Started",
        "answer_saved": "Answer Saved",
        "answer_checked": "Answer Checked",
        "diagram_answer_submitted": "Diagram Submitted",
        "answer_regrade_requested": "Regrade Requested",
        "question_skipped": "Question Skipped",
        "hint_used": "Hint Used",
        "user_registered": "Registered",
        "user_logged_in": "Logged In",
        "user_logged_out": "Logged Out",
        "test_submitted": "Submitted",
        "test_graded": "Graded",
        "chat_message_sent": "Message Sent",
        "chat_message_regenerated": "Regenerated",
        "chat_branch_switched": "Branch Switched",
        "chat_opened": "Opened",
        "feynman_started": "Started",
        "feynman_completed": "Completed",
        "feynman_aborted": "Aborted",
    }
    if event_type in action_labels:
        return action_labels[event_type]
    if event_group and event_type.startswith(f"{event_group}_"):
        event_type = event_type[len(event_group) + 1 :]
    return event_type.replace("_", " ").title()


def _session_summary(events: list[Any]) -> str:
    if not events:
        return "No activity"
    types = [event.event_type for event in events]
    if "test_submitted" in types or "test_graded" in types:
        score = next(
            (
                _score_percent(_metadata_for(event))
                for event in reversed(events)
                if event.event_type in {"test_submitted", "test_graded"}
            ),
            None,
        )
        if score is not None:
            return f"Completed test with {score:.0f}%"
        return "Worked through a test"
    if any(t.startswith("lesson_") for t in types):
        return "Worked on lesson content"
    if "chat_message_sent" in types or "chat_opened" in types:
        return "Used chat"
    return _human_event_label(events[-1])


def _session_signals(events: list[Any]) -> list[str]:
    signals: list[str] = []
    low_score_indices = [
        index
        for index, event in enumerate(events)
        if event.event_type in {"test_submitted", "test_graded"}
        and (score := _score_percent(_metadata_for(event))) is not None
        and score < LOW_SCORE_PERCENT
    ]
    low_score_seen = bool(low_score_indices)
    chat_after_low_score = any(
        event.event_type in {"chat_message_sent", "chat_opened"}
        and any(low_score_index < index for low_score_index in low_score_indices)
        for index, event in enumerate(events)
    )
    if low_score_seen:
        signals.append("low_score")
    if chat_after_low_score:
        signals.append("chat_after_low_score")

    started = {
        event.test_session_id
        for event in events
        if event.event_type == "test_started" and event.test_session_id is not None
    }
    finished = {
        event.test_session_id
        for event in events
        if event.event_type in {"test_submitted", "test_graded", "test_aborted"} and event.test_session_id is not None
    }
    if started - finished:
        signals.append("abandoned_test")

    saves_by_question: dict[tuple[uuid.UUID | None, Any], int] = {}
    for event in events:
        if event.event_type != "answer_saved":
            continue
        metadata = _metadata_for(event)
        key = (
            event.test_session_id,
            metadata.get("question_id") or metadata.get("question_index"),
        )
        saves_by_question[key] = saves_by_question.get(key, 0) + 1
    if any(count >= 4 for count in saves_by_question.values()):
        signals.append("many_answer_updates")

    if events:
        last = events[-1]
        last_score = _score_percent(_metadata_for(last))
        if last.event_type in {"test_submitted", "test_graded"} and last_score is not None and last_score < LOW_SCORE_PERCENT:
            signals.append("inactive_after_bad_result")

    return signals


def build_activity_sessions(events: Iterable[Any]) -> list[ActivitySession]:
    ordered = sorted(events, key=lambda event: event.created_at)
    chunks: list[list[Any]] = []
    for event in ordered:
        if not chunks or event.created_at - chunks[-1][-1].created_at > SESSION_GAP:
            chunks.append([event])
        else:
            chunks[-1].append(event)

    sessions: list[ActivitySession] = []
    for chunk in chunks:
        timeline = [
            ActivityTimelineEvent(
                event_id=str(event.id),
                event_type=event.event_type,
                event_group=event.event_group,
                action_label=_event_action_label(event),
                created_at=event.created_at,
                label=_human_event_label(event),
                metadata=_metadata_for(event),
                replay_payload=_replay_payload_for(event),
            )
            for event in chunk
        ]
        start_at = chunk[0].created_at
        end_at = chunk[-1].created_at
        sessions.append(
            ActivitySession(
                start_at=start_at,
                end_at=end_at,
                duration_seconds=max(0, int((end_at - start_at).total_seconds())),
                event_count=len(chunk),
                summary=_session_summary(chunk),
                signals=_session_signals(chunk),
                events=timeline,
            )
        )
    return list(reversed(sessions))


class ActivityService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def log_event(self, event: ActivityEventInput) -> None:
        metadata = sanitize_metadata(event.metadata or {})
        replay_payload = sanitize_replay_payload(event.replay_payload or {})
        record = UserActivityEvent(
            user_id=event.user_id,
            event_type=event.event_type,
            event_group=event.event_group or _event_group(event.event_type),
            request_path=event.request_path,
            http_method=event.http_method,
            route_label=event.route_label,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            folder_id=event.folder_id,
            lesson_id=event.lesson_id,
            test_session_id=event.test_session_id,
            event_metadata=metadata,
            replay_payload=replay_payload,
        )
        if event.created_at is not None:
            record.created_at = event.created_at
        async with self._session_factory() as db:
            db.add(record)
            await db.commit()

    def log_event_fire_and_forget(self, event: ActivityEventInput) -> None:
        async def _safe_log() -> None:
            try:
                await self.log_event(event)
            except Exception:
                logger.exception("Failed to log activity event %s for user %s", event.event_type, event.user_id)

        asyncio.create_task(_safe_log())

    async def list_events_for_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        period: str = "week",
        limit: int = 1000,
    ) -> list[UserActivityEvent]:
        _, since = resolve_period_start(period)
        stmt = (
            select(UserActivityEvent)
            .where(
                UserActivityEvent.user_id == user_id,
                UserActivityEvent.created_at >= since,
            )
            .order_by(UserActivityEvent.created_at.desc())
            .limit(limit)
        )
        rows = await db.scalars(stmt)
        return list(rows)

    async def get_admin_activity_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        period: str = "week",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        events = await self.list_events_for_user(
            db,
            user_id=user_id,
            period=period,
            limit=limit,
        )
        return [
            {
                "start_at": session.start_at,
                "end_at": session.end_at,
                "duration_seconds": session.duration_seconds,
                "event_count": session.event_count,
                "summary": session.summary,
                "signals": session.signals,
                "events": [
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "event_group": event.event_group,
                        "action_label": event.action_label,
                        "created_at": event.created_at,
                        "label": event.label,
                        "metadata": event.metadata,
                        "replay_payload": event.replay_payload,
                    }
                    for event in session.events
                ],
            }
            for session in build_activity_sessions(events)
        ]


def log_activity_from_request(request: Any, event: ActivityEventInput) -> None:
    service = getattr(getattr(request, "app", None), "state", None)
    activity_service = getattr(service, "activity_service", None) if service else None
    if activity_service is None:
        return
    try:
        activity_service.log_event_fire_and_forget(event)
    except Exception:
        logger.exception("Failed to enqueue activity event %s", event.event_type)
