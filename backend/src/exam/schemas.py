from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class RoadmapNodeOut(BaseModel):
    id: uuid.UUID
    name: str
    level: int
    position: int
    parent_id: uuid.UUID | None
    lesson_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ExamCreate(BaseModel):
    folder_id: uuid.UUID
    name: str
    exam_date: datetime
    roadmap_nodes: list[uuid.UUID]


class ExamUpdate(BaseModel):
    name: str | None = None
    exam_date: datetime | None = None
    roadmap_nodes: list[uuid.UUID] | None = None


class ExamOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    folder_id: uuid.UUID
    name: str
    exam_date: datetime
    roadmap_nodes: list[RoadmapNodeOut] = []
    created_at: datetime
    # Average RoadmapProgress across all roadmap_nodes for the current user (0-100).
    # 0 when no progress rows exist yet.
    progress: int = 0

    model_config = {"from_attributes": True}
