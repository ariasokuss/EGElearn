from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdminSourceRow:
    source_id: uuid.UUID
    code: str
    label: str | None
    is_active: bool
    owner_user_id: uuid.UUID
    owner_email: str
    created_at: datetime
    visits_count: int
    unique_visitors: int
    registrations: int
    purchases: int


@dataclass(frozen=True)
class AdminAttributionRow:
    user_id: uuid.UUID
    email: str
    registered_at: datetime
    purchased_at: datetime | None


@dataclass(frozen=True)
class AdminVisitRow:
    visited_at: datetime
    landing_page: str | None
    visitor_id: str
    visitor_email: str | None = None


@dataclass(frozen=True)
class AdminSourceDetail:
    source: AdminSourceRow
    attributions: list[AdminAttributionRow]
    recent_visits: list[AdminVisitRow]
