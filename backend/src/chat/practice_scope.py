from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from src.auth.models import User
from src.learning.tests.session_service import TestSessionService


async def resolve_practice_scope_params(
    folder_id: str | None,
    test_session_id: str | None,
    question_id: str | None,
    current_user: User,
    tests_service: TestSessionService,
    *,
    scope_type: str | None = None,
) -> tuple[str | None, str | None]:
    if test_session_id is None and question_id is None:
        return None, None
    if test_session_id is None or question_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="test_session_id and question_id must be sent together.",
        )
    if folder_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="folder_id is required when test_session_id and question_id are set.",
        )
    try:
        ts_uuid = uuid.UUID(test_session_id)
        q_uuid = uuid.UUID(question_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="test_session_id and question_id must be valid UUIDs.",
        ) from e

    ts = await tests_service.get_session(ts_uuid, current_user.id)
    if ts is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test session not found.",
        )
    if scope_type not in ("review", "feedback_review") and ts.session_mode != "practice":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chat scope is only supported for practice test sessions.",
        )
    template = ts.template
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Test session has no template.",
        )
    if str(template.folder_id) != folder_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="folder_id does not match the test session's folder.",
        )
    if not any(q.id == q_uuid for q in template.questions):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="question_id is not part of this test session.",
        )
    return test_session_id, question_id
