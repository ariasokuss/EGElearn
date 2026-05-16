from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ClientActivityEventIn(BaseModel):
    event_type: str = Field(max_length=64)
    route_label: str | None = Field(default=None, max_length=255)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    lesson_id: uuid.UUID | None = None
    test_session_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClientActivityEventOut(BaseModel):
    ok: bool = True


class AdminActivityEventRow(BaseModel):
    event_id: str
    event_type: str
    event_group: str
    action_label: str
    created_at: datetime
    label: str
    metadata: dict[str, Any]
    replay_payload: dict[str, Any] = Field(default_factory=dict)


class AdminActivitySessionRow(BaseModel):
    start_at: datetime
    end_at: datetime
    duration_seconds: int
    event_count: int
    summary: str
    signals: list[str]
    events: list[AdminActivityEventRow]
